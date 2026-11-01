# Pre-statement: fixes for the review's three blocking issues in the pool clock's time stop (8d10d07), before any test run

Written 2026-11-01 ~00:50 CDT, before running any test of the changed code. Code: branch pool-clock (worktree
~/github/arc-prize-2026-poolclock), on 8d10d07, solver.py and tests/pool_clock, uncommitted at the time of writing.
Already done before writing this, so not predictions: reading the review (the orchestrator's task text: issues 1-3 with
the reviewer's scenarios R1, R2, R3, R6 and their numbers), notes/prestate_pool_time_stop_review_2026-10-31.md, and
extracting the request latencies of the Kaggle 14-stream controls C1-C7 (18,684 metrics `request` events; mean 32.4 s,
p50 19.6, p90 72.0, p99 198.3, max 718.4; mean wait from a random moment to the next request boundary 41.4 s, its
90th percentile 99.0 s; 3 requests over 600 s). The 1,000-quantile table of those latencies is
tests/pool_clock/c1c7_request_latency_quantiles.txt (its own mean 32.3, wait p90 98.0, max 453.9).

## The changes

1. Issue 1, the reserve counted slot by slot. 8d10d07 breached when (concurrency x left - committed) / unstarted < M,
   pooling slot-time over all slots, so its last wave of r games was placed ~r x M / 14 before the end. Now
   (`_pool_reserve_capacity`): a slot frees in a = the rest of its game's share + its boundary wait, then holds the
   k games with a + k x M + (k - 1) x w <= left (w = the pooled boundary wait); breached when the sum over slots of
   those k is below the number of unstarted games.
2. Issue 1(a), the boundary wait. 8d10d07 budgeted the slot's mean seconds per action (~13 s). Now: the 90th percentile
   of the wait from a random moment to the game's next should_stop poll, time-weighted over its recent gaps between
   polls (the q with sum((gap - q)+) = 0.1 x sum(gap); near-zero gaps inside a turn carry no weight), else over all
   games' gaps, else (no gap yet) the old mean seconds per action; at most the analyzer timeout. 99.0 s on C1-C7.
3. Issue 2, protection while the reserve binds. A game taking a slot is protected for min(its fluid budget, max(M,
   left - need x (M + w))), where need = the unstarted games after it that the other slots cannot fit: M (not the
   600 s floor, not a larger fluid share) when the reserve binds, more only while the plan stays feasible, unchanged
   when it does not bind or M is unset.
4. Issue 1(c). A game is not stopped by the reserve before its first action in its slot (it is waiting on its first
   model request; the stop then takes effect at the poll right after that action), unless it is one analyzer timeout
   past its share.
5. Issue 3, the end of play. New `pool_end_margin_s`, default 600 s (v36's ARC3_END_MARGIN_S): on a run with the pool
   clock, an end epoch and no soft end (a scored rerun), play ends at end epoch - margin: `_run_games` sets the stop
   event there, requests are capped to end by then, unstarted and parked games finish without playing, it waits at
   most cancel_drain_timeout_s (120 s) for the game tasks, finishes every open game and returns, so TAAF closes the
   competition scorecard. Shares and the reserve count slot-time to the end of play. With a soft end (a commit run,
   where the notebook sets the end epoch to the soft end) nothing changes. None = no end stop.
   Not changed: the builder (main checkout). With the default 600 s the builder's current pool-clock notebook gets the
   end of play on a scored rerun without a new flag.

## What refutes "it is fixed" (all on the REAL solver; 100x clock for the scenarios, scorecard = the real
## taaf.game_api._CompetitionScorecard on a fake arcade)

Scenarios (tests/pool_clock/_scen.py; marathon = clears every 2 actions, never wins; never = never clears; "fixed" =
10 s requests of 1 action; "mix" = C1-C7 latencies, geometric(2.5) action batches, seeded; park off unless stated;
every request cut at request_timeout_seconds as the real analyzer's HTTP timeout cuts it). On this checkout:
- R1 (issue 2): 14 marathon + 30 never, T 3,000 s, M 300 s, fixed, killed at T. Refuted if any game does not act
  before T, or the last never game's first action is < 150 s before T.
- R2: 14 marathon + 30 never, T 3,000 s, M 600 s, fixed, killed at T. Refuted if any game does not act before T or
  the last first action is < 300 s before T.
- R6: 14 marathon + 1 never, as R2. Refuted if the never game's first action is < 300 s before T.
- R3: 14 marathon + 85 never, T 8,000 s, M 600 s, mix, seeds 1, 2, 3. Refuted if in any seed a game does not act
  before T or the last first action is < 300 s before T.
- E (issue 3): no soft end, end epoch T 3,000 s, margin 600 s, 14 marathon + 6 never, stall 1,500 s, M 600 s, mix,
  not killed. Refuted unless: the run returns by itself; the scorecard closes exactly once and before T; every game
  has a final score; nothing crashed; no traceback; no action later than the end of play + 10 s; exactly one "end of
  play" line; at least one game with stop reason pool_end.
- EU: E with no time knobs (6 games unstarted at the end of play): as E, and the 6 finish with 0 actions, cancelled.
- EP: 2 slots, 4 never games, park on, stall 300 s, no reserve: as E, and the games still parked at the end of play
  are finished, cancelled.
Known-bad comparators (must MISS the criterion, else the scenario cannot show the fix and is VOID, not passed):
- R1, R2, R6 on `git archive 8d10d07 harness/src`. Expected from the review: R1 2 never act; R2 last first action
  47-76 s before T; R6 36-42 s.
- R3 on 8d10d07: reported only (the review saw 6-9 of 85 never act under its own request model, not this one).
- E0 = E with pool_end_margin_s None on this checkout, killed at T: the scorecard must not close before T.
- E on 8d10d07: it must not end by itself (the watchdog stops it 1,000 s after T).
Unit checks (tests/pool_clock/test_time_stop.py; any FAIL refutes): U0 defaults (pool_end_margin_s 600 s, also on the
solver unpickled from harness/benchmark_initial.pkl); U3 the slot-by-slot count equals the test's own count (140 in its
setup), breached at count + 1 and not at count, the boundary wait alone tips it, it fires where 8d10d07's pooled test
did not (1 unstarted, 605 s left), only over-share games stop, not before their first action unless overdue, never
with 0 unstarted, no end epoch or M <= 0; U4 the new reserve stop line; U5 protection 300 s (floor 600) and 600 s
(fluid 840) while binding, 591 s with one game of slack, the plain fluid share when not binding or off; U6 the wait
quantile (10 s gaps -> 9 s, not diluted by 2 ms gaps, the C1-C7 table -> 95-101 s), own > pooled > mean s/action,
capped at 900 s, should_stop records gaps >= 1 ms; U7 the end of play applies only with pool clock + end epoch +
margin + no soft end, requests capped (0.1 s past it), shares counted to it, stop reason pool_end.
No regression (refuted by any FAIL): test_off_unchanged (all knobs off incl. pool_end_margin_s None, identical to
6091476 on 5 scenarios), test_park_resume, test_run_110 arms A (>= 10 never start, else VOID), SR, SRP, SRPD with
their 10-31 criteria, and a new arm PLAN (stall 1,500 s, M 600 s, park off, margin 600 s, no soft end, no kill):
every game acts before the end of play, the run returns by itself before the end epoch, the scorecard closes once
before it, every game scored, no crash, no traceback.

Expectations, not criteria: R2/R6 last never game's first action ~550-600 s before T; R1 ~250-300 s; R3 >= 400 s.

## Conditions

A local GPU run (container arc3-local-kvtier_kt3) holds the RTX 6000. Every test process runs alone (sequentially),
nice 19, OMP_NUM_THREADS=1, pinned with taskset to 4 CPUs, so its 14 mostly-sleeping game threads can use at most 4
hardware threads. Every run is reported, including failures and VOIDs.

## Amendment 1 (~00:45 CDT, after the first runs)

The header's "~00:50 CDT" is wrong: this note was committed at 00:39:06 (4e89493) and the first test log is from
00:39:15. The text above is unchanged.

## Amendment 2 (~01:25 CDT, after the first full suite; before any diagnostic run)

Results so far, every run: test_time_stop 43/43 (twice); test_off_unchanged and test_park_resume pass (twice);
test_run_110 passes (A 58 never started, PLAN 110/110, returned 39.78 s, scorecard closed 39.80 s of 40.5);
test_end_of_play passes twice (both comparators miss, as they must). test_reserve_tail run 1 passed (R1 290 s, R2 598,
R6 585 and 587, R3 seeds 1-3 584 / 468 / 501; 8d10d07 missed R1 R2 R6, and R3 had 1 / 2 / 1 never acting). In the
full suite (run 2) it FAILED: R3 seed 2 on this checkout, last two first actions 204 / 211 s before T (slots taken
238 / 260 s before T); R1 290, R2 593, R6 590, R3 seeds 1 / 3 634 / 461. So "it is fixed" is refuted for R3 as
pre-stated. Two candidate mechanisms, to be told apart with per-game end times and slot segments (instrumentation
added now) on R3 seed 2, this checkout, 3 runs: (a) a game took a slot when the reserve did not bind (need <= 0) and
got its uncapped fluid share, so its slot stayed protected past the point the plan later needed it: the slot a late
game (taken < 400 s before T) takes was then held by a game whose protection ended < 400 s before T; (b) the plan was
on time but the game holding that slot was over its share early (protection ended >= 600 s before T) and its stop
came late, a long request in flight: its stop came > 200 s after its protection ended or after the breach. If late
games appear and neither pattern holds, both are refuted.

## Amendment 3 (~01:40 CDT, after the 3 diagnostic runs; before any change or rerun)

Diagnostic runs, R3 seed 2, this checkout: last first actions 548 / 561 / 243 s before T (slots 575 / 628 / 270). Run 3
traced: the last 4 games (never-095..098) took the slots of never-072, -073, -071, -081, whose protection had ended
1,218 / 1,212 / 1,253 / 811 s before T (budgets exactly 600 s) and whose stops came 454 / 119 / 182 / 454 s after
their last analyze call (two 454 s requests, the table's maximum). The other 10 slots held the previous wave, taken
820-637 s before T and protected to the end. So (b) holds and (a) is refuted: the plan was on time; one budgeted
wait per transition at the 90th percentile (98 s on the table) is exceeded by about 1 slot in 10, and a final wave that
depends on specific slots inherits their worst wait. Wait quantiles of C1-C7 (raw / table): p90 99 / 98 s, p95 146 /
143, p98 221 / 213, p99 283 / 269, p99.9 510 / 422; P(wait > 300 s) = 0.8%.
Change (one variable): _POLL_WAIT_QUANTILE 0.9 -> 0.99, everything else as is. Expected cost: the reserve's first
breach comes about ceil(unstarted / 14) x 170-185 s earlier, so the games holding the slots then lose that much play.
Refuted (as a fix of the failure) if, on this checkout with the change, any of 9 runs of R3 (seeds 1, 2, 3 x 3)
leaves a game without an action before T or has the last first action < 300 s before T; the full suite is then rerun
once and every test must pass as pre-stated above (U3/U6 adapt to the constant: U6's table check becomes 255-285 s).
Reported, not a criterion: the first reserve stop and the marathon games' total actions in those R3 runs.
