# Pre-statement: fine-tuning the DFlash2 drafter on our v22 quant (2026-11-01 ~07:45 CST, drafter-tune lane, kasoti fork)

Goal (coordinator, 07:2x): a tuned DFlash drafter in a TESTED, submittable notebook for Monday's slot (window closes
Mon 17:59 CST). Cause addressed: the stock incoai drafter was trained against Qwen's FP8 Flash-Next; on our NVFP4 quant
and our prompts its served mean acceptance length was 2.37-2.70 (l4..l9) vs MTP's 2.73-2.83, with the same 3 drafts.

Data: our own request logs (Kaggle runs since 10-26 on the v22 quant; the xz W4A16 run excluded), replayed WITH their
board embeds through our runtime in extract_hidden_states mode (branch drafter-extract 4fda488): per request, the last
4,096 prompt positions' features = the 5 tensors our DFlash path feeds the drafter (streams entering layers
6,16,26,36,46) + the lm_head input (teacher). Loss on assistant-turn tokens (our quant's own reasoning/tool calls).
Held-out GAMES for validation (no request from them in training): ls20, tn36, sp80, vc33.
Training: speculators (live main 07b4fcf) dflash2, from incoai's weights, block size 8 kept (so a raised draft cap
can use it), verifier_norm = identity (Qwen4Exp's lm_head input is already normalized by the final mixer).

Readings, fixed now:
1. Pipeline sanity (before training): the STOCK drafter's offline accepted length on held-out windows, at 3 drafts,
   should land within 0.5 of its served 2.37-2.70. If not, the features or the metric are wrong: stop and fix, no
   training conclusions drawn.
2. Offline, held-out games, 3 drafts (accepted length incl. the verified anchor, realized selector path):
   tuned - stock >= +0.30 AND tuned >= 3.00 -> proceed to serving. tuned - stock <= +0.10 -> tuning does not help
   here: stop the lane and say so. Between: one more training round if time allows, else stop.
   Also reported at block size 8 (7 drafts), for the draft-cap question.
3. Served (local smoke on the 6000, same notebook config as the DFlash runs plus whatever cache fix lands, 25 min of
   play, 5-min windows): mean acceptance length >= 3.00 and >= stock + 0.30, AND generation throughput >= the MTP
   controls' in the same windows (r2/r6). Throughput below MTP = not submittable, whatever the acceptance.
4. Kaggle commit run: the candidate's cut (notes/prestate_candidate_2026-11-01.md: no traceback/500, ends itself,
   25/25 games played, mean >= 32.6) AND generation tokens/s >= 90% of the MTP runs' (754-866).
Invalid if: training or validation windows share a game with held-out games; extraction ran with prefix caching on.

## Result (2026-11-01 09:45 CST, drafter-tune lane)

Data: 700 usable replayed requests (dx5; 639 train / 61 val, held-out games ls20 sp80 tn36 vc33), 2.87M tokens, 797k
assistant-token loss positions; 18 requests not reconstructable and 18 over the 147,072-token context (HTTP 400) excluded.
Features validated: [4096,6,2560] bf16 finite; lm_head(teacher) reproduces our quant's own sampled tokens 87-95%.
Instrument: validation pass 1 with anchors seeded (identical 13,518 blocks for every checkpoint), realized selector path
(eal) and the sampled-acceptance proxy at T=0.6 (esl = 1 + sum of cumulative p_target(draft)), at 3 and 7 drafts.

| checkpoint | eal_d3 | eal_d7 | esl_d3 | esl_d7 |
|---|---|---|---|---|
| stock (incoai) | 3.146 | 4.490 | 3.086 | 4.384 |
| lr 1e-4 epoch 5 (best) | 3.193 (+0.047) | 4.633 (+0.143) | 3.127 (+0.041) | 4.518 (+0.134) |
| lr 1e-4 epoch 14 | 3.190 (+0.044) | 4.638 (+0.147) | 3.126 | 4.523 |
| lr 3e-4 epoch 2 / 14 | 3.154 / 3.123 | 4.560 / 4.519 | 3.095 / 3.069 | 4.455 / 4.428 |
(mid read, 227 train samples, separate val set: best +0.011 at d3 / +0.075 at d7; lr 1e-3 about -0.17 at d3.)

Reading 1 (pipeline sanity): PASS (stock offline 3.05-3.16 vs served 2.37-2.70; offline greedy overstates sampling).
Reading 2: tuned - stock = +0.047 at 3 drafts <= +0.10 -> STOP, as pre-stated: tuning the drafter on our quant's own data
does not buy acceptance at the served 3 drafts. At 7 drafts it buys +0.14 accepted tokens per step (+3.2%), relevant
only if a K=7 serving configuration (dfr7) wins on its own. Readings 3-4 not run (the stop applies first).
What it says about the cause: the stock drafter is already well matched to our NVFP4 quant (first-draft accuracy ~0.86 on
held-out games); the served DFlash deficit is not a drafter-tuning problem at 3 drafts. Gain grows slowly with data
(+0.011 -> +0.047 at d3 from 227 -> 639 samples), so +0.30 would need far more data than exists before Monday.
Best checkpoint exported to the serving layout (incoai config + tuned 81 tensors): /mnt/data/drafter_tune/export_full_lr1e-4_ep5
(not uploaded). Runs: /mnt/data/drafter_tune/runs/ (sweep_full.out, eval_full.out, fe_*.log).
