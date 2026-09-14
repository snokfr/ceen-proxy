"""What's my (real) IP? — the number that should CHANGE when connected.

Fetched without any proxy (your ISP IP) or through the tunnel (your
exit IP). Displaying both is how you *prove* the VPN reroute works.
"""

from __future__ import annotations

import json
import logging
import re
import socket
from typing import Optional

_log = logging.getLogger("proxy.ipcheck")

# Plain-HTTP IP echo services (fast, tiny, no TLS overhead).
_URL = "http://ip-api.com/json/?fields=query,country,countryCode"
_IPV4_RE = re.compile(r"(\d{1,3}(?:\.\d{1,3}){3})")


def _looks_ip(s: str) -> bool:
    if not _IPV4_RE.fullmatch(s):
        return False
    return all(int(o) <= 255 for o in s.split("."))


def direct_ip_probe(timeout: float = 4.0) -> Optional[str]:
    """Your DIRECT ip (no proxy involved). Safe to call from any thread."""
    try:
        import urllib.request
        req = urllib.request.Request(
            _URL, headers={"User-Agent": "Mozilla/5.0 (CeenProxy)"})
        # explicitly no proxy handler:
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}))
        with opener.open(_URL, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8", "replace"))
        ip = str(data.get("query", ""))
        return ip if _looks_ip(ip) else None
    except Exception as exc:  # noqa: BLE001 — best effort only
        _log.debug("direct ip probe: %s", exc)
        return None
