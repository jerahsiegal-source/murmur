import json

import numpy as np
import soundfile as sf

from yappr.meeting import recover_unfinished, unfinished_meetings
from yappr.storage import new_meeting_dir


class FakeTranscriber:
    def __init__(self):
        self.pins = 0

    def pin(self):
        self.pins += 1

    def unpin(self):
        self.pins -= 1

    def transcribe_segments(self, audio):
        return [(1.0, 2.0, "hello from akifer")] if np.max(np.abs(audio), initial=0) > 0.01 else []


def test_interrupted_call_is_finished_and_its_audio_deleted(tmp_path):
    d = new_meeting_dir(tmp_path, "Client call")
    (d / "transcript.md").write_text("# Client call\n\nMonday\n\n[0:00:01] **Me:** first part\n\n", encoding="utf-8")
    (d / "state.json").write_text(json.dumps({"finished": False, "chunk_s": 300}))
    audio = d / "audio"
    audio.mkdir()
    sf.write(audio / "mic_0001.flac", np.full(16000, 0.2, np.float32), 16000)
    sf.write(audio / "sys_0001.flac", np.zeros(16000, np.float32), 16000)
    (audio / "sys_0002.flac").write_bytes(b"truncated by a crash")  # unreadable piece must not stop recovery
    other = new_meeting_dir(tmp_path, "Done call")
    (other / "state.json").write_text(json.dumps({"finished": True}))
    assert unfinished_meetings(tmp_path) == [d]

    tr = FakeTranscriber()
    done = recover_unfinished(tmp_path, tr, None, None, lambda: [{"word": "Okafor", "sounds_like": ["akifer"]}])

    assert done == [d] and tr.pins == 0
    text = (d / "transcript.md").read_text(encoding="utf-8")
    assert "first part" in text and "recovered after Yappr was closed" in text
    assert "[0:05:01] **Me:** hello from Okafor" in text
    assert not audio.exists()
    assert json.loads((d / "state.json").read_text())["finished"] is True
    assert (d / "summary.md").exists()
    assert unfinished_meetings(tmp_path) == []


def test_active_meeting_is_not_recovered(tmp_path):
    d = new_meeting_dir(tmp_path, "Live")
    (d / "state.json").write_text(json.dumps({"finished": False}))
    assert recover_unfinished(tmp_path, FakeTranscriber(), None, None, lambda: [], active=lambda: d) == []


def test_piece_transcribed_before_crash_is_not_duplicated(tmp_path):
    d = new_meeting_dir(tmp_path, "Crash after append")
    (d / "transcript.md").write_text("# t\n\nx\n\n", encoding="utf-8")
    (d / "state.json").write_text(json.dumps({"finished": False, "chunk_s": 300, "chunks_done": 1}))
    audio = d / "audio"
    audio.mkdir()
    sf.write(audio / "mic_0000.flac", np.full(16000, 0.2, np.float32), 16000)  # already in transcript
    sf.write(audio / "mic_0001.flac", np.full(16000, 0.2, np.float32), 16000)
    recover_unfinished(tmp_path, FakeTranscriber(), None, None, lambda: [])
    text = (d / "transcript.md").read_text(encoding="utf-8")
    assert text.count("hello from akifer") == 1 and "[0:05:01]" in text and not audio.exists()


def test_one_broken_folder_does_not_block_the_others(tmp_path):
    class Boom(FakeTranscriber):
        def transcribe_segments(self, audio):
            raise RuntimeError("engine failed")

    bad = new_meeting_dir(tmp_path, "A bad")
    good = new_meeting_dir(tmp_path, "B good")
    for d in (bad, good):
        (d / "transcript.md").write_text("# t\n\nx\n\n", encoding="utf-8")
        (d / "state.json").write_text(json.dumps({"finished": False}))
    (bad / "audio").mkdir()
    sf.write(bad / "audio" / "mic_0000.flac", np.full(16000, 0.2, np.float32), 16000)
    tr = Boom()
    done = recover_unfinished(tmp_path, tr, None, None, lambda: [])
    assert done == [good] and tr.pins == 0
    assert (bad / "audio" / "mic_0000.flac").exists()  # kept for the next try


def test_failed_piece_is_retried_not_deleted_after_a_crash(tmp_path):
    """Review F25: chunk 0 failed, chunk 1 succeeded, then the app crashed mid-call."""
    d = new_meeting_dir(tmp_path, "Failed then crash")
    (d / "transcript.md").write_text("# t\n\nx\n\n", encoding="utf-8")
    (d / "state.json").write_text(json.dumps({"finished": False, "chunk_s": 300, "chunks_done": 2, "failed_chunks": [0]}))
    audio = d / "audio"
    audio.mkdir()
    sf.write(audio / "mic_0000.flac", np.full(16000, 0.2, np.float32), 16000)  # failed: must be transcribed
    recover_unfinished(tmp_path, FakeTranscriber(), None, None, lambda: [])
    text = (d / "transcript.md").read_text(encoding="utf-8")
    assert "[0:00:01] **Me:** hello from akifer" in text
    assert not audio.exists()
    assert json.loads((d / "state.json").read_text())["failed_chunks"] == []
