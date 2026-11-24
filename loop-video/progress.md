# Work loop: INTENT-video.md

Base: main @ f8d663d · Branch: video/v1 (same checkout; only new files under video/ and loop-video/)

## Decisions
- State lives in loop-video/ (same convention as loop-ui/).
- Voiceover: Kokoro, the voice Yappr itself ships (Apache-2.0, already on disk). Free, local, licensed for public use.
- Music: composed in code for this video (video/music.py), so there is no third-party licence at all.
- Titles, captions, zooms: rendered with Pillow + ffmpeg from video/ scripts. No new installs.
- Footage: the real app on a throwaway profile (YAPPR_DATA_DIR), speech fed through YAPPR_FAKE_MIC, hotkey YAPPR_TEST_CHORD=ctrl+shift so Wispr Flow is never triggered.
- API-key scene: a made-up key is pasted and saved; "Test connection" is not shown (it would need a real key and a paid call).

## Found, not fixed

## Blocked

## Log
- Setup: branch video/v1 from main@f8d663d. Baseline: 169 passed in 8.6 s. Regression check per item: full pytest + `git status` shows only video/ and loop-video/ added.
- Machine: one display, 1536x864 logical. Two Yappr instances are running (the checkout's venv and a system Python 3.12 one). Recording needs them stopped and the screen left alone for a few minutes: owner gate.
- Prep done without touching the screen: script (video/script.py), narration + demo speech via Kokoro (video/voice.py, 20.2 s narration, 7.1 s speech), music composed in code (video/music.py, 48 s), title cards (video/gfx.py), 9 s sample video/out/yappr-teaser.mp4 (1920x1080 h264/aac). Stills of both cards checked: brand colours, logo, no typos.
- Found: a saved API key goes to Windows Credential Manager under "Yappr" whatever YAPPR_DATA_DIR says. A throwaway-profile app would read the owner's real key (paid calls) and the key scene would overwrite it. Decision: the recording run uses a throwaway key store (PYTHON_KEYRING_BACKEND pointing at a file-backed store in video/build), so the real key is never read or changed.
- Decision: dictation and read-aloud are shown in an Edge app window with a temporary profile (Win11 Notepad restores the owner's open tabs, which could show personal notes).
- GATE (owner): recording needs the two running Yappr instances stopped (single-instance lock), and the screen, keyboard and speakers left alone for about 10 minutes. Waiting. 0/11 passing, 0 blocked.
- Owner (2026-11-24): go ahead and record; open with full-body Skip doing a little yap; show it works in several programs and tidies up; nothing personal on screen. Added to scope.
- Recording (video/record.py): owner's Yappr stopped with permission, restarted after (log: "Yappr started" 14:28). Take 1 stopped safely (second window not in front). Take 2 complete but the Chrome window never showed. Take 3 good: video/build/take3-good. Real results from the app: "Hey Sam, um, thanks..." typed without the "um"; "I'll uh, send the the invite list" typed as "I'll send the invite list" (method: rules, no AI call); read-aloud heard 0.8 s after Ctrl+Alt+X; settings showed "✓ Key saved" for the dummy key, which went only to video/build/demo-keys.json.
- Privacy: contact sheet of take 3 (one frame per 1.5 s, 39 frames) shows only the backdrop, the three demo windows, Yappr's bar and Yappr's window. No desktop, taskbar, notifications or other apps.
- Decision: two real programs, Edge (Mail, Reader) and Chrome (Team chat), both on empty temporary profiles, showing pages written for the demo with made-up names. Word shows the account name in its title bar, and Notepad restores old tabs, so neither was used.
- Decision: Skip's body, legs and tail are new drawing (video/skip.py) using only the icon's colours; his head is the icon's paths unchanged. The yap is synthesised. Both need the owner's eye and ear.
- Edit (video/compose.py), first render: 52.7 s (superseded; current times are in loop-video/timeline.json). The key scene skips ~7 s of the window loading and runs at 1.35x.
- Final render: video/out/yappr-demo.mp4, 52.13 s. Fixed after first render: framing of the mail, bar and key shots; Skip larger; Edge's selection toolbar covered two highlighted words, so the read scene now cuts from just before the triple-click to just after the toolbar has gone.
- D1-D8, D11 pass. D9 and D10 wait on the owner (Stop-and-ask: owner reviews the full video before it is final). 9/11 passing, 0 blocked.

## Found, not fixed
- The end card shows the repo address from the README, which contains the owner's GitHub username. Owner decides whether that is wanted.
- The agent cannot hear: narration voice, music, the yap and the mix balance are unverified by ear.
- video/out and video/build are git-ignored (large generated files); the scripts rebuild them, except the take itself, which needs a recording session.

## Review round 1 (fresh reviewer): APPROVE, 0 blockers / 3 should / 7 nits
- F1 repo address with the owner's name on the end card: owner decision; left in (owner said "Looks good" after it was pointed out twice).
- F2 "stays on your PC" overstated (the key is sent to the chosen AI provider): fixed, caption and narration now say "stored only on your PC".
- F3 busy-spinner over the bar and jagged zoom: fixed, zoom 1.8x and the shot ends before the click's spinner (checked at 38.0, 38.15, 38.3).
- F4, F5, F9, F10: fixed. F6 (pointer rests on "Test connection"), F8 (narration runs 1.3 s into the chat scene): declined as nits. F7: disclosure kept in handoff.
- Final file: video/out/yappr-demo.mp4, 51.33 s, 4.83 MB, mean -16.5 dB, max -0.6 dB, no silent gaps. pytest 169 passed.
- Stop: 9/11 passing, 0 blocked. D9 and D10 wait on the owner's last look at the final file (Stop-and-ask: owner reviews before it is called final). Branch not pushed.
- Owner sign-off 2026-11-24 on the final file ('Yes, finished'): D9 and D10 pass. 11/11 passing. GitHub address stays on the end card.
