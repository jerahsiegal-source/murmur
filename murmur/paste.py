"""Clipboard + synthetic keystrokes (Windows only, no extra dependencies)."""
from __future__ import annotations

import ctypes
import logging
import threading
import time
from ctypes import wintypes
from typing import Callable

from .hotkeys import (
    MURMUR_TAG,
    VK_LCONTROL,
    VK_LMENU,
    VK_LSHIFT,
    VK_LWIN,
    VK_RCONTROL,
    VK_RMENU,
    VK_RSHIFT,
    VK_RWIN,
)

log = logging.getLogger(__name__)

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

ULONG_PTR = ctypes.c_size_t
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x2
CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x2
VK_V = 0x56


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.SendInput.restype = wintypes.UINT
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = ctypes.c_short
user32.OpenClipboard.argtypes = [wintypes.HWND]
user32.GetClipboardData.argtypes = [wintypes.UINT]
user32.GetClipboardData.restype = wintypes.HANDLE
user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
user32.SetClipboardData.restype = wintypes.HANDLE
user32.IsClipboardFormatAvailable.argtypes = [wintypes.UINT]
user32.RegisterClipboardFormatW.argtypes = [wintypes.LPCWSTR]
user32.RegisterClipboardFormatW.restype = wintypes.UINT
kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalFree.restype = wintypes.HGLOBAL

# Ask Windows clipboard history / cloud clipboard not to keep our dictations.
_EXCLUDE_FMT = user32.RegisterClipboardFormatW("ExcludeClipboardContentFromMonitorProcessing")


def _key_input(vk: int, up: bool) -> INPUT:
    i = INPUT(type=INPUT_KEYBOARD)
    i.u.ki = KEYBDINPUT(wVk=vk, wScan=0, dwFlags=KEYEVENTF_KEYUP if up else 0, time=0, dwExtraInfo=MURMUR_TAG)
    return i


def send_keys(seq: list[tuple[int, bool]]) -> None:
    arr = (INPUT * len(seq))(*[_key_input(vk, up) for vk, up in seq])
    n = user32.SendInput(len(seq), arr, ctypes.sizeof(INPUT))
    if n != len(seq):
        log.warning("SendInput sent %d/%d (err %s)", n, len(seq), ctypes.get_last_error())


def tap_key(vk: int) -> None:
    send_keys([(vk, False), (vk, True)])


HELD_MODIFIERS = (VK_LWIN, VK_RWIN, VK_LCONTROL, VK_RCONTROL, VK_LMENU, VK_RMENU, VK_LSHIFT, VK_RSHIFT)


def wait_modifiers_released(timeout: float = 4.0) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if not any(user32.GetAsyncKeyState(vk) & 0x8000 for vk in HELD_MODIFIERS):
            return True
        time.sleep(0.02)
    return False


def _open_clipboard() -> bool:
    for _ in range(50):
        if user32.OpenClipboard(None):
            return True
        time.sleep(0.01)
    return False


def get_clipboard_text() -> str | None:
    if not user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
        return None
    if not _open_clipboard():
        return None
    try:
        h = user32.GetClipboardData(CF_UNICODETEXT)
        if not h:
            return None
        p = kernel32.GlobalLock(h)
        try:
            return ctypes.wstring_at(p) if p else None
        finally:
            kernel32.GlobalUnlock(h)
    finally:
        user32.CloseClipboard()


def _alloc_bytes(data: bytes):
    """Movable global memory holding `data`, or None if Windows can't allocate it."""
    h = kernel32.GlobalAlloc(GMEM_MOVEABLE, max(1, len(data)))
    if not h:
        return None
    p = kernel32.GlobalLock(h)
    if not p:
        kernel32.GlobalFree(h)
        return None
    ctypes.memmove(p, data, len(data))
    kernel32.GlobalUnlock(h)
    return h


def _alloc_text(text: str):
    buf = ctypes.create_unicode_buffer(text)  # includes the terminating NUL
    return _alloc_bytes(ctypes.string_at(ctypes.addressof(buf), ctypes.sizeof(buf)))


def set_clipboard_text(text: str, private: bool = True) -> bool:
    if not _open_clipboard():
        return False
    try:
        user32.EmptyClipboard()
        h = _alloc_text(text)
        if not h:
            return False
        user32.SetClipboardData(CF_UNICODETEXT, h)
        if private and _EXCLUDE_FMT:
            h = _alloc_bytes(b"\0\0\0\0")
            if h:
                user32.SetClipboardData(_EXCLUDE_FMT, h)
        return True
    finally:
        user32.CloseClipboard()


# ---- full clipboard snapshot (text, rich text, HTML, images, copied files...)
# Formats whose data is a GDI handle rather than memory can't be copied this way; Windows
# re-creates CF_BITMAP etc. from CF_DIB, so skipping them loses nothing in practice.
_GDI_FORMATS = {2, 3, 9, 14, 0x80, 0x82, 0x83, 0x8E}  # BITMAP, METAFILEPICT, PALETTE, ENHMETAFILE, owner/dsp*
_SYNTH_FORMATS = {1, 7}  # CF_TEXT / CF_OEMTEXT are synthesized from CF_UNICODETEXT
SNAPSHOT_BUDGET_BYTES = 32 * 1024 * 1024
# Never hold up a paste for long: apps render some formats lazily. The budget is checked between
# formats, so one slow format (e.g. a huge Excel range rendered on demand) can still overrun it once.
SNAPSHOT_BUDGET_S = 0.15
_PRIVACY_FORMATS = [user32.RegisterClipboardFormatW(n) for n in (
    "ExcludeClipboardContentFromMonitorProcessing", "CanIncludeInClipboardHistory", "CanUploadToCloudClipboard")]
user32.EnumClipboardFormats.argtypes = [wintypes.UINT]
user32.EnumClipboardFormats.restype = wintypes.UINT
kernel32.GlobalSize.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalSize.restype = ctypes.c_size_t


def _read_format(fmt: int) -> bytes | None:
    h = user32.GetClipboardData(fmt)
    if not h:
        return None
    size = kernel32.GlobalSize(h)
    p = kernel32.GlobalLock(h) if size else None
    if not p:
        return None
    try:
        return ctypes.string_at(p, size)
    finally:
        kernel32.GlobalUnlock(h)


def snapshot_clipboard(budget_s: float = SNAPSHOT_BUDGET_S, budget_bytes: int = SNAPSHOT_BUDGET_BYTES):
    """Copy the clipboard's memory-based formats (text first, then the rest while time/size allow).

    Keeps privacy markers such as "ExcludeClipboardContentFromMonitorProcessing" (set by password
    managers), so restored content stays out of clipboard history. Returns None if the clipboard
    couldn't be opened.
    """
    t0 = time.monotonic()
    if not _open_clipboard():
        return None
    out, total, partial = [], 0, False
    try:
        text = _read_format(CF_UNICODETEXT) if user32.IsClipboardFormatAvailable(CF_UNICODETEXT) else None
        if text is not None:  # plain text always survives, whatever else happens
            out.append((CF_UNICODETEXT, text))
            total += len(text)
        for pf in _PRIVACY_FORMATS:  # tiny, and must survive with the text (password managers)
            if pf and user32.IsClipboardFormatAvailable(pf):
                data = _read_format(pf)
                if data is not None:
                    out.append((pf, data))
        fmt = user32.EnumClipboardFormats(0)
        while fmt:
            if fmt not in _GDI_FORMATS and fmt not in _SYNTH_FORMATS and fmt != CF_UNICODETEXT \
                    and fmt not in _PRIVACY_FORMATS:
                if time.monotonic() - t0 > budget_s or total > budget_bytes:
                    partial = True
                    break
                data = _read_format(fmt)
                if data is not None:
                    total += len(data)
                    if total > budget_bytes:
                        partial = True
                        break
                    out.append((fmt, data))
            fmt = user32.EnumClipboardFormats(fmt)
    finally:
        user32.CloseClipboard()
    dt = time.monotonic() - t0
    if partial or dt > 0.05:
        log.info("clipboard snapshot: %d formats, %.1f MB, %.0f ms%s", len(out), total / 1e6, dt * 1000,
                 " (partial: kept text and what fit)" if partial else "")
    return out


def restore_clipboard(snap: list[tuple[int, bytes]]) -> bool:
    if not _open_clipboard():
        return False
    try:
        user32.EmptyClipboard()
        for fmt, data in snap:
            h = _alloc_bytes(data)
            if h:
                user32.SetClipboardData(fmt, h)
        return True
    finally:
        user32.CloseClipboard()


_paste_lock = threading.Lock()
_pending = {"token": 0, "snapshot": None}  # a restore that hasn't happened yet


def paste_text(text: str, restore_after: float = 1.0, max_wait: float = 30.0) -> bool:
    """Put text on the clipboard, press Ctrl+V in the focused window, then put the old clipboard back.

    Never pastes while Ctrl/Win/Alt/Shift are still held (that would turn Ctrl+V into another
    shortcut); waits up to `max_wait` seconds, then gives up and leaves the result for Alt+Shift+Z.
    """
    if not text:
        return False
    if not wait_modifiers_released(max_wait):
        log.warning("modifier keys held too long; not pasting (Alt+Shift+Z pastes it)")
        return False
    with _paste_lock:
        _pending["token"] += 1
        token = _pending["token"]
        # back-to-back pastes: keep the user's original clipboard, not our previous dictation
        previous = _pending["snapshot"] if _pending["snapshot"] is not None else snapshot_clipboard()
        if not set_clipboard_text(text):
            log.error("could not put the dictation on the clipboard")
            if previous:
                restore_clipboard(previous)  # don't leave the user's clipboard empty
            _pending["snapshot"] = None
            return False
        _pending["snapshot"] = previous
        time.sleep(0.03)
        send_keys([(VK_LCONTROL, False), (VK_V, False), (VK_V, True), (VK_LCONTROL, True)])

    def restore():
        time.sleep(restore_after)
        with _paste_lock:
            if _pending["token"] != token:
                return  # a newer paste took over and will restore
            snap, _pending["snapshot"] = _pending["snapshot"], None
            # only restore if nobody replaced our text in the meantime
            if snap and get_clipboard_text() == text:
                restore_clipboard(snap)

    if restore_after > 0:
        threading.Thread(target=restore, name="clipboard-restore", daemon=True).start()
    else:
        _pending["snapshot"] = None
    return True


# ---- read the highlighted text (copy it, then put the user's clipboard back)
user32.GetClipboardSequenceNumber.restype = wintypes.DWORD
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
VK_C, VK_INSERT, VK_MASK = 0x43, 0x2D, 0xE8
# Terminals: Ctrl+C can interrupt the running program, so only Ctrl+Insert is used there.
TERMINAL_CLASSES = {"ConsoleWindowClass", "CASCADIA_HOSTING_WINDOW_CLASS", "mintty", "VirtualConsoleClass",
                    "PuTTY", "Alacritty", "org.wezfurlong.wezterm"}


def foreground_class() -> str:
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(user32.GetForegroundWindow(), buf, 256)
    return buf.value


def _press_copy_locally(copy_vk: int) -> None:
    """Fallback when the hotkey helper isn't available (tools/tests): uses the logical key state."""
    down = lambda vk: bool(user32.GetAsyncKeyState(vk) & 0x8000)  # noqa: E731
    lctrl_held = down(VK_LCONTROL)
    keys: list[tuple[int, bool]] = [(VK_LCONTROL, False)]  # before the releases: no Alt-menu / Start menu
    keys += [(vk, True) for vk in (VK_LMENU, VK_RMENU, VK_LSHIFT, VK_RSHIFT, VK_LWIN, VK_RWIN) if down(vk)]
    keys += [(copy_vk, False), (copy_vk, True)]
    if not lctrl_held:  # holding Right Ctrl: still release the Left Ctrl we pressed
        keys.append((VK_LCONTROL, True))
    send_keys(keys)


def _wait_seq(seq: int, timeout: float) -> bool:
    end = time.monotonic() + timeout
    while user32.GetClipboardSequenceNumber() == seq:
        if time.monotonic() >= end:
            return False
        time.sleep(0.01)
    return True


def _restore_if_late_copy(seq: int, before, wait: float = 2.0) -> None:
    """The app may copy after we gave up: put the user's clipboard back if that happens."""
    def run():
        if _wait_seq(seq, wait) and before is not None:
            time.sleep(0.05)
            with _paste_lock:
                restore_clipboard(before)

    threading.Thread(target=run, name="clipboard-late-copy", daemon=True).start()


def copy_selection(press: Callable[[int], None] | None = None, timeout: float = 0.6,
                   insert_wait: float = 0.2) -> str | None:
    """Copy the highlighted text in the focused window and return it (None if nothing was highlighted).

    `press(vk)` presses Ctrl+<vk> for the app; Murmur passes its hotkey helper, which knows which keys
    the user is physically holding and restores them afterwards. Ctrl+Insert is tried first because
    it only ever copies (Ctrl+C interrupts programs in terminals); Ctrl+C is the fallback outside
    terminals. The user's clipboard is put back afterwards, even if the app copies late.
    """
    press = press or _press_copy_locally
    with _paste_lock:
        before = snapshot_clipboard()
        seq = user32.GetClipboardSequenceNumber()
        terminal = foreground_class() in TERMINAL_CLASSES
        press(VK_INSERT)
        copied = _wait_seq(seq, timeout if terminal else insert_wait)
        if not copied and not terminal:
            press(VK_C)
            copied = _wait_seq(seq, timeout)
        if not copied:
            _restore_if_late_copy(seq, before)
            return None  # nothing highlighted (the app didn't copy anything)
        text = None
        for _ in range(10):  # some apps announce the copy before the text is readable
            text = get_clipboard_text()
            if text is not None:
                break
            time.sleep(0.01)
        if before is not None:
            restore_clipboard(before)
        return text
