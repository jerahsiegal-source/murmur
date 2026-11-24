"""Drawing for the Yappr video: brand colours, type, title cards. Frames are Pillow images, 1920x1080."""
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H, FPS = 1920, 1080, 30
ROOT = Path(__file__).resolve().parents[1]
# DESIGN.md
BUTTER, BARK, INK, CREAM = (255, 233, 168), (90, 53, 36), (42, 24, 16), (251, 248, 243)
TAN, FAWN, ROSE, MUTED = (217, 164, 108), (232, 195, 154), (239, 138, 154), (187, 168, 151)
FONT = "C:/Windows/Fonts/SegUIVar.ttf"  # Segoe UI Variable, the app's typeface


@lru_cache(None)
def font(size: int, weight: int = 600):
    f = ImageFont.truetype(FONT, size)
    f.set_variation_by_axes([weight, 36 if size >= 36 else max(5, size)])
    return f


@lru_cache(None)
def logo(size: int) -> Image.Image:
    return Image.open(ROOT / "branding" / "yappr-1024.png").convert("RGBA").resize((size, size), Image.LANCZOS)


def ease(x: float) -> float:  # ease-out cubic, clamped
    x = min(1.0, max(0.0, x))
    return 1 - (1 - x) ** 3


def ramp(t: float, start: float, dur: float) -> float:
    return ease((t - start) / dur)


def mix(a, b, k):
    return tuple(round(x + (y - x) * k) for x, y in zip(a, b))


def text(img, xy, s, f, fill, alpha=1.0, anchor="mm", dy=0):
    """Draw text with opacity (fades towards whatever is under it)."""
    if alpha <= 0:
        return
    if alpha >= 1:
        ImageDraw.Draw(img).text((xy[0], xy[1] + dy), s, font=f, fill=fill, anchor=anchor)
        return
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).text((xy[0], xy[1] + dy), s, font=f, fill=fill + (round(255 * alpha),), anchor=anchor)
    img.alpha_composite(layer)


def paste_logo(img, cx, cy, size, alpha=1.0, shadow=True):
    lg = logo(size)
    if shadow:
        sh = Image.new("RGBA", (size + 120, size + 120), (0, 0, 0, 0))
        ImageDraw.Draw(sh).rounded_rectangle((60, 76, 60 + size, 76 + size), radius=size * 15 // 64,
                                             fill=INK + (round(60 * alpha),))
        img.alpha_composite(sh.filter(ImageFilter.GaussianBlur(26)), (cx - size // 2 - 60, cy - size // 2 - 60))
    if alpha < 1:
        lg = lg.copy()
        lg.putalpha(lg.getchannel("A").point(lambda a: round(a * alpha)))
    img.alpha_composite(lg, (cx - size // 2, cy - size // 2))


def intro(t: float) -> Image.Image:
    """Skip pops in, then the name."""
    img = Image.new("RGBA", (W, H), CREAM + (255,))
    k = ramp(t, 0.05, 0.55)
    size = round(300 * (0.8 + 0.2 * k)) // 2 * 2
    paste_logo(img, W // 2, 430, size, alpha=k)
    a = ramp(t, 0.45, 0.5)
    text(img, (W // 2, 690), "Yappr", font(150, 700), INK, a, dy=round(24 * (1 - a)))
    b = ramp(t, 0.9, 0.5)
    text(img, (W // 2, 810), "Talk. It types. It reads back.", font(46, 500), BARK, b, dy=round(16 * (1 - b)))
    return img


def pitch(t: float) -> Image.Image:
    """The one-line pitch, on the bar's dark ink."""
    img = Image.new("RGBA", (W, H), INK + (255,))
    paste_logo(img, W // 2, 250, 150, shadow=False, alpha=ramp(t, 0.0, 0.4))
    a = ramp(t, 0.15, 0.5)
    text(img, (W // 2, 420), "An open source", font(64, 500), CREAM, a, dy=round(18 * (1 - a)))
    f = font(124, 700)
    parts = [("Wispr Flow", BUTTER, 0.75), ("  +  ", MUTED, 1.55), ("Speechify", BUTTER, 1.85)]
    total = sum(f.getlength(s) for s, _, _ in parts)
    x = (W - total) / 2
    for s, col, at in parts:
        k = ramp(t, at, 0.45)
        text(img, (x, 570), s, f, col, k, anchor="lm", dy=round(22 * (1 - k)))
        x += f.getlength(s)
    c = ramp(t, 2.75, 0.5)
    text(img, (W // 2, 720), "in one app", font(64, 500), CREAM, c, dy=round(18 * (1 - c)))
    return img


def crossfade(a: Image.Image, b: Image.Image, k: float) -> Image.Image:
    return a if k <= 0 else b if k >= 1 else Image.blend(a, b, k)
