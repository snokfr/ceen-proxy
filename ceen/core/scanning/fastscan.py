"""Fast "is anything listening?" pre-check — the scan speed trick.

Checking a full proxy can take up to the whole timeout (6s) when a
server is dead, because protocols wait for handshakes. But ~90% of dead
free proxies can't even open a TCP connection. So: a 2.5-second plain
TCP connect first. Nothing listening? Skip the expensive test entirely.
Alive ones go straight to the full check (they were going to pass this
step instantly anyway), so nothing is lost — dead ones just fail 2x
sooner.
"""

from __future__ import annotations

import socket
from typing import List, Tuple

from ceen.core.proxies.entry import ProxyEntry

# (workers who only pre-check, seconds for the pre-check)
# A server that ACCEPTS connections does so almost instantly, so 1.5s
# is generous; anything slower is dead weight for a free-proxy list.
PRECHECK_TIMEOUT = 1.5
PRECHECK_WORKERS = 400


def tcp_alive(entry: ProxyEntry, timeout: float = PRECHECK_TIMEOUT) -> bool:
    """True if the proxy's port accepts a TCP connection quickly."""
    try:
        sock = socket.create_connection((entry.host, entry.port),
                                        timeout=timeout)
        sock.close()
        return True
    except OSError:
        return False


def split_alive_guess(entries: List[ProxyEntry], workers: int) \
        -> Tuple[List[ProxyEntry], int]:
    """Pre-check a chunk of entries with many threads.

    Returns (entries that answered, how many were dead-on-arrival). The
    caller only full-checks the survivors — that's the time saved.
    """
    import concurrent.futures as cf
    dead = 0
    alive: List[ProxyEntry] = []
    with cf.ThreadPoolExecutor(max_workers=PRECHECK_WORKERS) as ex:
        for entry, ok in zip(entries, ex.map(tcp_alive, entries)):
            if ok:
                alive.append(entry)
            else:
                dead += 1
    return alive, dead
