from pathlib import Path

from yappr import settings_ui


class FakeWinreg:
    """In-memory stand-in so the test never touches the real registry."""
    HKEY_CURRENT_USER = "HKCU"
    KEY_SET_VALUE = 2
    KEY_QUERY_VALUE = 1
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


def _fake_startup(monkeypatch, tmp_path):
    fake = FakeWinreg()
    monkeypatch.setattr(settings_ui, "winreg", fake)
    lnk = tmp_path / "Murmur.lnk"
    monkeypatch.setattr(settings_ui, "legacy_startup_shortcut", lambda: lnk)
    return fake, lnk


def test_migrate_moves_the_murmur_run_value(monkeypatch, tmp_path):
    fake, _ = _fake_startup(monkeypatch, tmp_path)
    fake.values[(settings_ui.RUN_KEY, "Murmur")] = '"pythonw.exe" -m murmur'
    assert settings_ui.migrate_startup()
    assert fake.values == {(settings_ui.RUN_KEY, "Yappr"): settings_ui.startup_command()}


def test_migrate_replaces_the_murmur_startup_folder_shortcut(monkeypatch, tmp_path):
    fake, lnk = _fake_startup(monkeypatch, tmp_path)
    lnk.write_bytes(b"L\x00\x00\x00" + "pythonw.exe -m murmur".encode("utf-16-le"))
    assert settings_ui.migrate_startup()
    assert not lnk.exists()
    assert fake.values == {(settings_ui.RUN_KEY, "Yappr"): settings_ui.startup_command()}
    assert not settings_ui.migrate_startup()  # nothing left to do the second time


def test_migrate_leaves_an_unrelated_shortcut_and_startup_off(monkeypatch, tmp_path):
    fake, lnk = _fake_startup(monkeypatch, tmp_path)
    lnk.write_bytes(b"L\x00\x00\x00" + "notepad.exe".encode("utf-16-le"))
    assert not settings_ui.migrate_startup()
    assert lnk.exists() and not fake.values


def test_startup_command_uses_windowless_python():
    cmd = settings_ui.startup_command()
    exe = cmd.split('"')[1]
    assert Path(exe).name.lower() == "pythonw.exe" and Path(exe).exists()
    assert cmd.endswith("-m yappr")
