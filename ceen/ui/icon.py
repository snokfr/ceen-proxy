"""Ceen Proxy icons, generated on the fly (no .ico files needed).

One function draws the brand mark at any size: a dark rounded square, a
blue ring and a power bar. Used for the window icon (taskbar + title
bar) — pure Python, works everywhere.
"""

from __future__ import annotations

import struct
from typing import List, Tuple

# brand colors (same palette as the UI theme)
_BG = (24, 27, 34, 255)
_RING = (66, 133, 244, 255)
_BAR = (240, 242, 247, 255)


def _rounded_alpha(x: float, y: float, size: int, r: int) -> bool:
    """True if (x, y) is inside the rounded square."""
    edge = size - r
    if r <= x < edge and r <= y < edge:
        return True                              # middle (fast path)
    cx = min(max(x, r), edge - 1)                # nearest corner centre
    cy = min(max(y, r), edge - 1)
    return (x - cx) ** 2 + (y - cy) ** 2 <= r * r


def _ring_alpha(x: float, y: float, m: int) -> bool:
    """True if (x, y) sits on the power-symbol ring (with a top gap)."""
    dx, dy = x - m, y - m
    d2 = dx * dx + dy * dy
    outer, inner = (m * 0.62) ** 2, (m * 0.45) ** 2
    if not (inner <= d2 <= outer):
        return False
    import math
    ang = math.degrees(math.atan2(-dy, -dx)) % 360
    return not (250 <= ang <= 290)               # gap at the top


def _bar_alpha(x: float, y: float, m: int) -> bool:
    """True if (x, y) is the vertical power bar (top half)."""
    return abs(x - m) <= max(1, m * 0.09) and \
        (m * 0.18) <= y <= (m * 0.95)


def render_rgba(size: int) -> List[Tuple[int, int, int, int]]:
    """Pixel-by-pixel icon at `size`x`size`."""
    m = size / 2
    px = []
    for y in range(size):
        for x in range(size):
            if _ring_alpha(x, y, m):
                px.append(_RING)
            elif _bar_alpha(x, y, m):
                px.append(_BAR)
            elif _rounded_alpha(x, y, size, max(2, size // 5)):
                px.append(_BG)
            else:
                px.append((0, 0, 0, 0))          # transparent corner
    return px


def save_ico(path: str, size: int = 32) -> None:
    """Write a Windows .ico containing one PNG-compressed image."""
    import io
    import zlib
    raw = b"".join(b"\x00" + bytes(v for p in
                                   (render_rgba(size)[y * size:(y + 1) * size])
                                   for v in p)
                   for y in range(size))
    def chunk(tag: bytes, data: bytes) -> bytes:
        c = tag + data
        return struct.pack(">I", len(data)) + c + \
            struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
           + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))
    # ICO container: 1 image, PNG-encoded (Vista+ accepts this)
    ico = struct.pack("<HHH", 0, 1, 1)
    ico += struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32,
                       len(png), 22)
    with open(path, "wb") as fh:
        fh.write(ico + png)


def save_png(path: str, size: int = 64) -> None:
    """Same drawing as a plain PNG (for dpg.load_image)."""
    import zlib
    px = render_rgba(size)
    raw = b"".join(b"\x00" + bytes(v for p in px[y * size:(y + 1) * size]
                                   for v in p)
                   for y in range(size))
    def chunk(tag: bytes, data: bytes) -> bytes:
        c = tag + data
        return struct.pack(">I", len(data)) + c + \
            struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    with open(path, "wb") as fh:
        fh.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
                 + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))
