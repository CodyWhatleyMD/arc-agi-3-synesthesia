# Pre-statement: which public metric predicts the hidden score, levels or score? (10-28 14:25 CDT)

Cody's question, 10-28 14:21: "What do you think is a better prediction for the hidden set, levels complete or score?"
Sakshi's answer: levels. Written down BEFORE any further hidden submission so the remaining slots can test it.

## Prediction (Sakshi)
Over the configs we submit to the hidden set from here on (plus the rows below), the rank order of hidden scores
is better reproduced by the configs' PUBLIC LEVELS (mean levels completed per game) than by their PUBLIC SCORE
(mean score per game): Spearman(hidden, public levels) > Spearman(hidden, public score).
Secondary: a linear fit hidden ~ public levels has the narrower residual spread.

Reasons (mechanism, not scoreboard): the score is a weighted level count with a saturating efficiency term, so it is
levels plus two noise sources; the weighting makes one extra deep level on one game move the score by tens of points
(cn04 3.9 / 71.4 / 4.8 across identical runs) and the level count by one. Every arm so far: level intervals 3-10x
tighter than score intervals (on/off: levels -0.24 [-0.64, +0.19] vs score -3.62 [-9.89, +3.22]; Batch A local:
levels +0.36 [-0.05, +0.77] p=0.078 vs score +3.45 [-4.35, +10.92]). ICC 0.55 for score across identical runs.
And the hidden games are different games: "clears levels and composes past the first" is a property of the agent;
a public score carries those 25 games' weights.

## Rule (before each hidden submission)
1. Record the config (notebook sha / harness commit / switches) and its PUBLIC rows from the valid public-25 runs of
   that exact config: mean levels per game, mean score per game, n runs, PLATFORM (Kaggle commit run vs local 6000).
   Same platform for all rows of one comparison; the same config scores 47.37 on a Kaggle commit run and 42.21 on
   the local 6000 pool, so local and Kaggle rows are never mixed in one rank order.
2. Submit; record the hidden score when COMPLETE.
3. Compute both Spearman correlations only when >= 5 configs have all three numbers; report both with n, no
   claim below that.

## Rows known at writing (hidden column blank where pending)
| config | public platform | n | public levels/game | public score | hidden |
| v36 (8552964, anchor) | local 6000 pool r2,r3,r4,r6 | 4 | 4.21 | 42.21 | 20.90 (57704437), 21.85 (57725544) |
| v36 (8552964, anchor) | Kaggle commit run | 1 | [read from log] | 47.37 | same |
| room G-s (1c4799d, sakshi) | local gs1b,gs2b,gs3b | 3 | 4.36 | 43.22 | pending |
| room G-s (1c4799d, sakshi) | Kaggle commit run room-s-k1 | 1 | 4.62 (21/25 per-game lines captured) | 42.89 | pending |
| room G-c (be9603e, cody) | local gc1 (gc2,gc3 running) | 1 | [gates read, score unread] | - | pending |
| room G-c (be9603e, cody) | Kaggle commit run room-c-k1 | 1 | 4.76 (21/25 per-game lines captured) | 42.57 | pending (slot tonight, Sakshi's plan) |
| v36 Kaggle control pool (12a000d all-off) | Kaggle C1-C7 | 7 | [per-run levels not yet tabulated] | 39.06 (sd 5.07) | - |
| Batch A (12a000d) | Kaggle ba* | 3 | 4.19 (controls 4.13) | +0.98 vs controls | none yet |
| no-echo (c82ffc3) | pending smoke | - | - | - | - |

Caveat: with at most ~7 slots left, the test is over 5-8 points; a directional answer with n stated, not a result.
Parser: scripts/compare_arm_groups.py gives both means per run.
