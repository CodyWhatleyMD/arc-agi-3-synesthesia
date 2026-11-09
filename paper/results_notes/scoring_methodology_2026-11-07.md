# ARC-AGI-3 scoring, two sources read 2026-11-07 06:52 CST (CL1, in the investigator's browser; the Kaggle text from the API archive)

## 1. ARC Prize docs, https://docs.arcprize.org/methodology (verbatim where quoted)
"ARC-AGI-3 uses Relative Human Action Efficiency (RHAE, pronounced 'ray') to score AI systems."
Action: "Each turn where the agent submits a command, move, or input that affects the game state counts as an action.
Internal operations that do not alter the environment (tool calls, reasoning steps, retries) are not counted as actions."
Human baseline: "the upper median human (by fewest actions) per level is recorded as the baseline" (first-time players).
Per level: level_score = (human_baseline_actions / ai_actions) ^ 2; "The maximum score per level is capped at 1.15x human
baseline."
Per game: "the weighted average of all per-level scores, using the 1-indexed level number as the weight ... it is capped
based on how many levels the AI actually completed." Example: 4 of 5 levels -> max_game_score = (1+2+3+4)/(1+2+3+4+5) = 66.7%.
Total: "the average of all game scores".

## 2. Kaggle competition pages (notes/competition_pages_2026-11-07.md, data description)
"Per-level score = min(human_actions / agent_actions, 1.0), then squared ... Per-game score = Weighted average of level
scores (weighted by level index, 1-indexed). Total score = Average of all individual game scores."

## Discrepancy
The per-level cap: 1.0 (Kaggle page) vs 1.15 (ARC docs). Which the Kaggle board applies is not stated on either page;
the paper cites both and does not choose. Everything else agrees: squared ratio, level-index weights, completion ceiling.
