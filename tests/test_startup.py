from pathlib import Path

from yappr import settings_ui


class FakeWinreg:
    """In-memory stand-in so the test never touches the real registry."""
    HKEY_CURRENT_USER = "HKCU"
    KEY_SET_VALUE = 2
    REG_SZ = 1

    def __init__(self):
        self.values = {}

    class _Key:
        def __init__(self, store, path):
            self.store, self.path = store, path

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def OpenKey(self, root, path, *a):
        return self._Key(self, path)

    def QueryValueEx(self, key, name):
        if (key.path, name) not in self.values:
            raise OSError("not found")
        return self.values[(key.path, name)], self.REG_SZ

    def SetValueEx(self, key, name, _r, _t, value):
        self.values[(key.path, name)] = value

    def DeleteValue(self, key, name):
        if (key.path, name) not in self.values:
            raise OSError("not found")
        del self.values[(key.path, name)]


def test_startup_toggle_writes_and_removes_run_value(monkeypatch):
    fake = FakeWinreg()
    monkeypatch.setattr(settings_ui, "winreg", fake)
    assert not settings_ui.startup_enabled()
    settings_ui.set_startup(True)
    assert settings_ui.startup_enabled()
    assert fake.values[(settings_ui.RUN_KEY, "Yappr")] == settings_ui.startup_command()
    settings_ui.set_startup(False)
    assert not settings_ui.startup_enabled()
    settings_ui.set_startup(False)  # idempotent


def test_startup_command_uses_windowless_python():
    cmd = settings_ui.startup_command()
    exe = cmd.split('"')[1]
    assert Path(exe).name.lower() == "pythonw.exe" and Path(exe).exists()
    assert cmd.endswith("-m yappr")
