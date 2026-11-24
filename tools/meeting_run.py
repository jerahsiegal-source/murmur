"""Run the real meeting pipeline on a recorded two-track call (played back in real time or faster).

Usage: python tools/meeting_run.py <dir with mic.wav/sys.wav> <out_meetings_dir> [speed] [chunk_s]
Prints RSS over time, then the transcript/summary paths. Uses the API key from Credential
Manager / MURMUR_ANTHROPIC_API_KEY (Claude) or MURMUR_API_KEY (OpenAI-compatible) if present (for the summary); otherwise the summary is a placeholder.
"""
import os
import sys
import threading
import time
from pathlib import Path

import numpy as np
import psutil
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from murmur.config import Store  # noqa: E402
from murmur.llm import make_llm  # noqa: E402
from murmur.meeting import MeetingSession, SR  # noqa: E402
from murmur.stt import Transcriber  # noqa: E402

src, out = Path(sys.argv[1]), Path(sys.argv[2])
speed = float(sys.argv[3]) if len(sys.argv) > 3 else 1.0
chunk_s = int(sys.argv[4]) if len(sys.argv) > 4 else 300


class FilePlayback:
    """Stands in for Capture: writes the two tracks at `speed` x real time."""

    def __init__(self, mic_track, sys_track):
        self.tracks = {"mic": mic_track, "sys": sys_track}
        # stream from disk (like a real device) so the harness doesn't inflate the process's memory
        self.files = {k: sf.SoundFile(src / f"{k}.wav") for k in self.tracks}
        self._stop = threading.Event()
        self.done = threading.Event()
        self.devices = {"mic": "file playback", "sys": "file playback"}

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        blk = SR // 10
        n = max(f.frames for f in self.files.values())
        t0 = time.monotonic()
        for i in range(0, n, blk):
            if self._stop.is_set():
                break
            for k, tr in self.tracks.items():
                tr.write(self.files[k].read(blk, dtype="float32"))
            delay = t0 + (i + blk) / SR / speed - time.monotonic()
            if delay > 0:
                time.sleep(delay)
        self.done.set()

    def stop(self):
        self._stop.set()


store = Store()
s = store.settings
llm = make_llm(s.llm_provider, s.llm_base_url, Store.get_api_key(s.llm_provider), s.llm_model,
               s.price_in_per_m, s.price_out_per_m, store.root / "usage.jsonl")
tr = Transcriber(s.stt_model, s.stt_quantization, s.stt_threads, s.stt_idle_unload_min)
proc = psutil.Process()
holder = {}


def factory(m, sy):
    holder["pb"] = FilePlayback(m, sy)
    return holder["pb"]


m = MeetingSession(out, "Northwind kickoff (test)", tr, llm, s, on_status=lambda st: print("status:", st, flush=True),
                   chunk_s=chunk_s, capture_factory=factory,
                   dictionary=lambda: store.dictionary)
print(f"start RSS {proc.memory_info().rss / 1e6:.0f} MB", flush=True)
t0 = time.monotonic()
m.start()
samples = []
while not holder["pb"].done.wait(30 / max(speed, 1)):
    rss = proc.memory_info().rss / 1e6
    samples.append(rss)
    print(f"t={m.elapsed() * speed / 60:5.1f} call-min  RSS {rss:.0f} MB  lines={m.lines_written}", flush=True)
m.stop()
t_stop = time.monotonic()
m.wait()
print(f"stop->notes ready: {time.monotonic() - t_stop:.1f}s; RSS min/max during call: {min(samples):.0f}/{max(samples):.0f} MB")
print("folder:", m.dir)
print("files:", sorted(p.name for p in m.dir.iterdir()))
