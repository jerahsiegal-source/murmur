"""Restart Yappr from a given checkout and measure startup time and memory over time.

    python tools/measure_startup.py <checkout dir> [seconds] [--fake-mic WAV]

Prints: launch -> "Yappr started" log line, and resident memory of the Yappr process
(the interpreter running `-m yappr`, not the venv launcher or the hotkey helper) every second.
"""
import os
import subprocess
import sys
import time
from pathlib import Path

import psutil

VENV_PYW = str(Path(sys.executable).with_name("pythonw.exe"))  # run this script with the venv's python
LOG = Path(os.environ["LOCALAPPDATA"]) / "Yappr" / "yappr.log"


def yappr_procs():
    out = []
    for p in psutil.process_iter(["pid", "name", "cmdline"]):
        cl = p.info["cmdline"] or []
        if p.info["name"] and "python" in p.info["name"].lower() and cl[-2:] == ["-m", "yappr"]:
            out.append(p)
    return out


def main():
    checkout = sys.argv[1]
    secs = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else 12
    env = dict(os.environ)
    if "--fake-mic" in sys.argv:
        env["YAPPR_FAKE_MIC"] = sys.argv[sys.argv.index("--fake-mic") + 1]
        env["YAPPR_TEST_CHORD"] = "ctrl+shift"
    for p in yappr_procs():
        p.kill()
    for p in psutil.process_iter(["cmdline"]):
        if (p.info["cmdline"] or [])[-2:] == ["-m", "yappr.hotkey_host"]:
            p.kill()
    time.sleep(1.0)
    size = LOG.stat().st_size
    t0 = time.time()
    subprocess.Popen([VENV_PYW, "-m", "yappr"], cwd=checkout, env=env, stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP)
    started = None
    for i in range(secs * 10):
        time.sleep(0.1)
        new = LOG.read_bytes()[size:].decode("utf-8", "replace")
        if started is None and "Yappr started" in new:
            started = time.time() - t0
        if i % 10 == 9:
            procs = [p for p in yappr_procs() if "Scripts" not in " ".join(p.cmdline())]
            rss = max((p.memory_info().rss for p in procs), default=0) / 2**20
            print(f"{(i + 1) / 10:4.0f}s  Yappr RSS {rss:6.0f} MB", flush=True)
    print(f"launch -> 'Yappr started': {started:.2f}s" if started else "no 'Yappr started' line")
    tail = LOG.read_bytes()[size:].decode("utf-8", "replace")
    for line in tail.splitlines():
        if "voice model loaded" in line or "Yappr started" in line:
            print(line)


if __name__ == "__main__":
    main()
