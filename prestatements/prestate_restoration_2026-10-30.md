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

## Amendment 1 (16:45 CDT), from Kas's code read of the anchor (8552964 + v36 pickles; before any run)
CORRECTIONS to "the cuts on record": two of them are NOT in v36. C1: no thinking budget exists in v36 (the 1024 cap
was an older build's cell); R0 is already uncapped. C2: the request window is already ~127k (LOCAL_ANALYZER_CONTEXT_
WINDOW 127,488; budget 126,464), not 32k. C3 is real but different: the 30-turn constant never applies while
TARGET > 0; the actual cut is the trim-back TARGET 81,536 (history grows to 126k, then is cut to 81k). The lobotomy
in the SHIPPED config is therefore: the job clock (9,300 s), the per-game clock (3,918 s), 14 games sharing one
server, the 81k trim-back, the strategy-audit cadence tied to the clock, and the student eye. The thinking cap, the
32k context and the no-echo were ARMS we tested, not v36. The pre-statement's narrative stands with that correction.
R5 REDEFINED: per-game clock off + concurrency 1 + TARGET 126,463 (history to the limit) + native tower (the staged
synesthesia_board_native arm: ARM_B_STUDENT_TOWER=0, image limit 143, MULTIMODAL_UPSCALE 16).
TERMINATION, as the code has it (not as first written): a game ends on WIN or crash only. GAME_OVER auto-RESETs and
play continues; there is no harness action cap (max_actions_per_game None); analyzer failures retry every 1 s with no
limit. Untimed games CAN run forever. So the cap is a SAFETY NET derived from measured play, not a budget:
  max_actions_per_game = 5,184 = 4 x 1,296, where 1,296 is the MAXIMUM per-game action count seen in any of 9 timed
  Kaggle runs x 25 games (n=225; mean 307, median 251, p90 556). Cap hits are counted and reported; a cap hit is a
  "did not finish", never a level count. analyzer_timeout stays 900 s.
STRATEGY AUDIT: with no clock it would never fire (its interval is 25% of the per-game clock, ~980 s in v36). Kept,
on an ACTION trigger mapping the same fraction: every 77 actions = 25% of the timed mean 307. R0 = v36 minus the clocks
with the audit on that trigger; named as such.
EFFECT-TIMING (Kas): LOCAL_ANALYZER_* must be set after cell 7 and before cell 9; bm.solver.* in cell 10 carries.
ARM_MAX_RUNTIME_S must be "0" (unset = 2,100 s fallback). Other caps unchanged: TOOL_TIMEOUT 30 (hard), TOOL_OUTPUT
4,096 chars, YIELD 150 s, sampling 0.6/0.95/20, thinking on.
PLE output test (Cody's "measure it"): INCONCLUSIVE by instrument — greedy with MTP spec-decode is not repeatable
(full vs full diverges at the median 3rd token, 7.1% agreement); a real measure needs teacher-forced prompt_logprobs
on a measurement server. Recorded, not pursued today.

## R0 LAUNCHED 16:42:54 CDT (Kas; tag r0_untimed; notebook synesthesia_r0 sha 630a9c6b9871; commit 331b784; log
## ~/kaggle_local/run_synesthesia_r0_untimed.log; chain_r0.sh disk-guarded <3 GB = stop/invalid)
Diff vs v36: ARM_MAX_RUNTIME_S "0"; cell 10 adds max_runtime_s_per_game=None, concurrency=1, max_actions_per_game=5184,
and the strategy audit on an action trigger every 77 (monkeypatch of _should_audit_strategy keeping the time trigger's
reset rules: count restarts at a level clear or a delivered audit; prints "strategy audit due at action N").
analyzer_timeout 900, TARGET 81,536, student tower. Harness dataset = 8552964 byte for byte (metadata aside).
Generator fixes in 331b784: (a) 2e1af90's cell 2 required patch_ple_inc.py on every build but 8552964 doesn't ship
it — R0 and the 14:35 px8 notebook would have raised at cell 2 (px8 needs a rebuild before any use); (b) 4cc799f's
--model-source wrote MODEL_PARTS with repr(), so the default build no longer reproduced the pushed anchor. Both fixed;
the anchor rebuilds byte-identical to f9af78d9 + metadata.
R5 runs AFTER R0, not alongside (two concurrent games would change per-request batching = serving).
