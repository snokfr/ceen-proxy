"""Live UI verification: a REAL window, a REAL scan, a scripted connect.

Runs with CEEN_TEST=1 so the Windows system proxy is never touched.
Asserts the on-screen text follows the tunnel state (the exact bug that
was reported: 'it says connected but the GUI still says Not Connected'),
then disconnects and checks the UI returns to the resting state.
"""

import os
import sys
import threading
import time

os.environ["CEEN_TEST"] = "1"          # never touch the Windows proxy

import dearpygui.dearpygui as dpg       # noqa: E402

from ceen.ui.app import CeenApp         # noqa: E402
from ceen.ui.bootstrap import Ui        # noqa: E402


def main() -> int:
    ok = {"val": True}

    def check(cond: bool, msg: str) -> None:
        print(f"  [{'ok' if cond else 'FAIL'}] {msg}")
        ok["val"] = ok["val"] and cond

    print("[Ceen Proxy] live UI test (real window, scripted connect)")
    app = CeenApp()
    ui = Ui(app)

    # scripted actions run on the dpg thread via the render loop
    results = []          # (label, ok) pairs asserted at the end
    t0 = time.monotonic()

    def read_loc():
        return dpg.get_value(app.tags["loc_name"])

    def do_connect():
        app.connect_fastest()

    def assert_connected():
        loc = read_loc()
        results.append(("location line shows the exit country "
                        f"(got: {loc!r})", "Not Connected" not in loc))
        # the status pill label must say protected now (label bug check)
        results.append((f"pill says protected (got: "
                        f"{dpg.get_item_label(app.tags['state_pill'])!r})",
                        dpg.get_item_label(app.tags["state_pill"])
                        == "protected"))
        # the bottom button must now read DISCONNECT (the off-switch)
        btn = dpg.get_item_label(app.tags["fast_btn"])
        results.append((f"action button reads DISCONNECT (got: {btn!r})",
                        btn == "DISCONNECT"))

    def do_disconnect():
        # press the REAL button: fetch its callback and fire it (there is
        # no 'execute_item_callback' in dpg, this is the equivalent)
        try:
            cb = dpg.get_item_callback(app.tags["fast_btn"])
            if callable(cb):
                cb(None, None)
            else:
                app._disconnect()
        except Exception:  # noqa: BLE001 — fall back to the action itself
            app._disconnect()

    def assert_disconnected():
        results.append((f"location line back to rest (got: {read_loc()!r})",
                        read_loc() == "Not Connected"))
        results.append((f"pill back to unprotected (got: "
                        f"{dpg.get_item_label(app.tags['state_pill'])!r})",
                        dpg.get_item_label(app.tags["state_pill"])
                        == "unprotected"))
        btn = dpg.get_item_label(app.tags["fast_btn"])
        results.append((f"action button back to CONNECT FASTEST "
                        f"(got: {btn!r})", btn == "CONNECT FASTEST"))

    runner_stage = {"connected_at": None}

    def runner():
        now = time.monotonic()
        # stage 1: wait for the scan to find servers, then connect (45s cap)
        if runner_stage["connected_at"] is None:
            if app.connected:
                runner_stage["connected_at"] = now
            elif now - t0 < 45 and len(app.pool) > 0 \
                    and not app.connecting:
                # first: expand the first country and check server rows appear
                if "fired" not in runner_stage:
                    runner_stage["fired"] = True
                    app.toggle_expand(app.groups[0][0])
                elif "expanded_ok" not in runner_stage:
                    shown = sum(dpg.is_item_shown(r)
                                for r in app.list_rows)
                    results.append((
                        f"expanding a country reveals its servers "
                        f"({shown} rows for {len(app.groups)} countries)",
                        shown > len(app.groups)))
                    runner_stage["expanded_ok"] = True
                    do_connect()
            return
        # stage 2: 1s after connected, assert + disconnect
        if now - runner_stage["connected_at"] > 1.0 \
                and "asserted" not in runner_stage:
            runner_stage["asserted"] = True
            assert_connected()
            do_disconnect()
            runner_stage["disc_at"] = now
        # stage 3: a moment AFTER disconnect (so a repaint happened),
        # assert the UI returned to rest and stop
        if "disc_at" in runner_stage \
                and now - runner_stage["disc_at"] > 0.5 \
                and "done" not in runner_stage:
            runner_stage["done"] = True
            assert_disconnected()
            dpg.stop_dearpygui()

    dpg.setup_dearpygui()
    dpg.show_viewport()
    app.start()                      # loads list + starts auto-scan
    frames = 0
    while dpg.is_dearpygui_running() and "done" not in runner_stage \
            and frames < 60_000:
        app.update()
        runner()
        dpg.render_dearpygui_frame()
        frames += 1
    # timeout path: if we got here without completing, note it
    if "done" not in runner_stage:
        results.append((f"test completed in time (connected="
                        f"{app.connected}, pool={len(app.pool)})",
                        False))
    app.shutdown()
    dpg.destroy_context()
    for msg, good in results:
        check(good, msg)
    print(f"  live-ui: {'PASS' if ok['val'] else 'FAIL'}")
    return 0 if ok["val"] else 1


if __name__ == "__main__":
    sys.exit(main())
