# Pre-statement: the agent manages its own time (2026-11-01 06:45 CST, written before any code or run)

Owner: Sakshi (Cody 06:36: "Worth a shot"). Arm name: agent clock. Base: the candidate with the pinned fix and the boot
clock (harness 848f336 = fa326e3 + ARM_PINNED_ROUND_MB; builder --pool-clock --boot-clock). Kept off main and off every
existing harness dataset.

## Why
Every pool-clock cutoff so far (1,500 / 750 actions; 1,500 s stall; 600 s reserve; equal "fair share") is a rule from
outside the game guessing when a game is stuck, and the values are arbitrary in the sense that matters: the simulation
that picked them is flat from 900 to 2,400 s and was built from public-game timings (notes/pool_timestop_sim_
2026-10-31.md). The agent is the only part of the system that reads its own progress. This arm hands it that decision.

## Design (one switch, `ARM_AGENT_CLOCK=1`; unset = the base exactly)
1. **The agent sees the shared clock every turn**, one status line in the turn message: time left in the run, games
   not yet started (each scores 0 until it starts), games paused, games playing; for this game: minutes used, levels
   cleared, minutes since its last clear.
2. **`yield_slot(reason, outlook)` in the Python sandbox** (beside `action()`): pauses this game at the end of the
   current tool call so another game can play. `outlook` is one of "close" (near a level clear), "working" (making
   progress), "stuck" (no working idea); `reason` is free text, logged. Paused games resume once every game has
   started, ordered by outlook (close, working, stuck), then deeper level first, then less time used.
3. **No stall timers and no fair share:** pool_stall_seconds, pool_stall_actions and pool_soft_stall_actions are off.
4. **One hard rule, from the constraint itself, that every game gets started** (unstarted games score 0): the existing
   reserve, with its time per unstarted game taken from THIS run, as the median time from slot start to first level
   clear among the run's games that have cleared one. Until three games have, the fallback is 600 s, the base's value,
   a stated choice, not a derived one. The reserve stops a game only while unstarted games remain.
5. Everything else is the base: model, board channel, prompts (apart from the status line and the yield_slot entry
   in the tool description), pinned rounding, start retry, boot clock, pool end margin 600 s.

## What is read, in order (commit run on the 25 public games first; a hidden run only if the gates pass)
- **Gates for a submission:** 0 tracebacks; 25/25 games played, each with > 0 actions; the status line present in
  turn messages; at least one yield_slot call and one resume happened, or the log shows why none did; the run ends by
  its soft end.
- **Behaviour, reported in full (no direction predicted):** yields per game, outlook distribution, the stated
  reasons, what resumed games did next (clears after resuming, by outlook), how many games never yielded.
- **Score:** one commit run against the control pool (n=7, mean 39.06, sd 5.07) and the candidate (38.58). Any
  difference inside the pool's spread is NOT RESOLVED. The informative test is a hidden run, where three identical
  v36 runs spanned 1.41 points (20.44-21.85); a hidden score outside 19-24 would be a real difference.
- **Failure modes named in advance:** (a) the agent never yields: then the reserve does all the scheduling and the arm
  is the candidate with no stall timer; (b) it yields too eagerly: many short slots, resume overhead (one long
  prefill each, 10-40 s, unmeasured); (c) the status line changes play in other ways: prompt text moved the hidden
  score by ~6 points before (room G-c 15.28 vs v36 ~21). Each shows in the logs; none is excluded in advance.

## Not claimed
The arm does not test whether removing the fixed clock helps (the candidate does that); it tests whether the agent's
own reading of its progress schedules better than arbitrary cutoffs. One hidden run is n=1.

## Amendment 1 (2026-11-01 07:05 CST; after the build ece6730, before any run with a model)
- A yield takes effect at once, not at the end of the tool call: the harness polls should_stop before every action, so
  no action after `yield_slot` in that call runs. The model-facing text says so ("no further action in the call runs").
- The reserve's median has no floor (as specified): if first clears come fast, late-starting games get little
  guaranteed time. Left as specified, reported.
- Added gate, from my review of the code: if the agent seldom yields, waiting games start only when the reserve forces
  them, late in the run (hidden run: 96 games waiting behind 14 slots, reserve binding at ~68 min before the end at
  600 s per game). So the commit run also reports every game's first-start time; if the last game started in the final
  15% of the run, or fewer than a quarter of games ever yielded, the arm does NOT go to a hidden slot.
- Built and tested (all CPU): sandbox 6/6, units 18/18, end-to-end 11/11, switch-off identical on 5 scenarios;
  existing pool and start-guard suites pass with the switch off (park_resume 9/9, time_stop 43/43, end_of_play 14/14,
  start_retry ALL PASS, scorecard_hold ALL PASS, off_unchanged pass); re-run by me on a clean checkout of ece6730.
