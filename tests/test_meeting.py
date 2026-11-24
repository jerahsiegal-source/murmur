import numpy as np

from murmur.meeting import Resampler, Track, merge_segments, SR


def test_echo_of_speakers_dropped_from_mic():
    others = [(10.0, 13.0, "we will ship the pilot in Denver next week")]
    me = [(10.2, 13.1, "we will ship the pilot in denver next week"), (20.0, 21.0, "sounds good")]
    rows = merge_segments(me, others)
    assert [(w, t) for _, w, t in rows] == [("Others", "we will ship the pilot in Denver next week"), ("Me", "sounds good")]


def test_same_speaker_segments_joined():
    me = [(0.0, 2.0, "Okay, let's get started."), (2.5, 5.0, "Thanks for coming."), (9.0, 10.0, "Next.")]
    rows = merge_segments(me, [])
    assert rows == [(0.0, "Me", "Okay, let's get started. Thanks for coming."), (9.0, "Me", "Next.")]


def test_speaker_change_breaks_paragraph():
    rows = merge_segments([(0, 2, "a"), (4, 5, "c")], [(2.2, 3.8, "b")])
    assert [w for _, w, _ in rows] == ["Me", "Others", "Me"]


def test_resampler_48k_to_16k_length_and_tone():
    rs = Resampler(48000)
    t = np.arange(48000 * 2) / 48000
    x = np.sin(2 * np.pi * 440 * t).astype(np.float32)
    out = np.concatenate([rs.process(x[i:i + 4800]) for i in range(0, len(x), 4800)])
    assert abs(len(out) - 32000) <= 2
    spec = np.abs(np.fft.rfft(out[1000:17000]))
    assert abs(np.argmax(spec) * SR / 16000 - 440) < 3


def test_resampler_44k1():
    rs = Resampler(44100)
    out = np.concatenate([rs.process(np.zeros(4410, np.float32)) for _ in range(30)])
    assert abs(len(out) - 48000) <= 2


def test_track_rotates_chunks_and_pads(tmp_path):
    import soundfile as sf

    tr = Track(tmp_path, "mic", chunk_s=1)
    tr.write(np.ones(int(1.5 * SR), np.float32) * 0.1)
    tr.pad_to(int(2.2 * SR))
    tr.close()
    lens = [sf.info(tr.path(i)).frames for i in range(3)]
    assert lens == [SR, SR, int(0.2 * SR)]


def test_fix_spacing():
    from murmur.stt import fix_spacing

    assert fix_spacing(" we agreed on$42,000 ") == "we agreed on $42,000"


def test_full_chunk_is_closed_and_readable_immediately(tmp_path):
    """Regression: a full chunk must be finalized before it is reported finished (90-min run bug)."""
    import soundfile as sf

    tr = Track(tmp_path, "sys", chunk_s=1)
    tr.write(np.full(SR, 0.1, np.float32))  # exactly one chunk, no further writes yet
    assert tr.finished == 1
    a, _ = sf.read(tr.path(0), dtype="float32")
    assert len(a) == SR
    tr.write(np.full(SR // 2, 0.1, np.float32))
    assert tr.finished == 1
    tr.close()
    assert tr.finished == 2
