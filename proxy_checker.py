"""Ceen Proxy — launcher.

The app lives in the ceen/ package; this file just starts it (and keeps
startup as fast as possible: nothing heavy is imported before the
window is ready).

Usage:
    python proxy_checker.py              open the app (auto-scans)
    python proxy_checker.py --selftest   offline self-tests, no window
    python proxy_checker.py --smoke      automated engine test, no window
    python proxy_checker.py --liveui     real-window test of the connect flow
    python proxy_checker.py --debug      verbose console logs too
    python proxy_checker.py --novsync    uncap framerate (debugging)
"""

import sys


def main() -> int:
    args = set(sys.argv[1:])
    if "--selftest" in args:
        from tests.run_all import main as t
        return t()
    if "--smoke" in args:
        from tests.test_smoke import main as t
        return t()
    if "--liveui" in args:
        from tests.test_live_ui import main as t
        return t()

    from ceen.logging_setup import audit_last_run, setup_logging
    setup_logging(debug_console="--debug" in args)
    path, warns, errs = audit_last_run()
    if path:
        print(f"[audit] previous run: {warns} warnings, {errs} errors")

    # crash guard: whatever happens, the user keeps their internet
    from ceen.utils.netconfig import install_crash_guard
    install_crash_guard()

    from ceen.ui.app import CeenApp
    from ceen.ui.bootstrap import Ui
    app = CeenApp()
    ui = Ui(app)
    app.start()                     # load list + auto-scan right away
    ui.run(vsync="--novsync" not in args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
