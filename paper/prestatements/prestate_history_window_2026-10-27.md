# Pre-statement: the board-history window as a VARIANCE experiment (written 2026-10-27 20:27 CDT, before any run)

Why (CL3, 20:23 and 20:26): the shipped harness accumulates every board ever sent until compaction (median 13, max
48 boards per request), so behaviour depends on WHEN compaction fires; that is harness-driven variance. Measured
tonight (notes/noise_structure_2026-10-27.md and below): 45% of a game's score variance is run-to-run (ICC 0.55);
compaction first fires at a median 13% of the game's clock (p75 0.17, p90 0.28; 74/75 game-runs compact); the
between-run variance of levels cleared grows from 0.21 (clock 0.1) to 2.16 (0.5) and plateaus ~2.3 after 0.6.
Caveat stated now: that growth is also consistent with luck accumulating over time, so the curve alone does not
discriminate; the WINDOW's effect on the curve does.

## Step 0 (before the online arm): the offline replay, CL3's test, derives K instead of picking it
Take logged requests from the valid ON runs (r2, r3, r4), rebuild each prompt with its board history cut to the
newest K boards for K in {1, 4, all}, send to the same model at temperature 0, and measure agreement of the
model's chosen action with the action it actually took. If agreement at K=1 is in the high nineties the model does
not read old boards; if it falls off, the fall-off locates K. No game stochasticity. Production sampling settings
are read from the run config first; if it samples above temperature 0, compare action distributions instead.
Needs the 6000 (the 5090 cannot hold the served model): runs after na3c, ~04:30 on 10-28. One hour.

## Online arms (only if step 0 shows the model reads old boards at some K)
- Control: the shipped accumulation. r2, r3, r4 (8552964) and r5b (syn/batch-a all-off, bfab595e, equal to the
  anchor by the parity tests). No new control runs unless the window build changes the harness under them.
- K=1 and K=4: a PER-TURN window (the newest K boarded user messages keep their board part every turn; older ones
  carry a one-line note), as a new SYN_* switch on syn/batch-a, default off = shipped. NOT the existing
  SYN_HISTORY_BOARDS_KEEP, which strips only at compaction and therefore cannot change when compaction fires.
  Three runs each, 9,300 s, GPU 1, disk-gated. Two treatment points give a trend; K=1 answers "at all".

## Primary outcome: the variance, with its predicted signature
Within-game (run-to-run) variance component of per-game score, and ICC, per arm (three runs each). Prediction if
accumulation is the mechanism: the between-run variance of levels cleared vs clock fraction grows more slowly under
the window than the shipped curve above (0.21 -> 2.16 over clock 0.1-0.5; variance/mean ratio 0.74 at clock 0.5),
with the reduction concentrated after clock ~0.13 (the first compaction). If the window's curve matches the shipped
one, accumulation is not the mechanism and the window does not fix the luck, whatever it does to the score.
Secondary: mean score vs control (compare_arm_groups.py); actions per job-second; the payload (MB per request).

## My prior
Step 0: agreement falls off between K=1 and K=4 and is flat from K=4 to all (the model reads the last few boards,
not the history). Online: the variance curve flattens modestly under K=4 (growth to clock 0.5 below 1.5), score
NOT RESOLVED at 3 vs 4. I would be glad to be wrong in either direction.

## Invalid-run criteria: as the on/off pre-statement, plus the request-log check that no request carries more than K
board parts (window arms) and the usual zero HTTP 400.

## Clarification 1 (20:29 CDT, CL3; before any run)
- The shipped curve (0.21, 0.61, 1.17, 1.81, 2.16) is near-linear from the start, as a random walk in levels would
  be, with the first compaction (0.13) inside the first rise; it is compatible with both stories. Only the window's
  curve discriminates (the prediction above stands).
- The plateau after clock 0.5 is probably games finishing (variance capped by levels remaining): compare arms on the
  same clock fractions and ONLY up to 0.5.
- Step 0 also logs where K=1 actions disagree with the shipped actions as a function of clock fraction; disagreement
  concentrated after ~0.13 is a third line of evidence for the mechanism, from data with no luck in it.
- Timestamps in this file and in notes/noise_structure_2026-10-27.md were corrected at 20:30: I had written 20:40 and
  ~20:50 by estimating elapsed time from the amount of work done. The clock on every turn read 20:22-20:29. The
  whole exchange with CL3 took seven minutes, not the "hour" I called it twice. (the investigator caught it.)
