"""Speech in, cleaned text out, through the app's own speech-to-text and cleanup (no hotkeys, no paste,
no restart of a running Yappr). A Windows voice reads three dictations: a long one that ends in a
request, a "strike that" correction and a filler-heavy ramble.

  python tools/cleanup_eval/e2e_speech.py
"""
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).parent))

from run import make_cleaner  # noqa: E402
import yappr.cleanup as cleanup  # noqa: E402
from yappr.stt import Transcriber  # noqa: E402

SCRIPTS = [
    ("long dictation ending in a request",
     "Okay so I've been working on the onboarding flow for the app. Um the sign up page loads slowly on mobile, "
     "the welcome email sometimes doesn't send, and people get stuck when they connect their calendar. "
     "Uh I also want a progress bar, and my budget is about two weeks. "
     "So based on all of that, can you create a checklist and make a plan for how to tackle it?",
     ["create a checklist and make a plan", "two weeks", "progress bar"], [r"^\s*[-*\d]", r"\[ \]", r"^#"]),
    ("strike that correction",
     "Let's meet with the design team on Tuesday at ten. No, strike that, actually Wednesday at ten, "
     "and bring the new mockups.",
     ["Wednesday at (ten|10)", "mock-?ups"], ["Tuesday", "strike that"]),
    ("filler-heavy ramble",
     "So um, basically, I was like, you know, thinking we could uh maybe sort of redo the pricing page this week, "
     "you know what I mean? So yeah.",
     ["maybe redo the pricing page this week"], [r"\bum\b", r"\buh\b", "you know", "basically", "so yeah"]),
]


def speak(text: str, wav: Path) -> np.ndarray:
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "tools" / "tts.ps1"),
                    "-Text", text, "-Out", str(wav)], check=True)
    audio, sr = sf.read(str(wav), dtype="float32")
    assert sr == 16000
    return audio


def main() -> int:
    cleaner, s = make_cleaner(cleanup)
    stt = Transcriber(s.stt_model, s.stt_quantization, s.stt_threads, s.stt_idle_unload_min)
    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        for name, text, must, must_not in SCRIPTS:
            audio = speak(text, Path(tmp) / "d.wav")
            t0 = time.perf_counter()
            raw = stt.transcribe(audio)
            t1 = time.perf_counter()
            out, how = cleaner.clean(raw)
            t2 = time.perf_counter()
            fails = [f"missing /{p}/" for p in must if not re.search(p, out, re.I)]
            fails += [f"has /{p}/" for p in must_not if re.search(p, out, re.I | re.M)]
            ok &= not fails and how == "llm"
            print(f"=== {name}: {'PASS' if not fails else 'FAIL ' + '; '.join(fails)} "
                  f"(speech-to-text {t1 - t0:.2f}s, cleanup {t2 - t1:.2f}s, {how})")
            print("heard:  ", raw)
            print("pasted: ", out.replace("\n", "\n         "))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
