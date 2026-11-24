"""Press the dictation hotkeys into whatever window is focused (no test window).

Usage: python tools/hotkey_only.py <seconds> [handsfree] [delay_before_s]
"""
import sys
import time

from e2e_dictation import VK_LCONTROL, VK_LWIN, VK_SPACE, key

secs = float(sys.argv[1])
handsfree = len(sys.argv) > 2 and sys.argv[2] == "handsfree"
time.sleep(float(sys.argv[3]) if len(sys.argv) > 3 else 0)
key(VK_LCONTROL); time.sleep(0.05); key(VK_LWIN)
if handsfree:
    time.sleep(0.4); key(VK_SPACE); key(VK_SPACE, True)
    time.sleep(0.1); key(VK_LWIN, True); key(VK_LCONTROL, True)
    time.sleep(secs)
    key(VK_LCONTROL); key(VK_LWIN); time.sleep(0.08); key(VK_LWIN, True); key(VK_LCONTROL, True)
else:
    time.sleep(secs + 0.3)
    key(VK_LWIN, True); key(VK_LCONTROL, True)
print("keys sent")
