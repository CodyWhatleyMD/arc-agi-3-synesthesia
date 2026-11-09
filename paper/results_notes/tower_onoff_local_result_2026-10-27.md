# Tower on/off, local replication: result (read 2026-10-27 18:30 CDT, with the investigator; pre-statement notes/prestate_tower_onoff_2026-10-27.md)

**Verdict: NOT RESOLVED at n=3 vs 3, leaning toward the board channel helping.** The 10-14 single run (214d) read as
"the image buys nothing"; three runs each way lean the other direction, short of proof.

## Runs (all valid on every pre-stated gate before any score was read)
| run | arm | notebook | mean score | levels | actions | tokens | gen tok/s | slope 10-100 play-min | @60 | @90 | @100 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| r2 | ON | f9af78d9 | 40.19 | | 10,643 | 6,149,189 | 784.5 | 0.352 | 21.1 | 34.2 | 37.8 |
| r3 | ON | f9af78d9 | 44.26 | | 9,264 | 6,053,215 | 772.1 | 0.416 | 21.8 | 38.2 | 40.1 |
| r4 | ON | f9af78d9 | 41.41 | | 9,128 | 6,163,306 | 786.2 | 0.427 | 29.0 | 35.9 | 38.4 |
| bo1b | OFF | 13ca3836 | 42.66 | | 8,046 | 6,499,996 | 829.3 | 0.403 | 27.6 | 35.2 | 39.3 |
| bo2b | OFF | 13ca3836 | 39.89 | | 7,610 | 6,766,214 | 863.2 | 0.431 | 23.7 | 36.3 | 37.5 |
| bo3b | OFF | 13ca3836 | 32.44 | | 10,157 | 6,521,308 | 831.8 | 0.223 | 13.8 | 19.2 | 24.3 |
OFF = MULTIMODAL_CONTEXT=none (no board part on any turn, no MULTIMODAL_CONTEXT_ADDENDUM in the system prompt); OFF
harness = 8552964 + faab14c (one inert run-time env lookup); gates incl. 0 image parts in 3,134 / 3,241 / 3,720
requests; 0 sandbox deaths in all six; analyzer read-timeouts 16-21 per run (per-game clocks expiring, as in v8).

## Primary (scripts/compare_arm_groups.py; notes/tower_onoff_local_primary_2026-10-27.json)
- Mean score: OFF 38.33 vs ON 41.96, **Δ = −3.62, 95% paired-by-game bootstrap CI [−9.89, +3.22]**, sign 7 up / 17
  down / 1 tie, p = 0.064. CI includes 0 -> NOT RESOLVED. Direction: OFF lower on 17 of 24 decided games.
- Levels: Δ = −0.24, CI [−0.64, +0.19], sign 6/15/4, p = 0.078. Same lean, same verdict.

## Secondary (reported, not deciding)
- Throughput: OFF generates faster (829-863 vs 772-786 tok/s, ~+8%, the 214d direction) and uses MORE tokens
  (6.50-6.77M vs 6.05-6.16M) but takes FEWER actions in two of three runs (8,046 / 7,610 vs 9,128-10,643). Without the
  board part the model writes more per action and acts less; the payload saving did not become score. Both tails
  were named; the "OFF gains from speed" tail did not happen.
- Slopes (exploratory, clarification 2): ON 0.352 / 0.416 / 0.427 (mean 0.398); OFF 0.403 / 0.431 / 0.223 (mean
  0.353). Two OFF runs sit inside the ON range; bo3b is an outlier slow from its first summary (13.8 at 60 min vs
  21-29 for every other run) and carries most of the mean difference. Arm effect or bad run: not separable at n=3.
- Stable bottom five (bp35 lf52 ls20 sk48 wa30): mean levels OFF 1.87 vs ON 2.20. Coin-flip ten: in the JSON.

## What this does and does not say
It measures the board part AND its prompt section together, in the shipped harness, locally, 25 public games, 9,300 s.
It does not separate student from native pixels (F208b), does not touch the hidden set, and does not speak to Batch A.
The paper's slot reports it as written here: not resolved at n=3 vs 3, leaning toward the channel helping.

## Annotation (21:52 CDT, after the 19:19 finding; a side agent caught that this file still lacked it)
The ON arm (the shipped student arm, r2/r3/r4) carried not one board per request but every board since the last
compaction: median 13 image_embeds parts per request, maximum 48 (r2's 2,817 requests; the history stripper in
vision_context.py:164 recognises only text and image_url parts, so embeds parts are invisible to it). OFF removed the
current board AND all of that history. The -3.62 [-9.89, +3.22] is the two together; the current board's own share is
unknown. The history-window arm (notes/prestate_history_window_2026-10-27.md; K = 1 and 4) is what separates them.
