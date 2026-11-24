from murmur.hotkeys import HotkeyMachine, VK_LCONTROL, VK_LWIN, VK_SPACE, VK_LMENU, VK_LSHIFT, VK_Z, HANDSFREE, IDLE

D = 0x44  # 'D'


def feed(m, seq):
    out = []
    for vk, down, t in seq:
        sup, ev = m.key(vk, down, t)
        out.append((sup, ev))
    return out


def events(res):
    return [e for _, ev in res for e in ev]


def test_hold_to_talk_ctrl_then_win():
    m = HotkeyMachine()
    r = feed(m, [(VK_LCONTROL, 1, 0), (VK_LWIN, 1, 0.1), (VK_LWIN, 1, 0.5), (VK_LWIN, 0, 2.0), (VK_LCONTROL, 0, 2.1)])
    assert events(r) == ["mask", "start", "stop"]
    assert m.mode == IDLE


def test_hold_win_then_ctrl_release_ctrl_first():
    m = HotkeyMachine()
    r = feed(m, [(VK_LWIN, 1, 0), (VK_LCONTROL, 1, 0.1), (VK_LCONTROL, 0, 1.5), (VK_LWIN, 0, 1.6)])
    assert events(r) == ["mask", "start", "stop"]


def test_short_tap_cancels():
    m = HotkeyMachine()
    r = feed(m, [(VK_LCONTROL, 1, 0), (VK_LWIN, 1, 0.05), (VK_LWIN, 0, 0.15), (VK_LCONTROL, 0, 0.2)])
    assert events(r) == ["mask", "start", "cancel"]


def test_handsfree_then_stop_with_chord():
    m = HotkeyMachine()
    r = feed(m, [(VK_LCONTROL, 1, 0), (VK_LWIN, 1, 0.1), (VK_SPACE, 1, 0.3)])
    assert r[-1] == (True, ["handsfree"])  # space suppressed
    r = feed(m, [(VK_SPACE, 0, 0.4), (VK_LWIN, 0, 0.5), (VK_LCONTROL, 0, 0.6)])
    assert r[0][0] is True  # space key-up suppressed too
    assert events(r) == []
    assert m.mode == HANDSFREE
    r = feed(m, [(VK_LCONTROL, 1, 10), (VK_LWIN, 1, 10.1), (VK_LWIN, 0, 10.2), (VK_LCONTROL, 0, 10.3)])
    assert events(r) == ["mask", "stop"]
    assert m.mode == IDLE
    # the next chord starts a fresh dictation
    r = feed(m, [(VK_LCONTROL, 1, 20), (VK_LWIN, 1, 20.1)])
    assert events(r) == ["mask", "start"]


def test_windows_shortcut_cancels_and_passes_through():
    m = HotkeyMachine()
    r = feed(m, [(VK_LCONTROL, 1, 0), (VK_LWIN, 1, 0.1), (D, 1, 0.2)])
    assert r[-1] == (False, ["cancel"])
    r = feed(m, [(D, 0, 0.3), (VK_LWIN, 0, 0.4), (VK_LCONTROL, 0, 0.5)])
    assert events(r) == []


def test_space_without_chord_is_untouched():
    m = HotkeyMachine()
    assert feed(m, [(VK_SPACE, 1, 0), (VK_SPACE, 0, 0.1)]) == [(False, []), (False, [])]


def test_alt_shift_z_pastes_last_and_is_suppressed():
    m = HotkeyMachine()
    r = feed(m, [(VK_LMENU, 1, 0), (VK_LSHIFT, 1, 0.1), (VK_Z, 1, 0.2), (VK_Z, 0, 0.3), (VK_LSHIFT, 0, 0.4), (VK_LMENU, 0, 0.5)])
    assert r[2] == (True, ["mask", "paste_last"])  # mask stops Alt+Shift switching keyboard layout
    assert r[3][0] is True


def test_plain_z_untouched():
    m = HotkeyMachine()
    assert feed(m, [(VK_Z, 1, 0)]) == [(False, [])]


def test_ctrl_alt_win_does_not_start():
    m = HotkeyMachine()
    r = feed(m, [(VK_LMENU, 1, 0), (VK_LCONTROL, 1, 0.1), (VK_LWIN, 1, 0.2)])
    assert events(r) == []


def test_test_chord_ctrl_alt_and_product_chord_ignored():
    m = HotkeyMachine("ctrl+alt")
    assert events(feed(m, [(VK_LCONTROL, 1, 0), (VK_LMENU, 1, 0.1), (VK_LMENU, 0, 1.0), (VK_LCONTROL, 0, 1.1)])) == ["mask", "start", "stop"]
    # Ctrl+Win does nothing under the test chord (so it can't collide with other apps' hotkeys)
    assert events(feed(m, [(VK_LCONTROL, 1, 2), (VK_LWIN, 1, 2.1), (VK_LWIN, 0, 3), (VK_LCONTROL, 0, 3.1)])) == []


def test_bad_chord_rejected():
    import pytest

    with pytest.raises(ValueError):
        HotkeyMachine("ctrl+q")
