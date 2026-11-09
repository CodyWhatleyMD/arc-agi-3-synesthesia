# Self-review: wa30-ee6fef47

game wa30-ee6fef47: state gave_up, levels 4/9, final score 13.990247014033468, stop reason ?
  level 1: your actions 51 vs human baseline 71
  level 2: your actions 134 vs human baseline 119
  level 3: your actions 199 vs human baseline 183
  level 4: your actions 193 vs human baseline 98
  level 5: your actions 748 vs human baseline 368 (not cleared)
  level 6: your actions - vs human baseline 68 (not cleared)
  level 7: your actions - vs human baseline 79 (not cleared)
  level 8: your actions - vs human baseline 442 (not cleared)
  level 9: your actions - vs human baseline 415 (not cleared)



## 1. The game

The core mechanic I eventually understood was:

- The player is a green 4×4 block with a white 1-cell “cap” showing facing direction.
- An arrow press turns the player and slides it 4 cells if the destination is free; if blocked, it only highlights the blocker.
- `SPACE` grabs/drops a box touching the cap. A carried box rides on the facing side and moves with the player.
- Early levels ask you to carry charcoal/blue boxes into the blue “bar”/target region.
- Later levels add an autonomous orange bot that also fetches boxes to the target region. On level 5 the goal appeared to be getting all six boxes into the blue-ringed gray region, but the exact valid slots were never fully confirmed.

The critical level was 5: six boxes, one narrow shared gap, an autonomous bot, and a hard 125-action budget. I never cleared it.

## 2. Timeline and decisive mistakes

**Level 1 — cleared, reasonably efficient.**  
I probed movement and `SPACE`, discovered that the white cap indicates facing, that blocked presses highlight, and that `SPACE` attaches/detaches boxes. I eventually understood the blue bar as a 3-slot target and cleared it in 51 actions. This was the cleanest part of the run.

**Levels 2–4 — cleared but inefficient.**  
I cleared levels 2 and 3 with 134 and 199 actions, and level 4 with 193 actions. Level 4 introduced bot/pulling behavior, and I saved notes such as `level3_notes` and `l4play`. These notes were useful, but I did not fully exploit them on level 5.

**Level 5 — the run broke here.**  
Level 5 consumed 748 actions and produced six game overs before I gave up. The transcript shows the same failure loop:

1. **Bot deadlock / gap blocking.**  
   I repeatedly carried a box into the only gap and found the bot parked there. For example:  
   > “The bot is parked at (28,28) and NOT moving while I idle.”  
   > “Blocked again by the bot at (28,28) in the gap.”  
   I spent many actions idling with `SPACE`, watching the bot, and trying to make it move. Those idles still consumed budget.

2. **Ambiguous grab/drop state.**  
   The white cap and attached white box often merged into one segmentation node, making it hard to tell whether a box was attached or dropped. I wrote:  
   > “SPACE did not drop it?”  
   > “Confusing. Two boxes?”  
   I burned actions testing the drop rule instead of first building a reliable state representation.

3. **Long unverified batches failed badly.**  
   I sent 30–40 action sequences based on a hand-derived route. The worst was P3:  
   > “my own placed box at (32,12) blocked the eastward exit.”  
   That 40-action batch failed because I had not simulated the player’s own previously placed box as an obstacle.

4. **Idling doomed runs instead of resetting/testing.**  
   When the remaining budget was clearly too small, I often wrote things like:  
   > “Idle out run 3 while bot places its box.”  
   > “Idle run 5 to game over.”  
   This wasted the remaining actions and prevented me from starting a cleaner attempt with a better plan.

5. **Saved-module friction.**  
   I tried to save level-5 plans, but several saves failed because old tests pinned old interfaces:  
   > “failed save made no workspace changes.”  
   This cost turns and fragmented my notes.

The decisive failure was not one bad move, but treating level 5 as a sequence of hand-computed carries while ignoring the joint dynamics of player, bot, boxes, and the single gap.

## 3. What I lacked or what misled me

**I lacked an explicit target map.**  
Early on I saw what looked like distinct sockets:

> “blue rings at cols 8-11... boxes I placed at cols 12-15 are NOT on sockets!”

But I later treated any charcoal box inside the gray region as progress. I never confirmed whether all interior cells were valid slots or whether only certain blue-ringed sockets counted. The final game-over frames showed boxes inside but no completion, and the exact win condition remained uncertain.

**I lacked a model of the bot.**  
The bot was just an orange node. The tools gave no bot target, path, or intent. I inferred that it freezes when I or my carried box blocks its route, but I never built a reliable simulator for it. That made every gap transit risky.

**The budget was indirect.**  
I had to count pink pixels in row 63 to estimate remaining actions. That worked, but it made endgame decisions clumsy and encouraged “idle and hope” behavior.

**The tools did not distinguish attached vs dropped boxes cleanly.**  
Because the cap and attached box could merge into one white node, I repeatedly misread state. That directly caused wasted grab/drop tests.

**The instructions encouraged action, but not joint-state search.**  
The system prompt says to use BFS/pathfinding when the objective is understood, but I mostly used hand-written action lists. Level 5 required planning with a moving NPC and dynamic obstacles, and I did not build that model until it was too late.

## 4. Improvements, ranked by expected score gain

### (a) Harness/tool improvements

1. **Expose goal/valid-slot state and held-object state.**  
   The biggest level-5 blocker was not knowing whether a box was attached, dropped, on a valid socket, or merely “inside” the region. A tool result like `held_box`, `target_cells`, `sockets_filled`, or `goal_progress` would have prevented dozens of ambiguous `SPACE` tests. Evidence: repeated “did SPACE drop it?” confusion and final uncertainty despite four boxes inside.

2. **Provide a dry-run/simulation action.**  
   A `simulate(actions)` call returning the first blocked/no-op action and resulting state would have saved the 40-action P3 failure and several 20–35 action batches. Evidence: “my own placed box at (32,12) blocked the eastward exit.”

3. **Expose NPC state: position, target, path, and freeze reason.**  
   The bot’s behavior was the central level-5 mechanic. Without a bot-target/path field, I had to infer it from idles. Evidence: bot parked at `(28,28)` and repeated deadlock around the gap.

4. **Give a numeric action budget.**  
   Counting pink pixels was error-prone and made endgames noisy. A direct `actions_remaining` field would have made reset/abort decisions clearer.

### (b) Instruction improvements

1. **Require verifying the goal representation before optimizing.**  
   The instructions say to test rules against transitions, but I should have been told explicitly: for placement puzzles, first identify the exact valid target cells, not just the large target region. Evidence: I initially saw blue sockets, then abandoned that clue and assumed “inside = placed.”

2. **Require modeling autonomous NPCs as dynamic obstacles/helpers.**  
   A stronger instruction would be: “If an NPC shares a corridor with the player, build a conflict-free schedule before executing long batches.” Evidence: level 5 repeatedly failed because the bot and player needed the same gap.

3. **Discourage idling doomed runs; encourage immediate reset and plan revision.**  
   The prompt says “Never give up,” which is good, but it should also say: “When the remaining budget cannot satisfy the known lower bound, stop and restart with a corrected model.” Evidence: many turns were spent idling out runs 3–6.

### (c) My own strategy improvements

1. **Build a level-5 simulator before carrying boxes.**  
   I should have written a small state-space model with player position/facing, bot position, boxes, target cells, and gap occupancy, then searched for a conflict-free schedule. Even a simple A* over player trips with the bot as a moving obstacle would have prevented the repeated gap deadlocks.

2. **Inspect the initial socket pattern and only drop on confirmed valid cells.**  
   At fresh level 5, I should have printed the blue/gray socket pattern before moving, then made every carry target a socket. Instead, I carried boxes into the east column and later found that did not complete the level. Evidence: the final game-over frame had the east column filled and the west column still blue/gray.

3. **Batch only after a dry-run or per-step assertion.**  
   My long sequences were plausible but fragile. I should have executed 3–5 actions, checked the state, and only then continued. The P3 failure shows why: one overlooked placed box invalidated the whole route.

4. **Use the level-4 bot/pull notes more directly.**  
   The saved `level3_notes` mentioned bots pulling boxes and border embedding. I did not test whether that mechanic applied to level 5. It might have made the bot much more efficient than my hand-carried trips.

5. **Save executable plans with assertions, not just prose notes.**  
   My saved modules were useful but brittle. A better pattern would have been a function returning an action list plus a validator that checks player/box/bot positions after each prefix. That would have caught wrong assumptions before burning 30+ actions.

The largest score gain would come from clearing level 5. That required one thing I did not do early enough: treat level 5 as a joint planning problem with explicit target cells, a bot model, and a simulator, rather than as a series of heroic manual carries.
