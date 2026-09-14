"""Sparkline — the tiny live traffic graph shown once you're connected.

A borderless mini plot: upload (blue) and download (green) rates over
the last ~30 seconds, sampled twice a second. No axes, no clutter.
"""

from __future__ import annotations

import time
from collections import deque

import dearpygui.dearpygui as dpg

from ceen.ui.theme import c

_INTERVAL = 0.4          # seconds between samples
_POINTS = 72             # samples kept (~29 s of history)


class Sparkline:
    """Owns the drawlist and the two data series; call update() per frame."""

    def __init__(self, width: int = 170, height: int = 34) -> None:
        self.w, self.h = width, height
        self.up = deque([0.0] * _POINTS, maxlen=_POINTS)
        self.down = deque([0.0] * _POINTS, maxlen=_POINTS)
        self._last = time.monotonic()
        self._last_bytes = None          # (up_total, down_total) from rotator
        self.ready = False

    def build(self) -> None:
        """Create the drawlist once (call from a build function)."""
        with dpg.drawlist(width=self.w, height=self.h, tag="spark"):
            dpg.draw_polyline([(0, self.h - 1), (self.w - 1, self.h - 1)],
                              color=c("panel_hi"), thickness=1, tag="sp_base")
            dpg.draw_polyline([(0, self.h - 1)] * 2, color=c("accent"),
                              thickness=1.5, tag="sp_up")
            dpg.draw_polyline([(0, self.h - 1)] * 2, color=c("green"),
                              thickness=1.5, tag="sp_down")
        self.ready = True

    def sample(self, totals) -> None:
        """Feed (bytes_up_total, bytes_down_total) or None when offline."""
        now = time.monotonic()
        if now - self._last < _INTERVAL:
            return
        self._last = now
        if totals is None:
            self._last_bytes = None
            self.up.append(0.0)
            self.down.append(0.0)
        else:
            if self._last_bytes is not None:
                dt = max(0.001, now - (self._last_ts if hasattr(
                    self, "_last_ts") else now - _INTERVAL))
                up_rate = max(0.0, (totals[0] - self._last_bytes[0]) / dt)
                down_rate = max(0.0, (totals[1] - self._last_bytes[1]) / dt)
                self.up.append(min(up_rate, 5_000_000))     # clamp spikes
                self.down.append(min(down_rate, 5_000_000))
            self._last_bytes = totals
        self._last_ts = now

    def _poly(self, data: deque) -> list:
        """Turn rates into drawlist points (log-scaled so small is visible)."""
        import math
        peak = max(4096.0, max(data))
        pts = []
        for i, v in enumerate(data):
            x = i / (_POINTS - 1) * (self.w - 2) + 1
            k = math.log1p(v) / math.log1p(peak)          # 0..1, soft
            y = self.h - 2 - k * (self.h - 6)
            pts.append((x, y))
        return pts

    def redraw(self, connected: bool) -> None:
        """Repaint both lines; fade to flat when not connected."""
        if not self.ready:
            return
        self._fade = getattr(self, "_fade", 1.0)
        self._fade += ((1.0 if connected else 0.0) - self._fade) * 0.08
        if self._fade < 0.02:
            dpg.configure_item("sp_up", points=[(0, self.h - 1)] * 2,
                               color=c("panel_hi"))
            dpg.configure_item("sp_down", points=[(0, self.h - 1)] * 2,
                               color=c("panel_hi"))
            return
        up_c, dn_c = c("accent"), c("green")
        base = c("panel_hi")
        mix = lambda a: tuple(round(base[i] + (a[i] - base[i]) * self._fade)
                              for i in range(3))
        dpg.configure_item("sp_up", points=self._poly(self.up),
                           color=mix(up_c))
        dpg.configure_item("sp_down", points=self._poly(self.down),
                           color=mix(dn_c))
