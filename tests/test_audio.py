import numpy as np

from yappr.audio import SR, find_cut


def tone(sec, amp=0.3):
    t = np.arange(int(sec * SR)) / SR
    return (amp * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


def silence(sec):
    return np.zeros(int(sec * SR), np.float32)


def test_cuts_in_middle_of_real_pause():
    a = np.concatenate([tone(11), silence(0.8), tone(1.0)])
    cut = find_cut(a, 10 * SR)
    assert cut is not None
    assert 11 * SR < cut < 11.8 * SR


def test_short_gap_is_not_a_pause():
    a = np.concatenate([tone(11), silence(0.2), tone(1.0)])
    assert find_cut(a, 10 * SR) is None


def test_no_cut_before_min_len():
    a = np.concatenate([tone(3), silence(1.0), tone(1.0)])
    assert find_cut(a, 10 * SR) is None


def test_prefers_longest_pause():
    a = np.concatenate([tone(10.5), silence(0.5), tone(0.5), silence(1.0), tone(0.3)])
    cut = find_cut(a, 10 * SR)
    assert 11.5 * SR < cut < 12.5 * SR


def test_trim_silence_keeps_speech_drops_edges():
    from yappr.audio import trim_silence

    a = np.concatenate([silence(2), tone(1), silence(3)])
    t = trim_silence(a)
    assert 1.0 * SR <= len(t) <= 1.6 * SR


def test_trim_silence_all_quiet_returns_empty():
    from yappr.audio import trim_silence

    assert len(trim_silence(silence(2) + 0.001)) == 0
