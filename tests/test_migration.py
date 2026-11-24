"""Yappr used to be called Murmur: existing setups must carry over untouched."""
import json

from yappr import config, storage
from yappr.meeting import unfinished_meetings


class FakeKeyring:
    def __init__(self, data=None):
        self.data = dict(data or {})

    def get_password(self, service, user):
        return self.data.get((service, user))

    def set_password(self, service, user, pw):
        self.data[(service, user)] = pw


def _murmur_setup(tmp_path, with_meetings_dir_setting=False):
    old = tmp_path / "Local" / "Murmur"
    old.mkdir(parents=True)
    settings = {"llm_provider": "claude", "read_speed": 1.5}
    if with_meetings_dir_setting:
        settings["meetings_dir"] = str(tmp_path / "custom-notes")
    (old / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
    (old / "dictionary.json").write_text(json.dumps([{"word": "Skip", "sounds_like": ["skipp"]}]), encoding="utf-8")
    (old / "history.jsonl").write_text('{"text": "hello"}\n', encoding="utf-8")
    (old / "murmur.log").write_text("old log\n", encoding="utf-8")
    (old / "retired-read-aloud").mkdir()
    (old / "retired-read-aloud" / "x.txt").write_text("x", encoding="utf-8")
    meetings = tmp_path / "Documents" / "Murmur" / "Meetings"
    (meetings / "2026-11-01 0900 Standup").mkdir(parents=True)
    (meetings / "2026-11-01 0900 Standup" / ".murmur-meeting").write_text("2026-11-01T09:00:00", encoding="utf-8")
    return old, meetings


def test_copies_settings_history_and_keys_without_touching_murmur(tmp_path):
    old, meetings = _murmur_setup(tmp_path)
    before = {p.relative_to(old): p.read_bytes() for p in old.rglob("*") if p.is_file()}
    kr = FakeKeyring({("Murmur", "anthropic-api-key"): "sk-ant-old", ("Murmur", "llm-api-key"): "sk-oa-old"})
    new = tmp_path / "Local" / "Yappr"

    done = config.migrate_from_murmur(new, old, meetings, keyring_mod=kr)

    assert done
    store = config.Store(new)
    assert store.settings.llm_provider == "claude" and store.settings.read_speed == 1.5
    assert store.dictionary == [{"word": "Skip", "sounds_like": ["skipp"]}]
    assert (new / "history.jsonl").read_text(encoding="utf-8") == '{"text": "hello"}\n'
    assert (new / "yappr.log").exists() and not (new / "murmur.log").exists()
    assert (new / "retired-read-aloud" / "x.txt").exists()
    # meeting notes are not moved; the setting points at them
    assert store.settings.meetings_dir == str(meetings)
    assert (meetings / "2026-11-01 0900 Standup").is_dir()
    # keys copied to the Yappr entries, Murmur entries left alone
    assert kr.get_password("Yappr", "anthropic-api-key") == "sk-ant-old"
    assert kr.get_password("Yappr", "llm-api-key") == "sk-oa-old"
    assert kr.get_password("Murmur", "anthropic-api-key") == "sk-ant-old"
    # nothing in the Murmur folder changed
    after = {p.relative_to(old): p.read_bytes() for p in old.rglob("*") if p.is_file()}
    assert after == before


def test_runs_once_and_never_overwrites_yappr_data(tmp_path):
    old, meetings = _murmur_setup(tmp_path)
    new = tmp_path / "Local" / "Yappr"
    config.migrate_from_murmur(new, old, meetings, keyring_mod=FakeKeyring())
    (new / "settings.json").write_text(json.dumps({"read_speed": 2.0}), encoding="utf-8")
    assert config.migrate_from_murmur(new, old, meetings, keyring_mod=FakeKeyring()) == []
    assert json.loads((new / "settings.json").read_text(encoding="utf-8")) == {"read_speed": 2.0}


def test_existing_yappr_key_wins(tmp_path):
    old, meetings = _murmur_setup(tmp_path)
    kr = FakeKeyring({("Murmur", "anthropic-api-key"): "old", ("Yappr", "anthropic-api-key"): "new"})
    config.migrate_from_murmur(tmp_path / "Y", old, meetings, keyring_mod=kr)
    assert kr.get_password("Yappr", "anthropic-api-key") == "new"


def test_custom_meetings_folder_kept(tmp_path):
    old, meetings = _murmur_setup(tmp_path, with_meetings_dir_setting=True)
    new = tmp_path / "Y"
    config.migrate_from_murmur(new, old, meetings, keyring_mod=FakeKeyring())
    assert config.Store(new).settings.meetings_dir == str(tmp_path / "custom-notes")


def test_fresh_install_without_murmur(tmp_path):
    new = tmp_path / "Y"
    assert config.migrate_from_murmur(new, tmp_path / "nope", tmp_path / "nope2", keyring_mod=FakeKeyring()) == []
    assert config.Store(new).settings.meetings_dir == config.default_meetings_dir()


def test_murmur_meeting_folders_still_recognised(tmp_path):
    d = tmp_path / "2026-01-01 0900 Old call"
    d.mkdir()
    (d / ".murmur-meeting").write_text("2026-01-01T09:00:00", encoding="utf-8")
    (d / "state.json").write_text('{"finished": false}', encoding="utf-8")
    assert storage.meeting_marker(d) == d / ".murmur-meeting"
    assert unfinished_meetings(tmp_path) == [d]


def test_old_env_var_names_still_work(monkeypatch):
    monkeypatch.delenv("YAPPR_ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("MURMUR_ANTHROPIC_API_KEY", "sk-ant-env-old")
    assert config.Store.get_api_key("claude") == "sk-ant-env-old"
    monkeypatch.setenv("YAPPR_ANTHROPIC_API_KEY", "sk-ant-env-new")
    assert config.Store.get_api_key("claude") == "sk-ant-env-new"
