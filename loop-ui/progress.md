# Work loop: INTENT-ui.md

Base: rename/yappr-app @ 955d29e · Branch: ui/v1 (worktree ../yappr-ui, so the owner's running Yappr in Voice-to-text is untouched)

## Decisions
- State lives in loop-ui/ (loop/ belongs to the earlier INTENT.md loop on work-loop/v1).
- Toolkit: pywebview (Edge WebView2) for Home/Notes/Settings/first run, owner-approved gate 2026-11-24. Bar + meeting prompt stay Tk.
- E2E hotkeys use YAPPR_TEST_CHORD=ctrl+shift so Wispr Flow (Ctrl+Win) is never triggered.

## Found, not fixed

## Blocked

## Log
- Setup: branch ui/v1 from rename/yappr-app@955d29e (main lacks the rename). Worktree ../yappr-ui shares the venv via a junction.
- Baseline tests: 121 passed in 6.0 s. Regression check per item: full pytest (fast enough to run every time).
- Baseline D7 (base code, fake mic, ctrl+shift chord): launch -> "Yappr started" 1.35 / 1.94 / 1.72 s; idle working set 250 MB, private 240 MB at 20 s (3 runs identical); dictation stop -> paste 0.79 / 0.76 s (30 s WAV, hold mode). tools/measure_startup.py stalled (per-second process scan), so tools/measure_quick.py samples once.
- Decision: body font Segoe UI Variable (DESIGN fallback). Bundling Atkinson Hyperlegible means downloading font files, which needs the owner's OK; asked at handoff.
- Decision: the window runs as its own process (pywebview needs the main thread, which Tk owns; and it frees its memory when closed). It talks to the app over a named pipe with a random key; the page is inlined HTML (no local web server).
- Owner added mid-loop (2026-11-24): the bar must be movable (drag) and hideable. Recorded in DESIGN.md (Bar). Folded into D2 (bar surface) and checked in D5/D6. Position saved as screen fractions (bar_position), hide via right-click menu, tray and Settings.
- D3 pass (attempt 1 after fixes): blank window traced to a non-JSON value in state() (pywebview serializes answers as JSON) -> removed and covered by test_every_answer_the_page_reads_is_json; page start waited for pywebviewready; welcome comes to the front once; other-AI path kept inside the welcome.
- Decision: env-gated test driver in window.py (YAPPR_WINDOW_TEST_DIR, set only by tools) to drive the live page; off in normal use.
- D5 pass. Added YAPPR_FAKE_MEETING (+_SPEED) test hook: a recorded call played into a real MeetingSession, like YAPPR_FAKE_MIC for dictation. First read-aloud run reported silent_after_stop=false only because the test sentence ended before the stop key (it restarted reading); with longer text: stop is silent.
- D7 attempt 1 failed: new latency median 0.85 vs base 0.68. Cause: bar redraw cost during 'processing' (font objects created per measure, 60 ms ticks) competing with speech-to-text. Fix: cached fonts/widths, 250 ms ticks outside listening. Attempt 2: median 0.73, ranges overlap -> pass (honest note: ~0.05 s median difference is within run-to-run spread).
- Window memory while open is ~237 MB private, above the 80-150 MB estimate given to the owner at the toolkit gate. Freed on close; idle unchanged. Reported in handoff.
- D6 pass, D7 pass.
- Bar (owner requirement) verified live with tools/e2e_bar.py: drag (805,953)->(205,453), saved [0.187, 0.498], same spot after restart, right-click "Hide the bar" -> hidden, show_bar false saved. Found: the bar never takes keyboard focus (by design, so it can't steal typing), so its right-click menu is mouse-only; keyboard users hide/show it from Settings or the tray.

## Review round 1 (fresh reviewer): CHANGES, 3 blockers / 6 should / 3 nits
- F1 blocker retention data-loss: fixed. Empty/invalid number boxes never save (page) and save_settings rejects empty/negative/0-day retention instead of clamping; lowering retention asks first; all values validated before any is applied (also F10). Tests: test_retention_is_never_quietly_shortened, test_a_bad_value_changes_nothing (fail on the old code: 5 failed).
- F2 blocker WebView2 network: confirmed and fixed. Control run (no switches): 3 remote connections from msedgewebview2 within 70 s of launch (150.171.23.17:443, 150.171.29.11:443, 23.200.0.21:80). With WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS (no background networking, component update, SmartScreen, pings, domain reliability, phishing detection) + IsReputationCheckingRequired=False: 0 remote, 0 loopback over 120 s from launch while clicking through every page. tools/netwatch_window.py; results loop-ui/netwatch-control.json / netwatch-fixed.json.
- F3 blocker D5 'fresh install': agreed, D5 -> waiting on an install.ps1 run on a clean machine.
- F4 D3 human timing: agreed, D3 -> waiting on the owner's timed run.
- F5 window memory 237 MB vs 80-150 MB estimate: owner decision in handoff.
- F6 font: owner decision in handoff.
- F7 review page gaps: added read-aloud bar messages, Today/My words dark; tray menu + installer still text only (tray menu is drawn by Windows; installer not run here).
- F8 tray page ignored when window open: fixed (Api.take_page, page polls every 0.8 s while open). Test added.
- F9 back-to-back counter: script takes the expected word; reran.
- F11 esc() on numbers: done. F12 plain connection errors: plain_error(), test added.
