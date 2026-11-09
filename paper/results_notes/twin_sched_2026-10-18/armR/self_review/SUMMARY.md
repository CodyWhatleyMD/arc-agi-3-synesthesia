# Self-review: the whole run



Assumption: expected total score gain is dominated by preventing low-scoring stalls, game overs, and uncleared later levels; action efficiency matters where levels were already cleared.

## Top 10 improvements, ranked by expected total score gain

### 1. Hard budget guard + safe action executor  
**Change:** Expose exact `actions_remaining` per level; make `action()` support a hard cap, auto-stop on `game_over`/`level_completed`, and abort after repeated no-progress actions. Instructions should require plan length ≤ remaining budget minus margin.  
**Evidence:** `tr87` burned 256 RIGHT presses in an unguarded loop; `ka59` spent 1036 actions on level 6 partly via deliberate burn batches; `wa30` spent 748 actions idling doomed runs; `sk48` spent 197 actions before realizing little budget remained; `ls20` executed a 41-move plan when true budget was ~21; `tn36` repeated three 61-action game overs; `cd82`, `dc22`, `vc33` all suffered budget misreads.  
**Implement:** Add `current_frame.actions_remaining`, `action(actions, max_actions=...)`, no-progress counter, and post-game-over hard stop. In strategy, maintain `estimated_remaining` every turn and refuse batches longer than it.  
**Measure:** Max level actions, number of game overs, timeout count, action ratio vs human baseline.  
**Risk:** Too conservative caps can prevent needed exploration; cap should be adaptive and overridable only with explicit reasoning.

### 2. Semantic action-effect recorder  
**Change:** After every action, return compact semantic diff: what moved, what was blocked, what was denied, selection change, object-state change, events, and budget change separated from gameplay change.  
**Evidence:** `m0r0` needed “left square moved, right blocked, no reset”; `re86` needed blocked/deformed/split info; `s5i5` needed push/pull/blocked-object info; `sk48` simulator bugs caused 110 wasted actions; `g50t` repeatedly re-derived red-snake behavior; `dc22` needed denial reason; `sp80` needed pour/activation/drain events; `tu93` needed hazard marker-color state; `vc33` missed clickable saturated bands.  
**Implement:** Post-action parser using segmentation and animation: `changed_cells`, `moved_objects`, `blocked_by`, `denied`, `events`, `selection_changed`, `budget_changed`. Keep output under ~10 lines.  
**Measure:** Probes to first mechanic, wrong-model duration, action waste per level.  
**Risk:** Verbose or noisy diffs; needs filtering and stable object IDs.

### 3. Mandatory early saved simulator and validation before batching  
**Change:** Require a saved, executable world model after the first confirmed mechanic; validate it against observed transitions before executing long plans.  
**Evidence:** `s5i5` had “Saved modules: none” and stalled on level 3; `sk48` executed a 110-action plan from a buggy simulator; `g50t` never saved a state module; `tn36` repeatedly rebuilt helpers; `cn04` wasted turns on a buggy rotation model; `wa30` failed a 40-action batch because placed boxes were not simulated; `dc22`, `vc33`, `ka59`, `tr87` all solved late because modeling came too late.  
**Implement:** Instruction checkpoint: by first mechanic, save `state(frame)`, `apply(state, action)`, `goal(state)`, and a validator against `transitions`. Only batch simulator-verified plans. Harness could scaffold a template module.  
**Measure:** Simulator validation pass rate, long-batch failure rate, levels cleared, action ratio.  
**Risk:** Over-modeling simple levels; model can be wrong if mechanics change per level.

### 4. Affordance/object-role discovery helper and immediate affordance sweep  
**Change:** Provide a tool that identifies likely interactive objects and safely probes one representative per color/hash; instruct the agent to click every distinct object before building a movement model.  
**Evidence:** `bp35` spent ~100 actions before discovering green blocks were clickable doors; `ft09` misread icon cells as constraints instead of Lights Out buttons; `tu93` missed hazard marker-color state; `sp80` delayed bar activation rule; `r11l` delayed color-pickup mechanic; `wa30` confused held/dropped boxes and valid sockets; `cd82` confused ball/mold; `re86` struggled with deformable shapes.  
**Implement:** `affordance_probe()` selects non-background, repeated, or control-looking nodes and returns compact diffs. Strategy rule: “If goal is unclear, click one representative of each distinct object color/hash before movement theory.”  
**Measure:** Actions to first mechanic, false-positive probes, avoided game overs.  
**Risk:** Probes can be lethal or irreversible; need safe-position checks and cheap undo/reset awareness.

### 5. Derived game-state / selection / role API  
**Change:** Expose higher-level state: selected object, agent, held object, attached targets, cursor, buttons, hazards, phase, registers, and target satisfaction.  
**Evidence:** `ar25` lost actions because selection was implicit; `r11l` lacked hub color state; `re86` lacked logical shape/arm state; `sk48` needed player/beam/target/attached state; `ls20` needed roles for rings, key, cross, box; `sp80` needed active/locked bar roles; `tn36` failed to see dual toggle registers; `wa30` lacked held/valid-slot state.  
**Implement:** Add `frame.selected`, `frame.held`, `frame.targets`, `frame.hazards`, `frame.cursor`, `frame.registers`, or annotate segmentation nodes with `role` and `state`.  
**Measure:** State-misread incidents, wasted selection probes, level clear rate.  
**Risk:** Hard to generalize; may require game-family adapters or become misleading if roles are guessed.

### 6. Hypothesis ledger + anti-stall / game-over reset policy  
**Change:** Maintain explicit hypotheses, status, and next discriminating test. After any game over, no-progress streak, or contradiction, force a change of hypothesis family rather than repeating the same probe.  
**Evidence:** `tn36` repeated the same 61-action sweep three times; `g50t` repeatedly retested red-head capture; `sk48` kept using a diverged simulator; `dc22` held “pink is inert” too long; `bp35` repeated flood/no-op tests; `tu93` repeated the same lethal level-8 route; `tr87` burned a whole budget after a stuck navigation loop.  
**Implement:** Add a compact ledger: `hypothesis | status | next_test`. Harness can track no-progress count and warn. Strategy: after game over, inspect game-over frame and add lethal state to model before retrying.  
**Measure:** Repeated experiment count, post-game-over action diversity, time to switch hypotheses.  
**Risk:** Premature abandonment of correct but slow hypotheses.

### 7. Compact animation/event summaries and game-over reason  
**Change:** Replace raw animation dumps with event tracks and reasons: path, rejected move, cup filled, drain reached, bar activated, launch event, game-over reason.  
**Evidence:** `tr87` needed cursor/path info; `su15` needed `move_rejected` and compact animation tracks; `sp80` needed pour/cup/drain/activation events; `g50t` needed game-over reason; `sk48` needed target movement tracks; `tn36` needed pawn path extraction; `ka59` lost launch-animation details.  
**Implement:** Animation parser returns `animation_tracks`, `path`, `events`, `game_over_reason`, and compact frame summaries. Keep raw frames opt-in.  
**Measure:** Tokens spent on animation dumps, time to infer event-based rules, wasted probes after game over.  
**Risk:** Parser may miss visual nuance; keep raw-frame fallback.

### 8. Generic instruction pack for common hidden mechanics  
**Change:** Add short, general warnings: budget bars may be nonuniform; selection persists; marker color can encode phase; click-on-occupied-slot may swap; wall bands may become clickable; shapes may deform; colored pickups may be stateful; visually connected controls may contain independent bits; denial animations are diagnostic.  
**Evidence:** `lp85` bracket/token and HUD confusion; `ar25` selection/mirror ambiguity; `ft09` icon/button semantics; `tu93` marker-color phase; `sb26` click-swap semantics; `re86` deformable shapes and simultaneous capture; `r11l` color pickups; `vc33` saturated bands; `sp80` recoloring as activation; `tn36` dual registers.  
**Implement:** Add a concise system-prompt section: “Common ARC-3 traps” with one-line rules. Avoid level-specific spoilers.  
**Measure:** Wrong-hypothesis stalls, instruction adherence, action waste on common traps.  
**Risk:** Prompt overload; too many warnings can dilute attention.

### 9. Persistent save/scratchpad infrastructure  
**Change:** Make saved modules first-class, transactional, and encouraged; provide a persistent scratchpad for world-model state.  
**Evidence:** Many transcripts show `Saved Python modules: none`; `save_module` misuse; `wa30` had failed saves and stale notes; `ls20` had save rollback after later exceptions; `s5i5`, `g50t`, `tn36`, `sk48` repeatedly rebuilt helpers.  
**Implement:** Separate `save_module` from execution, persist successful saves despite later errors, add `session_state` dict, auto-checkpoint after level clear or major mechanic.  
**Measure:** Repeated helper code, context-loss incidents, save failures, recovery time after reset.  
**Risk:** Stale modules can mislead; need versioning and validation.

### 10. Geometry-first / constraint-solving before probing  
**Change:** Strategy: inspect visual geometry first, hypothesize rings/loops/assignments, verify with one or two presses, then solve CSP/BFS before moving.  
**Evidence:** `lp85` overprobed levels 6/8 despite simple ring/loop geometry; `ft09` should have run CSP before wrong batches; `sb26` breakthroughs were multiset arithmetic done late; `r11l` needed global ghost→ring→chain assignment before moving; `tr87` should have solved wheel-state CSP after dumping wheels; `tn36` should have searched full dual-register state; `wa30` needed joint scheduling model.  
**Implement:** Instruction: “If the board has visible cycles, rows, loops, or repeated regions, guess geometry before color-diff matching.” Add small CSP/BFS helper templates.  
**Measure:** Learning actions vs execution actions, action ratio vs baseline, number of failed long batches.  
**Risk:** Wrong geometry can cause confident mistakes; always verify with minimal probes.

## Harness / infrastructure faults or suspected faults

- **Sandbox crash:** `vc33` level 7 ended with “Sandbox process exited unexpectedly” during a BFS attempt. This likely cost the largest score in that run.
- **Runaway action timeout:** `ls20` had a timeout with `action_calls 6935` after continuing to call `action()` post-game-over. Even if the loop was partly a player mistake, the harness should hard-stop or return an unrecoverable stop signal.
- **Save-module rollback behavior:** `wa30` and `ls20` report failed saves or “no workspace changes” after exceptions. If a successful save can be rolled back by a later unrelated exception, that is infrastructure friction.
- **Tool output truncation:** Many games mention 1024-token caps, truncated masks, and lost animation details. This is a design limitation, but it functioned as an infrastructure bottleneck causing repeated re-derivation.
- **Missing semantic game-over reason:** `sp80`, `g50t`, and others received `game_over=True` with almost no diagnostic. Not necessarily a fault, but a harness omission that strongly hurt recovery.