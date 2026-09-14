"""Windows system-proxy switch + the kill-switch — in plain language.

The SYSTEM PROXY switch tells Windows itself "send everyone's internet
through Ceen's tunnel" (browsers follow automatically). The KILL SWITCH
is the safety net: if every proxy server dies while the system proxy is
on, we deliberately LEAVE the (now dead) system proxy in place so your
traffic is blocked, not quietly sent uncovered. Blocked is safe; leaked
is not.

All functions here are safe to call on any OS — on non-Windows systems
they simply report "not supported" instead of crashing.
"""

from __future__ import annotations

import logging
import sys
from typing import Optional

from ceen.config import _winreg

_log = logging.getLogger("proxy.netconfig")

# Where Windows keeps its internet-settings in the Registry (like a big
# settings notebook the whole system reads from).
_INTERNET_KEY = (r"Software\Microsoft\Windows"
                 r"\CurrentVersion\Internet Settings")

# Remembers the user's original proxy settings so we can put them back
# exactly the way they were when Ceen disconnects.
_saved_enable: Optional[int] = None
_saved_server: Optional[str] = None


def sys_supported() -> bool:
    """True when this computer is Windows and we can change its settings."""
    return sys.platform == "win32" and _winreg is not None


def sys_set(on: bool, port: int = 8888) -> bool:
    """Turn the Windows system proxy on (pointing at our tunnel) or off.

    Returns True if the change was made, False if this OS can't do it.
    """
    if not sys_supported():
        _log.info("system proxy not supported on this OS — skipping")
        return False
    global _saved_enable, _saved_server
    assert _winreg is not None
    try:
        if on and _saved_enable is None:      # first connect: take a snapshot
            _saved_enable, _saved_server = sys_get()
        with _winreg.CreateKeyEx(_winreg.HKEY_CURRENT_USER, _INTERNET_KEY, 0,
                                 _winreg.KEY_SET_VALUE) as key:
            _winreg.SetValueEx(key, "ProxyEnable", 0, _winreg.REG_DWORD,
                               1 if on else 0)
            if on:
                _winreg.SetValueEx(key, "ProxyServer", 0, _winreg.REG_SZ,
                                   f"127.0.0.1:{port}")
            elif _saved_enable is not None:   # restore what the user had
                _winreg.SetValueEx(key, "ProxyEnable", 0, _winreg.REG_DWORD,
                                   _saved_enable)
                if _saved_server:
                    _winreg.SetValueEx(key, "ProxyServer", 0, _winreg.REG_SZ,
                                       _saved_server)
    except OSError as exc:
        _log.error("could not change system proxy: %s", exc)
        return False
    _refresh_windows()
    _log.info("system proxy %s (port %d)", "ON" if on else "OFF", port)
    return True


def sys_get() -> tuple:
    """Read the current system-proxy settings (enabled?, server string)."""
    if not sys_supported():
        return 0, None
    assert _winreg is not None
    try:
        with _winreg.OpenKey(_winreg.HKEY_CURRENT_USER, _INTERNET_KEY) as key:
            enable, _ = _winreg.QueryValueEx(key, "ProxyEnable")
            try:
                server, _ = _winreg.QueryValueEx(key, "ProxyServer")
            except OSError:
                server = None
            return int(enable), server
    except OSError:
        return 0, None


def sys_keep_blocked(on: bool, port: int = 8888) -> None:
    """Kill-switch helper: keep the (dead) system proxy in place on purpose.

    Normally "on = safe, off = restore old settings". The kill-switch flips
    that: even when the tunnel has no working servers, we keep the system
    pointing at the empty tunnel so traffic is BLOCKED, never leaked.
    """
    if not sys_supported():
        return
    assert _winreg is not None
    try:
        with _winreg.CreateKeyEx(_winreg.HKEY_CURRENT_USER, _INTERNET_KEY, 0,
                                 _winreg.KEY_SET_VALUE) as key:
            _winreg.SetValueEx(key, "ProxyEnable", 0, _winreg.REG_DWORD, 1)
            _winreg.SetValueEx(key, "ProxyServer", 0, _winreg.REG_SZ,
                               f"127.0.0.1:{port}")
        _refresh_windows()
        _log.warning("KILL SWITCH: system proxy kept at 127.0.0.1:%d so "
                     "traffic stays blocked (no leak)", port)
    except OSError as exc:
        _log.error("kill-switch could not enforce block: %s", exc)


def install_crash_guard() -> None:
    """THE safety net, registered at program start. Three layers:

    1. any UNCAUGHT exception (main thread)  -> proxy OFF immediately
    2. any exception in a background thread  -> proxy OFF immediately
    3. process exit for ANY reason (atexit)  -> proxy OFF if stale

    'Off' means: clear the 127.0.0.1 tunnel pointer and tell Windows to
    refresh, so the user can never be stuck with 'no internet' because
    the app crashed mid-session.
    """
    import atexit
    import sys as _sys
    import threading as _threading

    def _emergency_off(why: str) -> None:
        try:
            _log.critical("EMERGENCY PROXY OFF — %s", why)
            sys_set(False)
        except Exception:  # noqa: BLE001 — a guard must never raise
            pass

    def _main_hook(kind, value, tb) -> None:
        _emergency_off(f"uncaught error: {value!r}")
        _sys.__excepthook__(kind, value, tb)   # still print the traceback

    def _thread_hook(args) -> None:
        _emergency_off(f"thread crash in {args.thread}: {args.exc_value!r}")

    def _restore_at_exit() -> None:
        try:
            enabled, server = sys_get()
            if enabled and server and server.startswith("127.0.0.1:"):
                sys_set(False)
        except Exception:  # noqa: BLE001
            pass

    _sys.excepthook = _main_hook
    _threading.excepthook = _thread_hook
    atexit.register(_restore_at_exit)


def _refresh_windows() -> None:
    """Tell Windows 'settings changed' so browsers pick it up instantly."""
    try:
        import ctypes
        inet = ctypes.windll.wininet.InternetSetOptionW  # type: ignore
        inet(None, 39, None, 0)   # 39 = INTERNET_OPTION_SETTINGS_CHANGED
        inet(None, 37, None, 0)   # 37 = INTERNET_OPTION_REFRESH
    except Exception:  # noqa: BLE001 — best effort only
        pass
