# D4: on-screen wording review

Scope: every string a user can see.
- Window: 224 strings pulled from every page and state (welcome 1-3, Today new/set up, Notes meetings/dictations/empty, My words, Settings with both AI choices and "More AI options"), incl. placeholders and screen-reader labels -> `loop-ui/strings-window.txt` (regenerate: see the extraction in progress.md).
- Bar + meeting prompt + tray menu + bar messages (yappr/ui.py, yappr/app.py), installer (install.ps1).

Searched for: STT, speech-to-text, base URL, token(s), provider, API, model, iCal, LLM, endpoint, MME, JSON, transcribe/transcript, OpenAI-compatible, credential, hotkey, ICS, segment, quantize.

| Term on screen | Where | How it's handled |
|---|---|---|
| STT / speech-to-text / LLM / provider / endpoint / MME / JSON | — | Not shown anywhere. Old labels replaced: "Provider" -> "Which AI"; "API key" -> "Your key"; "Base URL" -> "Service address"; "Unload speech model after idle" -> "Free up memory after"; microphone names drop the ", MME" suffix; "AI cleanup" -> "AI helper"; "Dictionary" -> "My words". |
| OpenAI-compatible | Settings + welcome, "Which AI" choice | Shown as "Another AI service (OpenAI-compatible)", and the row says what it covers: "OpenAI, OpenRouter, Groq, Gemini or one running on this PC". |
| API keys | "Get one at console.anthropic.com → API keys" | Quoted as the menu name on Anthropic's site so people can find it; the field itself is "Your key". |
| Credential Manager | Your key | Named Windows feature, in a sentence that says what it means: "kept … never in a file, and only sent to the service you picked". |
| Model | Settings → More AI options only | Explained: "Which version of the AI to use. The default is fast and cheap." / "Leave blank to use the same model." Hidden by default. |
| token(s) | Settings → More AI options → Prices | Explained inline: "A token is about ¾ of a word. Only used for the estimate below." |
| iCal | Calendar link (Settings, welcome) | Field is "Calendar link"; "Secret address in iCal format" is quoted as Google Calendar's own label, with the click path. |
| transcript | Notes → "Full transcript" | Plain word (the full word-for-word text), shown under the summary. |
| log ("see log") | bar messages | Removed: "Meeting notes failed — see log" -> "Couldn't finish the notes. Try again in Yappr → Notes"; window error -> "Try again from the tray icon"; raw exception text no longer shown when recording can't start ("Check your microphone"). |
| Transcribing | bar message | "Transcribing the rest…" -> "Finishing your notes…". |
| Hotkey | — | Not shown; keys are drawn as keycaps (Ctrl + Win). |

Installer: steps say what and why in plain words ("Downloading the speech engine … It runs on this PC, so your voice never leaves it."); no "pip", "venv" or "model" in its messages. Python errors from pip itself can still appear if an install fails (unchanged).

Result: no term from the list appears without a plain explanation, and the technical ones sit behind "More AI options".
