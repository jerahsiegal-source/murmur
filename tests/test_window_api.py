"""The new Yappr window: its bridge to the app (api.py), the page it shows, and where the bar sits."""
import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from yappr import storage
from yappr.api import Api, Server, parse_summary
from yappr.config import Store
from yappr.ui import bar_origin, format_countdown
from yappr.window import build_html


class FakeBar:
    def __init__(self):
        self.win = SimpleNamespace(deiconify=lambda: None, withdraw=lambda: None)

    def post(self, fn):
        fn()


class FakeApp:
    def __init__(self, root: Path):
        self.store = Store(root)
        self.store.settings.meetings_dir = str(root / "Meetings")
        self.bar = FakeBar()
        self.reader = SimpleNamespace(set_speed=lambda v: None, speak=lambda t: None)
        self.meeting = None
        self.llm = None
        self.reloaded = 0
        self.calendar = SimpleNamespace(next_event=lambda: None, refresh_now=lambda: None, last_error="")
        self.google = SimpleNamespace(connected=False, configured=False, problem="")

    def reload_settings(self):
        self.reloaded += 1

    def finished_meeting_dirs(self):
        d = Path(self.store.settings.meetings_dir)
        return sorted((p for p in d.iterdir() if p.is_dir()), reverse=True) if d.exists() else []


@pytest.fixture
def app(tmp_path):
    return FakeApp(tmp_path)


# ---------------------------------------------------------------- bar position
def test_bar_defaults_to_bottom_centre():
    assert bar_origin((0, 0, 1000, 800), 200, 40, None, 10) == (400, 750)


def test_bar_goes_where_it_was_dragged():
    # centre at 25% across, bottom edge at half height
    assert bar_origin((0, 0, 1000, 800), 200, 40, (0.25, 0.5), 10) == (150, 360)


def test_bar_stays_on_screen_when_screen_shrinks():
    assert bar_origin((0, 0, 1000, 800), 200, 40, (0.99, 0.01), 10) == (800, 0)
    assert bar_origin((100, 0, 1100, 800), 200, 40, (0.0, 1.0), 10) == (100, 760)


def test_countdown_text():
    assert format_countdown("Design sync", 18) == "Design sync in 18 min"
    assert format_countdown("Design sync", 0) == "Design sync now"
    assert format_countdown("A very long meeting title indeed", 5).startswith("A very long meeting t…")


# ---------------------------------------------------------------- page
def test_page_is_self_contained():
    """The window loads nothing from the internet: no http(s) URLs in src/href/url()."""
    html = build_html("today")
    assert "/*CSS*/" not in html and "/*JS*/" not in html and "{{SKIP}}" not in html
    assert not re.search(r'(src|href)\s*=\s*"https?:', html)
    assert not re.search(r"url\(\s*['\"]?https?:", html)
    assert "@import" not in html


def test_page_name_is_sanitised():
    assert 'data-start="today"' in build_html("x\" onload=\"alert(1)")


# ---------------------------------------------------------------- settings
def test_save_settings_applies_and_coerces(app):
    r = Api(app).save_settings({"retention_days": "30", "read_speed": 9, "use_llm_cleanup": 0, "stt_threads": 99})
    s = app.store.settings
    assert r["ok"]
    assert s.retention_days == 30
    assert s.read_speed <= 2.0
    assert s.use_llm_cleanup is False
    assert s.stt_threads == 4  # not editable from the window
    assert json.loads(app.store.settings_path.read_text())["retention_days"] == 30
    assert app.reloaded == 1


@pytest.mark.parametrize("bad", [0, "0", "", None, -3, "  "])
def test_retention_is_never_quietly_shortened(app, bad):
    """A cleared or zero 'keep for' box must not turn into 'delete everything older than a day'."""
    r = Api(app).save_settings({"retention_days": bad})
    assert not r["ok"]
    assert app.store.settings.retention_days == 90
    assert not app.store.settings_path.exists()


def test_a_bad_value_changes_nothing(app):
    r = Api(app).save_settings({"read_speed": 1.5, "price_in_per_m": "lots"})
    assert not r["ok"]
    assert app.store.settings.read_speed == 1.3  # the good value wasn't applied either


def test_connection_errors_are_plain():
    from yappr.api import plain_error

    assert "key wasn't accepted" in plain_error(Exception("Error code: 401 - invalid x-api-key"))
    assert "internet" in plain_error(TimeoutError("timed out"))
    assert "Couldn't reach" in plain_error(OSError("[WinError 10061] connection refused"))
    assert "out of credit" not in plain_error(Exception("could not generate a reply"))
    for e in (Exception("401"), TimeoutError(), OSError("getaddrinfo failed"), Exception("weird")):
        assert "Error" not in plain_error(e) and "Win" not in plain_error(e)


def test_save_settings_refuses_plain_http_for_remote_ai(app):
    r = Api(app).save_settings({"llm_provider": "openai", "llm_base_url": "http://example.com/v1"})
    assert not r["ok"] and "Nothing was saved" in r["error"]
    assert app.store.settings.llm_provider == "claude"


def test_save_settings_rejects_non_numbers(app):
    r = Api(app).save_settings({"retention_days": "lots"})
    assert not r["ok"]


def test_words(app):
    a = Api(app)
    a.add_word("Kiyosaki", "key a saki, kiyo saki")
    a.add_word("kiyosaki", "")  # same word, any case: replaces
    assert app.store.dictionary == [{"word": "kiyosaki", "sounds_like": []}]
    assert a.remove_word("KIYOSAKI") == []


# ---------------------------------------------------------------- notes
def make_meeting(app, name, summary):
    d = Path(app.store.settings.meetings_dir) / name
    d.mkdir(parents=True)
    (d / "summary.md").write_text(summary, encoding="utf-8")
    (d / "transcript.md").write_text("# T\n\nwhen\n\n[0:00:01] Me: hi\n[0:46:30] Others: bye\n", encoding="utf-8")
    return d


SUMMARY = """# Q4 planning

Tuesday, November 24, 2026 at 10:00

## Summary
- Beta ships 12 December.
## Next steps
- [ ] Sam — invite list (Friday)
- [x] Me — legal
## Open questions
None

---
Full transcript: [transcript.md](transcript.md)
"""


def test_parse_summary():
    p = parse_summary(SUMMARY)
    assert p["title"] == "Q4 planning" and p["when"].startswith("Tuesday")
    steps = next(s for s in p["sections"] if s["heading"] == "Next steps")["items"]
    assert steps == [{"text": "Sam — invite list (Friday)", "done": False}, {"text": "Me — legal", "done": True}]
    assert all("transcript.md" not in i["text"] for s in p["sections"] for i in s["items"])


def test_meetings_list_and_reader(app):
    make_meeting(app, "2026-11-24 1000 Q4 planning", SUMMARY)
    a = Api(app)
    [m] = a.meetings()
    assert m == {"id": "2026-11-24 1000 Q4 planning", "title": "Q4 planning", "date": "2026-11-24", "time": "10:00",
                 "steps": 2, "minutes": 46, "ready": True}
    assert a.meeting(m["id"])["title"] == "Q4 planning"
    assert "[0:00:01]" in a.transcript(m["id"])


@pytest.mark.parametrize("bad", ["..", "../x", "C:\\Windows", "2026-11-24 1000 nope"])
def test_meeting_ids_cannot_escape_the_notes_folder(app, bad):
    with pytest.raises(ValueError):
        Api(app).meeting(bad)


def test_today_counts_only_today(app):
    storage.append_history(app.store.root, {"raw": "a b", "text": "one two three", "method": "llm"})
    with open(app.store.root / "history.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": "2020-01-01T10:00:00+00:00", "text": "old words here"}) + "\n")
    t = Api(app).today()
    assert (t["words"], t["dictations"], t["meetings"]) == (3, 1, 0)
    assert t["timeline"][0]["kind"] == "said" and t["next_meeting"] is None


# ---------------------------------------------------------------- first run
def test_first_run_flags(app):
    a = Api(app)
    assert a.state()["onboarded"] is False
    a.finish_onboarding()
    assert a.state()["onboarded"] is True
    assert a.state()["checklist_hidden"] is False
    a.dismiss_checklist()
    assert a.state()["checklist_hidden"] is True


def test_people_who_already_dictated_skip_the_welcome(tmp_path):
    storage.append_history(tmp_path, {"text": "hi"})
    assert Store(tmp_path).onboarded()


# ---------------------------------------------------------------- transport
def test_pipe_round_trip_and_wrong_key(app):
    from multiprocessing.connection import AuthenticationError, Client

    srv = Server(Api(app))
    srv.start()
    with Client(srv.address, family="AF_PIPE", authkey=srv.key) as c:
        c.send(("add_word", ["Yappr", ""]))
        assert c.recv() == ("ok", [{"word": "Yappr", "sounds_like": []}])
        c.send(("_dir", ["x"]))  # private methods are not reachable
        assert c.recv()[0] == "error"
    with pytest.raises((AuthenticationError, EOFError, OSError)):
        with Client(srv.address, family="AF_PIPE", authkey=b"wrong" * 6) as c:
            c.send(("state", []))
            c.recv()


def test_every_answer_the_page_reads_is_json(app, monkeypatch):
    """The window passes answers to the page as JSON; anything else leaves the page blank."""
    monkeypatch.setattr("yappr.settings_ui.startup_enabled", lambda: False)
    make_meeting(app, "2026-11-24 1000 Q4 planning", SUMMARY)
    storage.append_history(app.store.root, {"raw": "a", "text": "b", "method": "rules"})
    a = Api(app)
    for value in (a.state(), a.today(), a.meetings(), a.meeting("2026-11-24 1000 Q4 planning"), a.dictations(),
                  a.usage(), a.last_dictation(), a.save_settings({"read_speed": 1.2})):
        json.dumps(value)


def test_page_requests_reach_an_open_window(app):
    a = Api(app)
    assert a.take_page() == ""
    app.window_page = "settings"
    assert a.take_page() == "settings"
    assert a.take_page() == ""  # taken once


def test_open_yappr_doesnt_move_an_open_window(monkeypatch):
    """Tray/bar 'Open Yappr' only brings the window forward (it mustn't drop the welcome or the page you're on);
    'Settings' or 'Meeting notes' switch it."""
    from yappr import app as app_mod

    monkeypatch.setattr(app_mod, "focus_process_window", lambda pid: None)
    a = object.__new__(app_mod.App)
    a.window_proc = SimpleNamespace(poll=lambda: None, pid=1)
    a.window_page = ""
    a.open_window()
    assert a.window_page == ""
    a.open_window("settings")
    assert a.window_page == "settings"
