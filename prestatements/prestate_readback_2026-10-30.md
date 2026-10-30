# Pre-statement: what does Flash-Next read through the board channel? (2026-10-30 12:50 CDT, Sakshi; Cody's questions via Kas 12:44)

## Why this exists
Per-token cosine to the teacher is ~97% a shared position vector (S0: 16 centre tokens of a solid board 0.982 alike;
colour 2-5% of energy; same colour centre vs corner cos 0.04). So the student fidelity numbers — px16 0.897, px4 0.651,
px8 tonight — are POSITION scores and say nothing about colour. Whether the MODEL reads boards through the channel has
one data point (a 3-block synthetic board, 10-05). The play reads are all unresolved. Cody, 12:44: "What is the model
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
Also run: the linear colour probe on the teacher's and students' tokens (Kas, 5090, scripts/board_tower/colour_probe.py)
as the lower bound on colour RECOVERABLE from the tokens, interior vs boundary, by component size, per colour.

## Prior (before any number)
(d) text is the ceiling on cell accuracy for this model. (a) and (b) are above (e) on region/bbox but below (d) on cells;
(b) ≈ (a) (consistent with native +2.07 unresolved). Colour at flat interiors near chance for (a)-(c); edges and small
objects above chance. If (a)-(c) are all near (e): the eye is not reading colour, px8's geometry cannot matter, and the
lever is a readback-trained student (ground-truth questions with the frozen model in the loss + a distillation term to
stay in-vocabulary) — post-deadline. If (a) ≫ (b): the student lost colour the cosine never saw; retrain with a colour
term. If (b) ≈ (a) ≈ (d) on region/bbox: the channel reads layout; keep it; px8's play decides cost.

## What this does NOT decide
A hidden slot (Cody's), the requant (parked), the paper's final config.
