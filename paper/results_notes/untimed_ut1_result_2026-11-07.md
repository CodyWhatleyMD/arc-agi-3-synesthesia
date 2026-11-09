# ut1: the second untimed pass, on the GCP server (read 2026-11-07 01:15 CST)
Anchor harness 8552964, our v22, 25 public games, no per-game clock, no job budget, 5,184-action cap, concurrency 1
(the R0 notebook, staged synesthesia_r0, nb sha 630a9c6b), on the Kaggle-shaped g4-standard-48 Spot VM.
Started 2026-11-03 07:37:20Z (restart after a preemption), ended 2026-11-05 12:16:25Z, 52 h 39 m. Uploaded by the
queue guard to gs://CL1-arc3-uc1/runs/ut1/ (DONE); copied to ~/kaggle_local/server_runs/ut1/.
RESULT: mean score 56.88 | 149 levels = 5.96 per game | 17 of 25 games fully cleared | 8 games hit the 5,184-action cap |
58,439 actions | 29.7 Mtok | 0.25 levels per 100 actions.
Against: R0 (local 6000, 10-31, 13 games finished) 6.15 levels/game, 66.23; the timed fixed-host controls r2-r6 about
4.2 levels/game and ~42 (notes/run_level_ci_results; paper §4). Untimed is now n=2 (one of them partial). The other
untimed attempts died with the machine: r0rep3 (killed 11-03), r0rep4 (crash 11-04 18:10, 18.5 h in), Colab r5/r0c
(pollers died in the crash, sessions expired at 24 h, nothing retrieved). prestate_experience_efficiency E1-E4 can be
computed on R0 + ut1 (+ r0c14 if it finishes: local, concurrency 14, started 11-07 01:15 CST).

Note (11-08): no benchmark.json exists for this run anywhere (bucket, VM, local drives; CL2's search). The server's queue guard uploaded only the logs and the executed notebook; the per-game results are the final table in its stdout.log, kept in the results repository under results/server/ut1/.
