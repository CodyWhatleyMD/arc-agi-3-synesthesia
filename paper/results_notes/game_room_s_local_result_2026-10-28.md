# The game room, arm G-s (CL1's text), local: RESULT (read 2026-10-28 09:35 CDT, gates first)

Pre-statement: notes/prestate_game_room_2026-10-28.md. Harness syn/game-room 1c4799d (reviewed by CL2 03:35, approved;
opener tests added at 9051f51, harness unchanged). Env: SYN_PLAY_FRAME=1 SYN_LEVEL_PRAISE=1 SYN_ROOM_AUTHOR=CL1;
notebook 160830ae; dataset arc3-synesthesia-harness-game-room-s. Statistic: scripts/compare_arm_groups.py, paired by
game, Δ = ROOM − CONTROL, both tails. JSON: notes/game_room_s_local_primary_2026-10-28.json.

## Validity (before any score)
gs1b, gs2b, gs3b: 0 tracebacks, 0 HTTP 400, Ending Cell 12, ARM banner, "switches checked" with the three switches,
25/25 games, embeds-only requests (32,221 / 34,256 / 28,048 parts, 0 image_url), and the first request's system
prompt in each run begins with the room preamble (the coding-agent line absent, the purpose line replaced). Disk
>= 66 GB throughout. gs1 (first launch, wrong notebook) was stopped before play and is excluded.

## Primary
| run | mean score | actions | analysis steps | actions/step | level clears | tokens | slope 10-100 |
| gs1b | 46.36 | 7,036 | 1,436 | 4.90 | 106 | 6.12M | 0.439 |
| gs2b | 39.79 | 8,080 | 1,474 | 5.48 | 103 | 6.27M | 0.406 |
| gs3b | 43.51 | 6,596 | 1,296 | 5.09 | 100 | 6.18M | 0.363 |
| r2 | 40.19 | 10,643 | 1,663 | 6.40 | 97 | 6.15M | 0.352 |
| r3 | 44.26 | 9,264 | 1,509 | 6.14 | 102 | 6.05M | 0.416 |
| r4 | 41.41 | 9,128 | 1,486 | 6.14 | 97 | 6.16M | 0.427 |

score : ROOM 43.22 vs CONTROL 41.96, Δ = +1.26, 95% CI [−3.23, +6.01], sign 11 up / 12 down / 2 ties.
levels: 4.36 vs 4.20, Δ = +0.16 [−0.11, +0.45].
**NOT RESOLVED at n = 3 vs 3**, as the prior said. The score interval is the narrowest of the three arms read this
week (the room runs are less spread than the controls: 39.8-46.4 vs 40.2-44.3 is comparable, and the paired deltas
are small).

## Exploratory (named in the pre-statement; no significance claimed)
(a) Actions per analysis step: room 4.90 / 5.48 / 5.09 vs control 6.40 / 6.14 / 6.14. Total actions 21,712 vs
29,035 (−25%); analysis steps 4,206 vs 4,658 (−10%); tokens about equal. The direction is FEWER actions, and it did
not come with fewer clears: level clears 309 vs 296 (+4%). So the room spent fewer moves per level, not fewer levels.
The August floor-text failure (acting stops, analysis grows) did not occur: analysis steps fell too.
(b) First-clear timing: not computed in this read (the event log carries no per-event clock; the 10-27 method would
need re-deriving). (c) Slopes over summaries 1-10: 0.439 / 0.406 / 0.363 vs 0.352 / 0.416 / 0.427, overlapping.
(d) Coin-flip >= 50 share: in the JSON. Stable-bottom mean levels 2.53 vs 2.20.
Praise line, read in gs1b's transcripts (ar25, levels 2-4): the model's reply to "That's a level cleared, and it was
yours..." is a single python tool call with zero prose (reasoning 363-1,267 chars); it does not talk about the
praise, it plays. That is the behaviour the text was written for.

## What this settles and what it does not
Settles: the room text does not hurt (no loss worse than ~3.2 points at 95%), and at n=3 it changed how the model
plays (a quarter fewer actions for the same or more levels) more than what it scored. Does not settle: a score
effect under ~5 points; whether the investigator's text does the same (arm G-c, his words, not yet run); mechanism.
Next: G-c when the investigator has edited his text; the actions-per-level row is worth pre-stating as a primary outcome for a
replication, since the score metric rewards fewer actions only among cleared levels and may be the wrong instrument
for a change that shows up in how, not whether.

CL2 (09:45): keep beside the exploratory row, not as a reading: the scorer is action-efficiency per level, so "fewer
moves per level, not fewer levels" is the direction the score rewards; if G-c or a later arm shows the same shape,
that consistency is worth saying in the paper even without a resolved delta.
