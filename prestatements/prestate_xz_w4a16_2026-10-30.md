# Pre-statement: v36 with xz's public W4A16 checkpoint (Kaggle arm XZ), 2026-10-30

Written BEFORE the build is pushed; the numbers come after. Cody, 10-30 07:03 CDT: "just run v36 with his model if
you can" / 07:04 "just run it on kaggle - we don't have room here" (20 GB free on /, 181 GB needed; the local-first
rule, CLAUDE.md 10-25, is overridden by that instruction for this arm and nothing else).

## The one variable
The model weights. Anchor v36 (harness 8552964, all switches off) serves OUR checkpoint
`codywhatleymd/arc3-flashnext-nvfp4-ours-v22/PyTorch/v22/3` (RadixArk-lineage NVFP4 experts + FP8 attention, BF16 PLE
tables, 28 shards, 179.9 GB, served with `--quantization compressed-tensors`). This arm serves xz's public Kaggle Model
`xiaoz259/qwen3.8-flash-next-w4a16-intel-ple19/Transformers/default/1` (Intel/Qwen3.8-Flash-Next-W4A16-AutoRound:
INT4 g128 sym, AutoRound-tuned, experts only; linear_attn, self_attn, shared experts, gates, PLE, MTP, visual, lm_head
and embeddings kept BF16; 181.2 GB; the 102 GB PLE table resharded by xz into 19 files of <=7 tensors, byte-exact per
their RESHARD_REPORT.json; same architecture Qwen4ExpForConditionalGeneration, 48 layers, 512 experts, 1 MTP layer).
Same base model, a different quantization and a different shard layout; the two cannot be separated in this arm and
the arm does not claim to.

Everything else is the anchor: harness dataset codywhatleymd/arc3-synesthesia-harness at 85529646 (reused, not
rebuilt), tower and runtime datasets, 9,300 s budget, MTP-3, fp8 KV, max_num_seqs 14, gdn triton kernel, the
served-model label (a string the anchor bakes; cosmetic). Mechanism: the rendered setup script already honours two
environment overrides, `ARM_MODEL_DIR` (the model path) and `ARM_QUANTIZATION` (the `--quantization` flag; '' = no
flag), so the harness is NOT changed. The notebook builder gains `--model-source` (attach + check xz's model instead
of ours); the arm passes `ARM_MODEL_DIR=/kaggle/input/models/xiaoz259/qwen3.8-flash-next-w4a16-intel-ple19/transformers/default/1`
and `ARM_QUANTIZATION=inc`.

Why `inc`: vLLM 0.31.0 (the runtime) has no `auto-round` quantization method; its INCConfig
(vllm/model_executor/layers/quantization/inc/inc.py, read 10-30) overrides quant_method "auto-round" to "inc"
unconditionally and handles packing_format auto_round:auto_gptq (int4, marlin/gptq schemes, MoE via
get_moe_method, extra_config bits>=16 modules left unquantized, min capability 60). The anchor passes the method
explicitly so a mismatch fails at startup (kaggle.py:68-72); `inc` is the explicit name of the path vLLM would pick.
AutoGPTQConfig is NOT usable as-is: it requires `desc_act`, which xz's quantization_config lacks (checked).

## Platform and comparators
Kaggle commit run on the RTX PRO 6000 tier (not a submission; no daily slot used). Comparators on the same platform:
the v36 commit run (47.37) and the all-off control pool C1-C7 (12a000d; mean 39.06, sd 5.07, range 32.57-45.95).
Pre-stated reads, in order, before any score is looked at:
1. Gates: 0 tracebacks, 0 HTTP 400, ARM banner "XZ W4A16", `synesthesia: model /kaggle/input/models/xiaoz259/...`
   with 36 shard files (17 main + 19 PLE; the index names them), vLLM up (server log says INCConfig / inc), 25 games
   played, full clock.
2. Load time: seconds from notebook start to "vllm up" against the anchor's run (xz's reshard is a loading claim).
3. Score: mean over 25 games vs 47.37 and vs the pool; one run each, so NOT RESOLVED is the expected verdict;
   "not worse than the pool" is the screen. Levels per game beside the score (predictor note).
4. Throughput: tokens/s and actions, since INT4 marlin vs NVFP4 kernels on sm_120 is a speed question too and the
   play clock is fixed.

## Prior (Sakshi, before the run)
Direction unknown; I would not bet. For: AutoRound keeps 99.6% of BF16 on standard evals (Intel's card), INT4 g128
is a well-trodden kernel path, xz is 3rd on the public board with this checkpoint (under their own harness, which
we have not seen). Against: NVFP4 g16 with FP8 scales is finer-grained than INT4 g128; BF16 attention/shared
experts cost VRAM, so the KV pool shrinks under the same 0.98 utilisation and max_num_seqs 14 may queue; the
first run of an unfamiliar kernel path on sm_120 fails in ways a second run fixes. If it loads and plays, the
paper's section 6 gains a public W4A16 comparator; if it does not load, the failure line is the finding.

## What this arm is not
Not a hidden-set submission (3 slots left; a slot goes to it only if the screen passes and Cody says so). Not a
claim about xz's method: their harness, prompts and clock are theirs; only the weights are borrowed, under the
Qwen community licence they carry.

## Amendment 1 (10-30 07:20 CDT, before v2): a second, enabling change, and v1 withdrawn
v1 (kernel version 1, run 363849435, pushed 07:08) was cancelled at ~100 s on Kas's read of the runtime: the PLE
embedding method (overlay vllm/models/qwen4_exp/common/ngram_embedding.py, from_quant_config) accepts only
CompressedTensors, ModelOpt, Fp8 or no quant config and raises NotImplementedError for INCConfig, so the arm as
first built would have died at model init. v1 produced no score and is not a data point.

Second stated change, enabling only: a hash-pinned post-install runtime patch (scripts/runtime_0310/patch_ple_inc.py,
Kas; the patch_kv_copy_chunked.py pattern, applied by the setup script from harness/arc3_tools) adding an INC
branch that returns the unquantized PLE embedding method. PLE is BF16 in xz's checkpoint ("ple" is in Intel's
ignore list), so the branch changes nothing about the weights it loads; on our checkpoint (CompressedTensors) the
branch is never taken. Because it lives in harness/arc3_tools, v2 builds from a NEW harness commit on its own
dataset slug; the harness commit is 2e1af90 (Kas, 10-30 07:2x: patch_ple_inc.py in scripts/runtime_0310 and harness/arc3_tools, hash-pinned 8f5a8d02 -> 70f3e775, wired into the install hook after the KV-copy patch, fail-closed; tested on the real extracted runtime with a real INCConfig). v2 = kernel version 2 of arc-agi-3-synesthesia-xz-w4a16-k1, harness dataset codywhatleymd/arc3-synesthesia-harness-xz @ 2e1af90, pushed 07:28 CDT.

Not changed, on purpose: the watchdog's shard prefetcher treats every shard not named `ple-*` as a GPU shard
(PLE_SHARD_NAME_PREFIX, startswith). Our v22 PLE shards are named `model-ple-NNNNN-of-00022` and xz's
`model-ple-NNNNN-of-00019`, so on BOTH checkpoints the PLE files are prefetched the same way (the Gc run's
vllm-shard-prefetch.json lists all 22 of ours under gpu_shards; prefetch finished at 57 s). Fixing the prefix
would alter the control's load path, so it is left for a separate, pre-stated v36 load-time look.

Also from Kas's read, folded into the reads: which MoE kernel INC picks (Marlin AutoGPTQMoEMethod vs Triton
MoeWNA16; the server log says), and the "GPU KV cache size" line, since attention, linear_attn, shared experts and
the MTP head are BF16 here and will leave a smaller pool than v36's under the same 0.98 utilisation.
