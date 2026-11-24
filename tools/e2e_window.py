"""Drive the live Yappr window: focus it, then dictate into it with the test chord (Ctrl+Shift).

    python tools/e2e_window.py dictate <seconds>

Refuses to press anything unless Yappr's window is in front, so keys never land in another app.
"""
import ctypes
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from e2e_dictation import key  # noqa: E402
from grab import windows  # noqa: E402
from measure_quick import yappr_procs  # noqa: E402

user32 = ctypes.WinDLL("user32")
user32.GetForegroundWindow.restype = ctypes.c_void_p


def focus() -> int:
    import grab

    grab.hwnds.clear()
    found = windows({p.pid for p in yappr_procs("yappr.window")})
    hwnd = next((grab.hwnds[i] for i, (t, _) in enumerate(found) if t == "Yappr"), None)
    if not hwnd:
        sys.exit("Yappr window not found")
    for _ in range(20):
        user32.ShowWindow(hwnd, 9)
        key(0xE8); key(0xE8, True)
        user32.SetForegroundWindow(hwnd)
        time.sleep(0.15)
        if user32.GetForegroundWindow() == hwnd:
            return hwnd
    sys.exit("could not bring Yappr's window to the front; not pressing any keys")


DRIVE = Path(__import__("tempfile").gettempdir()) / "yappr-window-test"


def js(code: str, timeout: float = 20):
    """Run JavaScript in the live window (needs the app started with YAPPR_WINDOW_TEST_DIR=DRIVE)."""
    import json

    DRIVE.mkdir(exist_ok=True)
    name = f"{time.time_ns()}"
    (DRIVE / f"{name}.js").write_text(code, encoding="utf-8")
    out = DRIVE / f"{name}.out"
    end = time.time() + timeout
    while time.time() < end:
        if out.exists():
            r = json.loads(out.read_text(encoding="utf-8"))
            out.unlink()
            return r["value"]
        time.sleep(0.1)
    raise TimeoutError(code[:60])


def dictate(secs: float) -> None:
    hwnd = focus()
    t0 = time.time()
    key(0xA2); key(0xA0)  # left Ctrl + left Shift: the test chord
    time.sleep(secs)
    if user32.GetForegroundWindow() != hwnd:
        print("warning: focus moved while dictating")
    key(0xA0, True); key(0xA2, True)
    print(f"held {time.time() - t0:.1f}s")


def main():
    if sys.argv[1] == "dictate":
        dictate(float(sys.argv[2]))
    elif sys.argv[1] == "js":
        print(js(sys.argv[2]))


if __name__ == "__main__":
    main()
