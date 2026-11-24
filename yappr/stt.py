"""Local speech-to-text (Parakeet via onnx-asr). Audio never leaves the machine.

The model is loaded on demand and unloaded after an idle period so the app stays small
in the background.
"""
from __future__ import annotations

import gc
import re
import logging
import threading
import time

import numpy as np

log = logging.getLogger(__name__)
SR = 16000


def fix_spacing(text: str) -> str:
    """Small model quirks: 'on$42' -> 'on $42'."""
    return re.sub(r"(?<=[A-Za-z])(?=[$€£])", " ", text).strip()


class Transcriber:
    def __init__(self, model: str, quantization: str = "int8", threads: int = 4, idle_unload_min: float = 10.0):
        self.model_name = model
        self.quantization = quantization or None
        self.threads = threads
        self.idle_unload_s = idle_unload_min * 60
        self._model = None
        self._vad_model = None
        self._load_lock = threading.Lock()
        self._run_lock = threading.Lock()
        self._last_used = time.monotonic()
        self._users = 0  # long-running users (meetings) pin the model
        threading.Thread(target=self._idle_watch, name="stt-idle", daemon=True).start()

    # ---- lifecycle
    def _session_options(self):
        import onnxruntime as ort

        so = ort.SessionOptions()
        so.enable_cpu_mem_arena = False  # keeps RSS ~40% lower, same speed
        so.intra_op_num_threads = self.threads
        # don't busy-wait between operations: same speed, far less CPU stolen from other apps
        so.add_session_config_entry("session.intra_op.allow_spinning", "0")
        so.log_severity_level = 3
        return so

    def ensure_loaded(self):
        with self._load_lock:
            if self._model is None:
                import onnx_asr

                t = time.monotonic()
                kw = {"quantization": self.quantization} if self.quantization else {}
                self._model = onnx_asr.load_model(self.model_name, sess_options=self._session_options(), **kw)
                # warm-up: the first inference is ~2x slower
                self._model.recognize(np.zeros(SR // 2, np.float32), sample_rate=SR)
                log.info("STT model loaded in %.1fs", time.monotonic() - t)
            self._last_used = time.monotonic()
            return self._model

    def preload_async(self) -> None:
        threading.Thread(target=self.ensure_loaded, name="stt-preload", daemon=True).start()

    def loaded(self) -> bool:
        return self._model is not None

    def pin(self) -> None:
        self._users += 1

    def unpin(self) -> None:
        self._users = max(0, self._users - 1)
        self._last_used = time.monotonic()

    def unload(self) -> None:
        with self._load_lock, self._run_lock:
            self._model = None
            self._vad_model = None
        gc.collect()
        log.info("STT model unloaded (idle)")

    def _idle_watch(self) -> None:
        while True:
            time.sleep(15)
            if (
                self._model is not None
                and self.idle_unload_s > 0
                and self._users == 0
                and time.monotonic() - self._last_used > self.idle_unload_s
            ):
                self.unload()

    # ---- inference
    def transcribe(self, audio: np.ndarray) -> str:
        from .audio import trim_silence

        audio = trim_silence(audio)
        if len(audio) < SR * 0.25:
            return ""
        model = self.ensure_loaded()
        with self._run_lock:
            text = model.recognize(audio.astype(np.float32, copy=False), sample_rate=SR)
        self._last_used = time.monotonic()
        return fix_spacing(text or "")

    def transcribe_segments(self, audio: np.ndarray) -> list[tuple[float, float, str]]:
        """Long audio -> [(start_s, end_s, text)] using Silero VAD to split speech."""
        if len(audio) < SR * 0.25:
            return []
        model = self.ensure_loaded()
        with self._load_lock:
            if self._vad_model is None:
                import onnx_asr

                import onnxruntime as ort

                vso = ort.SessionOptions()
                vso.enable_cpu_mem_arena = False
                vso.intra_op_num_threads = 1
                vad = onnx_asr.load_vad("silero", sess_options=vso)
                # batch_size=1: measured ~30% faster than the default on a 5-min chunk, same memory,
                # and lets a dictation slip in between segments
                self._vad_model = model.with_vad(vad, max_speech_duration_s=25, min_silence_duration_ms=500,
                                                 batch_size=1)
            vm = self._vad_model
        out = []
        gen = iter(vm.recognize(audio.astype(np.float32, copy=False), sample_rate=SR))
        while True:
            # take the lock per segment, so a dictation can slip in between meeting segments
            with self._run_lock:
                try:
                    seg = next(gen)
                except StopIteration:
                    break
            txt = fix_spacing(seg.text or "")
            if txt:
                out.append((float(seg.start), float(seg.end), txt))
        self._last_used = time.monotonic()
        return out


class background_priority:
    """Context manager: run heavy background work (meeting transcription) politely.

    Lowers the process priority, so the apps you're using during the meeting get the CPU first.
    The keyboard hook lives in a separate process, so hotkeys are unaffected.
    """

    _depth = 0
    _lock = threading.Lock()

    def __enter__(self):
        with self._lock:
            type(self)._depth += 1
            if type(self)._depth == 1:
                _set_background(True)
        return self

    def __exit__(self, *exc):
        with self._lock:
            type(self)._depth -= 1
            if type(self)._depth == 0:
                _set_background(False)


def _set_background(on: bool) -> None:
    """Below-normal priority: other apps get the CPU first; when the PC is idle it costs nothing.

    (Windows "efficiency mode" / EcoQoS was tried and removed: it pinned the work to slow cores and
    made a 5-minute meeting chunk take ~58 s instead of ~8 s, so notes arrived minutes late.)
    """
    try:
        import ctypes
        from ctypes import wintypes

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.GetCurrentProcess.restype = wintypes.HANDLE
        k32.SetPriorityClass.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        k32.SetPriorityClass.restype = wintypes.BOOL
        BELOW_NORMAL, NORMAL = 0x4000, 0x20
        if not k32.SetPriorityClass(k32.GetCurrentProcess(), BELOW_NORMAL if on else NORMAL):
            log.warning("SetPriorityClass failed: %s", ctypes.get_last_error())
    except Exception:
        log.warning("could not change process priority", exc_info=True)
