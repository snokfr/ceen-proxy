"""Scan + connect behaviors, split from the controller so every file
stays small and readable.

These two mixins hold the "what happens" code (scanning the list,
building the tunnel, engaging the system proxy). CeenApp mixes them in,
so the app object itself stays mostly layout + state painting.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import List

from ceen.config import (DEFAULT_PORT, DEFAULT_TEST_URL, DEFAULT_TIMEOUT,
                         DEFAULT_WORKERS)
from ceen.core.proxies.entry import ProxyEntry
from ceen.core.tunnel.pool import ProxyPool, group_by_country
from ceen.core.tunnel.probe import probe_via_rotator
from ceen.core.tunnel.rotator import RotatorServer
from ceen.utils.netconfig import sys_set, sys_supported

_log = logging.getLogger("proxy.app")


# ════════════════════════ scanning ═══════════════════════════════════════
class ScanMixin:
    """Testing the whole proxy list in the background."""

    def start_scan(self) -> None:
        """Test the whole list — on a WORKER thread so the window can
        paint immediately (the 2.5s port pre-check must never freeze
        startup)."""
        if getattr(self, "scanning", False) or not self.entries:
            return
        self.scanning = True
        self.pool = ProxyPool()
        self.groups = []
        self._dirty_locations = True
        threading.Thread(target=self._scan_worker, name="scan",
                         daemon=True).start()

    def _scan_worker(self) -> None:
        """Off-thread: run the engine (it spawns its own checkers)."""
        _log.info("scan started: %d proxies", len(self.entries))
        try:
            self.engine.start(self.entries, DEFAULT_WORKERS,
                              DEFAULT_TIMEOUT, DEFAULT_TEST_URL)
        except Exception as exc:  # noqa: BLE001
            _log.error("scan crashed: %s", exc)
            self.events.put(("scan_done", self.engine.scan_id))

    def stop_scan(self) -> None:
        """Ask the workers to stop at the next proxy boundary."""
        self.engine.stop()
        self.scanning = False

    def _on_result(self, entry: ProxyEntry, sid: int) -> None:
        """Worker thread -> UI thread hop (results arrive as events)."""
        self.events.put(("result", entry, sid))

    def _on_scan_done(self, sid: int) -> None:
        self.events.put(("scan_done", sid))

    def _recompute_pool(self) -> None:
        """Refresh pool + country groups from the alive set (any thread)."""
        alive = [e for e in self.entries if e.alive]
        self.pool.set_entries(alive)
        self.groups = group_by_country(alive)
        self._dirty_locations = True


# ════════════════════════ connecting ═════════════════════════════════════
class ConnectMixin:
    """Turning the tunnel on and off (the power button's real work)."""

    def toggle(self) -> None:
        """Power ring clicked: switch on if off, off if on."""
        if self.connected or self.connecting:
            self._disconnect()
        else:
            self._connect()

    def _connect(self) -> None:
        """Begin connecting (unless a scan must finish/find servers first)."""
        if self.connecting:
            return
        if not len(self.pool):
            if not self.scanning and self.entries:
                self.start_scan()
            _log.info("connect requested with empty pool — scanning first")
            return
        self.connecting = True
        threading.Thread(target=self._connect_worker, name="connect",
                         daemon=True).start()

    def _connect_worker(self) -> None:
        """Off-thread: start tunnel, verify exit, engage system proxy.

        Staged so a bad exit can never hang the button: the local
        listener is instant, and the internet check gets a SHORT
        timeout — worst case the ring returns to 'off' in seconds.
        """
        port = self.settings.get("port", DEFAULT_PORT)
        rot = None
        try:
            rot = RotatorServer(port, self.pool)
            rot.on_pool_change = lambda: self.events.put(("pool_change",))
            rot.start()
            if not rot.wait_ready(2.0):
                raise RuntimeError(rot.last_error or "tunnel did not start")
            # real internet test THROUGH the tunnel. Up to 3 tries: a
            # probe failure makes the rotator bench that server, so a
            # retry automatically goes out through a different one.
            result = None
            for attempt in range(3):
                try:
                    result = probe_via_rotator(rot.port, timeout=7.0)
                    break
                except Exception as exc:  # noqa: BLE001
                    if attempt == 2:
                        raise
                    _log.info("exit probe try %d failed (%s) — rotating",
                              attempt + 1, str(exc)[:40])
                    time.sleep(0.4)
            self.rotator = rot
            self.events.put(("connected", *result))
            # watchdog: if every server dies mid-session, auto-disconnect
            threading.Thread(target=self._tunnel_watchdog, name="watchdog",
                             daemon=True).start()
        except Exception as exc:  # noqa: BLE001
            _log.error("connect failed: %s", exc)
            if rot is not None:
                rot.stop()
            self.events.put(("connect_failed", str(exc)[:60]))

    def _tunnel_watchdog(self) -> None:
        """While connected: probe the tunnel every 10s. Two failures in
        a row = the exit servers died -> disconnect (and un-hook the
        system proxy) instead of silently going dark."""
        fails = 0
        while self.connected and self.rotator is not None:
            time.sleep(10)
            if not (self.connected and self.rotator is not None):
                return
            try:
                probe_via_rotator(self.rotator.port, timeout=6.0)
                fails = 0
            except Exception:  # noqa: BLE001 — any failure counts once
                fails += 1
                _log.warning("tunnel probe failed (%d/2)", fails)
                if fails >= 2:
                    self.events.put(("tunnel_lost",))
                    return

    def cancel_connect(self) -> None:
        """CANCEL while connecting: give up and go back to 'off'."""
        if self.rotator is not None:
            self.rotator.stop()
            self.rotator = None
        self.connecting = False
        _log.info("connect cancelled by user")

    def _disconnect(self) -> None:
        """Stop the tunnel and give Windows its old settings back."""
        if self.rotator is not None:
            self.rotator.stop()
            self.rotator = None
        if self.system_proxy_on:
            sys_set(False)
            self.system_proxy_on = False
        self.connected = self.connecting = False
        self.exit_ip = self.exit_country = self.exit_cc = None
        _log.info("disconnected — traffic direct again")

    def connect_country(self, name: str) -> None:
        """Tap a country row: pin its fastest server, connect."""
        for gname, _cc, servers in self.groups:
            if gname == name and servers:
                self.pool.set_sticky(servers[0])
                if not (self.connected or self.connecting):
                    self._connect()
                return

    def connect_server(self, entry) -> None:
        """Use THIS exact server (from the expanded country list).

        Already connected? Hot-switch: drop the tunnel and reconnect
        through the picked server right away.
        """
        self.pool.set_sticky(entry)
        if self.connected:
            self._disconnect()
        if not (self.connected or self.connecting):
            self._connect()

    def connect_fastest(self) -> None:
        """Un-pin and let rotation pick the fastest server."""
        self.pool.set_sticky(None)
        if not (self.connected or self.connecting):
            self._connect()

    def toggle_system_proxy(self) -> None:
        """The second safety switch: point Windows itself at the tunnel."""
        on = not self.system_proxy_on
        if on and not sys_supported():
            _log.warning("system proxy needs Windows")
            return
        if sys_set(on, self.settings.get("port", DEFAULT_PORT)):
            self.system_proxy_on = on
            self.save_settings(system_proxy=on)
            _log.info("system proxy %s", "ON" if on else "OFF")
