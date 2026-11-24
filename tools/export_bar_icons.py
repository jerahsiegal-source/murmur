r"""Render Skip for the floating bar: a round badge in two poses (resting, and ears up while listening).

    .venv\Scripts\python.exe tools\export_bar_icons.py

Writes yappr/assets/skip-bar.png and skip-bar-listen.png (128 px; the bar scales them to the screen).
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

import export_icon

ROOT = Path(__file__).resolve().parents[1]
SIZE = 128


def badge(svg: Path) -> Image.Image:
    export_icon.SVG = svg
    big = export_icon.render(512)
    mask = Image.new("L", big.size, 0)
    ImageDraw.Draw(mask).ellipse((0, 0, *big.size), fill=255)
    big.putalpha(mask)
    return big.resize((SIZE, SIZE), Image.LANCZOS)


def main() -> None:
    out = ROOT / "yappr" / "assets"
    badge(ROOT / "branding" / "yappr-icon.svg").save(out / "skip-bar.png")
    badge(ROOT / "branding" / "skip-listening.svg").save(out / "skip-bar-listen.png")
    print("wrote", out / "skip-bar.png", out / "skip-bar-listen.png")


if __name__ == "__main__":
    main()
