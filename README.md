# Murmur

Local-first hotkey dictation, meeting notes and read-aloud for Windows. Bring your own AI key.

Murmur does three things:

1. **Dictation anywhere.** Hold **Ctrl+Win** and talk, then let go, and cleaned-up text is pasted into whatever text box you're in.
2. **Meeting notes.** Click **Notes** on the small bar at the bottom of your screen, or accept the prompt when a calendar meeting starts. Murmur records your mic and the call audio, transcribes it on your machine, and writes a summary with next steps.
3. **Read aloud.** Highlight text anywhere and press **Ctrl+Alt+X**. A natural-sounding voice reads it to you, at the speed you choose. It's made for listening to AI replies: file paths are read as just the file name, links as the site name, and markdown symbols aren't read out.

Speech-to-text runs **locally** (NVIDIA Parakeet, on the CPU). **Audio never leaves your computer.** Only the transcribed *text* is sent to the AI model you choose, for cleanup and summaries. Without a key, Murmur still works and uses local cleanup rules. Read-aloud is fully local too (the open [Kokoro](https://huggingface.co/hexgrad/Kokoro-82M) voice, Apache-2.0, on the CPU): free, and Murmur never sends the text you highlight anywhere. (It's copied through the Windows clipboard for a moment, so if you've turned on Windows clipboard history or cloud clipboard sync, Windows sees it like any other copy.)

## Hotkeys

| Keys | What it does |
|---|---|
| Hold **Ctrl+Win** | Dictate while held; release to paste |
| **Ctrl+Win**, then **Space** | Hands-free: keeps listening after you let go |
| **Ctrl+Win** (while hands-free) | Stop and paste |
| **Alt+Shift+Z** | Paste the last result again (if it didn't land) |
| Ctrl+Win + any other key | Ignored, so Windows shortcuts like Ctrl+Win+→ still work |
| **Ctrl+Alt+X** | Read the highlighted text aloud (no need to copy). Press again to stop |
| **Ctrl+Alt+P** | Pause / resume reading |
| **Ctrl+Alt+]** / **Ctrl+Alt+[** | Read faster / slower (0.8×–2.0×, remembered) |

Murmur puts your previous clipboard text back after pasting, and asks Windows not to keep dictations in clipboard history.

> If another dictation app (e.g. Wispr Flow) is running with the same hotkey, quit it; otherwise both will react. The same goes for another read-aloud tool bound to Ctrl+Alt+X.

## Read aloud

Highlight text in any app (browser, AI chat, Claude, Cursor, Word, a PDF…) and press **Ctrl+Alt+X**. Murmur copies the highlight for you (your clipboard is put back right after), cleans it up for listening and starts speaking in under a second, even for a long reply: the first few words are voiced first, and the rest is prepared while you listen.

**Settings → Read aloud** has the voice (8 voices: US and UK, female and male), a speed slider and a *Hear sample* button. What gets cleaned up:

- `D:\home\me\project\murmur\app.py:42` → "app.py" (Windows, Unix and relative paths, with or without line numbers)
- `https://www.github.com/org/repo/...` → "github.com"
- `**bold**`, `# headings`, bullets, table pipes and backticks aren't read; tables are read row by row
- code blocks inside a reply are announced as "Code block" and skipped (if you highlight only code, it's read)

Pressing Ctrl+Win to dictate stops the reading, so the mic doesn't hear it.

## Install

Requirements: Windows 10/11, Python 3.10–3.13 (3.12 recommended), about 1 GB of disk.

```powershell
git clone https://github.com/jerahsiegal-source/murmur.git
cd murmur
powershell -ExecutionPolicy Bypass -File install.ps1
```

The installer creates `.venv`, installs dependencies, downloads the speech and voice models once (~750 MB) and adds **Murmur** to the Start Menu. Start it from there. A small pill appears at the bottom-centre of the screen, and a tray icon appears next to the clock.

## Set up your AI key (optional, recommended)

Right-click the bar (or tray icon → **Settings…**) → **AI cleanup**:

- **Provider**:
  - **Claude (Anthropic)**, the default. Uses `claude-haiku-5-5`: fast and cheap. Get a key at console.anthropic.com → API keys.
  - **OpenAI-compatible**: any chat-completions API. Set a **Base URL** and a model, for example:
    - OpenAI: `https://api.openai.com/v1` with `gpt-4.1-nano`
    - OpenRouter: `https://openrouter.ai/api/v1`
    - Groq: `https://api.groq.com/openai/v1`
    - Google Gemini: `https://generativelanguage.googleapis.com/v1beta/openai`
- **API key**: stored in Windows Credential Manager (one per provider), never in a file, and sent only to the provider you picked over https. See [SECURITY.md](SECURITY.md) for the details, and set a monthly spending limit in your provider's console.
- **$ / 1M tokens**: filled in for the default models, and used only for the local cost log shown on that tab.
- Click **Test connection**, then **Save**.

To keep dictation fully local and use AI only for meeting summaries, untick **Use AI cleanup for dictation**.

### What it costs

Measured request sizes: a 30-second dictation is about 400 input and 100 output tokens. A 90-minute meeting summary is about 24k input and 1k output tokens. At Claude Haiku 5.5 prices ($0.10 in / $0.50 out per 1M tokens; gpt-4.1-nano is about the same):

| Usage per month | Approx. cost |
|---|---|
| 100 dictations/day (3,000) | ~$0.27 |
| 20 meetings of 90 min | ~$0.06 |

The **AI cleanup** tab shows your real 30-day spend and a monthly projection from `usage.jsonl`.

## Meetings

- Click **Notes** on the bar to start, and **■ Stop** to finish. The bar shows a timer and live audio levels while recording.
- Murmur records two tracks: **Me** (your mic) and **Others** (whatever your speakers play). That works for Google Meet in a browser, Zoom, Teams, Slack, Discord and so on, with no bots joining the call.
- Long calls are fine. Audio goes to disk in 5-minute pieces, and each piece is transcribed during the call and then deleted. Memory stays flat, and the notes are ready seconds after you stop.
- Output goes to `Documents\Murmur\Meetings\<date time title>\`:
  - `summary.md`: Summary, Decisions, **Next steps**, Open questions, and Key moments with timestamps
  - `transcript.md`: the full timestamped transcript (`[0:42:17] **Others:** …`)
- **Settings → Meetings → Summarize again** re-runs the summary, for example after adding your key.

### Calendar prompt

Google Calendar → Settings → your calendar → **Secret address in iCal format** → paste it into **Settings → Meetings → Calendar iCal address**. When a meeting is about to start, Murmur asks "Start notes?". It never records on its own. All-day and "free" events are ignored. Any calendar that offers an iCal/ICS link works.

## Dictionary

**Settings → Dictionary**: add words Murmur should always spell your way (names, products, jargon). Fill in *Sounds like* with what the transcript writes instead (e.g. `Siobhan` ← `syabin, shivawn`). The dictionary applies to dictation, meeting transcripts and summaries.

## Storage, privacy and retention

| What | Where | Kept |
|---|---|---|
| Settings, dictionary, dictation history, cost log, app log | `%LOCALAPPDATA%\Murmur` | history: 90 days (adjustable) |
| Meeting notes | `Documents\Murmur\Meetings` (changeable; point it at a Google Drive folder to back up) | 90 days (adjustable) |
| Meeting audio | inside the meeting folder while recording | deleted as soon as each piece is transcribed |
| Dictation audio | memory only | never written to disk |
| API key | Windows Credential Manager | until you remove it |
| Text you read aloud | memory only (your clipboard is restored right after copying it) | never written to disk |

Network use: only the AI endpoint you configure (text only), the calendar feed if you set one, and a one-time model download from Hugging Face.

## Resource use (i7-12650H laptop)

- Idle: ~90 MB RAM, ~0% CPU, plus the read-aloud voice (below). The speech model unloads after 10 idle minutes (adjustable).
- Read aloud: the voice model stays loaded (about 200–300 MB) so reading starts in under a second at any time. It loads a few seconds after Murmur starts, so startup isn't slower. First words 0.4–0.8 s after the hotkey; no gaps up to 2.0×.
- While dictating: the model loads in ~2 s *while you talk*, using ~800 MB RAM until it unloads.
- Latency: text is pasted 0.2–0.7 s after you release the keys (local rules). Add your AI model's response time, typically 0.3–1 s.
- Meetings: about 6–15 s of background CPU per 5 minutes of call, at low priority.

## Development

```powershell
.venv\Scripts\python.exe -m pip install -e .[dev]
.venv\Scripts\python.exe -m pytest -q
git config core.hooksPath .githooks   # blocks commits that would add a key or personal data
```

`tools/` holds the end-to-end checks used during development: real hotkeys with a WAV file standing in for the mic (`MURMUR_FAKE_MIC`), a synthetic two-person meeting generator, a network/privacy logger and resource measurements. Set `MURMUR_TEST_CHORD=ctrl+shift` to run them without colliding with apps bound to Ctrl+Win, and `MURMUR_DATA_DIR` to keep test data separate.

## License

MIT. Read-aloud uses the Kokoro voice model (Apache-2.0) through [kokoro-onnx](https://github.com/thewh1teagle/kokoro-onnx) (MIT), which installs [espeak-ng](https://github.com/espeak-ng/espeak-ng) (GPL-3.0) for pronunciation; it is downloaded as a separate package, not bundled in this repo.
