#!/usr/bin/env python3
"""Time the HC down+inject projection at the padded MTP3 decode rows: his SM120 GEMM vs upstream's fused kernel.

At e975732 Han Solo's rc3 SM120 GEMM served input_mix_weight_down_block_inject (336 x 10240, BF16)
at M = 40/44/48/52/56/64, followed by the separate hc_silu op. vLLM v0.31.0 (#58957) routes this
projection through a fused CuTe-DSL down+SiLU kernel for M <= 48 instead, so in the ported runtime
his GEMM serves it only at M = 52/56/64. This times both paths on the visible GPU (CUDA graphs,
median of repeated replays) and checks they agree, so the dispatch choice rests on a measurement.

usage (inside rt_env.py): bench_hc_down.py [--iters 2000]
"""
from __future__ import annotations

import argparse
import statistics

import torch

from vllm.models.qwen4_exp.nvidia.arc3_sm120_gemm import GEMM_ROWS, PROJECTIONS, run_gemm
from vllm.models.qwen4_exp.nvidia.ops.cute_dsl.hc_down_silu import MAX_FUSED_M, hc_down_silu
from vllm.models.qwen4_exp.nvidia.ops.hc import hc_silu

RANK, HC, K = 320, 4, 10240
N = 336  # rank + hc + pad to 16


def graph_time(fn, iters: int) -> float:
    """Median microseconds per call of fn() replayed in a CUDA graph."""
    stream = torch.cuda.Stream()
    stream.wait_stream(torch.cuda.current_stream())
    with torch.cuda.stream(stream):
        for _ in range(3):
            fn()
    torch.cuda.current_stream().wait_stream(stream)
    graph = torch.cuda.CUDAGraph()
    with torch.cuda.graph(graph):
        for _ in range(20):
            fn()
    samples = []
    for _ in range(max(iters // 20, 5)):
        start, end = torch.cuda.Event(enable_timing=True), torch.cuda.Event(enable_timing=True)
        start.record()
        graph.replay()
        end.record()
        end.synchronize()
        samples.append(start.elapsed_time(end) * 1000 / 20)
    return statistics.median(samples)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--iters", type=int, default=2000)
    ap.add_argument("--all-m", action="store_true", help="every decode row up to 64, with the stock path")
    args = ap.parse_args()
    torch.manual_seed(0)
    dev = torch.device("cuda")
    print("device:", torch.cuda.get_device_name(dev), "capability", torch.cuda.get_device_capability(dev))
    plan = PROJECTIONS["mlp_hyper_connection.input_mix_weight_down_block_inject"][1]
    weight = (torch.randn(N, K, device=dev) * 0.02).to(torch.bfloat16)
    rows = []
    rows_m = (1, 2, 4, 8, 16, 24, 32, 36, 40, 44, 48, 52, 56, 64) if args.all_m else (40, 44, 48, 52, 56, 64)
    for m in rows_m:
        x = torch.randn(m, K, device=dev).to(torch.bfloat16)

        def stock_path():
            # e975732 below his GEMM rows: the unquantized linear (cuBLAS), then the split and hc_silu op
            out = torch.nn.functional.linear(x, weight)
            lora, inj, _ = out.split([RANK, HC, N - RANK - HC], dim=-1)
            return hc_silu(lora, HC), inj

        def his_path():
            out = run_gemm(x, weight, plan)
            lora, inj, _ = out.split([RANK, HC, N - RANK - HC], dim=-1)
            return hc_silu(lora, HC), inj

        def fused_path():
            return hc_down_silu(x, weight, RANK, HC)

        row = {"M": m, "stock_us": round(graph_time(stock_path, args.iters), 2)}
        if m in GEMM_ROWS:
            ref_full = (x.float() @ weight.float().T)
            his_lora, his_inj = his_path()
            row["his_us"] = round(graph_time(his_path, args.iters), 2)
            row["his_inj_rel_err"] = float((his_inj.float() - ref_full[:, RANK:RANK + HC]).norm()
                                           / ref_full[:, RANK:RANK + HC].norm())
        else:
            his_lora, his_inj = stock_path()
        if m <= MAX_FUSED_M:
            f_lora, f_inj = fused_path()
            row["fused_us"] = round(graph_time(fused_path, args.iters), 2)
            row["lora_max_abs_diff_vs_his"] = float((f_lora.float() - his_lora.float()).abs().max())
            row["inj_max_abs_diff_vs_his"] = float((f_inj.float() - his_inj.float()).abs().max())
        rows.append(row)
        print(row, flush=True)


if __name__ == "__main__":
    main()
