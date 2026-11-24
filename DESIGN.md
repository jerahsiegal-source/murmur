# Design

Source: `branding/yappr-icon.svg` (Skip the dog, the master icon) and the owner's pick from `explore/yappr-ui.html` (2026-11-24).

## Brand
- Colors: butter #ffe9a8 (highlight, primary buttons on dark), bark #5a3524 (accent), ink #2a1810 (text, dark surfaces), cream #fbf8f3 (background), tan #d9a46c / fawn #e8c39a (Skip's details), rose #ef8a9a (sparingly: recording, alerts with a word). Success #2e7d4f, danger #c8433f (default).
- Dark mode: background #1a1411, surface #241b17, ink #f4ebe0, muted #bba897, line #3a2d25, accent butter #ffe9a8.
- Type: body Atkinson Hyperlegible, bundled with the app (never downloaded at runtime), with Segoe UI Variable as the fallback. Headings in the same family at 600–700. Numbers use tabular figures. (default)
- Shape: radius 12–14px for windows and panels, 999px for the bar and chips, thin 1px lines, soft shadows only on floating things (the bar, prompts).
- Logo: Skip appears on the bar, in the title bar, and on first run. Never stretched or recoloured.
- Voice: plain, warm, brief. Say what happens ("Take notes now"), not how it works.

## Look
- Style: **Today**, a warm home-screen app (direction D), with Notebook's reader for notes (direction E).
- Density: balanced. Home is scannable at a glance, and notes are airy for reading.
- One bold move: **Skip lives in the bar** and his ears perk up while he's listening.

## Pages
- **Bar (always on screen):** shaped like direction A's bar. It's a dark ink pill with Skip on the left, "Hold Ctrl+Win to talk", and a butter **Notes** button. States: ready → listening (Skip's ears perk up, plus a sound wave and "Listening… let go to paste") → pasted ("✓ Pasted 42 words") → meeting (● recording timer plus ■ Stop). It can also show D's next-meeting countdown when a meeting is close. **Owner requirement (2026-11-24):** you can drag the bar anywhere (it remembers the spot), and hide it from its right-click menu, the tray menu or Settings. Hotkeys keep working when it's hidden.
- **Home (opens by default):** direction D. Next-meeting card at the top, today's numbers (words dictated, dictations, meetings, all real counts only), a timeline of today's dictations and notes, and a setup checklist on the right until setup is done. Icon rail on the left: Today, Notes, My words, then Settings at the bottom.
- **Notes:** direction E's two-pane reader. Meetings and dictations are grouped by day on the left. On the right are the summary, next steps as checkboxes, and the full transcript behind a click.
- **Settings:** in Today's palette and spacing, not stock Windows. Every setting has a plain one-line "what this does" (from A). Sections: AI helper, My words, Meetings, Read aloud, General.
- **First run:** D's checklist (try a dictation ✓ → AI helper, optional → connect calendar), which you can come back to from Home. No one-time wizard.
- **Meeting prompt:** a small floating card in the bar's style: "Design sync is starting" with **Take notes** and **Not now** buttons.

## Never
- Redesign Skip. New poses (ears up, wag) must match the existing icon's shapes and colours.
- Show status by colour alone. Recording, connected and errors always pair an icon with a word.
- Show made-up stats. If a number can't be counted honestly (e.g. "time saved"), leave it out.
- Load fonts, images or anything else from the internet.
