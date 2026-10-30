# Pre-statement: the px8 student tower (256 tokens per board), 2026-10-30 11:25 CDT (Sakshi)

Cody, 11:16: "Lets do it - we've got nothing to lose." His question that led here: "what is the smallest unit on the
boards where a single color appears?" — the cell; game logic moves in 4- or 8-cell steps (dossier); only the 1-cell
HUD meters live below. The shipped student is px16 (one token per 2x2 cell block, 1,024 tokens/board, 18.2M params,
held-out cosine 0.8972). A px4 student (8x8 blocks, 64 tokens) fit poorly: 0.651 vs the 0.595 board-blind floor
[F188]. px8 (4x4 blocks, 256 tokens) sits between and is untested.

## The one variable
Student geometry: px8 / 256 tokens per board, against the shipped px16 / 1,024. Everything else held: same teacher
(Flash-Next's own 449M tower, final post-merger output), same 8,914 boards and the same five holdout games
(cd82, m0r0, re86, s5i5, sk48), same student architecture (8 x 384, 6 heads, MLP 1,536, pos bias + rope),
same recipe as run_full.sh (dihedral augmentation as in ckpt_px16_dih; TRAIN_MINUTES=180, batch 8, lr 3e-4),
same harness commit as the anchor (8552964 / f9af78d9 lineage) with only the checkpoint and ARM_B_EXPECT_NPOS=256
changed. Consequence named, not a confound: the history budget is token-based, so at 256 tokens/board the model will
hold ~4x more boards in context than the anchor does. That is part of what "cheaper channel" means and is read as
such (boards per request is a pre-stated read below).

## Reads, in order, before any number is quoted
1. Fidelity: held-out per-token cosine to the teacher on the 500 eval boards and on the 5 holdout games, reported
   beside px16 (0.8972) and px4 (0.651) and the floor (0.595). No threshold is invented here; the number is reported
   and the next step is Cody's call with it in hand.
2. Serving gates: student loads, n_pos=256 accepted by assert_request_shapes/token_estimate (only 1,024 and 4,096 are
   verified today — Kas verifies 256 before the first request), 0 tracebacks, 0 HTTP 400, consumption gate PASS
   (scripts/consumption_gate.py).
3. Local public-25 vs the local controls r2/r3/r4/r6 (RTX PRO 6000, 9,300 s): score, levels, actions, tok/s,
   boards per request, by scripts/compare_arm_groups.py (paired-by-game 95% bootstrap). n=1 first; replicate if the
   first read is not worse.
4. Kaggle commit run vs the Kaggle pool C1-C7 (39.06, sd 5.07), same script.
5. A hidden slot only if 3 and 4 read "not worse" AND Cody says yes to that slot.

## Prior (written before any number)
Score: direction unknown. Throughput: up (4x fewer prefill tokens per board). Fidelity: between 0.651 and 0.8972;
if it lands near px4's, the arm stops at read 1 and the result is still reported.

## Disk and lane
Targets to /mnt/data/board_tower/targets_px8 (claude-extra has 27 GB free; px16's set is 44 GB, px8 ~11 GB).
/ is at 9 GB free, under the 15 GB gate for a local docker run: needs ~6 GB more before read 3 (Cody's call which
directory moves; ~/kaggle_local/kaggle_runs is 24 GB of downloaded Kaggle outputs and would move, not delete).
Kas builds; Sakshi reads (Fable week at 94%).

## Amendment 1 (11:22 CDT, from Kas's build report, before any number)
- Geometry: px8 only. px10 is NOT representable by the student (model.py:59-60 requires cell_patch to divide 64;
  400 tokens = 3.2 cells per token). Valid points are px32/16/8/4; px8 is the curve's missing interior point.
- Teacher: the default CK (claude-extra/Qwen3.8-Flash-Next-NVFP4-ours) has a stale index and cannot record; Kas
  used /mnt/data/arc3_local_model/v22. Same teacher by three checks: all 333 visual.* tensors byte-identical to the
  BF16 base; recorder sha 5c8207cd2237 = px16's manifest; 4 boards re-recorded at px16 match targets_px16 at
  cosine min 0.999996.
- Noise floor at px8 (teacher batch-1 vs batch-2): cosine min 0.946 / p05 0.991 / mean 0.998, vs 0.999998 at
  px16. Targets are batch 1 (unbiased); the floor caps how closely any px8 student can match and is reported
  beside the fidelity number when it is compared to px16's 0.897.
- Pipeline: base px8 set on the 5090 (~86 boards/s), then run_dih.sh PX=8 (dihedral copies on the 6000, 180 min
  train) -> /mnt/data/board_tower/ckpt_px8_dih. Script change: a PX knob (default 16) + CK passthrough.

## Amendment 2 (11:29 CDT, Kas's 11:50-stamped status; the clock in their note runs ahead of mine, recorded as sent)
- Targets: base 8,914 (8,414/500, holdout as px16) 10.9 GiB; dihedral +58,894 = 67,308 train, the same count as
  px16_dih. Training ~11:40 -> ~14:40 CDT on the 6000, 180 min. CKPT /mnt/data/board_tower/ckpt_px8_dih.
- Builder fd60e64: the anchor hard-codes 1024 beyond ARM_B_EXPECT_NPOS — cell 10's (1024, 2560) assertion and
  real-part price, cell 11's evidence gate (n_tokens == 1024 only; a px8 run would have read "no board sent").
  New options --tower-dataset/--tower-ckpt/--tower-ckpt-sha/--tower-npos rewrite exactly those lines. Payload at
  256 rows MEASURED 1,749,732 bytes (the method gives the anchor's 6,992,612 at 1024). Old vs new builder with no
  tower options: byte-identical outputs.
- Harness commit for the arm: 8552964 (the local controls' 85529646afc4), NOT HEAD (which carries the PLE patch).
- Tower dataset arc3-board-tower-px8 = armb's 68 files byte for byte + ckpt_px8_dih; serving code byte-identical;
  model.py takes cell_patch=4. Client shapes at 256 verified (grid [1,32,32]; estimator prices 256). Server
  acceptance is read from the local run's first request.
- Fidelity comes from train.py's final_eval (cos_mean/p05/min on 500 eval + per_game holdout) with the noise
  floor beside it, before any play.
- Lane: the 6000 is held until ~14:40; the requant (if restarted) waits or runs on the 5090 alone.
