# Pre-statement: the pool clock's time-based stop, tests (2026-10-31 ~22:55 CDT; written before any test run)

Code: branch pool-clock (worktree ~/github/arc-prize-2026-poolclock) on 6091476, harness solver.py, uncommitted at the
time of writing. Two knobs, both default None: `pool_stall_seconds` (while other games wait, a game over its fair
share hands its slot back after this long without a level clear) and `pool_min_share_s` (while any game is unstarted,
if the slot-time left cannot give each unstarted game this much, every over-share game hands its slot back at its next
action boundary). The action cuts (1,500 / 750) are unchanged. Why: the action cuts are mis-scaled for time
(prestate_pool_clock amendment 2). Re-measured tonight from benchmark.json of the local 14-stream runs, as the in-slot
interval (last - first action wallclock) / (actions - 1), which excludes queue time: r6 11.8 s, gc1 9.8 s, ne1 15.8 s
per action pooled; per-game medians 12.2 / 11.5 / 17.6 s. So 750 actions is 2.0-3.3 h. These are local RTX 6000 runs,
not Kaggle; I did not find the "c10 on Kaggle" log behind the task's 13.1 s figure.

All tests run the REAL solver (HarnessSolver, _run_games, _HarnessGameSession.play/should_stop/step_env) on real TAAF
games. The stand-ins are a scripted engine (levels clear at scripted action counts) and a fake analyzer: it polls
should_stop, sleeps the "model time", sends one action. On a compressed clock the 600 s pool floor is set on the
solver instance. The tests are in tests/pool_clock/ on the branch.

## What refutes "it works"
1. Off = unchanged (test_off_unchanged.py). Five deterministic scenarios at concurrency 1, where every decision depends
   on action counts: soft cut with every game over share; the same with park; hard cut only; the same with park;
   pool clock off. Each runs under `git archive 6091476 harness/src` and under the new tree. Compared: each game's
   state, levels, actions, actions per level, score and note; stop reasons in end order; every "pool clock:" and
   "[finished]" line; resumes. ANY difference refutes. So does the two solver.py files being identical (that
   comparison could not fail).
2. Time-stall (test_time_stop.py U2): over share x stalled x waiting (nobody / an unstarted game / a parked game with
   park on / a parked game with park off), 16 cells. It must fire in exactly the 2 cells that have all three, with
   waiting meaning an unstarted game or parked+park. Firing anywhere else refutes, as does missing either cell or
   firing with nobody waiting after 10 h. A level clear must reset the stall.
3. Reserve (U3). With 14 running games (300 actions each, 7 over share, 7 with 1,200 s of share left), 7,200 s left,
   30 unstarted: the slot-time per unstarted game must equal (14 x left - remaining shares - boundary waits) / 30
   within 0.5 s. It must be breached at min share = that + 5 s and not at that - 5 s. A min share between the values
   with and without the boundary allowance must be breached. Only over-share games stop, also one that cleared a level
   this second. Nothing fires with 0 unstarted or with no end epoch. Any miss refutes.
4. Off (U1): with both knobs unset, any stop in 16 states refutes, and so does anything latched. Also refuted if the
   solver unpickled from harness/benchmark_initial.pkl (the object the notebook runs) does not resolve both knobs to
   None.
5. Latch / reason / logs (U4). Refuted if a fired stop un-fires when nobody waits any more, or if the stop reason is
   not time_stall / reserve. With park on, the game must park unfinished and the park line must carry the detail.
   With park off: a "pool clock: stop" line, the game finished, stop reason time_stall. After a resume: the stop
   cleared and both windows restarted at the resume.
6. 110 games on 14 slots (test_run_110.py; 800x compressed clock: 40.5 s run, 15 ms per action, stall 5.0 s =
   4,000 s, min share 1.5 s = 1,200 s; 30 fast / 25 slow / 25 stuck / 30 never-clearing games, seed 1031).
   - Arm A (knobs off): if fewer than 10 games never start, the scenario cannot show the difference: the test is VOID,
     not a pass. My expectation is ~40-60 never started.
   - Arms SR, SRP (both knobs, park off/on, run cancelled at the end epoch as the platform ends the scored run) and
     SRPD (both knobs, park on, the commit run's soft end): refuted by any game without an action before the end epoch,
     a watchdog hang (60 s after the kill; SRPD: 100 s after start), a game left without a final score, a crash or a
     traceback, or SRPD not ending by itself.
   - SRP, SRPD: refuted by no park or no resume, a resume before every game has had a slot, or a resumed slot whose
     windows do not start at the resume. Also by a time-stall in a resumed slot earlier than
     max(share, pool_stall_seconds).
   - Arms S (stall only) and R (reserve only): reported, no criterion. Expectation, not criterion: S still leaves games
     unstarted (the slow games clear every 2-4.5 s, never stall, and hold their slots); R starts all.
The synthetic mix says nothing about scores on the hidden set. It tests the mechanics: starts, stops, parking,
resumes, termination. Every arm is reported, not only the passing ones.
