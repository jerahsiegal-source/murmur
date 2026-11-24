"""Settings, paths and secrets.

Everything user-specific lives outside the repo:
- settings + dictionary + history:  %LOCALAPPDATA%\\Yappr
- meeting notes:                     ~/Documents/Yappr/Meetings (changeable)
- API key:                           Windows Credential Manager (via keyring)

The app used to be called Murmur. `migrate_from_murmur()` copies an existing Murmur setup the first
time Yappr starts and never deletes or moves the old files. MURMUR_* environment variables still work.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import threading
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

APP_NAME = "Yappr"
LEGACY_APP_NAME = "Murmur"
KEYRING_SERVICE = "Yappr"
LEGACY_KEYRING_SERVICE = "Murmur"
KEYRING_USER = "llm-api-key"  # OpenAI-compatible key (name kept for existing installs)
KEYRING_USERS = {"openai": KEYRING_USER, "claude": "anthropic-api-key"}
# Optional environment overrides (for scripts/tests), one per provider so a key can never be sent to the
# other provider's server. YAPPR_API_KEY is the original name and stays OpenAI-compatible only.
ENV_KEYS = {"openai": "YAPPR_API_KEY", "claude": "YAPPR_ANTHROPIC_API_KEY"}
MIGRATED_MARKER = ".migrated-from-murmur"

log = logging.getLogger(__name__)


def getenv(name: str) -> str | None:
    """YAPPR_X, falling back to the old MURMUR_X name."""
    v = os.environ.get(name)
    if v:
        return v
    if name.startswith("YAPPR_"):
        return os.environ.get("MURMUR_" + name[len("YAPPR_"):]) or None
    return None

# Defaults applied when switching provider in Settings (model, $ per 1M input, $ per 1M output)
PROVIDER_DEFAULTS = {
    "claude": ("claude-haiku-5-5", 0.10, 0.50),
    "openai": ("gpt-4.1-nano", 0.10, 0.40),
}


def data_dir() -> Path:
    base = getenv("YAPPR_DATA_DIR") or os.path.join(
        os.environ.get("LOCALAPPDATA", str(Path.home())), APP_NAME
    )
    p = Path(base)
    p.mkdir(parents=True, exist_ok=True)
    return p


def legacy_data_dir() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / LEGACY_APP_NAME


def default_meetings_dir() -> str:
    return str(Path.home() / "Documents" / APP_NAME / "Meetings")


def legacy_meetings_dir() -> Path:
    return Path.home() / "Documents" / LEGACY_APP_NAME / "Meetings"


def migrate_from_murmur(new_root: Path, old_root: Path | None = None,
                        old_meetings: Path | None = None, keyring_mod=None) -> list[str]:
    """Carry an existing Murmur setup over to Yappr, once. Copies only; the Murmur files stay as they were.

    - settings, dictionary, history, usage log and voice data: copied from old_root
    - meeting notes: left where they are; settings keep pointing at them
    - API keys: copied from the "Murmur" Credential Manager entries to "Yappr" ones
    Returns a list of what was done (for the log). Safe to call on every start.
    """
    old_root = old_root or legacy_data_dir()
    old_meetings = old_meetings or legacy_meetings_dir()
    done: list[str] = []
    marker = new_root / MIGRATED_MARKER
    if marker.exists():
        return done
    new_root.mkdir(parents=True, exist_ok=True)

    if old_root.is_dir() and not (new_root / "settings.json").exists():
        for item in old_root.iterdir():
            dest = new_root / ("yappr.log" if item.name == "murmur.log" else item.name)
            if dest.exists():
                continue
            if item.is_dir():
                shutil.copytree(item, dest)
            else:
                shutil.copy2(item, dest)
            done.append(f"copied {item.name}")

    # Meeting notes stay in Documents\Murmur\Meetings. Pin the setting so the new default doesn't hide them.
    settings_path = new_root / "settings.json"
    if old_meetings.is_dir():
        try:
            raw = json.loads(settings_path.read_text(encoding="utf-8")) if settings_path.exists() else {}
        except Exception:
            raw = None  # unreadable: leave it alone
        if raw is not None and "meetings_dir" not in raw:
            raw["meetings_dir"] = str(old_meetings)
            settings_path.write_text(json.dumps(raw, indent=2), encoding="utf-8")
            done.append(f"meeting notes stay in {old_meetings}")

    try:
        kr = keyring_mod
        if kr is None:
            import keyring as kr
        for user in KEYRING_USERS.values():
            old = kr.get_password(LEGACY_KEYRING_SERVICE, user)
            if old and not kr.get_password(KEYRING_SERVICE, user):
                kr.set_password(KEYRING_SERVICE, user, old)
                done.append(f"copied API key {user}")
    except Exception as e:  # no keyring backend: the user can paste the key again
        done.append(f"API keys not copied ({e.__class__.__name__})")

    marker.write_text("Copied from Murmur. The Murmur files were left in place.\n", encoding="utf-8")
    return done


@dataclass
class Settings:
    # LLM: "claude" (Anthropic API) or "openai" (any OpenAI-compatible chat-completions endpoint)
    llm_provider: str = "claude"
    llm_base_url: str = "https://api.openai.com/v1"  # used by the OpenAI-compatible provider only
    llm_model: str = "claude-haiku-5-5"
    llm_summary_model: str = ""  # empty = same as llm_model
    price_in_per_m: float = 0.10  # USD per 1M input tokens, for the cost log
    price_out_per_m: float = 0.50
    llm_timeout_s: float = 4.0
    use_llm_cleanup: bool = True

    # Speech-to-text
    stt_model: str = "nemo-parakeet-tdt-0.6b-v2"
    stt_quantization: str = "int8"
    stt_threads: int = 4
    stt_idle_unload_min: float = 10.0  # 0 = keep loaded forever
    mic_device: str = ""  # empty = system default

    # Storage
    meetings_dir: str = field(default_factory=default_meetings_dir)
    retention_days: int = 90

    # Calendar
    calendar_ics_url: str = ""
    calendar_prompt_min_before: float = 1.0

    # Read aloud (local Kokoro voice)
    read_voice: str = "af_heart"
    read_speed: float = 1.3

    # UI
    show_bar: bool = True


class Store:
    """Thread-safe settings + dictionary persistence."""

    def __init__(self, root: Path | None = None):
        self.root = root or data_dir()
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self.settings = self._load_settings()
        self.dictionary = self._load_dictionary()

    # ---- settings
    @property
    def settings_path(self) -> Path:
        return self.root / "settings.json"

    def _load_settings(self) -> Settings:
        s = Settings()
        try:
            raw = json.loads(self.settings_path.read_text(encoding="utf-8"))
            names = {f.name for f in fields(Settings)}
            for k, v in raw.items():
                if k in names:
                    setattr(s, k, v)
            if "llm_provider" not in raw and "llm_model" in raw:
                s.llm_provider = "openai"  # saved before Claude support existed: keep what they chose
        except FileNotFoundError:
            pass
        except Exception:
            pass
        return s

    def save_settings(self) -> None:
        with self._lock:
            tmp = self.settings_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(asdict(self.settings), indent=2), encoding="utf-8")
            tmp.replace(self.settings_path)

    # ---- dictionary: list of {"word": "Acme", "sounds_like": ["akmi", "act me"]}
    @property
    def dictionary_path(self) -> Path:
        return self.root / "dictionary.json"

    def _load_dictionary(self) -> list[dict]:
        try:
            d = json.loads(self.dictionary_path.read_text(encoding="utf-8"))
            return [
                {"word": str(e["word"]).strip(), "sounds_like": [str(x).strip() for x in e.get("sounds_like", []) if str(x).strip()]}
                for e in d
                if str(e.get("word", "")).strip()
            ]
        except Exception:
            return []

    def save_dictionary(self, entries: list[dict]) -> None:
        with self._lock:
            self.dictionary = entries
            tmp = self.dictionary_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")
            tmp.replace(self.dictionary_path)

    # ---- secrets
    @staticmethod
    def get_api_key(provider: str = "openai") -> str:
        env = getenv(ENV_KEYS.get(provider, ENV_KEYS["openai"]))
        if env:
            return env.strip()
        try:
            import keyring

            return keyring.get_password(KEYRING_SERVICE, KEYRING_USERS.get(provider, KEYRING_USER)) or ""
        except Exception:
            return ""

    @staticmethod
    def set_api_key(key: str, provider: str = "openai") -> None:
        import keyring

        user = KEYRING_USERS.get(provider, KEYRING_USER)
        if key:
            keyring.set_password(KEYRING_SERVICE, user, key)
        else:
            try:
                keyring.delete_password(KEYRING_SERVICE, user)
            except Exception:
                pass
