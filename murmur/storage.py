"""Where things are kept, and when they are deleted.

- Dictation history: <data>/history.jsonl (local only; used for "paste last", review, cost checks)
- Meetings: <meetings_dir>/<YYYY-MM-DD HHMM> <title>/{summary.md, transcript.md}
  Plain Markdown so it can be searched, copied, exported, or synced (e.g. a Google Drive folder).
- Retention: anything older than `retention_days` is deleted (history lines, meeting folders,
  leftover audio).
"""
from __future__ import annotations

import json
import logging
import re
import shutil
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger(__name__)
_lock = threading.Lock()
MEETING_MARKER = ".murmur-meeting"  # only folders with this file are ever auto-deleted


def append_history(data_dir: Path, rec: dict) -> None:
    rec = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), **rec}
    with _lock, open(data_dir / "history.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def read_history(data_dir: Path, limit: int = 200) -> list[dict]:
    try:
        lines = (data_dir / "history.jsonl").read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return []
    out = []
    for line in lines[-limit:]:
        try:
            out.append(json.loads(line))
        except Exception:
            pass
    return out[::-1]


def safe_name(title: str) -> str:
    t = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", title).strip().rstrip(".")
    return re.sub(r"\s+", " ", t)[:60] or "Meeting"


def new_meeting_dir(meetings_dir: Path, title: str, when: datetime | None = None) -> Path:
    when = when or datetime.now()
    base = meetings_dir / f"{when:%Y-%m-%d %H%M} {safe_name(title)}"
    p, i = base, 2
    while p.exists():
        p = Path(f"{base} ({i})")
        i += 1
    p.mkdir(parents=True)
    (p / MEETING_MARKER).write_text(when.isoformat(timespec="seconds"), encoding="utf-8")
    return p


def purge(data_dir: Path, meetings_dir: Path, retention_days: int, now: float | None = None) -> dict:
    """Delete history lines and meeting folders older than retention_days. Returns counts."""
    now = now or time.time()
    retention_days = max(1, int(retention_days))  # never "0 = delete everything"
    cutoff = now - retention_days * 86400
    removed = {"history": 0, "meetings": 0}

    hist = data_dir / "history.jsonl"
    if hist.exists():
        cutoff_dt = datetime.fromtimestamp(cutoff, timezone.utc)
        with _lock:
            keep = []
            for line in hist.read_text(encoding="utf-8").splitlines():
                try:
                    if datetime.fromisoformat(json.loads(line)["ts"]) < cutoff_dt:
                        removed["history"] += 1
                        continue
                except Exception:
                    pass
                keep.append(line)
            if removed["history"]:
                hist.write_text("\n".join(keep) + ("\n" if keep else ""), encoding="utf-8")

    if meetings_dir.exists():
        for d in meetings_dir.iterdir():
            marker = d / MEETING_MARKER
            if not (d.is_dir() and marker.exists()):
                continue  # never touch folders we didn't create
            try:
                created = datetime.fromisoformat(marker.read_text(encoding="utf-8").strip()).timestamp()
            except Exception:
                created = marker.stat().st_mtime
            if created < cutoff:
                if _unfinished(d) and created > cutoff - 30 * 86400:
                    continue  # a call still recording / awaiting recovery: 30 extra days to finish it
                shutil.rmtree(d, ignore_errors=True)
                removed["meetings"] += 1
    if any(removed.values()):
        log.info("retention purge: %s", removed)
    return removed


def _unfinished(d: Path) -> bool:
    try:
        return json.loads((d / "state.json").read_text(encoding="utf-8")).get("finished") is False
    except Exception:
        return False


def disk_usage(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) if path.exists() else 0
