"""Smoke test of the real device capture (mic + speaker loopback).

Plays a WAV through the default speakers while a MeetingSession records, then prints the
transcript. Usage: python tools/capture_smoke.py <wav> <out_dir>
"""
import sys
import time
import winsound
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from yappr.config import Store  # noqa: E402
from yappr.meeting import MeetingSession  # noqa: E402
from yappr.stt import Transcriber  # noqa: E402

wav, out = sys.argv[1], Path(sys.argv[2])
store = Store()
s = store.settings
tr = Transcriber(s.stt_model, s.stt_quantization, s.stt_threads, 10)
m = MeetingSession(out, "Capture smoke test", tr, None, s, on_status=lambda st: print("status:", st))
m.start()
print("devices:", m.capture.devices)
time.sleep(1.0)
winsound.PlaySound(wav, winsound.SND_FILENAME)
time.sleep(1.5)
print(f"recorded {m.elapsed():.1f}s; track samples mic={m.tracks['mic'].pos} sys={m.tracks['sys'].pos}")
m.stop()
m.wait(120)
print((m.dir / "transcript.md").read_text(encoding="utf-8"))
print("files:", sorted(p.name for p in m.dir.iterdir()))
