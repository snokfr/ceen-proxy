"""Persistent settings — the app remembers things between runs.

Saved as a tiny JSON file in your user folder (~/.ceen_proxy.json):
window size, chosen port, auto-system-proxy preference, and anything
else the app marks as worth keeping.

Design goals (each one earns its function):
  * NEVER crashes the app: a missing, corrupt, or half-written file is
    just "default settings" — and a corrupt file gets moved aside
    (backup) so it can be inspected instead of silently destroyed.
  * NEVER loses data mid-write: saves go to a temp file first, then are
    atomically renamed over the real one (a crash mid-save can't leave
    a half-written file behind).
  * Values are VALIDATED on load: anything impossible (window smaller
    than the minimum, port out of range) silently becomes the default.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from typing import Dict, Optional

from ceen.config import SETTINGS_PATH

_log = logging.getLogger("proxy.settings")

# the values we accept, with their types and sane bounds (for numbers)
_SCHEMA: Dict[str, tuple] = {
    "win_w": (int, 340, 4000),
    "win_h": (int, 520, 4000),
    "port": (int, 1024, 65535),
    "auto_system_proxy": (bool, None, None),
    "system_proxy": (bool, None, None),
    "list_path": (str, None, None),
}


def defaults() -> Dict[str, object]:
    """The factory settings (also what a bad value falls back to)."""
    from ceen.config import DEFAULT_PORT
    return {"win_w": 380, "win_h": 590, "port": DEFAULT_PORT,
            "auto_system_proxy": True, "system_proxy": False}


def load() -> Dict[str, object]:
    """Read the settings file, returning validated values.

    Missing file -> defaults. Corrupt file -> defaults + a `.bad` backup
    of the corrupt file so nothing is silently destroyed.
    """
    values = defaults()
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
        if not isinstance(raw, dict):
            raise ValueError("settings root is not an object")
    except FileNotFoundError:
        return values                      # first run: perfectly normal
    except (OSError, ValueError) as exc:
        _quarantine(exc)                   # keep the evidence, move on
        return values
    for key, (kind, lo, hi) in _SCHEMA.items():
        if key not in raw:
            continue
        v = raw[key]
        try:
            if not isinstance(v, kind):
                raise ValueError(f"{key}: wrong type")
            if lo is not None and not (lo <= v <= hi):
                raise ValueError(f"{key}: out of range")
        except ValueError as exc:
            _log.warning("settings: %s — using default", exc)
            continue                       # keep the default for this key
        values[key] = v
    _log.info("settings loaded from %s", SETTINGS_PATH)
    return values


def save(values: Dict[str, object]) -> bool:
    """Write settings atomically: temp file first, then rename over.

    Returns True when the file was written successfully.
    """
    clean = {k: v for k, v in values.items() if k in _SCHEMA}
    try:
        d = os.path.dirname(SETTINGS_PATH) or "."
        fd, tmp = tempfile.mkstemp(prefix=".ceen_", suffix=".tmp", dir=d)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(clean, fh, indent=1)
            os.replace(tmp, SETTINGS_PATH)  # atomic on the same drive
        except BaseException:
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise
        _log.info("settings saved to %s", SETTINGS_PATH)
        return True
    except OSError as exc:
        _log.warning("could not save settings: %s", exc)
        return False


def _quarantine(exc: Exception) -> None:
    """Move a corrupt settings file aside (as .bad) instead of deleting."""
    bad = SETTINGS_PATH + ".bad"
    _log.warning("settings file unreadable (%s) — starting fresh; "
                 "old file kept as %s", exc, os.path.basename(bad))
    try:
        os.replace(SETTINGS_PATH, bad)
    except OSError:
        pass


def merge(base: Dict[str, object], **updates) -> Dict[str, object]:
    """Handy helper: copy `base` with `updates` applied (returns new)."""
    out = dict(base)
    out.update({k: v for k, v in updates.items() if k in _SCHEMA})
    return out


def current_size(saved: Dict[str, object]) -> Optional[tuple]:
    """The (w, h) to open the window at, per saved settings."""
    try:
        return int(saved["win_w"]), int(saved["win_h"])
    except (KeyError, TypeError, ValueError):
        return None
