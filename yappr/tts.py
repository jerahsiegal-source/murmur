"""Read-aloud: a local Kokoro voice (ONNX, runs on the CPU, nothing leaves the PC).

Text is split into short chunks (speech_text.chunks). A producer thread synthesizes them
ahead of playback; a sounddevice output stream plays them back to back. The first chunk is
kept short so the first words start well under a second after the hotkey.

Speed changes apply from the next chunk (about a sentence): queued audio is dropped and
re-synthesized at the new speed. Pause keeps the stream open and plays silence.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from pathlib import Path
from typing import Callable

import numpy as np

from .speech_text import Chunk, chunks

log = logging.getLogger(__name__)

SR = 24000
MODEL_REPO = "onnx-community/Kokoro-82M-v1.0-ONNX"
MODEL_FILE = "onnx/model_quantized.onnx"  # 92 MB; same clarity as fp32 in tests, ~1/3 the memory
VOICES = {
    "af_heart": "Heart (US, female)",
    "af_bella": "Bella (US, female)",
    "af_nicole": "Nicole (US, female, soft)",
    "am_michael": "Michael (US, male)",
    "am_fenrir": "Fenrir (US, male)",
    "am_puck": "Puck (US, male)",
    "bf_emma": "Emma (UK, female)",
    "bm_george": "George (UK, male)",
}
DEFAULT_VOICE = "af_heart"
SPEED_MIN, SPEED_MAX = 0.8, 2.0  # Kokoro accepts 0.5-2.0
AHEAD_S = 20.0  # how much audio to synthesize ahead of playback
KEEPALIVE_S = 600  # tiny synthesis every 10 min while idle, so the model stays warm in memory


def _wasapi_default_output():
    """WASAPI entry for Windows' current default speakers: ~0.1 s less latency than MME.

    Returns (None, None) if it can't be matched (e.g. a headset plugged in after Yappr started
    isn't in PortAudio's device list yet); MME's sound mapper always follows the default device.
    """
    try:
        import sounddevice as sd

        from .meeting import default_devices_signature

        name = default_devices_signature()[0]
        if not name:
            return None, None
        api = next(i for i, a in enumerate(sd.query_hostapis()) if "WASAPI" in a["name"])
        outs = [(i, d["name"]) for i, d in enumerate(sd.query_devices())
                if d["hostapi"] == api and d["max_output_channels"] > 0]
        exact = [i for i, n in outs if n == name]
        prefix = [i for i, n in outs if n.startswith(name[:31])]  # winmm truncates names to 31 chars
        match = exact if len(exact) == 1 else prefix if len(prefix) == 1 and not exact else []
        if match:
            return match[0], sd.WasapiSettings(auto_convert=True)
    except Exception:
        log.debug("no WASAPI default output", exc_info=True)
    return None, None


_audio_exec = None
_audio_exec_lock = threading.Lock()


def _audio_thread():
    """One long-lived thread opens, starts, stops and closes every output stream.

    WASAPI needs COM on the thread that opens a stream; doing it here keeps COM off the Tk thread
    ("Hear sample") and other callers, and serializing open/start/stop removes start-vs-stop races.
    """
    global _audio_exec
    with _audio_exec_lock:
        if _audio_exec is None:
            from concurrent.futures import ThreadPoolExecutor

            _audio_exec = ThreadPoolExecutor(1, thread_name_prefix="tts-audio", initializer=_com_init)
        return _audio_exec


def _on_audio_thread() -> bool:
    return threading.current_thread().name.startswith("tts-audio")


def _com_init() -> None:
    try:
        import ctypes

        ctypes.windll.ole32.CoInitializeEx(None, 0)  # COINIT_MULTITHREADED; harmless if already set
    except Exception:
        pass


def clamp_speed(v: float) -> float:
    return round(min(SPEED_MAX, max(SPEED_MIN, float(v))), 2)


def _download(filename: str) -> str:
    from huggingface_hub import hf_hub_download

    try:
        return hf_hub_download(MODEL_REPO, filename, local_files_only=True)
    except Exception:
        return hf_hub_download(MODEL_REPO, filename)


class Cancelled(Exception):
    pass


class _CancellableSession:
    """Wraps the onnxruntime session so an in-flight synthesis can be stopped (RunOptions.terminate)."""

    def __init__(self, sess, voice: "Voice"):
        self._sess = sess
        self._voice = voice

    def run(self, output_names, feeds, run_options=None):
        return self._sess.run(output_names, feeds, self._voice._run_options)

    def __getattr__(self, name):
        return getattr(self._sess, name)


class Voice:
    """The Kokoro model: loads once, synthesizes one chunk at a time (thread-safe)."""

    def __init__(self, cache_dir: Path, threads: int = 6):
        self.cache_dir = Path(cache_dir)
        self.threads = threads
        self._k = None
        self._styles: dict[str, np.ndarray] = {}
        self._lock = threading.Lock()  # one synthesis at a time
        self._run_options = None
        self._cancel_lock = threading.Lock()
        self._cancel_seq = 0
        self._load_lock = threading.Lock()
        self.last_used = 0.0

    @property
    def loaded(self) -> bool:
        return self._k is not None

    def ensure_loaded(self) -> None:
        with self._load_lock:
            if self._k is not None:
                return
            t = time.monotonic()
            import onnxruntime as rt
            from kokoro_onnx import Kokoro

            for v in VOICES:
                self._styles[v] = np.fromfile(_download(f"voices/{v}.bin"), dtype=np.float32).reshape(-1, 1, 256)
            # kokoro-onnx wants an .npz of voices; build it once next to the settings
            npz = self.cache_dir / "tts_voices.npz"
            if not npz.exists():
                self.cache_dir.mkdir(parents=True, exist_ok=True)
                tmp = npz.with_name("tts_voices.tmp.npz")
                np.savez(tmp, **self._styles)
                tmp.replace(npz)
            so = rt.SessionOptions()
            so.intra_op_num_threads = self.threads
            # memory arena stays on: without it every new chunk length re-allocates and synthesis is ~2x slower
            sess = rt.InferenceSession(_download(MODEL_FILE), so, providers=["CPUExecutionProvider"])
            k = Kokoro.from_session(sess, str(npz))
            k.sess = _CancellableSession(sess, self)
            self._rt = rt
            k.create("Ready.", voice=self._styles[DEFAULT_VOICE], speed=1.0)  # warm-up
            self._k = k
            self.last_used = time.monotonic()
            log.info("voice model loaded in %.1fs", time.monotonic() - t)

    def preload_async(self) -> None:
        threading.Thread(target=self._safe_load, name="tts-load", daemon=True).start()

    def _safe_load(self) -> None:
        try:
            self.ensure_loaded()
        except Exception:
            log.exception("voice model load failed")

    def synth(self, text: str, voice: str, speed: float) -> np.ndarray:
        seq = self._cancel_seq  # a cancel() from now on applies to this call, even before it runs
        self.ensure_loaded()
        style = self._styles.get(voice) if voice in self._styles else self._styles[DEFAULT_VOICE]
        with self._lock:
            with self._cancel_lock:
                if self._cancel_seq != seq:
                    raise Cancelled()
                self._run_options = self._rt.RunOptions()
            try:
                audio, _ = self._k.create(text, voice=style, speed=clamp_speed(speed))
            except Exception as e:
                if self._run_options.terminate:
                    raise Cancelled() from e
                raise
            finally:
                self.last_used = time.monotonic()
        return np.asarray(audio, dtype=np.float32)

    def cancel(self) -> None:
        """Stop the synthesis that is running right now (if any); it raises Cancelled."""
        with self._cancel_lock:
            self._cancel_seq += 1
            if self._run_options is not None:
                self._run_options.terminate = True

    def keepalive(self) -> None:
        if self._k is not None and time.monotonic() - self.last_used > KEEPALIVE_S:
            self.synth("Hi.", DEFAULT_VOICE, 1.0)


class Reader:
    """Plays text aloud. All public methods are safe to call from any thread."""

    def __init__(self, voice: Voice, get_voice: Callable[[], str], get_speed: Callable[[], float],
                 on_done: Callable[[], None] | None = None, output=None,
                 on_error: Callable[[str], None] | None = None, busy: Callable[[], bool] | None = None):
        self.voice = voice
        self.on_error = on_error
        self.busy = busy or (lambda: False)
        self.get_voice = get_voice
        self.get_speed = get_speed
        self.on_done = on_done
        self._output = output  # test hook: replaces the sounddevice stream
        self._cv = threading.Condition()
        self._gen = 0
        self._epoch = 0
        self._chunks: list[Chunk] = []
        self._next = 0  # next chunk index to synthesize
        self._playing = -1  # chunk index currently playing
        self._queue: deque = deque()  # (idx, audio) synthesized, not yet playing
        self._cur: np.ndarray | None = None
        self._pos = 0
        self._produced_all = False
        self._paused = False
        self._active = False
        self._starved = False
        self._stream = None
        self.speed = clamp_speed(get_speed())
        self.stats: dict = {}
        threading.Thread(target=self._keepalive_loop, name="tts-keepalive", daemon=True).start()

    # ---------------------------------------------------------------- public
    @property
    def active(self) -> bool:
        return self._active

    @property
    def paused(self) -> bool:
        return self._paused

    def speak(self, text: str, t0: float | None = None) -> bool:
        """Start reading `text` (already cleaned). Stops anything currently being read."""
        cs = chunks(text)
        if not cs:
            return False
        self.stop()
        t0 = time.monotonic() if t0 is None else t0
        with self._cv:
            self._gen += 1
            gen = self._gen
            self._chunks = cs
            self._next, self._playing = 0, -1
            self._queue.clear()
            self._cur, self._pos = None, 0
            self._produced_all = False
            self._paused = False
            self._starved = False
            self._active = True
            self.speed = clamp_speed(self.get_speed())
            self.stats = {"t0": t0, "chunks": len(cs), "chars": len(text), "first_audio_s": None,
                          "underruns": 0, "underrun_s": 0.0, "first_synth_s": None}
        threading.Thread(target=self._produce, args=(gen,), name="tts-produce", daemon=True).start()
        try:
            self._open_stream(gen)
        except Exception:
            log.exception("could not open the audio output")
            self.stop()
            self._error("Couldn't play sound — check your speakers")
            return False
        return True

    def _error(self, msg: str) -> None:
        if self.on_error:
            try:
                self.on_error(msg)
            except Exception:
                log.exception("on_error")

    def stop(self) -> None:
        with self._cv:
            was = self._active
            self._gen += 1
            self._active = False
            self._paused = False
            self._queue.clear()
            self._cur = None
            self._cv.notify_all()
            stream, self._stream = self._stream, None
        self._cancel_synth()
        if stream is not None:
            if self._output is not None or _on_audio_thread():
                self._close(stream)
            else:
                try:
                    _audio_thread().submit(self._close, stream).result(5)
                except Exception:
                    log.exception("closing audio stream")
        if was:
            self._log_stats("stopped")

    @staticmethod
    def _close(stream) -> None:
        try:
            stream.abort()
            stream.close()
        except Exception:
            log.exception("closing audio stream")

    def toggle_pause(self) -> bool:
        """Returns True if now paused."""
        with self._cv:
            if not self._active:
                return False
            self._paused = not self._paused
            return self._paused

    def set_speed(self, speed: float) -> None:
        """New speed from the next chunk on; already-synthesized audio is redone at the new speed."""
        speed = clamp_speed(speed)
        with self._cv:
            if speed == self.speed:
                return
            self.speed = speed
            if not self._active:
                return
            self._epoch += 1
            self._queue.clear()
            self._next = self._playing + 1
            self._produced_all = False
            self._cv.notify_all()
        self._cancel_synth()

    def _cancel_synth(self) -> None:
        cancel = getattr(self.voice, "cancel", None)
        if cancel:
            cancel()

    # ---------------------------------------------------------------- producer
    def _ahead_s(self) -> float:
        n = sum(len(a) for _, a in self._queue)
        if self._cur is not None:
            n += len(self._cur) - self._pos
        return n / SR

    def _produce(self, gen: int) -> None:
        voice = self.get_voice()
        while True:
            with self._cv:
                while self._gen == gen and (self._next >= len(self._chunks) or self._ahead_s() > AHEAD_S):
                    if self._next >= len(self._chunks):
                        self._produced_all = True
                    self._cv.wait(0.5)
                if self._gen != gen:
                    return
                idx, epoch, speed = self._next, self._epoch, self.speed
                self._next += 1
                ch = self._chunks[idx]
            t = time.monotonic()
            try:
                audio = self.voice.synth(ch.text, voice, speed)
            except Cancelled:
                with self._cv:  # a cancel aimed at an older read/speed can land on this chunk: redo it
                    if self._gen == gen and self._epoch == epoch and self._next == idx + 1:
                        self._next = idx
                continue
            except Exception:
                log.exception("synthesis failed for chunk %d", idx)
                if not getattr(self.voice, "loaded", True):  # model missing/corrupt: don't sit there silent
                    with self._cv:
                        mine = self._gen == gen
                    if mine:
                        threading.Thread(target=self.stop, daemon=True).start()
                        self._error("Couldn't load the voice — see the log")
                    return
                audio = np.zeros(0, np.float32)
            pad = np.zeros(int(SR * ch.pause / max(speed, 0.5)), np.float32)
            audio = np.concatenate([audio, pad])
            with self._cv:
                if self._gen != gen:
                    return
                if self._epoch != epoch:
                    continue  # speed changed while synthesizing: _next was rewound, redo it
                if self.stats.get("first_synth_s") is None:
                    self.stats["first_synth_s"] = round(time.monotonic() - t, 3)
                self._queue.append((idx, audio))
                if self._next >= len(self._chunks):
                    self._produced_all = True  # so playback can end right after the last chunk
                self._cv.notify_all()

    # ---------------------------------------------------------------- playback
    def _open_stream(self, gen: int) -> None:
        if self._output is not None:
            self._stream = self._output(self._callback, lambda: self._finished(gen))
            return
        _audio_thread().submit(self._open_stream_now, gen).result(10)

    def _open_stream_now(self, gen: int) -> None:
        """Runs on the audio thread. WASAPI on the default speakers, else MME."""
        import sounddevice as sd

        kw = dict(samplerate=SR, channels=1, dtype="float32", latency="low",
                  callback=self._callback, finished_callback=lambda: self._finished(gen))
        dev, extra = _wasapi_default_output()
        options = ([dict(device=dev, extra_settings=extra)] if dev is not None else []) + [{}]  # WASAPI, then MME
        last = None
        for opt in options:
            with self._cv:
                if self._gen != gen:
                    return  # stopped meanwhile: don't open anything
            stream = None
            try:
                stream = sd.OutputStream(**opt, **kw)
                stream.start()
            except Exception as e:
                last = e
                log.warning("audio output %s failed: %s", "WASAPI" if opt else "MME", e)
                if stream is not None:
                    stream.close()
                continue
            with self._cv:
                if self._gen == gen:
                    self._stream = stream
                    return
            self._close(stream)  # stopped while starting (stop() found no stream to close)
            return
        raise last

    def fill(self, out: np.ndarray) -> bool:
        """Fill `out` (1-D float32) with the next samples. Returns False once everything has played."""
        n, w = len(out), 0
        with self._cv:
            if self._paused or not self._active:
                out[:] = 0
                return self._active
            while w < n:
                if self._cur is None or self._pos >= len(self._cur):
                    if not self._queue:
                        break
                    idx, self._cur = self._queue.popleft()
                    self._pos, self._playing = 0, idx
                    self._cv.notify_all()
                take = min(n - w, len(self._cur) - self._pos)
                out[w:w + take] = self._cur[self._pos:self._pos + take]
                self._pos += take
                w += take
            if w and self.stats.get("first_audio_s") is None:
                self.stats["first_audio_s"] = round(time.monotonic() - self.stats["t0"], 3)
            if w < n:
                out[w:] = 0
                if self._produced_all and not self._queue and self._next >= len(self._chunks):
                    return False
                if self.stats.get("first_audio_s") is not None:  # a gap in the middle of reading
                    if not self._starved:
                        self.stats["underruns"] += 1
                    self._starved = True
                    self.stats["underrun_s"] += (n - w) / SR
            else:
                self._starved = False
            return True

    def _callback(self, outdata, frames, time_info, status) -> None:
        if status and getattr(status, "output_underflow", False):
            self.stats["device_underflows"] = self.stats.get("device_underflows", 0) + 1
        buf = np.zeros(frames, np.float32)
        more = self.fill(buf)
        outdata[:, 0] = buf
        if not more:
            import sounddevice as sd

            raise sd.CallbackStop

    def _finished(self, gen: int) -> None:
        with self._cv:
            if self._gen != gen:
                return
            self._active = False
            stream, self._stream = self._stream, None
        if stream is not None:  # can't close from inside PortAudio's own callback thread
            _audio_thread().submit(stream.close)
        self._log_stats("finished")
        if self.on_done:
            try:
                self.on_done()
            except Exception:
                log.exception("on_done")

    def _log_stats(self, how: str) -> None:
        s = dict(self.stats)
        if s:
            log.info("read %s at %.1fx: %d chars, %d chunks, first audio %.3fs (first synth %ss), gaps %d (%.2fs), "
                     "device underflows %d", how, self.speed, s.get("chars", 0), s.get("chunks", 0),
                     s.get("first_audio_s") or -1, s.get("first_synth_s"), s.get("underruns", 0),
                     s.get("underrun_s", 0.0), s.get("device_underflows", 0))

    def _keepalive_loop(self) -> None:
        while True:
            time.sleep(60)
            try:
                if not self._active and not self.busy():
                    self.voice.keepalive()
            except Cancelled:
                pass
            except Exception:
                log.exception("voice keepalive")
