"""Engine smoke test: load -> pre-filter -> scan -> connect -> disconnect.

Runs the real network stack headlessly (no window). The exit probe is
faked so the connect leg needs no internet.
"""

import os
import sys
import threading
import time

# MUST be set before CeenApp exists: tests never touch the real
# Windows system proxy (that's how the 'lost wifi' incident happened).
os.environ["CEEN_TEST"] = "1"

import ceen.ui.app as app_mod
from ceen.ui.app import CeenApp


def main() -> int:
    ok = {"val": True}

    def check(cond: bool, msg: str) -> None:
        print(f"  [{'ok' if cond else 'FAIL'}] {msg}")
        ok["val"] = ok["val"] and cond

    print("[Ceen Proxy] engine smoke test (headless)")
    app = CeenApp()
    app.start()
    check(len(app.entries) > 0, "proxy list loaded")

    # drive state manually (no window, no dpg): pump() is thread-safe
    stop = threading.Event()

    def loop() -> None:
        while not stop.is_set():
            app.pump()
            time.sleep(0.02)

    threading.Thread(target=loop, daemon=True).start()

    t0 = time.monotonic()
    app.start_scan()
    check(app.scanning, "scan started")
    while app.scanning and time.monotonic() - t0 < 75:
        time.sleep(0.2)
    took = time.monotonic() - t0
    check(not app.scanning, f"scan finished in {took:.0f}s")
    check(len(app.pool) > 0, f"{len(app.pool)} alive proxies found")

    # connect leg with a stubbed probe (no internet needed)
    app.pool.set_entries([e for e in app.entries if e.alive])
    app_mod.probe_via_rotator = lambda *a, **k: ("203.0.113.7",
                                                 "United States", "US")
    app._connect()
    t1 = time.monotonic()
    while not app.connected and time.monotonic() - t1 < 8:
        time.sleep(0.1)
    check(app.connected, "connected (fake probe, real rotator)")
    app._disconnect()
    app.pump()
    check(not app.connected, "disconnected cleanly")
    check(app.system_proxy_on is False, "system proxy restored off")
    stop.set()
    time.sleep(0.1)
    print(f"  smoke: {'PASS' if ok['val'] else 'FAIL'}")
    return 0 if ok["val"] else 1


if __name__ == "__main__":
    sys.exit(main())
