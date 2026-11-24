import threading
import time

import numpy as np

from yappr import tts


class FakeVoice:
    """Each chunk becomes 0.1 s of audio whose sample value encodes the chunk number."""

    def __init__(self, delay=0.0):
        self.calls = []
        self.delay = delay
        self.n = 0

    def synth(self, text, voice, speed):
        time.sleep(self.delay)
        self.calls.append((text, speed))
        self.n += 1
        return np.full(int(tts.SR * 0.1), float(len(self.calls)), np.float32)

    def keepalive(self):
        pass


class FakeStream:
    def __init__(self, cb, finished):
        self.finished = finished
        self.closed = False

    def abort(self):
        pass

    def close(self):
        self.closed = True


def make(voice, speed=1.0):
    st = {"speed": speed}
    done = threading.Event()
    r = tts.Reader(voice, lambda: "af_heart", lambda: st["speed"], on_done=done.set, output=FakeStream)
    return r, st, done


def pump(r, seconds, block=1200):
    """Pull `seconds` of audio through the reader; returns the samples and whether it is still going."""
    out, more = [], True
    for _ in range(int(seconds * tts.SR / block)):
        b = np.zeros(block, np.float32)
        more = r.fill(b)
        out.append(b)
        if not more:
            break
    return np.concatenate(out), more


def wait_for(cond, timeout=3.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.01)
    return False


TEXT = " ".join(f"This is sentence number {w} of the test." for w in
                ("one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"))
PIECES = [c.text for c in tts.chunks(TEXT)]
N = len(PIECES)


def test_reads_every_chunk_in_order_then_finishes():
    v = FakeVoice()
    r, _, _ = make(v)
    assert r.speak(TEXT)
    assert N >= 4
    assert wait_for(lambda: len(v.calls) == N and r._produced_all)
    audio, more = pump(r, 5)
    assert not more
    vals = [int(x) for x in dict.fromkeys(np.round(audio[audio > 0]))]
    assert vals == list(range(1, N + 1))
    assert [t for t, _ in v.calls] == PIECES
    assert r.stats["first_audio_s"] is not None


def test_pause_outputs_silence_and_resumes_where_it_was():
    v = FakeVoice()
    r, _, _ = make(v)
    r.speak(TEXT)
    assert wait_for(lambda: len(v.calls) == N)
    a1, _ = pump(r, 0.05)
    assert r.toggle_pause() is True
    silent, more = pump(r, 0.5)
    assert more and not silent.any()
    assert r.toggle_pause() is False
    a2, _ = pump(r, 0.05)
    assert a1[-1] == a2[0] == 1.0  # still in chunk 1


def test_speed_change_redoes_queued_chunks_at_new_speed():
    v = FakeVoice()
    r, st, _ = make(v, speed=1.0)
    r.speak(TEXT)
    assert wait_for(lambda: len(v.calls) == N)
    pump(r, 0.05)  # chunk 1 is playing
    st["speed"] = 1.5
    r.set_speed(1.5)
    assert wait_for(lambda: len(v.calls) == 2 * N - 1 and r._produced_all)
    assert [s for _, s in v.calls[N:]] == [1.5] * (N - 1)
    assert [t for t, _ in v.calls[N:]] == PIECES[1:]
    audio, more = pump(r, 10)
    assert not more
    # chunk 1 finishes at the old speed, then the re-synthesized chunks play (the old ones are dropped)
    assert [int(x) for x in dict.fromkeys(np.round(audio[audio > 0]))] == [1] + list(range(N + 1, 2 * N))


def test_stop_silences_and_stops_producing():
    v = FakeVoice(delay=0.05)
    r, _, _ = make(v)
    r.speak(TEXT * 5)
    assert wait_for(lambda: len(v.calls) >= 1)
    r.stop()
    n = len(v.calls)
    time.sleep(0.3)
    assert len(v.calls) <= n + 1  # at most the chunk that was mid-synthesis
    b = np.zeros(1200, np.float32)
    assert r.fill(b) is False and not b.any()
    assert not r.active


def test_speed_is_clamped():
    assert tts.clamp_speed(5) == tts.SPEED_MAX
    assert tts.clamp_speed(0.1) == tts.SPEED_MIN
    assert tts.SPEED_MIN <= 1.0 and tts.SPEED_MAX >= 2.0


def test_synthesis_stays_ahead_but_bounded():
    v = FakeVoice()
    r, _, _ = make(v)
    long = " ".join(f"Sentence number {i}." for i in range(3000))  # far more than 20 s of fake audio
    r.speak(long)
    time.sleep(0.5)
    assert len(v.calls) < len(tts.chunks(long))
    with r._cv:
        ahead = r._ahead_s()
    assert tts.AHEAD_S <= ahead < tts.AHEAD_S + 1  # synthesized ~20 s ahead, then waits
    r.stop()


class CancellableVoice(FakeVoice):
    """Synthesis takes `delay` seconds unless cancelled, like the real model with RunOptions.terminate."""

    def __init__(self, delay):
        super().__init__()
        self.delay = delay
        self.cancel_evt = threading.Event()
        self.lock = threading.Lock()

    def synth(self, text, voice, speed):
        with self.lock:
            self.cancel_evt.clear()
            if self.cancel_evt.wait(self.delay):
                raise tts.Cancelled()
            self.calls.append((text, speed))
            return np.full(int(tts.SR * 0.1), float(len(self.calls)), np.float32)

    def cancel(self):
        self.cancel_evt.set()


def test_stop_cancels_inflight_synthesis_so_next_read_starts_fast():
    v = CancellableVoice(delay=2.0)
    r, _, _ = make(v)
    r.speak(TEXT)
    time.sleep(0.1)  # first chunk is mid-synthesis (would take 2 s)
    t = time.monotonic()
    r.stop()
    v.delay = 0.05
    r.speak("A new short text to read now.")
    assert wait_for(lambda: len(v.calls) >= 1, timeout=1.0)
    assert time.monotonic() - t < 0.5
    assert v.calls[0][0] == "A new short text to read now."


def test_audio_device_failure_does_not_leave_reader_stuck():
    def broken(cb, fin):
        raise OSError("no default output device")
    errors = []
    r = tts.Reader(FakeVoice(), lambda: "af_heart", lambda: 1.0, output=broken, on_error=errors.append)
    assert r.speak(TEXT) is False
    assert not r.active and errors


def test_cancel_just_before_synthesis_starts_still_cancels():
    class V:
        loaded = True
        _cancel_seq = 0
    # Voice.synth captures the cancel sequence on entry; a cancel before it gets the model lock wins
    v = tts.Voice.__new__(tts.Voice)
    v._cancel_seq, v._cancel_lock, v._lock = 0, threading.Lock(), threading.Lock()
    v._run_options = None
    v._k = object()
    v._styles = {"af_heart": None}
    v._load_lock = threading.Lock()
    v.ensure_loaded = lambda: v.cancel()  # cancel lands after entry, before the run starts
    try:
        v.synth("Hello.", "af_heart", 1.0)
        raise AssertionError("expected Cancelled")
    except tts.Cancelled:
        pass


def test_falls_back_to_mme_when_wasapi_output_fails(monkeypatch):
    import sounddevice as sd

    opened = []

    class Stream:
        def __init__(self, device=None, extra_settings=None, **kw):
            self.device = device
            opened.append(device)

        def start(self):
            if self.device is not None:
                raise sd.PortAudioError("WASAPI start failed")

        def abort(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(sd, "OutputStream", Stream)
    monkeypatch.setattr(tts, "_wasapi_default_output", lambda: (11, None))
    r = tts.Reader(FakeVoice(), lambda: "af_heart", lambda: 1.0)
    assert r.speak(TEXT) is True
    assert opened == [11, None] and r.active
    r.stop()
