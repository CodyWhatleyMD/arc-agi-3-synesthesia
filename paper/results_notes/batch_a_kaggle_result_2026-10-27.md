# Batch A on Kaggle: three same-time pairs, the pre-stated read -- 2026-10-27 21:12 CDT
Design: notes/prestate_batch_a_2026-10-26.md (Clarifications 3-10). Arm = Batch A (syn/batch-a 12a000d, 11 SYN_*
switches on) vs control (same commit, all off = v8 prompt sha 6521089c), both from the arms dataset, RTX PRO 6000
hosts, 9,300 s job budget, pushed as same-time pairs after the serial fallback was abandoned (Clarification 5).
All six runs VALID on every gate before any score was read (CL2, gates first): 0 harness tracebacks (A2 and A3 each
had one sandbox death inside a stderr block, excluded under Clarification 1; C1 checked from its stdout log: 0),
0 HTTP 400, switches-checked lines present ({} for C, 11 True for A), 25/25 games played, tower parts present.
Logs: ~/kaggle_local/kaggle_runs/{A1_k3_362923544, A2_k4_362959199, A3_k5_362988134, C1_probe-arms-newk_362774583,
C2_control-k2_362959205, C3_control-k3_362988126}/stdout.log. Script: scripts/compare_arm_groups.py; JSON:
notes/batch_a_kaggle_primary_2026-10-27.json.

## Primary (pre-stated): group means, paired-by-game bootstrap, both tails
| | arm (A1-A3) | control (C1-C3) | delta A-C | 95% CI | sign (A>C / A<C / tie) |
|---|---|---|---|---|---|
| score (public 25) | 41.15 | 40.16 | **+0.98** | [-5.80, +8.62] | 13 / 12 / 0, p = 1.000 |
| levels | 4.19 | 4.13 | +0.05 | [-0.31, +0.43] | 10 / 9 / 6 |
**NOT RESOLVED at n = 3 vs 3.** The interval excludes a loss worse than about 6 points and a gain beyond about 9.

## Per pair, with Clarification 9's covariate (play seconds; load minutes), exploratory
| pair | C | A | A-C | paired CI | C play s | A play s | C load | A load | note |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 41.96 | 41.89 | -0.07 | [-15.9, +15.2] | 8,110 | 7,402 | 10.1 | 21.7 | load-confounded: A played 708 s less and tied |
| 2 | 32.57 | 34.83 | +2.26 | [-8.8, +12.8] | 7,454 | 7,521 | 21.0 | 19.7 | balanced |
| 3 | 45.95 | 46.72 | +0.77 | [-8.3, +10.0] | 7,843 | 7,749 | 14.3 | 15.9 | balanced |
Wins (games at 100): C 7/4/8, A 7/5/8. Sandbox deaths: C 0/0/0, A 0/1/1. tok/s round 3: C 745.7, A 767.2.
Note the pair-to-pair swing of the CONTROL (32.57 to 45.95): the same code, 13.4 points apart, which is the
single-run noise the design was built around.

## Exploratory (pre-stated as exploratory; not for ranking)
Coin-flip games (10): share of runs at >= 50: arm 0.27, control 0.37 (the local test had 0.50 vs 0.27; the two
platforms disagree in sign, as a coin flip does). Stable bottom five, mean levels: arm 2.33, control 1.93 (ls20 4.0 vs
2.7 carries it; bp35 1.33 vs 1.0; lf52 equal).

## Read across platforms (NOT pooled; Clarification 5 forbids pooling)
Local (notes/batch_a_local_result_2026-10-27.md): +3.45 [-4.35, +10.92], n = 2 vs 3. Kaggle: +0.98 [-5.80, +8.62],
n = 3 vs 3. Two independent tests, both positive in direction, neither resolved; the consistent statement is that
Batch A is not a large effect in either direction. Resolving an effect of +1 to +3 points needs on the order of
28 runs per arm (the on/off interval scaled), which the remaining quota (95,672 s, about 9 runs, resets 10-31
00:00Z) cannot buy; four more pairs would take Kaggle to 7 vs 7 and an interval of roughly +/-4.6, which resolves
only an effect of that size or larger.

## What this does and does not say
It does not say Batch A helps; it does not say it hurts; it says the harness fixes it bundles are safe to carry
(no loss beyond ~6 points at 95%) and that their gain, if any, is below what six runs per platform can see. The
hidden set is untested. Rounds 1-3 ran 12a000d; the ultrareview fix (7570e11, merged 21:05) changes only
400-containing trajectories, which the gates exclude (Clarification 10).
