"""End-to-end read-aloud check against the running Murmur: real hotkeys, real app, real speakers.

Focuses a window, selects all its text (Ctrl+A, or Ctrl+Shift+A in Windows Terminal), presses
Ctrl+Alt+X like a person would, and records what the speakers play (WASAPI loopback) to measure
when sound actually starts, whether it has gaps, and that Ctrl+Alt+X again stops it.

    python tools/e2e_read.py --window "read-test" [--runs 3] [--listen 8] [--select ctrl+a]
                             [--pause] [--speed] [--out results.jsonl]

Also checks the clipboard is unchanged afterwards. Needs Murmur running and the PC otherwise quiet.
"""
from __future__ import annotations

import argparse
import ctypes
import json
import subprocess
import sys
import threading
import time
from ctypes import wintypes
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from murmur.paste import get_clipboard_text, set_clipboard_text  # noqa: E402

user32 = ctypes.WinDLL("user32", use_last_error=True)
ULONG_PTR = ctypes.c_size_t


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class _U(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("pad", ctypes.c_byte * 32)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _U)]


CTRL, ALT, SHIFT, X, P, A, OEM6, OEM4 = 0xA2, 0xA4, 0xA0, 0x58, 0x50, 0x41, 0xDD, 0xDB


def key(vk: int, up: bool = False) -> None:
    i = INPUT(type=1)
    i.u.ki = KEYBDINPUT(wVk=vk, wScan=0, dwFlags=2 if up else 0, time=0, dwExtraInfo=0)  # untagged: like a person
    user32.SendInput(1, ctypes.byref(i), ctypes.sizeof(INPUT))


def chord(*vks: int, hold: float = 0.06) -> None:
    for vk in vks:
        key(vk)
        time.sleep(0.03)
    time.sleep(hold)
    for vk in reversed(vks):
        key(vk, True)
        time.sleep(0.02)


class Loopback:
    """Speaker loopback; keeps (time, rms) per 10 ms block."""

    def __init__(self):
        import pyaudiowpatch as pa

        self.pa = pa.PyAudio()
        wasapi = self.pa.get_host_api_info_by_type(pa.paWASAPI)
        spk = self.pa.get_device_info_by_index(wasapi["defaultOutputDevice"])
        if not spk.get("isLoopbackDevice"):
            spk = next(lb for lb in self.pa.get_loopback_device_info_generator() if spk["name"] in lb["name"])
        self.rate, ch = int(spk["defaultSampleRate"]), int(spk["maxInputChannels"])
        self.blocks: list[tuple[float, float]] = []
        self.lock = threading.Lock()

        def cb(data, frames, t, status):
            x = np.frombuffer(data, dtype=np.float32)
            now = time.perf_counter()
            with self.lock:
                self.blocks.append((now, float(np.sqrt(np.mean(x * x))) if len(x) else 0.0))
            return (None, pa.paContinue)

        self.s = self.pa.open(format=pa.paFloat32, channels=ch, rate=self.rate, input=True,
                              input_device_index=spk["index"], frames_per_buffer=int(self.rate * 0.01),
                              stream_callback=cb)
        self.s.start_stream()
        self.name = spk["name"]

    def window(self, t0: float, t1: float) -> list[tuple[float, float]]:
        with self.lock:
            return [(t, r) for t, r in self.blocks if t0 <= t <= t1]


TH = 0.002  # rms above this = sound


def analyse(blocks, t0):
    loud = [t for t, r in blocks if r > TH]
    if not loud:
        return None, 0, 0.0
    first = loud[0] - t0
    gaps, longest, prev = 0, 0.0, loud[0]
    for t in loud[1:]:
        if t - prev > 0.9:  # natural pauses are ~0.2-0.4 s; longer = waiting for audio
            gaps += 1
        longest = max(longest, t - prev)
        prev = t
    return first, gaps, longest


def fg_title() -> str:
    h = user32.GetForegroundWindow()
    buf = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(h, buf, 512)
    return buf.value


def focus(title: str) -> bool:
    r = subprocess.run([sys.executable, str(Path(__file__).with_name("focus_window.py")), title],
                       capture_output=True, text=True)
    time.sleep(0.6)
    return "[]" not in r.stdout.splitlines()[0] if r.stdout else False


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--window", required=True)
    ap.add_argument("--label", default="")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--listen", type=float, default=8)
    ap.add_argument("--select", default="ctrl+a", choices=["ctrl+a", "ctrl+shift+a"])
    ap.add_argument("--pause", action="store_true", help="also test Ctrl+Alt+P pause/resume")
    ap.add_argument("--speed", action="store_true", help="also test Ctrl+Alt+] and [")
    ap.add_argument("--hold-tap", action="store_true",
                    help="hold Ctrl+Alt, tap X to read, tap X again (still holding) to stop")
    ap.add_argument("--rctrl", action="store_true", help="use Right Ctrl for the hotkey")
    ap.add_argument("--out", default="")
    a = ap.parse_args()

    global CTRL
    if a.rctrl:
        CTRL = 0xA3
    lb = Loopback()
    rows = []
    sentinel = f"clipboard sentinel {time.time():.0f}"
    for i in range(a.runs):
        set_clipboard_text(sentinel, private=False)
        if not focus(a.window):
            print(json.dumps({"error": f"window not found: {a.window}"}))
            return
        # resync: if something is still being read (a previous run's stop press started a read), stop it
        if analyse(lb.window(time.perf_counter() - 0.5, time.perf_counter()), 0)[0] is not None:
            chord(CTRL, ALT, X)
            time.sleep(1.0)
        chord(0x1B)  # Escape: leave any key-tip / menu mode
        time.sleep(0.2)
        if a.select == "ctrl+a":
            chord(0xA2, A)
        else:
            chord(0xA2, SHIFT, A)
        time.sleep(0.8)
        quiet_before = analyse(lb.window(time.perf_counter() - 0.7, time.perf_counter()), 0)[0] is None
        title_before = fg_title()
        t0 = time.perf_counter()
        if a.hold_tap:
            key(CTRL); time.sleep(0.03); key(ALT); time.sleep(0.05)
            key(X); time.sleep(0.06); key(X, True)
        else:
            chord(CTRL, ALT, X)
        time.sleep(a.listen)
        row = {"label": a.label or a.window, "run": i + 1, "quiet_before": quiet_before}
        first, gaps, longest = analyse(lb.window(t0, time.perf_counter()), t0)
        row.update(first_sound_s=None if first is None else round(first, 3), gaps_over_0_9s=gaps,
                   longest_silence_s=round(longest, 2))
        if a.pause and first is not None:
            chord(CTRL, ALT, P)
            tp = time.perf_counter()
            time.sleep(2.0)
            row["silent_while_paused"] = analyse(lb.window(tp + 0.4, time.perf_counter()), 0)[0] is None
            chord(CTRL, ALT, P)
            tr = time.perf_counter()
            time.sleep(1.5)
            f2 = analyse(lb.window(tr, time.perf_counter()), tr)[0]
            row["resumed_after_s"] = None if f2 is None else round(f2, 3)
        if a.speed and first is not None:
            for _ in range(3):
                chord(CTRL, ALT, OEM6, hold=0.04)
                time.sleep(0.25)
            time.sleep(3)
            ts = time.perf_counter()
            time.sleep(2)
            row["sound_after_speed_up"] = analyse(lb.window(ts, time.perf_counter()), ts)[0] is not None
            for _ in range(3):
                chord(CTRL, ALT, OEM4, hold=0.04)
                time.sleep(0.25)
        # stop
        tstop = time.perf_counter()
        if a.hold_tap:  # second tap of X while Ctrl+Alt are still held from the first
            key(X); time.sleep(0.06); key(X, True); time.sleep(0.05)
            key(ALT, True); time.sleep(0.02); key(CTRL, True)
        else:
            chord(CTRL, ALT, X)
        time.sleep(1.5)
        row["window_title_unchanged"] = fg_title() == title_before
        row["left_ctrl_stuck"] = bool(user32.GetAsyncKeyState(0xA2) & 0x8000)
        tail = lb.window(tstop + 0.5, time.perf_counter())
        row["silent_after_stop"] = analyse(tail, 0)[0] is None
        row["clipboard_restored"] = get_clipboard_text() == sentinel
        rows.append(row)
        print(json.dumps(row), flush=True)
        time.sleep(1.0)
    if a.out:
        with open(a.out, "a", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")


if __name__ == "__main__":
    main()


def lctrl_logically_down() -> bool:
    return bool(user32.GetAsyncKeyState(0xA2) & 0x8000)
