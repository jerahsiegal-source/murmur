# Work loop: reliable dictation cleanup

Brief: INTENT-cleanup.md · Base: origin/main (a845c71) · Branch: cleanup/v1

## Baseline
- `pytest -q`: 172 passed, 0 failed (2026-11-25).
- Regression check per item: full suite (7.5 s).
- Real-model eval: `tools/cleanup_eval.py` runs against the owner's Claude key (Haiku 5.5, about $0.0001 per case). Local history set: `data/eval/` (gitignored), 120 dictations.
- History timing today (LLM rows, ready_s - stt_s): see the before/after report.

## Decisions
- State folder is `loop-cleanup/` (matches loop-ui / loop-video), since several INTENT files share the root.
- No assistant prefill (Haiku 5.5 rejects it). Thinking stays off and effort low (fastest settings).

- Bullets only when the speaker counts items out (first/second, step one/two, number one/two). Why: the reported failure was the old prompt bulleting a list said inside a sentence, which together with a dictated "make a checklist" turned the transcript into the checklist. Owner asked for "bullets for spoken lists"; counting out is the unambiguous form of that.
- Output guard falls back to the rule-pass text rather than retrying. Why: a retry doubles the wait; the rule text is the speaker's own words, so it can never act on them.
- Fixed prompt is cached (Claude, 5-minute cache). Why: a longer prompt with examples would otherwise raise cost per dictation (a stop-and-ask gate). Measured: average cost per call fell from $0.0000587 to $0.0000403 on the eval run.
- Fast path: dictations of 16 words or fewer with no filler, correction, counting or spoken-punctuation words skip the LLM. Why: on owner history the LLM returned all 28 such dictations character-for-character unchanged; skipping saves ~0.35 s each and pays back the ~16 ms the larger prompt adds to short LLM calls.
- Real history (local only) is sent to the same Claude API the app already uses for dictation; nothing new receives it; results stay in data/eval/ (gitignored).
- Three case sets: cases.json (tuned on), holdout.json (tuned on once after first scoring), final.json (written after tuning stopped, never tuned on). final.json is the honest before/after number.
- Hedges ("maybe", "probably", "I think") are meaning, not filler. Found by the speech end-to-end run dropping "maybe".

## Log
- Baseline (origin/main) on cases.json x3: 131/162 (instruction 30/42, correction 39/42, filler 18/30, preserve 35/36, format 9/12). Reproduced the bug: the onboarding dictation ending "create a checklist and make a plan" came back bulleted 3/3.
- New prompt + guard: cases 162/162, holdout 60/60 (old 54/60 on holdout), final 60/60 vs old 50/60.
- 5x reliability run: 469/469 LLM outputs passed all checks; 1 network timeout fell back to rules (pre-existing behaviour).
- Guard over 1,961 recorded outputs: rejected 26, all old-prompt outputs that restructured dictation into an uncounted list; 0 new-prompt outputs and 0 history outputs rejected.
- History (119 real dictations): filler left 5 -> 4 (of 228 in the raw), acted-on 0 -> 0, lost-content flags 2 -> 0, new-word share 1.9% -> 0.7% (less rewording).
- Speed, paired old/new alternating per input (x3): long median 0.81 -> 0.70 s, p90 1.36 -> 1.18 s; short LLM calls +16 ms median (95% CI +1..+33 ms) before the fast path widened to 16 words.
- Commits: eca5a57 eval tooling, 10234c0 prompt caching, 75a35c5 cleanup prompt/guard/fast path.

## Found, not fixed
- A timed-out cleanup can take ~8.5 s before falling back: llm_timeout_s is 4 s and the Anthropic SDK retries once (max_retries=1). Pre-existing; worth a separate change (e.g. no retry for dictation, or a total deadline).
- Speech-to-text glued "app um" into "appum" in one run; the cleanup removed it correctly, but the rule pass alone would not.

## Blocked

## Stop report (usage limit reached, 2026-11-25)
- Final x5 run: cases 270/270, holdout 100/100, final 100/100. Speech end-to-end (TTS -> Parakeet -> cleanup) 3/3.
- Speed on owner history (paired): short median 0.36 -> 0.35 s, p90 0.87 -> 0.85; long median 0.89 -> 0.69, p90 1.28 -> 1.24.
- Added: request-dropped guard (catches the 1-in-5 "Put this into bullet points" deletion), hedge keep-rule, one worked example.
- Open: history filler-left went 4 -> 7 after the hedge rule (some are metric false positives: "looks like", "that that happened"; real ones: "kind of like Whisperflow", "a couple, like, a minute"). Needs a look: the hedge rule may make the model keep borderline "like"/"kind of".
- Not done: D9 owner check in the real app (restart Yappr from branch cleanup/v1), independent review, handoff.md, push.
