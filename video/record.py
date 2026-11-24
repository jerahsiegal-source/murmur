r"""Record the real Yappr app for the product video, without showing anything personal.

    .venv\Scripts\python.exe video\record.py

What it does: covers the desktop with a plain backdrop, starts Yappr from this checkout on an empty
throwaway profile (fake microphone, Ctrl+Shift test hotkey so other dictation apps stay quiet, and a
throwaway key store so the real API key is never read or changed), opens demo pages in Edge and Chrome
on empty temporary profiles, drives everything with real key presses and mouse clicks, and records the
screen (ffmpeg) and what the speakers play. Writes video/build/take/{screen.mkv, speakers.wav, events.json}.

Yappr must not already be running (it allows one copy). Nothing is restarted or killed here except
what this script started.
"""
import ctypes
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from ctypes import wintypes
from pathlib import Path

import numpy as np
import soundfile as sf

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(HERE))
import script  # noqa: E402
from yappr.paste import get_clipboard_text, set_clipboard_text  # noqa: E402

ctypes.windll.shcore.SetProcessDpiAwareness(2)
user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.GetForegroundWindow.restype = wintypes.HWND
user32.WindowFromPoint.restype = wintypes.HWND
user32.WindowFromPoint.argtypes = [wintypes.POINT]
user32.GetAncestor.restype = wintypes.HWND
user32.GetAncestor.argtypes = [wintypes.HWND, ctypes.c_uint]
user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_uint]
BUILD = HERE / "build"
TAKE = BUILD / "take"
PROFILE = BUILD / "profile"
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PYW = str(ROOT / ".venv" / "Scripts" / "pythonw.exe")
PY = str(ROOT / ".venv" / "Scripts" / "python.exe")
SCALE = user32.GetDpiForSystem() / 96
EVENTS: list = []
HOME: dict = {}


def ev(name, **kw):
    EVENTS.append(dict(name=name, t=time.time(), **kw))
    print(ascii(f"  {name} {kw or ''}")[1:-1][:200], flush=True)


# ---------- input
class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class _U(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("pad", ctypes.c_byte * 32)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _U)]


def key(vk, up=False):
    i = INPUT(type=1)
    i.u.ki = KEYBDINPUT(wVk=vk, wScan=0, dwFlags=2 if up else 0, time=0, dwExtraInfo=0)
    user32.SendInput(1, ctypes.byref(i), ctypes.sizeof(INPUT))


def chord(*vks, hold=0.07):
    for vk in vks:
        key(vk)
        time.sleep(0.03)
    time.sleep(hold)
    for vk in reversed(vks):
        key(vk, True)
        time.sleep(0.02)


def cursor():
    p = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(p))
    return p.x, p.y


def glide(x, y, dur=0.7):
    """Move the pointer the way a hand does: ease in and out along a slight curve."""
    x0, y0 = cursor()
    n = max(2, int(dur * 120))
    bend = 0.08 * ((x - x0) ** 2 + (y - y0) ** 2) ** 0.5
    for i in range(1, n + 1):
        k = i / n
        e = k * k * (3 - 2 * k)
        b = bend * 4 * k * (1 - k)
        user32.SetCursorPos(int(x0 + (x - x0) * e), int(y0 + (y - y0) * e - b))
        time.sleep(dur / n)


def click(n=1):
    for _ in range(n):
        user32.mouse_event(2, 0, 0, 0, 0)
        time.sleep(0.04)
        user32.mouse_event(4, 0, 0, 0, 0)
        time.sleep(0.07)


# ---------- windows
def find(title):
    out = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def each(h, _):
        n = user32.GetWindowTextLengthW(h)
        if n and user32.IsWindowVisible(h):
            b = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(h, b, n + 1)
            if b.value == title:
                out.append(h)
        return True

    user32.EnumWindows(each, 0)
    return out[0] if out else None


def wait_window(title, secs=25):
    end = time.time() + secs
    while time.time() < end:
        h = find(title)
        if h:
            return h
        time.sleep(0.2)
    raise RuntimeError(f"window never appeared: {title}")


def rect(h):
    r = wintypes.RECT()
    user32.GetWindowRect(h, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


def place(h, x, y, w, hgt):
    """Position (physical pixels) and keep above the backdrop."""
    user32.ShowWindow(h, 9)
    user32.SetWindowPos(h, wintypes.HWND(-1), int(x), int(y), int(w), int(hgt), 0x0010)  # TOPMOST, NOACTIVATE


def hide(h):
    """Park the window off the screen (hiding and re-showing browser windows proved unreliable)."""
    l, t, r, b = rect(h)
    if l < 2500:
        HOME[h] = (l, t)
    user32.SetWindowPos(h, None, 3200, t, 0, 0, 0x0001 | 0x0004 | 0x0010)  # NOSIZE, NOZORDER, NOACTIVATE


def show(h):
    x, y = HOME.get(h, (300, 60))
    user32.SetWindowPos(h, wintypes.HWND(-1), x, y, 0, 0, 0x0001 | 0x0010)
    user32.SetWindowPos(h, wintypes.HWND(0), 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)  # top of the always-on-top group


def on_top_at(h, fx, fy):
    """Is this window really the one showing at that spot?"""
    x, y = at(h, fx, fy)
    w = user32.WindowFromPoint(wintypes.POINT(x, y))
    return user32.GetAncestor(w, 2) == h


def activate(h):
    """Make sure a window we just clicked really has the keyboard."""
    for _ in range(15):
        if user32.GetForegroundWindow() == h:
            return
        key(0xE8)
        key(0xE8, True)
        user32.SetForegroundWindow(h)
        time.sleep(0.1)


def at(h, fx, fy):
    l, t, r, b = rect(h)
    return int(l + (r - l) * fx), int(t + (b - t) * fy)


def must_be_front(h, what):
    activate(h)
    if user32.GetForegroundWindow() != h:
        raise RuntimeError(f"{what} is not in front; not pressing any keys")


# ---------- speakers
class Loopback:
    def __init__(self, path):
        import pyaudiowpatch as pa

        self.pa = pa.PyAudio()
        wasapi = self.pa.get_host_api_info_by_type(pa.paWASAPI)
        spk = self.pa.get_device_info_by_index(wasapi["defaultOutputDevice"])
        if not spk.get("isLoopbackDevice"):
            spk = next(lb for lb in self.pa.get_loopback_device_info_generator() if spk["name"] in lb["name"])
        self.rate, self.ch = int(spk["defaultSampleRate"]), int(spk["maxInputChannels"])
        self.path, self.chunks, self.first, self.lock = path, [], None, threading.Lock()

        def cb(data, frames, t, status):
            now = time.time()
            x = np.frombuffer(data, dtype=np.float32).copy()
            with self.lock:
                if self.first is None:
                    self.first = now - frames / self.rate
                self.chunks.append((now, x))
            return (None, pa.paContinue)

        self.s = self.pa.open(format=pa.paFloat32, channels=self.ch, rate=self.rate, input=True,
                              input_device_index=spk["index"], frames_per_buffer=int(self.rate * 0.02),
                              stream_callback=cb)
        self.s.start_stream()

    def level(self, since):
        with self.lock:
            xs = [x for t, x in self.chunks if t >= since]
        return float(np.sqrt(np.mean(np.concatenate(xs) ** 2))) if xs else 0.0

    def close(self):
        self.s.stop_stream()
        self.s.close()
        with self.lock:
            x = np.concatenate([c for _, c in self.chunks]) if self.chunks else np.zeros(0, np.float32)
        sf.write(self.path, x.reshape(-1, self.ch), self.rate)
        return self.first


# ---------- the app
def history_count():
    try:
        return len((PROFILE / "history.jsonl").read_text(encoding="utf-8").splitlines())
    except Exception:
        return 0


def dictate(mic, hwnd, what):
    shutil.copyfile(BUILD / mic, BUILD / "mic.wav")
    secs = sf.info(str(BUILD / mic)).duration
    n = history_count()
    must_be_front(hwnd, what)
    key(0xA2)
    time.sleep(0.05)
    key(0xA0)  # Ctrl+Shift: the test stand-in for Ctrl+Win
    ev(f"{what}_down", mic=mic)
    time.sleep(secs + 0.15)
    key(0xA0, True)
    key(0xA2, True)
    ev(f"{what}_up")
    end = time.time() + 20
    while history_count() == n and time.time() < end:
        time.sleep(0.03)
    if history_count() == n:
        raise RuntimeError("nothing was pasted")
    rec = json.loads((PROFILE / "history.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    ev(f"{what}_pasted", rec=rec)


def browser(exe, profile, url, x, y, w, h):
    subprocess.Popen([exe, f"--user-data-dir={BUILD / profile}", "--no-first-run", "--no-default-browser-check",
                      "--disable-sync", "--disable-features=Translate,CalculateNativeWinOcclusion",
                      "--disable-backgrounding-occluded-windows", "--hide-crash-restore-bubble",
                      f"--window-position={x},{y}", f"--window-size={w},{h}", f"--app={url}"],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def kill_tree(needle):
    import psutil

    for p in psutil.process_iter(["cmdline"]):
        try:
            if any(needle in a for a in (p.info["cmdline"] or [])):
                p.kill()
        except Exception:
            pass


def main():
    from measure_quick import yappr_procs

    if yappr_procs() or yappr_procs("yappr.hotkey_host"):
        sys.exit("Yappr is already running; stop it first.")
    for d in (PROFILE, TAKE, BUILD / "edge-profile", BUILD / "chrome-profile", BUILD / "window-drive"):
        shutil.rmtree(d, ignore_errors=True)
    PROFILE.mkdir(parents=True, exist_ok=True)
    TAKE.mkdir(parents=True, exist_ok=True)
    (PROFILE / ".onboarded").write_text("demo\n")
    (BUILD / "demo-keys.json").unlink(missing_ok=True)
    trigger = TAKE / "sync"
    art = BUILD / "article.html"
    art.write_text((HERE / "pages" / "article.html").read_text(encoding="utf-8")
                   .replace("__READ_TEXT__", script.READ_TEXT), encoding="utf-8")
    clip_before = get_clipboard_text()
    mouse_before = cursor()
    cap = lb = backdrop = None
    try:
        backdrop = subprocess.Popen([PY, str(HERE / "backdrop.py"), str(trigger), "420"])
        wait_window("Yappr demo backdrop")
        # --- Yappr itself, on an empty profile
        env = {k: v for k, v in os.environ.items() if not k.startswith(("YAPPR_", "MURMUR_"))}
        env.update(YAPPR_DATA_DIR=str(PROFILE), YAPPR_FAKE_MIC=str(BUILD / "mic.wav"), YAPPR_TEST_CHORD="ctrl+shift",
                   YAPPR_WINDOW_TEST_DIR=str(BUILD / "window-drive"),
                   PYTHON_KEYRING_BACKEND="demo_keyring.FileKeyring", PYTHONPATH=str(HERE),
                   YAPPR_DEMO_KEYS=str(BUILD / "demo-keys.json"))
        shutil.copyfile(BUILD / "mic1.wav", BUILD / "mic.wav")
        subprocess.Popen([PYW, "-m", "yappr"], cwd=str(ROOT), env=env, stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP)
        log = PROFILE / "yappr.log"
        end = time.time() + 60
        while time.time() < end and not (
                log.exists() and "Yappr started" in log.read_text(encoding="utf-8", errors="ignore")):
            time.sleep(0.3)
        import e2e_bar

        end = time.time() + 20
        while time.time() < end and not e2e_bar.bar_rect():
            time.sleep(0.3)
        bar = e2e_bar.bar_rect()
        if not bar:
            raise RuntimeError("the bar never appeared")
        print("bar", bar, "scale", SCALE, flush=True)
        # --- demo windows (sizes in screen points; Windows scales them)
        browser(EDGE, "edge-profile", (HERE / "pages" / "mail.html").as_uri(), 218, 70, 1100, 640)
        mail = wait_window("New message")
        browser(CHROME, "chrome-profile", (HERE / "pages" / "chat.html").as_uri(), 268, 90, 1000, 600)
        chat = wait_window("Team chat")
        browser(EDGE, "edge-profile", art.as_uri(), 218, 70, 1100, 640)
        reader = wait_window("Reader")
        time.sleep(1.5)
        for h in (mail, chat, reader):
            l, t, r, b = rect(h)
            place(h, (1920 - (r - l)) // 2, 60, r - l, b - t)
        hide(chat)
        hide(reader)
        time.sleep(0.5)

        # --- warm-up (not recorded): the first dictation loads the speech model
        glide(*at(mail, 0.5, 0.62), 0.3)
        click()
        time.sleep(0.5)
        dictate("mic2.wav", mail, "warmup")
        time.sleep(0.8)
        chord(0xA2, 0x41)
        chord(0x2E)  # Ctrl+A, Delete: empty the box again
        time.sleep(0.3)
        EVENTS.clear()
        glide(1560, 330, 0.3)

        # --- recording starts
        lb = Loopback(str(TAKE / "speakers.wav"))
        cap = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "gdigrab", "-framerate", "30", "-draw_mouse", "1",
                                "-i", "desktop", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "12",
                                "-pix_fmt", "yuv444p", str(TAKE / "screen.mkv")], stdin=subprocess.PIPE)
        time.sleep(2.5)
        trigger.write_text("go")
        time.sleep(1.0)

        # 1. dictation into Mail (Edge)
        ev("mail_show")
        time.sleep(0.8)
        glide(*at(mail, 0.42, 0.6), 0.8)
        click()
        time.sleep(0.6)
        dictate("mic1.wav", mail, "d1")
        time.sleep(2.6)

        # 2. dictation into Team chat (Chrome)
        hide(mail)
        show(chat)
        time.sleep(0.3)
        if not on_top_at(chat, 0.4, 0.86):
            raise RuntimeError("the chat window is not showing")
        ev("chat_show")
        time.sleep(0.7)
        glide(*at(chat, 0.4, 0.86), 0.7)
        click()
        time.sleep(0.6)
        dictate("mic2.wav", chat, "d2")
        time.sleep(2.6)

        # 3. read aloud in Reader (Edge)
        hide(chat)
        show(reader)
        time.sleep(0.3)
        if not on_top_at(reader, 0.5, 0.56):
            raise RuntimeError("the reader window is not showing")
        ev("reader_show")
        time.sleep(0.8)
        glide(*at(reader, 0.5, 0.56), 0.8)
        click(3)
        ev("read_selected")
        time.sleep(0.9)
        must_be_front(reader, "Reader")
        t_read = time.time()
        chord(0xA2, 0xA4, 0x58)  # Ctrl+Alt+X
        ev("read_key")
        end = time.time() + 15
        started = None
        while time.time() < end:
            time.sleep(0.1)
            if started is None and lb.level(t_read) > 0.002:
                started = time.time()
                ev("read_sound")
            if started and time.time() - started > 2 and lb.level(time.time() - 0.7) < 0.0005:
                break
        ev("read_done")
        time.sleep(0.8)

        # 4. paste a key into Yappr's own settings
        hide(reader)
        bl, bt, br, bb = bar
        glide(bl + int(26 * SCALE), (bt + bb) // 2, 0.8)
        click()
        ev("bar_click")
        ywin = wait_window("Yappr")
        l, t, r, b = rect(ywin)
        place(ywin, (1920 - (r - l)) // 2, 30, r - l, b - t)
        ev("yappr_window")
        import e2e_window

        e2e_window.DRIVE = BUILD / "window-drive"
        js = e2e_window.js
        end = time.time() + 20
        dpr = None
        while time.time() < end and not dpr:
            try:
                dpr = js("window.devicePixelRatio", timeout=3)
            except Exception:
                time.sleep(0.5)
        org = wintypes.POINT(0, 0)
        user32.ClientToScreen(ywin, ctypes.byref(org))

        def centre(sel):
            x, y = js("(()=>{const r=document.querySelector('%s').getBoundingClientRect();"
                      "return [r.left+r.width/2,r.top+r.height/2]})()" % sel)
            return int(org.x + x * dpr), int(org.y + y * dpr)

        time.sleep(1.6)
        glide(*centre('.nav[data-page=\\"settings\\"]'), 0.8)
        click()
        ev("settings_click")
        time.sleep(1.4)
        glide(*centre("#key"), 0.8)
        click()
        ev("key_click")
        time.sleep(0.5)
        set_clipboard_text(script.DUMMY_KEY, private=True)
        must_be_front(ywin, "Yappr")
        chord(0xA2, 0x56)  # Ctrl+V
        ev("key_pasted")
        time.sleep(1.0)
        glide(*centre("#savekey"), 0.6)
        click()
        ev("key_saved")
        time.sleep(2.8)
        ev("end", status=js("document.querySelector('#s-ai .status').textContent"))
    finally:
        if cap:
            try:
                cap.stdin.write(b"q")
                cap.stdin.flush()
                cap.wait(timeout=15)
            except Exception:
                cap.kill()
        first = lb.close() if lb else None
        sync = None
        try:
            sync = float((TAKE / "sync.time").read_text())
        except Exception:
            pass
        (TAKE / "events.json").write_text(
            json.dumps(dict(events=EVENTS, sync=sync, speakers_start=first, scale=SCALE), indent=1), encoding="utf-8")
        for p in yappr_procs() + yappr_procs("yappr.hotkey_host") + yappr_procs("yappr.window"):
            try:
                p.kill()
            except Exception:
                pass
        kill_tree(str(BUILD / "edge-profile"))
        kill_tree(str(BUILD / "chrome-profile"))
        if backdrop:
            backdrop.kill()
        try:
            if clip_before is not None:
                set_clipboard_text(clip_before, private=True)
        except Exception:
            pass
        user32.SetCursorPos(*mouse_before)
        for vk in (0xA0, 0xA2, 0xA4):  # never leave a modifier held
            key(vk, True)
    print("done", flush=True)


if __name__ == "__main__":
    main()
