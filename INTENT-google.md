# Intent: Connect Google Calendar with one click

## Outcome
In Settings → Meetings (and on the welcome screen) there is a **Connect Google Calendar** button. It opens Google's sign-in in the normal browser. After you approve, Yappr shows "Connected as you@…" with a **Disconnect** button, and from then on:
- the "Start notes?" prompt comes from your Google Calendar (no iCal link to dig out), and skips meetings you declined;
- meeting notes use the event's title, and `summary.md` lists the attendees and the Meet link at the top. Attendee names go to the AI so it spells them right.

The iCal link stays as "Other calendar" for Outlook and others.

## Why
Finding Google's "secret address in iCal format" is the hardest step of setup, and most people never get through it. One click is the normal way apps do this. The calendar event also knows things that make the notes better (who was there, which call it was).

Owner-only for now (Google Cloud project in test mode, owner as test user). Later anyone on GitHub should be able to use it after Google reviews the app, and that should need paperwork only, no code changes.

## Done when (all must pass)
- [ ] **Sign-in works:** the standard Google flow for desktop apps: system browser, loopback redirect on 127.0.0.1, PKCE and a state check. Access is read-only: `calendar.events.readonly` plus `openid email`. Evidence: a live connect in the real app on the owner's account, and unit tests for the flow against a fake Google.
- [ ] **Saved safely:** the refresh token lives only in Windows Credential Manager (`Yappr / google-refresh-token`), and the access token only in memory. It is never in settings.json, the logs or the repo. Disconnect revokes the access at Google and deletes the token. Evidence: tests plus a check of settings.json and the log after a live connect.
- [ ] **Prompts come from Google:** while connected, events come from the Calendar API (primary calendar). All-day, "free", cancelled and declined events are skipped. If the token is revoked or expired, Settings says so in plain words and asks you to reconnect, and nothing crashes. Evidence: tests and a live prompt.
- [ ] **Better notes:** a meeting started from a Google event gets the event title, an attendee list and the Meet link in `summary.md`. Only attendee names (not emails) go to the AI. Evidence: tests and a live meeting.
- [ ] **iCal still works** for people who don't connect Google. Evidence: the existing calendar tests pass.
- [ ] **Docs:** README and SECURITY.md say what is stored, where, and which Google addresses Yappr contacts. A step-by-step guide covers the owner's Google Cloud setup.
- [ ] **No regressions:** the full test suite passes. Dictation, hotkeys and startup are unchanged.

**Progress 2026-11-24 (branch `google/connect`, not committed):** the code, tests and docs are written. `yappr/google_auth.py` handles sign-in. The Google source is in `calendar_watch.py`, attendees and the call link in `meeting.py`, and Connect/Disconnect in Settings and the welcome. There are 17 new tests against a fake Google, and the full suite passes (169). The secret scan now also catches Google tokens and client files. Screens were checked with `tools/ui_preview.py` (Settings connected and not connected, and Notes with attendees). **Live 2026-11-24 11:5x:** the owner created Google Cloud project `yappr-515716` (External, Testing, owner as test user; scopes `openid`, `userinfo.email`, `calendar.events.readonly`) and a Desktop client, installed at `%LOCALAPPDATA%\Yappr\google-client.json`. Yappr was restarted on this branch and the owner connected. Checked: the refresh token is in Credential Manager; settings.json holds only the email address; the log has no token or code; the Calendar API answered with 6 events across yesterday to 7 days out, all of them timed meetings. **Live test 2026-11-24 11:55:** a test event ("Yappr test call", Meet link, one example.com guest, no invites sent) prompted "Start notes?" 5 minutes before the start, which matches the owner's setting. The owner started notes from the prompt. state.json holds the event, summary.md lists With / Call / Calendar, and parse_summary reads all three. Only the guest's name reached the AI. The owner didn't see the "Open in Google Calendar" button; the data is there, and the button shows in Yappr → Notes at the bottom of that meeting. The owner said it isn't needed. The test event was deleted afterwards.

## Never
- Ask Google for more than read-only calendar access plus your email.
- Store tokens outside Credential Manager, or log them.
- Add network calls other than to Google's sign-in and Calendar addresses, and only while connected.
- Sign in inside the Yappr window (Google blocks embedded sign-in, and it is less safe).
- Break the iCal path, existing settings or keys.
- Quit Wispr Flow.

## Stop and ask before
- Creating the Google Cloud project, consent screen or client ID. The owner does this; Claude guides.
- Anything public: pushing, PRs, GitHub settings, Google verification.
- Adding a heavy dependency (the plan is plain Python, no Google SDK).
