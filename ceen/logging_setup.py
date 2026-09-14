"""Per-run log files + the "audit the last run for errors" checker.

Every time Ceen starts it creates a brand-new file in logs/ named like
    ceen_proxy_2026-09-13_17-30-05.log
The window shows friendly messages; the FILE keeps everything (including
the very chatty per-proxy detail) so bugs can be reconstructed later.

`audit_last_run()` re-reads the previous session's file and reports how
many errors/warnings it contained — the user asked for "check my logs
after every run, just in case", and this is that, automated.
"""

from __future__ import annotations

import glob
import logging
import logging.handlers
import os
import re
import os
import sys
import time
from typing import List, Optional, Tuple

from ceen.config import APP_NAME


def app_dir() -> str:
    """The folder the app's data lives next to — works BOTH as a script
    (project root) and as a frozen .exe (the exe's own folder, where
    __file__/cwd are useless but sys.executable points at the exe)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    # running from source: this file is <root>/ceen/logging_setup.py
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


_LOG_DIR = os.path.join(app_dir(), "logs")
_log = logging.getLogger("proxy.logging")

# The logging "bridge": the network threads put messages on this queue and
# the window's own thread drains it — the one safe way to cross threads.
gui_queue: "logging.handlers.QueueHandler" = None  # type: ignore[assignment]


class LogBuffer:
    """A tiny in-memory mailbox of recent log lines the UI can display."""

    def __init__(self, limit: int = 4000) -> None:
        self._lines: List[Tuple[str, str]] = []   # (level, text)
        self._limit = limit

    def write(self, level: str, line: str) -> None:
        self._lines.append((level, line))
        if len(self._lines) > self._limit:
            del self._lines[: len(self._lines) - self._limit]

    def snapshot(self) -> List[Tuple[str, str]]:
        return list(self._lines)


_buffer: Optional[LogBuffer] = None


class _BufferHandler(logging.Handler):
    """Sits at the end of the logging pipeline and fills the LogBuffer."""

    def emit(self, record: logging.LogRecord) -> None:
        if _buffer is not None:
            try:
                _buffer.write(record.levelname, self.format(record))
            except Exception:  # noqa: BLE001 — logging must never crash
                pass


def setup_logging(debug_console: bool = False) -> str:
    """Create this run's log file and wire up all the log destinations.

    Returns the log file path. Console gets INFO (or DEBUG if
    debug_console), the file always gets full DEBUG.
    """
    global _buffer
    os.makedirs(_LOG_DIR, exist_ok=True)
    stamp = time.strftime("%Y-%m-%d_%H%M%S")
    path = os.path.join(_LOG_DIR, f"ceen_proxy_{stamp}.log")

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    fmt = logging.Formatter(
        "%(asctime)s  %(levelname)-7s %(name)-16s %(message)s", "%H:%M:%S")

    fh = logging.FileHandler(path, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    root.addHandler(fh)

    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG if debug_console else logging.INFO)
    ch.setFormatter(fmt)
    root.addHandler(ch)

    _buffer = LogBuffer()
    bh = _BufferHandler()
    bh.setLevel(logging.DEBUG)
    bh.setFormatter(fmt)
    root.addHandler(bh)

    _log.info("%s session started — log file: %s", APP_NAME, path)
    return path


def gui_lines() -> List[Tuple[str, str]]:
    """Recent log lines for display inside the window (level, text)."""
    return _buffer.snapshot() if _buffer else []


def audit_last_run() -> Tuple[Optional[str], int, int]:
    """Read the PREVIOUS session's log and count its problems.

    Returns (path, warnings, errors); path is None when this is the very
    first run (nothing to audit yet).
    """
    files = sorted(glob.glob(os.path.join(_LOG_DIR, "ceen_proxy_*.log")))
    if len(files) < 2:
        return None, 0, 0            # only THIS run exists — nothing prior
    prev = files[-2]                 # [-1] is the current run's file
    warns = errs = 0
    warn_re = re.compile(r"\b(WARNING|ERROR)\b")
    try:
        with open(prev, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if warn_re.search(line):
                    if " ERROR " in line:
                        errs += 1
                    else:
                        warns += 1
    except OSError as exc:
        _log.warning("could not audit previous log %s: %s", prev, exc)
        return prev, 0, 0
    _log.info("audited previous log %s: %d warnings, %d errors",
              prev, warns, errs)
    return prev, warns, errs
