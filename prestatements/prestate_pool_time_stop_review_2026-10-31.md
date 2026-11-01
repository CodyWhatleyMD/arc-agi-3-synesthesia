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
