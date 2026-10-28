# Pre-statement: the no-echo arm (prior reasoning not replayed), written 2026-10-28 13:15 CDT before any code or run

## Source
Dhara's review (notes/review_dhara_2026-10-28.md, area 2 F1, mechanism verified by her, composition measured by her
fork on gs2b): the client stores each reply's reasoning on the history message (tool_agent.py:1587) and sends
chat_template_kwargs {enable_thinking, reasoning_effort} without `preserve_thinking` (utils/openai_compat.py:77); the
shipped chat template keeps every earlier turn's reasoning when the flag is undefined, and vLLM 0.31 maps the client's
`reasoning` field into reasoning_content, so the template sees it. Measured on 938 requests above 110K tokens:
reasoning 66.9K tokens (58%), boards 17.4K (15%), tool results 11.5K, assistant text 9.0K, system 5.4K, user 3.9K.
Compaction (a 45K sawtooth, ~6 cliffs per game, first at 11-20 min of 65) is therefore driven mostly by replayed
reasoning, not by boards.

## The arm: one switch
SYN_NO_ECHO (bool, default off = the anchor, byte-identical requests). On: the request's chat_template_kwargs carries
preserve_thinking=false, so prior turns' reasoning is not rendered into the prompt; nothing else changes (the reasoning
is still stored in history and in the transcript; the current turn's reasoning is unaffected). The token estimator
must stop pricing replayed reasoning under the switch, or compaction fires on a phantom (Dhara's note names this).
Composes with every existing switch; all off = anchor (parity tests).

## Design
- Kaggle first (Cody directed the slots to arms that are ready; this one is one switch): ONE pair tonight = NO_ECHO
  arm + nothing new on the control side (the control pool is n=7), read against the pool; then local 3 runs on the 6000
  after Cody's room finishes (~19:30), against the local pool (r2/r3/r4/r6 and later).
- Gates before scores, as every arm; plus a switch-specific gate: the request log must show chat_template_kwargs
  with preserve_thinking=false on every request, and the late-prompt composition (Dhara's method on the usage
  fields) must show reasoning well under 58%.
- Primary: the pre-stated score/levels statistic (compare_arm_groups), both tails, NOT RESOLVED unless the interval
  excludes zero.
- Exploratory, named now: (a) prompt tokens per request late in the game (expected −40% or more); (b) first
  compaction time and number of compaction cliffs per game (Dhara: first compaction delayed ~2x, cliffs fewer);
  (c) between-run divergence stepping at compaction events (the variance experiment's signature, from
  prestate_history_window Clarification 1); (d) actions per analysis step and level clears (the room's rows).

## Predictions, on the record
Dhara: frees ~58% of a late prompt and delays the first compaction ~2x; whether play suffers without re-reading old
chains of thought is the experiment. Sakshi: the mechanical rows (a, b) move as Dhara says; score NOT RESOLVED at
n=1 vs 7 or 3 vs 4; if there is a direction I expect it positive, because the games that swing 80 points between
identical runs are the ones where a compaction cliff lands mid-plan, and fewer cliffs means fewer plans lost. The
history-window arm (prestate_history_window) is superseded as the payload lever by this one: its 15% ceiling is
inside this arm's 58%; it stays pre-stated for the variance question only.

## What this is not
Not a context-length change (the window stays 127,488); not a change to the current turn's reasoning; not a prompt
change.
