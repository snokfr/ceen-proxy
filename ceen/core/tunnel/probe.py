"""Exit verification: fetch the test URL THROUGH the local rotator.

Used by the Connect panel to prove the tunnel really works and to show
which country you are actually exiting from.
"""

from __future__ import annotations

import socket
from typing import Optional, Tuple
from urllib.parse import urlparse

from ceen.config import DEFAULT_TEST_URL
from ceen.core.proxies.checker import extract_exit_ip, extract_geo
from ceen.core.proxies.handshakes import ProxyError


def probe_via_rotator(port: int, timeout: float = 7.0,
                      url: str = DEFAULT_TEST_URL
                      ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """GET the test URL via 127.0.0.1:port.

    Returns (exit_ip, country_name, country_code); raises ProxyError if the
    rotator or every upstream failed.
    """
    u = urlparse(url)
    sock = socket.create_connection(("127.0.0.1", port), timeout=timeout)
    try:
        sock.settimeout(timeout)
        sock.sendall((f"GET {url} HTTP/1.1\r\nHost: {u.hostname}\r\n"
                      f"User-Agent: Mozilla/5.0 (CeenProxy probe)\r\n"
                      f"Connection: close\r\n\r\n").encode())
        buf = bytearray()
        while len(buf) < 131072:
            try:
                chunk = sock.recv(8192)
            except (socket.timeout, TimeoutError):
                break
            if not chunk:
                break
            buf += chunk
        text = bytes(buf).decode("utf-8", "replace")
        if "\r\n\r\n" not in text:
            raise ProxyError("empty probe response")
        status = int(text.split(" ", 2)[1])
        body = text.split("\r\n\r\n", 1)[1]
        if not (200 <= status < 400):
            raise ProxyError(f"probe http {status}")
        country, cc = extract_geo(body)
        return extract_exit_ip(body, ""), country, cc
    finally:
        try:
            sock.close()
        except OSError:
            pass
