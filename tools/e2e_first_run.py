"""First run, end to end, in the real app on a brand-new throwaway profile:
welcome opens -> first dictation lands in the practice box -> AI helper added (a local fake AI service, so
nothing is paid or sent out) -> welcome finished -> Today. Then a second dictation is tidied by the AI helper.

    python tools/e2e_first_run.py <out dir> <fake mic wav> [--full <recorded call dir>]

With --full it goes on (D5): a dictation pasted into another app (tools/e2e_dictation.py), a meeting taken
from the Today page with a recorded call played in at 10x (YAPPR_FAKE_MEETING), its notes opened in Notes,
and read-aloud in Notepad (tools/e2e_read.py: this one plays through the speakers for a few seconds).

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


def run_full(out: Path, prof: Path, wav: str):
    import soundfile as sf

    env = dict(os.environ, YAPPR_TEST_CHORD="ctrl+shift")
    secs = sf.info(wav).duration
    r = subprocess.run([sys.executable, str(HERE / "e2e_dictation.py"), f"{secs + 0.5:.1f}"], env=env,
                       capture_output=True, text=True, encoding="utf-8", timeout=120)
    print("dictation into another app:", " | ".join(l for l in r.stdout.splitlines() if l.startswith(("RESULT", "TEXT"))))

    ew.js("go('today')")
    wait(lambda: ew.js("!!document.querySelector('#mt')"), what="today button")
    t0 = time.time()
    ew.js("document.querySelector('#mt').click()")
    log = prof / "data" / "yappr.log"
    meetings = prof / "Meetings"
    d = wait(lambda: next(iter([x for x in meetings.iterdir() if x.is_dir()]), None) if meetings.exists() else None, what="meeting folder")
    time.sleep(3)
    sys.argv = ["grab", str(out / "first-run-7-bar-taking-notes.png"), "bar"]
    grab.hwnds.clear(); grab.main()
    secs_call = max(sf.info(str(Path(os.environ["YAPPR_FAKE_MEETING"]) / f"{k}.wav")).duration for k in ("mic", "sys"))
    time.sleep(secs_call / 10 + 2)
    ew.js("go('today')")
    wait(lambda: ew.js("(document.querySelector('#mt')||{}).textContent||''").startswith("■"), what="stop button")
    shot(out, "8-today-during-meeting")
    ew.js("document.querySelector('#mt').click()")
    wait(lambda: (d / "summary.md").exists(), timeout=300, what="summary")
    print(f"meeting: {secs_call:.0f} s call played at 10x -> notes written {time.time() - t0:.0f}s after starting; "
          f"transcript lines: {sum(1 for l in (d / 'transcript.md').read_text(encoding='utf-8').splitlines() if l.startswith('['))}")
    time.sleep(1)
    ew.js("go('notes', {mode: 'meetings', id: null})")
    wait(lambda: ew.js("!!document.querySelector('#reader article')"), what="notes reader")
    time.sleep(0.5)
    print("notes page shows:", ew.js("document.querySelector('#reader article').innerText.slice(0, 200)"))
    shot(out, "9-notes")

    page = Path(tempfile.mkdtemp()) / "read-test.txt"
    page.write_text("Yappr can read this sentence out loud. Highlight any text and press Control Alt X.", encoding="utf-8")
    note = subprocess.Popen(["notepad.exe", str(page)])
    time.sleep(2.5)
    r = subprocess.run([sys.executable, str(HERE / "e2e_read.py"), "--window", "read-test", "--runs", "1", "--listen", "6"],
                       capture_output=True, text=True, encoding="utf-8", timeout=180)
    print("read aloud:", r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr[-300:])
    subprocess.run(["taskkill", "/PID", str(note.pid), "/F"], capture_output=True)


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
    full = sys.argv[sys.argv.index("--full") + 1] if "--full" in sys.argv else ""
    if full:
        os.environ["YAPPR_FAKE_MEETING"] = full
        os.environ["YAPPR_FAKE_MEETING_SPEED"] = "10"
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
        if full:
            run_full(out, prof, wav)
    finally:
        fake.terminate()


if __name__ == "__main__":
    main()
