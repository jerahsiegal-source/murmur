"""Press Alt+Shift+Z in a fresh text box and check the last dictation arrives."""
import json, os, subprocess, sys, tempfile, time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from e2e_dictation import key, user32  # noqa: E402  (tools/ is on sys.path when run directly)

out = os.path.join(tempfile.gettempdir(), f"yappr_target_pl_{os.getpid()}.json")
p = subprocess.Popen([sys.executable, os.path.join(os.path.dirname(__file__), "paste_target.py"), out])
hwnd = 0
for _ in range(100):
    time.sleep(0.05)
    hwnd = user32.FindWindowW(None, "Yappr paste target")
    if hwnd:
        break
time.sleep(0.3)
for _ in range(20):
    if user32.GetForegroundWindow() == hwnd:
        break
    key(0xE8); key(0xE8, True); user32.SetForegroundWindow(hwnd); time.sleep(0.1)
key(0xA4); key(0xA0); key(0x5A); key(0x5A, True); key(0xA0, True); key(0xA4, True)
t = time.time()
txt = ""
for _ in range(100):
    time.sleep(0.05)
    try:
        st = json.load(open(out))
        if st["text"]:
            time.sleep(0.2); st = json.load(open(out)); txt = st["text"]; break
    except Exception:
        pass
p.terminate()
print("RESULT", "ok" if txt else "nothing pasted", f"latency_s={time.time()-t:.2f}" if txt else "")
print("TEXT:", txt[:200])
print("literal Z typed:", txt.lower().startswith("z"))
