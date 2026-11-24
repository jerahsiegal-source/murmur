r"""Skip, full body, doing two little yaps: the opening animation.

    .venv\Scripts\python.exe video\skip.py      -> video/build/skip/sheet-*.png, video/build/yap.wav

His head is the app icon's drawing, path for path (branding/yappr-icon.svg). The body, legs and tail are
new, in the same flat shapes and only the icon's colours. Each frame is an SVG; headless Edge draws them
all in one go as a sprite sheet with a clear background. The yap sound is made in code.
"""
import math
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
BUILD = HERE / "build"
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
FPS, DUR, CELL, COLS = 30, 2.4, 800, 9
YAPS = (0.80, 1.12)          # when each yap starts (seconds)
YAP_LEN = 0.17
CREAM, BARK, FAWN = "#fbf8f3", "#5a3524", "#e8c39a"


def ease(x):
    x = min(1.0, max(0.0, x))
    return 1 - (1 - x) ** 3


def pulse(t, start, up=0.05, hold=0.07, down=0.09):
    """0 -> 1 -> 0: a quick open-and-shut."""
    x = t - start
    if x < 0 or x > up + hold + down:
        return 0.0
    if x < up:
        return ease(x / up)
    if x < up + hold:
        return 1.0
    return 1 - ease((x - up - hold) / down)


def frame_svg(t: float) -> str:
    yap = max(pulse(t, y) for y in YAPS)                       # mouth open, head up
    crouch = max(pulse(t, y - 0.12, 0.08, 0.02, 0.06) for y in YAPS)  # the little wind-up before each yap
    enter = ease(t / 0.45)
    hop = -2.6 * yap + 1.2 * crouch                            # whole dog: dips, then pops up
    squash = 1 + 0.05 * crouch - 0.03 * yap
    head_rot = -9 * yap + 3 * crouch
    jaw = -6.0 * (1 - yap)
    wag = 20 * math.sin(2 * math.pi * 5.5 * t) * (0.5 + 0.5 * yap + 0.3 * enter)
    ear = -14 * yap
    marks = ""
    for y in YAPS:
        k = (t - y) / 0.26
        if 0 <= k <= 1:
            o, s = 1 - k ** 2, 0.7 + 0.6 * ease(k)
            marks += (f'<g transform="translate(55 26) scale({s:.3f}) translate(-55 -26)" opacity="{o:.3f}" fill="none" '
                      f'stroke="{BARK}" stroke-width="2.8" stroke-linecap="round">'
                      '<path d="M54.5 21.5l4-5"/><path d="M57 27H61.5"/><path d="M55.5 33.5l4.2 3.2"/></g>')
    scale_in = 0.6 + 0.4 * enter
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="-38 -12 108 108" width="{CELL}" height="{CELL}">
<g opacity="{enter:.3f}" transform="translate(16 84) scale({scale_in:.3f}) translate(-16 -84)">
 <ellipse cx="6" cy="83.5" rx="{30 - 3 * yap:.2f}" ry="2.6" fill="{BARK}" opacity=".16"/>
 <g transform="translate(0 {hop:.2f}) translate(6 82) scale({2 - squash:.3f} {squash:.3f}) translate(-6 -82)">
  <g transform="rotate({wag:.2f} -19 52)"><path d="M-19 52C-23 46 -25 40 -24 33" fill="none" stroke="{CREAM}" stroke-width="5.4" stroke-linecap="round"/>
   <path d="M-24.4 37C-24.6 35.6 -24.4 34.2 -24 33" fill="none" stroke="{BARK}" stroke-width="5.4" stroke-linecap="round"/></g>
  <rect x="-13.5" y="62" width="6.6" height="20" rx="3.3" fill="{FAWN}"/>
  <rect x="21" y="62" width="6.6" height="20" rx="3.3" fill="{FAWN}"/>
  <clipPath id="b"><rect x="-24" y="45" width="60.5" height="26" rx="13"/></clipPath>
  <rect x="-24" y="45" width="60.5" height="26" rx="13" fill="{CREAM}"/>
  <ellipse cx="-9" cy="46" rx="15" ry="10.5" fill="{BARK}" clip-path="url(#b)"/>
  <rect x="-21" y="60" width="7" height="22" rx="3.5" fill="{CREAM}"/>
  <rect x="28" y="60" width="7" height="22" rx="3.5" fill="{CREAM}"/>
  <g transform="rotate({head_rot:.2f} 22 48)">
   <path d="M13 44C10 52 9 60 9 66H36L33 49Z" fill="{CREAM}"/>
   <path d="M13 44C11 50 10 55 10 60 15 58 18 53 19 47Z" fill="{BARK}"/>
   <circle cx="26" cy="36" r="15.5" fill="{CREAM}"/>
   <path d="M10.6 35C10 24.5 17.5 20 26 20.3 33 20.6 38 24.5 39.6 29.5 34 27.8 29 29.6 25.4 34.6 20 31.5 15 32.5 10.6 35Z" fill="{BARK}"/>
   <g transform="rotate({ear:.2f} 21 28)">
    <path d="M18.5 26.5C14.5 15.5 23.5 9 31.5 14.5 31 19.5 28.5 23 23.5 28.5 21.5 29.5 19.5 28.8 18.5 26.5Z" fill="{BARK}"/>
    <path d="M20.6 24.6C18.6 17.8 24 13.6 28.8 16 28 19.4 26 21.8 22.6 25.6Z" fill="#c98b6b"/></g>
   <ellipse cx="32" cy="32.6" rx="5.8" ry="4.8" fill="#d9a46c"/>
   <path d="M30 38.5C32.5 40.5 35 41 37.5 40.6" fill="none" stroke="{FAWN}" stroke-width="2.6" stroke-linecap="round"/>
   <g opacity="{min(1.0, yap * 3):.2f}"><path d="M36.5 39.4H49L46.6 42.6H36.5Z" fill="#4a1a1d"/>
    <path d="M40 41.2Q43 40.2 45.6 41.2L45 42.6H40.4Z" fill="#ef8a9a"/></g>
   <path d="M36.5 42.6H46.6A3.3 3.3 0 0 1 46.6 49.2H36.5Z" fill="{CREAM}" transform="translate(0 {jaw:.2f})"/>
   <path d="M36.5 29.8H50.6A4.8 4.8 0 0 1 50.6 39.4H36.5Z" fill="{CREAM}"/>
   <path d="M37 32.6C40 30.6 44 30.2 48 30.6" fill="none" stroke="{FAWN}" stroke-width="2" stroke-linecap="round"/>
   <circle cx="32.6" cy="32.4" r="3" fill="#2a1810"/><circle cx="33.6" cy="31.4" r="1" fill="#fff"/>
   <ellipse cx="54.8" cy="32.4" rx="3" ry="2.7" fill="#7a4a3c"/><circle cx="54" cy="31.6" r=".8" fill="#a8766a"/>
   {marks}
  </g>
 </g>
</g></svg>'''


N = int(DUR * FPS)


def build_sheet():
    out = BUILD / "skip"
    out.mkdir(parents=True, exist_ok=True)
    rows = -(-N // COLS)
    cells = "".join(f'<div style="position:absolute;left:{(i % COLS) * CELL}px;top:{(i // COLS) * CELL}px">{frame_svg(i / FPS)}</div>'
                    for i in range(N))
    html = out / "sheet.html"
    html.write_text(f'<!doctype html><meta charset="utf-8"><body style="margin:0;background:transparent">{cells}</body>',
                    encoding="utf-8")
    subprocess.run([EDGE, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1",
                    "--default-background-color=00000000", f"--window-size={COLS * CELL},{rows * CELL}",
                    f"--screenshot={out / 'sheet.png'}", html.as_uri()], check=True, capture_output=True, timeout=120)
    print(out / "sheet.png", f"{N} frames")


@lru_cache(None)
def _sheet():
    from PIL import Image

    return Image.open(BUILD / "skip" / "sheet.png").convert("RGBA")


def frame(t: float):
    """Skip at time t (a CELL x CELL image, clear background). Holds the last pose after the animation."""
    i = min(N - 1, max(0, int(t * FPS)))
    x, y = (i % COLS) * CELL, (i // COLS) * CELL
    return _sheet().crop((x, y, x + CELL, y + CELL))


def yap_sound(sr=48000):
    """Two small, bright terrier yaps."""
    out = np.zeros(int(DUR * sr), np.float32)
    rng = np.random.default_rng(3)
    for j, start in enumerate(YAPS):
        n = int(YAP_LEN * sr)
        t = np.arange(n) / sr
        k = t / YAP_LEN
        f0 = (620 + 520 * np.sin(np.pi * np.minimum(k * 1.6, 1.0)) - 260 * k) * (1.0 if j == 0 else 1.07)
        ph = 2 * np.pi * np.cumsum(f0) / sr
        x = np.zeros(n)
        for h in range(1, 14):
            fh = f0 * h
            # two vocal resonances give it a "yap" rather than a beep
            g = np.exp(-((fh - 1350) / 600) ** 2) + 0.7 * np.exp(-((fh - 2900) / 900) ** 2) + 0.12
            x += g * np.sin(h * ph + 0.3 * h) / h ** 0.35
        x += 0.25 * np.diff(rng.standard_normal(n), prepend=0) * np.exp(-t / 0.02)  # breathy start
        env = np.minimum(t / 0.008, 1.0) * np.exp(-t / 0.075) * np.minimum((YAP_LEN - t) / 0.02, 1.0)
        x = np.tanh(1.8 * x * env / np.max(np.abs(x)))
        i = int(start * sr)
        out[i:i + n] += (x * (0.9 if j == 0 else 1.0)).astype(np.float32)
    return out / np.max(np.abs(out)) * 0.6


if __name__ == "__main__":
    import soundfile as sf

    build_sheet()
    sf.write(BUILD / "yap.wav", yap_sound(), 48000)
    from PIL import Image

    strip = Image.new("RGBA", (CELL * 5, CELL), (255, 233, 168, 255))
    for n, t in enumerate((0.2, 0.6, 0.86, 1.0, 2.0)):
        strip.alpha_composite(frame(t), (n * CELL, 0))
    strip.convert("RGB").resize((CELL * 5 // 2, CELL // 2)).save(BUILD / "skip" / "poses.png")
