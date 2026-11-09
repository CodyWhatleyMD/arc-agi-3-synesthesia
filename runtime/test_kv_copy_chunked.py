#!/usr/bin/env python3
"""The bounded KV block copy against the stock single gather, byte for byte, on CPU.

copy_kv_cache_blocks_inplace and the module-level ARC3_* constants are taken verbatim from each given utils.py
(ast-extracted source) and run on CPU tensors. Checks:

  1. result: every byte of every KV cache equals the stock function's, for chunk sizes 0,1,2,3,4,5,8,64,
     on the four cache layouts the function distinguishes (one storage aliased by two layers, a uint8
     storage per layer, two layers interleaved in one storage with 2 kernel blocks per scheduler block,
     a storage longer than num_blocks rows = the unflatten path) and five copy patterns: fresh
     destinations (the copy-on-write call sites: destinations distinct and never a source, sources may
     repeat), chains (a destination is the source of a later copy), reverse chains, permutations
     (swaps, cycles, self-copies) and random sources;
  2. bound: the largest gather (rows materialised at once) is min(chunk, N) whenever at most `chunk`
     copies read a block that is also written, and N (the stock gather) otherwise;
  3. an empty copy list writes nothing; VLLM_ARC3_KV_COPY_CHUNK < 0 is rejected at import.

Run it with the runtime's torch, e.g.
  rt_env.py RUNTIME_ROOT MANIFEST -- python3 test_kv_copy_chunked.py STOCK_UTILS_PY PATCHED_UTILS_PY
"""
from __future__ import annotations

import argparse
import ast
import os
import random
import sys
from collections.abc import Iterable, Sequence
from typing import NamedTuple

import numpy as np
import torch

CHUNK_ENV = "VLLM_ARC3_KV_COPY_CHUNK"


class KVCacheBlockCopy(NamedTuple):
    src_block_id: int
    dst_block_id: int


def async_tensor_h2d(data, device=None, dtype=None, out=None):  # noqa: ARG001 - vLLM's signature
    t = torch.from_numpy(data) if isinstance(data, np.ndarray) else torch.as_tensor(data)
    return t.to(device=device, dtype=dtype)


def load_fn(path: str, chunk: int | None):
    """Exec the ARC3_* module constants and copy_kv_cache_blocks_inplace of `path` with VLLM_ARC3_KV_COPY_CHUNK=chunk."""
    src = open(path).read()
    parts = []
    for node in ast.parse(src).body:
        if isinstance(node, ast.FunctionDef) and node.name == "copy_kv_cache_blocks_inplace":
            parts.append(ast.get_source_segment(src, node))
        elif isinstance(node, (ast.Assign, ast.If)) and "ARC3_" in (ast.get_source_segment(src, node) or "").split(
                "\n", 1)[0]:
            parts.append(ast.get_source_segment(src, node))
    ns = {"np": np, "torch": torch, "os": os, "async_tensor_h2d": async_tensor_h2d, "Iterable": Iterable,
          "Sequence": Sequence, "KVCacheBlockCopy": KVCacheBlockCopy}
    old = os.environ.get(CHUNK_ENV)
    try:
        if chunk is not None:
            os.environ[CHUNK_ENV] = str(chunk)
        exec(compile("\n\n".join(parts), path, "exec"), ns)
    finally:
        if old is None:
            os.environ.pop(CHUNK_ENV, None)
        else:
            os.environ[CHUNK_ENV] = old
    return ns["copy_kv_cache_blocks_inplace"]


def make_caches(layout: str, num_blocks: int, rng: torch.Generator) -> list[torch.Tensor]:
    if layout == "shared_storage":  # one allocation, two layers alias it (same data_ptr): copied once
        raw = torch.randint(0, 256, (num_blocks, 3, 2, 5, 8), dtype=torch.uint8, generator=rng)
        base = raw.view(torch.bfloat16)
        return [base, base]
    if layout == "per_layer_fp8":  # a uint8 storage per layer
        return [torch.randint(0, 256, (num_blocks, 2, 4, 16), dtype=torch.uint8, generator=rng) for _ in range(3)]
    if layout == "interleaved_views":  # 2 kernel blocks per scheduler block, 2 layers interleaved in one storage
        big = torch.randn(num_blocks * 2, 2, 4, 6, generator=rng, dtype=torch.float32)
        return [big[:, 0], big[:, 1]]
    if layout == "padded_unflatten":  # storage longer than num_blocks rows: the unflatten path, bf16
        return [torch.randn((num_blocks + 3) * 2, 4, 6, generator=rng).to(torch.bfloat16)[: num_blocks * 2]
                for _ in range(2)]
    raise ValueError(layout)


def storage_bytes(t: torch.Tensor) -> bytes:
    """Every byte of the tensor's storage (NaN-safe, layout-independent)."""
    return bytes(torch.empty(0, dtype=torch.uint8).set_(t.untyped_storage()).numpy())


def same_result(stock, patched, layout: str, num_blocks: int, copies, seed: int) -> bool:
    caches_a = make_caches(layout, num_blocks, torch.Generator().manual_seed(seed))
    caches_b = make_caches(layout, num_blocks, torch.Generator().manual_seed(seed))
    stock(caches_a, num_blocks, copies)
    patched(caches_b, num_blocks, copies)
    return all(storage_bytes(a) == storage_bytes(b) for a, b in zip(caches_a, caches_b))


class Tracking(torch.Tensor):
    """Records the most rows one advanced-indexing gather materialises (the copy temporary)."""

    max_rows = 0

    @classmethod
    def __torch_function__(cls, func, types, args=(), kwargs=None):
        out = super().__torch_function__(func, types, args, kwargs or {})
        if func is torch.Tensor.__getitem__ and isinstance(args[1], torch.Tensor) and isinstance(out, torch.Tensor):
            Tracking.max_rows = max(Tracking.max_rows, out.shape[0])
        return out


def largest_gather(fn, copies, num_blocks: int) -> int:
    cache = torch.randn((num_blocks + 3) * 2, 4, 6)[: num_blocks * 2].as_subclass(Tracking)
    Tracking.max_rows = 0
    fn([cache], num_blocks, copies)
    return Tracking.max_rows


def gen_copies(kind: str, n: int, num_blocks: int, r: random.Random) -> list[KVCacheBlockCopy]:
    ids = list(range(num_blocks))
    r.shuffle(ids)
    dst = ids[:n]
    if kind == "fresh_dst":
        src = [r.choice(ids[n:]) for _ in range(n)]
    elif kind == "chain":
        src = [r.choice(ids[n:]) if i == 0 or r.random() < 0.5 else dst[r.randrange(i)] for i in range(n)]
    elif kind == "reverse_chain":
        src = [r.choice(ids[n:]) if i == n - 1 or r.random() < 0.5 else dst[r.randrange(i + 1, n)] for i in range(n)]
    elif kind == "permutation":
        src = dst[:]
        r.shuffle(src)
    elif kind == "random":
        src = [r.randrange(num_blocks) for _ in range(n)]
    else:
        raise ValueError(kind)
    return [KVCacheBlockCopy(s, d) for s, d in zip(src, dst)]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("stock")
    ap.add_argument("patched")
    ap.add_argument("--trials", type=int, default=25)
    args = ap.parse_args()
    stock = load_fn(args.stock, None)
    r = random.Random(1234)
    layouts = ("shared_storage", "per_layer_fp8", "interleaved_views", "padded_unflatten")
    kinds = ("fresh_dst", "chain", "reverse_chain", "permutation", "random")

    cases = mismatches = 0
    for chunk in (0, 1, 2, 3, 4, 5, 8, 64):
        patched = load_fn(args.patched, chunk)
        for layout in layouts:
            for kind in kinds:
                for _ in range(args.trials):
                    n = r.choice([1, 2, 3, 4, 5, 7, 8, 9, 16, 31, 32, 33, 44, 45])
                    num_blocks = n * 2 + r.randrange(1, 9)
                    copies = gen_copies(kind, n, num_blocks, r)
                    cases += 1
                    if not same_result(stock, patched, layout, num_blocks, copies, r.randrange(1 << 30)):
                        mismatches += 1
                        if mismatches <= 5:
                            print(f"MISMATCH chunk={chunk} layout={layout} kind={kind} n={n}: {copies}")
    print(f"1. result: {cases - mismatches}/{cases} cases byte-identical to the stock function")

    bounds = violations = 0
    for chunk in (1, 2, 4, 8):
        patched = load_fn(args.patched, chunk)
        for kind in kinds:
            for _ in range(args.trials):
                n = r.choice([5, 9, 16, 32, 44])
                num_blocks = n * 2 + 4
                copies = gen_copies(kind, n, num_blocks, r)
                dst = {c.dst_block_id for c in copies}
                reads_written = sum(c.src_block_id in dst for c in copies)
                expect = min(chunk, n) if reads_written <= chunk else n
                got = largest_gather(patched, copies, num_blocks)
                bounds += 1
                if got != expect:
                    violations += 1
                    if violations <= 5:
                        print(f"BOUND chunk={chunk} kind={kind} n={n} reads_written={reads_written}: "
                              f"gathered {got} rows, expected {expect}")
    print(f"2. bound: {bounds - violations}/{bounds} cases gather exactly the expected number of rows")

    patched = load_fn(args.patched, 4)
    caches = make_caches("per_layer_fp8", 8, torch.Generator().manual_seed(0))
    before = [storage_bytes(c) for c in caches]
    patched(caches, 8, [])
    empty_ok = before == [storage_bytes(c) for c in caches]
    try:
        load_fn(args.patched, -1)
        negative_ok = False
    except ValueError:
        negative_ok = True
    print(f"3. empty copy list writes nothing: {empty_ok}; {CHUNK_ENV}=-1 rejected: {negative_ok}")
    print(f"torch {torch.__version__}")
    sys.exit(0 if mismatches == 0 and violations == 0 and empty_ok and negative_ok else 1)


if __name__ == "__main__":
    main()
