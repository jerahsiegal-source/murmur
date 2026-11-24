"""Restart Yappr from a checkout and report: launch -> 'Yappr started', and idle memory after N seconds.

    python tools/measure_quick.py <checkout dir> [seconds] [--fake-mic WAV]

Like measure_startup.py, but samples memory only once at the end (scanning every process's command line
each second was slow enough to stall on this machine). Uses YAPPR_TEST_CHORD=ctrl+shift with --fake-mic.
"""
import os
import subprocess
import sys
import time
from pathlib import Path

import psutil

VENV_PYW = str(Path(sys.executable).with_name("pythonw.exe"))
LOG = Path(os.environ["LOCALAPPDATA"]) / "Yappr" / "yappr.log"


def yappr_procs(module="yappr"):
    out = []
    for p in psutil.process_iter(["name", "cmdline"]):
        try:
            cl = p.info["cmdline"] or []
        except Exception:
            continue
        if any(cl[i:i + 2] == ["-m", module] for i in range(len(cl) - 1)):
            out.append(p)
    return out


def main():
    checkout = sys.argv[1]
    secs = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else 20
    env = dict(os.environ)
    if "--fake-mic" in sys.argv:
        env["YAPPR_FAKE_MIC"] = sys.argv[sys.argv.index("--fake-mic") + 1]
        env["YAPPR_TEST_CHORD"] = "ctrl+shift"
    for p in yappr_procs() + yappr_procs("yappr.hotkey_host") + yappr_procs("yappr.window"):
        p.kill()
    time.sleep(1.0)
    size = LOG.stat().st_size if LOG.exists() else 0
    t0 = time.time()
    subprocess.Popen([VENV_PYW, "-m", "yappr"], cwd=checkout, env=env, stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP)
    started = None
    while time.time() - t0 < secs:
        time.sleep(0.05)
        if started is None and "Yappr started" in LOG.read_bytes()[size:].decode("utf-8", "replace"):
            started = time.time() - t0
    procs = [p for p in yappr_procs() if "Scripts" not in " ".join(p.cmdline())]
    rss = sum(p.memory_info().rss for p in procs) / 2**20
    priv = sum(p.memory_info().private for p in procs) / 2**20
    print(f"launch -> 'Yappr started': {started:.2f}s" if started else "no 'Yappr started' line")
    print(f"after {secs}s: Yappr working set {rss:.0f} MB, private {priv:.0f} MB")


if __name__ == "__main__":
    main()
