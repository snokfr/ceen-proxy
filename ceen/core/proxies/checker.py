"""Proxy check pipeline: connect -> handshake -> fetch test URL -> read result.

`check_proxy()` is the one-call tester: give it a proxy and it returns
whether the proxy works, how fast it was, and which country it exits
from. It never raises — every failure comes back as a short reason
string so the interface can always explain itself.
"""

from __future__ import annotations

import json
import logging
import re
import socket
import time
from typing import Optional, Tuple
from urllib.parse import urlparse

from ceen.core.proxies.handshakes import (CheckResult, ProxyError, _Timeout,
                                          classify, http_connect,
                                          socks4_handshake, socks5_handshake,
                                          tls_wrap)
from ceen.core.proxies.entry import ProxyEntry

_log = logging.getLogger("proxy.checker")

# A plausible IPv4 anywhere in a response body.
_IP_RE = re.compile(r"(?<![\w.])(\d{1,3}(?:\.\d{1,3}){3})(?![\w.])")


# ── low-level receive helpers (deadline-driven) ──────────────────────────────

def _recv_exact(sock: socket.socket, n: int, deadline: float) -> bytes:
    """Receive exactly n bytes or raise _Timeout / ProxyError."""
    buf = bytearray()
    while len(buf) < n:
        if time.perf_counter() > deadline:
            raise _Timeout()
        try:
            chunk = sock.recv(n - len(buf))
        except (socket.timeout, TimeoutError):
            raise _Timeout()
        if not chunk:
            raise ProxyError("closed early")
        buf += chunk
    return bytes(buf)


def _recv_until_headers(sock: socket.socket, deadline: float,
                        cap: int = 32768) -> bytes:
    """Receive until the \r\n\r\n header terminator (or EOF)."""
    buf = bytearray()
    while b"\r\n\r\n" not in buf:
        if len(buf) > cap:
            raise ProxyError("header flood")
        if time.perf_counter() > deadline:
            raise _Timeout()
        try:
            chunk = sock.recv(4096)
        except (socket.timeout, TimeoutError):
            raise _Timeout()
        if not chunk:
            break
        buf += chunk
    return bytes(buf)


def _read_body(sock: socket.socket, head: bytes, rest: bytes,
               deadline: float) -> bytes:
    """Read a body honouring Content-Length; otherwise read until close."""
    m = re.search(rb"(?i)\bcontent-length:\s*(\d+)", head)
    cl = int(m.group(1)) if m else 0
    buf = bytearray(rest[:cl] if cl else rest)
    while (cl and len(buf) < cl) or (not cl):
        if len(buf) > 262144:
            break
        if time.perf_counter() > deadline:
            if cl:
                raise _Timeout()
            break
        try:
            chunk = sock.recv(8192)
        except (socket.timeout, TimeoutError):
            if cl:
                raise _Timeout()
            break
        if not chunk:
            break
        buf += chunk
    return bytes(buf[:cl] if cl else buf)


def _auth_header(entry: ProxyEntry) -> str:
    """Proxy-Authorization header for the entry's credentials, or ''."""
    import base64
    if entry.user:
        token = base64.b64encode(
            f"{entry.user}:{entry.password}".encode()).decode()
        return f"Proxy-Authorization: Basic {token}\r\n"
    return ""


# ── response parsing ─────────────────────────────────────────────────────────

def _looks_ip(s: str) -> bool:
    if not re.fullmatch(r"(\d{1,3}\.){3}\d{1,3}", s):
        return False
    return all(int(o) <= 255 for o in s.split("."))


def extract_exit_ip(text: str, proxy_host: str = "") -> Optional[str]:
    """Pull the exit IP out of a test-service body (JSON, line or raw)."""
    try:  # JSON services report the exit in "query"/"ip"/...
        data = json.loads(text)
        if isinstance(data, dict):
            for key in ("query", "ip", "ip_addr", "address"):
                v = data.get(key)
                if isinstance(v, str) and _looks_ip(v.strip()):
                    return v.strip()
    except Exception:  # noqa: BLE001 — body is not JSON, fall through
        pass
    for ln in text.splitlines():          # line-mode: IP on its own line
        ln = ln.strip()
        if _looks_ip(ln) and ln != proxy_host:
            return ln
    for m in _IP_RE.finditer(text):       # last resort: first plausible IPv4
        if _looks_ip(m.group(1)) and m.group(1) != proxy_host:
            return m.group(1)
    return None


def extract_geo(text: str) -> Tuple[Optional[str], Optional[str]]:
    """Return (country_name, country_code) from a test-service body."""
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            name = data.get("country") or data.get("countryName")
            cc = data.get("countryCode") or data.get("country_code")
            cc = str(cc).upper()[:2] if cc else None
            return (name if isinstance(name, str) else None, cc)
    except Exception:  # noqa: BLE001 — not JSON, try line mode
        pass
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if lines and lines[0].lower() == "success" and len(lines) > 2:
        return lines[1], lines[2].upper()[:2]
    return None, None


# ── the full check ───────────────────────────────────────────────────────────

def _fetch(sock: socket.socket, entry: ProxyEntry, test_url: str,
           deadline: float, tunneled: bool) -> Tuple[int, bytes]:
    """GET the test URL (absolute-URI for plain HTTP, inner req when tunneled)."""
    u = urlparse(test_url)
    thost = u.hostname or "ip-api.com"
    path = (u.path or "/") + (("?" + u.query) if u.query else "")
    if tunneled:
        # HTTP/1.0 inner request: close-delimited reply, never chunked.
        req = (f"GET {path} HTTP/1.0\r\nHost: {thost}\r\n"
               f"User-Agent: Mozilla/5.0 (CeenProxy)\r\nAccept: */*\r\n\r\n")
    else:  # plain HTTP proxy: absolute-URI request
        req = (f"GET {u.scheme}://{thost}:{u.port or 80}{path} HTTP/1.0\r\n"
               f"Host: {thost}\r\nUser-Agent: Mozilla/5.0 (CeenProxy)\r\n"
               f"Accept: */*\r\n" + _auth_header(entry) + "\r\n")
    sock.sendall(req.encode())
    head = _recv_until_headers(sock, deadline)
    parts = head.split(b"\r\n", 1)[0].split()
    if len(parts) < 2 or not parts[0].startswith(b"HTTP"):
        raise ProxyError("bad response")
    try:
        status = int(parts[1])
    except (ValueError, IndexError):
        raise ProxyError("bad response")
    header, _, rest = head.partition(b"\r\n\r\n")
    return status, _read_body(sock, header, rest, deadline)


def check_proxy(entry: ProxyEntry, test_url: str, timeout: float) -> CheckResult:
    """Full proxy test. Never raises — every failure becomes a reason string."""
    t0 = time.perf_counter()
    deadline = t0 + timeout
    u = urlparse(test_url)
    thost = u.hostname or "ip-api.com"
    tport = u.port or (443 if u.scheme == "https" else 80)
    sock: Optional[socket.socket] = None
    try:
        try:
            sock = socket.create_connection((entry.host, entry.port),
                                            timeout=timeout)
        except OSError as exc:
            return CheckResult(False, None, None, None, None, classify(exc))
        sock.settimeout(max(0.05, deadline - time.perf_counter()))

        tunneled = False
        if entry.kind == "SOCKS5":
            socks5_handshake(sock, entry, thost, tport, deadline)
            tunneled = True
        elif entry.kind == "SOCKS4":
            socks4_handshake(sock, entry, thost, tport, deadline)
            tunneled = True
        if u.scheme == "https":
            if not tunneled:
                http_connect(sock, entry, thost, tport, deadline)
            sock = tls_wrap(sock, thost)
            tunneled = True

        sock.settimeout(max(0.05, deadline - time.perf_counter()))
        status, body = _fetch(sock, entry, test_url, deadline, tunneled)
        latency = int((time.perf_counter() - t0) * 1000)
        if not (200 <= status < 400):
            return CheckResult(False, latency, None, None, None, f"http {status}")
        text = body.decode("utf-8", "replace")
        country, cc = extract_geo(text)
        return CheckResult(True, latency, extract_exit_ip(text, entry.host),
                           cc, country, None)
    except _Timeout:
        lat = int((time.perf_counter() - t0) * 1000) if sock else None
        return CheckResult(False, lat, None, None, None, "timeout")
    except ProxyError as exc:
        return CheckResult(False, None, None, None, None, str(exc)[:64])
    except OSError as exc:
        return CheckResult(False, None, None, None, None, classify(exc))
    except Exception as exc:  # noqa: BLE001 — a checker must never crash the pool
        return CheckResult(False, None, None, None, None, f"error: {exc}"[:64])
    finally:
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
