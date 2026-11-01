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
