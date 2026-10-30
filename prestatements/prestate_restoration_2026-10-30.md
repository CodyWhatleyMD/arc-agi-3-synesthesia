# Pre-statement: the restoration series (2026-10-30 16:30 CDT). Cody: "see if we actually abandoned our smartest model along the quest to increase the score"

## Decision (Cody, 16:23)
The leaderboard is called. Remaining hidden slots (tonight 19:00 CDT + two) = v36 replicates only (hidden mean with
spread for the record). No arm is submitted. The cards go to untimed, one-game-at-a-time runs of OUR OWN designs.

## The question
Did the cuts we made for throughput remove capability? Restore them one at a time with the clock off.

## The cuts on record (what gets restored)
C1 thinking budget: capped (A8, thinking_token_budget 1024 per request) -> uncapped.
C2 context: 32,768 (Keith's Kaggle number; the model's ceiling 262,144; findings 166 addendum 19:36) -> 131,072
   (max_model_len is already 147,072 in configs/inference.json; the request-side cap is what moves).
C3 history: Duck's _PERSISTENT_HISTORY_ASSISTANT_TURNS = 30 (bare constant) + the token-window trimmer (~22.5k mean
   prompts) -> history kept to the context limit.
C4 reasoning echo: kept in v36 (no-echo cost -29.6 timed) -> stays kept in every arm; the NO-ECHO arm is re-run
   untimed as P3's test only.
C5 perception: student tower (1,024 tokens) -> native tower resident (the pathway as designed), and -> text only.
C6 concurrency: 14 games sharing the server -> 1 game at a time (every arm; this is the untimed condition itself).
Not restorable here: a larger quantization. BF16 is 335 GiB; FP8 routed experts alone exceed the 96 GB card. Needs
rented cards; stated, not pretended.

## Arms (all untimed: no job budget, no per-game clock; a game ends on WIN, GAME_OVER or the harness's action cap,
## which is recorded; one game at a time; local RTX PRO 6000; same vLLM 0.31 runtime)
R0 control: v36 exactly, untimed, single-game.
R5 all restored: C1+C2+C3+C5(native).
If R0 and R5 differ beyond the noise read below, bisect: R1 (C1 only), R2 (C2+C3), R4 (C5 native only).
RN: v36 no-echo untimed (P3).
RT: v36 text-only untimed (the readback says the image channel does not read cells; this is the honest comparator).
Order: R0, R5, then by the gap. n=1 each first pass on the public 25; the custom three (zk01, zs02, zg03) after.

## Reads, in order, before any number is quoted
1. Gates: 0 tracebacks, 0 HTTP 400, every game reached a terminal state, action cap hits counted.
2. Levels completed per game (the benchmark's depth term) and actions per level; wall-clock used per game recorded.
3. R5 vs R0 by scripts/compare_arm_groups.py (paired by game); the timed anchor's levels (4.21/game local pool) as
   the reference for "what the clock cost".
4. The untimed run-to-run noise: R0 twice if the week allows; until then, the timed pool's ICC 0.55 is the prior
   on swing and NOTHING at n=1 is called resolved.

## Predictions (before any run)
P1 (Cody's): R5 clears more levels than R0 untimed — the cuts removed capability, not just time.
P2: the biggest single restoration is C1 (thinking) or C3 (history), not C5 (perception): the readback says the eye
    never read cells, so giving it back changes little; the lobotomy was memory and thought, not sight.
P3: RN loses levels untimed as it did timed.
P4 (the embarrassing one): R5 ≈ R0 untimed. Then the cuts cost only time, and the paper says the clock measured
    hardware without having cost cognition.

## Lane
Starts tonight on the 6000 (idle). Kas maps C1-C6 to the harness's actual flags and reports them verbatim before
launch; untimed single-game runs have no known duration — the first R0 pass measures it.
