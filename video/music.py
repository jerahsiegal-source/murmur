r"""Background music for the Yappr video, composed in code (no samples, no third-party licence).

    .venv\Scripts\python.exe video\music.py [seconds]
Writes video/build/music.wav (48 kHz stereo). Warm, light and unhurried: a soft pad, a plucked
pattern, a round bass and a quiet beat, ending on a held chord.
"""
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

SR = 48000
BPM = 96
BEAT = 60 / BPM
BAR = 4 * BEAT
BUILD = Path(__file__).parent / "build"


def hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


# F major: Fmaj7 | Am7 | Dm7 | Bbmaj7(add9)   (midi notes; bass root first)
CHORDS = [
    (41, [60, 64, 65, 69, 72]),
    (45, [60, 64, 67, 69, 72]),
    (38, [60, 62, 65, 69, 72]),
    (46, [58, 62, 65, 69, 72]),
]
ARP = [0, 2, 4, 3, 1, 3, 4, 2]  # which chord tone each eighth note plays


def env(n, a, d, sustain=0.0, r=0.0):
    t = np.arange(n) / SR
    e = np.minimum(t / max(a, 1e-4), 1.0) * (sustain + (1 - sustain) * np.exp(-t / d))
    if r:
        k = int(r * SR)
        e[-k:] *= np.linspace(1, 0, k)
    return e


def pluck(f, dur, bright=0.35):
    n = int(dur * SR)
    t = np.arange(n) / SR
    x = np.sin(2 * np.pi * f * t) + bright * np.sin(2 * np.pi * 2 * f * t) * np.exp(-t / 0.12) \
        + 0.15 * np.sin(2 * np.pi * 4 * f * t) * np.exp(-t / 0.05)
    return x * env(n, 0.004, 0.32, r=0.02)


def pad(f, dur):
    n = int(dur * SR)
    t = np.arange(n) / SR
    x = sum(np.sin(2 * np.pi * f * (1 + d) * t + p) for d, p in ((-0.003, 0), (0.0, 1.3), (0.003, 2.1)))
    x += 0.25 * np.sin(2 * np.pi * 2 * f * t)
    a = np.minimum(t / 0.9, 1.0) * np.minimum((dur - t) / 0.9, 1.0)
    return x * np.clip(a, 0, 1) / 3


def bass(f, dur):
    n = int(dur * SR)
    t = np.arange(n) / SR
    x = np.sin(2 * np.pi * f * t) + 0.3 * np.sin(2 * np.pi * 2 * f * t) * np.exp(-t / 0.2)
    return x * env(n, 0.01, 0.9, sustain=0.35, r=0.05)


def kick():
    n = int(0.28 * SR)
    t = np.arange(n) / SR
    return np.sin(2 * np.pi * (48 * t + 60 * 0.03 * (1 - np.exp(-t / 0.03)))) * np.exp(-t / 0.09)


def shaker(rng):
    n = int(0.06 * SR)
    x = rng.standard_normal(n)
    x = np.diff(x, prepend=0)  # crude high-pass
    return x * np.exp(-np.arange(n) / SR / 0.012)


def add(buf, x, at, gain=1.0, pan=0.0):
    i = int(at * SR)
    if i >= len(buf):
        return
    x = x[: len(buf) - i]
    buf[i:i + len(x), 0] += x * gain * (1 - max(0, pan))
    buf[i:i + len(x), 1] += x * gain * (1 + min(0, pan))


def make(total: float) -> np.ndarray:
    rng = np.random.default_rng(7)
    out = np.zeros((int((total + 3) * SR), 2))
    end = total - 3.2                         # last downbeat-ish: hold a chord and let it ring
    bars = int(end // BAR)
    for b in range(bars + 1):
        t0 = b * BAR
        root, tones = CHORDS[(b // 2) % 4]
        last = b == bars
        dur = (total - t0 + 1.5) if last else BAR
        full = b >= 2 and not last            # the beat and bass join after the intro
        for m in (tones[0] - 12, tones[1] - 12, tones[2], tones[3]):
            add(out, pad(hz(m), dur + 0.6), t0, 0.050, pan=rng.uniform(-0.3, 0.3))
        if last:
            for k, m in enumerate(tones):     # final rolled chord
                add(out, pluck(hz(m), 3.0), t0 + 0.07 * k, 0.16, pan=(k - 2) * 0.2)
            add(out, bass(hz(root), 3.0), t0, 0.22)
            break
        for e in range(8):
            m = tones[ARP[e]] + (12 if e in (3, 6) and full else 0)
            g = 0.13 if e % 2 == 0 else 0.09
            add(out, pluck(hz(m), 0.9), t0 + e * BEAT / 2, g if b >= 1 else g * 0.7, pan=0.35 if e % 2 else -0.35)
        if full:
            add(out, bass(hz(root), BEAT * 1.8), t0, 0.24)
            add(out, bass(hz(root), BEAT * 1.2), t0 + 2.5 * BEAT, 0.17)
            for q in (0, 2):
                add(out, kick(), t0 + q * BEAT, 0.30)
            for e in range(8):
                add(out, shaker(rng), t0 + e * BEAT / 2, 0.035 if e % 2 else 0.018, pan=0.2)
    # a touch of space: two soft echoes
    for d, g in ((0.375 * BEAT * 2, 0.18), (0.75 * BEAT * 2, 0.09)):
        k = int(d * SR)
        out[k:] += out[:-k][:, ::-1] * g
    out = out[: int(total * SR)]
    fade = int(0.4 * SR)
    out[:fade] *= np.linspace(0, 1, fade)[:, None]
    tail = int(1.8 * SR)
    out[-tail:] *= (np.linspace(1, 0, tail) ** 1.5)[:, None]
    out = np.tanh(out * 1.6) / 1.6            # gentle limiting
    return (out / np.max(np.abs(out)) * 0.8).astype(np.float32)


if __name__ == "__main__":
    total = float(sys.argv[1]) if len(sys.argv) > 1 else 48.0
    BUILD.mkdir(exist_ok=True)
    x = make(total)
    sf.write(BUILD / "music.wav", x, SR)
    print(f"music.wav {len(x) / SR:.1f}s peak {np.max(np.abs(x)):.2f} rms {np.sqrt(np.mean(x * x)):.3f}")
