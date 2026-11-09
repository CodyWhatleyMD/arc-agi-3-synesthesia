# Run-level (cluster) intervals for every arm in the paper — 2026-11-02 09:00 CST

Method: scripts/compare_arm_groups.py --cluster (two-stage bootstrap: runs with replacement within each group,
then games; 10,000 resamples; seed 0). Pre-stated in notes/prestate_run_level_ci_2026-11-02.md before any number
was computed. Game-only CI = the interval the draft currently carries. All predictions in the pre-statement held.

| arm (score) | runs | Δ | game-only 95% CI | cluster 95% CI | verdict (cluster) | run means arm / control (sd) |
|---|---|---|---|---|---|---|
| no-echo ne1-3 vs r2,r3,r4,r6 | 3 v 4 | −29.60 | [−38.33, −21.30] | [−39.55, −20.04] | LOSS (RESOLVED) | 14.01 13.75 10.08 (2.20) / 40.19 44.26 41.41 42.96 (1.78) |
| tower on/off bo1b-3b vs r2-4 | 3 v 3 | −3.62 | [−9.89, +3.22] | [−14.01, +6.76] | not resolved | 42.66 39.89 32.44 (5.28) / 40.19 44.26 41.41 (2.09) |
| native na1c-3c vs r2-4 | 3 v 3 | +2.07 | [−4.65, +9.15] | [−8.80, +12.88] | not resolved | 44.41 49.43 38.23 (5.61) / same |
| Batch A ba1b,ba2b vs r2-4 | 2 v 3 | +3.45 | [−4.35, +10.92] | [−8.78, +14.83] | not resolved | 49.23 41.58 (5.41) / same |
| Batch A on Kaggle A1-A3 vs C1-C3 (RTX PRO 6000 hosts) | 3 v 3 | +0.98 | [−5.80, +8.62] | [−11.69, +13.91] | not resolved | 41.89 34.83 46.72 (5.98) / 41.96 32.57 45.95 (6.87) |
| agent clock ac1,3,4,5,6 vs cp1-5 (server) | 5 v 5 | −0.87 | [−7.09, +5.76] | [−10.29, +9.37] | not resolved | 49.70 44.79 35.44 39.31 44.98 (5.54) / 45.49 35.78 43.82 47.74 45.73 (4.65) |

Levels (cluster): no-echo [−2.57, −1.50] LOSS; on/off [−0.88, +0.41]; native [−0.57, +0.77]; Batch A [−0.34, +1.02];
agent clock [−0.67, +0.50]; Batch A Kaggle [−0.72, +0.80]; all but no-echo not resolved.

Note: the game-only no-echo interval here ([−38.33, −21.30], 10,000 resamples) differs in the second decimal from the draft's [−38.43, −21.38] (the no-echo JSON, 4,000 resamples); same Δ, same runs. Added 09:05: the Batch A Kaggle row (not in the pre-statement's list; its verdict could not change).

Why the game-only interval is too narrow: two Kaggle runs of the identical candidate_pinned notebook (54.70, 32.22)
give, game-only, Δ −22.47 [−35.68, −10.91], p = 0.004 — a "resolved loss" on unchanged code. A run-level state
(which mechanics were cracked early) moves many games together. At n = 1 per group the script now withholds the
cluster verdict rather than print a number it cannot support.

Paper: swap each interval for the cluster interval, keep the Δ and the game-only interval labelled as such if space
allows, verdict words from the cluster column. No number removed.
