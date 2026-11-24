"""Time read-aloud without making sound: real Kokoro voice, a fake speaker that consumes audio
at real-time pace (10 ms blocks), so first-audio time and gaps are what you'd hear.

    python tools/read_bench.py [--idle-min N] [--speed S] [--out results.jsonl]

Reads a short reply and a 2,000+ word AI reply (cleaned like the hotkey path does), warm, and
optionally once more after N idle minutes (model stays loaded; keepalive runs as in the app).
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from yappr import tts  # noqa: E402
from yappr.speech_text import clean_for_speech  # noqa: E402

SHORT = ("Done. I fixed the paste bug in `yappr/paste.py:214` and reran the tests: all 74 pass. "
         "See D:\\home\\me\\Documents\\Projects\\Voice-to-text\\loop\\progress.md for the log.")


def long_reply() -> str:
    paras = []
    for i in range(1, 31):
        paras.append(
            f"## Step {i}: update the module\n\n"
            f"In step {i}, I changed `yappr/module_{i}.py` so it reads settings from "
            f"D:\\home\\me\\AppData\\Local\\Yappr\\settings.json before it starts. **Why:** the old code "
            f"loaded them twice, which made startup slower by about {i * 10} milliseconds, and it ignored "
            f"changes you made while it was running. I also added a test in tests/test_module_{i}.py that "
            f"fails on the old code and passes now, and I checked the docs at https://docs.python.org/3/library/json.html "
            f"to make sure the encoding is right. Nothing else changed in this step."
        )
    return "\n\n".join(paras)


class RealTimeSink:
    """Stands in for the sound card: pulls 10 ms of audio every 10 ms of wall time."""

    def __init__(self, cb, finished):
        self.finished = finished
        self.stopped = False
        self.reader: tts.Reader | None = None
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        while self.reader is None:
            time.sleep(0.001)
        block, t = 240, time.monotonic()
        buf = np.zeros(block, np.float32)
        while not self.stopped:
            if not self.reader.fill(buf):
                self.finished()
                return
            t += block / tts.SR
            time.sleep(max(0.0, t - time.monotonic()))

    def abort(self):
        self.stopped = True

    def close(self):
        self.stopped = True


def run_read(reader: tts.Reader, text: str, label: str, max_s: float, out: list) -> None:
    sinks = []
    orig = reader._output

    def make(cb, fin):
        s = RealTimeSink(cb, fin)
        s.reader = reader
        sinks.append(s)
        return s

    reader._output = make
    t0 = time.monotonic()
    cleaned = clean_for_speech(text)
    t_clean = time.monotonic() - t0
    reader.speak(cleaned, t0=t0)
    end = time.monotonic() + max_s
    while reader.active and time.monotonic() < end:
        time.sleep(0.05)
    played = time.monotonic() - t0
    reader.stop()
    reader._output = orig
    st = dict(reader.stats)
    row = {"label": label, "words": len(text.split()), "clean_s": round(t_clean, 3),
           "first_audio_s": st.get("first_audio_s"), "first_synth_s": st.get("first_synth_s"),
           "gaps": st.get("underruns"), "gap_s": round(st.get("underrun_s", 0.0), 3),
           "listened_s": round(played, 1), "chunks": st.get("chunks"), "speed": reader.speed}
    out.append(row)
    print(json.dumps(row), flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--idle-min", type=float, default=0)
    ap.add_argument("--speed", type=float, default=1.3)
    ap.add_argument("--long-listen", type=float, default=900, help="max seconds to play the long reply")
    ap.add_argument("--out", default="")
    a = ap.parse_args()

    cache = Path(__file__).resolve().parents[1] / "data" / "tts-bench"
    voice = tts.Voice(cache)
    t = time.monotonic()
    voice.ensure_loaded()
    print(json.dumps({"model_load_s": round(time.monotonic() - t, 2)}), flush=True)
    reader = tts.Reader(voice, lambda: "af_heart", lambda: a.speed, output=RealTimeSink)
    rows: list = []
    for i in range(3):
        run_read(reader, SHORT, f"short warm {i + 1}", 60, rows)
    run_read(reader, long_reply(), "long warm (2000+ words, full listen)", a.long_listen, rows)
    if a.idle_min:
        print(json.dumps({"idling_min": a.idle_min}), flush=True)
        time.sleep(a.idle_min * 60)
        run_read(reader, SHORT, f"short after {a.idle_min:g} min idle", 60, rows)
        run_read(reader, long_reply(), f"long after {a.idle_min:g} min idle (first 60 s)", 60, rows)
    if a.out:
        Path(a.out).write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
