"""Proxy list parsing and the ProxyEntry data model.

Tolerant of messy free-list files: optional schemes, CRLF, commas, comments,
[IPv6], user:pass@ auth, duplicates and mixed encodings.
"""

from __future__ import annotations

import ipaddress
import logging
import re
from typing import List, Optional, Set, Tuple

_log_parser = logging.getLogger("proxy.parser")

# scheme? user:pass@ host : port — one proxy token
_PROXY_RE = re.compile(
    r"(?:(?P<scheme>https?|socks5h?|socks4a?)://)?"
    r"(?:(?P<user>[^:@/\s]+):(?P<pass>[^@\s]+)@)?"
    r"(?P<host>\[[0-9A-Fa-f:.]+\]|\d{1,3}(?:\.\d{1,3}){3}"
    r"|[A-Za-z0-9](?:[A-Za-z0-9._-]{0,253}[A-Za-z0-9])?)"
    r":(?P<port>\d{1,5})"
)

# canonical scheme -> display kind
_KIND = {"http": "HTTP", "https": "HTTP", "socks5": "SOCKS5",
         "socks5h": "SOCKS5", "socks4": "SOCKS4", "socks4a": "SOCKS4"}


class ProxyEntry:
    """One proxy and its latest check state (slots keep 800+ rows cheap)."""

    __slots__ = ("scheme", "kind", "host", "port", "user", "password",
                 "index", "state", "alive", "latency", "exit_ip", "exit_cc",
                 "country", "error", "flash_ts")

    def __init__(self, scheme: str, kind: str, host: str, port: int,
                 user: str = "", password: str = "", index: int = 0) -> None:
        self.scheme, self.kind = scheme, kind
        self.host, self.port = host, port
        self.user, self.password = user, password
        self.index = index
        self.state = "idle"          # idle | queued | done
        self.alive = False
        self.latency: Optional[int] = None
        self.exit_ip: Optional[str] = None
        self.exit_cc: Optional[str] = None      # ISO code, for flags
        self.country: Optional[str] = None
        self.error: Optional[str] = None
        self.flash_ts = 0.0

    @property
    def uri(self) -> str:
        """Round-trippable form: socks5://1.2.3.4:1080"""
        return f"{self.scheme}://{self.host}:{self.port}"

    def reset(self) -> None:
        """Clear all check results (before a scan)."""
        self.state, self.alive = "idle", False
        self.latency = self.exit_ip = self.exit_cc = self.country = None
        self.error = None
        self.flash_ts = 0.0


def _valid_host(host: str) -> bool:
    """Accept [IPv6], dotted quads with octets <=255, sane hostnames."""
    if host.startswith("[") and host.endswith("]"):
        try:
            ipaddress.IPv6Address(host[1:-1])
            return True
        except ValueError:
            return False
    if re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}", host):
        return all(int(o) <= 255 for o in host.split("."))
    return len(host) <= 254


def parse_proxy_line(line: str) -> Optional[ProxyEntry]:
    """Parse one token: 'socks5://1.2.3.4:1080', '1.2.3.4:8080', '[::1]:80'...

    Returns None for comments/blank lines/garbage.
    """
    line = line.strip().strip(",").strip(";")
    if not line or line.startswith("#"):
        return None
    m = _PROXY_RE.fullmatch(line)
    if not m:
        return None
    scheme = (m.group("scheme") or "http").lower()
    kind = _KIND.get(scheme)
    if not kind:
        return None
    host = m.group("host")
    if host.startswith("["):
        host = host[1:-1]
    port = int(m.group("port"))
    if not (1 <= port <= 65535) or not _valid_host(m.group("host")):
        return None
    return ProxyEntry(scheme, kind, host, port,
                      m.group("user") or "", m.group("pass") or "")


def load_proxy_list(path: str) -> Tuple[List[ProxyEntry], int]:
    """Read a whole list file.

    Tries UTF-8 -> UTF-16 -> Latin-1, splits on newlines and commas, drops
    duplicates (proto+host+port). Returns (entries, skipped_count).
    """
    raw = ""
    for enc in ("utf-8", "utf-16", "latin-1"):
        try:
            with open(path, "r", encoding=enc) as fh:
                raw = fh.read()
            break
        except UnicodeError:
            continue

    entries: List[ProxyEntry] = []
    seen: Set[Tuple[str, str, int]] = set()
    skipped = 0
    for chunk in re.split(r"[\r\n]+", raw):
        for token in chunk.split(","):
            e = parse_proxy_line(token)
            if e is None:
                tok = token.strip()
                if tok and not tok.startswith("#"):
                    skipped += 1
                    _log_parser.debug("skipped token: %r", tok[:80])
                continue
            key = (e.kind, e.host, e.port)
            if key in seen:
                skipped += 1
                continue
            seen.add(key)
            e.index = len(entries)
            entries.append(e)
    _log_parser.info("parsed %d unique proxies from %s (%d skipped)",
                     len(entries), path, skipped)
    return entries, skipped
