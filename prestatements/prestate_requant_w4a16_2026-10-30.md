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
