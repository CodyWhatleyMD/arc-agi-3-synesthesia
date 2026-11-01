# Pre-statement: server replicate series, candidate_pinned vs agent clock (2026-11-01, Sakshi)

Written 08:50 CST Nov 1 before any server result exists. The agent-clock server run ac1 had been playing for
about 35 minutes when this was written; its score had not been read and no yields had been seen at 10 minutes.

## Why
Monday's slot (closes Nov 2 17:59 CST) chooses between candidate_pinned and the agent clock (Kas's drafter is a third
candidate in Kas's lane, not tested here). Single commit runs can't separate them. Identical code has scored 51.37
and 32.78, and the control pool sd is 5.07 at n=7. Cody, 08:40: "just run the tests you need to."

## Platform
sakshis-server (reference_sakshis_server.md): g4-standard-48 with one RTX PRO 6000, Kaggle's GPU image, run under
papermill in commit mode. The model is on local disk, not Kaggle's network mount, so loads are faster than on
Kaggle and absolute scores are NOT comparable with Kaggle runs. Both arms run on the same box, in the same commit
mode, in alternation, so the comparison between them is fair. Spot instance: a preemption stops the VM, and a
preempted run is discarded and re-run, never pooled half-done.

## Arms (unchanged notebooks, exactly as staged and pushed to Kaggle)
- CP = notebooks_duck/kaggle_staged/synesthesia_candidate_pinned: harness 848f336 (pool clock + time stop
  1,500/600 + start guard + ARM_PINNED_ROUND_MB=1024), built with --boot-clock.
- AC = notebooks_duck/kaggle_staged/synesthesia_agent_clock: harness ece6730 (ARM_AGENT_CLOCK=1; pre-statement
  prestate_agent_clock_2026-11-01.md and its amendment 1).
Order: ac1 (already running), cp1, ac2, cp2, ac3, cp3, ... one at a time. The series stops at Monday 14:00 CST,
on Cody's word, or after six runs per arm, whichever comes first.

## Statistic (fixed now)
scripts/compare_arm_groups.py --arm <AC logs> --control <CP logs>: per-game mean score, paired by game, 95%
bootstrap CI over games. RESOLVED only if the interval excludes 0, in either direction. Levels are reported the
same way. Also reported per AC run: yields, their outlooks, and when the last game started as a fraction of run
length (amendment 1's gate). Every run is reported, including failed or discarded ones.

## What each outcome means for Monday (my recommendation; the slot is Cody's)
- AC resolved above CP, and AC's gate passes on the Kaggle commit run: recommend AC.
- CP resolved above AC: recommend CP.
- Unresolved (my prediction at n <= 6 per arm): recommend CP if AC's gate fails anywhere; if the gate passes, AC,
  because it removes the arbitrary stall numbers ("a coin flip is data") and is the paper's arm.

## Predictions
P1: unresolved at the n this weekend allows. P2: AC yields in at least 1 of 4 games per run. P3: neither arm
records a traceback or a game with zero actions.

## Amendment 1 (2026-11-01 10:55 CST): the AC arm's commit changes after ac1

ac1 ran harness ece6730 and showed the alone ping-pong (prestate_agent_clock_2026-11-01.md, amendment 2: 84
park/resume cycles on lf52 and 11 on dc22 with no actions between them, in the tail of the run). The fix is
746434e (a 'stuck' yield with no game waiting finishes the game). From ac2 on, AC = 746434e; CP is unchanged
(848f336 + boot clock). ac1 is kept and reported as its own row with this note; the paired comparison is run both
with and without ac1, and the two are reported side by side, not merged. The second Kaggle commit run of the agent
clock also uses 746434e (harness dataset arc3-syn-harness-agentclock-k2). Expectation unchanged: the comparison is
most likely unresolved at this n; the fix is expected to remove 0-action park/resume cycles (0 in ac2+), not to move
the score beyond the replicate spread.
