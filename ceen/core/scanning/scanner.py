"""ScanEngine — tests hundreds of proxies at the same time.

It keeps a fixed team of worker threads alive and hands each one proxies
to test from a queue. Every scan gets a generation number, so if you stop
and restart a scan, results from the old (cancelled) scan can never leak
into the new one. Results are delivered through the two callback
functions you provide (`on_result`, `on_done`).
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Callable, Dict, List, Tuple

from ceen.core.proxies.checker import check_proxy
from ceen.core.proxies.handshakes import CheckResult
from ceen.core.proxies.entry import ProxyEntry

_log = logging.getLogger("proxy.engine")


class ScanEngine:
    """Bounded pool of daemon checkers; `start()` cancels any previous run."""

    def __init__(self, on_result: Callable[[ProxyEntry, int], None],
                 on_done: Callable[[int], None]) -> None:
        self._on_result = on_result
        self._on_done = on_done
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._stats: Dict[int, List[int]] = {}      # scan_id -> [done, total]
        self.scan_id = 0
        self.active = False

    @property
    def progress(self) -> Tuple[int, int]:
        """(checked, total) for the current scan."""
        with self._lock:
            st = self._stats.get(self.scan_id)
            return (st[0], st[1]) if st else (0, 0)

    def start(self, targets: List[ProxyEntry], workers: int,
              timeout: float, test_url: str,
              fast_prefilter: bool = True) -> None:
        """Launch a new scan generation over `targets`.

        With fast_prefilter, a quick TCP pre-check first kills the huge
        majority of dead proxies in ~2.5s instead of the full timeout —
        alive ones then get the complete check as normal.
        """
        self.stop()
        self.scan_id += 1
        sid = self.scan_id
        if fast_prefilter:
            from ceen.core.scanning.fastscan import split_alive_guess
            survivors, dead = split_alive_guess(targets, workers)
            _log.info("pre-check: %d of %d ports dead in ~%.1fs — full "
                      "checks only for the rest", dead, len(targets),
                      2.5)
            targets = survivors
            if not targets:
                with self._lock:
                    self._stats = {sid: [0, 0]}
                self._on_done(sid)
                return
        self._stop.clear()
        q: "queue.Queue[ProxyEntry]" = queue.Queue()
        with self._lock:
            self._stats = {sid: [0, len(targets)]}
        if not targets:
            self._on_done(sid)
            return
        for e in targets:
            e.reset()
            e.state = "queued"
            q.put(e)
        self.active = True
        n = max(1, min(workers, len(targets), 1000))
        _log.info("scan #%d started: %d targets, %d workers, timeout=%.1fs",
                  sid, len(targets), n, timeout)
        for i in range(n):
            threading.Thread(target=self._worker,
                             args=(sid, q, timeout, test_url),
                             name=f"checker-{sid}-{i}", daemon=True).start()

    def stop(self) -> None:
        """Signal all workers of the current generation to exit."""
        self._stop.set()
        self.active = False

    def _worker(self, sid: int, q: "queue.Queue[ProxyEntry]",
                timeout: float, test_url: str) -> None:
        """One checker thread: pull entries until the queue drains."""
        while not self._stop.is_set() and sid == self.scan_id:
            try:
                entry = q.get_nowait()
            except queue.Empty:
                return
            if self._stop.is_set() or sid != self.scan_id:
                return
            try:
                res: CheckResult = check_proxy(entry, test_url, timeout)
            except Exception:  # noqa: BLE001 — absolute last resort
                res = CheckResult(False, None, None, None, None, "internal")
            if sid != self.scan_id:            # a newer scan took over
                return
            entry.alive = res.alive
            entry.latency = res.latency_ms
            entry.exit_ip = res.exit_ip
            entry.exit_cc = res.exit_cc
            entry.country = res.country
            entry.error = res.error
            entry.state = "done"
            entry.flash_ts = time.monotonic()
            finished = False
            with self._lock:
                st = self._stats.get(sid)
                if st is None:
                    return
                st[0] += 1
                finished = st[0] >= st[1]
            try:
                self._on_result(entry, sid)
            except Exception:  # noqa: BLE001 — UI callback must not kill us
                pass
            if res.alive:
                _log.info("ALIVE  %-34s %5dms  exit=%-15s %s", entry.uri,
                          res.latency_ms or 0, res.exit_ip or "?",
                          res.country or "")
            else:
                _log.debug("DEAD   %-34s %s", entry.uri, res.error or "?")
            if finished and self.scan_id == sid:
                self.active = False
                _log.info("scan #%d complete: %d/%d checked", sid, st[0], st[1])
                try:
                    self._on_done(sid)
                except Exception:  # noqa: BLE001
                    pass
