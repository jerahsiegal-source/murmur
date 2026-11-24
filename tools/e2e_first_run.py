"""First run, end to end, in the real app on a brand-new throwaway profile:
welcome opens -> first dictation lands in the practice box -> AI helper added (a local fake AI service, so
nothing is paid or sent out) -> welcome finished -> Today. Then a second dictation is tidied by the AI helper.

    python tools/e2e_first_run.py <out dir> <fake mic wav>

Uses the Ctrl+Shift test chord (never Ctrl+Win, which other dictation apps listen to). Stops any running
Yappr first. Screenshots of each step go to <out dir>/first-run-*.png; timings are printed.
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import e2e_window as ew  # noqa: E402
import grab  # noqa: E402


def wait(cond, timeout=30, every=0.3, what=""):
    end = time.time() + timeout
    while time.time() < end:
        v = cond()
        if v:
            return v
        time.sleep(every)
    raise TimeoutError(what)


def shot(out: Path, name: str):
    grab.hwnds.clear()
    sys.argv = ["grab", str(out / f"first-run-{name}.png"), "window"]
    grab.main()


def main():
    out, wav = Path(sys.argv[1]), sys.argv[2]
    out.mkdir(parents=True, exist_ok=True)
    prof = Path(tempfile.mkdtemp(prefix="yappr-fresh-"))
    (prof / "data").mkdir()
    (prof / "data" / "settings.json").write_text(json.dumps({"meetings_dir": str(prof / "Meetings")}), encoding="utf-8")
    shutil.rmtree(ew.DRIVE, ignore_errors=True)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    fake = subprocess.Popen([sys.executable, str(HERE / "fake_llm.py"), str(port), str(prof / "fake_llm.jsonl")])
    log = prof / "data" / "yappr.log"
    try:
        t0 = time.time()
        subprocess.run([sys.executable, str(HERE / "run_fresh.py"), str(prof / "data"), wav], check=True)
        wait(lambda: log.exists() and "window opened (welcome)" in log.read_text(encoding="utf-8"), what="welcome")
        wait(lambda: ew.js("!!document.querySelector('#try')"), what="practice box")
        t_welcome = time.time() - t0
        print(f"launch -> welcome on screen: {t_welcome:.1f}s")
        shot(out, "1-welcome")

        t1 = time.time()
        ew.dictate(6)
        got = wait(lambda: ew.js("document.querySelector('#got').textContent"), what="dictation seen")
        typed = ew.js("document.querySelector('#try').value")
        print(f"first dictation: {time.time() - t1:.1f}s (6 s of talking) -> box has: {typed!r}; page says: {got!r}")
        shot(out, "2-dictated")

        ew.js("document.querySelector('#next1').click()")
        wait(lambda: ew.js("!!document.querySelector('#wprov')"), what="step 2")
        shot(out, "3-ai-step")
        t2 = time.time()
        ew.js("const s=document.querySelector('#wprov'); s.value='openai'; s.dispatchEvent(new Event('change'))")
        wait(lambda: ew.js("!!document.querySelector('#wurl')"), what="service address field")
        ew.js(f"document.querySelector('#wurl').value='http://127.0.0.1:{port}/v1';"
              "document.querySelector('#wkey').value='test-key-not-real'; document.querySelector('#next2').click()")
        ok = wait(lambda: (lambda m: m if ("✓" in m or "!" in m) else "")(
            ew.js("(document.querySelector('#wkeyrow .msg')||{textContent:''}).textContent")), what="check")
        shot(out, "4-ai-checked")
        wait(lambda: ew.js("!!document.querySelector('#done')"), what="step 3")
        print(f"AI helper step: {time.time() - t2:.1f}s -> {ok!r}")
        shot(out, "5-meetings-step")
        ew.js("document.querySelector('#done').click()")
        wait(lambda: ew.js("document.querySelector('#welcome').hidden && !!document.querySelector('.stats')"), what="today")
        time.sleep(0.5)
        shot(out, "6-today")
        print(f"whole welcome, launch -> Today: {time.time() - t0:.1f}s (scripted; a person also reads each step)")

        ew.dictate(6)
        hist = prof / "data" / "history.jsonl"
        wait(lambda: hist.exists() and len(hist.read_text(encoding="utf-8").splitlines()) >= 2, what="second dictation")
        last = json.loads(hist.read_text(encoding="utf-8").splitlines()[-1])
        print(f"second dictation tidied by: {last['method']} -> {last['text']!r}")
        print("onboarded marker:", (prof / "data" / ".onboarded").exists())
        print("profile:", prof)
    finally:
        fake.terminate()


if __name__ == "__main__":
    main()
