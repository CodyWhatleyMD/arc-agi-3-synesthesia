# Self-review: sb26-7fbdac44

game sb26-7fbdac44: state won, levels 8/8, final score 72.03981222487187, stop reason ?
  level 1: your actions 9 vs human baseline 18
  level 2: your actions 16 vs human baseline 28
  level 3: your actions 15 vs human baseline 18
  level 4: your actions 17 vs human baseline 19
  level 5: your actions 41 vs human baseline 31
  level 6: your actions 19 vs human baseline 23
  level 7: your actions 80 vs human baseline 58
  level 8: your actions 51 vs human baseline 18



## 1. The game

A "splice the sequence" puzzle. A colored **target sequence** sits at the top; below are a bracketed **main box** and one or more **sub‑boxes** with slots; a bottom **palette** holds solid tiles and **ring** tiles. Click a palette tile to select it, click a slot to place it (clicking an occupied slot while holding a tile **swaps**). **SPACE** submits. The mechanic I eventually understood: the main box is read left‑to‑right, and a **ring placed in a slot is read as the contents of the sub‑box whose color matches the ring** (a splice/insertion). A ring *inside a spliced box* splices recursively, so a self‑referencing ring pair can make the reading repeat — which is exactly why level 8's target is the same 6‑color pattern printed twice. Pre‑filled tiles are locked. Levels 1–4 are the base case; 5–8 add multiple rings, recursion, and locked prefills.

## 2. Timeline

- **L1–L3 (9/16/15 vs 18/28/18):** clean. Inferred "fill slots in sequence order, SPACE to submit" from one probe, and the ring‑marks‑a‑plug rule by level 2. No real waste.
- **L4 (17 vs 19):** one wasted submission — I left the plug slot empty and submitted; the palette's hollow ring was actually a tile I had to place. Recovered in ~6 actions.
- **L5 (41 vs 31):** first stall. I cycled through wrong ring semantics (repeat‑previous, hole, mirror, insert‑once) and many SPACE probes, misreading the error animation. The eventual key was pure arithmetic — `sequence = M + (N,R,R) + (N,R,R) + Y,p` ⇒ the 3‑tile sub‑box splices at **both** rings.
- **L6 (19 vs 23):** cracked immediately from the L5 insight.
- **L7 (80 vs 58):** the worst leak. Three boxes, two rings, one locked prefill. I held "skip", "prefill‑first", "prefill‑last" models far too long against an ambiguous flash, then **discovered the correct model (nested splices: red=(R,b,ringN), green=(N,Y,ringb), blue=(N,b,R))** only after ~60 actions. A second killer: my carry‑chain swap plan **re‑clicked the source cell after a swap, undoing it** ("my step 3 was (26,23) again … that undid step 2").
- **L8 (51 vs 18):** correct model derived (red=(ringb,N,p,ringR), blue=(R,Y,O,b) expanding twice), but I executed the 8‑cycle permutation **wrong twice** for the same re‑click reason, then had to redo it as a clean carry chain.

## 3. What misled me

- **The error animation as an oracle.** `last_action_result['animation']['bbox']` is a *union* across 16 frames and includes the scan sweep, so "first mismatch column" was not reliably readable; I burned actions on probes that turned out non‑discriminating (L5's two "blue=R,ring,Y vs R,ring,Y" probes produced identical flashes).
- **My own hand‑tracing of clicks.** I never encoded the swap/undo semantics in code, so long carry‑chains silently broke and I lost track of board state (L7, L8).
- **Delayed multiset arithmetic.** The decisive facts on L5/L7/L8 (tile‑multiset vs sequence, locked‑prefill position) were derivable from symbols alone, before any probing; I probed first and reasoned later.
- **Budget bar misread** early (thought 1 cell/action; it ticks slower) — minor, but it made me over‑cautious.

## 4. Improvements, ranked by expected score gain

**(a) Harness / tools**
1. **Structured submission feedback** — return `first_mismatch_index` and the producing slot in `last_action_result` instead of forcing me to diff `animation_frames`. *Evidence:* the entire L5/L7 flash‑reading detours (~30+ actions). Highest gain.
2. **Per‑click resulting slot→tile map** (or a "swap/undo occurred" flag). *Evidence:* the re‑click‑undo bug cost ~10 actions on L7 and ~20 on L8.
3. Numeric `actions_remaining` field (the bar is ambiguous).

**(b) Instructions**
1. **State the click‑swap semantics explicitly** ("clicking an occupied slot while holding a tile swaps them; the held tile becomes the displaced one; clicking the source again undoes"). *Evidence:* L7/L8 carry‑chain failures.
2. **Hint the ring/splice mechanic** (ring = splice of the color‑matched box; recursion possible). The whole game is one evolving mechanic; an early hint would compress L5–L8.
3. Prompt me to **model the click action in a saved module and test it before batching swaps** — I had the `save_module` facility and never built the obvious `apply_click`/`read_state` module.

**(c) My own strategy**
1. **Build a saved `state` extractor + `splice_read(arrangement)` + arrangement search** that compares the produced sequence to the target *before* touching the board, then emits a click plan from a tested click‑simulator. *Evidence:* L5/L7/L8 breakthroughs were all arithmetic I did late; a solver would have made them near‑baseline.
2. **Do multiset/locked‑prefill arithmetic first**, probe only to disambiguate residual models.
3. **Use verified pairwise swaps** (segmentation diff after each) instead of long carry‑chains; treat `per_step_changed_pixels==0` as an immediate no‑op/undo signal.
4. On a failed SPACE, **change the hypothesis, not just one tile** — I repeated near‑identical probes (L5) that the instructions explicitly warn against.

Net: the win came through, but the score leaked almost entirely in L7 (80 vs 58) and L8 (51 vs 18), both from a wrong‑model‑too‑long plus a self‑inflicted click‑undo bug — both fixable with a saved click‑simulator and an earlier multiset analysis.
