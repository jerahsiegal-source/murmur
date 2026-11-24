r"""Make the narration and the demo speaker's audio with Kokoro (the voice Yappr ships).

    .venv\Scripts\python.exe video\voice.py
Writes video/build/vo/<scene>.wav (24 kHz) and video/build/mic.wav (16 kHz, for YAPPR_FAKE_MIC).
"""
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).parent))
import script  # noqa: E402
from yappr.tts import SR, Voice  # noqa: E402

BUILD = Path(__file__).parent / "build"


def trim(x, thr=0.004, pad=int(0.06 * SR)):
    idx = np.where(np.abs(x) > thr)[0]
    return x if not len(idx) else x[max(0, idx[0] - pad): idx[-1] + pad]


def main():
    (BUILD / "vo").mkdir(parents=True, exist_ok=True)
    v = Voice(BUILD / "kokoro")
    for sid, line, _ in script.SCENES:
        x = trim(np.asarray(v.synth(line, script.NARRATOR, script.SPEED), dtype=np.float32))
        sf.write(BUILD / "vo" / f"{sid}.wav", x, SR)
        print(f"{sid:10s} {len(x) / SR:5.2f}s  {line}")
    for name, line in (("1", script.DICTATION), ("2", script.DICTATION_2)):
        x = trim(np.asarray(v.synth(line, script.SPEAKER, 1.0), dtype=np.float32))
        sf.write(BUILD / "vo" / f"speaker{name}.wav", x, SR)
        n = int(len(x) * 16000 / SR)  # 16 kHz copy for the app's microphone hook, with a little lead-in and tail
        y = np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.float32)
        y = np.concatenate([np.zeros(int(0.35 * 16000), np.float32), y, np.zeros(int(0.5 * 16000), np.float32)])
        sf.write(BUILD / f"mic{name}.wav", y, 16000)
        print(f"speaker{name}   {len(x) / SR:5.2f}s  mic{name}.wav {len(y) / 16000:5.2f}s")

if __name__ == "__main__":
    main()
