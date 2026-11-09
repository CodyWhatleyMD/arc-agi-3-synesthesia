#!/usr/bin/env python3
"""Run vLLM v0.31.0's own test files for the overlay-touched code against an extracted runtime.

The tests are copied out of the v0.31.0 worktree into a directory without the vllm/ source tree, so
`import vllm` resolves to the runtime under test, never to the checkout. Each file runs in its own
pytest process in the harness environment (rt_env.build_env) on the GPU picked by PCI bus id; the
per-file outcome counts go to a JSON file so stock and patched runs can be compared file by file.

usage: run_upstream_tests.py --runtime-root R --manifest M --tests-src WORKTREE/tests --label L
                             --out-dir O [--switch 0|1] [--bus 04:00.0] [--group core|worker|model|kernels|all]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import rt_env  # noqa: E402
from serve_validate import ALLOWED_GPU_TENANTS, cuda_index_for_bus, gpu_tenants  # noqa: E402

GROUPS = {
    "core": [
        "v1/core/test_single_type_kv_cache_manager.py", "v1/core/test_kv_cache_utils.py",
        "v1/core/test_prefix_caching.py", "v1/core/test_mamba_align_chunk_split.py",
        "v1/core/test_deferred_block_free.py", "v1/core/test_contiguous_kv_packing.py",
        "v1/core/prefix_cache/test_hybrid_prefix_cache_hit_rate.py",
        "v1/core/prefix_cache/test_mamba_eagle_resume_checkpoint.py",
        "v1/core/prefix_cache/test_partial_prefix_cache_hits.py",
        "v1/core/prefix_cache/test_partial_prefix_cache_primitives.py",
        "v1/core/test_scheduler.py",
    ],
    "worker": [
        "v1/attention/test_gdn_metadata_builder.py", "v1/attention/test_mamba_update_block_table.py",
        "v1/worker/test_mamba_hybrid_model_state.py", "v1/worker/test_mamba_utils.py",
        "v1/worker/test_gpu_batch_ordering.py", "v1/worker/test_gpu_worker.py",
        "v1/spec_decode/test_rejection_sampler_utils.py",
        "model_executor/model_loader/test_ep_weight_filter.py",
    ],
    "model": [
        "models/qwen4_exp/test_ple.py", "models/qwen4_exp/test_hc_ops.py",
        "models/qwen4_exp/test_qsa_reference.py", "models/qwen4_exp/test_config.py",
        "models/qwen4_exp/test_qsa_pre_indexer.py", "models/kimi_k3/test_kda.py",
    ],
    "kernels": [
        "kernels/mamba/test_causal_conv1d.py", "kernels/mamba/test_mamba_ssm.py",
        "kernels/fla/test_fused_sigmoid_gating_delta_rule.py", "kernels/fla/test_fused_recurrent_packed_decode.py",
        "kernels/mamba/test_gdn_forward_core_split.py", "kernels/moe/test_moe_weight_loading_padded.py",
    ],
}
SUMMARY = re.compile(r"(\d+) (passed|failed|skipped|errors?|xfailed|xpassed|deselected)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runtime-root", type=Path, required=True)
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--tests-src", type=Path, required=True)
    ap.add_argument("--work", type=Path, default=Path("/media/ignaz/model-storage-2/runtime_0310/tests_v031"))
    ap.add_argument("--testdeps", type=Path, default=Path("/media/ignaz/model-storage-2/runtime_0310/testdeps"))
    ap.add_argument("--cache-root", type=Path, required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--switch", default="0", choices=("0", "1"), help="VLLM_ARC3_GDN_RECOVERSSM")
    ap.add_argument("--bus", default="04:00.0")
    ap.add_argument("--group", default="all", choices=(*GROUPS, "all"))
    ap.add_argument("--timeout", type=int, default=3600)
    ap.add_argument("--files", nargs="*", default=None, help="run only these test files (paths under tests/)")
    ap.add_argument("--hf-online", type=Path, default=None,
                    help="let the tests fetch HF configs/tokenizers into this HF_HOME (the runtime itself stays "
                         "offline; many v0.31.0 unit tests build a ModelConfig from a hub id)")
    args = ap.parse_args()

    tenants = [t for t in gpu_tenants(args.bus) if not any(a in t for a in ALLOWED_GPU_TENANTS)]
    if tenants:
        raise SystemExit(f"REFUSING: GPU {args.bus} has compute processes: {tenants}")
    if not (args.work / "tests").exists():
        shutil.copytree(args.tests_src, args.work / "tests")
    manifest = json.loads(args.manifest.read_text())
    os.environ["PYTHONPATH"] = str(args.testdeps)  # appended after the runtime's own paths
    os.environ["VLLM_ARC3_GDN_RECOVERSSM"] = args.switch
    env = rt_env.build_env(args.runtime_root, manifest, None, args.cache_root)
    env.update({"CUDA_DEVICE_ORDER": "PCI_BUS_ID", "CUDA_VISIBLE_DEVICES": str(cuda_index_for_bus(args.bus))})
    if args.hf_online:
        args.hf_online.mkdir(parents=True, exist_ok=True)
        env.update({"HF_HUB_OFFLINE": "0", "TRANSFORMERS_OFFLINE": "0", "HF_DATASETS_OFFLINE": "0",
                    "HF_HOME": str(args.hf_online)})
    files = args.files or [f for g, fs in GROUPS.items() if args.group in (g, "all") for f in fs]
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out_json = args.out_dir / f"tests_{args.label}.json"
    results = json.loads(out_json.read_text()) if out_json.exists() else {}
    for rel in files:
        t0 = time.time()
        log = args.out_dir / f"tests_{args.label}__{rel.replace('/', '__')}.log"
        try:
            p = subprocess.run(["/usr/bin/python3", "-m", "pytest", "-q", "-p", "no:cacheprovider", "-rfE",
                                f"tests/{rel}"], cwd=args.work, env=env, capture_output=True, text=True,
                               timeout=args.timeout)
            text, rc = p.stdout + p.stderr, p.returncode
        except subprocess.TimeoutExpired as e:
            text, rc = (e.stdout or b"").decode() if isinstance(e.stdout, bytes) else (e.stdout or ""), "timeout"
        log.write_text(text)
        tail = text.strip().splitlines()[-1] if text.strip() else ""
        counts = {k if not k.startswith("error") else "errors": int(n) for n, k in SUMMARY.findall(tail)}
        results[rel] = {"rc": rc, "counts": counts, "seconds": round(time.time() - t0, 1), "tail": tail[-200:]}
        print(f"{rel}: rc={rc} {counts} ({results[rel]['seconds']}s)", flush=True)
        out_json.write_text(json.dumps(results, indent=1) + "\n")


if __name__ == "__main__":
    main()
