"""Murmur: hotkey dictation + meeting notes for Windows."""
from __future__ import annotations

import ctypes
import logging
import os
import subprocess
import sys
import threading
import time
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor
from logging.handlers import RotatingFileHandler
from pathlib import Path

from . import storage
from .audio import MicRecorder
from .calendar_watch import CalendarWatcher
from .cleanup import Cleaner
from .config import Store
from .hotkeys import VK_MASK, HotkeyProcess
from .llm import LLMClient, make_llm
from .paste import copy_selection, paste_text, tap_key
from .speech_text import clean_for_speech
from .stt import Transcriber
from .tts import Reader, Voice, clamp_speed
from .ui import Bar, MeetingPrompt

log = logging.getLogger("murmur")


def setup_logging(data_dir: Path) -> None:
    logging.getLogger("phonemizer").setLevel(logging.ERROR)  # warns on every chunk, harmlessly
    h = RotatingFileHandler(data_dir / "murmur.log", maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(h)
    if sys.stderr and os.environ.get("MURMUR_DEBUG"):
        root.addHandler(logging.StreamHandler())


def single_instance() -> bool:
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateMutexW.restype = ctypes.c_void_p
    single_instance._h = k32.CreateMutexW(None, False, "Local\\MurmurDictation")
    return ctypes.get_last_error() != 183  # ERROR_ALREADY_EXISTS


class App:
    WHOLE_PASS_MAX_S = 15.0
    def __init__(self, root: tk.Tk, store: Store):
        self.root = root
        self.store = store
        self.data = store.root
        s = store.settings
        self.llm = self._make_llm()
        self.cleaner = Cleaner(self.llm, store)
        self.transcriber = Transcriber(s.stt_model, s.stt_quantization, s.stt_threads, s.stt_idle_unload_min)
        self.bar = Bar(root, on_notes=self.toggle_meeting, on_stop_dictation=self.stop_handsfree, on_settings=self.open_settings)
        # phrases are only split off once a dictation is longer than the one-pass limit
        self.rec = MicRecorder(on_level=self.bar.set_level, on_segment=self._segment, device=s.mic_device or None,
                               segment_min_s=self.WHOLE_PASS_MAX_S)
        self.stt_exec = ThreadPoolExecutor(1, thread_name_prefix="stt")
        self.finish_exec = ThreadPoolExecutor(1, thread_name_prefix="finish")  # one worker: pastes stay in order
        self.hook = HotkeyProcess(self.on_hotkey)
        self.lock = threading.Lock()
        self.recording = False  # mic open for a dictation
        self.pending = 0  # dictations still being transcribed/cleaned/pasted
        self.seg_futures: list = []
        self.last_text = ""
        for h in storage.read_history(self.data, 1):
            self.last_text = h.get("text", "")
        self.meeting = None
        self.meeting_lock = threading.Lock()
        self.meeting_busy = False  # a start/stop is in progress
        self.prompts: list = []
        self.calendar = CalendarWatcher(lambda: self.store.settings.calendar_ics_url, self._calendar_prompt,
                                        lambda: self.store.settings.calendar_prompt_min_before)
        self.voice = Voice(self.data)
        self.reader = Reader(self.voice, lambda: self.store.settings.read_voice,
                             lambda: self.store.settings.read_speed,
                             on_error=lambda msg: self.bar.toast(msg, 4),
                             busy=lambda: self.recording or self.meeting is not None)
        self.read_lock = threading.Lock()
        self.tray = None
        self.settings_win = None

    def _make_llm(self) -> LLMClient:
        s = self.store.settings
        return make_llm(s.llm_provider, s.llm_base_url, Store.get_api_key(s.llm_provider), s.llm_model,
                        s.price_in_per_m, s.price_out_per_m, self.data / "usage.jsonl")

    def reload_settings(self) -> None:
        s = self.store.settings
        self.llm = self._make_llm()
        self.cleaner.llm = self.llm
        self.transcriber.idle_unload_s = s.stt_idle_unload_min * 60
        self.rec.device = s.mic_device or None
        self.calendar.refresh_now()

    # ------------------------------------------------------------ lifecycle
    def start(self) -> None:
        self.hook.start()
        self.calendar.start()
        threading.Thread(target=self._housekeeping, name="housekeeping", daemon=True).start()
        self._start_tray()
        if not self.store.settings.show_bar:
            self.bar.win.withdraw()
        self.root.after(3000, self.voice.preload_async)  # after startup, so it never slows it down
        log.info("Murmur started")

    def quit(self) -> None:
        def finish():
            for _ in range(100):  # let a start/stop that's already under way complete first
                with self.meeting_lock:
                    if not self.meeting_busy:
                        m, self.meeting = self.meeting, None
                        self.meeting_busy = True  # nothing new may start while quitting
                        break
                time.sleep(0.1)
            else:
                m = None
            if m is not None:
                self.bar.toast("Finishing meeting notes…", 600)
                m.stop()
                m.wait(600)
            self.reader.stop()
            self.hook.stop()
            if self.tray is not None:
                self.tray.stop()
            self.bar.post(self.root.destroy)

        threading.Thread(target=finish, name="quit", daemon=True).start()  # keep the UI responsive

    def _housekeeping(self) -> None:
        from .meeting import recover_unfinished

        s = self.store.settings
        try:  # notes from a call that was cut off (crash, restart): finish them, then drop the audio
            recover_unfinished(Path(s.meetings_dir), self.transcriber, self.llm, s, lambda: self.store.dictionary,
                               active=lambda: self.meeting.dir if self.meeting else None)
        except Exception:
            log.exception("meeting recovery")
        while True:
            try:
                s = self.store.settings
                storage.purge(self.data, Path(s.meetings_dir), int(s.retention_days))
            except Exception:
                log.exception("purge")
            time.sleep(6 * 3600)

    # ------------------------------------------------------------ hotkeys
    def on_hotkey(self, e: str) -> None:
        log.info("hotkey %s (recording=%s, pending=%d)", e, self.recording, self.pending)
        if e == "start":
            self._start_dictation()
        elif e == "handsfree":
            if self.recording:
                self.bar.set_state("handsfree")
        elif e == "stop":
            self._stop_dictation()
        elif e == "cancel":
            self._cancel_dictation()
        elif e == "paste_last":
            if self.last_text:
                threading.Thread(target=paste_text, args=(self.last_text,), daemon=True).start()
            else:
                self.bar.toast("Nothing to paste yet")
        elif e == "read":
            threading.Thread(target=self.read_selection, args=(time.monotonic(),), name="read", daemon=True).start()
        elif e == "read_pause":
            if self.reader.active:
                self.bar.toast("Paused" if self.reader.toggle_pause() else "Reading", 1.2)
        elif e in ("read_faster", "read_slower"):
            self.change_read_speed(0.1 if e == "read_faster" else -0.1)

    # ------------------------------------------------------------ read aloud
    def read_selection(self, t0: float | None = None) -> None:
        """Ctrl+Alt+X: read the highlighted text, or stop if already reading."""
        if not self.read_lock.acquire(blocking=False):
            tap_key(VK_MASK)  # X was swallowed: don't leave the app a bare Ctrl+Alt tap
            return  # still grabbing the previous selection
        copied = False
        try:
            if self.reader.active:
                tap_key(VK_MASK)  # X was swallowed: don't leave the app a bare Ctrl+Alt tap
                self.reader.stop()
                return
            if self.recording or self.meeting is not None:
                tap_key(VK_MASK)
                # the mic / meeting recording would pick the voice up
                self.bar.toast("Not while recording" if self.recording else "Not during meeting notes", 2)
                return
            t0 = time.monotonic() if t0 is None else t0
            copied = True  # the copy keys (Ctrl+Insert/C) stand in for the mask from here on
            raw = copy_selection(self.hook.copy)
            t_copy = time.monotonic()
            if raw is None:
                tap_key(VK_MASK)  # nothing was copied; the copy keys may not have reached the app
            text = clean_for_speech(raw or "")
            if not text:
                self.bar.toast("Highlight some text first", 2)
                return
            if not self.voice.loaded:
                self.bar.toast("Loading voice…", 2)
            if self.recording or self.meeting is not None:  # started while we were copying
                return
            self.reader.speak(text, t0=t0)
            log.info("read: %d chars selected, copy %.3fs", len(raw or ""), t_copy - t0)
        except Exception:
            log.exception("read aloud failed")
            if not copied:
                tap_key(VK_MASK)
            self.bar.toast("Couldn't read that")
        finally:
            self.read_lock.release()

    def change_read_speed(self, delta: float) -> None:
        s = self.store.settings
        new = clamp_speed(round(float(s.read_speed) + delta, 1))
        if new != s.read_speed:
            s.read_speed = new
            self.store.save_settings()
        self.reader.set_speed(new)
        self.bar.toast(f"Speed {new:.1f}×", 1.2)

    def _idle_state(self) -> str:
        return "meeting" if self.meeting else "idle"

    def _start_dictation(self) -> None:
        # A new dictation may start while the previous one is still being cleaned up and pasted;
        # results are pasted in order by the single finish worker.
        with self.lock:
            if self.recording:
                return
            self.recording = True
            self.seg_futures = []
        if self.reader.active:  # don't dictate over the voice (the mic would hear it)
            self.reader.stop()
        self.transcriber.preload_async()
        try:
            self.rec.start()
        except Exception:
            log.exception("mic start failed")
            with self.lock:
                self.recording = False
            self.hook.reset()
            self.bar.toast("Microphone unavailable")
            return
        self.bar.set_state("listening")

    def _segment(self, audio) -> None:
        self.seg_futures.append(self.stt_exec.submit(self.transcriber.transcribe, audio))

    def stop_handsfree(self) -> None:
        self.hook.reset()
        threading.Thread(target=self._stop_dictation, daemon=True).start()

    def _stop_dictation(self) -> None:
        with self.lock:
            if not self.recording:
                return
            audio_s = self.rec.duration()
            tail = self.rec.stop()
            full = self.rec.full_audio() if audio_s <= self.WHOLE_PASS_MAX_S else None
            segs = self.seg_futures
            self.recording = False
            self.pending += 1
        t_stop = time.monotonic()
        self.bar.set_state("processing")
        if full is not None:
            # short dictation: one pass over everything gives the best punctuation (~1 s)
            futures = [self.stt_exec.submit(self.transcriber.transcribe, full)]
        else:
            # long dictation: phrases were transcribed while talking; only the tail is left
            futures = list(segs) + [self.stt_exec.submit(self.transcriber.transcribe, tail)]
        self.finish_exec.submit(self._finish, futures, t_stop, audio_s)

    def _cancel_dictation(self) -> None:
        with self.lock:
            if not self.recording:
                return
            self.recording = False
            self.rec.stop()
            busy = self.pending > 0
        self.bar.set_state("processing" if busy else self._idle_state())

    def _finish(self, futures, t_stop: float, audio_s: float) -> None:
        try:
            parts = [f.result() for f in futures]
            raw = " ".join(p for p in parts if p).strip()
            t_stt = time.monotonic()
            if not raw:
                self.bar.toast("Didn't catch that")
                return
            text, how = self.cleaner.clean(raw)
            t_ready = time.monotonic()
            if not text:
                self.bar.toast("Didn't catch that")
                return
            self.last_text = text
            ok = paste_text(text)
            storage.append_history(self.data, {
                "raw": raw, "text": text, "method": how, "audio_s": round(audio_s, 1),
                "stt_s": round(t_stt - t_stop, 2), "ready_s": round(t_ready - t_stop, 2), "pasted": ok,
            })
            log.info("dictation %.1fs audio -> ready in %.2fs (stt %.2fs, %s)", audio_s, t_ready - t_stop, t_stt - t_stop, how)
            if not ok:
                self.bar.toast("Couldn't paste — press Alt+Shift+Z")
        except Exception:
            log.exception("dictation failed")
            self.bar.toast("Something went wrong")
        finally:
            with self.lock:
                self.pending -= 1
                quiet = not self.recording and self.pending == 0
            if quiet:
                self.bar.set_state(self._idle_state())

    # ------------------------------------------------------------ meetings
    def toggle_meeting(self, title: str = "") -> None:
        """Bar / tray button: start if idle, stop if recording."""
        threading.Thread(target=self._meeting_action, args=("toggle", title), daemon=True).start()

    def start_meeting(self, title: str = "") -> None:
        """Calendar prompt: only ever starts (never stops a recording that is already running)."""
        threading.Thread(target=self._meeting_action, args=("start", title), daemon=True).start()

    def _meeting_action(self, action: str, title: str) -> None:
        from .meeting import MeetingSession

        with self.meeting_lock:  # one start/stop at a time; double-clicks can't create two sessions
            if self.meeting_busy:
                return
            if self.meeting is not None:
                if action == "start":
                    return
                m, self.meeting = self.meeting, None
                stopping = True
            else:
                stopping = False
            self.meeting_busy = True
        try:
            if stopping:
                m.stop()
                if not self.recording:
                    self.bar.set_state("idle")
                self.bar.toast("Transcribing the rest…", 4)
                return
            s = self.store.settings
            try:
                m = MeetingSession(Path(s.meetings_dir), title or "Meeting", self.transcriber, self.llm, s,
                                   on_status=self._meeting_status, dictionary=lambda: self.store.dictionary)
                m.start()
            except Exception as e:
                log.exception("meeting start failed")
                self.bar.toast(f"Couldn't start recording: {e}"[:60], 4)
                return
            with self.meeting_lock:
                self.meeting = m
            self.bar.post(self._close_prompts)
            self.bar.meeting_started = time.monotonic()
            if not self.recording:
                self.bar.set_state("meeting")
            threading.Thread(target=self._meeting_levels, args=(m,), daemon=True).start()
        finally:
            with self.meeting_lock:
                self.meeting_busy = False

    def _close_prompts(self) -> None:
        for p in self.prompts:
            p.close()
        self.prompts = []

    def _meeting_levels(self, m) -> None:
        while self.meeting is m:
            self.bar.set_level(m.levels() / 6)
            time.sleep(0.25)

    def _meeting_status(self, status: str) -> None:
        if status == "summarizing":
            self.bar.toast("Writing summary…", 6)
        elif status == "done":
            self.bar.toast("Meeting notes saved", 4)
        elif status == "error":
            self.bar.toast("Meeting notes failed — see log", 5)
        elif status == "device-error":
            self.bar.toast("Audio device changed — couldn't follow it", 6)

    def finished_meeting_dirs(self) -> list[Path]:
        d = Path(self.store.settings.meetings_dir)
        return sorted((p for p in d.iterdir() if p.is_dir()), reverse=True) if d.exists() else []

    def _calendar_prompt(self, ev: dict) -> None:
        if self.meeting is not None:
            return

        def show():
            self.prompts = [p for p in self.prompts if p.alive()]
            self.prompts.append(MeetingPrompt(self.root, ev["title"], lambda: self.start_meeting(ev["title"])))

        self.bar.post(show)

    # ------------------------------------------------------------ tray + settings
    def _start_tray(self) -> None:
        try:
            import pystray
            from PIL import Image, ImageDraw
        except Exception:
            log.warning("pystray unavailable; no tray icon")
            return
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle((4, 4, 60, 60), 16, fill=(24, 24, 27, 255))
        for i, h in enumerate((10, 22, 34, 22, 10)):
            x = 14 + i * 9
            d.line((x, 32 - h / 2, x, 32 + h / 2), fill=(138, 180, 255, 255), width=5)
        M = pystray.MenuItem
        menu = pystray.Menu(
            M(lambda _: "Stop note-taker" if self.meeting else "Start note-taker", lambda: self.toggle_meeting()),
            M("Paste last dictation", lambda: self.on_hotkey("paste_last")),
            M("Stop reading aloud", lambda: self.reader.stop(), visible=lambda _: self.reader.active),
            M("Open meeting notes folder", self.open_meetings_folder),
            M("Settings…", lambda: self.bar.post(self.open_settings), default=True),
            pystray.Menu.SEPARATOR,
            M("Quit Murmur", lambda: self.bar.post(self.quit)),
        )
        self.tray = pystray.Icon("Murmur", img, "Murmur — hold Ctrl+Win to dictate · Ctrl+Alt+X reads aloud", menu)
        self.tray.run_detached()

    def open_meetings_folder(self) -> None:
        p = Path(self.store.settings.meetings_dir)
        p.mkdir(parents=True, exist_ok=True)
        os.startfile(p)

    def open_settings(self) -> None:
        from .settings_ui import SettingsWindow

        if self.settings_win is not None and self.settings_win.alive():
            self.settings_win.focus()
            return
        self.settings_win = SettingsWindow(self.root, self)


def main() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass
    store = Store()
    setup_logging(store.root)
    if not single_instance():
        log.info("already running")
        return
    root = tk.Tk()
    root.withdraw()
    app = App(root, store)
    app.start()
    root.mainloop()
