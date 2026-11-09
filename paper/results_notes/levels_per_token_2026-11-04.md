# Levels per token across our runs (2026-11-04 08:20 CST; Investigator: "which of our runs had the most levels complete per token")
Method: scripts/compare_benchmark_logs.parse_log over every local/server/flattened-Kaggle log with >=10 games and
>=3 Mtok (full-budget runs; short smoke runs play only cheap first levels and rank highest by construction, up to
53 lv/Mtok, excluded). lv/Mtok = sum(levels)/sum(tokens)*1e6; lv/100act = sum(levels)/sum(actions)*100. 43 runs.

Top (timed, 9,300 s or Kaggle commit):
  ba1_9300      23.75 lv/Mtok  1.74 lv/100act  117 lv  4.9 Mtok  score 51.46  (INVALID run: disk hit zero 10-26)
  na2c_9300     19.89           1.27            118     5.9       49.43        (native tower, local)
  ba1b_9300     19.54           1.55            120     6.1       49.23        (Batch A, valid)
  run5470       18.96           1.00            127     6.7       54.70        (candidate_pinned Kaggle commit; most levels)
  gc3 / gs1b    18.5 / 18.5     1.47 / 1.61     112/113 6.0/6.1   45.8 / 46.4  (the rooms)
Timed full runs span 13.8-19.9 (identical code: 54.70 run 18.96 vs its 32.22 re-run 14.55).
No-echo (ne1-ne3): 7.6-8.6. Untimed: R0 6.69 (84 levels, 12.6 Mtok, 0.25 lv/100act); r0rep3 (killed) 4.18; r0rep4 (running) 4.48.

Reading: levels per token is driven by DEPTH and game mix, not by a lever we set: first levels are cheap, later levels
cost several times more, so a run that clears more early levels looks "efficient" and an untimed run that keeps going
on hard levels looks worst. This is prestate_experience_efficiency P1 in the aggregate at n=1 (levels per action falls
untimed while clears rise). Not a ranking of intelligence; a measurement of where the tokens go.
