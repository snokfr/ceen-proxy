"""CeenApp — the controller: owns state, drives the UI every frame.

The network side (scanner, pool, rotator) runs on its own threads and
never touches the GUI; instead they push events into a thread-safe
queue which this controller drains once per frame (`update()`). The
GUI itself is Dear PyGui: every frame we simply set the values of
widgets from current state — no callbacks fighting threads, no
re-layout.

The "what happens" code (scanning, connecting) lives in behaviors.py;
this file is state + painting + UI callbacks.
"""

from __future__ import annotations

import logging
import os
import queue
import threading
import time
from typing import List, Optional

import dearpygui.dearpygui as dpg

from ceen.config import DEFAULT_LIST
from ceen.core.proxies.entry import ProxyEntry, load_proxy_list
from ceen.core.scanning.scanner import ScanEngine
from ceen.core.tunnel.pool import ProxyPool
from ceen.logging_setup import gui_lines
from ceen.ui import panel_checker, panel_connect, server_list, titlebar
from ceen.ui.behaviors import ConnectMixin, ScanMixin
from ceen.ui.theme import c
from ceen.utils.ipcheck import direct_ip_probe
from ceen.utils.netconfig import sys_get, sys_set, sys_supported
from ceen.utils import settings as settings_store
from ceen.utils.textutil import flag_emoji

_log = logging.getLogger("proxy.app")


class CeenApp(ScanMixin, ConnectMixin):
    """All app state + the per-frame update that paints it."""

    def __init__(self) -> None:
        self.events: "queue.Queue[tuple]" = queue.Queue()
        self.entries: List[ProxyEntry] = []
        self.pool = ProxyPool()
        self.groups: list = []                    # (name, cc, [servers])
        self.engine = ScanEngine(self._on_result, self._on_scan_done)
        self.rotator = None
        self.scanning = False
        self.connected = False
        self.connecting = False
        self.direct_ip: Optional[str] = None
        # what the big location line shows while connected (set by the
        # 'connected' event — works for BOTH fastest and country picks)
        self.exit_ip: Optional[str] = None
        self.exit_country: Optional[str] = None
        self.exit_cc: Optional[str] = None
        self.settings = self._load_settings()
        self.system_proxy_on = False
        self.search = ""
        self.alive_only = False
        self.expanded: Optional[str] = None   # which country is unfolded
        self.tags = {k: f"app_{k}" for k in (
            "connect_root", "checker_root", "menu_btn", "state_pill",
            "proto_pill", "proto_txt", "net_lbl", "loc_name", "loc_city",
            "exit_ip", "loc_count", "fast_btn", "backup_hint", "search",
            "alive_only", "scan_btn", "stop_btn", "copy_btn", "export_btn",
            "log_btn", "progress", "checker_status")}
        # Test runs must NEVER touch the real Windows proxy setting.
        self.test_mode = os.environ.get("CEEN_TEST") == "1"
        self._last_table = 0.0
        self._prev_frame = time.monotonic()
        self._dirty_locations = True

    # ══ settings ══════════════════════════════════════════════════════
    def _load_settings(self) -> dict:
        """Validated, crash-safe load (see utils/settings.py)."""
        return settings_store.load()

    def save_settings(self, **kw) -> None:
        """Atomic save (temp file + rename) — can never half-write."""
        self.settings.update(kw)
        settings_store.save(self.settings)

    # ══ startup (called by run() after the UI exists) ═════════════════
    def start(self) -> None:
        """Load the list, show the direct IP, kick off the auto-scan."""
        path = self.settings.get("list_path") or DEFAULT_LIST
        if os.path.exists(path):
            self.entries, _skip = load_proxy_list(path)
            _log.info("loaded %d proxies", len(self.entries))
        self._detect_direct_ip()
        self._clear_stale_proxy()
        # NOTE: no dpg calls in here — the window paints the current
        # state on its first frame (locations start flagged dirty).
        self.start_scan()

    def _clear_stale_proxy(self) -> None:
        """Clear a crashed session's leftover 'dead tunnel' proxy."""
        enabled, server = sys_get()
        if enabled and server and server.startswith("127.0.0.1:"):
            sys_set(False)
            _log.warning("cleared stale system proxy %s", server)

    def shutdown(self) -> None:
        """Restore internet settings on the way out (belt AND braces)."""
        try:
            self._disconnect()
            sys_set(False)
        except Exception as exc:  # noqa: BLE001
            _log.error("shutdown problem: %s", exc)

    def _detect_direct_ip(self) -> None:
        """Your real IP without any proxy — shown as 'before' for proof."""
        def work() -> None:
            try:
                ip = direct_ip_probe()
                if ip:
                    self.events.put(("direct_ip", ip))
            except Exception as exc:  # noqa: BLE001
                _log.debug("direct ip probe failed: %s", exc)
        threading.Thread(target=work, name="direct-ip", daemon=True).start()

    # ══ per-frame update ══════════════════════════════════════════════
    def update(self) -> None:
        """One UI frame: absorb events, then repaint. MAIN THREAD ONLY
        (Dear PyGui is not thread-safe — everything below touches dpg)."""
        self.pump()
        now = time.monotonic()
        dt = min(0.1, now - self._prev_frame)
        self._prev_frame = now
        # glow/pulse animation runs every frame (cheap value mutations)
        panel_connect.set_ring_frame(self, dt)
        if getattr(self, "_frames", 0) >= 1:  # layout only exists once a
            panel_connect.place_power_hit(self)   # frame has been drawn
        # sparkline samples traffic while connected, fades out otherwise
        spark = getattr(self, "spark", None)
        if spark is not None:
            totals = ((self.rotator.bytes_up, self.rotator.bytes_down)
                      if (self.connected and self.rotator) else None)
            spark.sample(totals)
            spark.redraw(self.connected)
        if self._dirty_locations:
            self._dirty_locations = False
            server_list.refresh(self)
        mode = ("on" if self.connected else
                "connecting" if self.connecting else "off")
        panel_connect.set_ring_mode(self, mode)
        panel_connect.update_action_button(self)   # the obvious off-switch
        titlebar.tick_titlebar()      # keeps _ and X pinned right
        # The big text under the ring reflects the REAL tunnel state —
        # the exit ip/country arrived with the 'connected' event, so this
        # works no matter which way you connected (fastest or a country).
        if self.connected:
            cc = (self.exit_cc or "").upper()
            title = (f"{flag_emoji(cc)}  {self.exit_country or 'Connected'}"
                     if cc else "Connected")
            panel_connect.set_location_line(self, title)
            panel_connect.set_exit_ip(self, self.exit_ip or "?")
        else:
            panel_connect.set_location_line(self, "Not Connected")
            direct = f"{self.direct_ip} · direct" if self.direct_ip \
                else "not protected"
            panel_connect.set_exit_ip(self, direct)
        done, total = self.engine.progress
        panel_checker.set_progress(self, done, total, self.scanning)
        if now - self._last_table > 0.15:         # ~7 fps is plenty
            self._last_table = now
            panel_checker.refresh_table(self)

    def pump(self) -> None:
        """Absorb queued events into state. NO dpg calls here — safe to
        call from any thread (and from headless tests with no window)."""
        while True:
            try:
                ev = self.events.get_nowait()
            except queue.Empty:
                return
            kind = ev[0]
            if kind == "result":
                if ev[1].alive:
                    self._recompute_pool()
            elif kind == "scan_done":
                self.scanning = False
                _log.info("scan complete: %d alive", len(self.pool))
                self._recompute_pool()
            elif kind == "direct_ip":
                self.direct_ip = ev[1]
            elif kind == "connected":
                self._dirty_locations = True   # repaint active-server star
                self.connected, self.connecting = True, False
                _ip, country, cc = ev[1], ev[2], ev[3]
                # remember WHERE we came out so every widget can show it
                self.exit_ip, self.exit_country, self.exit_cc = \
                    _ip, country, cc
                _log.info("connected via %s (%s) exit=%s", country, cc, _ip)
                # THE FIX for "my IP didn't change": automatically point
                # Windows at our tunnel so every browser follows along.
                # (Disabled in test mode — tests must not touch the OS.)
                if not self.test_mode \
                        and self.settings.get("auto_system_proxy", True) \
                        and sys_supported() and not self.system_proxy_on:
                    self.toggle_system_proxy()
            elif kind == "connect_failed":
                self.connecting = False
                _log.warning("connect failed: %s", ev[1])
            elif kind == "tunnel_lost":
                _log.warning("tunnel lost — disconnecting to stay safe")
                self._disconnect()
            elif kind == "pool_change":
                self._recompute_pool()

    # ══ UI callbacks (from widgets) ═══════════════════════════════════
    def ui_search(self, sender, val) -> None:
        self.search = val.strip()

    def ui_filter(self, sender, val) -> None:
        self.alive_only = val

    def ui_start_scan(self) -> None:
        self.start_scan()

    def ui_stop_scan(self) -> None:
        self.stop_scan()

    def ui_copy(self) -> None:
        uris = [e.uri for e in self.entries if e.alive]
        dpg.set_clipboard_text("\n".join(uris))
        _log.info("copied %d alive proxies", len(uris))

    def ui_export(self) -> None:
        uris = [e.uri for e in self.entries if e.alive]
        from ceen.logging_setup import app_dir
        path = os.path.join(app_dir(), "alive_proxies.txt")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(uris))
        _log.info("exported %d alive -> %s", len(uris), path)

    def ui_show_checker(self) -> None:
        """Swap the visible page to the Checker screen."""
        dpg.configure_item(self.tags["connect_root"], show=False)
        dpg.configure_item(self.tags["checker_root"], show=True)

    def ui_show_connect(self) -> None:
        """Back to the main screen (the Checker's BACK button)."""
        dpg.configure_item(self.tags["checker_root"], show=False)
        dpg.configure_item(self.tags["connect_root"], show=True)

    def toggle_expand(self, name: str) -> None:
        """Tap a country row: unfold its servers (or fold it back up).
        Only one country is open at a time, so the list stays tidy."""
        self.expanded = None if self.expanded == name else name
        self._dirty_locations = True

    def ui_open_log(self) -> None:
        panel_checker.open_log_window(self, gui_lines())

    def visible_rows(self) -> List[ProxyEntry]:
        """Entries after the search + alive-only filters, sorted fast-first."""
        rows = self.entries
        if self.alive_only:
            rows = [e for e in rows if e.alive]
        if self.search:
            q = self.search.lower()
            rows = [e for e in rows if q in e.uri.lower()
                    or q in (e.country or "").lower()]
        return sorted(rows, key=lambda e: e.latency or 10 ** 9)
