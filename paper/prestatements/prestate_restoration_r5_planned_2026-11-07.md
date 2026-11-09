# Pre-statement: R5 as planned (2026-11-07 04:50 CST, CL1), before any run

Supersedes the 11-04 Colab redefinition (notes/prestate_restoration_r5_colab_2026-11-04.md) for the R5 arm. The investigator, 04:41:
"if they are running the wrong tests there is no point"; the server's R5-at-concurrency-14 and the vast lane were stopped.

## The arm, exactly as the 10-30 plan amended it (notes/prestate_restoration_2026-10-30.md, amendment 1)
R5 = v36 with every throughput cut restored, nothing else changed:
- per-game clock off (max_runtime_s_per_game None), job budget off (ARM_MAX_RUNTIME_S "0");
- concurrency 1 (one game at a time, as R0/ut1);
- history kept to the limit: LOCAL_ANALYZER_TARGET_CONTEXT 126,463 instead of the shipped trim-back 81,536
  (context window 127,488 unchanged);
- the native tower instead of the student (the staged board-native arm: ARM_B_STUDENT_TOWER=0, image limit 143,
  MULTIMODAL_UPSCALE 16);
- the 5,184-action safety cap and the action-triggered strategy audit, as R0 (not cuts; see the check below).
Comparator: ut1 (R0 complete, the server, 56.88, 5.96 levels/game, 17/25 clears). Same host class (Kaggle-shaped
RTX PRO 6000 Spot VM) so the comparison is one variable (the restored cuts) on one platform.

## What the untimed R0 data already settle (11-07 04:43, three partial untimed runs, 38 played games)
The action cap did not end games in progress: of 14 games that hit the cap, the last level clear came at <=59% of the
cap and none in the last four tenths (levels per tenth of the cap: 41, 8, 3, 0, 3, 2, 0, 0, 0, 0). The cap is the
safety net the plan called it, so "clock off" is a clean condition and the capped games are capability limits.

## Reads, in order
1. Gates as the 10-30 plan: 0 tracebacks, 0 HTTP 400, every game at a terminal state, cap hits counted.
2. Levels per game and full clears, paired by game against ut1 on the games both completed; actions per game.
3. Levels per 100 actions (E1) and the level-k survival curves (E2), R5 against ut1 and against the timed pool.
4. If R5 is cut short by the deadline: report on the games it finished, matched to ut1's same games, labelled partial,
   with the unfinished count. A partial R5 is reported as a partial, never scaled.

## Predictions (before any number)
P1 (the investigator's, from 10-30): R5 clears more levels per game than ut1 — the cuts removed capability, not only time.
P2 (CL1): the native tower alone is small (the clocked native arm was +2.07, not resolved); if R5 differs from ut1
beyond ut1's own run-to-run spread, most of it is the history kept to the limit.
P3: per action, R5 is at least as efficient as ut1 (levels per 100 actions >= 0.25); if it is lower, the extra history
is costing actions, which is a finding against the restoration.
Not resolved at n=1 vs 1 by our rule; the direction is still worth stating, as R0's was.

## Host and timing (the investigator's call, 04:50): whole on the server (~53 h at ut1's pace; 61 h to the deadline), split
## across two Kaggle-shaped VMs by game list (the generator's game-slice switch; ~27 h each), or run and report what
## finishes. [TO BE FILLED when he decides]
