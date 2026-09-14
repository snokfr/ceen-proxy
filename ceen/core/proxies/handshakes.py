"""Raw-socket proxy protocol handshakes — HTTP-CONNECT, SOCKS4, SOCKS5.

This is the code that actually *talks* to a proxy server, byte by byte,
with no outside libraries. Each handshake either succeeds silently or
raises ProxyError with a short reason ("timeout", "socks5 auth required",
"connect 403") that the app can show to the user.
"""

from __future__ import annotations

import base64
import ipaddress
import logging
import re
import socket
import ssl
import time
from typing import NamedTuple, Optional, Tuple

from ceen.core.proxies.entry import ProxyEntry

_log_checker = logging.getLogger("proxy.checker")


class CheckResult(NamedTuple):
    """Outcome of one proxy check."""
    alive: bool
    latency_ms: Optional[int]
    exit_ip: Optional[str]
    exit_cc: Optional[str]      # ISO country code (for flags)
    country: Optional[str]
    error: Optional[str]


class _Timeout(Exception):
    """Internal: our own deadline (finer-grained than socket timeouts)."""


class ProxyError(Exception):
    """Protocol-level failure with a short user-facing message."""


_IP_BODY_RE = re.compile(r"(?<![\w.])(\d{1,3}(?:\.\d{1,3}){3})(?![\w.])")


def classify(exc: BaseException) -> str:
    """Map an exception to a short reason string."""
    if isinstance(exc, (socket.timeout, TimeoutError, _Timeout)):
        return "timeout"
    if isinstance(exc, ConnectionRefusedError):
        return "refused"
    if isinstance(exc, ConnectionResetError):
        return "reset"
    if isinstance(exc, ConnectionAbortedError):
        return "aborted"
    if isinstance(exc, PermissionError):
        return "forbidden"
    if isinstance(exc, socket.gaierror):
        return "dns error"
    return (str(exc).strip() or exc.__class__.__name__)[:64]


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
    if entry.user:
        token = base64.b64encode(
            f"{entry.user}:{entry.password}".encode()).decode()
        return f"Proxy-Authorization: Basic {token}\r\n"
    return ""


# ── protocol handshakes (public: the rotator reuses them) ────────────────────

def socks5_handshake(sock: socket.socket, entry: ProxyEntry,
                     host: str, port: int, deadline: float) -> None:
    """SOCKS5 CONNECT with optional user/pass auth."""
    methods = b"\x02\x00" if entry.user else b"\x00"
    sock.sendall(b"\x05\x01" + bytes([len(methods)]) + methods)
    resp = _recv_exact(sock, 2, deadline)
    if resp[0] != 5:
        raise ProxyError("bad socks5 reply")
    if resp[1] == 0xFF:
        raise ProxyError("socks5 auth required")
    if resp[1] == 2:                                   # server wants auth
        if not entry.user:
            raise ProxyError("socks5 auth required")
        u, p = entry.user.encode(), entry.password.encode()
        sock.sendall(b"\x01" + bytes([len(u)]) + u + bytes([len(p)]) + p)
        if _recv_exact(sock, 2, deadline)[1] != 0:
            raise ProxyError("socks5 auth failed")
    elif resp[1] != 0:
        raise ProxyError("socks5 no acceptable method")
    # request: prefer raw IP; fall back to domain (ATYP=3)
    try:
        ip = ipaddress.ip_address(host)
        atyp, addr = (4, ip.packed) if ip.version == 6 else (1, ip.packed)
    except ValueError:
        atyp, addr = 3, host.encode("idna")[:255]
    if atyp == 3:
        req = b"\x05\x01\x00\x03" + bytes([len(addr)]) + addr \
            + port.to_bytes(2, "big")
    else:
        req = b"\x05\x01\x00" + bytes([atyp]) + addr + port.to_bytes(2, "big")
    sock.sendall(req)
    rep = _recv_exact(sock, 4, deadline)
    if rep[0] != 5:
        raise ProxyError("bad socks5 reply")
    if rep[1] != 0:
        reasons = {1: "socks5 general failure", 2: "socks5 not allowed",
                   3: "socks5 net unreachable", 4: "socks5 host unreachable",
                   5: "socks5 refused", 6: "socks5 ttl expired",
                   7: "socks5 cmd unsupported", 8: "socks5 addr unsupported"}
        raise ProxyError(reasons.get(rep[1], f"socks5 error {rep[1]}"))
    # drain bound address: IPv4(4) / IPv6(16) / domain(1-byte len + name)
    tail = {1: 4, 4: 16}.get(rep[3])
    if tail is None:
        tail = 1 + _recv_exact(sock, 1, deadline)[0]
    _recv_exact(sock, tail + 2, deadline)


def socks4_handshake(sock: socket.socket, entry: ProxyEntry,
                     host: str, port: int, deadline: float) -> None:
    """SOCKS4 CONNECT — DNS-SAFE: hostnames are NEVER resolved here.

    Classic SOCKS4 wants a raw IP, and resolving one locally would leak
    every site name to your ISP's DNS servers. So hostnames go out as
    SOCKS4a (protocol extension: the PROXY does the resolving). If a
    proxy is too old for SOCKS4a it simply fails the handshake — the
    caller benches it and rotates to the next server. Privacy wins.
    """
    try:
        packed, tail = socket.inet_aton(host), b""      # literal IP: fine
    except OSError:
        packed = b"\x00\x00\x00\x01"                   # SOCKS4a marker
        tail = host.encode("idna")[:255] + b"\x00"      # name for the proxy
    uid = entry.user.encode()[:255]
    sock.sendall(b"\x04\x01" + port.to_bytes(2, "big") + packed + uid
                 + b"\x00" + tail)
    resp = _recv_exact(sock, 8, deadline)
    if resp[1] != 0x5A:
        codes = {0x5B: "socks4 rejected", 0x5C: "socks4 no identd",
                 0x5D: "socks4 ident mismatch"}
        raise ProxyError(codes.get(resp[1], f"socks4 error {resp[1]}"))


def http_connect(sock: socket.socket, entry: ProxyEntry,
                 host: str, port: int, deadline: float) -> None:
    """HTTP CONNECT tunnel (used for HTTPS through plain proxies)."""
    req = (f"CONNECT {host}:{port} HTTP/1.1\r\nHost: {host}:{port}\r\n"
           + _auth_header(entry) + "\r\n")
    sock.sendall(req.encode())
    parts = _recv_until_headers(sock, deadline).split(b"\r\n", 1)[0].split()
    if len(parts) < 2 or not parts[0].startswith(b"HTTP"):
        raise ProxyError("bad connect reply")
    try:
        code = int(parts[1])
    except (ValueError, IndexError):
        raise ProxyError("bad connect reply")
    if not (200 <= code < 300):
        raise ProxyError(f"connect {code}")


def tls_wrap(sock: socket.socket, host: str) -> socket.socket:
    """Upgrade to TLS; retry unverified if the system CA bundle fails."""
    try:
        return ssl.create_default_context().wrap_socket(
            sock, server_hostname=host)
    except ssl.SSLError:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx.wrap_socket(sock, server_hostname=host)
