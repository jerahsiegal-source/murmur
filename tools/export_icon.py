"""Render branding/yappr-icon.svg into the app's icon files.

Uses headless Edge (or Chrome) to rasterize the SVG at 1024 px, then Pillow to make:
- yappr/assets/yappr.ico       (16, 20, 24, 32, 40, 48, 64, 128, 256: Start Menu, taskbar, tray, window)
- yappr/assets/yappr-64.png    (tray icon source)
- branding/yappr-1024.png      (README / GitHub)

    .venv\\Scripts\\python.exe tools\\export_icon.py
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SVG = ROOT / "branding" / "yappr-icon.svg"
ASSETS = ROOT / "yappr" / "assets"
BROWSERS = [
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
]
ICO_SIZES = [16, 20, 24, 32, 40, 48, 64, 128, 256]


def render(size: int = 1024) -> Image.Image:
    browser = next((b for b in BROWSERS if b.exists()), None)
    if browser is None:
        sys.exit("Edge or Chrome is needed to render the SVG.")
    svg = SVG.read_text(encoding="utf-8").replace('width="256" height="256"', f'width="{size}" height="{size}"')
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "icon.html"
        page.write_text(f'<html><body style="margin:0;background:transparent">{svg}</body></html>', encoding="utf-8")
        out = Path(tmp) / "icon.png"
        subprocess.run([str(browser), "--headless=new", "--disable-gpu", "--hide-scrollbars",
                        "--default-background-color=00000000", f"--window-size={size},{size}",
                        f"--screenshot={out}", page.as_uri()], check=True, capture_output=True, timeout=60)
        return Image.open(out).convert("RGBA").crop((0, 0, size, size))


def main() -> None:
    big = render()
    ASSETS.mkdir(parents=True, exist_ok=True)
    big.save(ROOT / "branding" / "yappr-1024.png")
    big.resize((64, 64), Image.LANCZOS).save(ASSETS / "yappr-64.png")
    big.resize((256, 256), Image.LANCZOS).save(ASSETS / "yappr.ico", sizes=[(s, s) for s in ICO_SIZES])
    print("wrote", ASSETS / "yappr.ico", ASSETS / "yappr-64.png", ROOT / "branding" / "yappr-1024.png")


if __name__ == "__main__":
    main()
