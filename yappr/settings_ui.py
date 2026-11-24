"""Helpers behind the Settings page: start with Windows, and the list of microphones.

The Settings page itself is part of the Yappr window (yappr/window.py, yappr/web); it reads and saves
through yappr/api.py.
"""
from __future__ import annotations

import os
import sys
import winreg
from pathlib import Path

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def startup_command() -> str:
    exe = Path(sys.executable)
    pyw = exe.with_name("pythonw.exe") if exe.name.lower() == "python.exe" else exe
    return f'"{pyw}" -m yappr'


STARTUP_VALUE = "Yappr"
LEGACY_STARTUP_VALUE = "Murmur"  # the app's old name


def startup_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, STARTUP_VALUE)
            return True
    except OSError:
        return False


def set_startup(on: bool) -> None:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if on:
            winreg.SetValueEx(k, STARTUP_VALUE, 0, winreg.REG_SZ, startup_command())
        else:
            try:
                winreg.DeleteValue(k, STARTUP_VALUE)
            except OSError:
                pass


def legacy_startup_shortcut() -> Path:
    """Murmur could also start with Windows through a shortcut in the Startup folder."""
    return Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs/Startup/Murmur.lnk"


def _starts_murmur(lnk: Path) -> bool:
    try:
        data = lnk.read_bytes()
    except OSError:
        return False
    return any("-m murmur".encode(enc) in data for enc in ("utf-16-le", "ascii"))


def migrate_startup() -> bool:
    """If Murmur was set to start with Windows, start Yappr instead. Returns True if it changed anything."""
    changed = False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_QUERY_VALUE | winreg.KEY_SET_VALUE) as k:
            winreg.QueryValueEx(k, LEGACY_STARTUP_VALUE)
            winreg.SetValueEx(k, STARTUP_VALUE, 0, winreg.REG_SZ, startup_command())
            winreg.DeleteValue(k, LEGACY_STARTUP_VALUE)  # its command (-m murmur) no longer exists
            changed = True
    except OSError:
        pass
    lnk = legacy_startup_shortcut()
    if _starts_murmur(lnk):
        set_startup(True)  # before removing the shortcut, so a failure never leaves nothing starting
        lnk.unlink()
        changed = True
    return changed


def input_devices() -> list[str]:
    """Microphones, named the way the recorder expects them ("<name>, MME")."""
    try:
        import sounddevice as sd

        api = next(i for i, a in enumerate(sd.query_hostapis()) if "MME" in a["name"])
        return sorted({f"{d['name']}, MME" for d in sd.query_devices() if d["max_input_channels"] > 0 and d["hostapi"] == api})
    except Exception:
        return []
