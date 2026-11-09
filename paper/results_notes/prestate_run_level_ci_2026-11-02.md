# Pre-statement: run-level (cluster) bootstrap for every arm comparison — 2026-11-02 08:55 CST

Written before any interval is recomputed.

## Why
Two Kaggle runs of the identical candidate_pinned notebook (54.70 and 32.22) paired game by game through
scripts/compare_arm_groups.py give Δ −22.47, 95% CI [−35.68, −10.91], p = 0.004: a "resolved LOSS" on
unchanged code. The script resamples games only; a run-level state (which mechanics were cracked early)
moves many games together, so games are not independent draws and the interval is too narrow. The
same unit-of-analysis error as the July factorial study (trials inside a cluster). Every CI in paper draft
v4.4 comes from this method.

## Method added (no change to the existing statistic; it stays reported)
`--cluster`: two-stage bootstrap. Each resample draws runs with replacement within the arm and within the
control (sizes preserved), computes per-game group means, then draws games with replacement and takes the
mean paired delta. 10,000 resamples, seed 0. Verdict for the paper comes from the cluster CI. With 3 runs per
arm the run stage has 10 distinct multisets per group, so the cluster CI is coarse; it is still the honest one.
Also reported: each run's mean over the compared games, the run-mean sd per group, and the number of runs.

## Arms to recompute (same logs as the result notes)
no-echo (ne1–ne3 vs r2/r3/r4/r6); tower on/off (bo1b–bo3b vs r2–r4); native (na1c–na3c vs r2–r4);
Batch A local (ba1b, ba2b vs r2–r4); AC vs CP on the server (ac1,3,4,5,6 vs cp1–cp5).

## Predictions
- no-echo stays RESOLVED (−29.6 against run sds near 5).
- on/off, native, Batch A stay NOT RESOLVED, intervals wider than now.
- AC vs CP stays centred on zero, wider.
- If any NOT RESOLVED arm becomes resolved under the cluster CI, that is an error in the implementation, not a finding: cluster intervals can only be wider or equal in expectation.

## What happens to the paper
The paper agent swaps each interval for the cluster interval and labels the method; verdict words follow
the cluster CI. No number is removed because it points the wrong way.
