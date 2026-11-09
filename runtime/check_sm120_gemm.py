#!/usr/bin/env python3
"""Numerics of the ARC3 SM120 GEMM plans on the visible GPU, in the spirit of his test_sm120_gemm.py.

His dataset ships no tests, so this re-derives the core of his rc3 suite from its VALIDATION notes:
for every projection plan at every GEMM row (M = 40/44/48/52/56/64), the custom GEMM's output vs
FP32 (relative RMS, worst over seeds), never worse than torch's own BF16 matmul at the same M, and
CUDA-graph replay bit-identical to eager. Synthetic weights; not a model-quality test.

usage (inside rt_env.py): check_sm120_gemm.py [--seeds 5]
"""
from __future__ import annotations

import argparse

import torch

from vllm.models.qwen4_exp.nvidia.arc3_sm120_gemm import GEMM_ROWS, PROJECTIONS, run_gemm


def rel_rms(a: torch.Tensor, ref: torch.Tensor) -> float:
    return float((a.float() - ref).pow(2).mean().sqrt() / ref.pow(2).mean().sqrt())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=5)
    args = ap.parse_args()
    dev = torch.device("cuda")
    print("device:", torch.cuda.get_device_name(dev), torch.cuda.get_device_capability(dev))
    failures = 0
    for name, ((n, k), plan) in PROJECTIONS.items():
        for m in GEMM_ROWS:
            worst_custom = worst_torch = 0.0
            graph_equal = True
            for seed in range(args.seeds):
                g = torch.Generator(device=dev).manual_seed(seed)
                x = torch.randn(m, k, device=dev, generator=g).to(torch.bfloat16)
                w = (torch.randn(n, k, device=dev, generator=g) * k ** -0.5).to(torch.bfloat16)
                ref = x.float() @ w.float().T
                out = run_gemm(x, w, plan)
                worst_custom = max(worst_custom, rel_rms(out, ref))
                worst_torch = max(worst_torch, rel_rms(x @ w.T, ref))
                static_out = torch.empty_like(out)
                s = torch.cuda.Stream()
                s.wait_stream(torch.cuda.current_stream())
                with torch.cuda.stream(s):
                    static_out.copy_(run_gemm(x, w, plan))
                torch.cuda.current_stream().wait_stream(s)
                graph = torch.cuda.CUDAGraph()
                with torch.cuda.graph(graph):
                    static_out.copy_(run_gemm(x, w, plan))
                graph.replay()
                torch.cuda.synchronize()
                graph_equal &= bool(torch.equal(static_out, out))
            ok = worst_custom <= worst_torch * 1.0001 and graph_equal
            failures += not ok
            print(f"{'OK ' if ok else 'BAD'} {name:58s} M={m:2d} rel_rms custom {worst_custom:.5f} "
                  f"torch-bf16 {worst_torch:.5f} graph==eager {graph_equal}", flush=True)
    print(f"{len(PROJECTIONS) * len(GEMM_ROWS)} plan x row checks, {failures} failures")


if __name__ == "__main__":
    main()
