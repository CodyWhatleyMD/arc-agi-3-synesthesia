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

## Clarification 1 (10:50 CDT, before the relaunch; bo1 produced no score)
- bo1 (09:55) died at cell 10's flipped assertion five minutes in: the harness dataset's setup_commands.json froze
  `'MULTIMODAL_CONTEXT': 'current_grid'` as a literal, and cell 7 re-applies that setup env over os.environ after the
  arm's switch is set (Kas's read, confirmed in the log: line 65 printed env MULTIMODAL_CONTEXT=none, line 1175 the
  assertion). The guard did its job; nothing was scored. bo1 is invalid and its tag is retired.
- The OFF arm's harness is now 8552964 plus ONE inert change (branch syn/env-multimodal-context): setup_commands.json
  reads `os.environ.get('MULTIMODAL_CONTEXT', 'current_grid')` the way it already reads ARM_UPSCALE, and the template
  line in kaggle.py that rendered the literal renders that lookup. With the variable unset it evaluates to
  'current_grid': the ON controls (r2, r3, r4, run on 8552964 itself) are unaffected in behaviour, and the ON arm of
  this harness would be byte-identical in effect. It is built into its own dataset (arc3-synesthesia-harness-off),
  never the anchor's.
- "The channel" includes the system prompt's MULTIMODAL_CONTEXT_ADDENDUM (tool_agent.py:264-265), which the OFF arm
  drops. The arm therefore measures the board part AND its prompt section together, as 214d did.
- Belt and braces for the negative gate (Kas): after each OFF run, the saved request logs are checked for zero image
  parts of any kind; an OFF run whose requests carry a board part is invalid.
- Tags for the relaunch: bo1b, bo2b, bo3b.

## Clarification 2 (15:02 CDT, before any OFF score or slope is read): score-rate as an exploratory outcome
Cody, on the v36 curve (mean score vs minutes, near-linear ~0.43/min until the budget bites, then flat): the slope
may be a better number than the endpoint. Pre-stated as EXPLORATORY (the primary outcome is unchanged):
- Score-rate = OLS slope of "mean score" against minutes-since-notebook-start over the periodic summaries from the
  first summary up to and including the last summary at or before 120 min (the v36 knee; fixed here so it is not
  picked per run). Also reported: mean score at the summary nearest 60, 90 and 120 min.
- Computed identically for every run in the comparison (r2, r3, r4, bo1b, bo2b, bo3b), from their own logs;
  same bootstrap-by-game machinery does not apply (one slope per run), so OFF-vs-ON slopes are reported as
  group means with the run-level spread, n=3 vs 3, no significance claim.
- Reading: a faster OFF slope with an equal endpoint means the channel's cost is time, not score; a slower OFF slope
  means the board part buys progress per minute. Both tails named now.
- Not yet computed for any run as of this clarification.
- AMENDMENT (15:14 CDT, still before any OFF slope): the axis is PLAY time, not notebook time. Every run writes its
  periodic summary every 600 s of benchmark time (periodic_save_interval_s = 600; v36's first summary is 604 s after
  its benchmark start, and locally the model loads faster, so notebook-minutes are not comparable). Summary k is at
  10k play-minutes. The slope window is the first TEN summaries (play minutes 10-100; v36's knee at 120
  notebook-minutes is ~100 play-minutes). The 60/90/120 checkpoints become the summaries at 60, 90 and 100
  play-minutes. Same window for every run, ON and OFF.
- CONTROLS READ (15:16 CDT; no OFF score or slope read yet). Slope over summaries 1-10 (play min 10-100):
  r2 0.352, r3 0.416, r4 0.427 pts/min (mean 0.398; spread 0.075); v36 (Kaggle, same config, for reference only,
  never pooled) 0.419. Scores at 60/90/100 play-min: r2 21.1/34.2/37.8, r3 21.8/38.2/40.1, r4 29.0/35.9/38.4;
  v36 24.4/35.5/41.5. All four curves are near-linear to 100 play-min and bend after, so the window is confirmed on
  both platforms. The 40.2-47.4 endpoint spread comes mostly from the last three summaries (the budget tail).
