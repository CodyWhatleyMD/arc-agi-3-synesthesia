# r0c14: untimed at concurrency 14, local 6000 (read 2026-11-07 16:15 CST, CL2) -- n=1
Anchor harness, our v22, 25 public games, no per-game clock, no job budget, 5,184-action cap, concurrency 14
(RUN_CONFIG.json: kernel codywhatleymd/arc-agi-3-synesthesia-r0-untimed-c14, harness dataset arc3-synesthesia-harness-r0,
max_runtime_s_per_game None, analyzer_timeout 900), on our RTX PRO 6000 Max-Q. Log times are UTC: started 07:16:56Z,
ended 22:09:14Z (01:16 -> 16:09 CST), 14 h 52 m 17 s (~/kaggle_local/run_synesthesia_r0c14.log, summary block l.5001-5013;
~/kaggle_local/working_r0c14/synesthesia/benchmark.json).
RESULT (n=1): mean score 52.31 | median 49.81 | 145 levels = 5.80 per game | 13 of 25 games fully cleared (= 13 won) |
12 games at the 5,184-action cap | 72,920 actions | 30.46 Mtok | 0.199 levels per 100 actions.
The hand count in the 16:12 status was checked against benchmark.json and holds on every figure.

Why this run matters for §4: it is the CONCURRENCY-MATCHED untimed run. The timed fixed-host controls r2, r3, r4, r6 ran
at concurrency 14 with a 3,918 s per-game clock and a 9,300 s job budget (parse_log config of each
run_synesthesia_r{2,3,4,6}_9300.log). r0c14 differs from them in the clock, the job budget and the 5,184 cap, not in
concurrency or card. ut1 (concurrency 1, the GCP server) differs from them in concurrency and machine as well.

## Per run (sources: compare_benchmark_logs.parse_log over the run logs; same numbers from experience_efficiency.py
## on benchmark.json where one exists; ut1 has no benchmark.json, only ~/kaggle_local/server_runs/ut1/run.log)
| run | clock | conc. | levels | lv/game | full clears | actions | lv/100 act (E1) | E4: ended by limit | score |
|---|---|---|---|---|---|---|---|---|---|
| r0c14 | none | 14 | 145 | 5.80 | 13 | 72,920 | 0.20 | 12 at the cap | 52.31 |
| ut1 | none | 1 | 149 | 5.96 | 17 | 58,439 | 0.26 | 8 at the cap | 56.88 |
| r2 | 3,918 s | 14 | 103 | 4.12 | 6 | 10,643 | 0.97 | 19 by the clock | 40.19 |
| r3 | 3,918 s | 14 | 108 | 4.32 | 6 | 9,264 | 1.17 | 19 by the clock | 44.26 |
| r4 | 3,918 s | 14 | 104 | 4.16 | 7 | 9,128 | 1.14 | 18 by the clock | 41.41 |
| r6 | 3,918 s | 14 | 106 | 4.24 | 7 | 7,186 | 1.48 | 18 by the clock | 42.96 |
Timed mean (n=4): 4.21 levels/game, 6.5 full clears, 1.19 levels per 100 actions, 18.5 clock-ended, score 42.21.
E4 is from scripts/experience_efficiency.py at HEAD 35bba9e (the cumulative-wallclock bug fixed at d3e20b0; it now reads
final_wallclock_seconds), --clock-s 3918 --cap 5184; output kept in this session's scratchpad (ee_r0c14.txt/.json).

## Paired by game against the timed mean (r2, r3, r4, r6), all 25 games
Game-level bootstrap, 10,000 resamples, seed 0, plus the sign test from compare_benchmark_logs. The bootstrap resamples
GAMES only; it carries no run-to-run variance for the untimed arm, which is n=1 per configuration here. The run-level
(--cluster) pass is CL1's once r0x1 and r0x2 (the same r0c14 notebook on vast) land and this configuration is n=3.
| untimed run | measure | mean diff per game | 95% game-bootstrap | up / down / tie | sign-test p |
|---|---|---|---|---|---|
| r0c14 | levels | +1.59 | [+0.74, +2.43] | 18 / 4 / 3 | 0.004 |
| r0c14 | score | +10.10 | [-2.15, +21.84] | 15 / 8 / 2 | 0.21 |
| ut1 | levels | +1.75 | [+1.07, +2.42] | 18 / 3 / 4 | 0.002 |
| ut1 | score | +14.67 | [+4.09, +25.55] | 16 / 7 / 2 | 0.09 |
Reading: on levels, both untimed runs are above the timed controls with game-level CIs clear of zero; on score, r0c14's
CI includes zero. All four of r0c14's down games (bp35, cd82, cn04, s5i5) ended at the 5,184 cap; cd82 is the largest
single loss (2 levels against 6.00 timed and 6 in ut1). The three ties are ar25, ft09, lp85 (cleared in every run).

r0c14 against ut1, by game: levels -0.16 per game (5 up / 7 down / 13 tied, p 0.77), score -4.57 (9 / 11 / 5, p 0.82).
How big that is depends on which spread you hold it against, and none of them is an untimed spread (there is none yet):
it is inside the Kaggle control pool's sd (C1-C7, 5.07) and the Arm B single-GPU controls' sd (5.0), and outside the
local timed four's sd (1.78 over r2/r3/r4/r6). The two runs differ in concurrency AND machine, so this note does not
attribute the gap to either.

## E2: actions to reach level k (Kaplan-Meier; timed 100 games, untimed r0c14 25 games)
| level | timed: median / within 100, 300, 1000, 3000 | r0c14: median / within 100, 300, 1000, 3000 | at curve end |
|---|---|---|---|
| 1 | 23 / 0.88, 0.95, 0.97, 1.00 | 24 / 1.00, 1.00, 1.00, 1.00 | 1.00 vs 1.00 |
| 3 | 132 / 0.37, 0.69, 0.89, 0.89 | 170 / 0.36, 0.68, 0.84, 0.88 | 0.89 vs 0.88 |
| 5 | 393 / 0.04, 0.41, 0.57, 0.57 | 454 / 0.08, 0.36, 0.60, 0.68 | 0.57 vs 0.76 |
| every | -- / 0.01, 0.26, 0.44, 0.44 | 3,102 / 0.00, 0.20, 0.40, 0.48 | 0.44 vs 0.52 |
Same shape as §4's twelve-run figure: the curves track each other to ~1,000 actions, and the untimed gain is in the tail
the clock never reaches (only 3 of the 100 timed games pass 1,000 actions; 15 of r0c14's 25 do). Figure:
notes/fig_untimed_r0c14_survival_2026-11-07.{svg,png} (scripts/plot_survival.py over the ee JSON; timed = r2/r3/r4/r6).

## Per game (r0c14 levels/total | ut1 levels | timed-mean levels | r0c14 actions | r0c14 score)
ar25 8/8 | 8 | 8.00 | 334 | 100.00 -- bp35 1/9 | 5 | 1.50 | 5184 | 1.17 -- cd82 2/6 | 6 | 6.00 | 5184 | 5.13 --
cn04 2/6 | 6 | 2.75 | 5184 | 5.48 -- dc22 5/6 | 4 | 3.50 | 5184 | 29.95 -- ft09 6/6 | 6 | 6.00 | 144 | 100.00 --
g50t 6/7 | 1 | 2.75 | 5184 | 30.33 -- ka59 6/7 | 6 | 3.00 | 5184 | 49.81 -- lf52 3/10 | 5 | 2.50 | 5184 | 2.00 --
lp85 8/8 | 8 | 8.00 | 143 | 100.00 -- ls20 6/7 | 7 | 2.25 | 5184 | 33.07 -- m0r0 6/6 | 6 | 3.25 | 452 | 99.71 --
r11l 6/6 | 6 | 3.00 | 121 | 100.00 -- re86 8/8 | 8 | 6.00 | 2586 | 61.22 -- s5i5 4/8 | 8 | 4.75 | 5184 | 17.98 --
sb26 8/8 | 8 | 6.25 | 149 | 100.00 -- sc25 6/6 | 6 | 3.25 | 544 | 56.79 -- sk48 8/8 | 4 | 1.00 | 1673 | 54.01 --
sp80 5/6 | 1 | 1.75 | 5184 | 45.24 -- su15 9/9 | 9 | 4.00 | 3102 | 29.53 -- tn36 7/7 | 7 | 5.00 | 764 | 59.92 --
tr87 5/6 | 6 | 4.50 | 5184 | 41.30 -- tu93 9/9 | 9 | 7.00 | 270 | 100.00 -- vc33 7/7 | 7 | 6.25 | 430 | 78.85 --
wa30 4/9 | 2 | 3.00 | 5184 | 6.15

## Pending
r0x1, r0x2 (this notebook, vast, France) make the configuration n=3; r5x1, r5x2 are the native-tower untimed arm (R5).
Both pairs are still playing (16:00 CST: 20-21 of 25 games each). r0c14b (CL1's second local c14 pass) started on the
6000 after this run ended. compare_arm_groups.py --cluster is CL1's pass once those land.
