#!/usr/bin/env python3
"""Reshard a safetensors checkpoint into small files, copying every tensor's raw bytes unchanged (the investigator, 2026-10-18:
"reshard and reupload the model").

Why: Han Solo's shard prefetcher (in the harness's vLLM watchdog) keeps an 8 GiB read-ahead window and skips files whose
names start with "ple-". Our v2.2 checkpoint has four 18.6 GiB GPU shards, larger than the window, so each was read on
one stream at single-stream NFS speed (findings 216d/216h: 37-351 MiB/s; 28 min to server-ready in v8), and its PLE
shards were named model-ple-*, so the prefetcher treated them as GPU shards too. His checkpoint uses ~1.4 GB GPU files.

What: every tensor of the source index is written, byte for byte, into GPU shards of at most --max-bytes (default
1.4e9; a tensor larger than that gets its own file), in index-file order; PLE files (source names containing "-ple-")
are copied whole under the name ple-<n>-of-<N>. Non-safetensors files are copied as they are. A new
model.safetensors.index.json maps every tensor to its new file. Each output file keeps its source's __metadata__.

Verify (--verify): re-opens every output file, and for every tensor compares dtype, shape and the SHA-256 of its bytes
with the source. Exit 1 on any mismatch.

usage: reshard_safetensors.py SRC_DIR DST_DIR [--max-bytes N] [--verify]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import shutil
import struct
import sys

CHUNK = 64 << 20


def read_header(path: pathlib.Path) -> tuple[dict, int]:
    """Return (header dict, data start offset) of a safetensors file."""
    with path.open("rb") as fh:
        n = struct.unpack("<Q", fh.read(8))[0]
        header = json.loads(fh.read(n))
    return header, 8 + n


def copy_range(src, dst, start: int, length: int) -> None:
    src.seek(start)
    left = length
    while left:
        buf = src.read(min(CHUNK, left))
        if not buf:
            raise IOError("short read")
        dst.write(buf)
        left -= len(buf)


def write_shard(out: pathlib.Path, items: list[tuple[str, dict, pathlib.Path, int]], metadata: dict | None) -> None:
    """items: (name, src tensor info, src path, src data start). Writes header then the raw bytes, in order."""
    header, offset = {}, 0
    for name, info, _, _ in items:
        begin, end = info["data_offsets"]
        header[name] = {"dtype": info["dtype"], "shape": info["shape"], "data_offsets": [offset, offset + end - begin]}
        offset += end - begin
    if metadata:
        header["__metadata__"] = metadata
    blob = json.dumps(header, separators=(",", ":")).encode()
    blob += b" " * ((8 - len(blob) % 8) % 8)          # the format pads the header to 8-byte alignment
    handles: dict[pathlib.Path, object] = {}
    try:
        with out.open("wb") as dst:
            dst.write(struct.pack("<Q", len(blob)))
            dst.write(blob)
            for name, info, path, start in items:
                fh = handles.get(path) or handles.setdefault(path, path.open("rb"))
                begin, end = info["data_offsets"]
                copy_range(fh, dst, start + begin, end - begin)
    finally:
        for fh in handles.values():
            fh.close()


_HANDLES: dict[pathlib.Path, object] = {}


def tensor_digest(path: pathlib.Path, start: int, info: dict) -> str:
    begin, end = info["data_offsets"]
    h = hashlib.sha256()
    fh = _HANDLES.get(path) or _HANDLES.setdefault(path, path.open("rb"))
    fh.seek(start + begin)
    left = end - begin
    while left:
        buf = fh.read(min(CHUNK, left))
        h.update(buf)
        left -= len(buf)
    return h.hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--max-bytes", type=int, default=1_400_000_000)
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--ple-max-bytes", type=int, default=0, help="also repack the PLE files into ple-NNNNN files of at most this many bytes (0 = copy them whole, as before)")
    a = ap.parse_args()
    src, dst = pathlib.Path(a.src), pathlib.Path(a.dst)
    dst.mkdir(parents=True, exist_ok=True)
    index = json.loads((src / "model.safetensors.index.json").read_text())
    weight_map: dict[str, str] = index["weight_map"]
    files = list(dict.fromkeys(weight_map.values()))        # index order of first appearance
    ple_files = [f for f in files if "-ple-" in f]
    gpu_files = [f for f in files if f not in ple_files]

    # plan the GPU shards: tensors in file order (header order), cut at max-bytes
    headers = {f: read_header(src / f) for f in files}
    groups: list[list[tuple[str, dict, pathlib.Path, int]]] = [[]]
    size = 0
    metas = set()
    for f in gpu_files:
        header, start = headers[f]
        metas.add(json.dumps(header.get("__metadata__"), sort_keys=True))
        tensors = sorted(((k, v) for k, v in header.items() if k != "__metadata__"), key=lambda kv: kv[1]["data_offsets"][0])
        for name, info in tensors:
            n = info["data_offsets"][1] - info["data_offsets"][0]
            if groups[-1] and size + n > a.max_bytes:
                groups.append([]); size = 0
            groups[-1].append((name, info, src / f, start)); size += n
    if len(metas) > 1:
        print(f"note: GPU source files carry {len(metas)} different __metadata__ blocks; the first is used: {sorted(metas)}")
    gpu_meta = json.loads(sorted(metas)[0]) if metas else None
    new_map: dict[str, str] = {}
    total = 0
    for i, items in enumerate(groups, 1):
        name = f"gpu-{i:05d}-of-{len(groups):05d}.safetensors"
        write_shard(dst / name, items, gpu_meta)
        for t, info, _, _ in items:
            new_map[t] = name
            total += info["data_offsets"][1] - info["data_offsets"][0]
        if i % 10 == 0 or i == len(groups):
            print(f"gpu shard {i}/{len(groups)} written", flush=True)
    if a.ple_max_bytes:
        # repack the PLE tensors the same way as the GPU ones (a Kaggle Model instance holds at most 50 files)
        pgroups: list[list[tuple[str, dict, pathlib.Path, int]]] = [[]]
        psize = 0
        pmeta = None
        for f in ple_files:
            header, start = headers[f]
            pmeta = pmeta or header.get("__metadata__")
            tensors = sorted(((k, v) for k, v in header.items() if k != "__metadata__"), key=lambda kv: kv[1]["data_offsets"][0])
            for name, info in tensors:
                n = info["data_offsets"][1] - info["data_offsets"][0]
                if pgroups[-1] and psize + n > a.ple_max_bytes:
                    pgroups.append([]); psize = 0
                pgroups[-1].append((name, info, src / f, start)); psize += n
        for i, items in enumerate(pgroups, 1):
            name = f"ple-{i:05d}-of-{len(pgroups):05d}.safetensors"
            write_shard(dst / name, items, pmeta)
            for t, info, _, _ in items:
                new_map[t] = name
                total += info["data_offsets"][1] - info["data_offsets"][0]
            print(f"ple shard {i}/{len(pgroups)} written", flush=True)
        ple_files = [f"ple-{i:05d}" for i in range(1, len(pgroups) + 1)]  # for the summary line only
    else:
        for i, f in enumerate(ple_files, 1):
            name = f"ple-{i:05d}-of-{len(ple_files):05d}.safetensors"
            shutil.copyfile(src / f, dst / name)
            header, _ = headers[f]
            for t, info in header.items():
                if t != "__metadata__":
                    new_map[t] = name
                    total += info["data_offsets"][1] - info["data_offsets"][0]
            print(f"ple shard {i}/{len(ple_files)} copied", flush=True)
    missing = set(weight_map) - set(new_map)
    if missing:
        raise SystemExit(f"{len(missing)} tensors were not written, e.g. {sorted(missing)[:3]}")
    for p in src.iterdir():
        if p.is_file() and not p.name.endswith(".safetensors") and p.name not in ("model.safetensors.index.json", "dataset-metadata.json"):
            shutil.copyfile(p, dst / p.name)
    (dst / "model.safetensors.index.json").write_text(json.dumps(
        {"metadata": {**index.get("metadata", {}), "total_size": total}, "weight_map": new_map}, indent=2))
    print(f"wrote {len(groups)} GPU shards + {len(ple_files)} PLE files; {len(new_map)} tensors, {total/1e9:.1f} GB")

    if a.verify:
        new_index = json.loads((dst / "model.safetensors.index.json").read_text())["weight_map"]
        new_headers = {f: read_header(dst / f) for f in set(new_index.values())}
        bad = 0
        for k, (t, f_old) in enumerate(weight_map.items()):
            h_old, s_old = headers[f_old]; i_old = h_old[t]
            h_new, s_new = new_headers[new_index[t]]; i_new = h_new[t]
            if (i_old["dtype"], i_old["shape"]) != (i_new["dtype"], i_new["shape"]) or \
               tensor_digest(src / f_old, s_old, i_old) != tensor_digest(dst / new_index[t], s_new, i_new):
                bad += 1
                print(f"MISMATCH {t}")
            if (k + 1) % 50000 == 0:
                print(f"verified {k + 1}/{len(weight_map)}", flush=True)
        print(f"verify: {len(weight_map)} tensors, {bad} mismatches")
        sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
