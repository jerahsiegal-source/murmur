"""Screenshot Yappr's own windows (the bar, the main window, prompts) from the live app.

    python tools/grab.py <out.png> [window|bar|all]

Finds top-level windows of the running Yappr processes and captures them with Pillow (no other app is
captured: only these rectangles).
"""
import ctypes
import sys
from ctypes import wintypes
from pathlib import Path

from PIL import Image, ImageGrab

sys.path.insert(0, str(Path(__file__).parent))
from measure_quick import yappr_procs  # noqa: E402

ctypes.windll.shcore.SetProcessDpiAwareness(2)
user32 = ctypes.WinDLL("user32")


hwnds = []


def print_window(hwnd, box):
    """The window's own pixels, even if other windows cover it (PrintWindow, full content)."""
    gdi32 = ctypes.WinDLL("gdi32")
    w, h = box[2] - box[0], box[3] - box[1]
    hdc = user32.GetWindowDC(hwnd)
    mem = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    gdi32.SelectObject(mem, bmp)
    user32.PrintWindow(hwnd, mem, 2)  # PW_RENDERFULLCONTENT
    buf = ctypes.create_string_buffer(w * h * 4)
    bmi = (ctypes.c_uint32 * 10)(40, w, -h, 1 | (32 << 16), 0, 0, 0, 0, 0, 0)
    gdi32.GetDIBits(mem, bmp, 0, h, buf, bmi, 0)
    img = Image.frombuffer("RGBA", (w, h), buf, "raw", "BGRA", 0, 1).convert("RGB")
    gdi32.DeleteObject(bmp); gdi32.DeleteDC(mem); user32.ReleaseDC(hwnd, hdc)
    return img


def windows(pids):
    out = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def each(hwnd, _):
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value in pids and user32.IsWindowVisible(hwnd):
            r = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(r))
            n = user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            if r.right - r.left > 20 and r.bottom - r.top > 20:
                out.append((buf.value, (r.left, r.top, r.right, r.bottom)))
                hwnds.append(hwnd)
        return True

    user32.EnumWindows(each, 0)
    return out


def main():
    out, which = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else "window")
    app = {p.pid for p in yappr_procs()}
    win = {p.pid for p in yappr_procs("yappr.window")}
    found = windows(win if which == "window" else app if which == "bar" else app | win)
    if not found:
        sys.exit("no Yappr window found")
    for i, (title, box) in enumerate(found):
        if which == "window" and title != "Yappr":
            continue
        path = out if i == 0 or which == "window" else out.replace(".png", f"-{i}.png")
        img = print_window(hwnds[i], box) if which == "window" else ImageGrab.grab(bbox=box, all_screens=True)
        img.save(path)
        print(title or "(untitled)", box, "->", path)
        if which == "window":
            break


if __name__ == "__main__":
    main()
