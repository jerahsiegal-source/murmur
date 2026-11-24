r"""Assemble the Yappr product video from the recorded take, the title cards, narration and music.

    .venv\Scripts\python.exe video\compose.py [take folder]     ->  video/out/yappr-demo.mp4

All times below marked "src" are seconds into the screen recording; "out" are seconds into the video.
"""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import soundfile as sf
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import gfx  # noqa: E402
import music  # noqa: E402
import script  # noqa: E402
import skip  # noqa: E402
from gfx import BARK, BUTTER, CREAM, FPS, H, INK, W, ease, font, ramp, text  # noqa: E402

BUILD, OUT = HERE / "build", HERE / "out"
TAKE = Path(sys.argv[1]) if len(sys.argv) > 1 else BUILD / "take3-good"
BG = (243, 230, 201)  # the recording backdrop, so the footage can float on a canvas of the same colour
SR = 48000

ev = json.loads((TAKE / "events.json").read_text(encoding="utf-8"))
SYNC = json.loads((TAKE / "sync.json").read_text())["sync_frame"] / 30
E = {e["name"]: e["t"] - ev["sync"] + SYNC for e in ev["events"]}  # event name -> src seconds
SPK0 = ev["speakers_start"] - ev["sync"] + SYNC
VO = {p.stem: sf.info(str(p)).duration for p in (BUILD / "vo").glob("*.wav")}

# ---------------------------------------------------------------- timeline
FIT = (0.86, 960, 534, 960, 600)  # scale, footage point (x, y) shown at canvas point (x, y)


def lerp_cam(a, b, k):
    return tuple(x + (y - x) * k for x, y in zip(a, b))


def cam_push(to, start, dur=1.6, frm=FIT):
    return lambda t: lerp_cam(frm, to, ease((t - start) / dur) if t > start else 0.0)


INTRO, PITCH = 3.3, 4.7
segs = []  # dict(kind, out, dur, ...)


def add(**k):
    k["out"] = segs[-1]["out"] + segs[-1]["dur"] if segs else 0.0
    segs.append(k)
    return k


add(kind="card", dur=INTRO, draw="intro")
add(kind="card", dur=PITCH, draw="pitch")
c = add(kind="shot", name="mail", src=E["d1_down"] - 1.9, dur=(E["d1_pasted"] + 1.9) - (E["d1_down"] - 1.9), speed=1.0,
        cam=cam_push((1.2, 960, 690, 960, 690), 1.3))
d = add(kind="shot", name="chat", src=E["d2_down"] - 1.9, dur=(E["d2_pasted"] + 1.6) - (E["d2_down"] - 1.9), speed=1.0,
        cam=cam_push((1.25, 960, 700, 960, 690), 0.9))
READ_CAM = (1.18, 960, 400, 960, 600)
# Edge pops a small toolbar over fresh selections for about a second; cut from just before the
# triple-click to just after it has gone, so nothing covers the highlighted words.
r1 = add(kind="shot", name="read-select", src=E["read_selected"] - 1.75, dur=1.7, speed=1.0, cam=cam_push(READ_CAM, 0.2, 1.3))
r = add(kind="shot", name="read", src=E["read_key"] - 0.12, dur=(E["read_done"] + 0.5) - (E["read_key"] - 0.12),
        speed=1.0, cam=lambda t: READ_CAM)
b = add(kind="shot", name="bar", src=E["bar_click"] - 1.05, dur=0.88, speed=1.0,
        cam=cam_push((1.8, 960, 960, 960, 620), 0.0, 0.7, frm=(1.3, 960, 880, 960, 620)))
KSPEED = 1.35
k0 = E["settings_click"] - 0.45
k = add(kind="shot", name="key", src=k0, dur=(E["end"] - 0.05 - k0) / KSPEED, speed=KSPEED,
        cam=cam_push((1.3, 1000, 640, 960, 600), (E["settings_click"] + 0.9 - k0) / KSPEED, 1.4,
                     frm=(0.95, 960, 470, 960, 630)))
o = add(kind="card", dur=6.0, draw="outro")
TOTAL = o["out"] + o["dur"]


def at(seg, src_t):
    """Output time of a moment in the recording, inside a shot."""
    return seg["out"] + (src_t - seg["src"]) / seg["speed"]


MIC_LEAD = 0.40  # the demo speech starts this long after the hotkey goes down
say1, say2 = at(c, E["d1_down"] + MIC_LEAD), at(d, E["d2_down"] + MIC_LEAD)
read0 = at(r, SPK0)
spk_len = sf.info(str(TAKE / "speakers.wav")).duration

# narration: (file, out time)
NARR = [
    ("intro", 1.75),
    ("pitch", segs[1]["out"] + 0.3),
    ("dictate_a", c["out"] + 0.2),
    ("dictate_b", at(c, E["d1_pasted"]) + 0.15),
    ("read", read0 - VO["read"] - 0.2),
    ("key", b["out"] + 0.25),
    ("outro", o["out"] + 0.5),
]

# captions: (out start, out end, headline, second line or None, extra)
up1, up2 = at(c, E["d1_up"]), at(d, E["d2_up"])
saved = at(k, E["key_saved"]) + 0.25
CAPS = [
    (c["out"] + 0.15, up1, "Hold Ctrl+Win and talk", ("say", script.DICTATION, say1, VO["speaker1"])),
    (up1, c["out"] + c["dur"], "Let go. It's typed where your cursor is.", ("line", "The “um” is gone: Yappr tidied it up.")),
    (d["out"] + 0.15, up2, "It works in any app", ("say", script.DICTATION_2, say2, VO["speaker2"])),
    (up2, d["out"] + d["dur"], "Tidied up as it types", ("line", "No “uh”, no repeated word.")),
    (r1["out"] + 0.15, read0 - 0.1, "Highlight anything. Press Ctrl+Alt+X.", None),
    (read0 - 0.1, r["out"] + r["dur"], "Yappr reads it to you", ("bars", "A natural voice, running on your own computer.")),
    (b["out"] + 0.1, saved, "Bring your own AI key. Paste it in once.", ("line", "Optional: it makes the tidy-up smarter.")),
    (saved, k["out"] + k["dur"], "Saved. Stored only on your PC.", ("line", "Kept in Windows Credential Manager, never in a file.")),
]


# ---------------------------------------------------------------- sound
def load(path, gain=1.0):
    x, sr = sf.read(str(path), dtype="float32")
    if x.ndim == 1:
        x = np.stack([x, x], 1)
    if sr != SR:
        n = int(len(x) * SR / sr)
        idx = np.linspace(0, len(x) - 1, n)
        x = np.stack([np.interp(idx, np.arange(len(x)), x[:, ch]) for ch in (0, 1)], 1)
    return (x * gain).astype(np.float32)


def put(buf, x, t):
    i = int(t * SR)
    x = x[: max(0, len(buf) - i)]
    buf[i:i + len(x)] += x


def norm(x, peak):
    return x * (peak / max(1e-6, float(np.max(np.abs(x)))))


def build_audio():
    n = int(TOTAL * SR)
    voice = np.zeros((n, 2), np.float32)
    for name, t in NARR:
        put(voice, norm(load(BUILD / "vo" / f"{name}.wav"), 0.85), t)
    put(voice, norm(load(BUILD / "vo" / "speaker1.wav"), 0.7), say1)
    put(voice, norm(load(BUILD / "vo" / "speaker2.wav"), 0.7), say2)
    app = load(TAKE / "speakers.wav")           # what the real app played through the speakers
    put(voice, norm(app, 0.75), read0)
    fx = np.zeros((n, 2), np.float32)
    put(fx, load(BUILD / "yap.wav", 0.55), 0.0)
    mus = music.make(TOTAL)
    # duck the music under any voice
    lvl = np.abs(voice).max(1)
    win = int(0.25 * SR)
    env = np.convolve((lvl > 0.02).astype(np.float32), np.ones(win) / win, mode="same")
    env = np.convolve(np.minimum(env * 3, 1.0), np.ones(win) / win, mode="same")
    gain = 0.42 - 0.27 * env
    mix = voice + fx + mus[:n] * gain[:, None]
    mix = np.tanh(mix * 1.1) / 1.1
    mix = mix / np.max(np.abs(mix)) * 0.93
    sf.write(BUILD / "mix.wav", mix, SR)
    step = SR // FPS  # speaker level per video frame, for the little sound bars
    a = np.abs(app).max(1)
    return np.array([a[i:i + step].max() if i < len(a) else 0 for i in range(0, len(a) + step, step)])


# ---------------------------------------------------------------- pictures
def band():
    """Top strip in the backdrop colour, fading out, so captions always sit on a calm surface."""
    a = np.zeros((H, W, 4), np.uint8)
    a[..., :3] = BG
    y = np.arange(H)
    a[..., 3] = (np.clip((215 - y) / 45, 0, 1) * 255).astype(np.uint8)[:, None]
    return Image.fromarray(a, "RGBA")


BAND = band()


def wrap_reveal(s, shown, f, maxw):
    """Lay out a sentence on up to two centred lines; only the first `shown` characters are inked."""
    words, lines, cur = s.split(), [], ""
    for w in words:
        if f.getlength((cur + " " + w).strip()) > maxw and cur:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    lines.append(cur)
    out, used = [], 0
    for ln in lines:
        vis = max(0, min(len(ln), shown - used))
        out.append((ln, vis))
        used += len(ln) + 1
    return out


def draw_caption(img, t, levels):
    for t0, t1, head, extra in CAPS:
        if not (t0 <= t < t1):
            continue
        a = ramp(t, t0, 0.25) * (1 - ramp(t, t1 - 0.15, 0.15))
        text(img, (W // 2, 70), head, font(60, 650), INK, a, dy=round(10 * (1 - ramp(t, t0, 0.25))))
        if not extra:
            return
        f = font(30, 500) if extra[0] == "say" else font(34, 500)
        if extra[0] == "line":
            text(img, (W // 2, 138), extra[1], f, BARK, a * ramp(t, t0 + 0.2, 0.3))
        elif extra[0] == "say":
            _, sentence, s0, dur = extra
            q = "“" + sentence + "”"
            shown = int(len(q) * min(1.0, max(0.0, (t - s0) / dur)) + 1) if t >= s0 else 0
            lines = wrap_reveal(q, shown, f, 1760)
            for i, (ln, vis) in enumerate(lines):
                x = W // 2 - f.getlength(ln) / 2
                y = 132 + i * 44 - (22 if len(lines) > 1 else 0) + 14
                if vis:
                    text(img, (x, y), ln[:vis], f, BARK, a, anchor="lm")
        elif extra[0] == "bars":
            wtxt = f.getlength(extra[1])
            x0 = W // 2 - (wtxt + 70) / 2
            i = int((t - read0) * FPS)
            lv = float(levels[i]) if 0 <= i < len(levels) else 0.0
            dr = ImageDraw.Draw(img)
            for j in range(5):
                hgt = 6 + 30 * min(1.0, lv * 1.6) * (0.45 + 0.55 * abs(np.sin(t * 9 + j * 1.7)))
                dr.rounded_rectangle((x0 + j * 10, 138 - hgt / 2, x0 + j * 10 + 6, 138 + hgt / 2), 3, fill=BARK)
            text(img, (x0 + 70, 138), extra[1], f, BARK, a, anchor="lm")
        return


def intro(t):
    img = Image.new("RGBA", (W, H), BUTTER + (255,))
    sp = skip.frame(t)
    img.alpha_composite(sp, (W // 2 - skip.CELL // 2 - 24, -40))
    a = ramp(t, 1.45, 0.45)
    text(img, (W // 2, 800), "Yappr", font(150, 700), INK, a, dy=round(22 * (1 - a)))
    b2 = ramp(t, 1.95, 0.45)
    text(img, (W // 2, 915), "Talk. It types. It reads back.", font(46, 500), BARK, b2, dy=round(14 * (1 - b2)))
    return img


def outro(t):
    img = Image.new("RGBA", (W, H), CREAM + (255,))
    gfx.paste_logo(img, W // 2, 250, 210, alpha=ramp(t, 0.0, 0.4))
    a = ramp(t, 0.2, 0.45)
    text(img, (W // 2, 455), "Yappr", font(120, 700), INK, a, dy=round(18 * (1 - a)))
    f = font(44, 600)
    chips = ["Free", "Open source", "Your voice stays on your computer"]
    pad, gap = 34, 26
    widths = [f.getlength(s) + 2 * pad for s in chips]
    x = (W - sum(widths) - gap * (len(chips) - 1)) / 2
    for i, (s, wd) in enumerate(zip(chips, widths)):
        kk = ramp(t, 0.7 + 0.35 * i, 0.4)
        if kk > 0:
            layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
            y = 610 + round(16 * (1 - kk))
            ImageDraw.Draw(layer).rounded_rectangle((x, y - 44, x + wd, y + 44), 44, fill=BUTTER + (round(255 * kk),))
            img.alpha_composite(layer)
            text(img, (x + wd / 2, y - 2), s, f, INK, kk)
        x += wd + gap
    u = ramp(t, 2.0, 0.5)
    text(img, (W // 2, 770), "An open source Wispr Flow + Speechify, in one app", font(40, 500), BARK, u)
    text(img, (W // 2, 880), script.REPO_URL, font(46, 650), INK, ramp(t, 2.4, 0.5))
    return img


CARDS = {"intro": intro, "pitch": gfx.pitch, "outro": outro}


class Shot:
    """Reads one stretch of the recording frame by frame."""

    def __init__(self, seg):
        vf = f"setpts=PTS/{seg['speed']},fps={FPS}" if seg["speed"] != 1 else f"fps={FPS}"
        self.p = subprocess.Popen(["ffmpeg", "-v", "error", "-ss", f"{seg['src']:.3f}", "-t", f"{seg['dur'] * seg['speed'] + 0.5:.3f}",
                                   "-i", str(TAKE / "screen.mkv"), "-vf", vf, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                                  stdout=subprocess.PIPE)
        self.last = None

    def next(self):
        raw = self.p.stdout.read(W * H * 3)
        if len(raw) == W * H * 3:
            self.last = Image.frombuffer("RGB", (W, H), raw, "raw", "RGB", 0, 1)
        return self.last

    def close(self):
        self.p.kill()


def shot_frame(seg, shot, t):
    src = shot.next().copy()
    ImageDraw.Draw(src).rectangle((0, 0, 40, 40), fill=BG)  # the sync marker
    s, fx, fy, cx, cy = seg["cam"](t)
    img = src.transform((W, H), Image.AFFINE, (1 / s, 0, fx - cx / s, 0, 1 / s, fy - cy / s),
                        resample=Image.BICUBIC, fillcolor=BG).convert("RGBA")
    img.alpha_composite(BAND)
    return img


def main():
    OUT.mkdir(exist_ok=True)
    levels = build_audio()
    print(f"total {TOTAL:.2f}s")
    for s in segs:
        print(f"  {s['out']:6.2f} {s['dur']:5.2f} {s.get('name') or s['draw']}")
    stills = {round((s["out"] + s["dur"] * f) * FPS): f"{i}-{s.get('name') or s['draw']}-{j}"
              for i, s in enumerate(segs) for j, f in enumerate((0.3, 0.6, 0.92))}
    (BUILD / "stills").mkdir(exist_ok=True)
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
                            "-i", "-", "-i", str(BUILD / "mix.wav"), "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-shortest",
                            str(OUT / "yappr-demo.mp4")], stdin=subprocess.PIPE)
    cur, shot, prev_last, frame = None, None, None, None
    for n in range(int(TOTAL * FPS)):
        T = n / FPS
        seg = next(s for s in segs if s["out"] <= T < s["out"] + s["dur"] + 1e-6)
        if seg is not cur:
            if shot:
                shot.close()
            prev_last, cur = frame, seg
            shot = Shot(seg) if seg["kind"] == "shot" else None
        t = T - seg["out"]
        frame = CARDS[seg["draw"]](t) if seg["kind"] == "card" else shot_frame(seg, shot, t)
        if seg["kind"] == "shot":
            draw_caption(frame, T, levels)
        out = frame
        if prev_last is not None and t < 0.3:
            out = Image.blend(prev_last, frame, ease(t / 0.3))
        rgb = out.convert("RGB")
        if n in stills:
            rgb.save(BUILD / "stills" / f"{stills[n]}.png")
        enc.stdin.write(rgb.tobytes())
    enc.stdin.close()
    enc.wait()
    (BUILD / "timeline.json").write_text(json.dumps(dict(
        total=TOTAL, segments=[{kk: v for kk, v in s.items() if kk != "cam"} for s in segs],
        narration=NARR, captions=[(a, b2, h) for a, b2, h, _ in CAPS], speech=[say1, say2], read_aloud=[read0, read0 + spk_len]),
        indent=1), encoding="utf-8")
    print("wrote", OUT / "yappr-demo.mp4")


if __name__ == "__main__":
    main()
