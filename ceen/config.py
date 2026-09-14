"""App-wide constants and defaults."""

import os

APP_NAME = "Ceen Proxy"
APP_VERSION = "3.0"
DEFAULT_LIST = "free-proxy-list.txt"
DEFAULT_TEST_URL = "http://ip-api.com/json/?fields=status,country,countryCode,query"
SETTINGS_PATH = os.path.join(os.path.expanduser("~"), ".ceen_proxy.json")
DEFAULT_WORKERS = 150
DEFAULT_TIMEOUT = 6
DEFAULT_PORT = 8888

try:  # Windows-only: system proxy auto-configuration
    import winreg as _winreg  # type: ignore
except ImportError:  # pragma: no cover
    _winreg = None  # type: ignore

# Optional: enables drag-&-drop of list files (pip install tkinterdnd2)
try:  # pragma: no cover - environment dependent
    from tkinterdnd2 import DND_FILES, TkinterDnD  # type: ignore

    _DND = True
except Exception:  # noqa: BLE001 - optional dependency
    DND_FILES = None  # type: ignore
    TkinterDnD = None  # type: ignore
    _DND = False
