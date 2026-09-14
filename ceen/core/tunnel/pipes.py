"""Pipe helpers — moving raw bytes between two network connections.

These are the "water hoses" of the tunnel: once a path from your app
through a proxy server is set up, one of these functions quietly copies
bytes in both directions (or just one) until the connection closes,
and reports how much traffic flowed.

They are plain reusable functions (no class needed) that take a
stop_event so the tunnel can shut them down instantly.
"""

from __future__ import annotations

import select
import socket
import threading
from typing import Tuple

_CHUNK = 65536          # bytes copied per step (64 KB is a good middle)
_TICK = 0.25            # seconds to wait for data before re-checking stop


def pipe_both(a: socket.socket, b: socket.socket,
              stop_event: threading.Event) -> Tuple[int, int]:
    """Copy bytes BOTH ways between two sockets until either side closes.

    Returns (a_to_b, b_to_a) byte counts. Used for CONNECT tunnels,
    where your app talks to a website through the proxy and the replies
    come back the same way.
    """
    up = down = 0
    while not stop_event.is_set():
        try:
            r, _w, _x = select.select([a, b], [], [], _TICK)
        except (OSError, ValueError):
            break
        if not r:
            continue                      # nothing to do this tick
        for s in r:
            dst = b if s is a else a
            try:
                data = s.recv(_CHUNK)
            except (OSError, socket.timeout, TimeoutError):
                data = b""                # treat any error as "closed"
            if not data:
                return up, down
            try:
                dst.sendall(data)
            except OSError:
                return up, down
            if s is a:
                up += len(data)
            else:
                down += len(data)
    return up, down


def pipe_one(src: socket.socket, dst: socket.socket,
             stop_event: threading.Event) -> int:
    """Copy bytes ONE way (source -> destination) until the source closes.

    Returns the number of bytes moved. Used for plain HTTP replies,
    where only the response streams back through the tunnel.
    """
    total = 0
    while not stop_event.is_set():
        try:
            r, _w, _x = select.select([src], [], [], _TICK)
        except (OSError, ValueError):
            break
        if not r:
            continue
        try:
            data = src.recv(_CHUNK)
        except (OSError, socket.timeout, TimeoutError):
            break
        if not data:
            break
        try:
            dst.sendall(data)
        except OSError:
            break
        total += len(data)
    return total
