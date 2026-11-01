# Pre-statement: dfc7, the Monday DFlash combination (2026-11-01 ~09:40 CST, kasoti)

What: candidate_pinned's exact notebook (pool clock 1500/600, start retry, boot clock, ARM_PINNED_ROUND_MB=1024) on
harness branch candidate-dflash 42bae15, plus dfr7 v2's DFlash switches (stock incoai drafter, ARM_MTP_TOKENS=7,
ARM_QSA_RING_FIT=1, ARM_DFLASH_SW_RETAIN=1, draft group, KV group log, Triton drafter attention) and the drafter
dataset; commit run, 9,300 s budget like candidate_pinned. It replaces dfr7 v2 (built on the dflash-cache branch,
which tests DFlash's parts but not the combination the Monday notebook would submit; Sakshi's point, 09:29).
Notebook diff vs staged candidate_pinned: names, harness dataset/commit, the DFlash switches, the extra dataset,
and cell 2's tool check gaining patch_ple_inc.py (present in 42bae15).

Pass (all must hold):
1. Candidate cut (33445ff): 0 tracebacks, 0 server 500s, ends itself, switch lines printed (pool clock, time stop,
   start retry, pinned, boot clock, and the DFlash lines: model path resolved, SW retain installed, ring fit installed,
   7 speculative tokens), all 25 games played.
2. No collapse: prefix-cache hit rate in every 5-min window from minute 10 on within 10 points of its first window,
   and of candidate_pinned's (from its vllm-openai-server.log).
3. Throughput: generated tokens/s (job wallclock) >= candidate_pinned's 833.6.
Score is reported, not gated: one public-25 run sits in a 32.6-54.7 spread (n=12).
Fail on 1 = do not submit; fail on 2 or 3 = DFlash does not beat MTP on this stack, Monday stays candidate_pinned-line MTP.

Amendment 1 (09:46 CST, before dfc7 ran): the drafter is the TUNED one (drafter-tune result 0a17b74: best lr 1e-4
epoch 5; paired on 13,518 held-out blocks +0.047 at 3 drafts, +0.143 at 7 drafts over stock), exported in incoai's
serving layout and uploaded as private dataset codywhatleymd/arc3-flashnext-dflash2-ours-tuned-k1 (4 files,
model.safetensors 1,206,140,040 B, SHA256SUMS verified before upload). Only ARM_DFLASH_MODEL and the extra dataset
change; the criteria above are unchanged. dfr3 (stock drafter, K=3, retention, dflash-cache branch) is the parts test.
