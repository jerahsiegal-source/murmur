"""Microphone capture for dictation.

The mic stream is opened only while dictating (Windows shows the mic-in-use icon only then).
Audio stays in memory as 16 kHz mono float32 and never touches disk or the network.

While recording, completed phrases (split at pauses) are handed to `on_segment` so they can be
transcribed before the user stops talking; at stop, only the tail is left.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Callable

import numpy as np

log = logging.getLogger(__name__)

SR = 16000
BLOCK = 1600  # 100 ms


def rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(x)))) if len(x) else 0.0


def find_cut(audio: np.ndarray, min_len: int, search_s: float = 2.5, min_pause_s: float = 0.6,
             silence: float | None = None) -> int | None:
    """Return a sample index in the middle of a real pause near the end of `audio`, or None.

    Only cuts after `min_len` samples. Looks for runs of quiet 50 ms windows lasting at least
    `min_pause_s` in the last `search_s` seconds, picks the longest, and cuts in its middle, so
    segments end where the speaker actually paused (usually a sentence break).
    """
    n = len(audio)
    hop = SR // 20
    if n < min_len + hop:
        return None
    start = max(min_len - int(min_pause_s * SR) // 2, n - int(search_s * SR))
    levels = [(rms(audio[i : i + hop]), i) for i in range(start, n - hop + 1, hop)]
    if not levels:
        return None
    loud = float(np.percentile(np.abs(audio[::4]), 95)) if silence is None else 0.0
    threshold = silence if silence is not None else max(0.004, 0.12 * loud)
    best, run = None, []
    for lv, i in levels + [(1e9, n)]:
        if lv <= threshold:
            run.append(i)
            continue
        if run and (len(run) * hop >= min_pause_s * SR) and (best is None or len(run) > len(best)):
            best = run
        run = []
    if best is None:
        return None
    cut = (best[0] + best[-1] + hop) // 2
    return cut if cut >= min_len // 2 else None


def trim_silence(audio: np.ndarray, pad_s: float = 0.25) -> np.ndarray:
    """Drop leading/trailing silence (speech models tend to invent words like "Yeah." in it)."""
    hop = SR // 20
    if len(audio) < hop:
        return audio[:0]
    n = len(audio) // hop
    lv = np.sqrt(np.mean(np.square(audio[: n * hop].reshape(n, hop)), axis=1))
    loud = float(np.percentile(np.abs(audio[::4]), 95))
    if loud < 0.01:
        return audio[:0]  # nothing above a whisper
    voiced = np.nonzero(lv > max(0.004, 0.1 * loud))[0]
    if len(voiced) == 0:
        return audio[:0]
    pad = int(pad_s * SR)
    return audio[max(0, voiced[0] * hop - pad) : min(len(audio), (voiced[-1] + 1) * hop + pad)]


class MicRecorder:
    """Records one dictation at a time."""

    def __init__(
        self,
        on_level: Callable[[float], None] | None = None,
        on_segment: Callable[[np.ndarray], None] | None = None,
        device: str | int | None = None,
        segment_min_s: float = 10.0,
    ):
        self.on_level = on_level or (lambda _l: None)
        self.on_segment = on_segment or (lambda _a: None)
        self.device = device or None
        self.segment_min = int(segment_min_s * SR)
        self._n = 0  # samples recorded
        self._all: list[np.ndarray] = []  # whole dictation (a few MB per minute)
        self._pending = np.zeros(0, np.float32)  # audio not yet handed to on_segment
        self._lock = threading.Lock()
        self._stream = None
        self._fake_thread: threading.Thread | None = None
        self._running = False
        self.started_at = 0.0

    # ---- public
    def start(self) -> None:
        with self._lock:
            self._n, self._pending, self._all = 0, np.zeros(0, np.float32), []
        self._running = True
        self.started_at = time.monotonic()
        fake = os.environ.get("MURMUR_FAKE_MIC")
        if fake:
            self._fake_thread = threading.Thread(target=self._fake_feed, args=(fake,), daemon=True)
            self._fake_thread.start()
            return
        import sounddevice as sd

        self._stream = sd.InputStream(
            samplerate=SR, channels=1, dtype="float32", blocksize=BLOCK, device=self.device, callback=self._callback
        )
        self._stream.start()

    def stop(self) -> np.ndarray:
        """Stop and return the audio not yet handed off as a segment."""
        self._running = False
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            finally:
                self._stream = None
        if self._fake_thread is not None:
            self._fake_thread.join(timeout=2)
            self._fake_thread = None
        with self._lock:
            tail, self._pending = self._pending, np.zeros(0, np.float32)
        self.on_level(0.0)
        return tail

    def full_audio(self) -> np.ndarray:
        with self._lock:
            return np.concatenate(self._all) if self._all else np.zeros(0, np.float32)

    def duration(self) -> float:
        with self._lock:
            return self._n / SR

    # ---- internals
    def _callback(self, indata, frames, t, status) -> None:  # sounddevice thread
        self._push(indata[:, 0].copy())

    def _push(self, block: np.ndarray) -> None:
        if not self._running:
            return
        self.on_level(rms(block))
        seg = None
        with self._lock:
            self._n += len(block)
            self._all.append(block)
            self._pending = np.concatenate([self._pending, block])
            if len(self._pending) >= self.segment_min:
                cut = find_cut(self._pending, self.segment_min)
                if cut is None and len(self._pending) > 4 * self.segment_min:
                    cut = len(self._pending)  # very long breathless run: cut anyway
                if cut is not None:
                    seg, self._pending = self._pending[:cut], self._pending[cut:]
        if seg is not None:
            self.on_segment(seg)

    def _fake_feed(self, path: str) -> None:
        """Test hook: play a WAV file in real time as if it were the microphone."""
        import soundfile as sf

        audio, sr = sf.read(path, dtype="float32")
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        if sr != SR:
            raise ValueError("fake mic file must be 16 kHz")
        t0 = time.monotonic()
        for i in range(0, len(audio), BLOCK):
            if not self._running:
                return
            self._push(audio[i : i + BLOCK])
            delay = t0 + (i + BLOCK) / SR - time.monotonic()
            if delay > 0:
                time.sleep(delay)
        while self._running:  # silence after the file ends
            self._push(np.zeros(BLOCK, np.float32))
            time.sleep(BLOCK / SR)
