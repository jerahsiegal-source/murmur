"""Global hotkeys via a Windows low-level keyboard hook.

Chord behaviour:
- Hold Ctrl+Win            -> dictate while held, release -> paste
- Ctrl+Win, then Space     -> hands-free (keeps recording after release)
- Ctrl+Win again           -> stop hands-free and paste
- Ctrl+Win + any other key -> cancelled (so Ctrl+Win+D / arrows still work normally)
- Alt+Shift+Z              -> paste the last result again

The decision logic is a pure state machine (HotkeyMachine) so it can be unit tested;
KeyboardHook wires it to Windows.
"""
from __future__ import annotations

import ctypes
import logging
import queue
import threading
import time
from ctypes import wintypes
from typing import Callable

log = logging.getLogger(__name__)

VK_SHIFT, VK_CONTROL, VK_MENU = 0x10, 0x11, 0x12
VK_LSHIFT, VK_RSHIFT, VK_LCONTROL, VK_RCONTROL, VK_LMENU, VK_RMENU = 0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5
VK_LWIN, VK_RWIN = 0x5B, 0x5C
VK_SPACE = 0x20
VK_Z = 0x5A
VK_MASK = 0xE8  # unassigned; used to stop the Start menu from opening on Win release

CTRL = {VK_CONTROL, VK_LCONTROL, VK_RCONTROL}
WIN = {VK_LWIN, VK_RWIN}
SHIFT = {VK_SHIFT, VK_LSHIFT, VK_RSHIFT}
ALT = {VK_MENU, VK_LMENU, VK_RMENU}
MODIFIERS = CTRL | WIN | SHIFT | ALT
GROUPS = {"ctrl": CTRL, "win": WIN, "alt": ALT, "shift": SHIFT}

# dwExtraInfo tag on events we inject ourselves, so the hook ignores them.
MURMUR_TAG = 0x4D55524D  # "MURM"

IDLE, HOLD, HANDSFREE = "idle", "hold", "handsfree"


class HotkeyMachine:
    MIN_HOLD_S = 0.30  # shorter taps are treated as accidental

    def __init__(self, chord: str = "ctrl+win") -> None:
        """`chord` is two modifier names. Ctrl+Win is the product hotkey; tests may pass another
        pair (via MURMUR_TEST_CHORD) so they don't also trigger other dictation apps."""
        names = chord.lower().split("+")
        if len(names) != 2 or not all(n in GROUPS for n in names):
            raise ValueError(f"bad chord {chord!r}")
        self.a, self.b = GROUPS[names[0]], GROUPS[names[1]]
        self.others = [g for n, g in GROUPS.items() if n not in names]
        self.down: set[int] = set()
        self.mode = IDLE
        self.hold_start = 0.0
        self.chord_was = False
        self.chord_consumed = False
        self.suppressed_up: set[int] = set()

    def _has(self, group: set[int]) -> bool:
        return bool(self.down & group)

    def chord(self) -> bool:
        return self._has(self.a) and self._has(self.b)

    def reset(self) -> None:
        """Called when the app finishes/cancels a recording on its own."""
        self.mode = IDLE

    def key(self, vk: int, is_down: bool, now: float | None = None) -> tuple[bool, list[str]]:
        """Feed one key event. Returns (suppress_event, events)."""
        now = time.monotonic() if now is None else now
        events: list[str] = []
        suppress = False

        if vk in MODIFIERS:
            if is_down:
                self.down.add(vk)
            else:
                self.down.discard(vk)
            chord = self.chord()
            if chord and not self.chord_was:
                if self.mode == IDLE and not self.chord_consumed and not any(self._has(g) for g in self.others):
                    self.mode = HOLD
                    self.hold_start = now
                    events += ["mask", "start"]
                elif self.mode == HANDSFREE:
                    self.mode = IDLE
                    self.chord_consumed = True
                    events += ["mask", "stop"]
            elif not chord and self.chord_was:
                if self.mode == HOLD:
                    self.mode = IDLE
                    events.append("cancel" if now - self.hold_start < self.MIN_HOLD_S else "stop")
                self.chord_consumed = False
            self.chord_was = chord
            return False, events

        # non-modifier key
        if not is_down:
            if vk in self.suppressed_up:
                self.suppressed_up.discard(vk)
                return True, events
            return False, events

        if self.chord():
            if vk == VK_SPACE and self.mode in (HOLD, HANDSFREE):
                if self.mode == HOLD:
                    self.mode = HANDSFREE
                    events.append("handsfree")
                self.suppressed_up.add(vk)
                return True, events
            if self.mode == HOLD:
                # Ctrl+Win+<other>: a Windows shortcut, not dictation.
                self.mode = IDLE
                self.chord_consumed = True
                events.append("cancel")
            return False, events

        if vk == VK_Z and self._has(ALT) and self._has(SHIFT) and not self._has(CTRL) and not self._has(WIN):
            self.suppressed_up.add(vk)
            # mask: with Z swallowed, Windows would see a bare Alt+Shift tap and switch keyboard layout
            events += ["mask", "paste_last"]
            suppress = True
        return suppress, events


# ---------------------------------------------------------------- Windows glue
user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

WH_KEYBOARD_LL = 13
WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP = 0x100, 0x101, 0x104, 0x105
WM_QUIT = 0x12
LRESULT = ctypes.c_ssize_t
ULONG_PTR = ctypes.c_size_t


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
user32.SetWindowsHookExW.restype = wintypes.HHOOK
user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
user32.CallNextHookEx.restype = LRESULT
user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]


user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = ctypes.c_short


class KeyboardHook:
    """Runs the low-level hook on its own thread; delivers events on a worker thread.

    A resync thread checks the real key state every 100 ms, so a key-up that Windows never
    delivered to the hook (it skips slow hooks) can't leave a chord "stuck".
    """

    def __init__(self, on_event: Callable[[str], None]):
        import os

        self.machine = HotkeyMachine(os.environ.get("MURMUR_TEST_CHORD") or "ctrl+win")
        self.on_event = on_event
        self._events: queue.Queue[str | None] = queue.Queue()
        self._thread_id = 0
        self._hook = None
        self._proc = HOOKPROC(self._callback)  # keep a reference
        self._ready = threading.Event()
        self._lock = threading.Lock()
        self._down_at: dict[int, float] = {}
        self._stale: dict[int, int] = {}

    def start(self) -> None:
        threading.Thread(target=self._dispatch, name="hotkey-dispatch", daemon=True).start()
        threading.Thread(target=self._run, name="keyboard-hook", daemon=True).start()
        threading.Thread(target=self._resync, name="hotkey-resync", daemon=True).start()
        if not self._ready.wait(5):
            raise RuntimeError("keyboard hook did not start")

    def stop(self) -> None:
        if self._thread_id:
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        self._events.put(None)

    def reset(self) -> None:
        with self._lock:
            self.machine.reset()

    def _run(self) -> None:
        self._thread_id = kernel32.GetCurrentThreadId()
        self._hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._proc, kernel32.GetModuleHandleW(None), 0)
        if not self._hook:
            log.error("SetWindowsHookEx failed: %s", ctypes.get_last_error())
        self._ready.set()
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            pass
        if self._hook:
            user32.UnhookWindowsHookEx(self._hook)

    def _feed(self, vk: int, is_down: bool) -> bool:
        with self._lock:
            if is_down:
                self._down_at.setdefault(vk, time.monotonic())
            else:
                self._down_at.pop(vk, None)
            suppress, events = self.machine.key(vk, is_down)
        for e in events:
            self._events.put(e)
        return suppress

    def _callback(self, n_code: int, w_param: int, l_param: int) -> int:
        try:
            if n_code == 0:
                kb = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                if kb.dwExtraInfo != MURMUR_TAG:
                    if self._feed(kb.vkCode, w_param in (WM_KEYDOWN, WM_SYSKEYDOWN)):
                        return 1
        except Exception:  # never let an exception kill keyboard input
            log.exception("hook callback")
        return user32.CallNextHookEx(None, n_code, w_param, l_param)

    def _resync(self) -> None:
        while True:
            time.sleep(0.1)
            now = time.monotonic()
            for vk in list(self.machine.down):
                if now - self._down_at.get(vk, now) < 0.3:
                    continue
                if user32.GetAsyncKeyState(vk) & 0x8000:
                    self._stale.pop(vk, None)
                    continue
                self._stale[vk] = self._stale.get(vk, 0) + 1
                if self._stale[vk] >= 2:  # up for two checks in a row: we missed the key-up
                    self._stale.pop(vk, None)
                    log.warning("missed key-up for vk %#x; resyncing", vk)
                    self._feed(vk, False)

    def _dispatch(self) -> None:
        while True:
            e = self._events.get()
            if e is None:
                return
            try:
                if e == "mask":
                    from .paste import tap_key

                    tap_key(VK_MASK)
                else:
                    self.on_event(e)
            except Exception:
                log.exception("hotkey handler for %s", e)


class HotkeyProcess:
    """Runs KeyboardHook in a small separate process.

    The main process loads speech models and runs inference; if the keyboard hook lived there,
    Python could be too busy to answer Windows in time, and Windows silently drops slow hooks.
    The helper does nothing but watch keys, so it always answers instantly.
    """

    def __init__(self, on_event: Callable[[str], None]):
        self.on_event = on_event
        self._p = None
        self._stopping = False
        self._wlock = threading.Lock()

    def start(self) -> None:
        self._spawn()
        threading.Thread(target=self._watch, name="hotkey-proc-watch", daemon=True).start()

    def _spawn(self) -> None:
        import subprocess
        import sys

        self._p = subprocess.Popen(
            [sys.executable, "-m", "murmur.hotkey_host"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) | 0x00008000,  # ABOVE_NORMAL_PRIORITY_CLASS
            text=True, bufsize=1,
        )
        threading.Thread(target=self._read, args=(self._p,), name="hotkey-proc-read", daemon=True).start()

    def _read(self, p) -> None:
        for line in p.stdout:
            e = line.strip()
            if e and e != "ready":
                try:
                    self.on_event(e)
                except Exception:
                    log.exception("hotkey handler for %s", e)

    def _watch(self) -> None:
        while not self._stopping:
            time.sleep(1)
            if self._p is not None and self._p.poll() is not None and not self._stopping:
                log.warning("hotkey helper exited (%s); restarting", self._p.returncode)
                self._spawn()

    def reset(self) -> None:
        self._send("reset")

    def _send(self, cmd: str) -> None:
        with self._wlock:
            try:
                self._p.stdin.write(cmd + "\n")
                self._p.stdin.flush()
            except Exception:
                pass

    def stop(self) -> None:
        self._stopping = True
        if self._p is not None:
            try:
                self._p.stdin.close()
                self._p.wait(2)
            except Exception:
                self._p.kill()
