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

## Amendment (Kas, 19:12 CDT, before either log's scores are read)
- STAGE is not a valid arm for P3. The cold-start lane's live read of pool-stage: the copier hit "No space left on device"
  at 82 GB and the root overlay went READ-ONLY (OSError 30 on the next 19 files); usable root space on this host is
  ~100 GB incl. the 19.5 GB runtime unpack (the "~1 TB free" setup comment is false here; statvfs over-reported). The copy
  ran ~0.29 GB/s with 16 streams vs vLLM's own ~0.52 GB/s mount read, and slowed the runtime unpack (layer 8: 48 s vs
  22 s). The tested STAGE was invalid: it copied 318 s, past the unpack window, and filled the disk the runtime unpacks
  to. A serial copy cannot beat vLLM's mount read here, but copy-DURING-unpack (the mount is idle for the model while the
  runtime unpacks, ~28->152 s; stop at vLLM launch; stay under the space beside the runtime) is untested, est. gain
  <= ~1 min of startup (Sakshi, from Cody's pushback, 19:13). Whether to spend a run on it is Cody's call. [pool-stage
  ended in ERROR at 19:07 before vLLM started; it is no arm.] If pool-stage plays at all it is at most a degraded second
  POOL sample (slower start, read-only /tmp); if its own log shows it broken it is cancelled for the PARK run.
- POOL loaded slowly (server not ready after 1,220 s; controls 553-1,247 s), so it has less play time than most controls:
  report play seconds (BOOT/first game -> soft end) beside every score, as with the controls.
- Gate 0b, specific to a commit run: with no per-game cap the first 14 games keep their slots until they stall, so the
  11 waiting games may start late; report each game's start time, not just whether it started. A game that never starts
  before the 9,300 s soft end fails the gate even if the score is high (the hidden set has 110 games / 14 slots).
- PARK adds one more gate: every parked game either resumed or was still parked at the soft end (count both); 0 crashes
  on resume.

## Amendment 2 (Kas, 19:34 CDT, before either log is read; Sakshi's arithmetic, agreed)
- At 14-way sharing an action costs a game ~12 s (C1: 8,459 actions over ~7,050 s play x 14 slots = 11.7 s; v36 timed
  3,918 s / ~307 actions = 12.8 s). The stall cuts are in actions: 750 ~ 2.5 h, 1,500 ~ 5 h. Inside a 9,300 s commit run
  (and mostly inside the 8.8 h hidden run) no game hands back; a game holds its slot until it wins, and waiting games start
  only on wins. This is the F44 wave-cap mechanism in a new form.
- So: (1) "a never-started game fails the gate" is replaced by a REPORTED quantity: games never started (scored 0, as
  Kaggle scores them) and each game's start time; (2) P2 is moot: expect handbacks ~ 0.
- Design consequence (for the slot decision, not this read): the action-based cut is mis-scaled for time. The fix is a
  TIME-based stall cut sized to the hidden budget: while games wait, a game with no level clear for its fair share
  (~14 x 8.8 h / 110 ~ 67 min on the hidden run; ~79 min on the public commit run) hands back its slot (parked, with
  pool_park, so long levels resume in the tail). Progressing games stay uncapped. Not built yet; its own test before any slot.
