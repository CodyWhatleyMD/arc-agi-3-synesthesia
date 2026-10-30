# Pre-statement: our own W4A16 AutoRound quant of Qwen3.8-Flash-Next, 2026-10-30

Cody, 10-30 08:07-08:08 CDT: "or if we requantized.." / "well we're not tuning anything else" (the 6000 is idle while
the XZ arm runs on Kaggle). Started before the XZ arm (v2) has reported, as the artifact that would be OURS if v2
shows xz's INT4 running faster or scoring higher than our NVFP4 in our harness.

## Recipe: Intel's, verbatim from the model card of Intel/Qwen3.8-Flash-Next-W4A16-AutoRound
auto-round --model <BF16 base> --scheme W4A16 --iters 200 \
  --ignore_layers lm_head,embed_tokens,visual,linear_attn,self_attn,hyper_connection,mlp.gate,shared_expert,in_proj_a,in_proj_b,ple,mtp,indexer \
  --device_map auto --format auto_round --output_dir <out>
INT4 g128 symmetric on the routed experts only; everything named in --ignore_layers stays BF16 (that is why the
output is ~181 GB with a ~102 GB BF16 PLE table). Intel's card: 99.64% of BF16 on GSM8K/MMLU/PIQA/HellaSwag average.

## Amendment 1 (08:12, before launch): OUR calibration, not pile-10k
Cody (to Kas): "that's not our specialized trained quant". What made v2/v22 ours was never a different base; it was
the calibration: calib_v2.jsonl, 976 chat-templated 4,096-token windows of real harness requests
(/media/ignaz/claude-extra/flashnext_calib_v2/calib_v2.jsonl, rows {"text","src_len","start"}). Intel's card command
names no dataset, so AutoRound would tune on its default (pile-10k). Ours = Intel's command + `--dataset <calib_v2.jsonl>
--seqlen 4096 --nsamples 976`, no chat-template flag (rows are already templated). The source stays the BF16 base
(requantizing our NVFP4 would stack two 4-bit errors). MTP stays BF16 as in Intel's ignore list for this first cut
(AutoRound-on-MTP is untested; v2.1's lesson that a BF16 MTP head shrinks the KV pool is noted, and v2's pool of
1,380,332 tokens played fine). So this quant differs from xz's in exactly one input: the calibration data.

## Inputs and tools (Kas, 08:10)
- Base: /media/ignaz/model-storage-1/Qwen3.8-Flash-Next (BF16, 131 shards, 360.0 GB = index total_size, 1,658
  tensors, mtp.* and visual.* present; headers checked against file sizes; NOT sha256-checked against HF).
- Tool: auto-round 0.16.1 in a COPY of /home/ignaz/quant-venv (which has 0.15.1 and is also our llm-compressor
  NVFP4 path, so it is not upgraded in place). Kas's 10-06 survey: Flash-Next ❌ on 0.15 ("group_size issue"), ✓ on
  0.16; Intel's own checkpoint says autoround_version 0.15.0; the release notes are to be read if 0.16 fails.
- Output: /mnt/data/arc3_local_model/ours-w4a16-autoround (the only disk with room: 617 GB free).
- GPUs: the 6000 (96 GB) + the 5090 (32 GB) under device_map auto; Intel's doc run was one H200 (~100 GB VRAM,
  ~120 GB RAM, ~9 h), so expect spill and longer here. Nothing else runs on the cards while it does.

## What counts, in order
1. It finishes: config.json with quantization_config quant_method auto-round / packing auto_round:auto_gptq, an
   index naming every shard, all shards present, extra_config listing the ignored modules at 16 bits.
2. It loads on our runtime the way xz's does: ARM_QUANTIZATION=inc + Kas's patch_ple_inc; the PLE table BF16.
3. Fidelity vs our NVFP4 v2.2: the same reference-agreement protocol (fidelity_512_chain.sh) if time allows,
   reported with its n; otherwise the play comparison only.
4. A Kaggle run under the v36 harness, pre-stated as its own arm, against the control pool and against v2 (xz's
   checkpoint): the one-variable pair xz-W4A16 vs ours-W4A16 isolates the quantization run from the weights' owner.

## Not claimed
That W4A16 is better than NVFP4; that is what v2 and the pair in (4) measure. The requant exists so that if it is,
the thing we ship is ours.

## Launch log (10-30, before any result)
- 08:12 attempt 1 (two cards, defaults): AutoProcessor failed (Qwen3VLVideoProcessor needs torchvision), then
  auto-round's CPU-load fallback hit its own bug (mllm_load_model given a model object). Fix: torchvision 0.28.0+cu130
  installed in the venv copy (--no-deps; torch unchanged).
- 08:15 attempt 2 (two cards): model loaded via the meta skeleton, calibration ran, block 0 started, then
  auto-round's two-card block allocator raised ZeroDivisionError (a parameterless layer sized at 0 in
  utils/device.py find_best_device). Patched in the venv COPY only: divide by max(estimated_memory, 1e-9).
- 08:20 attempt 3 (6000 alone): CUDA OOM in block 0's grouped-expert forward (94.6 GB used): the cached calibration
  inputs/outputs (976 x 4,096 tokens) on the card.
- 08:33 attempt 4 (two cards, --batch_size 4 --low_gpu_mem_usage): OOM on the 5090 (31 GB) in a compiled kernel.
- 08:44 attempt 5 (two cards, --batch_size 1 --low_gpu_mem_usage): running; log
  /mnt/data/arc3_local_model/logs/requant_w4a16_1030_08*.log (newest). Cody asked for the two-card fix rather than
  a single card.
Time estimate given to Cody at 08:32: 30-40 h at our calibration size (Intel's 9 h on an H200 was at 128 x 2,048);
Cody's standing rule (No half-measures) keeps every window; finishing Saturday night/Sunday.

## Amendment 2 (08:50, block 0 running): what attempt 5 actually tunes on (Kas's read of the parser and the log)
- Effective batch: --batch_size 1, so each of the 200 signSGD steps per block sees ONE 4,096-token window (200 windows
  per block), where Intel's default is batch 8 (1,600 per block). gradient_accumulate_steps is config-only in
  0.16.1 (no CLI flag); effective batch 8 at batch 1 would cost ~8x the tuning compute per block, which the Monday
  deadline rules out, and --seqlen 2048 at batch 4 would halve our windows, which the No-half-measures rule rules out.
  So this quant is Intel's quantization recipe with OUR calibration data and a SMALLER tuning batch than Intel's;
  "Intel's recipe" is true of the scheme, the ignore list and the iteration count, not of the tuning batch. Named here
  so no later sentence calls it a reproduction of Intel's tuning.
- Samples: AutoRound's length filter at seqlen 4,096 kept 873 of the 976 windows ("Insufficient number of samples:
  required 976, but only 873", 08:45:37). nsamples is recorded as 873.
- Host RAM during the run: process RSS ~125 GB, ~53 GB available, 20 GB swap in use (Kas, 08:47). No Open Brain
  captures (ollama loads 17-25 GB), no transcript walks, no heavy local python until it finishes; the 10-28 memory
  guard killed jobs at 3 GB free.
