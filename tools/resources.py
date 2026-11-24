"""Measure Yappr's footprint: idle RAM/CPU, RAM/CPU while transcribing, impact on another app, disk.

Usage: python tools/resources.py   (the app must be running: python -m yappr)
"""
import os
import sys
import threading
import time
from pathlib import Path

import numpy as np
import psutil

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def yappr_procs():
    out = []
    for p in psutil.process_iter(["pid", "cmdline"]):
        cmd = " ".join(p.info["cmdline"] or [])
        if ("-m yappr" in cmd) and "resources.py" not in cmd:
            out.append(p)
    return out


def snapshot(procs, secs=10):
    def safe(fn, p):
        try:
            return fn(p)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return 0  # the app was restarted mid-measurement
    for p in procs:
        safe(lambda q: q.cpu_percent(None), p)
    time.sleep(secs)
    rss = sum(safe(lambda q: q.memory_info().rss, p) for p in procs) / 1e6
    priv = sum(safe(lambda q: q.memory_full_info().private, p) for p in procs) / 1e6
    cpu = sum(safe(lambda q: q.cpu_percent(None), p) for p in procs) / psutil.cpu_count()
    return rss, priv, cpu


BENCH = """
import time
ts = []
for _ in range(5):
    t = time.perf_counter(); x = 0
    for i in range(3_000_000):
        x += i * i % 7
    ts.append(time.perf_counter() - t)
print(sum(ts) / len(ts))
"""


def bench():
    """A CPU-bound task in a separate normal-priority process, standing in for 'another app'."""
    import subprocess

    return float(subprocess.run([sys.executable, "-c", BENCH], capture_output=True, text=True).stdout)


def dir_size(p: Path) -> float:
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) / 1e6 if p.exists() else 0.0


procs = yappr_procs()
print("processes:", [(p.pid, " ".join(p.cmdline())[-30:]) for p in procs])
rss, priv, cpu = snapshot(procs, 30)
print(f"IDLE (model unloaded): working set {rss:.0f} MB, private {priv:.0f} MB, CPU {cpu:.2f}% of machine over 30 s")

# transcription load inside this process, same engine/settings as the app
from yappr.stt import Transcriber, background_priority  # noqa: E402

base = bench()
tr = Transcriber("nemo-parakeet-tdt-0.6b-v2", "int8", int(os.environ.get("STT_THREADS", "4")), 0)
audio = np.concatenate([np.random.randn(16000 * 300).astype(np.float32) * 0.0] + [
    __import__("soundfile").read(str(Path(__file__).resolve().parents[1] / "data/test/meet90/sys.wav"), dtype="float32",
                                 frames=16000 * 300)[0]])
tr.ensure_loaded()
me = psutil.Process()
loaded = me.memory_info().rss / 1e6
done = threading.Event()
cpu_samples = []


def load():
    t = time.perf_counter()
    with background_priority():  # exactly what MeetingSession does per chunk
        tr.transcribe_segments(audio)
    print(f"transcribed a 5-min meeting chunk in {time.perf_counter() - t:.1f} s")
    done.set()


me.cpu_percent(None)
threading.Thread(target=load, daemon=True).start()
under = bench()
while not done.wait(0.5):
    cpu_samples.append(me.cpu_percent(None) / psutil.cpu_count())
print(f"WHILE TRANSCRIBING: engine RSS {me.memory_info().rss / 1e6:.0f} MB (after load {loaded:.0f} MB), "
      f"CPU {np.mean(cpu_samples):.0f}% of machine (peak {max(cpu_samples):.0f}%)")
print(f"other-app benchmark: {base:.3f}s idle vs {under:.3f}s during transcription ({(under / base - 1) * 100:+.0f}%)")

venv = Path(sys.prefix)
hf = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface")) / "hub"
models = sum(dir_size(d) for d in hf.glob("models--*parakeet*")) + sum(dir_size(d) for d in hf.glob("models--*silero*"))
print(f"DISK: Python env {dir_size(venv):.0f} MB, speech models {models:.0f} MB, app code {dir_size(Path(__file__).resolve().parents[1] / 'yappr'):.1f} MB")
