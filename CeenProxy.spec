# -*- mode: python ; coding: utf-8 -*-
# PyInstaller recipe for Ceen Proxy.
#
# Build with:  pyinstaller CeenProxy.spec
# Result:      dist/CeenProxy.exe  (one file, no Python needed)
#
# Notes:
#  * onefile  = a single .exe that unpacks itself to a temp dir at launch
#  * windowed = no black console window behind the GUI
#  * dearpygui ships runtime data that its hook already knows about;
#    we still exclude test/build clutter to keep the exe lean.

a = Analysis(
    ["proxy_checker.py"],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter", "tests", "pyinstaller", "setuptools", "pip",
        "unittest", "xml", "pydoc_data",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="CeenProxy",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                      # UPX can trip antivirus; not worth it
    console=False,                  # GUI app: no console window
    icon="assets/ceen.ico",
)
