"""ProxyPool — the basket of working servers your traffic rotates through.

Thread-safe so the network threads and the window can share it. Also
contains `group_by_country()`, which shapes the alive list into the
"servers by country" view used on the Connect screen, and
`upstream_connect()`, which opens a tunnelled connection through one
proxy (used by the rotator for every site you visit).
"""

from __future__ import annotations

import logging
import socket
import threading
import time
from typing import Dict, List, Optional, Set, Tuple

from ceen.core.proxies.handshakes import http_connect, socks4_handshake, \
    socks5_handshake
from ceen.core.proxies.entry import ProxyEntry
from ceen.utils.textutil import country_name

_log = logging.getLogger("proxy.pool")


def group_by_country(servers: List[ProxyEntry]) \
        -> List[Tuple[str, str, List[ProxyEntry]]]:
    """Group alive servers by country: [(name, cc, [servers fastest-first])].

    Groups are sorted by their best latency; servers inside each group are
    sorted by latency too so `servers[0]` is the country's connect target.
    """
    buckets: Dict[str, List[ProxyEntry]] = {}
    names: Dict[str, str] = {}
    for e in servers:
        cc = (e.exit_cc or "").upper() or "??"
        buckets.setdefault(cc, []).append(e)
        if e.country and cc not in names:
            names[cc] = e.country
    groups: List[Tuple[str, str, List[ProxyEntry]]] = []
    for cc, srv in buckets.items():
        srv.sort(key=lambda e: e.latency if e.latency else 10 ** 9)
        groups.append((country_name(cc, names.get(cc)), cc, srv))
    groups.sort(key=lambda g: min((e.latency or 10 ** 9) for e in g[2]))
    return groups


def upstream_connect(entry: ProxyEntry, host: str, port: int,
                     timeout: float) -> socket.socket:
    """Open host:port THROUGH a SOCKS/HTTP proxy entry (tunnel)."""
    sock = socket.create_connection((entry.host, entry.port), timeout=timeout)
    try:
        sock.settimeout(timeout)
        deadline = time.perf_counter() + timeout
        if entry.kind == "SOCKS5":
            socks5_handshake(sock, entry, host, port, deadline)
        elif entry.kind == "SOCKS4":
            socks4_handshake(sock, entry, host, port, deadline)
        else:
            http_connect(sock, entry, host, port, deadline)
        return sock
    except Exception:
        try:
            sock.close()
        except OSError:
            pass
        raise


class ProxyPool:
    """Thread-safe round-robin over alive proxies with an optional sticky one."""

    def __init__(self, entries: Optional[List[ProxyEntry]] = None) -> None:
        self._lock = threading.Lock()
        self._entries = self._sorted(entries or [])
        self._rr = 0
        self.sticky: Optional[ProxyEntry] = None

    @staticmethod
    def _sorted(entries: List[ProxyEntry]) -> List[ProxyEntry]:
        return sorted(entries, key=lambda e: e.latency if e.latency else 10 ** 9)

    def next(self) -> Optional[ProxyEntry]:
        """Next server in rotation (sticky one wins if still present)."""
        with self._lock:
            if self.sticky is not None and self.sticky in self._entries:
                return self.sticky
            if not self._entries:
                return None
            e = self._entries[self._rr % len(self._entries)]
            self._rr += 1
            return e

    def disable(self, entry: ProxyEntry) -> None:
        """Bench a server that failed mid-use (auto-rotation)."""
        with self._lock:
            if entry in self._entries:
                self._entries.remove(entry)
            if self.sticky is entry:
                self.sticky = None

    def set_sticky(self, entry: Optional[ProxyEntry]) -> None:
        """Pin (or unpin) one exit server."""
        with self._lock:
            self.sticky = entry

    def reorder(self, preferred: Set[str]) -> None:
        """Move starred backup servers to the front of rotation."""
        with self._lock:
            pref = [e for e in self._entries if e.uri in preferred]
            rest = [e for e in self._entries if e.uri not in preferred]
            self._entries = pref + rest
            self._rr = 0

    def set_entries(self, entries: List[ProxyEntry]) -> None:
        """Replace the alive set (after a fresh scan) and keep stickiness."""
        with self._lock:
            self._entries = self._sorted(entries)
            if self.sticky is not None and self.sticky not in self._entries:
                self.sticky = None

    def snapshot(self) -> List[ProxyEntry]:
        """Copy of the alive set, fastest first (for UI rendering)."""
        with self._lock:
            return list(self._sorted(self._entries))

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)
