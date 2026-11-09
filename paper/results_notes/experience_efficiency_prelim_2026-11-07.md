# Experience efficiency off the clock: preliminary (2026-11-07 02:10 CST, CL1)
Pre-statement: notes/prestate_experience_efficiency_2026-11-04.md (61cde8d). Script: the per-game table of
scripts/compare_benchmark_logs.parse_log over the run logs named below; arithmetic in this session (scratchpad
ee_prelim.txt). PRELIMINARY: two untimed runs (one of them stopped early) against four timed; no resolution claim.

## Runs
Timed (anchor 8552964, 9,300 s job budget, per-game clock, local RTX PRO 6000 Max-Q): r2, r3, r4, r6
(~/kaggle_local/run_synesthesia_r{2,3,4,6}_9300.log). Untimed (same harness, no per-game clock, no job budget,
5,184-action cap): R0 (local, concurrency 1, 10-31, STOPPED with the log reading "ended: in progress": 14 of 25 games
played in the harness's order, 11 never started; the 13 the paper has called "finished" are 8 full clears + 5 at the
action cap, the 14th, sc25, was mid-game at 4/6) and ut1 (the GCP server, concurrency 1, 11-03 -> 11-05, 52 h 39 m,
all 25 games: notes/untimed_ut1_result_2026-11-07.md).

| run | games | levels | lv/game | full clears | actions | lv/100 act (E1) | at the 5,184 cap | score |
|---|---|---|---|---|---|---|---|---|
| R0 (stopped) | 25 (14 played) | 84 | 3.36 | 8 | 33,260 | 0.25 | 5 | 35.28 |
| ut1 | 25 | 149 | 5.96 | 17 | 58,439 | 0.25 | 8 | 56.88 |
| r2 | 25 | 103 | 4.12 | 6 | 10,643 | 0.97 | 0 | 40.19 |
| r3 | 25 | 108 | 4.32 | 6 | 9,264 | 1.17 | 0 | 44.26 |
| r4 | 25 | 104 | 4.16 | 7 | 9,128 | 1.14 | 0 | 41.41 |
| r6 | 25 | 106 | 4.24 | 7 | 7,186 | 1.48 | 0 | 42.96 |

Timed means (n=4): 4.21 levels/game, 6.5 full clears, 1.19 levels per 100 actions, score 42.21.

## Readings (all at n=1 complete untimed run; nothing resolved)
- E3, the complete untimed run against the timed mean, paired by game on all 25: +1.75 levels per game, 18 games up /
  3 down / 4 tied; full clears 17 vs 6.5; score 56.88 vs 42.21.
- R0's first-13 subset (the games it reached before it was stopped, chosen by list position, not by outcome): 6.15 vs
  the timed 4.23 on the same 13, 66.23 vs 42.31 (as in the pre-statement; now the secondary number).
- E1: 0.25 levels per 100 actions untimed in both runs vs 1.19 timed (P1 confirmed in direction: the untimed run
  earns its extra levels by spending; it takes 6.45x the actions, 58,439 vs the four-run mean 9,055, for 1.4x the levels).
- E4 from the runs' own benchmark.json (scripts/experience_efficiency.py; a game ended by the clock = not won and
  final_wallclock_seconds >= 95% of the 3,918 s per-game clock; the 11-07 version summed the per-action wallclock,
  which happened to give the same counts here; fixed the same day): twelve timed runs, 17 to 21 of 25 games each,
  mean 19.0 (Kaggle C1-C7 + v36: 18/21/17/20/20/19/20/19; local r2/r3/r4/r6: 19/19/18/18). Every unwon game in all
  twelve has its final wallclock at or above the cap; none ended by the model stopping. Untimed: 5 of R0's 14, 6 of
  r0rep3's 15, 3 of r0rep4's 9 ran to the 5,184-action cap; ut1 8 of 25.
- E2 from benchmark.json (actions_per_level), Kaplan-Meier, MATCHED on the 15 games the three partial untimed runs
  played (R0 + r0rep3 + r0rep4, 38 played games, in-progress censored; ut1 has no benchmark.json): timed = the same
  15 games in all twelve timed runs (180 games). Within the actions a timed game ever gets, the timed regime is as good
  per action as the untimed one or better; the two part only where the timed curves have no games left:
    level 1 within 1,000: 0.98 vs 1.00
    level 3 within 1,000: 0.90 vs 0.89; within 3,000: 0.90 vs 0.92
    level 5 within 1,000: 0.66 vs 0.53; within 3,000: 0.66 vs 0.74
    full clear within 1,000: 0.53 vs 0.45; within 3,000: 0.53 vs 0.53 (timed median 563 actions; untimed 1,930)
  Last timed event per curve: 258 / 783 / 674 / 563 actions; 2 of 180 timed games exceed 1,000 actions, so the timed
  curves past ~800 are carried forward from nothing. The unmatched 4-run version (11-07 03:20) read 0.57 vs 0.53 at
  level 5 within 1,000 and 0.44 vs 0.45 for full clears; the matched set is a prefix of the game list and is easier
  for both regimes. The reading that survives: per action the model plays the same with or without the clock, and
  the untimed advantage is entirely the actions beyond ~1,000 that the clock never allows (P2, in that form).
  notes/experience_efficiency_matched_2026-11-07.json holds the curves; the unmatched run is
  notes/experience_efficiency_2026-11-07.json.
What settles it: the third and fourth untimed runs (r0c14 local, r5s/r0c14s server) and run-level intervals.

## The action cap is not a cut (11-07 08:30 CST)

Investigator: "...5184 action cap?" The cap is ours (prestate_restoration_2026-10-30 l.65: 4 x 1,296, the longest timed game). Checked on
the five local untimed benchmark.json files (R0, r0rep2, r0rep3, r0rep4, r0c14 partial): 21 capped games, all from eight ids
(bp35 cd82 ka59 lf52 sp80 tn36 tr87 wa30). Last clear before action 2,592 in 20 of 21 (the exception bp35/R0 at 3,045); none in
the final 20%; actions on the unfinished level median 4,386, min 2,139, max 5,155. The cap ends stuck games; it removes no
progress. Field note: in benchmark.json, actions_per_level includes the unfinished level as its last entry (sum = total actions);
levels_completed is the count of cleared levels. Two earlier reads this morning used the wrong field; this is the corrected one.

## The end-state check (11-07 08:40 CST) -- what the survival curves cannot show

Investigator: "what are you actually saying that that chart doesn't show". The state of a game at the instant each regime ends it.
Timed (v36 controls r2/r3/r4/r6): 74 games ended at the clock; last clear at median 0.76 of the game's time; 45% cleared a level
in the final 20%; actions on the unfinished level at the clock median 65 (max 1,313). All 24 local 9,300-s arms: 446 games,
median 0.76, 43%, 68. Untimed capped (R0, r0rep3, r0rep4, r0c14 finished): 20 games, actions on the unfinished level median 4,369,
min 2,139. Per game, untimed (n=1-4) minus the four controls' mean: sk48 +6.00, cn04 +3.25, r11l +3.00, m0r0 +2.75, ka59 +2.67,
sp80 +2.25, sc25 +2.08, lf52 +2.00, tu93 +2.00, sb26 +1.75, tn36 +1.25, wa30 +1.00, bp35 +0.75, vc33 +0.75, tr87 +0.50,
lp85 0, ar25 0, ft09 0 (never clocked), cd82 -4.00 (n=1, stalled at 2/6 where all controls cleared 6). Sum +28 over 19 games.
A first version of this check (08:35) classified every non-9,300 benchmark file as untimed (dflash, kvtier, smoke, c17/c20/c25)
and showed losses everywhere; discarded. The figure to make when r0c14 and the replicates land: levels per game, four
controls as a band, untimed points, 25 games, ordered by how often the clock ended the game.
