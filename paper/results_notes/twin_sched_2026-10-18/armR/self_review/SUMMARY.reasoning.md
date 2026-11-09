We need answer user's request. Need produce final under 2500 words. User provided many game reviews. They ask: "Across all games, rank the top 10 improvements to the harness, its tools, its instructions, and your strategy by expected total score gain. For each: what to change, which games' evidence supports it, how to implement it, how to measure it, and any risk. Then list anything that looked like a harness or infrastructure fault rather than a playing mistake. Keep it under 2,500 words."

We need synthesize across all games. Need rank top 10 improvements by expected total score gain. Include harness/tools/instructions/strategy. Need for each: what change, evidence games, implementation, measurement, risk. Then list harness/infra faults.

Need likely include overall score impact: many low scores due stalls, game overs, not clearing levels. Need rank by expected total score gain. We need infer from reviews.

Need be concise but detailed. Under 2500 words. Could use table or list. Need include top 10 improvements. Also infrastructure faults. Need maybe mention exact numeric action budget, state extraction, affordance probing, simulator/search discipline, anti-runaway, animation/semantic events, selection/object tracking, hypothesis ledger/budget guard, save modules, geometry-first, etc.

Need analyze across games to identify highest expected total score gain. Let's list issues and games.

Games:
- lp85: won 100, but overprobing, action efficiency. Issues: action-effect oracle, HUD exclusion, history indexing, budget clarification, geometry first.
- ar25: won 100, action efficiency. Issues: selection API, budget numeric, instructions selection/mirror, verify selection before batch, save modules, threshold yellow, MOUSE semantics, stop no-op.
- ft09: won 100. Issues: icon/button-aware summary, action-effect diff, budget numeric, instructions icon encoding, forbid large batches before mechanics, save solvers, CSP before execute, probe nonuniform early.
- m0r0: 95.26. Issues: action effect summary, lattice classifier, budget numeric, blocking probe instruction, validate clicks, test per-square blocking, compact state.
- tr87: 80.36. Issues: budget numeric, safe action executor cap, cursor object, glyph metadata, guarded navigation, calibrate budget, verify cursor before no-change, constraint solving.
- sb26: 72.04. Issues: structured submission feedback, click resulting slot map, budget numeric, click-swap semantics, hint ring mechanic, saved click simulator, multiset arithmetic first, verified swaps.
- r11l: 71.43 gave up. Issues: color-state API, high-level action executor, color-aware solver, instructions stateful color, assignment before moving, ghost probe first.
- tu93: 62.22 gave up. Issues: hazard state marker color, instructions marker phase, after death probe, mode-aware simulator, budget numeric, save hazard parser.
- vc33: 53.13 gave up. Issues: budget numeric, derived game-state helpers, sandbox robustness, wall band hint, simulator before long manual, conservation warning, click newly colored band, defensive Python.
- ka59: 50.67 gave up. Issues: budget numeric, event log, occlusion tracking, piston phase, warn against burning actions, state-space model, save mechanics module, partial objective -> complete goal.
- sc25: 50.14 won. Issues: budget numeric, gameplay diff exclude budget, saved modules, large-object inspection, instructions budget reset, save world model, animations diagnostic, state machine earlier, test code once, game overs fatal, verify filters.
- re86: 41.67 gave up. Issues: object model for shapes, move results, segmentation diagonal, budget strip, deformable shapes, selection persists, capture semantics, saved shape solver, measure cleanly.
- cn04: 28.57 gave up. Issues: numeric budget/win-state, piece abstraction, non-truncated summaries, timing guard, explicit mechanics, budget bar, inactive pieces, anti-stall, solve level 4, verify rotation, save solver.
- dc22: 21.41 gave up. Issues: exact budget/denial, persistent macro runner, board-state summaries, saved state model before manual, budget/game-over policy, teleport/parity examples, button-state BFS, parity reset, game overs deliberate, save helpers.
- cd82: 14.29 gave up. Issues: budget numeric, changed cells, object tracking roles, button centers, budget accounting, hash tracking, button centers segmentation, saved solver, remeasure clean board.
- wa30: 13.99 gave up. Issues: goal/valid-slot/held state, dry-run simulate, NPC state, budget numeric, verify goal rep, model NPC, discourage idling, simulator, sockets, batch after dry-run.
- su15: 11.87 gave up. Issues: one-step simulator discriminating probe, save-scum UNDO, animation compact/object tracks, move_rejected flag, budget numeric, instructions hazard/UNDO/rejected, housekeeping.
- s5i5: 8.33 gave up. Issues: persistent scratchpad/world model, action-effect diff, exact budget, reduce context pollution, require saved state module, coordinate derivation, anti-stall, crosshair centers, simulator/search, save helpers, batch verified.
- sk48: 6.85 gave up. Issues: exact budget, canonical derived-state API, validate simulator helper, UNDO/MOUSE semantics, budget accounting before batches, win condition from history, mechanics per level, forbid long unverified batches, simulator/search, probes, budget hard constraint.
- ls20: 5.27 gave up. Issues: numeric budget/HUD diff, fail safe after game over, save_module transactional, object classes, budget bar mapping, per-action validator, save_module warning, state-space planner, generic solver, minimal goal, blocked animation, batch length budget, verified steps, clean save.
- sp80: 4.76 gave up. Issues: game-over reason/events, semantic pour events, stable roles, compact animation queries, budget nonuniform/game over reason, color role changes, state-machine modeling, hypothesis table, test win condition, one-action probes, stable identity, simulator regression, high-level search.
- lf52: 1.82 gave up. Only reasoning? Not much. Maybe incomplete.
- bp35: 0.047 gave up. Issues: affordance-probe helper, passability graph, reduce board output, affordance sweep, save world model, repeated probes, click every distinct object, graph model, flood path check, batch safe actions.
- tn36: 0.0 gave up. Issues: numeric budget, interactive regions query, animation/path info, scaffold saved modules, multiple independent bits, hypothesis ledger, budget guard, probe rows, abandon impossible goal, search full state, stop after game over.
- g50t: 0.0 gave up. Issues: action-effect/state-diff recorder, saved modules easier, budget semantics, early world-model save, hypothesis ledger, game overs first-class, state graph, stop repeating, game-over animation, alternative goals.

Need rank top 10 by expected total score gain across all games. Since many low scores due not clearing levels, improvements that prevent catastrophic stalls/game overs likely highest. Also harness improvements that directly expose budget and state likely high. Need include strategy improvements too.

Potential top 10:
1. Numeric per-level action budget + safe executor with hard cap / auto abort. Evidence: tr87 256 RIGHT loop, ka59 1036, wa30 748, sk48 197, ls20 41-move no-op, cd82, tn36, vc33, dc22. Expected: avoid game overs and runaway loops; huge. Implementation: current_frame.actions_remaining, max_actions, repeated no-progress abort, game_over stop. Measure: reduction in max level actions, game overs, timeouts. Risk: overrestrict exploration; need configurable cap.
2. Semantic action-effect / state-diff recorder (what moved, blocked, denied, selection changed, event log). Evidence: m0r0, re86, s5i5, sk48, g50t, dc22, sp80, tu93, vc33, ar25. Expected: faster mechanics discovery, fewer probes. Implementation: per action result: changed_cells, moved_objects, blocked_by, denied, events. Measure: probes to first mechanic, actions per level. Risk: output verbosity; need compact.
3. Early mandatory saved world model / state-space simulator and search before long batches. Evidence: many gave_up: s5i5, sk48, g50t, tn36, cn04, wa30, dc22, vc33, ka59, tr87. Expected: clear more levels, reduce manual waste. Implementation: instruction + tool scaffolding: after first mechanic save state(frame), apply, goal; validate on transitions; batch only from simulator. Measure: levels cleared, action ratio vs baseline, simulator validation pass. Risk: over-modeling static levels; time.
4. Affordance/object-role discovery helper and immediate affordance sweep. Evidence: bp35 green doors 145 actions, ft09 icons/buttons, tu93 hazard marker, sp80 bars, r11l color state, wa30 held/sockets, cd82 ball/mold, re86 shapes. Expected: huge for low-scoring games. Implementation: tool returns candidate interactive objects by color/hash, role guesses, click-probe helper; instruction click one per color before movement. Measure: actions to first mechanic, false positives. Risk: noisy in complex boards.
5. Derived game-state APIs for object tracking/selection/roles. Evidence: ar25 selection, r11l hub colors, re86 shape state, sk48 targets/attached, ls20 roles, sp80 bars, wa30 held, cd82 ball, tn36 registers. Expected: high. Implementation: segmentation roles: selected, agent, target, button, hazard state, held, attached. Measure: misread state incidents, wasted actions. Risk: game-specific hardcoding; need generic.
6. Hypothesis ledger + anti-stall/budget guard: after contradiction/game over, change hypothesis; no repeated no-op; stop if budget insufficient. Evidence: tn36 repeated 61-action sweeps, g50t repeated head, sk48 long unvalidated, dc22 parity, bp35 repeated flood, tu93 repeated death, tr87. Expected: prevent loops and give-up. Implementation: instruction + tool: track hypotheses, no-progress counter, game-over reset policy. Measure: repeated identical experiment count, post-game-over action class change. Risk: premature abandonment.
7. Explicit instructions for level-specific mechanics: budget bar semantics, selection persists, marker color phase, click-swap, wall bands, deformable shapes, stateful colors. Evidence: lp85, ar25, ft09, tu93, sb26, re86, r11l, vc33, sp80, tn36. Expected: medium-high; prevents wrong assumptions. Implementation: generic warnings not level-specific. Measure: fewer wrong hypothesis stalls. Risk: prompt overload.
8. Robust saved modules / persistent scratchpad. Evidence: many "Saved modules none", save_module misuse, rollback, repeated code. Implementation: transactional save, first-class tool, auto checkpoint, persistent state dict. Measure: repeated helper code, context loss. Risk: stale modules.
9. Compact animation/event summaries and game-over reason. Evidence: tr87, su15, sp80, g50t, sk48, tn36. Expected: high for animation-dependent puzzles. Implementation: animation_tracks, path extraction, cup_filled, game_over_reason. Measure: animation dump tokens, time to infer rule. Risk: loss of detail.
10. Geometry-first / constraint solving before probing; CSP/BFS over known states. Evidence: lp85, ft09, sb26, r11l, tr87, tn36, wa30. Expected: reduce overprobing. Implementation: instruction: infer geometry, one verification press; solve assignment before moving. Measure: learning actions vs execution actions. Risk: wrong geometry.

Need maybe rank by expected total score gain. Could include exact numeric budget and safe executor as #1. Semantic action diff #2. Mandatory early simulator #3. Affordance sweep #4. Derived state/selection roles #5. Hypothesis ledger/anti-stall #6. Budget/game-over policy and instructions #7? Need top 10.

Need maybe include "hard action cap / safe executor" separate from numeric budget? Could combine. But top 10 improvements to harness, tools, instructions, strategy. Could combine harness+instructions in each item. Need for each: what change, evidence games, implement, measure, risk.

Need also list harness/infra faults: sandbox process exited (vc33 level7), action loop timeout after game over (ls20), save_module rollback? Maybe tool output truncation? Some are harness limitations but not faults? User asks "anything that looked like a harness or infrastructure fault rather than a playing mistake." Need list: sandbox crash, action loop timeout, save_module non-transactional? Maybe tool output truncation is design limitation, not fault. Need distinguish. Evidence:
- vc33: "Sandbox process exited unexpectedly" during level 7; likely infra fault.
- ls20: action_calls 6935 timeout due loop after game over? Could be harness should stop, but playing mistake too. Infrastructure? Maybe action executor did not hard-stop after game_over, causing runaway; could be harness fault if action() kept accepting? But review says harness refuses after game_over but my loops did not stop. Timeout from 6935 action calls maybe harness allowed too many? It says action() refuses further actions after game_over, but loops did not always stop. If it returned stop signal but loop didn't check, playing mistake. But "timeout with action_calls 6935" could be harness issue if action call after game_over should terminate snippet? Hmm.
- tr87: unguarded loop caused 256 RIGHT; harness allowed unbounded action batch? Could be harness should cap, but playing mistake. Not fault.
- save_module: "save_module is a function inside python tool; call from Python code" is instruction misuse, not fault. "failed save made no workspace changes" due exception rollback maybe design.
- Tool output truncation: design limitation.
- "exec unavailable", "import time not allowed" maybe sandbox restrictions, not fault.
- "animation frames disappeared" maybe expected.
- "large masks unavailable >400 cells" maybe tool limitation.
- "game_over reason missing" design.
- "Sandbox process exited unexpectedly" is fault.
- "action_calls 6935 timeout" maybe harness should protect against runaway; maybe infrastructure fault? Could list as suspected harness/infra fault if action loop after game_over not hard-stopped.
- "save_module rolled back if later exception" maybe harness design fault? Could list as questionable.
- "Tool output cut off to 1024-token" maybe harness limitation, not fault.
- "Tool output was truncated" many. Could list as infrastructure friction.
- "Sandbox unavailable exec, import restrictions" not fault.
- "No direct game-over reason" design.
- "animation type other/path misleading" maybe game design.
Need include "looked like harness or infrastructure fault rather than playing mistake": sandbox crash, runaway action timeout, possibly save_module rollback, tool truncation, missing budget field? Missing budget field is design, not fault. Maybe "action() did not hard-stop after game_over"? Need phrase cautiously.

Need ensure under 2500 words. Need maybe use compact table. 10 items with 5 fields each could be long. Need concise. Could use numbered list with sub-bullets. Need maybe total word count around 1800-2200. Need include games evidence by IDs. Need expected total score gain maybe qualitative (huge, high). Could rank.

Need think about expected total score gain: Since scores range 0-100, top improvements that convert gave_up low scores to clears. Numeric budget + safe executor prevents catastrophic level blowups (tr87, ka59, wa30, sk48, ls20, tn36). But if harness gives budget, still need strategy. Mandatory simulator maybe highest for many low scores. Affordance sweep for bp35. Semantic action diff broadly. Need rank:
1. Hard action-budget guard + safe executor (numeric remaining, max batch, auto-abort no-progress/game_over). Evidence: tr87, ka59, wa30, sk48, ls20, tn36, cd82, dc22. Expected: largest because prevents 200-1000 action disasters and timeouts.
2. Semantic world/action diff (compact state transition: moved/blocked/denied/events). Evidence: m0r0, re86, s5i5, sk48, g50t, dc22, sp80, tu93, vc33. Expected: high across all.
3. Mandatory early saved simulator + validate against transitions before batching. Evidence: s5i5, sk48, g50t, tn36, cn04, wa30, dc22, vc33, ka59, tr87. Expected high.
4. Affordance/object-role discovery helper + click-one-per-color instruction. Evidence: bp35, ft09, tu93, sp80, r11l, wa30, cd82, re86. Expected high for early stalls.
5. Derived game-state/selection/roles API. Evidence: ar25, r11l, re86, sk48, ls20, sp80, tn36, wa30. High.
6. Hypothesis ledger + anti-stall/game-over reset policy. Evidence: tn36, g50t, sk48, dc22, bp35, tu93, tr87. High.
7. Compact animation/event summaries + game-over reason. Evidence: tr87, su15, sp80, g50t, sk48, tn36. Medium-high.
8. Generic instruction pack: budget bars, selection persists, marker color phase, click-swap, wall bands, deformable shapes, stateful colors. Evidence: lp85, ar25, ft09, tu93, sb26, re86, r11l, vc33, sp80, tn36. Medium-high.
9. Persistent save/module infrastructure (transactional, first-class, auto checkpoint). Evidence: many saved none, save_module misuse/rollback, repeated code. Medium.
10. Geometry-first/CSP before probing and assignment planning. Evidence: lp85, ft09, sb26, r11l, tr87, tn36, wa30. Medium.

Could include "numeric budget" in #1, but also instructions #8. Good.

Need for each: what to change, evidence, implement, measure, risk. Need maybe include "expected total score gain" maybe in title. Need not exact numeric. Could say "Expected: very high". Need rank by expected total score gain. Need maybe mention final score already 100 in some games but efficiency; across run includes low scores, so expected total across all games. Good.

Need ensure not too long. Let's draft with headings.

Potential structure:
"Assumption: score is level-weighted and action efficiency matters; many losses came from uncleared levels/game overs. Ranked by expected total score gain across all 22 games."
Then table maybe:
| Rank | Improvement | Evidence | Implement | Measure | Risk |
But table with long text may be hard. Use numbered list with bullets. Need under 2500 words. Could be ~2000.

Let's draft each item ~150-180 words => 1500-1800 plus infra list ~200. Good.

Need mention "harness, its tools, its instructions, and your strategy" maybe each item category. Could label [Harness/tools], [Instructions], [Strategy]. For each maybe combined.

Need include "which games' evidence supports it" with IDs. Need not list all games, but enough. Use abbreviations. Need ensure top 10 includes harness/tools/instructions/strategy. Some items are strategy. Good.

Need think if any other high-value improvement: "action-effect probe or automatic permutation recorder" from lp85. That's semantic action diff. Good.
"Expose selection API" included in derived state.
"Numeric budget" included.
"Safe action executor cap" included.
"Affordance sweep" huge for bp35 and others.
"State-space simulator" huge.
"Hypothesis ledger" huge.
"Animation summaries" high.
"Save modules" medium.
"Geometry-first" medium.

Need maybe include "per-level budget + game-over reason" separate? Could combine with #1 and #7. #1 includes budget and safe executor. #7 includes game-over reason.

Need list infra faults:
- vc33: sandbox process exited unexpectedly during level 7 BFS; likely infra fault.
- ls20: action loop timeout with 6935 action calls after game_over; suspected harness should hard-stop action() or snippet, but also player loop bug.
- save_module rollback behavior? "failed save made no workspace changes" in wa30 and ls20? Could be harness design, but if save succeeded then later exception rolled back, it is infrastructure friction. Maybe list as "questionable".
- Tool output truncation to ~1024 tokens caused repeated re-derivation; design limitation, not fault.
- Missing action budget field is design omission, not fault.
- "MOUSE did nothing" could be game rule, not fault.
- "animation frames disappeared" design.
Need maybe include "segmentation merging inactive pieces" game design.

Need be careful: user asks "Then list anything that looked like a harness or infrastructure fault rather than a playing mistake." So list only faults. Could include "sandbox crash", "runaway action timeout", "save_module non-transactional rollback", "tool output truncation" as infra friction? The latter is harness design, but not fault? They said rather than playing mistake; could include "infrastructure friction". Need maybe separate "Confirmed/suspected faults" and "design limitations". But asked list anything looked like harness/infra fault. Could list with caveats.

Need final under 2500 words. Let's estimate. Top 10 each 140 words = 1400, intro 50, infra 250 => 1700. Good.

Need maybe include expected total score gain qualitative. Could say "Expected total score gain: very high". Need rank by expected total score gain. Use "Gain:" field.

Let's craft final.

Potential final:

"Ranking by expected total score gain across all games (not just final displayed score)." Then list.

Need mention "games' evidence supports it" with IDs. Use game IDs: lp85, ar25, ft09, m0r0, tr87, sb26, r11l, tu93, vc33, ka59, sc25, re86, cn04, dc22, cd82, wa30, su15, s5i5, sk48, ls20, sp80, bp35, tn36, g50t. Need maybe not all.

Need ensure top 10 covers all. Let's write concise.

Item 1: Hard budget guard and safe executor.
- What: expose actions_remaining, max_actions, auto-abort on repeated no-progress, game_over, level_complete; instruction reserve margin.
- Evidence: tr87 256 RIGHT, ka59 burn 1036, wa30 748 idles, sk48 197, ls20 41-move impossible, tn36 3x61 overs, cd82, dc22.
- Implement: harness field, action() cap, no-progress counter; planner computes plan_len <= remaining-margin.
- Measure: max level actions, game overs, timeout count, action ratio.
- Risk: too conservative; need adaptive margin.

Item 2: Semantic action-effect recorder.
- What: compact diff: changed_cells, moved_objects, blocked_by, denied, events, selection changed, budget separated.
- Evidence: m0r0 per-square blocking, re86 deformation, s5i5 push/pull, sk48 simulator bugs, g50t red snake, dc22 denial, sp80 pour events, tu93 hazard marker, vc33 saturated band.
- Implement: post-action parser using segmentation/animation; output <= few lines.
- Measure: probes to first rule, wrong-model duration.
- Risk: output noise; need filtering.

Item 3: Mandatory early saved simulator and validate before batching.
- What: after first mechanic, save state(frame), apply, goal, validate against history; batch only simulator-verified.
- Evidence: s5i5 none, sk48 110-action bad plan, g50t none, tn36 no model, cn04 rotation bug, wa30 P3 failure, dc22 late plan, vc33 manual, ka59 late module.
- Implement: instruction checkpoint; tool scaffold/template; validator function.
- Measure: simulator validation pass rate, levels cleared, long-batch failures.
- Risk: overfitting, wasted modeling on simple levels.

Item 4: Affordance/object-role discovery helper + click-one-per-color sweep.
- What: tool returns interactive candidates; instruction click one per color/hash before movement model.
- Evidence: bp35 green doors after 100 actions, ft09 icons/buttons, tu93 hazard marker, sp80 bar activation, r11l color pickups, wa30 sockets/held, cd82 ball/mold, re86 shapes.
- Implement: segmentation heuristic: nonuniform, repeated, clickable-looking; affordance_probe() clicks representatives and returns diff.
- Measure: actions to first mechanic, false-positive rate.
- Risk: noisy, accidental deaths; use safe positions.

Item 5: Derived state/selection/roles API.
- What: expose selected, agent, held, attached, target, button, hazard phase, cursor, registers.
- Evidence: ar25 selection, r11l hub colors, re86 shape state, sk48 targets, ls20 roles, sp80 bars, tn36 dual registers, wa30 held/sockets.
- Implement: generic roles + per-game adapters? Maybe harness provides node['role'], state dict.
- Measure: state misreads, wasted selection probes.
- Risk: game-specific, hard to generalize.

Item 6: Hypothesis ledger + anti-stall/game-over policy.
- What: maintain hypotheses, status, next test; after game-over/no-progress switch family; never repeat same action class.
- Evidence: tn36 repeated sweeps, g50t repeated head, sk48 unvalidated, dc22 parity, bp35 flood, tu93 repeated deaths, tr87.
- Implement: instruction + tool: experiment ledger, no-progress counter; post-game-over forced analysis.
- Measure: repeated experiment count, post-game-over action diversity.
- Risk: premature abandonment.

Item 7: Compact animation/event summaries + game-over reason.
- What: animation_tracks, path, cup_filled, drain_reached, bar_activated, game_over_reason.
- Evidence: tr87 path, su15 rejected move, sp80 pour, g50t game over, sk48 path, tn36 path, ka59 launch.
- Implement: animation parser, event log persistent.
- Measure: animation dump tokens, time to infer event rule.
- Risk: missing visual nuance.

Item 8: Generic instruction pack for common hidden mechanics.
- What: warnings: budget bars nonuniform, selection persists, marker color phase, click-swap, wall bands clickable, deformable shapes, color pickups, dual registers, denied animations.
- Evidence: lp85, ar25, ft09, tu93, sb26, re86, r11l, vc33, sp80, tn36.
- Implement: system prompt section with short rules.
- Measure: wrong-hypothesis stalls, instruction adherence.
- Risk: prompt overload.

Item 9: Persistent save/scratchpad infrastructure.
- What: transactional save_module, first-class tool, persistent state dict, auto checkpoint.
- Evidence: many "Saved modules: none", save_module misuse, rollback, repeated helpers.
- Implement: save() separate, rollback only if save itself fails; session notes.
- Measure: repeated helper code, context loss, save failures.
- Risk: stale state; need versioning.

Item 10: Geometry-first/CSP before probing.
- What: infer visual geometry, hypothesize cycles/loops/assignments, verify one press, solve CSP/BFS before moving.
- Evidence: lp85 overprobing, ft09 CSP, sb26 multiset, r11l assignment, tr87 chain, tn36 dual registers, wa30 joint scheduling.
- Implement: instruction: inspect shape first; tool for geometry detection? maybe not.
- Measure: learning actions / execution actions, action ratio.
- Risk: wrong geometry, overconfidence.

Then infra faults:
- vc33 sandbox exited unexpectedly level 7.
- ls20 timeout with 6935 action calls; suspected action executor should hard-stop after game_over/timeout.
- save_module rollback? "failed save made no workspace changes" wa30, ls20; questionable design fault.
- tool output truncation? maybe design limitation; include as infra friction? The user says fault rather than playing mistake. Could say "not faults but harness limitations: truncation, missing budget field, animation thinning". But ask list anything that looked like fault. Could include "confirmed/suspected" and "design limitations". Need maybe under word count.

Need ensure final not too long. Let's write polished.

Double-check word count maybe around 2200. Need maybe avoid too much detail. Could use compact bullets.

Need mention "expected total score gain" for each. Could include "Gain: Very high" etc.

Let's draft final in final. Ensure under 2500. Use concise. Need maybe mention "across all games". Good.
