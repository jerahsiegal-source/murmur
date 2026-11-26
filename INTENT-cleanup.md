# Intent: Reliable dictation cleanup

## Outcome
What Yappr pastes is what I said, cleaned up: same words and meaning, minus filler and anything I took back. It never acts on what I said, even when I'm dictating instructions ("make a checklist and a plan"). That holds for long dictations as well as short ones.

## Why
I dictate long prompts and messages, often meant for an AI, and paste them in. If Yappr follows the instructions instead of transcribing them, I lose what I actually said. If it leaves filler and retracted phrases in, I have to fix it by hand, which defeats the point. Today it sometimes turns dictation into a checklist, leaves filler in, and keeps "no, strike that, actually" along with the part I took back. I want it noticeably better overall, at today's speed or faster.

## Done when (all must pass)
- [ ] **Never acts on what I said.** Dictations that contain instructions (make a checklist, plan this, summarise, answer this question, write an email) come back as the cleaned transcription. That includes a long one that ends in an instruction, like the one that failed. Nothing gets answered, summarised or restructured into a different artifact. Evidence: eval set, 0 failures on these cases.
- [ ] **Self-corrections resolved.** "X, no, strike that, actually Y" (and variants: "scratch that", "I mean", "wait, no", "let me rephrase", corrections that reach back a sentence or more) leaves only Y. Both the retracted part and the correction phrase are gone. Evidence: eval cases pass.
- [ ] **Filler removed.** um/uh, "you know", "like", "I mean", "sort of", "basically", "so yeah" when used as filler, plus false starts and stutters. Evidence: eval cases pass, and a filler count on cleaned history output drops clearly from today's output.
- [ ] **Nothing I meant is lost.** No dropped sentences, facts, names or numbers, and no added content. When unsure whether something is filler or a correction, keep it. Evidence: eval cases with tricky real uses ("I like it", "actually" as emphasis) pass. A content-preservation check over the history set flags no losses.
- [ ] **Formatting kept.** Spoken lists become bullets. Long dictations get paragraph breaks where the topic changes. Evidence: eval cases.
- [ ] **Bad output is caught.** If the model still returns something that isn't a cleanup (a checklist I didn't dictate, an answer, a summary), Yappr detects it and falls back rather than pasting it. Evidence: feed known-bad outputs to the check; all are rejected.
- [ ] **Speed same or better.** Median and slow-case cleanup time, short and long dictations, is no worse than today's. Evidence: timing before/after on the same set.
- [ ] **Measurably better than today.** The eval set is scored on the current build and the new one, and the new one wins on every category above. Evidence: before/after report.
- [ ] **End to end.** Dictate in the real app: a long instruction-style message, a "strike that" correction, a filler-heavy ramble. The pasted text is right each time. Evidence: owner check.
- [ ] **No regressions.** Existing tests pass. Dictionary spellings, the no-AI fallback and meeting notes still work.

Partial completion is not done. If any item cannot be met, stop and report which and why.

## Never
- Put my real dictations (history or eval cases built from it) in git or send them anywhere new. Real-history evals stay local; committed test cases are made up.
- Make dictation slower, or start using a more expensive model, without asking.
- Quit or interfere with Wispr Flow while testing.

## Stop and ask before
- Changing the AI model or provider, or anything that raises the cost per dictation.
- Changing what users see in settings.

## Yours to decide
Everything else: how the instructions are written, how the rule pass and the AI pass split the work, how output is checked, how the eval is built and scored, the order of the work. Prefer whatever best serves the Why.
