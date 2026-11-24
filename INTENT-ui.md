# Intent: Modern, easy-to-use Yappr UI

## Outcome
Everything you see in Yappr looks modern, matches the Yappr brand, and is easy for someone who has never used it: the pill, tray menu, Settings, meeting prompt, notes/history views, installer and first launch. A new user is guided from install to their first dictation without reading the README.

## Why
Yappr is no longer just for the owner. Other people will install it from GitHub, and right now it looks dated and assumes you already know the hotkeys and settings. The redesign is for people who want to "actually use it": when ease of use and looks conflict, choose ease of use. Yappr has to stay a lightweight, local, fast app, because that is why people would pick it over Wispr Flow.

## Done when (all must pass)
- [x] **Look chosen first.** Done 2026-11-24: the owner picked Today (D) as the base, Notebook's (E) reader for notes, A's bar, and Skip's ears perking up while listening. Recorded in `DESIGN.md`, which is now **fixed**: build to it, and treat changes to it as a stop-and-ask.
- [ ] **Every visible surface uses the chosen design:** pill, tray icon and menu, Settings (all of AI cleanup, Dictionary, Meetings, History, General), meeting prompt, notes/history views, read-aloud UI, installer and first launch. Evidence: before and after screenshots of every surface, in light and dark mode, signed off by the owner.
- [ ] **First-run setup exists.** On a fresh install, a new person is guided to do their first dictation (Ctrl+Win) and, if they want, add an AI key. Both take about 2 minutes, guided only by the app. Evidence: a timed walkthrough on a clean profile in the real app, with screenshots.
- [ ] **No jargon on screen.** Terms like STT, base URL, tokens or provider never appear without a plain-language explanation. Evidence: a review of every on-screen string, with each term listed and how it is handled.
- [ ] **End-to-end:** fresh install → first run → dictation pastes → a meeting is recorded and its notes are shown → read-aloud works, all in the redesigned UI. Evidence: a run in the real app, with screenshots.
- [ ] **No regressions:** dictation, hands-free, Alt+Shift+Z re-paste, meetings, read-aloud, dictionary and history all behave as before. The existing test suite passes, and the `tools/e2e_*` scripts pass.
- [ ] **Not slower:** hotkey → paste latency, startup time and idle memory are no worse than before. Evidence: numbers measured before and after.
Partial completion is not done. If any item cannot be met, stop and report which and why.

## Never
- Make dictation slower, make startup slower, or use more memory while idle.
- Break or remove any existing feature.
- Send anything off the PC that isn't sent today: no new network calls, web fonts, analytics or telemetry.
- Lose existing settings, API keys, dictionary words or notes on upgrade.
- Quit or disable Wispr Flow (it shares the Ctrl+Win hotkeys).

## Stop and ask before
- Starting the build before the owner has picked a design direction.
- Adding a large UI dependency (for example, one that noticeably grows the install size or startup time). Say what it costs.
- Committing on top of, or otherwise changing, the uncommitted Yappr rename work on `rename/yappr-app`.

## Yours to decide
Everything not listed above: toolkit (Tkinter, a modern Tk theme, Qt, a web view… anything, as long as it stays light), layout, wording, the structure of the first-run flow, and order of work. Prefer what best serves the Why.
Workflow the owner intends: `/explore` to pick a direction, then `/design` and `/work-loop` to refine and finish against this brief.
