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
