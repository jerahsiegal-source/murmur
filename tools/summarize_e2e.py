"""Summarize e2e_read.py JSON lines from stdin."""
import json
import statistics as st
import sys

rows = [json.loads(x) for x in sys.stdin if x.startswith("{")]
f = [r["first_sound_s"] for r in rows]
ok = [x for x in f if x is not None]
print("first sound (s):", f)
if ok:
    print(f"median {st.median(ok):.2f} max {max(ok):.2f} | no sound: {f.count(None)} | gaps>0.9s: "
          f"{sum(r['gaps_over_0_9s'] for r in rows)} | stopped: {all(r['silent_after_stop'] for r in rows)} | "
          f"clipboard restored: {all(r['clipboard_restored'] for r in rows)} | "
          f"document unchanged: {all(r.get('window_title_unchanged', True) for r in rows)}")
