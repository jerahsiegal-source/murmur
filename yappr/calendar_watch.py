"""Meeting-start prompts from your calendar.

Two sources, both read-only (nothing is ever sent back):
- Google Calendar, when you've clicked Connect (see google_auth.py). Also gives attendees and the Meet link.
- Otherwise a private iCal address (any calendar that offers one: Outlook, iCloud, Google...).
Polls every few minutes, and asks — never starts recording by itself.
"""
from __future__ import annotations

import logging
import threading
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

log = logging.getLogger(__name__)


def fetch_ics(url: str, timeout: float = 20) -> bytes:
    if url.startswith(("http://", "https://", "webcal://")):
        url = url.replace("webcal://", "https://", 1)
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.read()
    return Path(url.removeprefix("file:///")).read_bytes()  # local file, for testing


EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
SKIP_TYPES = {"outOfOffice", "focusTime", "workingLocation", "birthday"}


def _rfc3339(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def google_events(account, start: datetime, end: datetime) -> list[dict]:
    """Timed meetings from the primary Google Calendar that you haven't declined."""
    data = account.get_json(EVENTS_URL, {
        "timeMin": _rfc3339(start), "timeMax": _rfc3339(end), "singleEvents": "true",
        "orderBy": "startTime", "maxResults": "50",
    })
    return parse_google_events(data.get("items", []))


def parse_google_events(items: list[dict]) -> list[dict]:
    out = []
    for it in items:
        st = (it.get("start") or {}).get("dateTime")
        if not st:
            continue  # all-day
        if it.get("status") == "cancelled" or it.get("transparency") == "transparent":
            continue
        if it.get("eventType") in SKIP_TYPES:
            continue
        people = [a for a in it.get("attendees", []) if not a.get("resource")]
        if any(a.get("self") and a.get("responseStatus") == "declined" for a in people):
            continue
        start = datetime.fromisoformat(st.replace("Z", "+00:00")).astimezone(timezone.utc)
        en = (it.get("end") or {}).get("dateTime")
        meet = it.get("hangoutLink") or next(
            (e.get("uri") for e in (it.get("conferenceData") or {}).get("entryPoints", [])
             if e.get("entryPointType") == "video" and e.get("uri")), "")
        out.append({
            "uid": "g:" + str(it.get("id", "")) + start.isoformat(),
            "title": str(it.get("summary") or "Meeting"),
            "start": start,
            "end": datetime.fromisoformat(en.replace("Z", "+00:00")).astimezone(timezone.utc) if en else None,
            "attendees": [{"name": str(a.get("displayName", "")), "email": str(a.get("email", "")),
                           "me": bool(a.get("self"))} for a in people],
            "meet_link": str(meet),
            "html_link": str(it.get("htmlLink", "")),
        })
    return sorted(out, key=lambda e: e["start"])


def upcoming_events(ics: bytes, start: datetime, end: datetime) -> list[dict]:
    import icalendar
    import recurring_ical_events

    cal = icalendar.Calendar.from_ical(ics)
    out = []
    for ev in recurring_ical_events.of(cal).between(start, end):
        dt = ev.get("DTSTART").dt
        if not isinstance(dt, datetime):
            continue  # all-day events
        if dt.tzinfo is None:
            dt = dt.astimezone()  # floating time = local
        if str(ev.get("TRANSP", "")).upper() == "TRANSPARENT":
            continue  # "free" blocks aren't meetings
        status = str(ev.get("STATUS", "")).upper()
        if status == "CANCELLED":
            continue
        end = ev.get("DTEND")
        end = end.dt if end is not None and isinstance(end.dt, datetime) else None
        if end is not None and end.tzinfo is None:
            end = end.astimezone()
        out.append({
            "uid": str(ev.get("UID", "")) + dt.isoformat(),
            "title": str(ev.get("SUMMARY", "Meeting")),
            "start": dt.astimezone(timezone.utc),
            "end": end.astimezone(timezone.utc) if end is not None else None,
        })
    return sorted(out, key=lambda e: e["start"])


class CalendarWatcher:
    def __init__(self, get_url: Callable[[], str], on_meeting: Callable[[dict], None],
                 lead_min: Callable[[], float] = lambda: 1.0, poll_s: float = 300, google=None):
        self.get_url = get_url
        self.google = google  # GoogleAccount; used instead of the iCal link while connected
        self.on_meeting = on_meeting
        self.lead_min = lead_min
        self.poll_s = poll_s
        self._events: list[dict] = []
        self._prompted: set[str] = set()
        self._last_fetch = 0.0
        self._stop = threading.Event()
        self.last_error = ""

    def start(self) -> None:
        threading.Thread(target=self._run, name="calendar", daemon=True).start()

    def stop(self) -> None:
        self._stop.set()

    def next_event(self, now: datetime | None = None) -> dict | None:
        """The next meeting that hasn't started more than 5 minutes ago, from the last fetch (no network)."""
        now = now or datetime.now(timezone.utc)
        return next((e for e in self._events if e["start"] + timedelta(minutes=5) >= now), None)

    def current_event(self, now: datetime | None = None) -> dict | None:
        """A meeting happening right now (from 5 min before its start to its end), for "Take notes now"."""
        now = now or datetime.now(timezone.utc)
        for e in self._events:
            end = e.get("end") or e["start"] + timedelta(minutes=30)
            if e["start"] - timedelta(minutes=5) <= now <= end:
                return e
        return None

    def refresh_now(self) -> None:
        self._last_fetch = 0.0

    def _source(self) -> Callable[[datetime, datetime], list[dict]] | None:
        g = self.google
        if g is not None and g.connected:
            return lambda a, b: google_events(g, a, b)
        url = self.get_url()
        if url:
            return lambda a, b: upcoming_events(fetch_ics(url), a, b)
        return None

    def fetch(self, now: datetime | None = None) -> None:
        """Fetch now (on the calling thread). Errors end up in last_error, never raised."""
        src = self._source()
        if src is None:
            self._events, self.last_error = [], ""
            return
        now = now or datetime.now(timezone.utc)
        try:
            self._events = src(now - timedelta(minutes=10), now + timedelta(hours=12))
            self.last_error = ""
        except Exception as e:
            self.last_error = str(e)
            log.warning("calendar fetch failed: %s", type(e).__name__)
        self._last_fetch = time.monotonic()

    def _run(self) -> None:
        while not self._stop.wait(15):
            if self._source() is None:
                self._events = []
                continue
            now = datetime.now(timezone.utc)
            if time.monotonic() - self._last_fetch > self.poll_s or self._last_fetch == 0.0:
                self.fetch(now)
            lead = timedelta(minutes=self.lead_min())
            for ev in self._events:
                if ev["uid"] in self._prompted:
                    continue
                # prompt from `lead` before the start until 5 minutes after it
                if ev["start"] - lead <= now <= ev["start"] + timedelta(minutes=5):
                    self._prompted.add(ev["uid"])
                    self.on_meeting(ev)
