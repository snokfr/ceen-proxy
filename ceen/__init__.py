"""Ceen Proxy — a zero-dependency proxy checker + VPN-style tunnel.

Map of the project (start reading top to bottom):

    proxy_checker.py        the 5-line launcher you run
    ceen/config.py          app-wide constants (ports, file names, URLs)
    ceen/logging_setup.py   creates a fresh log file per run + audits the
                            previous one for errors
    ceen/core/              the "brain" — no window code in here
        proxies/            what a proxy is and how to talk to one
        scanning/           test hundreds of proxies at once
        tunnel/             your traffic's route out through them
    ceen/ui/                the window (tkinter, Apple-styled)
        widgets/            reusable controls (buttons, ring, table…)
        panels/             the Connect and Checker screens
        app.py              the controller gluing it all together
    ceen/utils/             shared helpers (system proxy, formatting)
    tests/                  self-tests: python -m tests.run_all
"""

APP_NAME = "Ceen Proxy"
APP_VERSION = "3.0"
