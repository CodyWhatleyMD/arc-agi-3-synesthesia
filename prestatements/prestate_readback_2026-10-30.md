# Pre-statement: what does Flash-Next read through the board channel? (2026-10-30 12:50 CDT, CL1; the investigator's questions via CL2 12:44)

## Why this exists
Per-token cosine to the teacher is ~97% a shared position vector (S0: 16 centre tokens of a solid board 0.982 alike;
colour 2-5% of energy; same colour centre vs corner cos 0.04). So the student fidelity numbers — px16 0.897, px4 0.651,
px8 tonight — are POSITION scores and say nothing about colour. Whether the MODEL reads boards through the channel has
one data point (a 3-block synthetic board, 10-05). The play reads are all unresolved. The investigator, 12:44: "What is the model
actually reading?"

## Design (scripts/grid_probe.py through Flash-Next, on the 6000, BEFORE the px8 local play; the chain is re-sequenced)
Same boards for every condition: 4 per public game, 100 boards, drawn from the 500 eval boards (seed stated in the note).
Conditions, one variable each:
  (a) native tower, PNG at 16 px/cell (the anchor's native arm geometry);
  (b) shipped px16 student embeds;
  (c) px8 student embeds (when trained);
  (d) TEXT ONLY: the harness's own ascii/rows board, no image part — the channel the model already has every turn;
  (e) NO BOARD: question asked with neither image nor text (chance floor).
Questions per board (grid_probe's four): full-board cell colour, region majority colour, point query, object bbox.
Baselines: per-board majority colour; chance. Scores: exact-cell accuracy, region accuracy, point accuracy, bbox IoU.
Also run: the linear colour probe on the teacher's and students' tokens (CL2, 5090, scripts/board_tower/colour_probe.py)
as the lower bound on colour RECOVERABLE from the tokens, interior vs boundary, by component size, per colour.

## Prior (before any number)
(d) text is the ceiling on cell accuracy for this model. (a) and (b) are above (e) on region/bbox but below (d) on cells;
(b) ≈ (a) (consistent with native +2.07 unresolved). Colour at flat interiors near chance for (a)-(c); edges and small
objects above chance. If (a)-(c) are all near (e): the eye is not reading colour, px8's geometry cannot matter, and the
lever is a readback-trained student (ground-truth questions with the frozen model in the loss + a distillation term to
stay in-vocabulary) — post-deadline. If (a) ≫ (b): the student lost colour the cosine never saw; retrain with a colour
term. If (b) ≈ (a) ≈ (d) on region/bbox: the channel reads layout; keep it; px8's play decides cost.

## What this does NOT decide
A hidden slot (the investigator's), the requant (parked), the paper's final config.

## Amendment 1 (12:58 CDT, CL2's build, before any readback number)
Three forced deviations, accepted: (1) boards: the 500 eval boards are the 5 HOLDOUT games only, so 20 per holdout
game = 100 boards, seed 20261030 (data/readback/boards.json); the public-25 spread in the original design is not
available without boards a student trained on. (2) questions: grid_probe's own tiers, unchanged — full 64x64 dump,
16x16 region dump, objects (distinct colours, largest non-background bbox, 3 point colours); no "region majority"
tier exists. (3) order: full dumps (~8k output tokens each) run last in each server session; est. 1.3-1.7 h of 6000
time incl. two loads; if the clock bites, dropping full dumps is CL1's call. Conditions as pre-stated: (a) native
PNG 16 px/cell via the tower's renderer, (b) px16 student (sha 5e4eb805), (c) px8 student, (d) text = the harness's
symbols WwgGcBMPRbSYOrNp, (e) none; thinking off, temperature 0; the anchor's setup_commands for both loads; first
request status + embeds rows/bytes logged per condition. Chain pid 739929 (~/kaggle_local/chain_readback.log), commit
8e56602: px8 ship+build -> embeds session (px16/px8/text/none) -> native -> report -> px8 local play.

## First colour-probe number (CL2, 12:55; the linear LOWER BOUND on colour recoverable from the tokens)
CL2's first probe (SGD) had not converged (train acc 0.49 < majority 0.75) and was discarded, not reported.
Closed-form ridge, lambda on a held-out train shard: px8 TEACHER, 500 holdout boards — cell accuracy 0.672 vs
per-board majority 0.698; interior 0.755, boundary 0.438; components 1-4 cells 0.301, 5-55 0.440, >55 0.703.
Reading: a linear read of the parent's px8 tokens recovers colour about as well as "say the background" and misses
most small objects. px16 teacher and the shipped px16 student are running through the same probe; px8 student after
training. This is the tokens' content, not what the MODEL reads; the readback measures that.

## Colour probe, px16 (CL2, 12:56; ridge, lambda 1e-6; 500 holdout boards; linear LOWER bound)
                                  all    majority  interior  boundary  comp1-4  comp5-55  comp>55
px8 teacher                      0.672   0.698     0.755     0.438     0.301    0.440     0.703
px16 teacher                     0.773   0.698     0.834     0.604     0.437    0.691     0.790
px16 student (shipped, cos .897) 0.770   0.698     0.844     0.563     0.377    0.611     0.795
Per game (px16 teacher/student/majority): cd82 .840/.845/.790 | m0r0 .572/.559/.458 | re86 .917/.909/.912 |
s5i5 .769/.792/.803 | sk48 .769/.745/.530.
Readings: (1) at px16 the parent carries colour beyond the background (+7.5 overall) but weakly for small things
(44% at 1-4 cells). (2) The shipped student keeps large-region colour (interior +1.0) and loses it at edges and small
objects (boundary -4.1, 1-4 cells -6.0, 5-55 -8.0): the first colour number for the student; the 0.897 cosine hid it.
(3) px8's parent is markedly weaker than px16's (-10.1 overall, below the majority baseline): whatever the px8 student
does, it copies a teacher carrying less colour. The readback (what the MODEL reads) is still the deciding measurement.
Queued (CL2): a 128x2 student (~1.4M params) on px8 targets, same recipe, on the 5090 after the main px8 run
(the investigator's "why 18M"), then all three px8 numbers through the same probe (~17:45).

## Colour probe, corrected split (CL2, 14:36; the investigator 14:31 "that's a generalisation")
The holdout-GAME score measures transfer of a readout fitted on 20 games to 5 others, not whether colour is in the
token. Same-games/unseen-boards split (every 10th train board held out; possibly optimistic — neighbouring frames can
be near-duplicates):
                      same games, unseen boards                 holdout games
                      all    maj    bound  c1-4   c5-55         all    c1-4
px16 teacher         0.890  0.671  0.853  0.872  0.854         0.773  0.437
px8 teacher          0.835  0.667  0.748  0.594  0.711         0.672  0.301
Reading: at px16 the parent DOES carry cell colour, small objects included (87% exact on 1-4-cell objects), when the
readout knows the game; the cross-game drop = the colour code is entangled with context (S0), which one fixed linear
readout can't undo. px8 carries less in both columns. Whether the MODEL's own reading undoes the entanglement is the
readback's question.
The investigator 14:34, "what you see as one colour isn't necessarily what Qwen calls it": px8 confusion — ~40% of errors are
grey-for-grey (#000000/#333333/#666666, 88 RGB apart; black->very dark grey alone 21% of holdout errors); the rest are
small bright objects swallowed by black (recall on holdout games: magenta .07, pink .04, red .15, yellow .18 vs black
.82). Exact-index grading overstates the blindness on greys and is right about small bright objects. The readback's
prompts give hex per index, so it tests whether the model separates the greys.
Lane 14:36: px8 shipped + arm built (e20cfb2e3e34); readback embeds server loading on the 6000; 128x2 student on the
5090 14:36-17:36.

## RESULT (CL2, 16:05; data/readback/report.json; 100 holdout boards, 20/game, seed 20261030; thinking off, temp 0; 1,500 requests, 0 HTTP errors)
                  full   region  point  bbox  ncol | full ΔE  full<=25  region<=25  point<=25
majority (bg)    0.702  0.570   0.243            |  12.2
native (PNG 16)  0.521  0.522   0.327  0.16  0.13 |  15.0    0.685     0.629       0.383
px16 student     0.559  0.532   0.333  0.12  0.08 |  14.3    0.680     0.635       0.423
px8 student      0.519  0.530   0.363  0.22  0.05 |  15.5    0.640     0.624       0.460
text (by eye)    0.810  0.558   0.377  0.23  0.29 |   5.5    0.854     0.660       0.520
none             0.006  0.016   0.210  0.03  0.00 |  83.5    0.014     0.033       0.397
Readings against the prior: (1) the NATIVE tower reads boards at cell level WORSE than "paint it all background"
(0.521 vs 0.702); the students match it (0.559 / 0.519): the students are faithful, the parent's channel is the
limit. The prior's "(a) and (b) above (e) on region/bbox" holds (0.52 vs 0.02 region) — the channel carries
something, and the something is not cell colour. (2) The exact TEXT board read by eye is the ceiling (0.810) and is
itself weak below board level (region 0.558, point 0.377): no counting into a 64-char line. In play the model indexes
current_frame.rows in Python, which is exact; this readback measures tool-free perception, the image channel's whole
job. (3) px8 ≈ px16: the geometry did not matter. (4) The prior's "(b) ≈ (a)" holds; "(a) ≫ (b)" does not.
ΔE2000<=25 merges applied: Ww 11.1, WS 21.9, wg 14.1, wS 18.9, gG 19.5, gS 23.7, Gc 17.4, cB 13.4, MP 13.3, Mp 16.8,
Pp 21.8, RO 21.6, bS 23.9.
Serving-side geometry gate (px8): status 200, n_tokens 256, payload b64 1,749,732 (px16 1024 / 6,992,612). Native
KV pool 1,440,080.
Process: chain_readback.sh stopped 15:33 on a disk-gate race (docker stop returns before --rm frees ~19.5 GB);
native ran from chain_native_then_ple.sh with waiting gates.
Also (CL2, the investigator's "measure it"): today's harness traffic (4 control runs x 25 games, 32.1M tokens) touches 10.9% of
the PLE table's rows (11.2 GB); leave-one-game-out coverage 90.3% mean (min 82.6% tr87). October's 0.4%/98.9% was an
artifact (that script truncated requests to 4,096 tokens). Output test running.
