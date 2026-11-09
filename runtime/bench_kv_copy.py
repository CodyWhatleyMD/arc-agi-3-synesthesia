#!/usr/bin/env python3
"""copy_kv_cache_blocks_inplace in isolation on the GPU: copy temporary and time per chunk size.

Imports the installed runtime's vllm.v1.worker.utils (run it under rt_env.py), builds a KV storage of
--num-blocks scheduler blocks of --block-bytes each (default 22,843,392 B = one Qwen3.8 block, as the
serving runs measured), and applies --copies copy-on-write copies (fresh destinations, random sources)
with VLLM_ARC3_KV_COPY_CHUNK = 0 (stock single gather), 1, 2, 4, 8. For each: the peak bytes allocated
during the call above what was allocated before it (torch.cuda.max_memory_allocated, deterministic),
the median CUDA time over --reps calls, and a checksum of the result, which must be the same for
every chunk size.

usage: rt_env.py ROOT MANIFEST -- python3 bench_kv_copy.py [--copies 44] [--num-blocks 120] [--reps 20]
"""
from __future__ import annotations

import argparse
import importlib
import os
import random
import statistics

import torch


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--copies", type=int, default=44)
    ap.add_argument("--num-blocks", type=int, default=120)
    ap.add_argument("--block-bytes", type=int, default=22_843_392)
    ap.add_argument("--reps", type=int, default=20)
    ap.add_argument("--chunks", default="0,1,2,4,8")
    args = ap.parse_args()
    import vllm.v1.worker.utils as U
    from vllm.v1.core.kv_cache_utils import KVCacheBlockCopy

    dev = torch.device("cuda")
    r = random.Random(0)
    ids = list(range(args.num_blocks))
    r.shuffle(ids)
    dst, pool = ids[: args.copies], ids[args.copies:]
    copies = [KVCacheBlockCopy(r.choice(pool), d) for d in dst]
    print(f"{U.__file__}\n{args.copies} copies of {args.block_bytes:,} B blocks in a "
          f"{args.num_blocks}-block storage ({args.num_blocks * args.block_bytes / 2**30:.2f} GiB)")
    print("| VLLM_ARC3_KV_COPY_CHUNK | peak temporary | = blocks | median time | checksum |")
    print("|---|---|---|---|---|")
    sums = set()
    for chunk in [int(c) for c in args.chunks.split(",")]:
        os.environ["VLLM_ARC3_KV_COPY_CHUNK"] = str(chunk)
        U = importlib.reload(U)
        assert U.ARC3_KV_COPY_CHUNK == chunk
        gen = torch.Generator(device=dev).manual_seed(1)
        cache = torch.randint(0, 256, (args.num_blocks, args.block_bytes), dtype=torch.uint8, device=dev,
                              generator=gen)
        U.copy_kv_cache_blocks_inplace([cache], args.num_blocks, copies)  # warm-up (also the result)
        torch.cuda.synchronize()
        words = cache.view(torch.int32)  # sums without an int64 copy of the storage
        checksum = (int(words[dst].sum(dtype=torch.int64).item()), int(words.sum(dtype=torch.int64).item()))
        sums.add(checksum)
        torch.cuda.empty_cache()
        base = torch.cuda.memory_allocated()
        torch.cuda.reset_peak_memory_stats()
        U.copy_kv_cache_blocks_inplace([cache], args.num_blocks, copies)
        torch.cuda.synchronize()
        peak = torch.cuda.max_memory_allocated() - base
        times = []
        for _ in range(args.reps):
            a, b = torch.cuda.Event(enable_timing=True), torch.cuda.Event(enable_timing=True)
            a.record()
            U.copy_kv_cache_blocks_inplace([cache], args.num_blocks, copies)
            b.record()
            torch.cuda.synchronize()
            times.append(a.elapsed_time(b))
        print(f"| {chunk} | {peak / 2**20:.1f} MiB | {peak / args.block_bytes:.2f} | "
              f"{statistics.median(times):.2f} ms | {checksum[0]:x} |")
        del cache
        torch.cuda.empty_cache()
    print("results identical across chunk sizes:", len(sums) == 1)


if __name__ == "__main__":
    main()
