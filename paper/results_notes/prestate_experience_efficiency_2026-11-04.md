# Pre-statement: experience efficiency, measured off the clock (2026-11-04 08:05 CST)

Written before any number is computed. The investigator, 08:04: "with the untimed runs we should be able to measure that -
the real efficiency - not compute or throughput."

## Claim under test
ARC-AGI-3's score is reasoning x throughput under a fixed wall-clock whose size is set by hosting economics (9 h per
notebook, a 10-28 min model copy, a 65-min per-game cap in our anchor). Efficiency that belongs to intelligence is
efficiency in EXPERIENCE: levels per action, attempts to a clear. The benchmark already logs actions; the clock
right-censors them. Untimed runs remove the censoring and let the same model's experience efficiency be read directly.

## Metrics (per game, then summarized over games)
- E1  levels per 100 actions = 100 * levels_completed / actions_taken (0 if no action).
- E2  actions to first clear (right-censored at the run's end if no clear); reported as a survival curve over games
  (the clear-time CDF already built for the restart decision, notes/.. clear-time CDF, 10-27).
- E3  full-clear rate and levels per game, timed vs untimed (the headline we already have at n=1: 4.23 -> 6.15).
- E4  censoring rate under the clock: fraction of timed games ended by the cap (anchor: 17-21 of 25).
Data: metrics.jsonl / benchmark.json per run. Timed arms: the fixed-host controls r2, r3, r4, r6 (9,300 s, public 25).
Untimed: R0 (local 6000, 13 games finished, n=1), r0rep4 (local, running since 11-03 23:40), ut1 (the GCP server,
running since 11-03 01:30). Same model, same harness commit (synesthesia_r0 nb 630a9c6b), same games.

## Predictions, written first
P1. E1 is LOWER untimed than timed (levels per action falls when the model is allowed to keep going on hard levels),
    while E3 is higher: the untimed model clears more by spending more. If instead E1 is equal or higher untimed, the
    clock was truncating cheap clears, which is the stronger claim; I don't expect it.
P2. E2 shows a long right tail: >=10% of clears untimed take more actions than the timed cap ever allowed (R0 showed
    13% of clears beyond 300 actions). Those clears are invisible on the leaderboard by construction.
P3. E4 >= 60% under the anchor's clock. A score where most games end by the clock is a throughput measurement.

## What counts as resolved
Three untimed runs (R0, r0rep4, ut1) against four timed controls, run-level (--cluster) intervals on E1 and E3, as in
notes/run_level_ci_results_2026-11-02.md. One untimed run resolves nothing; it is reported as n=1 with its direction.
Hosts differ (ut1 on the server): reported as a sensitivity, not pooled without saying so.

## Not claimed
That levels per action measures "intelligence." Only that it is the efficiency ARC's own description names (experience,
exploration, goal acquisition) and that the clock hides it. Every untimed number is a measurement of this model on
these 25 public games, not of the hidden set.
