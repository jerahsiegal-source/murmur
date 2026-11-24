# Handoff: Yappr product video

## Summary
A 16:9 product video for Yappr, 51.3 seconds, at `video/out/yappr-demo.mp4` (1920x1080, H.264 + AAC, web-ready MP4). Branch `video/v1` (from `main`), not pushed. Nothing under `yappr/`, `tests/` or `tools/` changed.

Scenes: Skip's two-yap intro, the "open source Wispr Flow + Speechify" pitch, dictation into Mail (Edge), dictation into Team chat (Chrome), read aloud in a Reader page (Edge), pasting an API key in Yappr's settings, end card. Exact times are in `loop-video/timeline.json`.

## Done items
| | Item | Evidence |
|---|---|---|
| D1 | One 16:9 file, 30-60 s, web format | ffprobe: h264 1920x1080 30 fps, aac 48 kHz, faststart |
| D2 | Dictation into a real app | Mail and Team chat scenes; app log shows the "um", "uh" and doubled "the" removed by the app's own rules |
| D3 | Read aloud, audibly | Reader scene; the audio is the app's own speech recorded from the speakers |
| D4 | Pasting an API key (dummy) | Settings scene ends on "✓ Key saved"; the key is a made-up demo value |
| D5 | Pitch names Wispr Flow + Speechify | Pitch card, narration, end card |
| D6 | Real app footage, polished | Take 3 of the real app; contact sheet in `loop-video/stills/` |
| D7 | Music + AI voiceover + captions | Mix levels measured, no silent gaps, captions on every app scene |
| D8 | App colours, logo, Skip | Stills in `loop-video/stills/` |
| D11 | Nothing in the app broken | pytest 169 passed (same as baseline); only `video/`, `loop-video/`, `INTENT-video.md` added |

## Not done
- Nothing. D9 and D10 passed on the owner's sign-off of the final file (2026-11-24).

## Decisions made
- Narration by Kokoro, the voice Yappr ships (Apache-2.0, local, free).
- Music composed in code (`video/music.py`): no third-party licence.
- Demo runs on an empty throwaway profile behind a full-screen backdrop, in Edge and Chrome on empty temporary profiles. Word (shows the account name) and Notepad (reopens old tabs) were avoided.
- A throwaway key store was used for the recording, so the real key in Windows Credential Manager was never read or overwritten.
- Skip's body, legs and tail are new drawing in the icon's colours; his head is the icon's paths unchanged.
- `video/build/` and `video/out/` are git-ignored (large generated files).

## What is real and what is a stand-in
- Real: the app, its bar, its window, the speech-to-text, the tidy-up, the pasted text, the read-aloud voice, the "Key saved" message.
- Stand-ins: the dictating "person" is an AI voice fed through the app's fake-microphone test hook; the hotkey pressed was the Ctrl+Shift test chord (so Wispr Flow stayed quiet) while the app and captions say Ctrl+Win, which is the real hotkey; the dummy key went to a throwaway file, while the caption describes where the product keeps keys.
- Edits: zooms and captions; a cut over about 7 s of the Yappr window loading; the key scene runs at 1.35x; a cut over Edge's selection toolbar.

## Found, not fixed
- The end card shows `github.com/jerahsiegal-source/yappr` (the public repo address, which contains the owner's name). Left in after the owner reviewed the cut; one line in `video/compose.py` (`outro`) removes it.
- The agent cannot hear. Narrator, music, the synthesised yap and their balance are unverified by ear.
- The Today page is on screen for a moment with the warm-up dictation listed, so one line appears twice.
- Re-recording needs Yappr stopped and the screen left alone for about 2 minutes (`video/record.py`).

## Review
One round, fresh reviewer: APPROVE. Fixed: "stays on your PC" reworded to "stored only on your PC" (caption and narration); bar close-up shortened and less zoomed (busy-spinner and jagged zoom); spoken-words caption made one line; stale log line; dead code. Declined as nits: pointer resting on "Test connection" after Save; narration running 1.3 s into the chat scene.

## Cross-model review prompt
> Review branch `video/v1` of this repo against `INTENT-video.md` using the work-loop reviewer brief. Read `loop-video/handoff.md`, `loop-video/done.json` and `loop-video/progress.md`. The deliverable is `video/out/yappr-demo.mp4`: extract a frame per second and check for anything personal, typos, and that each Done item is visible; check every caption and narration line in `video/script.py` and `video/compose.py` against `README.md`. Do not run `video/record.py` (it takes over the screen). Report VERDICT and findings.

## Owner's checklist
1. Play `video/out/yappr-demo.mp4` with sound on. Is the yap right? Narrator voice? Music level?
2. Play it once muted. Does it still make sense from the captions?
3. Pause on each scene: anything personal, any typo, anything that looks off?
4. Decide whether the GitHub address stays on the end card.
5. To rebuild after a wording change: `.venv\Scripts\python.exe video\voice.py` then `.venv\Scripts\python.exe video\compose.py`.
