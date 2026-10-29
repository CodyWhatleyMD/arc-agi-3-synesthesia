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

## Clarification 1 (13:25, before any code): the replay is an explicit choice, not an omission
Dhara's correction: the server is launched with --default-chat-template-kwargs '{"preserve_thinking": true,
"reasoning_effort": "xhigh"}' (framework/kaggle.py:1381) and all three configs/inference*.json set preserve_thinking
true. So the echo of prior reasoning was chosen, upstream: it is in Tufa's Duck baseline as shipped (ca031c1,
unmodified) and in Franzen's harness (his kaggle.py:332 and his CONFIGURATION.md documents an ARC3_PRESERVE_THINKING
env knob, default 1, "False disables it; an empty value omits it"). No written reason was found in either tree; the
presumed reason, marked presumed, is the obvious one for multi-turn tool use: the model's plan lives in its reasoning,
and replaying it lets a later turn continue the plan instead of re-deriving it. That is also the mechanism by which the
arm could HURT: a model that cannot see its earlier chain of thought may re-plan from the transcript alone. The
pre-stated exploratory rows (actions per analysis step, clears, cliffs) are where either direction shows first.
Our lever: a per-request chat_template_kwargs preserve_thinking=false under SYN_NO_ECHO (per-request kwargs override
the server default; to be confirmed against the 0.31 source before the run, Dhara read it). The configs are not
edited (they are the anchor's).

## Clarification 2 (13:25): temperature on both platforms
Dhara's F6: analyzer.temperature is 0.6 in configs/inference.json and 1.0 in inference.local.json, and no run record
names which was sent. By code path (framework/kaggle.py:215-232, "the launcher's Makefile exports each from
inference.json"), the notebook renders its analyzer settings from inference.json on BOTH platforms: the local runs
execute the same notebook under papermill, so local and Kaggle both ran at 0.6 and context 127,488. inference.local.json
is the harness's own local-launcher config and is not on the notebook's path. This is a code-path check, not a
request-field check (the request log carries no sampling fields); recorded as such.

## Clarification 3 (13:20): the local run comes first, per the standing rule
"Kaggle first" in the Design section was wrong against Cody's rule (CLAUDE.md, 10-25: execute the exact notebook
locally with papermill before ANY push). Kas held it. Order now: a short local smoke of the exact no-echo notebook on
the 6000 between gc1 and gc2 (Kas; gates: every request carries chat_template_kwargs.preserve_thinking=false, and
prompt tokens per request grow visibly slower than a control's first minutes), THEN the one Kaggle run, THEN the local
x3 after Cody's room. The smoke is not a replicate and is not read for score.

## Clarification 3 (10-28 16:52, from Kas's smoke read)
The chat template (chat_template.jinja:116) renders reasoning when `preserve_thinking` is undefined/true OR the message is after the last user turn, so SYN_NO_ECHO drops only PRIOR turns' stored reasoning; the in-progress turn's stays. Smoke nesmoke1: P/E_with 0.596, P/E_without 1.328, implying ~0.23 of stored reasoning still rendered, consistent with that rule. The arm frees the prior turns' share, not "~58
## Clarification 3 (10-28 16:52, from Kas's smoke read)
The chat template (chat_template.jinja:116) renders reasoning when preserve_thinking is undefined/true OR the message
is after the last user turn, so SYN_NO_ECHO drops only PRIOR turns' stored reasoning; the in-progress turn's stays.
Smoke nesmoke1: P/E_with 0.596, P/E_without 1.328, implying ~0.23 of stored reasoning still rendered, consistent with
that rule. The arm frees the prior turns' share, not "~58%"; the gate VERDICT ECHO OFF stands with that reading.
Both readers (Sakshi, Kas) matched line for line.

## Result, Kaggle (10-28 19:25 CDT; Kas's read, timing row commit 80bb333)
no-echo-k1 (363302371) COMPLETE 00:15Z. Gates all pass (0 tracebacks, 0 HTTP 400, switches {'SYN_NO_ECHO': True},
harness c82ffc3, 25/25 played, 0 sandbox deaths, image 9a6bcfda). Switch gate on the Kaggle output: 1,853 requests,
stored-reasoning share 68.2%, P/E_with 0.409, P/E_without 1.323 -> ECHO OFF.
SCORE 16.46 (median 7.30, won 2) vs the Kaggle control pool n=7 (39.06, sd 5.07, min 32.57): -22.60 = -4.5 sd, below
the pool minimum. n=1, gates clean: the direction is not in doubt. Exploratory counts (not a read): actions 5,930
(controls ~6,650-8,500), tokens 6.33M (controls ~5.7-6.0M), tower parts 1,075 (others ~1,370-1,470): more generation,
fewer actions. Hypothesis (Dhara's own caveat, now with a number): without prior turns' reasoning, each turn re-derives
the plan instead of continuing it. The per-turn reasoning lengths in metrics.jsonl would test it. Covariate: play
7,739 s (~5% under recent controls, as for the rooms).
Decision (Sakshi): no further Kaggle runs of this arm. The local triple (ne1-ne3, running from 19:06 on the 6000, card
otherwise idle) completes for the effect size with an interval on the local platform. Paper: the echoed reasoning is
working memory, not overhead; one sentence with -22.6 (n=1, Kaggle) and the local interval when it lands.

## Mechanism read, Kaggle metrics (10-28 19:27 CDT; Kas, no-echo vs controls C5/C6/C7)
- reasoning tokens per turn: median 4,326 / p90 12,604 vs controls 2,112-2,281 / 9,884-10,337 (~2x at the median)
- per request: median 1,846 vs 1,030-1,153; requests per turn 1.86 vs 1.85-1.89 (unchanged)
- turns in the clock: 1,058 vs 1,405-1,463 (-27%); prompt per request median 61.6K vs ~80K (smaller, as the switch should)
- generated tokens per EXECUTED action: 1,067 vs C6 751 (+42%)
Same requests per turn, twice the thinking per turn, fewer turns in the clock: "each turn re-derives the plan" has a
direct measure. Correction (Kas's own): action() CALLS != executed actions; executed = benchmark total 5,930
(turn.executed_action_count 5,892 agrees). The refused-call divergence (13,304 calls, 8,738 refused as
previous_game_over, 8,725 of them one streak in sk48: a snippet loop that never checked game over; SYN_TERMINAL_RAISE's
case, off here as in the anchor) is NOT what moved the score: 22 of 25 games below the C3-C7 averages by >1 (ar25 -92,
vc33 -71, tr87 -57, tu93 -53); without sk48, 17.14 vs 41.31. The drop is broad.
