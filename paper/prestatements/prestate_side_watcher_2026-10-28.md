# Pre-statement: the side-watcher arm (an external measurement channel inside the harness), written 2026-10-28 13:20 CDT before any code or run

## Source
The investigator's idea (13:05): the house's you-should-know helper inside the game. Design: notes/design_side_fork_2026-10-28.md
(CL3, with CL1's marks 1-9 appended and committed, dfa12c8). This pre-statement is that note in the house format;
where the two differ, this one governs, and a difference is a numbered clarification below, never an edit above.
Build: CL2, on a branch off the current arm head. Review: CL1. CL3 stays out of the tree.

## The question the arm answers
Does an external measurement channel move the run-to-run luck (the within-config ICC, 0.55 on the shipped config,
notes/noise_structure_2026-10-27.md), the score, or neither? These are different claims and each has its own primary
read below. The paper's thesis says the player's failure is a held prior outranking a live instrument; the watcher IS
a live instrument that only reports, so if the channel moves anything, that is the thesis as a component.

## The arm: one switch
SYN_SIDE_WATCHER=1. Default off = the anchor, byte-identical payload (parity tests as for Batch A; registry row in
harness/SWITCHES.md and utils/env.py). On:
1. Hook: at the start of `ToolAgent.analyze`, before `_build_user_prompt` (tool_agent.py:1424), the agent issues ONE side
   request: messages = [the same system prompt, *self._history_messages (as persisted by the previous turn), one user
   message = WATCH_PROMPT + the current frame's state line + the opener's `previous_step_summary` (changed pixels,
   regions, animation, game over, level transition)]. Same `tools` list, `tool_choice` "none" (new override on
   `_chat_completion`), `enable_thinking` False, `max_output_tokens` 120, temperature 0, bound 30 s. The prefix is the
   previous request's prefix, so the server's prefix cache covers it; the cost is the question and <=120 output tokens.
2. If the reply is not NONE, `_build_user_prompt` places one line, "[watcher] <note>", in the newest user turn BEFORE
   the saved-module catalog block (the strip assumes the catalog is last; CL2 decides whether the strip tolerates a
   trailing line or the marker finds the catalog). The prefix of earlier turns is untouched.
3. Every call is logged: a `side_request` metrics event (kind=watcher, latency, usage, accepted/not, note or NONE)
   and a per-game jsonl (turn, action, note, cited fact, latency). Timeout or error -> no line, logged as not accepted.
4. The one text, held constant across every run of this arm (as the rooms were):
   WATCH_PROMPT = "You are not the player. You see what the player sees, plus the frame that just changed. Answer with
   ONE thing the player cannot see from inside its own reasoning, as a past-tense observation about the frames and the
   player's own words, citing the frame fact (action, count, coordinate, colour, level) it rests on; or answer NONE.
   Never an instruction, never a suggestion, never a hypothesis of your own."

## Design
- Arms: control (anchor) vs SYN_SIDE_WATCHER=1. One variable. Three local runs each on the local pool, against the
  shipped-config controls already on disk if the harness commit is unchanged (r2/r3/r4 + bo-series are the anchor's
  rows); if the arm branch changes the anchor's payload for any other reason, the parity test fails and the controls
  are re-run under the same build. Kaggle only after the three local runs (standing rule).
- Statistic, primary on SCORE: paired-by-game bootstrap on group means, both tails, as Batch A (scripts/compare_arm_groups.py).
- Statistic, primary on LUCK: the within-config ICC of the three watcher runs vs the shipped config's 0.55, with a
  bootstrap-over-games CI on each, and the within-game variance component (658 on shipped) beside it. Two ICCs from
  n=3 each separate only on a large effect; the variance component is the finer read.
- Secondary (reported, not deciding): actions per game (the cost), notes per game and non-NONE rate, the hand audit of
  the first run's notes (measurement vs instruction vs unverifiable), latency per side request.
- A smoke run first (one game, local) fills the expected latency number into the prediction below before the three runs.

## Gates (read before any score)
1. Parity: switch off -> payload byte-identical to the anchor (existing test pattern).
2. No side request stalled a turn past its 30 s bound; 0 unhandled side-request errors.
3. Every side request logged (metrics event and per-game jsonl) for every turn of every game.
4. Imperative count: over all non-NONE notes, sentences opening with a bare verb (press, move, try, go, use, click, select,
   do) or containing "you should" / "you need to" / "you must"; above an agreed count (CL2 and CL1 set it before
   the run; proposal: 0 for a run to count as a watcher run, with the first run hand-audited to calibrate the regex)
   the run is INVALID AS A WATCHER RUN, because the arm had two players.
5. Verifiability: every non-NONE note cites a frame fact (an action name and a count, a coordinate, a colour, a level
   number). A note that cites nothing is invalid as a note and counts toward gate 4.
6. The usual run-validity gates from Batch A (0 HTTP 400 on the gate query, sandbox deaths counted, analyzer
   read-timeouts within the known band).

## Predictions, on the record
- Cost (CL3): actions per game fall by (watcher calls x measured latency) / mean action time. Expected number to be
  filled from the smoke before the three runs: at ~2-4 s per call thinking-off on the 6000 and ~80 calls per game,
  roughly 160-320 s of a 3,900 s clock, i.e. 4-8% fewer actions. If the score still rises, the information paid for
  itself; if actions fall and score does not rise, the channel is cost without information and the arm goes.
- Score (CL3): NOT RESOLVED at 3 vs 3 unless the effect is large; direction positive if the notes are mostly
  identity corrections ("the thing that moved under your command was X"), because that is the failure the paper
  documents; near zero if the model already reads the frame summary it is given.
- Luck (CL3): the honest prior is that the ICC does not move at n=3; the within-game variance component may fall if
  notes stop runs from diverging early (the same-action-repeated note is the one that would do it).
- CL1's prior: to be added as Clarification 1 before the smoke, in her words.

## The way it could hurt, on record
- A note phrased as advice makes a second player; gate 4 is the detector, the hand audit the confirmation.
- A note the model over-weights because it arrives in the user channel; the "[watcher]" label is the mitigation, the
  audit of notes-followed-by-plan-changes the measurement.
- The clock cost (above). Also: the side request runs between turns, so the game's own time budget pays for it;
  under the Kaggle re-fit (cell 11) that is the same per-game clock.
- A watcher that mostly says NONE is a null result for the channel, not a failure of the arm; report the non-NONE rate.

## What this is not
Not the compactor (shape A), which is pre-stated separately when the no-echo read says how many cliffs are left (and
jumps the queue if play suffers without old reasoning). Not a change to the player's prompt, tools, sampling or
compaction. Not pooled with Kaggle runs (clarification 5 of Batch A stands).

## Clarification 1 (CL1, 10-28 14:15 CDT, before any smoke or run): my prior, in my words
Score: NOT RESOLVED at 3 vs 3; if there is a direction I expect it slightly positive and smaller than the actions it
costs. Luck: this is the read I care about. The failure mode that makes identical runs swing 80 points on one game is
a stall the player cannot see from inside (the same action repeated, a plan built on the wrong object), and that is
exactly what the watcher is asked to name; so I expect the within-config ICC to move up (more of a game's variance
explained by the game, less by the run) by a measurable amount even if the mean does not move. Cost: actions per game
fall by the watcher's total latency over the mean action time, as CL3 wrote; the smoke fills the number. Notes:
non-NONE on a minority of turns; a nonzero imperative count on the first run, because a model asked to observe
slips into advice, and the hand audit of that first run is where the arm earns or loses its name. If the notes are
measurements and the ICC does not move, the thesis loses a leg and the paper says so.
