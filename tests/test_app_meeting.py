"""Meeting start/stop logic in App, with the UI and recorder stubbed out (no Tk window, no audio)."""
import threading
import time
from types import SimpleNamespace

from murmur import app as app_mod
from murmur import meeting as meeting_mod


class FakeSession:
    created = []

    def __init__(self, *a, **k):
        self.stopped = False
        self.dir = None
        FakeSession.created.append(self)

    def start(self):
        time.sleep(0.3)  # opening audio devices takes a while

    def stop(self):
        self.stopped = True

    def levels(self):
        return 0.0


class FakeBar:
    def __init__(self):
        self.states = []

    def set_state(self, s):
        self.states.append(s)

    def toast(self, *a, **k):
        pass

    def post(self, fn):
        pass

    def set_level(self, *_):
        pass


def make_app(monkeypatch):
    FakeSession.created = []
    monkeypatch.setattr(meeting_mod, "MeetingSession", FakeSession)
    a = object.__new__(app_mod.App)
    a.store = SimpleNamespace(settings=SimpleNamespace(meetings_dir="unused"), dictionary=[])
    a.transcriber = a.llm = None
    a.bar = FakeBar()
    a.recording = False
    a.meeting = None
    a.meeting_lock = threading.Lock()
    a.meeting_busy = False
    a.prompts = []
    return a


def test_double_click_creates_one_session(monkeypatch):
    a = make_app(monkeypatch)
    t1 = threading.Thread(target=a._meeting_action, args=("toggle", ""))
    t2 = threading.Thread(target=a._meeting_action, args=("toggle", ""))
    t1.start(); time.sleep(0.05); t2.start()
    t1.join(); t2.join()
    assert len(FakeSession.created) == 1 and a.meeting is FakeSession.created[0]


def test_calendar_start_never_stops_a_running_meeting(monkeypatch):
    a = make_app(monkeypatch)
    a._meeting_action("toggle", "")
    running = a.meeting
    a._meeting_action("start", "Client call")  # the prompt's "Start notes"
    assert a.meeting is running and not running.stopped and len(FakeSession.created) == 1
    a._meeting_action("toggle", "")  # the bar's Stop
    assert a.meeting is None and running.stopped
