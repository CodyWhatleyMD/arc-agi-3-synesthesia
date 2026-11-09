#!/usr/bin/env python3
"""Validation-only view of quant v2 with ple.key_proj dequantized to BF16 (option b, 2026-10-08).

v2 quantizes ple.key_proj to FP8 (group_0, per-channel) but leaves ple.value_proj BF16, and vLLM
fuses the two into one kv_proj, which compressed-tensors refuses ("Found different quantization
schemes for the shards of ...ple.kv_proj") on both e975732 and v0.31.0. This builds a directory
that serves: every file is a symlink into the source dir except
  - the shard holding ple.key_proj, rewritten by streaming copy with key_proj.weight replaced by
    bf16(fp8 * weight_scale) and key_proj.weight_scale removed (all other tensors byte-identical),
  - model.safetensors.index.json without the weight_scale entry,
  - config.json with the key_proj target removed from group_0 and key_proj added to ignore, so
    both kv_proj shards are unquantized, as in Han Solo's quant.
This is a model variant for runtime validation, not a quant to ship.

usage: make_kpbf16_view.py SRC_MODEL_DIR DST_DIR [ORIGINAL_BF16_DIR]   (run under rt_env.py for torch)

With ORIGINAL_BF16_DIR (the lead's choice, 2026-10-08) key_proj gets the original checkpoint's exact
BF16 bytes, the tensor a key_proj-excluded quant would carry; without it, bf16(fp8 * scale).
"""
from __future__ import annotations

import json
import os
import re
import struct
import sys
from pathlib import Path

import torch

KEY = re.compile(r"\.ple\.key_proj\.weight$")


def read_header(path: Path) -> tuple[int, dict]:
    with path.open("rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        return n, json.loads(f.read(n))


def original_bytes(base: Path, name: str, shape: list[int]) -> bytes:
    """The exact bytes of a BF16 tensor in the original (unquantized) checkpoint."""
    index = json.loads((base / "model.safetensors.index.json").read_text())["weight_map"]
    shard = base / index[name]
    n, header = read_header(shard)
    meta = header[name]
    if meta["dtype"] != "BF16" or meta["shape"] != shape:
        raise SystemExit(f"{name} in {shard}: {meta['dtype']} {meta['shape']}, want BF16 {shape}")
    a, b = meta["data_offsets"]
    with shard.open("rb") as f:
        f.seek(8 + n + a)
        return f.read(b - a)


def main() -> None:
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    base = Path(sys.argv[3]) if len(sys.argv) > 3 else None  # original BF16 checkpoint, if given
    dst.mkdir(parents=True, exist_ok=True)
    index = json.loads((src / "model.safetensors.index.json").read_text())
    keys = [n for n in index["weight_map"] if KEY.search(n)]
    if not keys:
        raise SystemExit("no ple.key_proj weights")
    shards = {index["weight_map"][k] for k in keys}
    rewritten = {}
    for shard in sorted(shards):
        n, header = read_header(src / shard)
        meta = header.pop("__metadata__", None)
        data_start = 8 + n
        new_tensors: dict[str, bytes] = {}
        drop = set()
        with (src / shard).open("rb") as f:
            for k in keys:
                if index["weight_map"][k] != shard:
                    continue
                w, s = header[k], header[k + "_scale"]
                assert w["dtype"] == "F8_E4M3" and s["dtype"] == "BF16", (w, s)
                f.seek(data_start + w["data_offsets"][0])
                wt = torch.frombuffer(bytearray(f.read(w["data_offsets"][1] - w["data_offsets"][0])),
                                      dtype=torch.float8_e4m3fn).reshape(w["shape"])
                f.seek(data_start + s["data_offsets"][0])
                st = torch.frombuffer(bytearray(f.read(s["data_offsets"][1] - s["data_offsets"][0])),
                                      dtype=torch.bfloat16).reshape(s["shape"])
                deq = (wt.to(torch.float32) * st.to(torch.float32)).to(torch.bfloat16).contiguous()
                if base is not None:
                    orig = original_bytes(base, k, w["shape"])
                    ot = torch.frombuffer(bytearray(orig), dtype=torch.bfloat16).reshape(w["shape"])
                    rel = float((deq.float() - ot.float()).norm() / ot.float().norm())
                    new_tensors[k] = orig
                    print(f"{k}: original BF16 {w['shape']} from {base} (fp8 dequant vs original rel err {rel:.4f})")
                else:
                    new_tensors[k] = deq.view(torch.uint8).numpy().tobytes()
                    print(f"{k}: fp8 {w['shape']} x scale {s['shape']} -> bf16, max|w| {deq.float().abs().max():.4f}")
                drop.add(k + "_scale")
        # new header: same tensor order, offsets recomputed
        order = sorted((k for k in header if k not in drop), key=lambda k: header[k]["data_offsets"][0])
        new_header, offset = {}, 0
        for k in order:
            size = len(new_tensors[k]) if k in new_tensors else header[k]["data_offsets"][1] - header[k]["data_offsets"][0]
            dtype = "BF16" if k in new_tensors else header[k]["dtype"]
            new_header[k] = {"dtype": dtype, "shape": header[k]["shape"], "data_offsets": [offset, offset + size]}
            offset += size
        if meta is not None:
            new_header["__metadata__"] = meta
        hbytes = json.dumps(new_header, separators=(",", ":")).encode()
        hbytes += b" " * (-len(hbytes) % 8)
        out = dst / shard
        tmp = out.with_name(out.name + ".part")
        with (src / shard).open("rb") as fin, tmp.open("wb") as fout:
            fout.write(struct.pack("<Q", len(hbytes)))
            fout.write(hbytes)
            for k in order:
                if k in new_tensors:
                    fout.write(new_tensors[k])
                    continue
                a, b = header[k]["data_offsets"]
                fin.seek(data_start + a)
                left = b - a
                while left:
                    chunk = fin.read(min(left, 1 << 26))
                    fout.write(chunk)
                    left -= len(chunk)
        tmp.replace(out)
        rewritten[shard] = offset
        print(f"rewrote {shard}: {len(order)} tensors, {offset:,} data bytes")
    for k in keys:
        index["weight_map"].pop(k + "_scale", None)
    (dst / "model.safetensors.index.json").write_text(json.dumps(index, indent=2) + "\n")
    cfg = json.loads((src / "config.json").read_text())
    q = cfg["quantization_config"]
    for g in q["config_groups"].values():
        g["targets"] = [t for t in g["targets"] if t != r"re:.*ple\.key_proj$"]
    for k in keys:
        q["ignore"].append(k[: -len(".weight")])
    (dst / "config.json").write_text(json.dumps(cfg, indent=2) + "\n")
    for p in src.iterdir():
        if p.name in rewritten or p.name in ("config.json", "model.safetensors.index.json"):
            continue
        link = dst / p.name
        if link.is_symlink() or link.exists():
            link.unlink()
        os.symlink(p, link)
    print(f"view ready at {dst}")


if __name__ == "__main__":
    main()
