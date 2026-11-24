"""A throwaway key store for the recording run, so the demo never reads or overwrites the real
keys in Windows Credential Manager. Used via PYTHON_KEYRING_BACKEND=demo_keyring.FileKeyring."""
import json
import os
from pathlib import Path

from keyring.backend import KeyringBackend

STORE = Path(os.environ.get("YAPPR_DEMO_KEYS") or Path(__file__).parent / "build" / "demo-keys.json")


class FileKeyring(KeyringBackend):
    priority = 1

    def _load(self):
        try:
            return json.loads(STORE.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def get_password(self, service, username):
        return self._load().get(f"{service}/{username}")

    def set_password(self, service, username, password):
        d = self._load()
        d[f"{service}/{username}"] = password
        STORE.write_text(json.dumps(d), encoding="utf-8")

    def delete_password(self, service, username):
        d = self._load()
        d.pop(f"{service}/{username}", None)
        STORE.write_text(json.dumps(d), encoding="utf-8")
