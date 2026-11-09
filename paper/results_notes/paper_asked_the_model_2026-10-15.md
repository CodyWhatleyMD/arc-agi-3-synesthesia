# "We asked the model": the harness as something its user designs (working notes, 2026-10-15)

The investigator, 01:06: "if our method ends up being — 'we asked the model' — that's worth a write up." This file is the trail,
kept as it happens, so the write-up is a selection rather than a reconstruction.

**Correction, 2026-10-16.** On 10-15 I summarized the model's review to the investigator as five claims with four negative
verdicts. The review made ~41 claims; of the 19 about the code that I have checked, 17 are true (three of them
corrections of our own documents, one a live bug), one is a fair overstatement, one a correctly flagged uncertainty,
none false. Of its 16 recommendations, five were tested as it proposed them; two went through my bugs or my
stronger variants first; nine were never built or never isolated. Full account: notes/taaf_review_scorecard_2026-10-16.md.
Sentences below that overstated against the model are struck through and corrected where they stand.

## The method in one paragraph

Every disclosed ARC-AGI-3 Kaggle entry runs on one harness (Tufa's Duck/TAAF), and competes on the checkpoint
inside it. We measured that the public 25 cannot rank checkpoints closer than ~10 points on one run (findings 214c)
and that our one hand-built perception tool bought nothing (214d). Instead of redesigning the harness ourselves, we
(1) audited it structurally against the shipped code (notes/taaf_audit_2026-10-14.md), (2) gave the model that plays
under it — Qwen3.8-Flash-Next, the same weights — read-only tools over that code and the audit, and asked it, as the
user of the harness, what pushes it toward wasted actions, what it can read exactly, what it wants to persist, how it
wants to act, and which five changes it would make first with the measurement for each
(notes/taaf_review_qwen_flash_2026-10-14.md), (3) implemented ~~exactly those~~ most of them (not all, and two not as specified -- see the scorecard) as
independently gated patches to the shipped harness (scripts/harness_patches/patch_model_review.py), and (4) measured
them ~~one variable at a time~~ mostly bundled, on the counts the model named and on score.

## Artifacts, in order

| step | artifact | what it is |
|---|---|---|
| audit | notes/taaf_audit_2026-10-14.md | per-turn loop, per-game policy, context policy, persistence, tunables, oddities; file:line against the shipped bundle (local copy was stale; the fork pulled the shipped files) |
| reviewer | scripts/arc_sdk/review_with_qwen.sh + taaf_review_prompt.md | Claude Code loop on Qwen's token-plan Anthropic endpoint, Read/Grep/Glob only, fresh HOME; continuation loop because a text-only reply ends `claude -p` (the model's first attempt died on "Let me read tool_agent.py in full" without calling the tool) |
| review | notes/taaf_review_qwen_flash_2026-10-14.md | 15 turns, 492 s, 24k chars, ~0.75M cached-input + 29k output tokens; corrected the brief's scoring formula from the code; found the act-then-inspect history rollback (TA:1666-1672, confirmed by reading); flagged a key-name mismatch with "verify before trusting" (verified: the shipped file is fine) |
| patches | scripts/harness_patches/patch_model_review.py | 29 exact anchors in 3 files; MR_* gates default to shipped; unit tests against a fake game (findings 215) |
| runner | /home/ignaz/taaf_local (run_local.py, run_ab.sh), scripts/arc_sdk/compare_local_runs.py | the shipped harness locally, CPU only, against the token plan's OpenAI-compatible endpoint; stock vs all-on on the same games, same clock, no image; counts: actions per cleared level, requests per action, no-ops, batch size, clock-tail timeouts, prompt tokens, API use |
| first live runs | findings 215a | lp85 600 s: mechanics work; a hot loop in my tail-safe found and fixed; the model used the post-action continuation (3x) and a note in its first ten minutes |

## What the model said that we would not have said (candidates for the write-up)

- The act-then-inspect trap as the single most expensive thing in the contract — undocumented, and the prompt
  invites the exact message shape that triggers it.
- "I don't want to read boards with my eyes at all": exactness comes from code over `rows`/`segmentation`; the
  image is a thumbnail at any scale. (Consistent with 214d, measured independently the same day.)
- The scored quantity (`actions_per_level`, all lives + RESETs) is the one number the prompt never shows; the
  state line shows the current life only.
- Honesty about itself: a stop-condition API could turn under-batching into over-batching; "whether I use them as
  discipline or as rope is the thing the public 25 will say, not this document."
- The scene-diff request: host-computed appeared/vanished/moved objects per turn, "outside python, so it costs no
  snippet time."

## Measurements (to be filled as they land)

- local ablation, 5 games (lp85 ft09 vc33 sb26 tr87) x 1800 s, hosted qwen3.8-flash, no image (findings 215b-e):
  | arm | levels | actions | act/cleared lvl | median request | tok/action | clock-tail timeouts |
  |---|---|---|---|---|---|---|
  | stock, run 1 / run 2 | 11 / 12 | 409 / 292 | 23.5 / 20.2 | 22.9 / 21.2 s | 773 / 1077 | 5 / 5 |
  | all gates (post=2, echo off) | 7 | 236 | 17.6 | 40.0 s | 1505 | 2 |
  | all gates (post=0, echo off) | 7 | 204 | 19.6 | 40.7 s | 1917 | 1 |
  | all gates (post=0, echo ON) | 12 | 322 | 16.1 | 26.7 s | 1238 | 0 |
  | minimal (keep-history, clock, tail-safe, stop API, notes; echo on, wall audit, no scene diff) | **17** | 541 | 25.9 | 20.4 s | 779 | 1 |
  ~~The model's suggestion #5 (stop echoing its reasoning) halved its pace~~ Removing its reasoning echo entirely -- the
  harshest of the three options its #5 gave (remove / cap / reorder compaction); the only one built -- halved its pace:
  it re-derives the game every request without its own prior reasoning in context. Its #1 (turn contract), #3 (clock + tail-safe) and the notes store
  compose into +40-55% levels in the same clock. Its #2 (stop-condition batches) it never used. Replicate running.
  Replicate (findings 215f): stock 13, minimal 14 -- means over runs 12.0 vs 15.5 levels (+29%); actions per
  cleared level equal; doomed final requests 7 -> 2. Generalization pair on five other games running.
- full-clock pair (3918 s, the Kaggle shape; findings 215h): stock 3 won / 29 levels / 35.7 actions per cleared level, mean 71.3;
  minimal set 1 won / 25 levels / 24.6 per cleared level, mean 58.8. The model's contract changes buy per-level efficiency and
  cost coverage; under RHAE (uncleared = 0) that is a net loss at n=1. ~~Its self-report was a hypothesis generator, not a
  design oracle -- which is the write-up's actual finding.~~ (Struck 10-16: an overreach from n=1 that the next day's
  replicates did not support, and it misdescribed a review whose factual content checked out; see the scorecard.) Single-gate full-clock arms running to attribute the two effects.
- Kaggle smoke-mr v2 (v2.2, no image, all gates): mechanics pass on our quant and server; play window confounded
  by a 1,345 s model load (findings 215d); clock-tail timeouts 14 -> 0.
- Kaggle q25-mr v1 (minimal set): INVALID -- my tail-safe set max_tokens ~130k early in each game, rejected 400 by vLLM;
  63k retries; 11.20 / 0 won measured the bug (findings 215i). v2 = notes only, cap fixed, running 07:30-11:00 CDT.
- Kaggle q25-mr v2 (notes only, no image, v2.2; 215k): 37.84 / 4 won / 102 levels vs the no-image stock 34.86 / 6 / 94 --
  inside the single-run noise; mechanics clean on our quant.
- single gates at full clock (215i): notes only ~ stock (28 levels, 2 wins); keep-turn-history as first implemented 20 levels, 0 wins --
  the model asked for act-then-inspect and my gate allowed act-then-act. Refined; re-measuring.
- component ablations (one gate at a time): TBD (after the 10-17 quota reset, or locally)

## The variance finding (215j)

At full clock on 5 games, two identical runs of one arm differed by 14 levels and 4 wins (20/0 -> 34/4). Every
attribution made from single runs that morning sat inside that spread. The method's honest output at this point: one
large robust effect (do NOT remove the model's reasoning echo entirely -- the harshest of its three options for #5;
the cap and the compaction reorder it also proposed were never tested), one small robust fix (no doomed
final request), one robust behaviour (notes used, batch-stop never), and no detectable coverage change from the
contract gates at this resolution. The instrument is moving to the full public 25 per run.

- full public 25 at full clock, local (215l): stock 3 won / 55 levels / 20.3 vs refined turn contract 1 / 57 / 20.99 -- equal.

- Correction (215q): the old plan ran out at 09:32 on 10-15, 57 min into the 'full-25' pair -- that pair was really 13 games
  at ~57 min each (fair between its two arms).
- ~~The Claude Code loop vs TAAF~~ (WITHDRAWN 215t: built for Claude, Anthropic endpoint with ~40% less reasoning, 9/25 sessions ended early) -- same hosted model, same 13 games (215q): TAAF 55 levels / 3 won / mean 39.0 vs the coding-agent loop
  24 / 1 / 12.3. The loop the model's review was implicitly compared against (lp85 in 96 actions) does not generalize.

- The model's design AS SPECIFIED, full 25 locally (215s): stock 43.98 / 6 won / 110 levels vs design 18.12 / 1 / 63, stock better on 23
  of 25. It turned the model into a faster, shallower actor (2x actions, half the tokens per action) -- the low-effort signature (215r:
  medium 21.70, low 8.41 vs xhigh 39.5). ~~The finding for the write-up: the model's diagnosis of its harness was accurate, line by line;
  its prescription, applied whole, halved the score. Asking the model is a good way to find out what the harness does; it was not a good
  way to decide what to change.~~ WITHDRAWN 10-17 (215t): the build was not its prescription -- two pieces of steering I added ('budget your
  thinking against it'; 'act again this turn') match the failure, and five other items were simplified. Untested: its design as it worded it.

## Where the instrument stopped (215m)

The token plan's monthly quota ran out at 13:20 on 10-15 (reset 11-14, after the competition closes). The local
instrument ran 15 five-game arms and one full-25 pair; the second full-25 pair got nothing. Everything above is
what 36 hours of 'ask the model, implement, measure' produced; continuing needs our own serving of the v2.2 quant.

## Honest limits to state

- The hosted model's identity (qwen3.8-flash on the token plan) vs our v2.2 quant of Flash-Next is unverified;
  harness effects measured locally transfer qualitatively, the Kaggle runs on our quant are the confirmation.
- ~~The model's review is an input we test, not an oracle; two of its claims were checked and one was wrong in the
  local copy only (the key name), one (history rollback) was right.~~ Corrected 10-16: 19 of its claims about the code
  were checked; 17 true, 1 qualified, 1 a correctly flagged uncertainty (the key name -- the mismatch was in the stale
  copy our audit told it to cite), none false. Its recommendations are what remain largely untested as specified.
- n is small everywhere; counts are lower-variance than score but still need replicates.
- Tufa's own philosophy ("lightweight harness, let the model drive", July 2026) predicts this direction; the
  difference is that we asked the model rather than inferred its needs.
