"""Write a local .ics file with one event starting N minutes from now (for calendar-prompt tests).

Usage: python tools/make_test_ics.py <out.ics> [minutes_from_now] [title]
"""
import sys
from datetime import datetime, timedelta, timezone

out = sys.argv[1]
mins = float(sys.argv[2]) if len(sys.argv) > 2 else 1
title = sys.argv[3] if len(sys.argv) > 3 else "Client call - Northwind"
start = datetime.now(timezone.utc) + timedelta(minutes=mins)
end = start + timedelta(minutes=60)
fmt = "%Y%m%dT%H%M%SZ"
open(out, "w", newline="\r\n").write(f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Murmur test//EN
BEGIN:VEVENT
UID:murmur-test-{start:%H%M%S}@local
DTSTAMP:{datetime.now(timezone.utc):{fmt}}
DTSTART:{start:{fmt}}
DTEND:{end:{fmt}}
SUMMARY:{title}
END:VEVENT
BEGIN:VEVENT
UID:murmur-allday@local
DTSTART;VALUE=DATE:{start:%Y%m%d}
SUMMARY:All-day thing (should not prompt)
END:VEVENT
END:VCALENDAR
""")
print("event at", start.astimezone().strftime("%H:%M:%S"))
