r"""A 9-second sample (intro + pitch, narration, music) so the look and sound can be judged early.

    .venv\Scripts\python.exe video\teaser.py   ->  video/out/yappr-teaser.mp4
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import gfx  # noqa: E402

BUILD, OUT = HERE / "build", HERE / "out"
OUT.mkdir(exist_ok=True)
DUR, CUT = 9.0, 2.5
vo = [("intro", 0.7), ("pitch", 3.0)]
inputs, filt = ["-i", str(BUILD / "music.wav")], ["[1:a]volume=0.22,atrim=0:%s,afade=t=out:st=%s:d=1.2[m]" % (DUR, DUR - 1.2)]
for i, (sid, at) in enumerate(vo, 2):
    inputs += ["-i", str(BUILD / "vo" / f"{sid}.wav")]
    filt.append(f"[{i}:a]adelay={int(at * 1000)}:all=1,volume=1.5[v{i}]")
filt.append("[m]" + "".join(f"[v{i}]" for i in range(2, len(vo) + 2)) + f"amix=inputs={len(vo) + 1}:normalize=0[a]")
p = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{gfx.W}x{gfx.H}",
                      "-r", str(gfx.FPS), "-i", "-", *inputs, "-filter_complex", ";".join(filt),
                      "-map", "0:v", "-map", "[a]", "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p",
                      "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-t", str(DUR),
                      str(OUT / "yappr-teaser.mp4")], stdin=subprocess.PIPE)
# video is input 0, so audio inputs shift by one
for n in range(int(DUR * gfx.FPS)):
    t = n / gfx.FPS
    f = gfx.crossfade(gfx.intro(t), gfx.pitch(t - CUT), (t - CUT) / 0.35) if t > CUT - 0.01 else gfx.intro(t)
    p.stdin.write(f.convert("RGB").tobytes())
    if n in (60, 150, 240):
        f.convert("RGB").save(BUILD / f"teaser-{n}.png")
p.stdin.close()
sys.exit(p.wait())
