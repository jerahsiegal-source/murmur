import time

from yappr.hotkeys import HotkeyMachine, VK_LCONTROL, VK_LWIN, VK_SPACE, VK_LMENU, VK_LSHIFT, VK_Z, HANDSFREE, IDLE

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


# ---- read aloud: Ctrl+Alt+X / P / ] / [
from yappr.hotkeys import VK_X, VK_P, VK_OEM_4, VK_OEM_6, VK_RMENU  # noqa: E402


def test_ctrl_alt_x_reads_and_key_is_swallowed():
    m = HotkeyMachine()
    r = feed(m, [(VK_LCONTROL, 1, 0), (VK_LMENU, 1, 0.05), (VK_X, 1, 0.1), (VK_X, 1, 0.15), (VK_X, 0, 0.2),
                 (VK_LMENU, 0, 0.3), (VK_LCONTROL, 0, 0.3)])
    assert events(r) == ["read"]  # auto-repeat of X does not toggle again; no mask (it would clear a terminal selection)
    assert r[2][0] and r[3][0] and r[4][0]  # X down, repeat and up all suppressed
    assert m.mode == IDLE


def test_pause_and_speed_keys():
    m = HotkeyMachine()
    r = feed(m, [(VK_LCONTROL, 1, 0), (VK_LMENU, 1, 0), (VK_P, 1, 0.1), (VK_P, 0, 0.2),
                 (VK_OEM_6, 1, 0.3), (VK_OEM_6, 1, 0.35), (VK_OEM_6, 0, 0.4),
                 (VK_OEM_4, 1, 0.5), (VK_OEM_4, 0, 0.6)])
    assert [e for e in events(r) if e != "mask"] == ["read_pause", "read_faster", "read_faster", "read_slower"]
    assert events(r).count("mask") == 4  # each swallowed key is masked so apps don't see a bare Ctrl+Alt


def test_read_keys_need_exactly_ctrl_alt():
    for mods in ([VK_LCONTROL], [VK_LMENU], [VK_LCONTROL, VK_LMENU, VK_LSHIFT], [VK_LCONTROL, VK_LMENU, VK_LWIN]):
        m = HotkeyMachine()
        seq = [(k, 1, 0) for k in mods] + [(VK_X, 1, 0.1), (VK_X, 0, 0.2)]
        r = feed(m, seq)
        assert "read" not in events(r), mods
        assert not r[len(mods)][0]  # X passes through to the app


def test_plain_x_typing_untouched():
    m = HotkeyMachine()
    assert feed(m, [(VK_X, 1, 0), (VK_X, 0, 0.1)]) == [(False, []), (False, [])]


def test_altgr_characters_are_not_swallowed():
    # AltGr = LCtrl + RAlt; on German/Polish layouts AltGr+[ / AltGr+X type characters
    for vk in (VK_X, VK_P, VK_OEM_4, VK_OEM_6):
        m = HotkeyMachine()
        r = feed(m, [(VK_LCONTROL, 1, 0), (VK_RMENU, 1, 0), (vk, 1, 0.1), (vk, 0, 0.2)])
        assert events(r) == [] and not r[2][0], hex(vk)


def test_right_ctrl_right_alt_still_reads():
    from yappr.hotkeys import VK_RCONTROL
    m = HotkeyMachine()
    r = feed(m, [(VK_RCONTROL, 1, 0), (VK_RMENU, 1, 0), (VK_X, 1, 0.1), (VK_X, 0, 0.2)])
    assert events(r) == ["read"]


# ---- copy while Ctrl+Alt are held: Alt must be pressed back down (else the next X is Ctrl+X = cut)
import yappr.paste as paste_mod  # noqa: E402
from yappr import hotkeys as hk  # noqa: E402


def _hook_with(monkeypatch, held):
    sent = []
    monkeypatch.setattr(paste_mod, "send_keys", lambda seq: sent.append(list(seq)))
    h = hk.KeyboardHook(lambda e: None)
    for vk in held:
        h._feed(vk, True)
    return h, sent


def test_copy_releases_alt_for_the_app_then_presses_it_back(monkeypatch):
    h, sent = _hook_with(monkeypatch, [VK_LCONTROL, VK_LMENU])
    h.copy(0x2D)
    first, second = sent
    assert (VK_LMENU, True) in first  # app sees plain Ctrl+Insert
    assert first.index((VK_LMENU, True)) < first.index((0x2D, False))
    assert first[0] == (VK_LCONTROL, False)  # Ctrl first: no menu, and terminals keep the selection
    assert (hk.VK_MASK, False) not in first and (VK_LCONTROL, True) not in first  # Ctrl stays held
    assert second[0] == (VK_LMENU, False) and second[-2:] == [(hk.VK_MASK, False), (hk.VK_MASK, True)]
    # the next X tap is still Ctrl+Alt+X for the hook, so it stops reading instead of cutting text
    sup, ev = h.machine.key(VK_X, True)
    assert sup and ev == ["read"]


def test_copy_does_not_press_back_a_key_the_user_let_go(monkeypatch):
    h, sent = _hook_with(monkeypatch, [VK_LCONTROL, VK_LMENU])
    orig = time.sleep

    def let_go(s):  # the user releases Alt during the copy
        h._feed(VK_LMENU, False)
        orig(0)
    monkeypatch.setattr(hk.time, "sleep", let_go)
    h.copy(0x2D)
    assert len(sent) == 1


def test_heal_releases_a_modifier_left_logically_down(monkeypatch):
    h, sent = _hook_with(monkeypatch, [VK_LCONTROL])
    h._repressed[VK_LMENU] = 0.0  # we pressed Alt back down, but the user had already let go
    monkeypatch.setattr(hk.user32, "GetAsyncKeyState", lambda vk: -32768 if vk == VK_LMENU else 0)
    h._heal_repressed(1.0)
    assert sent == [[(hk.VK_MASK, False), (hk.VK_MASK, True), (VK_LMENU, True)]]
    assert not h._repressed


def test_copy_without_ctrl_held_presses_and_releases_ctrl(monkeypatch):
    h, sent = _hook_with(monkeypatch, [VK_LMENU])
    h.copy(0x2D)
    first = sent[0]
    assert first[0] == (VK_LCONTROL, False) and first[-1] == (VK_LCONTROL, True)


def test_copy_while_holding_right_ctrl_never_leaves_left_ctrl_down(monkeypatch):
    from yappr.hotkeys import VK_RCONTROL
    h, sent = _hook_with(monkeypatch, [VK_RCONTROL, VK_LMENU])
    h.copy(0x2D)
    first = sent[0]
    assert first[0] == (VK_LCONTROL, False) and first[-1] == (VK_LCONTROL, True)
