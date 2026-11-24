"""Uses the real Windows clipboard; puts the user's clipboard back afterwards."""
import pytest

from yappr import paste


@pytest.fixture
def keep_user_clipboard():
    snap = paste.snapshot_clipboard()
    yield
    if snap is not None:
        paste.restore_clipboard(snap)


def test_snapshot_restores_non_text_formats(keep_user_clipboard):
    import ctypes

    fmt = paste.user32.RegisterClipboardFormatW("Yappr Test Binary")
    assert paste._open_clipboard()
    try:
        paste.user32.EmptyClipboard()
        data = bytes(range(256)) * 10
        h = paste.kernel32.GlobalAlloc(paste.GMEM_MOVEABLE, len(data))
        p = paste.kernel32.GlobalLock(h)
        ctypes.memmove(p, data, len(data))
        paste.kernel32.GlobalUnlock(h)
        paste.user32.SetClipboardData(fmt, h)
    finally:
        paste.user32.CloseClipboard()
    snap = paste.snapshot_clipboard()
    paste.set_clipboard_text("dictated words")
    assert paste.get_clipboard_text() == "dictated words"
    assert paste.restore_clipboard(snap)
    after = dict(paste.snapshot_clipboard())
    assert after[fmt][:len(data)] == data
    assert paste.get_clipboard_text() is None


def _put(formats):
    import ctypes

    assert paste._open_clipboard()
    try:
        paste.user32.EmptyClipboard()
        for fmt, data in formats:
            paste.user32.SetClipboardData(fmt, paste._alloc_bytes(data))
    finally:
        paste.user32.CloseClipboard()


def test_password_manager_privacy_marker_survives(keep_user_clipboard):
    # a password manager's copy: text + "don't keep in clipboard history"
    secret = "hunter2".encode("utf-16-le") + b"\0\0"
    _put([(paste.CF_UNICODETEXT, secret), (paste._EXCLUDE_FMT, b"\0\0\0\0")])
    snap = paste.snapshot_clipboard()
    paste.set_clipboard_text("dictated words")
    paste.restore_clipboard(snap)
    after = dict(paste.snapshot_clipboard())
    assert paste._EXCLUDE_FMT in after
    assert paste.get_clipboard_text() == "hunter2"


def test_snapshot_over_budget_still_keeps_text(keep_user_clipboard):
    big = paste.user32.RegisterClipboardFormatW("Yappr Test Big")
    _put([(paste.CF_UNICODETEXT, "keep me".encode("utf-16-le") + b"\0\0"), (big, b"x" * 2_000_000)])
    snap = dict(paste.snapshot_clipboard(budget_bytes=1_000_000))
    assert big not in snap
    paste.set_clipboard_text("dictated")
    paste.restore_clipboard(list(snap.items()))
    assert paste.get_clipboard_text() == "keep me"
