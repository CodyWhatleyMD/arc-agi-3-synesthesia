# Pre-statement: adversarial review of the pool clock's time-based stop (pool-clock 8d10d07), before any of my runs

Written 2026-10-31 ~23:45 CDT by the reviewer, before running any of the scenarios below. The author's own tests
(tests/pool_clock/run_all.sh at 8d10d07) were run first and all passed; that run is verification of their claims, not
one of these measurements.

Scenarios run the REAL solver (_run_games, sessions, should_stop) through the author's tests/pool_clock/_pool_common.py,
from a scratch runner outside the repo (rv_scen.py). Clock compressed 100x unless stated (the author used 800x), the
600 s pool floor scaled on the solver instance as the author does. "Real" seconds below = compressed seconds x scale.
"Marathon" = a game that clears a level every 2 actions and never wins (over its share, never time-stalled).
"Never" = never clears. Park off unless stated. A game "starts" when it executes an action before the end epoch T.

| id | setup | hypothesis | refuted if |
|---|---|---|---|
| H1 | 14 marathon + 30 never, T 3,000 s, M 300 s (< the 600 s floor), S off, polls every 10 s | the reserve budgets M but new games are protected for the 600 s floor, so some games never start | all 44 start |
| H2 | as H1 with M 600 s | all start, but the last starts far less than M before T: under 100 s | last first action >= 300 s before T |
| H3 | 14 marathon + 85 never, T 8,000 s, M 600 s, S off; polls fixed 25 s, and the measured heavy-tailed mix (3 seeds) | 7 waves: the last game starts < 60 s before T or never | last first action >= 300 s before T in every run |
| H4 | commit-run end as the notebook sets it (end epoch = soft end; games stop 60 s before it; cancel at soft end); 14 marathon + 1 never, T 3,000 s, M 600 s, 10 s polls | the never game's slot comes inside the last 60 s, so it executes 0 actions | it executes >= 1 action |
| H5 | 14 marathon + 3 never, T 3,000 s, M 600 s, 10 s polls, park off; at 100x and at 800x | the author's finding 2 (a breach finishes more over-share games than needed) is mostly an 800x artifact: at 100x exactly 3 reserve stops | >= 4 reserve stops at 100x |
| H6 | 5 games / 2 slots, park on, S 0.3 s (compressed), the analyzer factory raises for one game | `_pool_unstarted` never reaches 0 (decremented only after the analyzer is built), so no parked game ever resumes while slots sit idle | any parked game resumes |
| H7 | the planned config: S 1,500 s, M 600 s, park off; 110 games in the author's mix (seed 1031), measured heavy-tailed polls, 200x | all 110 start | any game never starts |

Every run is reported, not only those that support a hypothesis.

## Amendment 1 (~23:50 CDT, after H1, H2, H4, H5 and the first H6 runs; before H8 and the H6 reruns)

- The first H6 runs (H6p, H6n, H6p_ctl) were misconfigured: 14 slots for 5-8 games and T 1,000 s, so no game ever
  waited, parked or resumed. They test nothing about H6 and are reported as void. H6 is rerun on 2 slots, T 200 s,
  killed at 1,000 s, criterion unchanged.
- H8 (added): park on. 1 slot, 3 games in this order: A clears 3 levels in its first 6 actions then never again; B and
  C never clear. S 30 s, floor 20 s, T 600 s (100x), no kill before 600 s. Hypothesis: once every game has started,
  the parked game resumed next is always the deepest (A), including right after A itself was parked, and the resume
  gives A a fresh share and stall window, so A takes the slot back again and again while B and C, parked, never
  resume. Refuted if B or C resumes at least once before T.

## Amendment 2 (~00:05 CDT 11-01, after H1-H8 ran; before H3r)

Measured from the Kaggle 14-stream controls C1-C7 (metrics `request` events, 18,684 requests): request latency mean
32.4 s, p50 19.6, p90 72.0, p99 198, max 718 s; the expected wait from a random moment to the next request boundary
(where should_stop is polled) is E[L^2]/2E[L] = 41.4 s, against a per-game mean of 13.0 s per action (median over 175
games), which is what `pool_boundary_wait_s` budgets. H3's "mix" model (one poll per inter-action gap) has a 106 s
expected wait, heavier than this; H3's fixed-25 s model has 12.5 s, lighter.
- H3r (added): as H3 (14 marathon + 85 never, T 8,000 s, M 600 s, S off, 100x), with each analyzer call sleeping a
  latency resampled from those 18,684 requests and then sending a batch of geometric(mean 2.5) actions (32.4 / 13.0).
  3 seeds. Hypothesis: at least one game never starts in at least one seed, and the last start is < 60 s before T in
  every seed. Refuted if every game starts in every seed with the last first action >= 300 s before T.
