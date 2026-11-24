import json
import time
from datetime import datetime, timedelta, timezone

from murmur import storage


def test_purge_removes_old_history_and_meetings_only(tmp_path):
    data, meetings = tmp_path / "data", tmp_path / "meetings"
    data.mkdir()
    meetings.mkdir()
    now = datetime.now(timezone.utc)
    lines = [
        {"ts": (now - timedelta(days=100)).isoformat(), "text": "old"},
        {"ts": (now - timedelta(days=5)).isoformat(), "text": "new"},
    ]
    (data / "history.jsonl").write_text("\n".join(json.dumps(l) for l in lines) + "\n", encoding="utf-8")
    old = storage.new_meeting_dir(meetings, "Old call", datetime.now() - timedelta(days=91))
    new = storage.new_meeting_dir(meetings, "New call", datetime.now() - timedelta(days=2))
    mine = meetings / "my own folder"  # not created by Murmur: must never be deleted
    mine.mkdir()
    (old / "transcript.md").write_text("x")

    removed = storage.purge(data, meetings, retention_days=90)

    assert removed == {"history": 1, "meetings": 1}
    assert not old.exists() and new.exists() and mine.exists()
    assert [json.loads(l)["text"] for l in (data / "history.jsonl").read_text().splitlines()] == ["new"]


def test_meeting_dir_names_are_safe_and_unique(tmp_path):
    a = storage.new_meeting_dir(tmp_path, 'Client: "Q4" plan / review?')
    b = storage.new_meeting_dir(tmp_path, 'Client: "Q4" plan / review?')
    assert a != b and a.exists() and b.exists()
    assert ":" not in a.name[16:] and "?" not in a.name and "/" not in a.name


def test_history_roundtrip(tmp_path):
    storage.append_history(tmp_path, {"text": "one"})
    storage.append_history(tmp_path, {"text": "two"})
    assert [h["text"] for h in storage.read_history(tmp_path)] == ["two", "one"]


def test_zero_retention_is_clamped_and_unfinished_calls_survive(tmp_path):
    data, meetings = tmp_path / "data", tmp_path / "meetings"
    data.mkdir()
    meetings.mkdir()
    today = storage.new_meeting_dir(meetings, "Today")
    recording = storage.new_meeting_dir(meetings, "Still recording", datetime.now() - timedelta(days=2))
    (recording / "state.json").write_text(json.dumps({"finished": False}))
    removed = storage.purge(data, meetings, retention_days=0)  # 0 must not mean "delete everything"
    assert today.exists() and removed["meetings"] == 0
    removed = storage.purge(data, meetings, retention_days=1)
    assert recording.exists()  # unfinished: kept for recovery even though past retention
