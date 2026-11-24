"""What the Yappr window can ask the running app for.

The window (yappr/window.py) runs in its own process, only while it is open, so the app itself stays
small. Every read and write goes through `Api` in the app process, over a local named pipe
(`serve`), so there is one owner of settings, keys and the dictionary. Nothing here touches the network
except `test_connection`, which calls the AI service the user picked, exactly as Settings always did.
"""
from __future__ import annotations

import logging
import os
import re
import secrets
import threading
import time
from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path

from . import storage
from .config import PROVIDER_DEFAULTS, Store

log = logging.getLogger(__name__)

# Settings the window may change. Everything else is internal (model files, threads, timeouts).
EDITABLE = {
    "llm_provider", "llm_base_url", "llm_model", "llm_summary_model", "price_in_per_m", "price_out_per_m",
    "use_llm_cleanup", "stt_idle_unload_min", "mic_device", "meetings_dir", "retention_days",
    "calendar_ics_url", "calendar_prompt_min_before", "read_voice", "read_speed", "show_bar",
}
PIPE_PREFIX = r"\\.\pipe\yappr-window-"


def _words(text: str) -> int:
    return len(re.findall(r"\S+", text or ""))


def _local(ts: str) -> datetime | None:
    try:
        return datetime.fromisoformat(ts).astimezone()
    except Exception:
        return None


def parse_summary(md: str) -> dict:
    """summary.md -> {title, when, sections: [{heading, items: [{text, done?}] | paragraphs}]}."""
    lines = md.splitlines()
    title = lines[0].lstrip("# ").strip() if lines and lines[0].startswith("#") else "Meeting"
    when, sections, cur = "", [], None
    for line in lines[1:]:
        s = line.strip()
        if not s or s == "---" or s.startswith("Full transcript:"):
            continue
        if s.startswith("## "):
            cur = {"heading": s[3:].strip(), "items": []}
            sections.append(cur)
            continue
        if cur is None:
            if not when and not s.startswith("_"):
                when = s
            else:
                sections.append({"heading": "", "items": [{"text": s.strip("_")}]})
            continue
        m = re.match(r"[-*]\s+\[( |x|X)\]\s+(.*)", s)
        if m:
            cur["items"].append({"text": m.group(2), "done": m.group(1).lower() == "x"})
        else:
            cur["items"].append({"text": re.sub(r"^[-*]\s+", "", s)})
    return {"title": title, "when": when, "sections": sections}


class Api:
    """Methods the window calls. Each returns plain JSON-able data."""

    def __init__(self, app):
        self.app = app

    @property
    def store(self) -> Store:
        return self.app.store

    def log(self, message: str) -> bool:
        """Errors from the window's page, so they end up in yappr.log."""
        log.warning("window page: %s", str(message)[:500])
        return True

    # ------------------------------------------------------------ overview
    def state(self) -> dict:
        from .llm import PROVIDERS
        from .settings_ui import startup_enabled
        from .tts import VOICES

        s = self.store.settings
        keys = {p: bool(Store.get_api_key(p)) for p in PROVIDERS}
        return {
            "settings": {k: v for k, v in asdict(s).items() if k in EDITABLE},
            "provider_defaults": PROVIDER_DEFAULTS,
            "providers": PROVIDERS,
            "has_key": keys,
            "voices": VOICES,
            "start_with_windows": startup_enabled(),
            "onboarded": self.store.onboarded(),
            "checklist_hidden": (self.store.root / ".checklist-hidden").exists(),
            "dictated_once": bool(storage.read_history(self.store.root, 1)),
            "calendar_connected": bool(s.calendar_ics_url),
            "meeting_active": self.app.meeting is not None,
            "dictionary": self.store.dictionary,
            "bar_moved": len(s.bar_position) == 2,
        }

    def today(self) -> dict:
        now = datetime.now().astimezone()
        hist = storage.read_history(self.store.root, 500)
        todays = [h for h in hist if (d := _local(h.get("ts", ""))) and d.date() == now.date()]
        meetings = [m for m in self.meetings(limit=50) if m["date"] == now.date().isoformat()]
        timeline = [{"kind": "said", "time": _local(h["ts"]).strftime("%H:%M"), "text": h.get("text", "")}
                    for h in todays[:30]]
        timeline += [{"kind": "notes", "time": m["time"], "text": m["title"], "id": m["id"],
                      "steps": m["steps"], "minutes": m["minutes"]} for m in meetings]
        timeline.sort(key=lambda e: e["time"], reverse=True)
        nxt = self.app.calendar.next_event() if hasattr(self.app.calendar, "next_event") else None
        return {
            "words": sum(_words(h.get("text", "")) for h in todays),
            "dictations": len(todays),
            "meetings": len(meetings),
            "timeline": timeline,
            "next_meeting": ({"title": nxt["title"], "start": nxt["start"].astimezone().strftime("%H:%M"),
                              "in_min": max(0, int((nxt["start"] - now).total_seconds() // 60))} if nxt else None),
        }

    # ------------------------------------------------------------ notes
    def _meeting_dirs(self) -> list[Path]:
        return self.app.finished_meeting_dirs()

    def meetings(self, limit: int = 200) -> list[dict]:
        out = []
        for d in self._meeting_dirs()[:limit]:
            m = re.match(r"(\d{4})-(\d{2})-(\d{2}) (\d{2})(\d{2}) ?(.*)", d.name)
            if not m:
                continue
            y, mo, da, hh, mi, title = m.groups()
            summary = d / "summary.md"
            steps = 0
            if summary.exists():
                steps = len(re.findall(r"^\s*[-*]\s+\[[ xX]\]", summary.read_text(encoding="utf-8"), re.M))
            out.append({
                "id": d.name, "title": title or "Meeting", "date": f"{y}-{mo}-{da}", "time": f"{hh}:{mi}",
                "steps": steps, "minutes": self._minutes(d), "ready": summary.exists(),
            })
        return out

    @staticmethod
    def _minutes(d: Path) -> int | None:
        try:
            last = [l for l in (d / "transcript.md").read_text(encoding="utf-8").splitlines() if l.startswith("[")][-1]
            h, m, s = (int(x) for x in re.match(r"\[(\d+):(\d+):(\d+)\]", last).groups())
            return max(1, round((h * 3600 + m * 60 + s) / 60))
        except Exception:
            return None

    def _dir(self, mid: str) -> Path:
        base = Path(self.store.settings.meetings_dir).resolve()
        d = (base / mid).resolve()
        if d.parent != base or not d.is_dir():  # only folders directly in the notes folder
            raise ValueError("No such meeting")
        return d

    def meeting(self, mid: str) -> dict:
        d = self._dir(mid)
        summary = d / "summary.md"
        data = parse_summary(summary.read_text(encoding="utf-8")) if summary.exists() else {
            "title": mid[16:] or "Meeting", "when": "", "sections": [{"heading": "", "items": [{"text": "Notes are still being written…"}]}]}
        data["id"] = mid
        data["has_transcript"] = (d / "transcript.md").exists()
        return data

    def transcript(self, mid: str) -> str:
        p = self._dir(mid) / "transcript.md"
        return p.read_text(encoding="utf-8") if p.exists() else ""

    def dictations(self, limit: int = 200) -> list[dict]:
        out = []
        for i, h in enumerate(storage.read_history(self.store.root, limit)):
            d = _local(h.get("ts", ""))
            if d is None:
                continue
            out.append({"i": i, "date": d.date().isoformat(), "time": d.strftime("%H:%M"), "text": h.get("text", ""),
                        "raw": h.get("raw", ""), "ai": h.get("method") == "llm", "pasted": h.get("pasted", True)})
        return out

    def resummarize(self, mid: str) -> bool:
        from .meeting import summarize_folder

        d = self._dir(mid)
        summarize_folder(d, self.app.llm, self.store.settings, [e["word"] for e in self.store.dictionary])
        return True

    def open_notes_folder(self, mid: str = "") -> bool:
        p = self._dir(mid) if mid else Path(self.store.settings.meetings_dir)
        p.mkdir(parents=True, exist_ok=True)
        os.startfile(p)
        return True

    def toggle_meeting(self) -> bool:
        self.app.toggle_meeting()
        return True

    # ------------------------------------------------------------ settings
    def save_settings(self, changes: dict) -> dict:
        from .llm import PROVIDERS, base_url_problem
        from .tts import VOICES, clamp_speed

        s = self.store.settings
        changes = {k: v for k, v in changes.items() if k in EDITABLE}
        if changes.get("llm_provider", s.llm_provider) not in PROVIDERS:
            return {"ok": False, "error": "Unknown AI service"}
        if changes.get("llm_provider", s.llm_provider) == "openai":
            problem = base_url_problem(changes.get("llm_base_url", s.llm_base_url))
            if problem:  # the key would be sent there, so check before changing anything
                return {"ok": False, "error": f"{problem}. Nothing was saved."}
        try:
            for k, v in changes.items():
                cur = getattr(s, k)
                setattr(s, k, type(cur)(v) if not isinstance(cur, bool) else bool(v))
        except (TypeError, ValueError):
            return {"ok": False, "error": "One of the values isn't a number. Nothing else changed."}
        s.retention_days = max(1, int(s.retention_days))
        s.read_speed = clamp_speed(float(s.read_speed))
        if s.read_voice not in VOICES:
            s.read_voice = "af_heart"
        self.store.save_settings()
        self.app.reader.set_speed(s.read_speed)
        self.app.bar.post(lambda: (self.app.bar.win.deiconify() if s.show_bar else self.app.bar.win.withdraw()))
        self.app.reload_settings()
        return {"ok": True, "settings": {k: v for k, v in asdict(s).items() if k in EDITABLE}}

    def set_api_key(self, provider: str, key: str) -> bool:
        from .llm import PROVIDERS

        if provider not in PROVIDERS:
            raise ValueError("Unknown AI service")
        Store.set_api_key((key or "").strip(), provider)
        self.app.reload_settings()
        return bool(key)

    def reset_bar_position(self) -> bool:
        self.app.bar.post(self.app.bar.reset_position)  # saves through the bar's on_moved
        return True

    def set_start_with_windows(self, on: bool) -> bool:
        from .settings_ui import set_startup

        set_startup(bool(on))
        return bool(on)

    def test_connection(self, provider: str, base_url: str, model: str, key: str = "") -> dict:
        from .cleanup import SYSTEM_PROMPT
        from .llm import base_url_problem, make_llm

        if provider == "openai":
            problem = base_url_problem(base_url)
            if problem:
                return {"ok": False, "message": problem}
        key = (key or "").strip() or Store.get_api_key(provider)
        if not key:
            return {"ok": False, "message": "Add your key first."}
        s = self.store.settings
        client = make_llm(provider, base_url, key, model, s.price_in_per_m, s.price_out_per_m, self.store.root / "usage.jsonl")
        t = time.monotonic()
        try:
            out = client.chat(SYSTEM_PROMPT.format(terms="(none)"),
                              "<dictation>um so this is uh a quick test of the the cleanup</dictation>",
                              kind="test", timeout=15)
            return {"ok": True, "message": f"Connected. Replied in {time.monotonic() - t:.1f} s", "sample": out}
        except Exception as e:
            return {"ok": False, "message": f"Couldn't connect: {e}"[:200]}

    def usage(self) -> dict:
        from .llm import usage_summary

        return usage_summary(self.store.root / "usage.jsonl")

    def microphones(self) -> list[str]:
        from .settings_ui import input_devices

        return input_devices()

    def hear_sample(self, voice: str, speed: float) -> bool:
        self.save_settings({"read_voice": voice, "read_speed": speed})
        self.app.reader.speak("This is how I'll sound when I read to you. Highlight any text, "
                              "press Control Alt X, and I'll read it aloud.")
        return True

    # ------------------------------------------------------------ my words
    def add_word(self, word: str, sounds_like: str = "") -> list[dict]:
        word = (word or "").strip()
        if not word:
            return self.store.dictionary
        alias = [x.strip() for x in (sounds_like or "").split(",") if x.strip()]
        entries = [e for e in self.store.dictionary if e["word"].lower() != word.lower()]
        entries.append({"word": word, "sounds_like": alias})
        self.store.save_dictionary(entries)
        return entries

    def remove_word(self, word: str) -> list[dict]:
        entries = [e for e in self.store.dictionary if e["word"].lower() != (word or "").lower()]
        self.store.save_dictionary(entries)
        return entries

    # ------------------------------------------------------------ first run
    def finish_onboarding(self) -> bool:
        self.store.set_onboarded()
        return True

    def dismiss_checklist(self) -> bool:
        (self.store.root / ".checklist-hidden").write_text("Hidden from Today.\n", encoding="utf-8")
        return True

    def last_dictation(self) -> dict | None:
        h = storage.read_history(self.store.root, 1)
        return {"text": h[0].get("text", ""), "ts": h[0].get("ts", "")} if h else None


# ---------------------------------------------------------------- transport
class Server:
    """Answers the window's calls on a named pipe. Only a process given the random key can connect."""

    def __init__(self, api: Api):
        self.api = api
        self.key = secrets.token_bytes(32)
        self.address = PIPE_PREFIX + secrets.token_hex(8)
        self._listener = None

    def start(self) -> None:
        from multiprocessing.connection import Listener

        self._listener = Listener(self.address, family="AF_PIPE", authkey=self.key)
        threading.Thread(target=self._accept, name="window-api", daemon=True).start()

    def _accept(self) -> None:
        while True:
            try:
                conn = self._listener.accept()
            except Exception:
                log.exception("window connection refused")
                continue
            threading.Thread(target=self._serve, args=(conn,), daemon=True).start()

    def _serve(self, conn) -> None:
        with conn:
            while True:
                try:
                    method, args = conn.recv()
                except (EOFError, OSError):
                    return
                try:
                    fn = getattr(self.api, method) if not method.startswith("_") else None
                    if fn is None or not callable(fn):
                        raise AttributeError(f"no method {method}")
                    conn.send(("ok", fn(*args)))
                except Exception as e:
                    log.exception("window call %s failed", method)
                    conn.send(("error", str(e)))
