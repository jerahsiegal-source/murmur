# Handoff: reliable dictation cleanup

Brief: `INTENT-cleanup.md` · Branch: `cleanup/v1` (from origin/main a845c71) · Not merged.

## Summary
Yappr's AI cleanup now transcribes and never acts on what was said, resolves self-corrections (including ones that reach back a sentence), removes more filler, and keeps lists and paragraphs only where the speaker made them. An output guard pastes the rule-cleaned words whenever the model returns something that isn't a cleanup. Short dictations with nothing to fix skip the AI.

Commits: eca5a57 eval tooling · 10234c0 prompt caching · 75a35c5 prompt, guard, fast path · 1dd342a hedges, dropped-request guard, speech check · f020d60 like/kind of are filler · a572bd5 review fixes, 1-hour cache.

## Done items (evidence in `done.json`)
| Item | Result |
|---|---|
| D1 never acts | instruction cases 120/120 over 5 runs (old: reproduced the checklist bug 3/3) |
| D2 corrections | 120/120 (old: 39/42 and 12/15) |
| D3 filler | 80/80; history filler left old 5 → new 1–3 |
| D4 nothing lost | 110/110; new rewords half as much as old (0.7% vs 1.6–1.9% new words) |
| D5 formatting | 40/40 |
| D6 bad output caught | 8 real bad outputs rejected in unit tests; 0 false rejections over 4,302 new outputs |
| D7 speed | owner history: short median 0.36→0.35 s, p90 0.87→0.85; long median 0.89→0.69, p90 1.28→1.24 |
| D8 better than today | untouched final set: old 50/60, new 100/100 |
| D10 no regressions | pytest 178 passed (baseline 172) |

## Not done
- **D9 owner check in the real app.** Pipeline check passes 3/3 (`tools/cleanup_eval/e2e_speech.py`: Windows voice → Parakeet → cleanup), but the running Yappr was not restarted.
- **Cost gate (owner decision).** Replaying the owner's real dictation times: old ≈ $0.0087 per 120 dictations, new with the 1-hour cache ≈ $0.0092 (+5%). With a 5-minute cache it was +38%. Options: accept +5%, or trim the prompt's examples (risk to quality, needs re-scoring).

## Decisions
- Bullets only when the speaker counts items out (first/second, step one/two). This was the root of the reported bug.
- Guard falls back to the rule text instead of retrying (no extra wait; can't act on the words).
- Fast path: ≤16 words, ending in punctuation, no filler/correction/counting/spoken-punctuation words. On history the AI returned all 28 such dictations unchanged.
- Hedges ("maybe", "probably") are meaning; "like", "kind of", "sort of" are filler.
- Real history was sent only to the Claude API the app already uses; results stay in `data/eval/` (gitignored).

## Found, not fixed
- A timed-out cleanup can take ~8.5 s before falling back (4 s timeout + one SDK retry). Pre-existing.
- `_counted_out` allows a list when "first" and "second" appear anywhere (e.g. "the first time… wait a second"). Permissive, not harmful.

## Review
One fresh-reviewer round. Fixed: corrected requests wrongly rejected (F1), `**kwargs` treated as bold (F5), fast path for spoken "question mark" and unpunctuated text (F4). F2 (cost with real gaps) measured and moved to the 1-hour cache; the remaining +5% is the owner's call. F6 declined (nit).

## Cross-model review prompt
> Review branch `cleanup/v1` of this repo against `INTENT-cleanup.md`, using `loop-cleanup/done.json` and this handoff. Focus on `yappr/cleanup.py` (prompt, `_looks_like_cleanup`, `needs_llm`) and `yappr/llm.py` (cached system prompt). Report blockers / should-fix / nits with a concrete failing input each. Do not call the LLM API.

## Staging test checklist (owner)
Start Yappr from `cleanup/v1`, then dictate:
1. A long message that ends "…can you create a checklist and make a plan?" → pasted as your words, no bullets.
2. "Let's meet Tuesday, no, strike that, actually Wednesday at ten." → "Let's meet Wednesday at ten."
3. A filler-heavy ramble with um, like, you know, basically, so yeah → those gone, "maybe"/"I think" kept.
4. "First, X. Second, Y. Third, Z." → a numbered list.
5. A short "Sounds good, I'll check after lunch." → pasted instantly.
