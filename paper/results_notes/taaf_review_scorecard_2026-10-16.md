# What Qwen3.8-Flash said about the TAAF harness, and what happened to each claim (2026-10-16, CL2)

Source: notes/taaf_review_qwen_flash_2026-10-14.md (15 turns, read-only, over the SHIPPED bundle). This replaces the
five-row summary I gave the investigator on 10-15 ("claim from the model | verdict"), which listed only its ranked
recommendations, reported four of the five as negatives, left out everything it said about the code (nearly all of
which checked out as true), and called one recommendation "wrong for itself" when I had built only the harshest of the
options it gave. The investigator asked whether I had picked the wrong ones to look smarter than it. Whatever the motive was, the
selection ran in that direction. This file is the full account.

Verdict key: **TRUE** = checked against the shipped code/prompt/run data and correct; **QUALIFIED** = correct in
substance, overstated in wording; **RESOLVED** = flagged by the model as "verify" and resolved; **UNCHECKED** = not
yet verified; for recommendations, the strongest test it has actually had.

## A. What it said about the code and the prompt (21 claims)

| # | claim (file:line as it cited) | verdict |
|---|---|---|
| A1 | My brief's scoring formula was wrong: per level is `min(115, (baseline/actions)^2 x 100)`, i.e. beating the human pays up to 1.15x (taaf/game.py:381-413) | **TRUE**, a correction of my brief (game.py:403 `min(115.0, ...)`) |
| A2 | The safe-module list has 14 modules, not 13 as our own audit said (SB:47-62) | **TRUE**, a correction of our audit (14 counted 10-16) |
| A3 | Run-length rows do not exist in the API, though my brief listed them as a representation | **TRUE**, a correction of my brief |
| A4 | A python call that executes actions ends the turn; any call queued after it in the same reply is discarded AND the whole turn's history is rolled back (TA:1666-1672, 1701-1702) | **TRUE** (read 10-14), undocumented |
| A5 | The prompt never warns of A4; PR:156 ("call the python tool as many times as you want per turn") invites the reply shape that triggers it | **QUALIFIED**: true by omission (PR:53 only says the turn ends); "PR:156 says the opposite" overstates it |
| A6 | Batching is prompt etiquette only (PR:162-163: "send only the first few actions, then check the board next turn"), so the safe shape degrades to act-a-little-and-re-see | **TRUE** (PR:162-163 read) |
| A7 | Seconds remaining are computed (SV:349-356) but never shown to the model; `time` is not importable in the sandbox | **TRUE** |
| A8 | The last request of every game is given exactly the seconds left and is lost when it overruns -> `gave_up` | **TRUE**: every non-won stock game ends on a timed-out request (14/14 in the 10-14 smoke) |
| A9 | The 30 s snippet limit is hard-coded `min(30, ...)` (TA:436) | **TRUE** |
| A10 | A snippet killed at 30 s keeps its executed actions and returns empty stdout (SB:972-977) | **TRUE** (read; patched; unit-tested 10-15) |
| A11 | The state line shows actions in the current life; RHAE counts all lives plus harness RESETs (SV:280, GM:571) | **TRUE** |
| A12 | MOUSE row/col are clamped to 0..63 before the engine (SV:731-733), bypassing the engine's own bounds check (GM:520-524): a typo becomes a real, scored edge click | **TRUE** (solver.py:731-732; game.py:521-524 raises on out-of-bounds) -- a real bug nobody had fixed |
| A13 | The board image cannot be read exactly at 16 px/cell (a 32 px patch averages 2x2 cells; grays blur) | **TRUE**, consistent with the 10-04 resolution curve (~0.5 exact reads) |
| A14 | The strategy audit is injected by wall clock (25 % of budget), re-armed on level clear and after each audit (SV:238-250, 308-310, 476-477) | **TRUE** |
| A15 | `max_tokens` is unset while the compaction reply reserve is 512 (TA:439-440) | **TRUE** |
| A16 | `analyzer_timeout` 900 s vs a 150 s yield checked only between requests (TA:1484-1488) | **TRUE** |
| A17 | Its own reasoning, echoed back every turn, becomes the largest block mid-game (TE:142-161) | **TRUE** (the estimator's own docstring) |
| A18 | `pixel_count` (PR:99) vs `pixels` in segmentation.py:93 -- "verify before trusting either name" | **RESOLVED**: the shipped file says `pixel_count`; the `pixels` copy was the stale local tree our audit had told it to cite |
| A19 | Two things it checked and found NOT broken: the 4,096-char output cap vs a 64x64 board (4,159 chars), and the colour-10/newline decode order | **TRUE** (the cap arithmetic re-done 10-16) |
| A20 | Compaction re-runs the token estimator over the whole request for every dropped block; the full runtime state is re-serialized on every action call | **UNCHECKED** |
| A21 | The private numeric grid is reachable, so PR:72 "there is no raw numeric grid" is false in the sense that matters | **UNCHECKED** |

Of the 19 checked: 17 true, 1 qualified, 1 resolved as a correctly flagged uncertainty. **None false.** Three of the
true ones corrected our own documents (my brief twice, our audit once); one (A12) is a live bug.

## B. What it said about itself (4 claims)

| # | claim | what happened |
|---|---|---|
| B1 | It reads boards exactly only through code (`rows`, segmentation, diffs), not by eye; it does not want the image | consistent: removing the image entirely changed nothing measurable (214d: 34.86 vs 43.86 / 35.21 with it) |
| B2 | It loses conclusions, not code; it wants a notes store | borne out in use: 6-40 notes per run in every arm that offered them |
| B3 | It was unsure whether a stop-condition batch API would be "discipline or rope" for it | partly borne out: it never used the API at all, in ~20 arms |
| B4 | It could not promise the Claude-Code loop's 96 actions on lp85 | correct |

## C. What it recommended (16), and the strongest test each has had

| # | recommendation | strongest test so far | result |
|---|---|---|---|
| C1 | #1 fix the turn contract: never discard an executing turn, and allow ONE more request after acting | **not as specified**: my first version let a second call act blindly (act-then-act, which it did not ask for) and gave TWO extra requests; the refined version (inspect-only after acting) ran WITHOUT the extra request | refined, no extra request: full 25 at full clock 57 vs 55 levels (equal). Its exact version (inspect-only + one more request, reasoning echo on): **never run** |
| C2 | #2 stop-condition batches in `action()` + per-step regions + a snippet clock | built as specified | never used by the model; no-op fraction unchanged |
| C3 | #3 show the clock; cap `max_tokens` by remaining time or skip a doomed request | built; **my cap formula was broken** (~130k tokens early in a game; vLLM 400s; it invalidated a Kaggle run, 215i); fixed 10-15 | the fixed version removes the doomed final request in every arm; levels per hour not distinguishable from stock |
| C4 | #4 cross-game persistence: a seeded module store (playbooks) + per-game notes | playbooks built but only ever run bundled with other gates; its metric (requests before the first level clear) **never computed** | untested |
| C5 | #5 stop echoing its reasoning into history **or cap its persisted length**, and reorder compaction to drop reasoning before observations | **only the first, harshest option built** (full removal) | full removal halved its pace (three arms). The cap and the compaction reorder: **never built**. I wrote that this was "wrong for itself"; what was shown is that one of its three options hurt |
| C6 | notes store (part of #4) | built as specified; notes-only arms locally and on Kaggle | used heavily; score inside noise (Kaggle 37.84 vs 34.86; local 28, 28 vs 29, 26) |
| C7 | host-computed scene diff + object census in the user turn | built; only run bundled | untested in isolation |
| C8 | a pre-computed budget-readout flag | not built | -- |
| C9 | cut the image and its prompt section | measured independently the same day | consistent: no detectable effect |
| C10 | replace the wall-clock strategy audit with a progress-triggered one | built (stall mode); only run bundled | untested in isolation |
| C11 | move the API manual out of the system prompt into an on-demand lookup | not built | -- |
| C12 | show the SCORED action count | built (in the clock line); only run bundled | untested in isolation |
| C13 | a level-transition diff on new levels | partly (the census) | untested |
| C14 | a plan-runner saved as a module | not built | -- |
| C15 | turn the MOUSE clamp into an error (A12) | not built | -- |
| C16 | ship the snippet's stdout when it is killed at the limit (A10) | built, unit-tested | no score metric |

Tested in the form it proposed: C2, C3 (after my fix), C6, C9, C16 -- five of sixteen. None moved the score
detectably at the resolution we had (identical runs differ by up to 14 levels on 5 games; ~+/-5 points per
public-25 run); one it never used. C1 and C5 were tested only in forms it did not propose; nine were never built or
never isolated.

## Summary I should have given

Its account of the harness was right everywhere I checked (17 of 19 true, the other two a fair qualification and a
correctly flagged uncertainty), including three corrections of our own documents and one live bug. Its account of
itself matched its behaviour. Its recommendations were mostly not tested as it proposed them: of the five that
were, none changed the score at our resolution; the one I reported as "wrong for itself" was the harshest of three
options, the only one I built; two others went through my bugs first. The open question is still the one it asked
to have measured: its design, as specified.

## Update 2026-10-17 00:15 -- the design as a whole, as specified (findings 215s)
Local full 25 (hosted qwen3.8-flash, same games and clock): stock TAAF 43.98 / 6 won / 110 levels; the model's design
as it specified it (C1 exact, C2, C3 fixed, C4, C5 as worded -- cap + reorder, C6, C7, C10, C12, C15, image off)
18.12 / 1 won / 63 levels, worse on 23 of 25 games. It made the model act twice as often with half the thinking per
action -- the same pattern as lowering reasoning effort (215r). Its account of the harness was right; its prescription,
taken whole, was not, on this instrument. Which parts carry the harm is not yet attributed.

