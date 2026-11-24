from murmur.speech_text import chunks, clean_for_speech, file_name, site_name, spoken_len


def c(s):
    return clean_for_speech(s)


def test_windows_paths_become_file_names():
    assert c(r"I wrote the brief to D:\home\alex\Documents\Projects\Voice-to-text\INTENT-read-aloud.md today.") == \
        "I wrote the brief to INTENT-read-aloud.md today."
    assert c(r"See D:/home/me/repo/murmur/app.py:42 for details") == "See app.py for details."
    assert c(r"Log is in \\server\share\logs\murmur.log") == "Log is in murmur.log."


def test_quoted_paths_with_spaces():
    assert c(r"I found your old tool at `D:\home\alex\Text to speech tool`.") == \
        "I found your old tool at Text to speech tool."
    assert c('Open "C:\\Program Files\\Murmur\\murmur.exe" now') == "Open murmur.exe now."


def test_unix_and_relative_paths():
    assert c("Edit /home/me/project/src/main.ts and ~/notes/todo.md") == "Edit main.ts and todo.md."
    assert c("Changed murmur/app.py:136 and tests/test_hotkeys.py.") == "Changed app.py and test hotkeys.py."
    assert c("It lives in ./tools/run_timed.ps1") == "It lives in run timed.ps1."


def test_markdown_links_to_files_read_link_text():
    assert c("See [Bar.tsx:42](app/components/Bar.tsx:42) and [INTENT.md](INTENT.md).") == "See Bar.tsx and INTENT.md."


def test_words_with_slashes_are_left_alone():
    assert c("Use and/or either way, 1/2 cup, on 11/23/2026.") == "Use and/or either way, 1/2 cup, on 11/23/2026."


def test_urls_become_site_names():
    assert c("Docs at https://www.github.com/rhasspy/piper/blob/main/README.md.") == "Docs at github.com."
    assert c("Read <https://huggingface.co/onnx-community/Kokoro-82M-v1.0-ONNX>") == "Read huggingface.co."
    assert site_name("http://localhost:8080/x") == "localhost"


def test_markdown_symbols_not_read():
    text = (
        "## What changed\n\n"
        "- **Hotkeys**: `Ctrl+Alt+X` reads the highlight\n"
        "- *Speed* is saved\n"
        "1. First step\n"
        "> quoted note\n"
        "---\n"
        "| Keys | What it does |\n| --- | --- |\n| Ctrl+Alt+P | Pause |\n"
    )
    out = c(text)
    for junk in ("**", "#", "`", "|", "---", "> "):
        assert junk not in out
    assert out.split("\n") == [
        "What changed.",
        "Hotkeys: Ctrl+Alt+X reads the highlight.",
        "Speed is saved.",
        "1. First step.",
        "quoted note.",
        "Keys, What it does.",
        "Ctrl+Alt+P, Pause.",
    ]


def test_code_blocks_skipped_inside_prose_but_read_when_alone():
    prose = "Run this:\n```powershell\n.venv\\Scripts\\python.exe -m pytest -q\n```\nThen restart."
    assert c(prose).split("\n") == ["Run this:", "Code block.", "Then restart."]
    assert c("```\nprint('hi')\n```") == "print('hi')."


def test_arrows_emoji_and_snake_case():
    assert c("stop -> paste in 0.2 s ✅ 🎉") == "stop to paste in 0.2 s."
    assert c("set read_speed to ~1.3") == "set read speed to about 1.3."


def test_file_name_helper():
    assert file_name("D:\\home\\me\\") == "me"
    assert file_name("murmur/app.py:12:5") == "app.py"
    assert file_name("C:\\") == "C drive"


def test_real_ai_reply():
    reply = (
        "I found your old tool at `D:\\home\\alex\\Text to speech tool`. It's an AutoHotkey script that uses "
        "Piper voices. I wrote the brief to [INTENT-read-aloud.md](INTENT-read-aloud.md). Your existing "
        "[INTENT.md](INTENT.md) is the Murmur brief.\n\n"
        "- **What you get:** highlight text, press Ctrl+Alt+X, and it starts reading within about 1 second.\n"
        "- **Old tool:** see D:\\home\\alex\\AppData\\Roaming\\Microsoft\\Windows\\Start Menu\\Programs\\Startup\\Read Aloud.lnk"
    )
    out = c(reply)
    assert "alex" not in out and "\\" not in out and "**" not in out and "](" not in out
    assert "Text to speech tool" in out and "INTENT-read-aloud.md" in out


def test_chunks_short_first_then_sentences():
    text = c("Here's the short version of everything that changed in this branch today, with details. "
             "The second sentence is normal. Third.")
    cs = chunks(text)
    assert len(cs[0].text) <= 30
    assert " ".join(x.text for x in cs).replace("  ", " ") == text
    assert all(len(x.text) <= 150 for x in cs)


def test_chunks_cover_long_text_without_loss():
    para = ("Murmur reads highlighted text aloud using a local voice, so nothing leaves your computer. " * 40).strip()
    cs = chunks(para)
    assert " ".join(x.text for x in cs) == para
    assert all(len(x.text) <= 150 for x in cs)


def test_chunks_skip_symbol_only_pieces():
    assert chunks("...\n—\nHello there.") [0].text == "Hello there."


def test_short_opening_sentence_is_joined_with_the_next_words():
    cs = chunks("Done. I fixed the paste bug in paste.py and reran the tests: all 74 pass. See progress.md for the log.")
    assert cs[0].text.startswith("Done. I fixed")
    assert 20 <= len(cs[0].text) <= 30


def test_chunks_grow_gradually_so_playback_never_waits():
    para = " ".join(f"Sentence number {i} is a fairly ordinary sentence of normal length for a reply." for i in range(60))
    cs = chunks(para)
    total = spoken_len(cs[0].text)
    for c in cs[1:]:
        assert spoken_len(c.text) <= max(60, int(total * 1.2)) + 1  # covered by the audio already queued
        total += spoken_len(c.text)
    assert max(len(c.text) for c in cs) <= 150
    assert all(c.text.endswith("reply.") for c in cs[2:])  # once grown, sentences are never cut
    assert " ".join(c.text for c in cs) == para


def test_relative_windows_paths_and_dotfiles():
    assert c(r"Activate it with `.venv\Scripts\Activate.ps1` or run src\app\main.py.") == \
        "Activate it with Activate.ps1 or run main.py."
    assert c("Run `py -3.12 -m venv .venv` first.") == "Run py -3.12 -m venv .venv first."


def test_comparisons_and_spaced_slashes():
    assert c("Pin `numpy<2` and keep python>3") == "Pin numpy below 2 and keep python above 3."
    assert c("about $15 / 1M chars, cost / latency") == "about $15 per 1M chars, cost or latency."


def test_slash_lists_in_prose_are_kept():
    for s in ("client/server/database setups", "pros/cons/risks", "Q1/Q2/Q3", "Mon/Wed/Fri",
              "read/write/execute", "black/white/grey", "co-op/joint-venture/partnership", "TCP/IP"):
        assert c(s) == s + ".", s
    assert c("see src/app/main.py and src/components/") == "see main.py and components."


def test_programming_symbols_read_sensibly():
    assert c("Written in C# and F#.") == "Written in C sharp and F sharp."
    assert c("a 3 * 4 grid, 1920×1080") == "a 3 times 4 grid, 1920 times 1080."


def test_huge_selections_clean_quickly():
    import time
    for text in ("*a " * 30_000, "a. " * 50_000, "x" * 300_000):
        t = time.monotonic()
        c(text)
        assert time.monotonic() - t < 1.5


def test_digit_heavy_text_grows_slowly():
    text = c("Microsoft Windows. Version 10.0.26300.10075, build 2026.11.23, patch 4,512,331 of 9,000,000. Done.")
    cs = chunks(text)
    total = spoken_len(cs[0].text)
    assert total <= 30
    for ch in cs[1:]:
        assert spoken_len(ch.text) <= max(60, int(total * 1.2)) + 1
        total += spoken_len(ch.text)
