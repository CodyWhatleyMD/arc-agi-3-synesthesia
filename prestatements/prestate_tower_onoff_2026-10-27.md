# Pre-statement: the board tower on/off, replicated locally (written 2026-10-27 ~10:00 CDT, before any run)

Cody's ruling (10-27 09:21, recorded in notes/paper_draft_v3_changelog_2026-10-26.md): findings 214d (one no-image run,
34.86, against two image runs, 43.86 / 35.21, in the v2.2 harness on 10-14) is one test, not a finding and not an
acceptance of the null. This replicates it in the harness we ship, with replicates, on the local 6000, before Nov 9.

## Arms
- **ON (control):** the v8 anchor notebook, staged sha f9af78d9 (builder default build of 8552964), MULTIMODAL_CONTEXT
  = current_grid, ARM_B_STUDENT_TOWER=1: every user turn carries the board as a 1,024-token image_embeds part from the
  18.2M board tower. Already run: r2, r3, r4 (9,300 s job budget, all 25 games started, valid under the Batch A gates).
  n=3. No new ON runs unless the OFF arm's spread demands a fourth pair.
- **OFF (treatment):** the same notebook built with `--board-channel off`: MULTIMODAL_CONTEXT=none, nothing else
  changed. The harness then sends no board part on any turn and drops MULTIMODAL_CONTEXT_ADDENDUM from the system
  prompt (tool_agent.py:264-265); the board reaches the model only through its Python tool. This is exactly 214d's
  configuration. The start assertion and the end evidence gate are flipped for this arm: it must PROVE that zero
  image_embeds parts were sent (board_parts.jsonl has none), as the ON arm must prove ≥1. Tags bo1, bo2, bo3; 9,300 s
  each; GPU 1; run_synesthesia.sh (anchor dataset binding); disk-gated chain (15 GB to start, 3 GB to stop).
- Same model (v22/3), same runtime, same budget, same concurrency, same local hardware. Local vs local only; nothing
  here is compared with a Kaggle number.

## Primary outcome
Mean public-25 score, OFF (n=3) minus ON (n=3), by scripts/compare_arm_groups.py: paired-by-game bootstrap 95% CI on
the group means. Resolved if the CI excludes 0 in either direction; otherwise NOT RESOLVED and reported at n with the
interval. Both tails are read: a tower that helps shows as OFF losing; a tower that costs (84 MB per request, ~8% of
request latency, notes/payload_cost_2026-10-26.md) shows as OFF gaining.

## Secondary outcomes (reported, not deciding)
- Levels completed, same test.
- Actions per job-second (throughput), same test. Prediction: OFF is faster per turn (214d measured 919 vs 785 tok/s).
- Per-game: the stable top four (lp85, ar25, ft09, cd82) and the stable bottom five (bp35, lf52, sk48, wa30, ls20)
  from the 10-26 three-run table; the coin-flip middle is exploratory only.

## My prior (stated so it can be wrong)
NOT RESOLVED at n=3 vs 3: |delta| < 5, interval ≈ ±8 (the 10-26 identical-run spread). If anything resolves, I expect
OFF to be slightly faster and no better. A resolved OFF < ON by more than 5 would be the first evidence in the shipped
harness that the tower is read at all.

## Invalid-run criteria (decided before scores are read; same as the Batch A pre-statement + clarifications 1-2)
Any harness traceback outside a 'sandbox ... stderr follows:' block; any HTTP 400; disk reaching < 3 GB during the
run; the ARM banner or the board-channel check missing from the log; the flipped evidence gate failing (an OFF run
that sent any board part is not the OFF arm); fewer than 25 games started; the job budget not 9,300 s. An invalid run
is replaced, not patched.

## What this does not test
The student tower vs the native vision tower (pixels); that is the F208b question and needs a PNG arm on the same
harness, not built here. It does not test the hidden set. It does not speak to Batch A.
