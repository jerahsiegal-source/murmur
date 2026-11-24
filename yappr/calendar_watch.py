"""Meeting-start prompts from a calendar feed.

Uses the calendar's private iCal address (Google Calendar: Settings -> your calendar ->
"Secret address in iCal format"). Read-only; nothing is sent back. Polls every few minutes,
and asks — never starts recording by itself.
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
        out.append({
            "uid": str(ev.get("UID", "")) + dt.isoformat(),
            "title": str(ev.get("SUMMARY", "Meeting")),
            "start": dt.astimezone(timezone.utc),
        })
    return sorted(out, key=lambda e: e["start"])


class CalendarWatcher:
    def __init__(self, get_url: Callable[[], str], on_meeting: Callable[[dict], None],
                 lead_min: Callable[[], float] = lambda: 1.0, poll_s: float = 300):
        self.get_url = get_url
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

    def refresh_now(self) -> None:
        self._last_fetch = 0.0

    def _run(self) -> None:
        while not self._stop.wait(15):
            url = self.get_url()
            if not url:
                continue
            now = datetime.now(timezone.utc)
            if time.monotonic() - self._last_fetch > self.poll_s or self._last_fetch == 0.0:
                try:
                    self._events = upcoming_events(fetch_ics(url), now - timedelta(minutes=10), now + timedelta(hours=12))
                    self.last_error = ""
                except Exception as e:
                    self.last_error = str(e)
                    log.warning("calendar fetch failed: %s", e)
                self._last_fetch = time.monotonic()
            lead = timedelta(minutes=self.lead_min())
            for ev in self._events:
                if ev["uid"] in self._prompted:
                    continue
                # prompt from `lead` before the start until 5 minutes after it
                if ev["start"] - lead <= now <= ev["start"] + timedelta(minutes=5):
                    self._prompted.add(ev["uid"])
                    self.on_meeting(ev)
