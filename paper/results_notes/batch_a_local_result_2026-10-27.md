# Batch A, local result (2026-10-27 06:40 CDT), read against notes/prestate_batch_a_2026-10-26.md

Platform: RTX 6000 Max-Q, 9,300 s job budget, all 25 games started in every run. Validity checked BEFORE any score
was read (pre-statement criteria + Clarifications 1-2): all six runs have 0 harness tracebacks, 0 HTTP 400s, every
cell ended, 25/25 games started, and the expected switch line (11 True for batch-a, {} for r5b). The disk stayed
>= 116 GB free through the rerun chain. ba1 (the original) is excluded by Clarification 2 (disk filled), ruled
before its score was read; ba1b/ba2b are its reruns.

Runs: batch-a = ba1b 49.23, ba2b 41.58. Controls = r2 40.19, r3 44.26, r4 41.41 (anchor notebook, harness
8552964), r5b 47.09 (arms notebook, 12a000d, all switches off; added after the pre-statement, before any score).

## Primary statistic (pre-stated): batch-a x2 vs r2, r3, r4

| metric | batch-a | control | delta | 95% paired bootstrap CI (10,000) | sign test | reading |
|---|---|---|---|---|---|---|
| score | 45.40 | 41.96 | **+3.45** | [-4.35, +10.92] | 14/9/2, p = 0.405 | **not resolved at this n** |
| levels | 4.56 | 4.20 | +0.36 | [-0.05, +0.77] | 15/6/4, p = 0.078 | not resolved at this n |

## Secondary (reported, not deciding)

- + r5b as a fourth control (same harness commit): score +2.17 [-5.62, +9.86]; levels +0.26 [-0.13, +0.66].
- vs r5b alone (n = 1 control): score -1.69 [-13.58, +11.05]. r5b is the highest-scoring control run, which is
  the noise itself: adding one run moves the estimate by ~1.3 points.

## Exploratory (labelled; never deciding)

- Coin-flip games (cn04 dc22 m0r0 r11l s5i5 sb26 sc25 sp80 tn36 vc33): share of game-runs scoring >= 50,
  batch-a 0.50 vs control 0.27.
- Stable bottom (bp35 lf52 sk48 wa30 ls20): mean levels 2.20 vs 2.20 (no change).
- Sandbox deaths (Clarification 1, counted symmetrically from the model-facing text): r2 1, r3 0, r4 1, r5b 0,
  ba1b 0, ba2b 0.

## Reading

Not resolved at this n. The point estimate is positive (+3.45) and inside what the pre-statement's prior expected
(0 to +6); with two arm runs against three controls the interval still spans zero, as the prior (~65% "not
resolved" locally) said it probably would. This is not "no effect". The levels statistic is closest to resolving
(p = 0.078) and the coin-flip share is suggestive, but both are below the pre-stated bar or exploratory. The
pre-stated next evidence is the three Kaggle same-time pairs (round 1 running).

Reproduce: scripts/compare_arm_groups.py (reuses compare_benchmark_logs.parse_log/bootstrap/sign_test; seed 0);
JSON: notes/batch_a_local_primary_2026-10-27.json.
