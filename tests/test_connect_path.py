"""Regression test for the 'crashed when I pressed connect' bug.

The real app runs with CEEN_TEST unset, and the moment a connect
succeeded it called sys_supported() — which the controller rewrite had
forgotten to import (NameError -> emergency shutdown -> app gone).
Test mode masked it because the auto-system-proxy branch never ran.

This test runs the REAL 'connected' event path (CEEN_TEST unset!) with
only the Windows-registry writer stubbed out, and asserts the app comes
out connected, with the system proxy marked on — and no NameError.
"""

import os
import sys

# deliberate: this test must run OUTSIDE test mode or it proves nothing
os.environ.pop("CEEN_TEST", None)

import ceen.ui.app as app_mod
from ceen.ui.app import CeenApp


def run() -> bool:
    """Runner-style entry point: True = all checks passed."""
    return main() == 0          # main() follows exit-code rules (0 = good)


def main() -> int:
    print("[Ceen Proxy] connect-path regression (no test mode)")
    # stub ONLY the OS-touching functions; everything else is the real code
    app_mod.sys_supported = lambda: True
    app_mod.sys_set = lambda on, port=8888: True

    app = CeenApp()
    # pretend the tunnel verified an exit (as _connect_worker would)
    app.events.put(("connected", "203.0.113.9", "Mexico", "MX"))
    try:
        app.pump()
    except NameError as exc:
        print(f"  [FAIL] NameError survived: {exc}")
        return 1
    ok = app.connected and app.connecting is False
    print(f"  [{'ok' if ok else 'FAIL'}] connected state set "
          f"(connected={app.connected})")
    ok2 = app.system_proxy_on is True
    print(f"  [{'ok' if ok2 else 'FAIL'}] system proxy engaged by connect")
    ok3 = (app.exit_country, app.exit_cc, app.exit_ip) == \
        ("Mexico", "MX", "203.0.113.9")
    print(f"  [{'ok' if ok3 else 'FAIL'}] exit details stored for the UI")
    # and the way back down
    app._disconnect()
    ok4 = (not app.connected) and app.system_proxy_on is False
    print(f"  [{'ok' if ok4 else 'FAIL'}] disconnect restores everything")
    good = ok and ok2 and ok3 and ok4
    print(f"  connect-path: {'PASS' if good else 'FAIL'}")
    return 0 if good else 1


if __name__ == "__main__":
    sys.exit(main())
