# ARC3 vLLM 0.31.0 runtime: validation, 2026-10-08

Shipped overlay: `arc3_vllm_v0310_arc3_overlay.tar.blob`, sha256
`4848d1892a1fb6ad8bc8adc3475077735318d68ce97bd918d0ba6baee956218b`, 28 files, on
`vllm/vllm-openai:v0.31.0` (amd64 `sha256:a4a4c043…`, commit db9527a46), image layers
8/20/21/24/27/31. The port is from Han Solo's overlay `e3a6fe0d` on e975732.

Build history, all recorded in `prior_overlays.json` so the installer upgrades in place:

| build | change | validated by |
|---|---|---|
| `9f3431a1` | first port, 25 files | §4–§6 serving runs, §8 first test pass |
| `38f69d3f` | `mamba_hybrid` getattr fix, found by §8 | §8 second test pass, §10 paired repeats |
| `393f83bc` | + `hyperconnection.py`, his GEMM dispatch kept on sm_120 (§7) | §9 final serve, §11 |
| `92e368ac` | + `v1/worker/utils.py`, KV copies in chunks of 4; single gather whenever a destination is also a source | runtime-0310's serves, §12 |
| `55da1fed` | `utils.py`: overlapping copies go first in one chunk, so the bound holds for them too | offline only |
| `4848d189` | + `model_executor/warmup/kernel_warmup.py`, shipped FlashInfer autotune tactics (§13) | §1–§3, §12, §13 |

`92e368ac` was preceded by `1901288d`, the same sources plus a leaked `__pycache__` member, which
the installer refused; the builder now packs `.py` sources only.

## 1. Port reproducibility

`port_overlay.py --check` regenerates all 28 overlay files byte for byte from his overlay tar
and vLLM's git history. It replays a 3-way merge per file plus the recorded resolutions and
adaptations, giving 11 keep, 13 port, 8 drop and 4 new: two files his changes moved into, and two
of ours, `v1/worker/utils.py` and `model_executor/warmup/kernel_warmup.py`. A drop is accepted only when the merge
equals v0.31.0 byte for byte. A keep is accepted only when v0.31.0's file equals e975732's.

## 2. Offline checks (`validate_runtime_dataset.py`, no GPU)

```
PASS layers: 6 blobs, 8,263,460,562 B, sizes and sha256 match the registry manifest
PASS overlay: 28 members, sha256 4848d1892a1fb6ad8bc8adc3475077735318d68ce97bd918d0ba6baee956218b, pinned per-file digests, equals the committed sources
PASS stock: 26 targets match their pinned stock bytes in the layers, 2 new files absent from the image
PASS install: 'ARC3 vLLM 0.31.0 overlay installed=28, already-patched=0', then 'ARC3 vLLM 0.31.0 overlay installed=0, already-patched=28'; installed files == overlay
PASS py_compile: 28 installed modules compile
PASS rejection: a modified vllm/v1/worker/utils.py fails the applier with nothing written
PASS primary: vllm/models/qwen4_exp/nvidia/model.py stock b90aa88d8a09 -> patched eb09565f6b80
all 7 checks passed
```

The stock pins also equal the files at git tag v0.31.0.

## 3. Harness contract (`harness_contract_check.py`)

This runs the Arm B notebook's own setup code (frozen TAAF bundle `setup_commands.json`,
sha256 c041da15…) with only `RUNTIME_OWNER`, `RUNTIME_SLUG` and the three
`FINE_PREFIX_CACHE_*` pin blocks replaced (`harness_switch.diff`, 21 lines). It stops before
the server launch and calls `install_image_runtime()`:

```
Extracted runtime layer 8 … 31 (pigz) after 41s
Runtime patch arc3_vllm_v0310_arc3_overlay.tar.blob: ARC3 vLLM 0.31.0 overlay installed=28, already-patched=0
Image runtime ready at …: vLLM 0.31.0, torch 2.13.0+cu130
harness env: VLLM_ARC3_GDN_RECOVERSSM=1 VLLM_GDN_DECODE_KERNEL=triton VLLM_QWEN4_EXP_DRAFT_VOCAB=<bundle>/configs/draft_vocab_32k.json
```

`validate_prefix_cache_runtime()` passes with the new pins. The same check passed for each
build; the §9 final serve used the runtime it installed for 393f83bc, the §12 and §13 serves the
one it installed for 4848d189. With the e975732 KV copy hook inserted
(`--kv-copy-patch`), the same install prints `ARC3 KV copy patch: already patched (v0.31.0, …)`,
because the overlay carries the same bytes.

## 4. Serving on the local RTX PRO 6000 (PCI 04:00.0)

The card is a Max-Q workstation board (300 W limit), so throughput is relative only.

- **Serve line:** the recorded Arm B line, with only the model path, chat template and port
  substituted. That is TP1, max_num_seqs 14, max-model-len 147072, MTP 3 with
  `use_local_argmax_reduction`, fp8_e4m3 KV, `--enable-prefix-caching --prefix-match-unit 128
  --prefix-cache-retention-interval 0`, `--engram-config {"cpu_offload": true}
  --cpu-offload-params embed_tokens`, `--enable-mm-embeds`, limit-mm image:0/video:0,
  max_pixels 1048576, compressed-tensors, gpu-memory-utilization 0.98 and
  `--max-cudagraph-capture-size 56`.
- **Environment:** the harness's (`rt_env.build_env`): RecoverSSM on, Triton GDN decode, his
  32k draft vocabulary.
- **Model:** quant v2 cannot load in vLLM as shipped, on e975732 and v0.31.0 alike, because
  `ple.key_proj` is FP8 while `ple.value_proj` is BF16 inside the fused `kv_proj`. Both
  runtimes raise "Found different quantization schemes for the shards of
  language_model.model.layers.1.ple.kv_proj". The runs therefore use a validation view
  (`make_kpbf16_view.py`). Sections 4–6, 9 and 10 used v2 with the single PLE layer's
  key_proj dequantized to BF16. §11 uses the lead's final view: key_proj is Qwen's original BF16
  tensor, byte for byte, as a key_proj-excluded quant would carry it. In both views every other
  tensor is v2's own, and the shipped dirs are untouched.
- **Request suite (greedy):** smoke; one stream × 512 tokens; one student image_embeds request
  (1024 × 2560 bf16, grid [1,64,64]); 11, 13 and 14 concurrent streams × 512 tokens; 14
  concurrent image_embeds requests × 256 tokens; a 3-turn conversation over a ~9k-token prefix.

### Log lines from the new runtime

```
ARC3 GDN RecoverSSM enabled: GDN and PLE groups allocate no per-draft state blocks; set VLLM_ARC3_GDN_RECOVERSSM=0 before startup for stock slots
Qwen4Exp input embedding kept in pinned host memory: 1.18
GDN decode kernel: triton
ARC3 GDN RecoverSSM records: 1.760 MiB per GDN layer (14 rows x 4-token windows)
ARC3 rc3 SM120 GEMM enabled for target M=40/44/48/52/56/64; first decoder installs 6 projections; …
Initialized PLE embedding …layers.1.ple.ple_embedding.ngram_embedding: quantization_method=Qwen4ExpPLEUnquantizedEmbeddingMethod, weight_dtype=torch.bfloat16, weight_device=cpu, pinned=True
Checkpoint weight filter selected 33/296774 weights across 3/6 shards.
Qwen4Exp MTP drafts over 32000 of 248320 tokens from …/configs/draft_vocab_32k.json.
Setting attention block size to 1664 tokens to ensure that attention page size is >= mamba page size.
cudagraph_capture_sizes: [1, 2, 4, 8, 16, 24, 32, 40, 44, 48, 52, 56]   (12 PIECEWISE + 10 FULL uniform-decode graphs)
Warming up CuTeDSL compile_units=6 names=('Qwen4Exp HC down+SiLU GEMM',).
Available KV cache memory: 17.53 GiB
GPU KV cache size: 1,260,836 tokens, Maximum concurrency for 147,072 tokens per request: 8.57x
SpecDecoding metrics: Mean acceptance length: 2.53, … Per-position acceptance rate: 0.740, 0.481, 0.310, Avg Draft acceptance rate: 51.0%
```

**RecoverSSM and the ARC3 kernels did run.** Triton compiles a kernel at its first launch,
and the run's Triton cache holds `_gdn_recoverssm_verify_kernel` (1 variant),
`_gdn_recoverssm_commit_kernel` (4), the SM120 GEMM's `compute_partial_gemm` (19) and
`reduce_partial_gemm` (17), and `_lookup_embedding_from_pinned_kernel` (1). vLLM's JIT monitor
also logged `_gdn_recoverssm_commit_kernel` compiling during inference. The GDN commit needs
no column postprocess, so `_postprocess_recoverssm_align_kernel` (Kimi KDA's) correctly never
ran.

Errors before shutdown: 0. When the driver stops the server with SIGTERM after the suite, the
API server logs `EngineDeadError` while the engine core exits. That is the shutdown, after the
`[shutdown] EngineCore: trigger received signal=SIGTERM` line, and it is counted separately.

## 5. Side by side with e975732 + his overlay (same card, model view, serve line and requests)

The cold runs evict the model's page cache first and start with empty compile caches, as a
Kaggle run does. They ran back to back: e975732 first, then 0.31.0. The first 0.31.0 run came
an hour earlier with its cache partly warm.

| | e975732 + his overlay (cold) | 0.31.0 + this overlay (cold) | 0.31.0 + this overlay (1st run) |
|---|---|---|---|
| ready (launch -> /v1/models) s | 770.1 | 760.1 | 740.1 |
| weights load s (target, MTP) | 582.23, 21.74 | 561.40, 22.55 | 538.10, 21.18 |
| model GPU memory | 74.19 GiB | 74.19 GiB | 74.19 GiB |
| init engine s | 60.47 | 65.07 | 64.63 |
| graph capture | 11 secs, took 0.40 GiB; 4 secs, took 0.41 GiB | 11 secs, took 0.39 GiB; 4 secs, took 0.39 GiB | 11 secs, took 0.39 GiB; 4 secs, took 0.39 GiB |
| available KV cache memory | 17.53 GiB | 17.53 GiB | 17.53 GiB |
| GPU KV cache tokens | 1,260,836 | 1,260,836 | 1,260,836 |
| max concurrency @147,072 | 8.57x | 8.57x | 8.57x |
| attention block size | 1664 | 1664 | 1664 |
| smoke reply | '2 + 2 equals 4.' | '2 + 2 equals 4.' | '2 + 2 equals 4.' |
| single stream tok/s (512 tok) | 215.49 | 221.07 | 225.15 |
| image_embeds prompt tokens | 1059 | 1059 | 1059 |
| C11 aggregate tok/s | 734.21 | 747.23 | 736.2 |
| C13 aggregate tok/s | 907.57 | 881.61 | 903.8 |
| C14 aggregate tok/s | 962.41 | 928.62 | 959.55 |
| C14 image_embeds tok/s | 692.7 | 600.04 | 717.46 |
| MTP mean acceptance length | 2.565 | 2.500 | 2.539 |
| MTP draft acceptance rate | 52.2% | 50.0% | 51.3% |
| MTP per-position acceptance | 0.744, 0.502, 0.319 | 0.725, 0.476, 0.300 | 0.740, 0.496, 0.303 |
| multi-turn cached tokens (turn 2, 3) | 8832/9154, 8960/9237 | 8832/9180, 8960/9330 | 8832/9150, 8960/9259 |
| prefix cache hits / queries | 17792 / 44378 | 17792 / 44497 | 17792 / 44396 |
| requests stop/length/error/abort | 4/54/0/0 | 4/54/0/0 | 4/54/0/0 |
| errors before shutdown | 0 | 0 | 0 |

All deterministic quantities match, with no difference between the runtimes: KV pool, model
memory, capture sizes, attention block size, prefix-cache hits and the request outcomes.

Throughput and MTP acceptance move with the generated text and the card's power and thermal
state. The two 0.31.0 runs alone differ by 3% at C14 and by 16% on the C14 image_embeds load,
which is as wide as the gap to e975732. So this card shows neither a regression nor a gain.
MTP acceptance length was 2.500 and 2.539 on 0.31.0 and 2.565 on e975732. That gap is under 3%,
from three runs whose greedy texts differ because the runtimes differ numerically (see §7), so
it is not established either. The card is a Max-Q (300 W) workstation board, and throughput
here is relative only.

## 6. RecoverSSM on vs off on the new runtime (`VLLM_ARC3_GDN_RECOVERSSM=0`, the A/B launcher path)

With the switch off, the GDN builder keeps per-draft state slots and upstream #58762's
cross-group metadata reuse (`update_block_table`) is active. With it on, that reuse is disabled
(README, adaptation 1). Both paths serve the whole suite with no error:

| | RecoverSSM on (cold run) | RecoverSSM off (switch 0) |
|---|---|---|
| ready (launch -> /v1/models) s | 760.1 | 740.1 |
| weights load s (target, MTP) | 561.40, 22.55 | 546.88, 22.54 |
| model GPU memory | 74.19 GiB | 74.14 GiB |
| init engine s | 65.07 | 65.88 |
| graph capture | 11 secs, took 0.39 GiB; 4 secs, took 0.39 GiB | 15 secs, took 0.40 GiB; 4 secs, took 0.40 GiB |
| available KV cache memory | 17.53 GiB | 17.59 GiB |
| GPU KV cache tokens | 1,260,836 | 1,156,966 |
| max concurrency @147,072 | 8.57x | 7.87x |
| attention block size | 1664 | 1664 |
| smoke reply | '2 + 2 equals 4.' | '2 + 2 equals 4.' |
| single stream tok/s (512 tok) | 221.07 | 216.12 |
| image_embeds prompt tokens | 1059 | 1059 |
| C11 aggregate tok/s | 747.23 | 767.39 |
| C13 aggregate tok/s | 881.61 | 901.55 |
| C14 aggregate tok/s | 928.62 | 938.93 |
| C14 image_embeds tok/s | 600.04 | 589.32 |
| MTP mean acceptance length | 2.500 | 2.522 |
| MTP draft acceptance rate | 50.0% | 50.7% |
| MTP per-position acceptance | 0.725, 0.476, 0.300 | 0.728, 0.482, 0.312 |
| multi-turn cached tokens (turn 2, 3) | 8832/9180, 8960/9330 | 8832/9180, 8960/9333 |
| prefix cache hits / queries | 17792 / 44497 | 17792 / 44500 |
| requests stop/length/error/abort | 4/54/0/0 | 3/55/0/0 |
| errors before shutdown | 0 | 0 |

RecoverSSM frees the per-draft Mamba state blocks. On the same 17.5 GiB budget the pool holds
1,260,836 instead of 1,156,966 tokens, +103,870 tokens (+9.0%), and concurrency at full context
rises from 7.87x to 8.57x. Prefix reuse across turns is identical on both paths.

## 7. HC down+inject kernels and the SM120 GEMM on this card

`bench_hc_down.py --all-m` times Qwen4Exp's `input_mix_weight_down_block_inject` projection
(336 × 10240 BF16, then the split and hc_silu op): median of CUDA-graph replays, in µs.

| M | 1 | 2 | 4 | 8 | 16 | 24 | 32 | 40 | 44 | 48 | 52 | 56 | 64 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| linear + hc_silu (e975732 below M40) | 6.40 | 6.40 | 6.77 | 6.91 | 7.28 | 7.63 | 7.93 | 8.03 | 8.05 | 8.08 | 8.15 | 8.24 | 8.24 |
| his SM120 GEMM + hc_silu | | | | | | | | 7.53 | 7.64 | 7.73 | 7.84 | 8.01 | 8.14 |
| upstream #58957 fused down+SiLU | 3.34 | 3.63 | 5.49 | 7.31 | 8.16 | 11.28 | 11.38 | 16.13 | 16.51 | 16.75 | | | |

The fused kernel's split-K configs are tuned for SM100f. On sm_120 it beats e975732's dispatch only
at M ≤ 4. At M = 40–48, where 0.31.0 would have taken the projection away from his GEMM, it is
2.2× slower. Outputs agree: injection logits are bit-identical and LoRA activations differ at
most by bf16 rounding.

Overlay 393f83bc therefore adds `qwen4_exp/nvidia/hyperconnection.py`. Where his GEMM is installed
on that projection (TP1 sm_120, `VLLM_ARC3_SM120_GEMM=1`), the fused kernel serves only M ≤ 4, and
e975732's dispatch serves the rest. Elsewhere upstream dispatch is unchanged. At 96 calls per
forward, this is worth about 0.35 ms per decode step at C6 and 0.87 ms at C12.

`check_sm120_gemm.py` re-derives the core of his rc3 GEMM suite: every plan (9 projections) at
every GEMM row (40/44/48/52/56/64), 5 seeds each. The custom GEMM's relative RMS against FP32 is
never above torch's BF16 matmul at the same M, and CUDA-graph replay is bit-identical to eager:
**54 checks, 0 failures**. The two runtimes ship the same Triton (3.7.1) and the same GEMM module bytes.

## 8. vLLM v0.31.0's own tests for the code the overlay touches

The test files ran against stock 0.31.0 and against the ported runtime with
`VLLM_ARC3_GDN_RECOVERSSM` off and on: 31 files covering the KV-cache managers and coordinator,
the Mamba/GDN metadata builders, the MRV2 model state, the rejection sampler, the loaders, Qwen4Exp
PLE/HC/QSA, Kimi KDA, and the mamba/FLA/MoE kernels. Each file ran in its own pytest process in the
harness environment on the 6000. The tests were copied away from the source tree so that `vllm`
resolved to the runtime under test.

First pass, harness environment (HF offline):

| test file | stock 0.31.0 | ported, switch 0 | ported, switch 1 |
|---|---|---|---|
| `v1/core/test_single_type_kv_cache_manager.py` | 34 passed | 34 passed | 34 passed |
| `v1/core/test_kv_cache_utils.py` | 160 passed, 5 failed | 160 passed, 5 failed | 106 passed, 59 failed |
| `v1/core/test_prefix_caching.py` | 160 passed, 8 failed | 160 passed, 8 failed | 157 passed, 11 failed |
| `v1/core/test_mamba_align_chunk_split.py` | 46 passed | 46 passed | 46 passed |
| `v1/core/test_deferred_block_free.py` | 14 failed | 14 failed | 14 failed |
| `v1/core/test_contiguous_kv_packing.py` | 27 passed | 27 passed | 27 passed |
| `v1/core/prefix_cache/test_hybrid_prefix_cache_hit_rate.py` | 2 errors | 2 errors | 2 errors |
| `v1/core/prefix_cache/test_mamba_eagle_resume_checkpoint.py` | 13 passed | 13 passed | 13 passed |
| `v1/core/prefix_cache/test_partial_prefix_cache_hits.py` | 117 passed | 117 passed | 117 passed |
| `v1/core/prefix_cache/test_partial_prefix_cache_primitives.py` | 15 passed | 15 passed | 15 passed |
| `v1/core/test_scheduler.py` | 13 passed, 180 failed | 13 passed, 180 failed | 9 passed, 184 failed |
| `v1/attention/test_gdn_metadata_builder.py` | 48 failed | 48 failed | 48 failed |
| `v1/attention/test_mamba_update_block_table.py` | 8 passed | 8 passed | 8 passed |
| `v1/worker/test_mamba_hybrid_model_state.py` | 5 passed, 1 failed | 4 passed, 2 failed | 4 passed, 2 failed |
| `v1/worker/test_mamba_utils.py` | 43 passed | 43 passed | 43 passed |
| `v1/worker/test_gpu_batch_ordering.py` | 13 passed | 13 passed | 13 passed |
| `v1/worker/test_gpu_worker.py` | 20 passed | 20 passed | 20 passed |
| `v1/spec_decode/test_rejection_sampler_utils.py` | 54 passed | 54 passed | 54 passed |
| `model_executor/model_loader/test_ep_weight_filter.py` | 37 passed | 37 passed | 37 passed |
| `models/qwen4_exp/test_ple.py` | 70 passed | 70 passed | 70 passed |
| `models/qwen4_exp/test_hc_ops.py` | 13 passed | 13 passed | 13 passed |
| `models/qwen4_exp/test_qsa_reference.py` | 73 passed | 73 passed | 73 passed |
| `models/qwen4_exp/test_config.py` | 9 passed | 9 passed | 9 passed |
| `models/qwen4_exp/test_qsa_pre_indexer.py` | 16 passed | 16 passed | 16 passed |
| `models/kimi_k3/test_kda.py` | 86 passed, 13 skipped | 86 passed, 13 skipped | 86 passed, 13 skipped |
| `kernels/mamba/test_causal_conv1d.py` | 155 passed, 9 failed | 155 passed, 9 failed | 155 passed, 9 failed |
| `kernels/mamba/test_mamba_ssm.py` | 286 passed, 18 skipped | 286 passed, 18 skipped | 286 passed, 18 skipped |
| `kernels/fla/test_fused_sigmoid_gating_delta_rule.py` | 18 passed | 18 passed | 18 passed |
| `kernels/fla/test_fused_recurrent_packed_decode.py` | 8 passed | 8 passed | 8 passed |
| `kernels/mamba/test_gdn_forward_core_split.py` | 1 skipped | 1 skipped | 1 skipped |
| `kernels/moe/test_moe_weight_loading_padded.py` | 82 passed | 82 passed | 82 passed |
| **total** | 1581 passed, 265 failed, 2 errors, 32 skipped | 1580 passed, 266 failed, 2 errors, 32 skipped | 1519 passed, 327 failed, 2 errors, 32 skipped |

Every failure in the stock column is environmental:
- ModelConfig built from a hub id (`facebook/opt-125m`, `Qwen/Qwen3.5-0.8B`, `llava-hf/llava-1.5-7b-hf`,
  `Qwen/Qwen1.5-7B`) while the hub is offline;
- `pipeline_parallel_size=4` on one GPU;
- `CUDNN_STATUS_SUBLIBRARY_VERSION_MISMATCH` in the torch reference conv of `test_causal_conv1d`.

The one extra failure in the switch-0 column was a real defect of the port:
`test_prepare_attn_forwards_positions` builds `MambaHybridModelState` without `__init__`, and the
port's RecoverSSM row mask read `self._gdn_recoverssm` unconditionally. It is fixed in the recipe
(`getattr`, overlay 38f69d3f onward). Serving was never affected, because `__init__` always sets
the attribute.

Second pass, the files whose failures were hub lookups, rerun with HF configs fetchable into a
dedicated HF_HOME (the runtime itself stays offline), with overlay 38f69d3f:

| test file | stock 0.31.0 | ported, switch 0 | ported, switch 1 |
|---|---|---|---|
| `v1/core/test_kv_cache_utils.py` | 163 passed, 2 failed | 163 passed, 2 failed | 106 passed, 59 failed |
| `v1/core/test_prefix_caching.py` | 168 passed | 168 passed | 157 passed, 11 failed |
| `v1/core/test_deferred_block_free.py` | 14 passed | 14 passed | 14 failed |
| `v1/core/prefix_cache/test_hybrid_prefix_cache_hit_rate.py` | 2 passed | 2 passed | 2 errors |
| `v1/core/test_scheduler.py` | 191 passed, 2 failed | 191 passed, 2 failed | 9 passed, 184 failed |
| `v1/attention/test_gdn_metadata_builder.py` | 48 passed | 48 passed | 48 failed |
| `v1/worker/test_mamba_hybrid_model_state.py` | 6 passed | 6 passed | 5 passed, 1 failed |
| **total** | 592 passed, 4 failed | 592 passed, 4 failed | 277 passed, 317 failed, 2 errors |

With the switch off, the ported runtime matches stock file by file. That includes
`test_gdn_metadata_builder.py` (48/48), which covers the GDN builder the port adapted, and
`test_mamba_update_block_table.py` (8/8, upstream #58762's reuse path). The 4 remaining failures
need 4 GPUs.

With the switch on, every additional failure is Han Solo's own validator rejecting a test config
it was not built for: `VLLM_ARC3_GDN_RECOVERSSM=1 requires a Qwen4Exp target model, speculative
decoding, …`. The 2 errors are test servers that this rejection stopped. The switch is a
process-wide environment variable by design, as in e975732, and the harness sets it only for
the Qwen4Exp server.

## 9. Final overlay 393f83bc: cold serve from the harness-installed runtime

The harness's own `install_image_runtime()` installed this runtime (`installed=26`), and it was
served cold: page cache evicted, empty compile cache. It ran under `strace -f --seccomp-bpf -e
trace=connect` with all HTTP(S) proxies pointed at a closed local port, since the Kaggle
submission run is offline and this host cannot create a network namespace.

- Full suite passed: ready after 750 s, smoke "2 + 2 equals 4.", single stream 225.45 tok/s,
  image_embeds answered, C11/C13/C14 742.8 / 909.8 / 961.8 tok/s, C14 image_embeds 676.0 tok/s,
  multi-turn cached 8,832 then 8,960 tokens. KV pool 17.53 GiB = 1,260,836 tokens; graphs 0.40 + 0.41 GiB.
- **Network:** 15 `connect()` calls. 14 are local unix sockets: ZMQ IPC, the nvidia-mps probe and
  nscd. The one inet call is vLLM's `get_ip()` probe, a UDP `connect(8.8.8.8:80)` that sends no
  packet and only reads the local interface address. Nothing used the blackholed proxies. Han
  Solo's runtime shows the identical pattern.
- **Out of memory in a copy-on-write burst:** after the suite, the first repeat round sent 14 C14
  image_embeds requests that resume cached prefixes. The engine died with `torch.OutOfMemoryError`
  in MRV2 `update_requests` -> `copy_kv_cache_blocks_inplace` (`blocks[dst] = blocks[src]`):
  "Tried to allocate 698.00 MiB … 655.75 MiB is free". That step copied 32 KV blocks of ~21.8 MiB
  each for prefix-cache copy-on-write. The gather materialises all of them at once, and
  `--gpu-memory-utilization 0.98` leaves ~0.65 GiB free.

  The function is byte-identical in e975732. A copy logger (sitecustomize, diagnostic only) then
  ran both runtimes cold through the same suite and 5 repeats:

  | | copy calls | blocks copied | largest step | lowest CUDA-free before a copy |
  |---|---|---|---|---|
  | 0.31.0 + 393f83bc | 39 | 342 | 32 blocks (~0.7 GiB) | 200 MiB |
  | e975732 + his overlay | 39 | 342 | 44 blocks (~0.96 GiB) | 164 MiB |

  Both survived that pass, so survival is a matter of whether the caching allocator has a large
  enough free block. The copy-on-write traffic is identical, and e975732's largest burst was
  bigger. This is a latent crash risk in both runtimes, not a port regression.

  A Kaggle run starts with cold caches (CUDA-graph pool 0.40 + 0.41 GiB vs 0.24 GiB warm). If 14
  games resume cached prefixes in the same step, the same OOM can kill the server. The watchdog
  then restarts it, at the cost of a full reload.

  Remedies considered at the time:
  - (a) copy in bounded chunks, e.g. `for i in range(0, n, k): blocks[dst[i:i+k]] =
    blocks[src[i:i+k]]` with k·block_bytes ≤ 64 MiB (safe while no destination is also a source);
  - (b) `--gpu-memory-utilization 0.97`, about 1 GiB more headroom and ~0.95 GiB less KV pool.

  (a) was first gated on the crash reproducing on e975732, which it did not in two cold runs
  (whether the gather fits is allocator luck). It was then built: overlay 55da1fed, and for
  e975732 a post-install patch. §12 has the result.

## 10. Paired throughput repeats (order reversed from §5)

Each runtime served once: ours, overlay 38f69d3f, first, then his. Each ran the suite plus 5
alternating rounds of C14 text and C14 image_embeds, with warm compile caches.

| | 0.31.0 (overlay 38f69d3f) | e975732 |
|---|---|---|
| ready (launch -> /v1/models) s | 695.1 | 670.1 |
| weights load s (target, MTP) | 550.07, 21.57 | 540.22, 21.40 |
| model GPU memory | 74.19 GiB | 74.19 GiB |
| init engine s | 28.75 | 25.09 |
| graph capture | 4 secs, took 0.39 GiB; 4 secs, took 0.24 GiB | 3 secs, took 0.40 GiB; 4 secs, took 0.25 GiB |
| available KV cache memory | 17.53 GiB | 17.53 GiB |
| GPU KV cache tokens | 1,260,836 | 1,260,836 |
| max concurrency @147,072 | 8.57x | 8.57x |
| attention block size | 1664 | 1664 |
| smoke reply | '2 + 2 equals 4.' | '2 + 2 equals 4.' |
| single stream tok/s (512 tok) | 216.31 | 219.93 |
| image_embeds prompt tokens | 1059 | 1059 |
| C11 aggregate tok/s | 785.17 | 798.16 |
| C13 aggregate tok/s | 887.32 | 926.4 |
| C14 aggregate tok/s | 954.78 | 953.12 |
| C14 image_embeds tok/s | 634.33 | 605.81 |
| MTP mean acceptance length | 2.523 | 2.524 |
| MTP draft acceptance rate | 50.8% | 50.8% |
| MTP per-position acceptance | 0.734, 0.488, 0.301 | 0.730, 0.486, 0.308 |
| multi-turn cached tokens (turn 2, 3) | 8832/9180, 8960/9230 | 8832/9180, 8960/9334 |
| prefix cache hits / queries | 80512 / 120122 | 80512 / 120226 |
| requests stop/length/error/abort | 4/194/0/0 | 2/196/0/0 |
| errors before shutdown | 0 | 0 |

| 5 rounds | C14 text tok/s | C14 image_embeds tok/s |
|---|---|---|
| 0.31.0 + this overlay | 944.7 ± 13.3 (934–967) | 985.5 ± 80.8 (865–1088) |
| e975732 + his overlay | 943.6 ± 20.8 (908–957) | 946.2 ± 68.1 (869–1042) |

The repeated image_embeds rounds partly hit the prefix cache, so they compare only across
runtimes, not with §5. MTP mean acceptance length is 2.523 here and 2.524 on e975732. Neither
throughput nor acceptance differs between the runtimes beyond run-to-run noise.

## 11. Final validation with the lead's model view (original BF16 key_proj), overlay 393f83bc

The setup matches §9: the harness-installed runtime, cold page and compile caches, the full suite,
connect() tracing and blackholed proxies. The model is `model_v2_keyproj_orig`.

- Load: ready after 735 s (weights 548.7 s + MTP 21.6 s). Graphs 0.40 + 0.41 GiB.
  `Available KV cache memory: 17.53 GiB`, `GPU KV cache size: 1,260,836 tokens` (8.57x).
- Requests: smoke "2 + 2 equals 4."; image_embeds answered (1,059 prompt tokens). Single stream
  226.15 tok/s; C11/C13/C14 741.0 / 923.0 / 947.1 tok/s; C14 image_embeds 662.6 tok/s;
  multi-turn turn 2 cached 8,832 tokens.
- MTP: mean acceptance length 2.535, draft acceptance 51.2%, per position 0.735 / 0.489 / 0.311.
- Network: the get_ip UDP probe only. 58 requests: 2 stop, 56 length, 0 error. 0 errors before
  shutdown.

## 12. Bounded KV block copies: the overlay member (since 55da1fed) and the e975732 post-install patch

`copy_kv_cache_blocks_inplace` now copies at most `VLLM_ARC3_KV_COPY_CHUNK` blocks at a time (default
4; README "Bounded KV block copies"). The same edit is the overlay member here and, through
`patch_kv_copy_chunked.py` + `kv_copy_hook.py`, a post-install patch for e975732.

**Same result as the stock gather** (`test_kv_copy_chunked.py`, CPU, torch 2.13.0+cu130; the stock
and patched functions run verbatim from each utils.py): 4000/4000 cases byte-identical, over chunk
sizes 0-64, the four cache layouts the function distinguishes, and fresh-destination (call-site),
chain, reverse-chain, permutation and random copy patterns. 500/500 cases gather exactly
min(chunk, N) rows, or N when more than `chunk` copies read a written block. An empty list writes
nothing, and `VLLM_ARC3_KV_COPY_CHUNK=-1` is refused. This holds for both the 0.31.0 member and
e975732's patched file. As controls, a chunk loop without the reordering fails 1189/4000 cases.
The first form (92e368ac) is identical in result, but in 73/500 bound cases it gathers all N
blocks (its single-gather fallback on any overlap).

**Overlap at the call sites.** Every destination is a block taken from the free queue in the same
scheduler step (`single_type_kv_cache_manager.py:394`, `:1995/1999`) and held until the copy has
run (`:474`, `:2010`, scheduler `_free_cow_retained_blocks`), so destinations are distinct. Every
source is a prefix-cache hit with `ref_cnt > 0` (`:471`). A destination can be a source in the same
call only through a same-step hit on a block whose contents that step's copy or forward pass has
yet to produce. vLLM defers exactly that case for mamba groups (`:1823-1831`, `:2032`). The block
map returns the first block that registered a hash (`block_pool.py:62-69`), so a CoW copy that
registers the hash its source already holds is not returned while the source holds it. Every
path has not been traced, so the code does not rely on this: overlapping copies are reordered
(exact) and the runs below log the overlap count of every call.

**e975732, the notebook path** (`harness_contract_check.py --keep-pins --kv-copy-patch`, his setup
script, pins and dataset):

```
Runtime patch arc3_vllm_main_e975732_arc3_overlay.tar.blob: ARC3 main-e975732 overlay installed=32, already-patched=0
Image runtime ready at …: vLLM 0.29.1rc1.dev573+ge97573215, torch 2.13.0+cu130
ARC3 KV copy patch: installed (e975732, 3351a0410ac1 -> d9347553f5f8) …/vllm/v1/worker/utils.py
dataset applier rerun: 0 ARC3 main-e975732 overlay installed=0, already-patched=32
kv copy patch rerun: 0 ARC3 KV copy patch: already patched (e975732, d9347553f5f8) …
validate_prefix_cache_runtime rerun: OK
```

The installer upgrades a 92e368ac tree in place to 4848d189 (`installed=2, already-patched=26`: `utils.py` and `kernel_warmup.py`; then 0/28).

**Cold serves, chunking off and on, both runtimes.** Each serve is a harness-installed runtime with a cold
page cache and an empty compile cache, under the Arm B serve line. It runs the full request suite, then 5
alternating C14 / C14 image_embeds rounds, the rounds whose prefix-cache resumes crashed §9's run. The
two runtimes:
- e975732: his setup script, his pins and his dataset, with `kv_copy_hook` applied (`rt_e975_kv`).
- 0.31.0: this dataset (overlay 4848d189) installed through the harness (`rt_v031_kv`).

OFF sets `VLLM_ARC3_KV_COPY_CHUNK=0` on the same file: the stock single gather. ON leaves the variable
unset, so the shipped default of 4 applies. A diagnostic `sitecustomize` wrapped
`copy_kv_cache_blocks_inplace` and logged, for every call:
- the number of copies;
- copies whose source block is also a destination;
- free memory before the call;
- the temporary: `max_memory_allocated` during the call minus `memory_allocated` before it, which
  is deterministic and does not depend on allocator luck.

| | e975732 OFF | e975732 ON | 0.31.0 OFF | 0.31.0 ON |
|---|---|---|---|---|
| ARC3_KV_COPY_CHUNK in force | 0 | 4 | 0 | 4 |
| copy calls / blocks copied | 38 / 342 | 37 / 342 | 41 / 339 | 38 / 342 |
| largest call (blocks) | 40 | 40 | 40 | 36 |
| largest copy temporary | 872.0 MiB = 40.03 blocks | 87.1 MiB = 4.00 blocks | 872.0 MiB = 40.03 blocks | 87.1 MiB = 4.00 blocks |
| copies reading a written block | 0 | 0 | 0 | 0 |
| lowest free before a copy | 248 MiB | 598 MiB | 60 MiB | 400 MiB |
| server OOM | no | no | no | no |
| error log lines while serving / error requests | 0 / 0.0 | 0 / 0.0 | 0 / 0.0 | 0 / 0.0 |
| error log lines after the driver's shutdown | 0 | 0 | 0 | 8 |
| ready (s) | 735.1 | 715.1 | 700.1 | 700.1 |
| KV pool (tokens) | 1,260,836 | 1,260,836 | 1,260,836 | 1,260,836 |
| C14 suite tok/s | 945.92 | 948.42 | 962.48 | 957.55 |
| C14 repeats tok/s (mean ± sd, n) | 950.0 ± 13.2 (5) | 947.0 ± 15.1 (5) | 951.3 ± 7.1 (5) | 967.2 ± 14.2 (5) |
| C14 image_embeds repeats tok/s | 910.5 ± 106.3 | 1006.4 ± 105.0 | 954.6 ± 83.6 | 982.8 ± 112.7 |
| MTP mean acceptance length | 2.53 | 2.543 | 2.526 | 2.528 |

The KV storage is one allocation whose scheduler-block row is 22,843,392 B (21.785 MiB). The temporary
is n rows of that for the stock gather and min(n, 4) rows with the chunking. None of the 154 calls
had a source that was also a destination.

The crash in §9 needs a large burst at a moment of low free memory, so whether an OFF run dies is
allocator luck. Both OFF runs here survived 40-block bursts (872 MiB), the 0.31.0 one with as
little as 60 MiB free before a copy. §9's run died at 32 blocks. The ON runs never materialised more
than 87.1 MiB.

Throughput and MTP acceptance with the chunking are within run-to-run noise, and the KV pool is
unchanged. The 8 error lines of 0.31.0 ON come after the driver's own SIGTERM: the process manager force-kills
the EngineCore and the API server's output handler logs `EngineDeadError` (runtime-0310's OFF run shows the same).
runtime-0310's earlier pairs (first form 92e368ac on 0.31.0, and e975732 with that form's patch) agree: OFF
40 and 32 blocks, ON 4.00 blocks each.

**Isolated copy, both runtimes** (`bench_kv_copy.py`, the installed `copy_kv_cache_blocks_inplace`, 44
copies of 22,843,392 B blocks in a 120-block storage, median of 20 calls). The output is identical for
every chunk size, on both runtimes:

| `VLLM_ARC3_KV_COPY_CHUNK` | peak temporary | median time |
|---|---|---|
| 0 (stock gather) | 958.5 MiB (44.00 blocks) | 6.50 ms |
| 1 | 22.0 MiB | 5.49 ms |
| 2 | 44.0 MiB | 6.26 ms |
| 4 (default) | 88.0 MiB (4.04 blocks) | 7.14 ms |
| 8 | 174.3 MiB | 7.07 ms |

e975732's patched file gives the same table within 0.1 ms. The default costs 0.6 ms per 44-block
burst; a serving run here copies 342 blocks in all.

## 13. Shipped FlashInfer autotune tactics: overlay 4848d189

**What failed on Kaggle** (smoke run of this runtime on an RTX PRO 6000 Blackwell Server Edition, 2026-10-09
00:02 UTC, overlay 393f83bc, `installed=26`). The startup ran as follows:
- Weights took 74.19 GiB and the KV pool 17.5 GiB (1,259,304 tokens).
- `kernel_warmup` then ran `flashinfer_autotune` with an empty cache under `/tmp/vllm-image-runtime-cache`.
- Every bucket of every pass logged `Skipped 16 unsupported tactic(s)` for `trtllm::fused_moe::gemm1` and
  `Skipped 32` for `gemm2`.
- That is 7 identical gemm1/gemm2 passes, i.e. no winner was cached and each MoE layer of the
  2048-token dummy forward tuned again. The forward still went through those layers on the
  fallback tactic (-1).
- It died in a QSA layer: `qsa_select_paged_prefill` allocates its 512 MiB logits workspace per call
  (`VLLM_SPARSE_INDEXER_MAX_LOGITS_MB`). The error was `torch.OutOfMemoryError ... Tried to allocate
  512.00 MiB ... 381.62 MiB is free ... 92.95 GiB is allocated by PyTorch, and 615.11 MiB is reserved by
  PyTorch but unallocated`.

**Why tuning is where it breaks.**
- `compile_or_warm_up_model` calls `kernel_warmup` after the KV cache has been allocated and before
  CUDA-graph capture.
- `kernel_warmup.py` is byte-identical in e975732, so his runtime runs the same step. The difference
  is FlashInfer: 0.7.0.post1 here, 0.6.18.post1 in e975732.
- 0.7.0's fused-MoE tuning profiles each tactic inside a CUDA graph with cold-L2 input copies
  (`use_cuda_graph=True, use_cold_l2_cache=True`), which needs far more memory than running a tactic.
  It does so in what the 0.98 KV sizing leaves free.
- runtime-0310's local runs here were cold too (each label had a fresh cache root and logged
  `Saved 64 configs`). They skipped 2 tactics per op, tuned 2 passes (the NVFP4 experts and the
  BF16 MTP experts), and their own 512 MiB QSA request needed an allocator retry.
- Kaggle's model is not the difference: the v2.1 upload's `config.json` equals the local view's.

**Why a cache shipped as-is would not have helped.**
- vLLM keys the cache directory by `sha256(vllm_config.compute_hash())`, which includes the model
  path: `22e3b3fa…` on Kaggle vs `292a6ede…` here.
- FlashInfer's `load_configs` refuses a file whose recorded `gpu` differs from the device: a hard
  mismatch, the configs are ignored and tuned again. The raw Max-Q file
  (`NVIDIA RTX PRO 6000 Blackwell Max-Q Workstation Edition`) checked against
  `NVIDIA RTX PRO 6000 Blackwell Server Edition` is exactly that.
- The overlay therefore writes its copy into whatever path vLLM resolves, with `"gpu": "*"`. With
  the runtime's own FlashInfer: `load_configs(seed)` returns True ("Loaded 64 configs"), with no hard
  or soft mismatch; the other six fields equal this runtime's.

**Empty cache vs the shipped tactics, cold, on the 6000.** Both runs use the harness-installed 4848d189
runtime with a cold page cache, an empty compile cache and an empty FlashInfer autotune cache, the same
suite, 5 repeat rounds and the KV copy chunking at its default. The only difference is
`VLLM_ARC3_FLASHINFER_AUTOTUNE_SEED`: 0 (stock: the empty cache is tuned cold) vs unset (the shipped
tactics seed the empty cache). The same diagnostic `sitecustomize` wrapped
`kernel_warmup.flashinfer_autotune` and logged its duration, the caching allocator's retry and OOM
counters during it, peak reserved memory, free memory before and after, and FlashInfer's tuning
statistics.

| | seed off (empty cache, tuned cold) | seed on (shipped), KV ON | seed on (shipped), KV OFF |
|---|---|---|---|
| ARC3_KV_COPY_CHUNK in force | 4 | 4 | 0 |
| largest copy temporary | 87.1 MiB = 4.00 blocks | 87.1 MiB = 4.00 blocks | 872.0 MiB = 40.03 blocks |
| server OOM | yes | no | no |
| error log lines while serving / error requests | 267 / n.a. (engine dead, HTTP 500) | 0 / 0.0 | 0 / 0.0 |
| ready (s) | 725.1 | 700.1 | 700.1 |
| KV pool (tokens) | 1,260,836 | 1,260,836 | 1,260,836 |
| C14 suite tok/s | 962.38 | 957.55 | 962.48 |
| C14 repeats tok/s (mean ± sd, n) | - | 967.2 ± 14.2 (5) | 951.3 ± 7.1 (5) |
| MTP mean acceptance length | - | 2.528 | 2.526 |
| autotune: seeded / configs loaded | no / - | yes / 64 | yes / 64 |
| autotune: tuning passes, skipped tactics | 2, 2 gemm1; 2 gemm2 | 0, none | 0, none |
| autotune: seconds | 16.32 | 0.43 | 0.43 |
| autotune: allocator retries / OOMs | 2 / 0 | 0 / 0 | 0 / 0 |
| autotune: peak reserved | 93.81 GiB | 92.86 GiB | 92.86 GiB |
| autotune: free before -> after | 1938 -> 600 MiB | 1938 -> 946 MiB | 1938 -> 946 MiB |
| allocation-failure warnings in log | 4 | 0 | 2 |

**The stock cold tune reproduced the Kaggle crash here.**
- With the seed off, tuning took 16.3 s and needed 2 allocator retries (cache flushes). Its
  reservations reached every byte that was free (1,938 MiB) and left 600 MiB free.
- The server came up and passed the suite and one repeat round. In repeat round 2 a prefill died in
  `qsa_select_paged_prefill`: `torch.OutOfMemoryError ... Tried to allocate 512.00 MiB ... 393.75 MiB is free ...
  555.95 MiB is reserved by PyTorch but unallocated`. That is Kaggle's allocation, with numbers close to
  Kaggle's 381.62 MiB free and 615.11 MiB fragmented.
- With the shipped tactics, the same runtime and suite (two runs: KV chunking on, and off) loaded 64 configs,
  ran 0 tuning passes in 0.43 s with 0 retries and left 946 MiB free. The 2048-token dummy forward then needed
  992 MiB of new reservations. Both runs served the suite and all 5 repeat rounds with 0 errors.
- Throughput and MTP acceptance with the shipped tactics are in the range of the cold-tuned runs here and in
  §12. The cold-tuned run's C14 suite figure is 962.4, the seeded runs' 957.6 and 962.5.

A crash after a cold tune is allocator luck: runtime-0310's earlier cold runs of this runtime mostly
survived. That is one crash against two clean seeded runs. What the numbers show:
- After a cold tune 600 MiB is free instead of 946 MiB.
- The tune's 2 allocator retries are failed `cudaMalloc`s, each of which flushes every unused cached
  block. That includes the 512 MiB workspace the dummy forward had cached for later prefills.
- At the crash, 556 MiB was reserved but unallocated, and none of it was a free 512 MiB block.

With the shipped tactics nothing is profiled after the KV allocation, and there are no retries to
flush the cache.

What this cannot show: whether the Server Edition executes the Max-Q-chosen tactics. It is the same
GB202/sm_120 part, the Kaggle failures were in profiling, and the fallback tactic ran there. A Kaggle
smoke with this dataset is the test. `FLASHINFER_LOGGING_LEVEL=debug` with
`VLLM_ARC3_FLASHINFER_AUTOTUNE_SEED=0` would log the exception behind each skipped tactic, if the cause
of Kaggle's profiling failures is wanted.

## Warnings seen, and why they are not port issues

- `Unknown vLLM environment variable detected: VLLM_ARC3_GDN_RECOVERSSM`: same on e975732. The
  switch is read from os.environ in config/vllm.py, not registered in envs.py.
- `Draft model Qwen4ExpMTP does not support external multimodal embeddings … using text-only
  draft`: the same code and warning exist in e975732. Under `--enable-mm-embeds` the MTP drafter
  sees text only. Image requests still verify against the full target.
- `Triton kernel JIT compilation during inference: …` for the RecoverSSM commit, PLE conv,
  rejection-sampler and draft-gather kernels. The first use compiles them, on both runtimes.
  v0.31.0 has a JIT warmup registry that could precompile them. That is not done here (a
  behaviour change, not a port).
- `mamba_ssm_dtype='float32' in its config, but --mamba-ssm-cache-dtype='bfloat16' was passed`
  is the serve line's choice.
