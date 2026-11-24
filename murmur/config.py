"""Settings, paths and secrets.

Everything user-specific lives outside the repo:
- settings + dictionary + history:  %LOCALAPPDATA%\\Murmur
- meeting notes:                     ~/Documents/Murmur/Meetings (changeable)
- API key:                           Windows Credential Manager (via keyring)
"""
from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

APP_NAME = "Murmur"
KEYRING_SERVICE = "Murmur"
KEYRING_USER = "llm-api-key"  # OpenAI-compatible key (name kept for existing installs)
KEYRING_USERS = {"openai": KEYRING_USER, "claude": "anthropic-api-key"}
# Optional environment overrides (for scripts/tests), one per provider so a key can never be sent to the
# other provider's server. MURMUR_API_KEY is the original name and stays OpenAI-compatible only.
ENV_KEYS = {"openai": "MURMUR_API_KEY", "claude": "MURMUR_ANTHROPIC_API_KEY"}

# Defaults applied when switching provider in Settings (model, $ per 1M input, $ per 1M output)
PROVIDER_DEFAULTS = {
    "claude": ("claude-haiku-5-5", 0.10, 0.50),
    "openai": ("gpt-4.1-nano", 0.10, 0.40),
}


def data_dir() -> Path:
    base = os.environ.get("MURMUR_DATA_DIR") or os.path.join(
        os.environ.get("LOCALAPPDATA", str(Path.home())), APP_NAME
    )
    p = Path(base)
    p.mkdir(parents=True, exist_ok=True)
    return p


def default_meetings_dir() -> str:
    return str(Path.home() / "Documents" / APP_NAME / "Meetings")


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
        env = os.environ.get(ENV_KEYS.get(provider, ENV_KEYS["openai"]))
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
