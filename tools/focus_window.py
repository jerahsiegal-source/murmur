"""Restore and focus the first top-level window whose title contains the given text."""
import ctypes
import sys
from ctypes import wintypes

u = ctypes.WinDLL("user32")
needle = sys.argv[1].lower()
found = []


@ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
def cb(h, _):
    n = u.GetWindowTextLengthW(h)
    if n and u.IsWindowVisible(h):
        buf = ctypes.create_unicode_buffer(n + 1)
        u.GetWindowTextW(h, buf, n + 1)
        if needle in buf.value.lower():
            found.append((h, buf.value))
    return True


u.EnumWindows(cb, 0)
print(found)
if found:
    h = found[0][0]
    u.ShowWindow(h, 9)  # SW_RESTORE
    u.keybd_event(0xE8, 0, 0, 0); u.keybd_event(0xE8, 0, 2, 0)  # neutral key: lets us take focus without Alt side effects
    u.SetForegroundWindow(h)
