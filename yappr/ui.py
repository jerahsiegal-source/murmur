"""Floating bar at the bottom of the screen (tkinter, no focus stealing).

States: idle -> listening / handsfree -> processing -> idle; meeting (recording a call).
Nothing animates while idle, so it costs ~0% CPU in the background.
"""
from __future__ import annotations

import ctypes
import queue
import time
import tkinter as tk
from ctypes import wintypes
from typing import Callable

user32 = ctypes.WinDLL("user32", use_last_error=True)

GWL_EXSTYLE = -20
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_TOPMOST = 0x00000008
SPI_GETWORKAREA = 0x0030
user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
user32.GetParent.restype = wintypes.HWND
user32.GetParent.argtypes = [wintypes.HWND]

BG = "#18181b"
FG = "#f4f4f5"
MUTED = "#8b8b94"
ACCENT = "#8ab4ff"
RED = "#ff5c5c"
KEY = "#010203"  # transparent colour for rounded corners
FONT = ("Segoe UI", 9)
FONT_B = ("Segoe UI Semibold", 9)


def work_area() -> tuple[int, int, int, int]:
    r = wintypes.RECT()
    user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(r), 0)
    return r.left, r.top, r.right, r.bottom


def make_noactivate(win: tk.Misc) -> None:
    win.update_idletasks()
    hwnd = user32.GetParent(win.winfo_id()) or win.winfo_id()
    style = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
    user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, style | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_TOPMOST)


def rounded(c: tk.Canvas, x0, y0, x1, y1, r, **kw):
    pts = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1, x1 - r, y1, x0 + r, y1, x0, y1, x0, y1 - r, x0, y0 + r, x0, y0]
    return c.create_polygon(pts, smooth=True, **kw)


class Bar:
    def __init__(self, root: tk.Tk, on_notes: Callable[[], None], on_stop_dictation: Callable[[], None],
                 on_settings: Callable[[], None]):
        self.root = root
        self.on_notes = on_notes
        self.on_stop_dictation = on_stop_dictation
        self.on_settings = on_settings
        self.s = root.winfo_fpixels("1i") / 96.0
        self.state = "idle"
        self.level = 0.0
        self.levels = [0.0] * 14
        self.meeting_started = 0.0
        self.meeting_note = ""
        self._anim = None
        self._toast_until = 0.0
        self._toast_text = ""
        self._q: queue.Queue = queue.Queue()

        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.configure(bg=KEY)
        self.win.attributes("-transparentcolor", KEY)
        self.c = tk.Canvas(self.win, bg=KEY, highlightthickness=0, bd=0)
        self.c.pack(fill="both", expand=True)
        self.c.bind("<Button-1>", self._click)
        self.c.bind("<Button-3>", lambda e: self.on_settings())
        self.c.bind("<Enter>", lambda e: self._hover(True))
        self.c.bind("<Leave>", lambda e: self._hover(False))
        self.hover = False
        self._buttons: list[tuple[tuple[float, float, float, float], Callable[[], None]]] = []
        make_noactivate(self.win)
        self.render()
        self.root.after(30, self._drain)

    # ---- thread-safe API (call from any thread)
    def post(self, fn: Callable[[], None]) -> None:
        self._q.put(fn)

    def set_state(self, state: str) -> None:
        self.post(lambda: self._set_state(state))

    def set_level(self, level: float) -> None:
        self.level = level  # read by the animation loop; plain float write is atomic

    def toast(self, text: str, secs: float = 2.5) -> None:
        def f():
            self._toast_text, self._toast_until = text, time.monotonic() + secs
            self.render()
            self.root.after(int(secs * 1000) + 50, self.render)

        self.post(f)

    # ---- internals
    def _drain(self) -> None:
        try:
            while True:
                self._q.get_nowait()()
        except queue.Empty:
            pass
        self.root.after(30, self._drain)

    def _set_state(self, state: str) -> None:
        self.state = state
        self.render()
        animated = state in ("listening", "handsfree", "processing", "meeting")
        if animated and self._anim is None:
            self._tick()

    def _tick(self) -> None:
        if self.state not in ("listening", "handsfree", "processing", "meeting"):
            self._anim = None
            self.render()
            return
        lv = min(1.0, (self.level * 12) ** 0.6)
        self.levels = self.levels[1:] + [lv]
        self.render()
        self._anim = self.root.after(250 if self.state == "meeting" else 60, self._tick)

    def _hover(self, on: bool) -> None:
        self.hover = on
        self.render()

    def _click(self, e) -> None:
        for (x0, y0, x1, y1), fn in self._buttons:
            if x0 <= e.x <= x1 and y0 <= e.y <= y1:
                fn()
                return

    def _place(self, w: int, h: int) -> None:
        left, top, right, bottom = work_area()
        x = left + (right - left - w) // 2
        y = bottom - h - int(10 * self.s)
        self.win.geometry(f"{w}x{h}+{x}+{y}")

    def render(self) -> None:
        s, c = self.s, self.c
        c.delete("all")
        self._buttons = []
        st = self.state
        toast = self._toast_text if time.monotonic() < self._toast_until else ""
        H = int(30 * s)
        if st == "idle" and not toast:
            W = int((172 if self.hover else 96) * s)
        elif st == "meeting":
            W = int(250 * s)
        elif toast:
            W = int(max(120, 7.2 * len(toast) + 30) * s)
        else:
            W = int(170 * s)
        TOP = int(4 * s)
        self.win.geometry(f"{W}x{H + TOP}")
        self._place(W, H + TOP)
        c.config(width=W, height=H + TOP)
        rounded(c, 1, TOP, W - 1, H + TOP - 1, int(14 * s), fill=BG, outline="#2e2e33")
        cy = TOP + H // 2

        if toast:
            c.create_text(W // 2, cy, text=toast, fill=FG, font=FONT)
            return

        if st == "idle":
            # mic glyph (dots) + Notes button
            for i, hgt in enumerate((3, 6, 9, 6, 3)):
                x = int((16 + i * 5) * s)
                c.create_line(x, cy - hgt * s / 2, x, cy + hgt * s / 2, fill=MUTED, width=max(2, int(2 * s)), capstyle="round")
            bx0 = int(48 * s)
            c.create_oval(bx0, cy - 4 * s, bx0 + 8 * s, cy + 4 * s, fill=RED, outline="")
            c.create_text(bx0 + 13 * s, cy, text="Notes", fill=FG, font=FONT, anchor="w")
            self._buttons.append(((bx0 - 10 * s, TOP, W, TOP + H), self.on_notes))
            if self.hover:
                c.create_text(W - 10 * s, cy, text="Ctrl+Win", fill=MUTED, font=FONT, anchor="e")
            return

        if st in ("listening", "handsfree"):
            self._draw_levels(int(18 * s), cy, int(110 * s), ACCENT)
            if st == "handsfree":
                x = W - int(26 * s)
                c.create_rectangle(x, cy - 5 * s, x + 10 * s, cy + 5 * s, fill=FG, outline="")
                self._buttons.append(((x - 10 * s, TOP, W, TOP + H), self.on_stop_dictation))
            else:
                c.create_text(W - 12 * s, cy, text="●", fill=RED, font=FONT, anchor="e")
            return

        if st == "processing":
            phase = int(time.monotonic() * 4) % 3
            for i in range(3):
                x = W // 2 + (i - 1) * int(12 * s)
                col = FG if i == phase else MUTED
                c.create_oval(x - 3 * s, cy - 3 * s, x + 3 * s, cy + 3 * s, fill=col, outline="")
            return

        if st == "meeting":
            el = int(time.monotonic() - self.meeting_started)
            blink = int(time.monotonic() * 2) % 2 == 0
            c.create_oval(12 * s, cy - 4 * s, 20 * s, cy + 4 * s, fill=RED if blink else "#7a2e2e", outline="")
            c.create_text(26 * s, cy, text=f"{el // 3600}:{el // 60 % 60:02d}:{el % 60:02d}", fill=FG, font=FONT_B, anchor="w")
            self._draw_levels(int(90 * s), cy, int(80 * s), RED)
            bx = W - int(54 * s)
            c.create_text(bx, cy, text="■ Stop", fill=FG, font=FONT_B, anchor="w")
            self._buttons.append(((bx - 8 * s, TOP, W, TOP + H), self.on_notes))

    def _draw_levels(self, x0: int, cy: int, width: int, color: str) -> None:
        s, n = self.s, len(self.levels)
        step = width / n
        for i, lv in enumerate(self.levels):
            h = max(2 * s, lv * 18 * s)
            x = x0 + i * step
            self.c.create_line(x, cy - h / 2, x, cy + h / 2, fill=color, width=max(2, int(3 * s)), capstyle="round")


class MeetingPrompt:
    """Small card above the bar: 'Meeting starting: X  [Start notes] [Dismiss]'."""

    def __init__(self, root: tk.Tk, title: str, on_start: Callable[[], None], timeout_s: float = 300):
        s = root.winfo_fpixels("1i") / 96.0
        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.configure(bg=BG, highlightthickness=1, highlightbackground="#2e2e33")
        tk.Label(self.win, text="Meeting starting", bg=BG, fg=MUTED, font=FONT).pack(anchor="w", padx=12, pady=(10, 0))
        tk.Label(self.win, text=title[:60] or "(untitled)", bg=BG, fg=FG, font=("Segoe UI Semibold", 10)).pack(anchor="w", padx=12)
        row = tk.Frame(self.win, bg=BG)
        row.pack(fill="x", padx=12, pady=10)

        def start():
            self.close()
            on_start()

        for text, cmd, bg in (("Start notes", start, ACCENT), ("Dismiss", self.close, "#2e2e33")):
            b = tk.Label(row, text=text, bg=bg, fg="#000" if bg == ACCENT else FG, font=FONT_B, padx=10, pady=4, cursor="hand2")
            b.pack(side="left", padx=(0, 8))
            b.bind("<Button-1>", lambda e, f=cmd: f())
        make_noactivate(self.win)
        self.win.update_idletasks()
        w, h = self.win.winfo_reqwidth(), self.win.winfo_reqheight()
        left, top, right, bottom = work_area()
        self.win.geometry(f"+{left + (right - left - w) // 2}+{bottom - h - int(52 * s)}")
        root.after(int(timeout_s * 1000), self.close)

    def alive(self) -> bool:
        try:
            return bool(self.win.winfo_exists())
        except tk.TclError:
            return False

    def close(self) -> None:
        try:
            self.win.destroy()
        except tk.TclError:
            pass
