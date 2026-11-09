# ARC3 vLLM 0.31.0 runtime: Han Solo's e975732 ARC3 overlay ported to vLLM v0.31.0

This dataset is a Kaggle-offline vLLM runtime laid out like `lordhansolo/vllm-main-e975732-arc3`.
It holds six layers of the official `vllm/vllm-openai:v0.31.0` image, a hash-pinned overlay that
carries every change of his overlay `e3a6fe0d` (32 files) that v0.31.0 does not already contain,
the overlay's installer, and the `runtime-manifest.json` that the notebook setup reads. Two overlay
members are ours, not his: bounded KV block copies (`vllm/v1/worker/utils.py`) and shipped FlashInfer
autotune tactics (`vllm/model_executor/warmup/kernel_warmup.py`), both described below. The
installer contract is his: every overlay member is verified before anything is written, every
target must hold its pinned stock bytes, writes are atomic, and a second run changes nothing.

## Contents

| file | what |
|---|---|
| `layer-8-a48fcd63….tar.gz.blob` (1,453,071,769 B) | CUDA 13.0 toolkit pieces vLLM JITs with (nvcc, nvrtc, cuBLAS/cuRAND dev) |
| `layer-20-fd638f43….tar.gz.blob` (5,153,216,601 B) | vLLM's requirements (torch 2.13.0+cu130, triton 3.7.1, …) |
| `layer-21-927a5be8….tar.gz.blob` (1,265,185,169 B) | flashinfer-jit-cache 0.7.0.post1 (includes sm120f) |
| `layer-24-9066b0eb….tar.gz.blob` (62,007,612 B) | accelerate, modelscope, timm, runai-model-streamer |
| `layer-27-30530efd….tar.gz.blob` (315,499,561 B) | the vLLM 0.31.0 wheel |
| `layer-31-60bd59c4….tar.gz.blob` (14,479,850 B) | ep_kernels |
| `arc3_vllm_v0310_arc3_overlay.tar.blob` | the overlay, 28 files, sha256 `4848d1892a1fb6ad8bc8adc3475077735318d68ce97bd918d0ba6baee956218b` |
| `apply_vllm_v0310_arc3.py` | installer: `python apply_vllm_v0310_arc3.py <dist-packages>` |
| `PATCH_IDENTITY.json` | overlay digests, per-file stock and patched sha256, his ports and fixes with their v0.31.0 status, the per-file port dispositions |
| `runtime-manifest.json` | image digests, selected layers with whiteouts, dist-packages, nvcc, versions, the patch block |
| `README.md` = `PATCH_README.md`, `VALIDATION.md` | this file (twice, as in his dataset) and the checks |

Image: `vllm/vllm-openai:v0.31.0`, index `sha256:c1c9f6fd…`, amd64 manifest
`sha256:a4a4c0437bf7240089da5f08aa370c4aee17ae5290f7a3b468825ee26c4c3a6b`, built from
`db9527a46873454610df6dbedf79a36d6bf1a7f6` (tag `v0.31.0`). Selected layers total
8,263,460,562 B. The image has the same 40-layer structure as his `nightly-e975732` image, and
the six selected indices hold the same build steps he selects. The unselected layers are the
Ubuntu base, cudart, Python 3.12 + pip, uv, gdrcopy, the snapshot runtime, the KV-connector
stack (layer 35: LMCache/NIXL/Mooncake/cupy, which also replaces numpy and google-api-core),
the vllm-rs symlink, and the examples and benchmarks. The vLLM extensions carry sm_120 cubins
(`_C_stable_libtorch`: 83, `_moe_C_stable_libtorch`: 26).

## Switching the harness

The notebook setup (TAAF `setup_commands.json`) needs only its pins changed. These are
`RUNTIME_OWNER`/`RUNTIME_SLUG` and the three `FINE_PREFIX_CACHE_*` blocks (runtime identity,
patch identity, six required overlays). The values are in `scripts/runtime_0310/harness_pins.json`
in the arc-prize-2026 repo. `scripts/runtime_0310/harness_contract_check.py` runs the harness's
own `install_image_runtime()` against this dataset with exactly those constants replaced.
The environment the setup builds (RecoverSSM default on, Triton GDN decode, draft vocabulary,
PYTHONPATH/LD_LIBRARY_PATH from the manifest) needs no change.

## What happened to each of his 32 files

keep = v0.31.0's file is identical to e975732's, so his bytes ship unchanged. port = his diff
was rebased by a 3-way merge (base e975732, ours his, theirs v0.31.0). drop = the merge equals
v0.31.0 byte for byte, so upstream carries the change. new = a v0.31.0 file his change had to
move into. `scripts/runtime_0310/port_overlay.py` regenerates the overlay from his tar and vLLM's
git history and checks it byte for byte.

| file | disposition | his change | upstream commit (drops) |
|---|---|---|---|
| `vllm/config/vllm.py` | port | GDN RecoverSSM switch and validator; exact C11 M44 and C14 M44/M52 CUDA graph sizes | - |
| `vllm/distributed/kv_transfer/kv_connector/v1/mooncake/store/coordinator.py` | keep | Mooncake Mamba/EAGLE boundary reconciliation | - |
| `vllm/envs.py` | port | `VLLM_QWEN4_EXP_DRAFT_VOCAB` | - |
| `vllm/model_executor/layers/fused_moe/routed_experts.py` | drop | vllm#58720 expert mapping indexed by expert id | ad6817b68 |
| `vllm/model_executor/layers/mamba/abstract.py` | keep | RecoverSSM: no per-draft Mamba blocks | - |
| `vllm/model_executor/layers/mamba/gdn/qwen_gdn_linear_attn.py` | port | RecoverSSM records and verify path | - |
| `vllm/model_executor/layers/mamba/ops/arc3_gdn_recoverssm.py` | keep (new file) | RecoverSSM kernels (vllm#58863/#59366 still open upstream) | - |
| `vllm/model_executor/layers/mamba/ops/causal_conv1d.py` | keep | vllm#50021 bounds (PR head 79a2cb27b, unmerged) | - |
| `vllm/model_executor/layers/mamba/ops/mamba_ssm.py` | keep | vllm#50021 bounds | - |
| `vllm/model_executor/model_loader/default_loader.py` | port (3 conflicts) | MTP checkpoint weight prefilter | - |
| `vllm/model_executor/model_loader/weight_utils.py` | port | weight-name filter in the safetensors iterator | - |
| `vllm/models/kimi_k3/amd/ops/third_party/kda/fused_recurrent.py` | port | vllm#50021 bounds | - |
| `vllm/models/kimi_k3/nvidia/ops/third_party/kda/fused_recurrent.py` | keep | vllm#50021 bounds | - |
| `vllm/models/qwen4_exp/common/qsa_cache.py` | drop | vllm#58961 QSA key views release the profiling KV cache | a2be4d3cc |
| `vllm/models/qwen4_exp/nvidia/arc3_sm120_gemm.py` | keep (new file) | SM120 BF16 GEMM plans, M=40/44/48/52/56/64 | - |
| `vllm/models/qwen4_exp/nvidia/model.py` | port | embed_tokens in pinned host memory; SM120 GEMM install | - |
| `vllm/models/qwen4_exp/nvidia/mtp.py` | keep | MTP pruned draft vocabulary; MTP weight predicate | - |
| `vllm/models/qwen4_exp/nvidia/ngram_embedding.py` | drop (2 conflicts) | vllm#58489 PLE prefetch ids; the compressed-tensors PLE safeguard moves to `common/ngram_embedding.py` | 48d8880d0 (+ #57497 move) |
| `vllm/models/qwen4_exp/nvidia/ple_layer.py` | drop | vllm#58114 | 20b52e9f5 |
| `vllm/third_party/flash_linear_attention/ops/fused_recurrent.py` | keep | vllm#50021 bounds | - |
| `vllm/third_party/flash_linear_attention/ops/fused_sigmoid_gating.py` | keep | vllm#50021 bounds | - |
| `vllm/v1/attention/backends/gdn_attn.py` | port (1 conflict) + adapted | RecoverSSM metadata, commit and row selection | - |
| `vllm/v1/core/kv_cache_coordinator.py` | port | Mamba read-side EAGLE drop; replay boundaries with partial hash hits | - |
| `vllm/v1/core/kv_cache_utils.py` | port | PLE/GDN cache grouping on one TP/CP rank | - |
| `vllm/v1/core/single_type_kv_cache_manager.py` | port (1 conflict) | read-side EAGLE drop; align state retention and prompt-tail state for multi-turn prefix reuse | - |
| `vllm/v1/worker/gpu/model_states/mamba_hybrid.py` | port (1 conflict) + adapted | RecoverSSM state; resume-state block divisor; #58434 | - |
| `vllm/v1/worker/gpu_model_runner.py` | port | vllm#53919 accepted-token D2H sync (PR head d172b7f5d, unmerged) | - |
| `vllm/v1/worker/mamba_utils.py` | keep | RecoverSSM temporal copy modes; vllm#50021 bounds | - |
| `vllm/v1/attention/backends/mamba_attn.py` | drop | vllm#58114 | 20b52e9f5 |
| `vllm/v1/attention/backends/short_conv_attn.py` | drop | vllm#58114 | 20b52e9f5 |
| `vllm/v1/worker/gpu/spec_decode/rejection_sampler.py` | drop | vllm#58784 | fedbc3b56 |
| `vllm/v1/worker/gpu_worker.py` | drop (1 conflict) | vllm#58430 | 6491f481a |
| `vllm/models/qwen4_exp/common/ngram_embedding.py` | new | the compressed-tensors PLE safeguard, verbatim, where upstream #57497 moved `from_quant_config` | - |
| `vllm/models/qwen4_exp/nvidia/hyperconnection.py` | new | his SM120 GEMM keeps its rows on `input_mix_weight_down_block_inject` (adaptation 5) | - |
| `vllm/v1/worker/utils.py` | new (ours) | not his: bounded KV block copies (below) | - |
| `vllm/model_executor/warmup/kernel_warmup.py` | new (ours) | not his: shipped FlashInfer autotune tactics (below) | - |

Totals: 11 keep, 13 port, 8 drop, 2 new from his changes, plus our `utils.py` and
`kernel_warmup.py`, so 28 overlay files. Every one of his 9 ports and 16
custom fixes is either carried or already upstream; nothing was dropped without an upstream
equivalent. The 7 backports he lists (#58489, #58961, #58430, #58114, #58434, #58784, #58720)
are all in v0.31.0. #50021 and #53919 are unmerged PR heads and are carried.

## Bounded KV block copies (ours; not in e975732)

`copy_kv_cache_blocks_inplace` (byte-identical in e975732 and v0.31.0) applies a step's prefix-cache
copy-on-write copies with one gather, `blocks[dst] = blocks[src]`, which materialises every copied
block at once: 21.8 MiB per Qwen3.8 block, so 32-44 blocks need 0.7-0.96 GiB. At
`--gpu-memory-utilization 0.98` a cold start has far less free, and a cold run here died with
CUDA OOM in that gather (VALIDATION.md §9). The overlay's `utils.py` copies at most
`VLLM_ARC3_KV_COPY_CHUNK` blocks at a time (default 4, about 87 MiB; `0` restores the single
gather; a negative value is refused at import). The result equals the single gather for every
input: copies whose source is also a destination go first, together in one chunk, so they read
before anything is written, and no other source is ever written. If more copies than one chunk
holds read a written block, the single gather is used. The copy-on-write call sites are not
expected to produce such copies, since their destinations are blocks allocated in the same step.
None occurred in 154 instrumented calls. VALIDATION.md §12 has the equivalence test, the call-site
analysis and the cold serves with the chunking off and on.

For Han Solo's e975732 runtime, utils.py is not one of his 32 overlay targets, nor one of the
six `FINE_PREFIX_CACHE_REQUIRED_OVERLAYS`. `scripts/runtime_0310/patch_kv_copy_chunked.py`
applies the same edit after his installer, hash-pinned (e975732 stock `3351a041…` -> `d9347553…`;
on this runtime it reports "already patched"). `scripts/runtime_0310/kv_copy_hook.py` is the
setup-script hook that runs it between `install_image_runtime()` and the server start.

## Shipped FlashInfer autotune tactics (ours; not in e975732)

`kernel_warmup.flashinfer_autotune` (byte-identical in e975732 and v0.31.0) tunes FlashInfer's fused-MoE
tactics after the KV cache has taken `--gpu-memory-utilization` of the card. FlashInfer 0.7.0.post1
(this image) profiles every tactic of every token bucket in a CUDA graph with cold-L2 input copies.
On Kaggle's RTX PRO 6000 Server Edition, a cold start of this runtime died there. Every bucket of
every pass skipped all its profiled tactics, so no winner was cached and each MoE layer tuned again
(7 identical passes). The 2048-token dummy forward then could not allocate its 512 MiB QSA
workspace (VALIDATION.md §13).

The overlay's `kernel_warmup.py` writes the 64 fused-MoE tactics this runtime tuned cold on an RTX PRO
6000 (sm_120) into a missing autotune cache file before vLLM loads it. The tuning pass then finds
every key and profiles nothing; FlashInfer checks its cache before it builds any profiling input.
- The file is written wherever vLLM resolves the cache. That path hashes the whole vLLM config,
  model path included.
- The shipped copy records `"gpu": "*"`, because FlashInfer refuses a cache recorded on a
  differently named device (Max-Q vs Server Edition). The other metadata must still match: the
  FlashInfer, CUDA, cuBLAS, cuDNN, cudnn-frontend and CuTe-DSL versions of these layers.
- An existing cache file is never touched, and nothing is written on other architectures.
- `VLLM_ARC3_FLASHINFER_AUTOTUNE_SEED=0` restores stock behaviour.
- The tactics are generated by `scripts/runtime_0310/make_autotune_seed.py` from
  `recipe/data/flashinfer_autotune_sm120.json`. They cover this serve line's fused-MoE shapes:
  the NVFP4 experts, the BF16 MTP experts, and token buckets up to 2048. A model with other MoE
  shapes or quantization tunes the missing keys as before.

## Adaptations to v0.31.0

1. **Cross-group metadata reuse (upstream #58762).** Model Runner V2 now builds GDN metadata once
   per spec and gives the other KV-cache groups a `replace()` copy through `update_block_table`.
   RecoverSSM metadata is per group: its commit rows, source blocks and layer context belong to
   one group. A copy would commit the first group's layers once per group and never the others.
   With `VLLM_ARC3_GDN_RECOVERSSM=1` the GDN builder now reports
   `supports_update_block_table = False`, as upstream already does for Kimi KDA's RecoverSSM. With
   the switch off, upstream behaviour is unchanged.
2. **One-token prompt extensions run as decode (upstream #58400).** v0.31.0 marks any one-new-token
   prefill chunk over existing context as not prefilling. That includes a non-final chunk, which
   samples nothing. His RecoverSSM row selector takes every non-prefilling row, and the commit
   replays only sampled tokens, so such a row would lose its token's state. `mamba_hybrid` now
   passes the rows whose prefill had ended before the step, and the selector uses them. This is
   e975732's selection exactly. Draft-padded prompt tails still go through the draft rows.
3. **His #58434 port** is superseded by upstream's #58400 form (`prefill_runs_as_decode_np`).
4. **Prompt-tail EAGLE drop.** Upstream #58368 made the same change as his fix, keyed on
   `drop_eagle_checkpoint_block`. His condition (`use_eagle or drop_eagle_checkpoint_block`) is
   kept. It is a superset with the same effect.
5. **HC down+inject projection (upstream #58957).** v0.31.0 routes
   `input_mix_weight_down_block_inject` through a fused CuTe-DSL down+SiLU kernel for M <= 48.
   That overrides his SM120 GEMM at M = 40/44/48. On the RTX PRO 6000 the fused kernel is 2.2×
   slower there, and slower than e975732's linear path from M = 8 up. It is faster only at
   M <= 4 (VALIDATION.md §7). `qwen4_exp/nvidia/hyperconnection.py` therefore keeps e975732's
   dispatch above M = 4 wherever his GEMM is installed on that projection. Elsewhere upstream
   dispatch is unchanged, and so is `VLLM_ARC3_SM120_GEMM=0`.
6. **`mamba_hybrid` reads its RecoverSSM flag with `getattr`.** v0.31.0's own
   `test_prepare_attn_forwards_positions` builds the model state without `__init__`.

## Serve line (Arm B) against v0.31.0

Every flag of the recorded Arm B line exists in v0.31.0, `--enable-mm-embeds` and
`--limit-mm-per-prompt {"image":0,"video":0}` included. The rename
`--enable-mamba-fine-grained-prefix-cache` -> `--enable-mamba-shared-prefix-checkpoint` (#57382)
predates e975732 and the line uses neither. #58830 rejects per-request `mm_processor_kwargs`
unless `--trust-request-mm-kwargs` is set. The server-level `--mm-processor-kwargs` is
unaffected, and neither his bundle nor our board-tower code sends per-request kwargs.
`VLLM_PLE_CPU_OFFLOAD` is popped by the harness, and `--engram-config {"cpu_offload": true}`
replaces it.

## Build and check

From the arc-prize-2026 repo:

```bash
python3 scripts/runtime_0310/port_overlay.py --his-overlay <his overlay tar> --vllm-repo <vllm clone> --check
python3 scripts/runtime_0310/build_runtime_0310.py --out <dataset dir> --his-identity <his PATCH_IDENTITY.json> [--download]
python3 scripts/runtime_0310/validate_runtime_dataset.py <dataset dir>
python3 scripts/runtime_0310/harness_contract_check.py --setup-commands <bundle>/setup_commands.json \
    --bundle-dir <bundle> --dataset <dataset dir> --pins scripts/runtime_0310/harness_pins.json --runtime-root <dir>
# the shipped autotune tactics: the recipe edit regenerated from the committed cold-tuned configs
python3 scripts/runtime_0310/make_autotune_seed.py --check
# the e975732 post-install patch: generated from the same recipe edit, then his runtime + hook
python3 scripts/runtime_0310/make_kv_copy_patch.py --check --layer e975732=<his layer-27 blob> --layer v0.31.0=<layer-27 blob>
python3 scripts/runtime_0310/harness_contract_check.py --setup-commands <bundle>/setup_commands.json \
    --bundle-dir <bundle> --dataset <his dataset dir> --keep-pins \
    --kv-copy-patch scripts/runtime_0310/patch_kv_copy_chunked.py --runtime-root <dir>
# the chunked copy against the stock gather (CPU, the runtime's torch)
python3 scripts/runtime_0310/rt_env.py <runtime root> <manifest> -- \
    python3 scripts/runtime_0310/test_kv_copy_chunked.py <stock utils.py> <patched utils.py>
```
