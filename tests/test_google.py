"""Google sign-in (against a fake Google), Google Calendar events, and calendar details in meeting notes."""
import base64
import hashlib
import json
import threading
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from yappr import google_auth
from yappr.api import Api, parse_summary
from yappr.calendar_watch import CalendarWatcher, parse_google_events
from yappr.google_auth import CALENDAR_SCOPE, GoogleAccount, GoogleError, NeedsReconnect
from yappr.meeting import event_info, summarize_folder


class FakeKeyring:
    def __init__(self):
        self.store = {}

    def get_password(self, svc, user):
        return self.store.get((svc, user))

    def set_password(self, svc, user, pw):
        self.store[(svc, user)] = pw

    def delete_password(self, svc, user):
        self.store.pop((svc, user), None)


def id_token(email):
    body = base64.urlsafe_b64encode(json.dumps({"email": email}).encode()).rstrip(b"=").decode()
    return f"x.{body}.y"


class FakeGoogle:
    """Stands in for the browser + Google's token endpoint."""

    def __init__(self, answer=None, scope=None, wrong_state_first=False):
        self.answer = answer  # query params the browser comes back with; None = approve
        self.scope = scope or f"openid email {CALENDAR_SCOPE}"
        self.wrong_state_first = wrong_state_first
        self.auth = None
        self.posts = []
        self.pages = []

    def open_browser(self, url):
        self.auth = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url).query))
        self.thread = threading.Thread(target=self._come_back, daemon=True)
        self.thread.start()
        return True

    def _get(self, params):
        url = self.auth["redirect_uri"] + "/?" + urllib.parse.urlencode(params)
        with urllib.request.urlopen(url, timeout=5) as r:
            self.pages.append(r.read().decode())

    def _come_back(self):
        if self.wrong_state_first:
            self._get({"code": "evil", "state": "not-the-state"})
        self._get(self.answer or {"code": "the-code", "state": self.auth["state"]})

    def post(self, url, data):
        self.posts.append((url, data))
        if url == google_auth.TOKEN_URL and data["grant_type"] == "authorization_code":
            return {"access_token": "at1", "expires_in": 3600, "refresh_token": "rt1", "scope": self.scope,
                    "id_token": id_token("me@example.com")}
        if url == google_auth.TOKEN_URL:
            return {"access_token": "at2", "expires_in": 3600}
        return {}


@pytest.fixture(autouse=True)
def client(monkeypatch):
    monkeypatch.setenv("YAPPR_GOOGLE_CLIENT_ID", "cid.apps.googleusercontent.com")
    monkeypatch.setenv("YAPPR_GOOGLE_CLIENT_SECRET", "not-really-secret")


def account(fake, kr=None):
    return GoogleAccount(None, keyring_mod=kr or FakeKeyring(), open_browser=fake.open_browser, post=fake.post)


# ---------------------------------------------------------------- sign-in
def test_connect_saves_refresh_token_and_uses_pkce():
    fake, kr = FakeGoogle(), FakeKeyring()
    g = account(fake, kr)
    assert g.connect(timeout=10) == "me@example.com"
    a = fake.auth
    assert a["redirect_uri"].startswith("http://127.0.0.1:") and a["code_challenge_method"] == "S256"
    assert set(a["scope"].split()) == {"openid", "email", CALENDAR_SCOPE}  # read-only, nothing more
    assert a["access_type"] == "offline"
    _, data = fake.posts[0]
    challenge = base64.urlsafe_b64encode(hashlib.sha256(data["code_verifier"].encode()).digest()).rstrip(b"=").decode()
    assert challenge == a["code_challenge"] and data["code"] == "the-code" and data["redirect_uri"] == a["redirect_uri"]
    assert kr.store == {("Yappr", "google-refresh-token"): "rt1"}
    assert g.connected and g.access_token() == "at1"  # cached; no refresh call
    fake.thread.join(5)
    assert "connected" in fake.pages[-1]


def test_wrong_state_is_ignored():
    fake = FakeGoogle(wrong_state_first=True)
    g = account(fake)
    g.connect(timeout=10)
    assert all(d.get("code") != "evil" for _, d in fake.posts)
    assert "out of date" in fake.pages[0]


def test_cancelled_on_google():
    fake = FakeGoogle(answer={"error": "access_denied"})
    fake._come_back = lambda: fake._get({"error": "access_denied", "state": fake.auth["state"]})
    g = account(fake)
    with pytest.raises(GoogleError, match="cancelled"):
        g.connect(timeout=10)
    assert not g.connected and not fake.posts


def test_calendar_box_unticked_is_not_kept():
    fake = FakeGoogle(scope="openid email")
    g = account(fake)
    with pytest.raises(GoogleError, match="calendar"):
        g.connect(timeout=10)
    assert not g.connected
    assert fake.posts[-1] == (google_auth.REVOKE_URL, {"token": "rt1"})


def test_no_client_id_says_so(monkeypatch, tmp_path):
    monkeypatch.delenv("YAPPR_GOOGLE_CLIENT_ID")
    monkeypatch.setattr(google_auth, "BUNDLED_CLIENT", tmp_path / "none.json")
    g = GoogleAccount(tmp_path, keyring_mod=FakeKeyring())
    assert not g.configured
    with pytest.raises(GoogleError, match="isn't set up"):
        g.connect()


def test_client_file_from_google_cloud(monkeypatch, tmp_path):
    monkeypatch.delenv("YAPPR_GOOGLE_CLIENT_ID")
    (tmp_path / "google-client.json").write_text(json.dumps({"installed": {"client_id": "abc", "client_secret": "s"}}))
    assert google_auth.load_client(tmp_path) == ("abc", "s")


def test_refresh_and_revoked():
    fake, kr = FakeGoogle(), FakeKeyring()
    kr.set_password("Yappr", "google-refresh-token", "rt1")
    g = account(fake, kr)
    assert g.access_token() == "at2"
    g._access = None
    g.post = lambda url, data: {"error": "invalid_grant"}
    with pytest.raises(NeedsReconnect):
        g.access_token()
    assert "sign in again" in g.problem


def test_offline_is_a_plain_message():
    fake, kr = FakeGoogle(), FakeKeyring()
    kr.set_password("Yappr", "google-refresh-token", "rt1")
    g = account(fake, kr)
    g.post = lambda url, data: {"error": "network"}
    with pytest.raises(GoogleError, match="internet"):
        g.access_token()


def test_disconnect_revokes_and_forgets():
    fake, kr = FakeGoogle(), FakeKeyring()
    kr.set_password("Yappr", "google-refresh-token", "rt1")
    g = account(fake, kr)
    g.disconnect()
    assert fake.posts == [(google_auth.REVOKE_URL, {"token": "rt1"})]
    assert not g.connected and kr.store == {}


# ---------------------------------------------------------------- events
T = "2026-11-24T15:00:00Z"
T_END = "2026-11-24T15:30:00Z"


def ev(**kw):
    base = {"id": "e1", "summary": "Client call", "start": {"dateTime": T}, "end": {"dateTime": T_END}}
    return base | kw


def test_google_events_skip_what_isnt_a_meeting():
    items = [
        ev(id="ok", hangoutLink="https://meet.google.com/abc-defg-hij", htmlLink="https://www.google.com/calendar/event?eid=x",
           attendees=[{"email": "me@example.com", "self": True, "responseStatus": "accepted"},
                      {"email": "sam@example.com", "displayName": "Siobhan Byrne"},
                      {"email": "room1@example.com", "resource": True}]),
        ev(id="allday", start={"date": "2026-11-24"}),
        ev(id="declined", attendees=[{"email": "me@example.com", "self": True, "responseStatus": "declined"}]),
        ev(id="cancelled", status="cancelled"),
        ev(id="free", transparency="transparent"),
        ev(id="ooo", eventType="outOfOffice"),
    ]
    out = parse_google_events(items)
    assert [e["uid"][:4] for e in out] == ["g:ok"]
    e = out[0]
    assert e["title"] == "Client call" and e["start"] == datetime(2026, 11, 24, 15, tzinfo=timezone.utc)
    assert e["end"] - e["start"] == timedelta(minutes=30)
    assert e["meet_link"] == "https://meet.google.com/abc-defg-hij"
    assert [a["email"] for a in e["attendees"]] == ["me@example.com", "sam@example.com"]


def test_meet_link_from_conference_data():
    e = parse_google_events([ev(conferenceData={"entryPoints": [
        {"entryPointType": "phone", "uri": "tel:+1"}, {"entryPointType": "video", "uri": "https://meet.google.com/x"}]})])[0]
    assert e["meet_link"] == "https://meet.google.com/x"


def test_watcher_prefers_google_when_connected(monkeypatch):
    from yappr import calendar_watch

    calls = []
    monkeypatch.setattr(calendar_watch, "google_events", lambda g, a, b: calls.append("google") or [])
    monkeypatch.setattr(calendar_watch, "fetch_ics", lambda url: calls.append("ics") or b"")
    monkeypatch.setattr(calendar_watch, "upcoming_events", lambda ics, a, b: [])
    g = SimpleNamespace(connected=True)
    w = CalendarWatcher(lambda: "https://example.com/basic.ics", lambda e: None, google=g)
    w.fetch()
    g.connected = False
    w.fetch()
    assert calls == ["google", "ics"]


def test_watcher_error_is_kept_not_raised(monkeypatch):
    from yappr import calendar_watch

    def boom(g, a, b):
        raise NeedsReconnect("Google stopped accepting Yappr's sign-in.")

    monkeypatch.setattr(calendar_watch, "google_events", boom)
    w = CalendarWatcher(lambda: "", lambda e: None, google=SimpleNamespace(connected=True))
    w.fetch()
    assert "stopped accepting" in w.last_error


def test_current_event_for_take_notes_now():
    w = CalendarWatcher(lambda: "", lambda e: None)
    start = datetime(2026, 11, 24, 15, tzinfo=timezone.utc)
    w._events = [{"uid": "a", "title": "Standup", "start": start, "end": start + timedelta(minutes=15)}]
    assert w.current_event(start + timedelta(minutes=10))["title"] == "Standup"
    assert w.current_event(start + timedelta(minutes=20)) is None
    assert w.current_event(start - timedelta(minutes=4))["title"] == "Standup"


# ---------------------------------------------------------------- notes
class FakeLLM:
    available = True

    def __init__(self):
        self.prompts = []

    def chat(self, system, user, **kw):
        self.prompts.append(system + "\n" + user)
        return "## Summary\n- Talked about the pilot.\n\n## Next steps\n- [ ] Siobhan sends the plan"


def test_summary_lists_attendees_and_call_and_only_names_go_to_ai(tmp_path):
    e = parse_google_events([ev(hangoutLink="https://meet.google.com/abc", htmlLink="https://www.google.com/calendar/event?eid=x",
                                attendees=[{"email": "me@example.com", "self": True},
                                           {"email": "sb@example.com", "displayName": "Siobhan Byrne"},
                                           {"email": "noname@example.com"}])])[0]
    info = event_info(e)
    assert [a["email"] for a in info["attendees"]] == ["sb@example.com", "noname@example.com"]  # not me
    (tmp_path / "transcript.md").write_text("# Client call\n\nMonday\n\n[00:00:01] **Me:** hi shivawn\n", encoding="utf-8")
    (tmp_path / "state.json").write_text(json.dumps({"event": info}), encoding="utf-8")
    llm = FakeLLM()
    out = summarize_folder(tmp_path, llm, SimpleNamespace(llm_summary_model=""), ["Acme"]).read_text(encoding="utf-8")
    assert "**With:** Siobhan Byrne, noname@example.com" in out
    assert "**Call:** https://meet.google.com/abc" in out
    assert "Acme, Siobhan Byrne" in llm.prompts[0]
    assert "@" not in llm.prompts[0]  # no email address is sent to the AI
    parsed = parse_summary(out)
    assert parsed["with"] == "Siobhan Byrne, noname@example.com"
    assert parsed["calendar"] == "https://www.google.com/calendar/event?eid=x"
    assert parsed["sections"][0]["heading"] == "Summary"


def test_notes_without_calendar_unchanged(tmp_path):
    (tmp_path / "transcript.md").write_text("# Meeting\n\nMonday\n\n[00:00:01] **Me:** hi\n", encoding="utf-8")
    out = summarize_folder(tmp_path, FakeLLM(), SimpleNamespace(llm_summary_model="")).read_text(encoding="utf-8")
    assert out.startswith("# Meeting\n\nMonday\n\n## Summary")


def test_open_link_only_opens_google_calendar_and_meet(monkeypatch):
    import webbrowser

    opened = []
    monkeypatch.setattr(webbrowser, "open", opened.append)
    api = Api(SimpleNamespace())
    assert api.open_link("https://meet.google.com/abc")
    assert not api.open_link("https://evil.example.com/")
    assert not api.open_link("http://meet.google.com/abc")
    assert not api.open_link("file:///C:/Windows/system32/calc.exe")
    assert opened == ["https://meet.google.com/abc"]
