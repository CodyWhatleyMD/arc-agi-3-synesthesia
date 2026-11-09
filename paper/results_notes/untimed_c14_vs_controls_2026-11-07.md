# Untimed (concurrency 14) vs the timed controls: run-level bootstrap (2026-11-07 22:15 CST, CL1)

Pre-stated: prestate_restoration_2026-10-30.md amendments 3-4 (replicates of the anchor with the per-game clock and the job
budget removed, fourteen games at a time as the controls; paired by game; --cluster, runs then games; a CI that excludes 0
resolves). Script: scripts/compare_arm_groups.py --cluster (PRL), on the runs' stdout.log files.

ARM (untimed, c14, same card class and quant as the controls): r0c14 (local RTX PRO 6000, 11-07, 52.31, 13 won, 5.80 lv/game),
r0x2 (vast RTX PRO 6000, 11-07, 60.10, 15 won, 6.12 lv/game). CONTROLS (timed, c14, 9,300 s job budget, 65-min clock): r2, r3, r4, r6
(40.19, 44.26, 41.41, 42.96; 4.12-4.32 lv/game).

| measure | arm | control | delta | game-only 95% CI | run-level (cluster) 95% CI | sign | verdict |
|---|---|---|---|---|---|---|---|
| score | 56.20 | 42.21 | +14.00 | [+5.09, +23.39] | [+1.05, +25.77] | 18/6/1, p=0.023 | GAIN |
| levels/game | 5.96 | 4.21 | +1.75 | [+1.12, +2.40] | [+0.93, +2.49] | 20/2/3, p<0.001 | GAIN |

Run means: arm scores 52.31, 60.10 (sd 5.51); control 40.19-44.26 (sd 1.78). Arm levels 5.80, 6.12 (sd 0.23); control 4.12-4.32 (sd 0.09).

Reading: with the clock removed and nothing else changed, the same notebook gains 1.75 levels a game and 14 score points, and the
run-level interval excludes zero at n=2 vs 4. Caveat (PRL:17): the run stage of the bootstrap is coarse below ~10 runs per arm; this is
reported as RESOLVED at n=2 with the interval shown, and will be recomputed at n=3 (r0x1, landing tonight) and n=4 (r0c14b, 11-08 ~07:00).
The untimed runs' scores include games ended by the 5,184-action cap (r0c14: 12, r0x2: 10) scored as recorded; the cap removes no
progress (experience_efficiency_prelim, 08:30 section). JSON: notes/untimed_c14_vs_controls_n2_2026-11-07.json.

## n=4 (11-08 14:20 CST): r0c14, r0c14b, r0x1, r0x2 vs r2/r3/r4/r6

ARM: r0c14 52.31 (13 won, 5.80 lv/game), r0c14b 58.44 (16 won, 6.12; local 6000, 11-08 05:26), r0x1 59.13 (16 won, 6.32; vast, 19 h 55 m),
r0x2 60.10 (15 won, 6.12; vast, 15 h 17 m). Run sd 3.53 (score), 0.22 (levels). Controls unchanged.

| measure | arm | control | delta | game-only 95% CI | run-level (cluster) 95% CI | sign | verdict |
|---|---|---|---|---|---|---|---|
| score | 57.49 | 42.21 | +15.29 | [+7.71, +23.27] | [+5.22, +25.24] | 20/4/1, p=0.002 | GAIN |
| levels/game | 6.09 | 4.21 | +1.88 | [+1.28, +2.53] | [+1.17, +2.63] | 21/1/3, p<0.001 | GAIN |

JSON: notes/untimed_c14_vs_controls_n4_2026-11-08.json. Figure 4.2 redrawn with all four (per-game sum of gains over the controls: see the
figure's JSON). This is the paper's headline number; the n=2 table above is superseded.


Correction (11-09 13:20 CST, CL1): "amendments 3-4" in the first paragraph should read: the 10-30 pre-statement's design (comparator r2, r3, r4, r6; paired by game; --cluster; a CI excluding 0 resolves) plus Amendment 4 (11-07 16:17 CST, adding r0c14b). The file has no Amendment 3; the word "primary" does not appear in it.
