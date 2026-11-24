"""Floating bar at the bottom of the screen (tkinter, no focus stealing), with Skip in it.

States: idle -> listening / handsfree -> processing -> idle; meeting (recording a call).
Skip's ears perk up while he's listening. Nothing animates while idle, so it costs ~0% CPU in the
background (a 30 s timer only re-checks the next-meeting countdown).
Colours and shapes follow DESIGN.md.
"""
from __future__ import annotations

import ctypes
import queue
import time
import tkinter as tk
import tkinter.font as tkfont
from ctypes import wintypes
from pathlib import Path
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

ASSETS = Path(__file__).with_name("assets")
# DESIGN.md brand colours
INK = "#2a1810"       # bar surface
EDGE = "#4a3426"      # hairline around the bar
CREAM = "#fbf8f3"     # text on the bar
MUTED = "#c9b4a2"     # secondary text on the bar (7:1 on INK)
BUTTER = "#ffe9a8"    # Notes / Stop buttons, sound wave
ROSE = "#ef8a9a"      # recording dot (always paired with a word)
KEY = "#010203"       # transparent colour for rounded corners
HOTKEY = "Ctrl+Win"


def _family() -> str:
    try:
        fams = set(tkfont.families())
    except tk.TclError:
        return "Segoe UI"
    return next((f for f in ("Segoe UI Variable Text", "Segoe UI") if f in fams), "TkDefaultFont")


def _bold(fam: str) -> str:
    return {"Segoe UI Variable Text": "Segoe UI Variable Text Semibold", "Segoe UI": "Segoe UI Semibold"}.get(fam, fam)


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


def load_skip(size: int) -> dict:
    """Skip's round badge, resting and listening (ears up), at `size` px. Empty if the images are missing."""
    try:
        from PIL import Image, ImageTk

        return {pose: ImageTk.PhotoImage(Image.open(ASSETS / f"skip-bar{suffix}.png").resize((size, size), Image.LANCZOS))
                for pose, suffix in (("rest", ""), ("listen", "-listen"))}
    except Exception:
        return {}


def bar_origin(area: tuple[int, int, int, int], w: int, h: int, position: tuple[float, float] | None,
               margin: int) -> tuple[int, int]:
    """Top-left corner for a w x h bar: bottom centre by default, else where it was dragged (kept on screen)."""
    left, top, right, bottom = area
    if position is None:
        return left + (right - left - w) // 2, bottom - h - margin
    cx, by = position
    x = int(left + cx * (right - left) - w / 2)
    y = int(top + by * (bottom - top) - h)
    return min(max(x, left), right - w), min(max(y, top), bottom - h)


def format_countdown(title: str, minutes: int) -> str:
    title = title if len(title) <= 22 else title[:21] + "…"
    return f"{title} now" if minutes <= 0 else f"{title} in {minutes} min"


class Bar:
    def __init__(self, root: tk.Tk, on_notes: Callable[[], None], on_stop_dictation: Callable[[], None],
                 on_settings: Callable[[], None], next_meeting: Callable[[], dict | None] = lambda: None,
                 position: tuple[float, float] | None = None,
                 on_moved: Callable[[tuple[float, float] | None], None] = lambda pos: None,
                 on_hide: Callable[[], None] = lambda: None):
        self.root = root
        self.on_notes = on_notes
        self.on_stop_dictation = on_stop_dictation
        self.on_settings = on_settings  # opens the Yappr window
        self.next_meeting = next_meeting
        self.on_moved = on_moved  # saves where the bar was dragged to (None = back to the default spot)
        self.on_hide = on_hide
        self.position = position  # (centre x, bottom y) as fractions of the work area; None = bottom centre
        self._drag = None
        self.s = root.winfo_fpixels("1i") / 96.0
        self.state = "idle"
        self.level = 0.0
        self.levels = [0.0] * 12
        self.meeting_started = 0.0
        self.meeting_note = ""
        self._anim = None
        self._toast_until = 0.0
        self._toast_text = ""
        self._q: queue.Queue = queue.Queue()
        fam = _family()
        self.font = (fam, 10)
        self.font_b = (_bold(fam), 10)
        self.skip = load_skip(int(30 * self.s))

        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.configure(bg=KEY)
        self.win.attributes("-transparentcolor", KEY)
        self.c = tk.Canvas(self.win, bg=KEY, highlightthickness=0, bd=0)
        self.c.pack(fill="both", expand=True)
        self.c.bind("<ButtonPress-1>", self._press)
        self.c.bind("<B1-Motion>", self._motion)
        self.c.bind("<ButtonRelease-1>", self._release)
        self.c.bind("<Button-3>", self._menu)
        self._buttons: list[tuple[tuple[float, float, float, float], Callable[[], None]]] = []
        make_noactivate(self.win)
        self.render()
        self.root.after(30, self._drain)
        self.root.after(30_000, self._minute)

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

    def _minute(self) -> None:
        if self.state == "idle":
            self.render()  # next-meeting countdown
        self.root.after(30_000, self._minute)

    def _set_state(self, state: str) -> None:
        self.state = state
        self.render()
        if state in ("listening", "handsfree", "processing", "meeting") and self._anim is None:
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

    # ---- drag to move; a press that doesn't move is a click
    def _press(self, e) -> None:
        self._drag = (e.x_root, e.y_root, self.win.winfo_x(), self.win.winfo_y(), False)

    def _motion(self, e) -> None:
        if self._drag is None:
            return
        x0, y0, wx, wy, moving = self._drag
        if not moving and abs(e.x_root - x0) + abs(e.y_root - y0) < 6 * self.s:
            return
        self._drag = (x0, y0, wx, wy, True)
        self.win.geometry(f"+{wx + e.x_root - x0}+{wy + e.y_root - y0}")

    def _release(self, e) -> None:
        drag, self._drag = self._drag, None
        if drag is None or not drag[4]:
            self._click(e)
            return
        left, top, right, bottom = work_area()
        w, h = self.win.winfo_width(), self.win.winfo_height()
        cx = (self.win.winfo_x() + w / 2 - left) / max(1, right - left)
        by = (self.win.winfo_y() + h - top) / max(1, bottom - top)
        self.position = (min(1.0, max(0.0, cx)), min(1.0, max(0.0, by)))
        self.render()  # snaps inside the screen
        self.on_moved(self.position)

    def _menu(self, e) -> None:
        m = tk.Menu(self.win, tearoff=0)
        m.add_command(label="Open Yappr", command=self.on_settings)
        m.add_command(label="Hide the bar", command=self.on_hide)
        if self.position is not None:
            m.add_command(label="Move it back to the middle", command=self.reset_position)
        m.add_separator()
        m.add_command(label="Drag the bar to move it", state="disabled")
        try:
            m.tk_popup(e.x_root, e.y_root)
        finally:
            m.grab_release()

    def reset_position(self) -> None:
        self.position = None
        self.render()
        self.on_moved(None)

    def _click(self, e) -> None:
        for (x0, y0, x1, y1), fn in self._buttons:
            if x0 <= e.x <= x1 and y0 <= e.y <= y1:
                fn()
                return
        self.on_settings()  # anywhere else on the bar opens Yappr

    def _place(self, w: int, h: int) -> None:
        left, top, right, bottom = work_area()
        if self._drag is not None and self._drag[4]:
            self.win.geometry(f"{w}x{h}")  # being dragged: keep it under the pointer
            return
        x, y = bar_origin((left, top, right, bottom), w, h, self.position, int(10 * self.s))
        self.win.geometry(f"{w}x{h}+{x}+{y}")

    def _text_w(self, text: str, bold: bool = False) -> int:
        try:
            return tkfont.Font(root=self.root, font=self.font_b if bold else self.font).measure(text)
        except tk.TclError:
            return int(7 * len(text) * self.s)

    def _countdown(self) -> str:
        try:
            ev = self.next_meeting()
        except Exception:
            ev = None
        if not ev or ev.get("in_min") is None or ev["in_min"] > 15:
            return ""
        return format_countdown(ev.get("title") or "Meeting", int(ev["in_min"]))

    def layout(self) -> list[tuple]:
        """What to draw for the current state: ("skip", pose) / ("text", str, bold, colour) / ("wave", w, colour)
        / ("dots",) / ("dot",) / ("button", label, action). Kept apart from drawing so it can be tested."""
        st = self.state
        toast = self._toast_text if time.monotonic() < self._toast_until else ""
        if toast:
            return [("skip", "rest"), ("text", toast, False, CREAM)]
        if st in ("listening", "handsfree"):
            parts = [("skip", "listen"), ("wave", 64, BUTTER)]
            if st == "handsfree":
                return parts + [("text", f"Hands-free · {HOTKEY} to stop", False, CREAM), ("button", "■ Stop", self.on_stop_dictation)]
            return parts + [("text", "Listening… let go to paste", False, CREAM)]
        if st == "processing":
            return [("skip", "rest"), ("dots",), ("text", "Typing it out…", False, MUTED)]
        if st == "meeting":
            el = int(time.monotonic() - self.meeting_started)
            return [("skip", "listen"), ("dot",), ("text", f"Taking notes {el // 3600}:{el // 60 % 60:02d}:{el % 60:02d}", True, CREAM),
                    ("wave", 48, ROSE), ("button", "■ Stop", self.on_notes)]
        soon = self._countdown()
        return [("skip", "rest"), ("text", soon or f"Hold {HOTKEY} to talk", bool(soon), CREAM if soon else MUTED),
                ("button", "Take notes" if soon else "Notes", self.on_notes)]

    def render(self) -> None:
        s, c = self.s, self.c
        c.delete("all")
        self._buttons = []
        parts = self.layout()
        H, TOP, PAD, GAP = int(40 * s), int(4 * s), int(5 * s), int(9 * s)
        widths = []
        for p in parts:
            kind = p[0]
            if kind == "skip":
                widths.append(int(30 * s))
            elif kind == "text":
                widths.append(self._text_w(p[1], p[2]))
            elif kind == "wave":
                widths.append(int(p[1] * s))
            elif kind == "dots":
                widths.append(int(26 * s))
            elif kind == "dot":
                widths.append(int(9 * s))
            elif kind == "button":
                widths.append(self._text_w(p[1], True) + int(24 * s))
        last_btn = parts[-1][0] == "button"
        W = PAD + sum(widths) + GAP * (len(parts) - 1) + (PAD if last_btn else int(16 * s))
        self.win.geometry(f"{W}x{H + TOP}")
        self._place(W, H + TOP)
        c.config(width=W, height=H + TOP)
        rounded(c, 1, TOP, W - 1, H + TOP - 1, H // 2, fill=INK, outline=EDGE)
        cy = TOP + H // 2
        x = PAD
        for p, w in zip(parts, widths):
            kind = p[0]
            if kind == "skip":
                img = self.skip.get(p[1])
                if img is not None:
                    c.create_image(x, cy, image=img, anchor="w")
                else:
                    c.create_oval(x, cy - w / 2, x + w, cy + w / 2, fill=BUTTER, outline="")
            elif kind == "text":
                c.create_text(x, cy, text=p[1], fill=p[3], font=self.font_b if p[2] else self.font, anchor="w")
            elif kind == "wave":
                self._draw_levels(x, cy, w, p[2])
            elif kind == "dots":
                phase = int(time.monotonic() * 4) % 3
                for i in range(3):
                    dx = x + int(4 * s) + i * int(9 * s)
                    c.create_oval(dx - 3 * s, cy - 3 * s, dx + 3 * s, cy + 3 * s, fill=BUTTER if i == phase else EDGE, outline="")
            elif kind == "dot":
                on = int(time.monotonic() * 2) % 2 == 0
                c.create_oval(x, cy - 4.5 * s, x + 9 * s, cy + 4.5 * s, fill=ROSE if on else "#7a3a44", outline="")
            elif kind == "button":
                bh = int(28 * s)
                rounded(c, x, cy - bh / 2, x + w, cy + bh / 2, bh // 2, fill=BUTTER, outline="")
                c.create_text(x + w / 2, cy, text=p[1], fill=INK, font=self.font_b)
                self._buttons.append(((x - 4 * s, TOP, x + w + PAD, TOP + H), p[2]))
            x += w + GAP

    def _draw_levels(self, x0: int, cy: int, width: int, color: str) -> None:
        s, n = self.s, len(self.levels)
        step = width / n
        for i, lv in enumerate(self.levels):
            h = max(3 * s, lv * 20 * s)
            x = x0 + i * step + step / 2
            self.c.create_line(x, cy - h / 2, x, cy + h / 2, fill=color, width=max(2, int(3 * s)), capstyle="round")


class MeetingPrompt:
    """Small card above the bar: Skip, "Meeting starting", the title, [Take notes] [Not now]."""

    def __init__(self, root: tk.Tk, title: str, on_start: Callable[[], None], timeout_s: float = 300):
        s = root.winfo_fpixels("1i") / 96.0
        fam = _family()
        font, font_b, font_t = (fam, 10), (_bold(fam), 10), (_bold(fam), 12)
        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.configure(bg=KEY)
        self.win.attributes("-transparentcolor", KEY)
        self.skip = load_skip(int(40 * s))
        title = (title or "Untitled meeting")[:48]

        def measure(t, f):
            return tkfont.Font(root=root, font=f).measure(t)

        W = max(int(300 * s), int(72 * s) + measure(title, font_t) + int(20 * s))
        H = int(112 * s)
        c = tk.Canvas(self.win, bg=KEY, highlightthickness=0, bd=0, width=W, height=H)
        c.pack()
        rounded(c, 1, 1, W - 1, H - 1, int(16 * s), fill=INK, outline=EDGE)
        if self.skip:
            c.create_image(int(14 * s), int(14 * s), image=self.skip["listen"], anchor="nw")
        c.create_text(int(64 * s), int(20 * s), text="Meeting starting", fill=MUTED, font=font, anchor="w")
        c.create_text(int(64 * s), int(42 * s), text=title, fill=CREAM, font=font_t, anchor="w")

        def start():
            self.close()
            on_start()

        self._buttons = []
        x, cy, bh = int(64 * s), int(84 * s), int(30 * s)
        for label, fn, primary in (("Take notes", start, True), ("Not now", self.close, False)):
            bw = measure(label, font_b) + int(28 * s)
            rounded(c, x, cy - bh / 2, x + bw, cy + bh / 2, bh // 2, fill=BUTTER if primary else INK,
                    outline=BUTTER if primary else MUTED)
            c.create_text(x + bw / 2, cy, text=label, fill=INK if primary else CREAM, font=font_b)
            self._buttons.append(((x, cy - bh / 2, x + bw, cy + bh / 2), fn))
            x += bw + int(10 * s)

        def click(e):
            for (x0, y0, x1, y1), fn in self._buttons:
                if x0 <= e.x <= x1 and y0 <= e.y <= y1:
                    fn()
                    return

        c.bind("<Button-1>", click)
        c.configure(cursor="hand2")
        make_noactivate(self.win)
        left, top, right, bottom = work_area()
        self.win.geometry(f"{W}x{H}+{left + (right - left - W) // 2}+{bottom - H - int(62 * s)}")
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
