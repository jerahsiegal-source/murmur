"""End-to-end dictation test: drives the real hotkeys against the running app.

Usage: python tools/e2e_dictation.py <wav seconds> [handsfree]
The app must be running with MURMUR_FAKE_MIC pointing at the same WAV.
Prints the pasted text and the stop->paste latency.
"""
import ctypes, json, os, subprocess, sys, tempfile, time
from ctypes import wintypes

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from murmur.paste import INPUT, KEYBDINPUT, INPUT_KEYBOARD, KEYEVENTF_KEYUP

user32 = ctypes.WinDLL("user32")
user32.FindWindowW.restype = wintypes.HWND
user32.GetForegroundWindow.restype = wintypes.HWND
VK_LCONTROL, VK_SPACE = 0xA2, 0x20
# Second chord key: Win for the real hotkey; Alt /Shift when MURMUR_TEST_CHORD=ctrl+alt / ctrl+shift (so tests don't
# also trigger other dictation apps bound to Ctrl+Win, e.g. Wispr Flow).
VK_LWIN = {"alt": 0xA4, "shift": 0xA0}.get((os.environ.get("MURMUR_TEST_CHORD") or "ctrl+win").split("+")[1], 0x5B)


def key(vk, up=False):
    i = INPUT(type=INPUT_KEYBOARD)
    i.u.ki = KEYBDINPUT(wVk=vk, wScan=0, dwFlags=KEYEVENTF_KEYUP if up else 0, time=0, dwExtraInfo=0)
    user32.SendInput(1, ctypes.byref(i), ctypes.sizeof(INPUT))


def main():
    secs = float(sys.argv[1])
    handsfree = len(sys.argv) > 2 and sys.argv[2] == "handsfree"
    out = os.path.join(tempfile.gettempdir(), f"murmur_target_{os.getpid()}.json")
    p = subprocess.Popen([sys.executable, os.path.join(os.path.dirname(__file__), "paste_target.py"), out])
    hwnd = 0
    for _ in range(100):
        time.sleep(0.05)
        hwnd = user32.FindWindowW(None, "Murmur paste target")
        if hwnd:
            break
    time.sleep(0.3)
    for _ in range(20):  # Windows only lets the foreground app hand focus over; tap Alt to unlock
        if user32.GetForegroundWindow() == hwnd:
            break
        key(0xE8); key(0xE8, True)  # neutral key (Alt would open app menus)
        user32.SetForegroundWindow(hwnd)
        time.sleep(0.1)
    if user32.GetForegroundWindow() != hwnd:
        p.terminate(); print("RESULT: test target never got focus (not a product failure)"); sys.exit(2)
    key(VK_LCONTROL); time.sleep(0.05); key(VK_LWIN)
    t_start = time.time()
    if handsfree:
        time.sleep(0.4); key(VK_SPACE); key(VK_SPACE, True)
        time.sleep(0.1); key(VK_LWIN, True); key(VK_LCONTROL, True)
        time.sleep(max(0.0, secs + 0.3 - (time.time() - t_start)))
        key(VK_LCONTROL); key(VK_LWIN); t_stop = time.time()
        time.sleep(0.08); key(VK_LWIN, True); key(VK_LCONTROL, True)
    else:
        time.sleep(secs + 0.3)
        key(VK_LWIN, True); t_stop = time.time(); key(VK_LCONTROL, True)
    state = None
    for _ in range(300):
        time.sleep(0.05)
        try:
            state = json.load(open(out))
            if state["text"]:
                time.sleep(0.3)
                state = json.load(open(out))
                break
        except Exception:
            pass
    p.terminate()
    if not state or not state["text"]:
        print("RESULT: nothing pasted"); sys.exit(1)
    print(f"RESULT latency_s={state['first_change'] - t_stop:.2f} mode={'handsfree' if handsfree else 'hold'}")
    print("TEXT:", state["text"])


if __name__ == "__main__":
    main()
