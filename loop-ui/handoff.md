# Handoff: modern, easy-to-use Yappr UI (INTENT-ui.md)

## Summary
- **Branch:** `ui/v1`, built on `rename/yappr-app` (955d29e). Worktree: `C:\Users\33goa\Documents\Projects\yappr-ui`; your own checkout (`Voice-to-text`) was left on `rename/yappr-app` and your Yappr keeps running from it.
- **What's new:**
  - **Bar:** dark pill with Skip, whose ears go up while he listens. It shows plain states ("Listening… let go to paste", "Typing it out…", "✓ Pasted 42 words", "Taking notes 0:12:43", a next-meeting countdown). Drag it anywhere and it remembers the spot; hide it from its right-click menu, the tray or Settings.
  - **Yappr window:** pywebview, its own process, only while open. Pages: **Today** (next meeting, today's numbers, timeline, setup checklist), **Notes** (meeting reader + dictation history), **My words**, **Settings** (one page, plain wording, auto-save), and a 3-step **welcome** that opens on first run.
  - **Meeting prompt and tray menu** restyled and reworded.
  - **Installer:** friendly numbered steps, then it starts Yappr.
- **Commits:** f76cf07 (brief/design) → b1aecd0 (D3 window + bar) → installer → D4 → D5 → D6/D7 → bar drag test → review page → 793776f (review fixes). Tests: 121 → 151, all passing.

## Done items
| | Item | Status | Evidence |
|---|---|---|---|
| D1 | Look chosen first | ✓ pass | DESIGN.md |
| D2 | Every surface in the new design | ⏳ **needs you** | `loop-ui/review.html`: before/after for every surface, light + dark |
| D3 | First-run setup | ⏳ **needs you** (timed run by hand) | Scripted run on a new profile passes: `loop-ui/shots/first-run-1..6.png` |
| D4 | No jargon | ✓ pass | `loop-ui/jargon-review.md` |
| D5 | End to end | ⏳ **needs you** (installer on a clean machine) | Everything after install passes in the real app: `first-run-1..9.png` |
| D6 | No regressions | ✓ pass | 151 tests; hold, hands-free, re-paste, back-to-back, read-aloud, meeting |
| D7 | Not slower | ✓ pass | startup 1.0–1.2 s (was 1.35–1.94 s); idle 250 MB (was 250); stop→paste median 0.73 s (was 0.68 s, ranges overlap) |

## Decisions waiting on you
1. ~~Window memory~~ **Decided 2026-11-24: keep pywebview.** The owner accepted about 237 MB while the window is open (freed on close; idle unchanged).
2. ~~Font~~ **Decided 2026-11-24: keep Segoe UI Variable.** DESIGN.md updated.
3. **D2 sign-off** on `loop-ui/review.html`.

## Not done (needs a person or a clean machine)
- **D3:** a timed run by hand. A new person, Ctrl+Win, a real Claude key: about 2 minutes, guided only by the app?
- **D5:** `install.ps1` on a clean machine (it now starts Yappr, which opens the welcome). Not run here, because it would reinstall into your environment and download about 750 MB.
- **Tray menu and installer screenshots:** described in text only.

## Decisions made (yours to undo)
- The window runs in its own process and talks to the app over a named pipe with a random key. Reason: Tk owns the main thread, and closing the window frees its memory.
- The page is inlined HTML: no local web server, nothing loaded from the internet. WebView2's own background traffic (updater, SmartScreen, pings) is switched off. Control run: 3 outside connections; fixed: 0 over 120 s (`netwatch-control.json` / `netwatch-fixed.json`).
- Settings save as you change them. Empty or invalid number boxes never save, and lowering "keep for N days" asks first.
- Renamed on screen: "AI cleanup" → "AI helper", "Dictionary" → "My words", "Provider" → "Which AI", "Base URL" → "Service address".
- People who already used Yappr or Murmur (they have history) skip the welcome.
- Test-only switches, off unless set: `YAPPR_FAKE_MEETING` (a recorded call instead of the devices) and `YAPPR_WINDOW_TEST_DIR` (lets e2e scripts drive the window).
- After a finished dictation the bar briefly shows "✓ Pasted N words" (new).

## Found, not fixed
- The bar never takes keyboard focus (on purpose, so it can't steal your typing), so its right-click menu is mouse-only. Keyboard users use Settings or the tray.
- `tools/measure_startup.py` stalls on this PC (it scans every process each second; one scan takes about 19 s). `tools/measure_quick.py` replaces it for these numbers.
- One back-to-back run was cancelled by a stray key 24 ms after the chord; the next two runs passed 2/2.
- Read aloud has no state of its own on the bar (it shows messages only), the same as before.

## Cross-model review prompt (paste into Codex)
> Review branch `ui/v1` of this repo (base `rename/yappr-app`) against `INTENT-ui.md` and `DESIGN.md`, using the reviewer brief in the work-loop skill (`references/reviewer-brief.md`). Loop state: `loop-ui/done.json`, `loop-ui/progress.md`, `loop-ui/handoff.md`. Focus: `yappr/api.py` (named-pipe API, settings validation), `yappr/window.py` (WebView2 switches), `yappr/web/app.js` (escaping, auto-save), `yappr/ui.py` (bar drag/hide, redraw cost). Read and run `pytest` only; don't start the app or press hotkeys. Output: VERDICT plus findings [blocker|should|nit].

## Staging checklist (repeat by hand)
1. On a clean Windows PC: `git clone`, check out `ui/v1`, then run `powershell -ExecutionPolicy Bypass -File install.ps1`. The steps read clearly, and at the end Yappr starts and the welcome opens.
2. Welcome: click in the box, hold **Ctrl+Win**, talk, let go → the text appears and Next lights up. Time it.
3. Paste a real Claude key → "Check and save" → ✓. Finish → Today shows the checklist.
4. Dictate into Notepad and an email → it pastes; the bar shows Skip's ears up while listening and "✓ Pasted".
5. Drag the bar somewhere, restart Yappr → same spot. Right-click → Hide the bar; tray → Show the bar.
6. Click **Notes** on the bar during a real call → Stop → the notes show in Yappr → Notes.
7. Highlight text, **Ctrl+Alt+X** → it reads; press again → it stops.
8. Settings: clear "Keep notes for" and click away → "Enter a number. Nothing was saved."
9. Switch Windows to dark mode, reopen Yappr → dark pages.
