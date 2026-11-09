# Result: v36 harness with xz's W4A16 checkpoint, Kaggle commit run (arm XZ, v2), 2026-10-30

Pre-statement: notes/prestate_xz_w4a16_2026-10-30.md (4cc799f, amendments b96a3f3, cd4e02d). Kernel
codywhatleymd/arc-agi-3-synesthesia-xz-w4a16-k1 version 2 (run 363855849), harness 2e1af90 on dataset
arc3-synesthesia-harness-xz, ARM_MODEL_DIR = xz's mount, ARM_QUANTIZATION=inc. Started 07:28 CDT, COMPLETE ~09:50.
Outputs: ~/kaggle_local/kaggle_runs/XZ_xz-w4a16-k1_363855849/ (stdout.log, console log, synesthesia/benchmark.json).

## Gates (read before the score)
0 tracebacks, 0 HTTP 400, ARM banner present, model line "35 shard files, 181.2 GB, 224,280 tensors", 25 games
played, duration 2h 10m 38s (= the controls' clock), QUANTIZATION=inc echoed by the setup, GPU KV cache size
1,380,332 tokens (controls 1,501,360; -8%, the BF16 attention/shared experts), maximum concurrency 9.39x.
MoE kernel (CL2, 10:22, from the vLLM server log at /mnt/data/kaggle_runs_kas/xz_w4a16_k1_v2/vllm-openai-server.log):
"Using 'MARLIN' WNA16 MoE backend" (MarlinExperts) for the 4-bit experts; the PLE embedding initialised as
Qwen4ExpPLEUnquantizedEmbeddingMethod (CL2's patch fired); the BF16 MTP experts resolved to the FlashInfer CUTLASS
unquantized MoE backend. So the ~5% slower token rate is Marlin, not the Triton fallback.
Correction to an earlier sentence here: the server log WAS in the run's output; `kaggle kernels output` pages at 20
files by default and the 210-file output hid the root-level vllm-* files. A "file absent" read from that command
without --page-size 200 is not trustworthy (fetch: --file-pattern 'vllm.*|.*\.log$|taaf_setup_env.json' --page-size 200).

## Load time
KV-cache line at 604.7 s after start (rooms 950/1,027 s; control C7 663 s). Faster, one run.

## Score, pre-stated comparator (compare_arm_groups.py, paired by game, 95% bootstrap, JSON beside this note)
XZ 45.49 vs the Kaggle control pool C1-C7 39.06 (sd 5.07, range 32.57-45.95):
  score  delta +6.43  95% CI [-2.38, +15.72]  sign 17/8/0  p=0.108  NOT RESOLVED (n=1 vs 7)
  levels 4.48 vs 4.11  delta +0.37  95% CI [-0.19, +0.93]  sign 15/9/1  p=0.307  NOT RESOLVED
Against the v36 commit run (47.37, n=1): below it. Screen "not worse than the pool": passes.

## Throughput (the "faster machine" question)
generated tokens/sec 724 vs controls 746-785 (rooms 749/786): ~5% SLOWER per token under INC in our harness.
Actions 6,924 vs controls 6,653-8,489. So in our harness xz's checkpoint is not faster; the speed in their team
name is not in the weights, or not under vLLM 0.31's INC path on this card.

## Reading
One run. The point estimate sits 1.3 sd above the pool mean and inside the pool's range; the interval covers zero.
It does not reproduce xz's 58.59 or any part of the gap between us and them that could be attributed to weights:
same weights, our harness, 45.49. The gap is the harness and clock, as pre-stated as possible. Hidden slot: not
earned by this screen alone (3 slots left; the investigator's call); replicates of the same arm would cost 2.2 h of quota each.
