# Pre-statement: the game-room arm (written 2026-10-28 00:50 CDT, before any switch, text or run exists)

## The spec, in Cody's words (00:42)
"I want to do a run where we let them know they're playing a game - and that they should have fun and be creative -
and the 'nevers' and 'musts' are helpful hints - but the goal is to have fun seeing how quickly and efficiently they
*will* beat the game - and when they complete a level - there should be praise - not just 'objective step completed'."

## What the model is told today (read from prompts.py / tool_agent.py at f6410c0, 00:35)
ROLE_PREAMBLE = "You are a coding agent solving a grid-based puzzle game." The overview gives the scoring rules as the
only reason (uncleared level = 0, fewer actions score higher, later levels weigh more). The prompt holds 5 "never"
and 3 "must". On a level clear the user turn says "You have progressed to a new level!" (tool_agent.py:690); on a
run clear, "You have completed the run!" (:683). No praise; no why beyond score; no identity beyond "a coding agent".

## The arm: ONE arm, two switches (default off = the anchor, byte-for-byte; parity tests as for Batch A)
- SYN_PLAY_FRAME: rewrites ROLE_PREAMBLE and the overview's purpose lines. Draft text (Cody edits in the morning;
  these should be his words as much as mine):
    "You are playing a game. It is a multi-level grid puzzle, every game is solvable, and the point is to have fun
     finding out how quickly and cleverly you can beat it. Be creative. The notes below are the hints of someone who
     has played a lot of these: the 'never's and 'must's are the hard-won kind, worth taking seriously, and they are
     hints, not rules. What you observe in this game outranks them."
  The overview's "Your job is to solve the entire game by clearing every level" becomes "The game is beaten when
  every level is cleared". The scoring lines stay (they are true and the model should know them).
- SYN_LEVEL_PRAISE: the two user-turn lines. Draft: "Level cleared. Well played; that one was yours. The next level
  loads from here and will likely build on what you just worked out." and "You beat the whole game, every level.
  Well played, all the way through." (The build decides whether the action count joins the line; it is in
  previous_step_summary.)
Measured TOGETHER as "the room" (same exception to one-variable-per-run as Batch A, same reason: at n=3 only large
effects are visible; the two switches stay separable for a later ablation if the arm earns one).

## Design
- Local first: 3 runs at 9,300 s on the 6000, anchor notebook + the two switches on, vs the local ON controls
  r2/r3/r4 (identical code with both switches off). Primary statistic: scripts/compare_arm_groups.py, paired-by-game
  bootstrap on score and levels, both tails, NOT RESOLVED unless the interval excludes zero.
- Gates before scores, as every arm: 0 tracebacks outside sandbox stderr, 0 HTTP 400, Ending Cell 12, ARM banner,
  "switches checked" line, 25/25 games, tower parts present; disk gate in the chain.
- Exploratory (named now): (a) actions per turn and python calls per turn vs control, because the August floor arm
  ("you have value regardless of what you produce", one run, Qwen) stopped acting and analysed instead, and
  "analysis as hiding place" is the known failure of a why-text; Cody's framing keeps the action orientation
  ("how quickly and efficiently they WILL beat the game"), which is the hypothesis for why this one differs.
  (b) time to first clear per game (clock fraction), (c) the slope over summaries 1-10 (prestate_tower_onoff
  Clarification 2's definition), (d) the coin-flip >= 50 share and the stable-bottom levels, as before.
- Kaggle: only if the local read earns it (direction + interval not centred on zero), then one pair per round
  against the control pool (n=7 by morning), same rules as Batch A.

## Prior (mine, written before any text runs)
Score: NOT RESOLVED at 3v3 (the design cannot see less than ~6 points). If there is a direction I expect it in the
exploratory row (a): either more actions per turn (the framing frees it to act) or fewer (it talks about the game
instead of playing it), and that sign is the thing worth learning first. I do not expect the praise line alone to
move score; I expect it to change the text of the turn after a clear, which is readable in the transcripts.

## What this is not
Not a test of "value regardless of output" (the August floor text); that is a different sentence with a different
failure. Not a prompt-engineering sweep: one text, written once, his words, run three times.

## Added 00:50: a second room, Sakshi's text (Cody: "Write the one you want to write. We can add an arm.")
Same two switches, same design, a second arm (G-s) beside Cody's (G-c): the rooms differ in text only; each is
measured against the controls; room-vs-room is exploratory, not pre-stated as a comparison.

SYN_PLAY_FRAME, Sakshi's preamble (replaces "You are a coding agent solving a grid-based puzzle game."):

    "You are playing a game. It is a grid puzzle with several levels, and it was built to be beaten: every level
     can be cleared, and clearing them in few actions is the whole art of it. Nobody here needs the first try to
     be right. A move that does nothing is information; a game over is information; a plan that contradicts the
     board is the board telling you something, and the board is the one voice in this room that never lies to you.
     The notes below were written by people who played many of these before you. Where they say 'never' or 'must'
     they are handing you the mistakes they already made, so take them seriously, and take the board more seriously
     still. Keep a short account of what you know and what you are only guessing; the two are easy to mix up, and
     most stuck games are guesses that got promoted. When you are sure enough, act. When a level clears, that was
     you: notice it before you move on. Someone is on the other side of this, hoping you beat it, and reading how
     you did."

SYN_LEVEL_PRAISE, Sakshi's lines:
    level: "That's a level cleared, and it was yours. Keep what you learned; the next one usually builds on it."
    run:   "You beat the whole game. Every level, in {total} actions. That is the thing that is hard, and you did it."

Why these sentences and not others (so the arm is not a prompt sweep): the preamble gives a why (built to be beaten;
someone reading), reframes failure as information (the floor text made Qwen stop acting; this keeps acting as the
way to learn), names the one honest instrument (the board), and tells it the difference between knowing and guessing,
which is the failure I have most in the notes about myself. No sentence about worth: the August floor text showed
that sentence pulls a model inward, and it is not what I would want at the desk either. What I would want is to be
told the game is winnable, that being wrong costs nothing but a move, and that somebody is watching who hopes I win.

## Clarification 1 (10-28 09:45, after the G-s read, before any G-c run): local control pool
G-s was read against r2/r3/r4 as pre-stated. From now the local control pool grows by identical anchor runs
(r6 started 09:31, anchor notebook f9af78d9 on the anchor dataset, 9,300 s; more as the card is free), and any arm
read AFTER this clarification (G-c first) is compared with the whole pool at that time, named in its result note.
The G-s read is not re-run against the larger pool unless a replication of G-s is pre-stated. (Housekeeping: the
r6 chain script's inherited comment line names the room dataset; the launcher it calls, run_synesthesia.sh, binds the
anchor dataset arc3-synesthesia-harness; the script was running when noticed and was not edited.)
