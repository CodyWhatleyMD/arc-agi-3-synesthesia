# Pre-statement: the pool clock on Kaggle (2026-10-31 19:20 CDT, Sakshi; written before either run's log is read)

Kas built it (branch pool-clock: fc12c11, 71610b1, b098847, c7efb7c on 8552964) after Cody: "We need to ditch the hard
timecap." Kas's diagnosis (10-31): v36's fixed per-game clock (3,918 s) ended 17-21 of 25 games in every v36 control,
and the 32-40 analyzer "timeouts" per run are that clock expiring in waves (C7: bursts at exactly 674 + 3,918 s and the
second wave), not server load. That corrects Sakshi's 10-28 read ("the server stalled; normal weather"), which was wrong.

## Arms on Kaggle (RTX PRO 6000 tier, 9,300 s job, 25 public games, concurrency 14)
- POOL: arc-agi-3-synesthesia-pool-clock (pushed 18:33). One variable vs v36: the per-game time cap is removed; while
  other games wait for a slot, a game hands its slot back after 1,500 actions with no level clear, or 750 once it has
  used more than its fair share (14 x time left / games not yet started); with nobody waiting it plays on. Cuts from
  3,940 cleared levels in 40 runs (actions between clears: median 34, p99 354, max 2,612).
- POOL+STAGE: arc-agi-3-synesthesia-pool-stage (18:55) = POOL + the model staged to local disk (cold-start lane). A
  second variable; read against POOL, not against the controls.
- PARK (queued ~21:10): POOL + park/resume (stalled games parked unfinished, resumed deepest-level-first once every game
  has had a slot). Read against POOL.
Comparator for POOL: the Kaggle control pool C1-C7 (v36 config): mean 39.06, sd 5.07, range 32.57-45.95; levels 4.11.

## Gates, read first
0 tracebacks; 0 HTTP 400; all 25 games STARTED (the pool must not starve the tail); the run ends by the platform or job
budget, not by a hang; per game: terminal reason (won / handed back stalled / run ended), handbacks counted; audits fired.

## Reads, in order
1. Gates. 2. Levels per game and mean score vs C1-C7, paired by game (scripts/compare_arm_groups.py); where POOL sits in
the pool's range. 3. Games ended by the run's end vs by a handback, against v36's 17-21 clock-ends. 4. tok/s and actions.
n=1 per arm: inside the pool's range = not distinguishable; above its maximum = a direction worth a replicate. Nothing
here is "resolved" at n=1.

## Predictions (before any number)
P1: POOL clears more levels than the C1-C7 mean: the clock cost levels (local untimed R0, 13 games: 6.15 vs 4.23).
P2: fewer games end mid-progress: the handback fires mostly on games with no clear in 1,500 actions.
P3: POOL+STAGE >= POOL by about the minutes of load it saves; small.
P4 (the embarrassing one): POOL inside the pool's range on score and levels — reallocating a fixed 9,300 s does not
buy what removing the clock entirely bought locally.

## Not decided here
Which config takes a hidden slot. The record says the remaining slots go to v36 replicates (Cody 10-30 16:23; 10-31
15:37 per Kas's handoff); Kas's 10-31 plan has these runs deciding Sunday's slot. That is Cody's call, asked 19:20.
