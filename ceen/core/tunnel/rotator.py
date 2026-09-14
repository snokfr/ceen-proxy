"""RotatorServer — Ceen's "VPN tunnel": a small proxy on your own PC.

Apps send traffic to 127.0.0.1:<port>; we forward it through a working
proxy, retrying on the next one if a proxy dies mid-session.
"""

from __future__ import annotations

import logging
import re
import socket
import threading
import time
from typing import Callable, Optional, Set
from urllib.parse import urlparse

from ceen.core.proxies.handshakes import ProxyError
from ceen.core.tunnel.pipes import pipe_both, pipe_one
from ceen.core.tunnel.pool import ProxyPool, upstream_connect
from ceen.utils.textutil import fmt_bytes

_log_rotator = logging.getLogger("proxy.rotator")


def _close_quietly(sock: Optional[socket.socket]) -> None:
    """Close a network connection, ignoring 'already closed' errors."""
    if sock is None:
        return
    try:
        sock.close()
    except OSError:
        pass


class RotatorServer(threading.Thread):
    """Local HTTP + CONNECT forward proxy rotating through a ProxyPool."""

    def __init__(self, port: int, pool: ProxyPool, timeout: float = 6.0) -> None:
        super().__init__(name="rotator", daemon=True)
        self.pool = pool
        self.port = port
        self.timeout = timeout
        self.on_pool_change: Optional[Callable[[], None]] = None
        self._stop = threading.Event()
        self._serv: Optional[socket.socket] = None
        self._ready = threading.Event()
        self._conns: Set[socket.socket] = set()
        self._conn_lock = threading.Lock()
        self.requests = 0
        self.bytes_up = 0
        self.bytes_down = 0
        self.active = 0
        self.last_error: Optional[str] = None

    # ── lifecycle ────────────────────────────────────────────────────────
    def run(self) -> None:
        try:
            self._serv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._serv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._serv.bind(("127.0.0.1", self.port))
            self._serv.listen(64)
            self._serv.settimeout(0.5)
        except OSError as exc:
            _log_rotator.error("cannot bind 127.0.0.1:%d — %s", self.port, exc)
            self.last_error = f"bind: {exc}"
            self._serv = None
            return
        self._ready.set()
        _log_rotator.info("rotator listening on 127.0.0.1:%d (%d servers)",
                          self.port, len(self.pool))
        while not self._stop.is_set():
            try:
                conn, _addr = self._serv.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(target=self._client, args=(conn,),
                             name="rot-conn", daemon=True).start()
        _close_quietly(self._serv)
        _log_rotator.info("rotator stopped")

    def stop(self) -> None:
        self._stop.set()
        with self._conn_lock:
            conns = list(self._conns)
        for c in conns:
            try:
                c.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            _close_quietly(c)
        _close_quietly(self._serv)

    def wait_ready(self, timeout: float = 2.0) -> bool:
        """Wait until the listener is actually accepting connections.

        Returns False if the port could not be bound — the caller can
        fail the connect instantly instead of talking to a dead port.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._stop.is_set():
                return False
            if self.last_error:
                return False                      # bind already failed
            if self._ready.is_set():
                return True
            time.sleep(0.02)
        return self._ready.is_set()

    # ── stats ────────────────────────────────────────────────────────────
    def stats(self) -> Tuple[int, int, int, int]:
        with self._conn_lock:
            active = self.active
        return self.requests, self.bytes_up, self.bytes_down, active

    def _notify_pool(self) -> None:
        cb = self.on_pool_change
        if cb:
            try:
                cb()
            except Exception:  # noqa: BLE001
                pass

    # ── per-connection ───────────────────────────────────────────────────
    def _client(self, conn: socket.socket) -> None:
        with self._conn_lock:
            self._conns.add(conn)
            self.active += 1
        try:
            conn.settimeout(self.timeout)
            head = self._recv_head(conn)
            if head is None:
                return
            line = head.split(b"\r\n", 1)[0].decode("latin-1")
            parts = line.split()
            if len(parts) >= 3 and parts[0].upper() == "CONNECT":
                self._do_connect(conn, parts[1])
            elif len(parts) >= 3:
                self._do_http(conn, parts[0].upper(), parts[1], head)
            else:
                _log_rotator.debug("malformed request line: %r", line[:80])
        except (OSError, socket.timeout):
            pass
        except Exception as exc:  # noqa: BLE001 — a rotator must not die
            _log_rotator.debug("client error: %s", exc)
        finally:
            with self._conn_lock:
                self.active -= 1
                self._conns.discard(conn)
            _close_quietly(conn)

    @staticmethod
    def _recv_head(sock: socket.socket, cap: int = 65536) -> Optional[bytes]:
        buf = bytearray()
        while b"\r\n\r\n" not in buf:
            if len(buf) > cap:
                return None
            try:
                chunk = sock.recv(4096)
            except (socket.timeout, TimeoutError):
                return None
            if not chunk:
                return None
            buf += chunk
        return bytes(buf)

    # ── CONNECT tunneling ────────────────────────────────────────────
    def _do_connect(self, conn: socket.socket, target: str) -> None:
        host, _, port_s = target.rpartition(":")
        try:
            port = int(port_s)
        except ValueError:
            conn.sendall(b"HTTP/1.1 400 Bad Request\r\n\r\n")
            return
        self.requests += 1
        _log_rotator.info("CONNECT %s:%d", host, port)
        upstream = self._via_any(host, port)
        if upstream is None:
            conn.sendall(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
            return
        try:
            conn.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")
            up, down = self._pipe_both(conn, upstream)
            self.bytes_up += up
            self.bytes_down += down
            _log_rotator.debug("tunnel %s:%d closed (%s up / %s down)",
                               host, port, fmt_bytes(up), fmt_bytes(down))
        finally:
            _close_quietly(upstream)

    # ── plain HTTP forwarding ─────────────────────────────────────────
    def _do_http(self, conn: socket.socket, method: str, target: str,
                 head: bytes) -> None:
        body = b""
        m = re.search(rb"(?i)\bcontent-length:\s*(\d+)", head)
        if m:
            need = int(m.group(1))
            body = head.split(b"\r\n\r\n", 1)[1] if b"\r\n\r\n" in head else b""
            body = body[:need]
            while len(body) < need:
                chunk = conn.recv(min(65536, need - len(body)))
                if not chunk:
                    break
                body += chunk
        u = urlparse(target)
        if u.hostname:
            host, port = u.hostname, u.port or 80
            shown = (u.path or "/") + (("?" + u.query) if u.query else "")
        else:
            hm = re.search(rb"(?i)\r\nhost:\s*([^\r\n]+)", head)
            if not hm:
                conn.sendall(b"HTTP/1.1 400 Bad Request\r\n\r\n")
                return
            hp = hm.group(1).decode("latin-1").strip()
            host, _, port_s = hp.partition(":")
            port = int(port_s) if port_s else 80
            shown = target
        self.requests += 1
        _log_rotator.info("%s http://%s:%d%s", method, host, port, shown)
        for _attempt in range(3):
            entry = self.pool.next()
            if entry is None:
                break
            committed = False
            sock: Optional[socket.socket] = None
            try:
                if entry.kind == "HTTP":
                    sock = socket.create_connection((entry.host, entry.port),
                                                    timeout=self.timeout)
                    sock.settimeout(self.timeout)
                    req = self._rewrite_head(head, None)
                else:
                    path = (u.path or "/") + \
                        (("?" + u.query) if u.query else "")
                    sock = upstream_connect(entry, host, port, self.timeout)
                    req = self._rewrite_head(head, path)
                sock.sendall(req + body)
                resp = self._recv_head(sock)
                if resp is None:
                    raise ProxyError("empty upstream response")
                conn.sendall(resp)
                committed = True
                down = len(resp) + self._pipe_up_to_client(sock, conn)
                self.bytes_down += down
                self.bytes_up += len(req) + len(body)
                _log_rotator.debug("%s %s:%d via %s — %s down", method, host,
                                   port, entry.uri, fmt_bytes(down))
                return
            except Exception as exc:  # noqa: BLE001 — rotate to next server
                _log_rotator.warning("upstream %s failed: %s%s", entry.uri,
                                     exc,
                                     " (mid-stream)" if committed else "")
                self.last_error = f"{entry.uri}: {exc}"
                _close_quietly(sock)
                if not committed:
                    self.pool.disable(entry)
                    self._notify_pool()
                    continue
                return
        try:
            conn.sendall(b"HTTP/1.1 502 Bad Gateway\r\n\r\n"
                         b"Content-Type: text/plain\r\n"
                         b"Connection: close\r\n\r\nproxy chain failed\n")
        except OSError:
            pass
        _log_rotator.error("all upstreams failed for %s:%d", host, port)

    @staticmethod
    def _rewrite_head(head: bytes, path: Optional[str]) -> bytes:
        head_part, _, body_part = head.partition(b"\r\n\r\n")
        lines = head_part.split(b"\r\n")
        if path is not None:
            parts = lines[0].split(b" ")
            if len(parts) >= 2:
                parts[1] = path.encode("latin-1")
                lines[0] = b" ".join(parts)
        out = [lines[0]]
        for ln in lines[1:]:
            if ln.lower().startswith((b"proxy-authorization:",
                                      b"proxy-connection:", b"connection:",
                                      b"keep-alive:")):
                continue
            out.append(ln)
        out.append(b"Connection: close")
        return b"\r\n".join(out) + b"\r\n\r\n" + body_part

    # ── upstream selection with auto-rotation ─────────────────────────
    def _via_any(self, host: str, port: int) -> Optional[socket.socket]:
        for _attempt in range(3):
            entry = self.pool.next()
            if entry is None:
                break
            try:
                if entry.kind == "HTTP":
                    sock = socket.create_connection((entry.host, entry.port),
                                                    timeout=self.timeout)
                    sock.settimeout(self.timeout)
                else:
                    sock = upstream_connect(entry, host, port, self.timeout)
                _log_rotator.debug("via %s", entry.uri)
                return sock
            except Exception as exc:  # noqa: BLE001
                _log_rotator.warning("upstream %s failed: %s — rotating",
                                     entry.uri, exc)
                self.last_error = f"{entry.uri}: {exc}"
                self.pool.disable(entry)
                self._notify_pool()
        _log_rotator.error("no working upstream for %s:%d", host, port)
        return None

    # ── byte pumps (the real work lives in pipes.py) ────────────────
    def _pipe_both(self, a: socket.socket, b: socket.socket) -> tuple:
        """Copy bytes both ways until a side closes (see pipes.py)."""
        return pipe_both(a, b, self._stop)

    def _pipe_up_to_client(self, up: socket.socket,
                           client: socket.socket) -> int:
        """Copy the reply stream back to the app (see pipes.py)."""
        return pipe_one(up, client, self._stop)

