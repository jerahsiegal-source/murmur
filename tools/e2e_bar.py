"""Drag the live bar somewhere else, check the spot is saved and survives a restart, then open its
right-click menu and hide it. Uses the real mouse (it moves the pointer for a moment).

    python tools/e2e_bar.py <data dir of the running test app> <out dir> <fake mic wav>
"""
import ctypes
import json
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

from PIL import ImageGrab

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from grab import windows  # noqa: E402
from measure_quick import yappr_procs  # noqa: E402

ctypes.windll.shcore.SetProcessDpiAwareness(2)
user32 = ctypes.WinDLL("user32")


PIDS: set = set()


def bar_rect():
    if not PIDS:
        PIDS.update(p.pid for p in yappr_procs())  # slow (scans every process), so once per app start
    found = [b for t, b in windows(PIDS) if (b[2] - b[0]) < 900 and (b[3] - b[1]) < 80]
    return found[0] if found else None


def mouse(x, y, flags):
    user32.SetCursorPos(int(x), int(y))
    if flags:
        user32.mouse_event(flags, 0, 0, 0, 0)


def main():
    data, out, wav = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
    r0 = bar_rect()
    print("bar before:", r0)
    sx, sy = r0[0] + 80, (r0[1] + r0[3]) // 2  # on the hint text, not a button
    mouse(sx, sy, 0x0002)  # left down
    for i in range(1, 21):
        mouse(sx - 30 * i, sy - 25 * i, 0x0001)  # move
        time.sleep(0.02)
    mouse(sx - 600, sy - 500, 0x0004)  # left up
    time.sleep(0.8)
    r1 = bar_rect()
    print("bar after drag:", r1)
    pos = json.loads((data / "settings.json").read_text(encoding="utf-8")).get("bar_position")
    print("saved position:", pos)
    ImageGrab.grab(all_screens=False).crop((r1[0] - 40, r1[1] - 40, r1[2] + 40, r1[3] + 40)).save(out / "bar-moved.png")

    subprocess.run([sys.executable, str(HERE / "run_fresh.py"), str(data), wav], check=True, capture_output=True)
    time.sleep(6)
    PIDS.clear()
    r2 = bar_rect()
    print("bar after restart:", r2, "same spot:", r2 is not None and abs(r2[0] - r1[0]) <= 2 and abs(r2[1] - r1[1]) <= 2)

    cx, cy = (r2[0] + r2[2]) // 2, (r2[1] + r2[3]) // 2
    mouse(r2[0] + 80, cy, 0x0008); mouse(r2[0] + 80, cy, 0x0010)  # right click
    time.sleep(0.8)
    ImageGrab.grab().crop((r2[0] - 20, r2[1] - 20, r2[0] + 420, r2[3] + 160)).save(out / "bar-menu.png")
    # click "Hide the bar" (2nd item; the menu opens at the pointer). Never send keys: the bar doesn't take
    # keyboard focus, so keys would go to whatever app is in front.
    s = ctypes.windll.user32.GetDpiForSystem() / 96
    mouse(r2[0] + 80 + 60 * s, cy + 27 * s, 0x0002); mouse(r2[0] + 80 + 60 * s, cy + 27 * s, 0x0004)
    time.sleep(1.2)
    print("bar visible after 'Hide the bar':", bar_rect() is not None,
          "| show_bar saved:", json.loads((data / "settings.json").read_text(encoding="utf-8")).get("show_bar"))
    mouse(cx, cy - 300, 0)


if __name__ == "__main__":
    main()
