"""Two dictations back to back (the second starts right after the first is released), plus a check
that a non-text clipboard item survives. Needs the app running with YAPPR_FAKE_MIC set.

Usage: python tools/e2e_back_to_back.py <wav seconds> [word the clip contains, default Priya]
"""
import ctypes
import json
import os
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from e2e_dictation import VK_LCONTROL, VK_LWIN, key, user32  # noqa: E402
from yappr import paste  # noqa: E402

secs = float(sys.argv[1])
expect = sys.argv[2] if len(sys.argv) > 2 else "Priya"  # a word the fake-mic clip says once

# put a custom (non-text) item on the clipboard, like a copied image would be
fmt = paste.user32.RegisterClipboardFormatW("Yappr Test Binary")
marker = b"not text, should survive" * 4
assert paste._open_clipboard()
paste.user32.EmptyClipboard()
h = paste.kernel32.GlobalAlloc(paste.GMEM_MOVEABLE, len(marker))
p = paste.kernel32.GlobalLock(h)
ctypes.memmove(p, marker, len(marker))
paste.kernel32.GlobalUnlock(h)
paste.user32.SetClipboardData(fmt, h)
paste.user32.CloseClipboard()

out = os.path.join(tempfile.gettempdir(), f"yappr_target_b2b_{os.getpid()}.json")
proc = subprocess.Popen([sys.executable, os.path.join(os.path.dirname(__file__), "paste_target.py"), out])
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

for n in range(2):
    key(VK_LCONTROL); time.sleep(0.05); key(VK_LWIN)
    time.sleep(secs + 0.3)
    key(VK_LWIN, True); key(VK_LCONTROL, True)
    time.sleep(0.15)  # start the next one almost immediately, while the first is still finishing

text = ""
for _ in range(200):
    time.sleep(0.05)
    try:
        text = json.load(open(out))["text"]
        if text.count(expect) >= 2:
            break
    except Exception:
        pass
time.sleep(1.5)  # let the clipboard restore run
proc.terminate()
snap = dict(paste.snapshot_clipboard() or [])
print("RESULT dictations pasted:", text.count(expect), "/ 2")
print("TEXT:", text)
print("RESULT non-text clipboard item restored:", snap.get(fmt, b"")[:len(marker)] == marker)
