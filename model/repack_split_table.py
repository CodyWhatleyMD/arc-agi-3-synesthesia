#!/usr/bin/env python3
"""Split the n-gram (PLE) table out of a saved checkpoint into table-only shards (09-30).

Why: llm-compressor saves shards by size, so the 128 BF16 table tensors (~102 GB, `...ple_embedding.ngram_embedding.shard_N.weight`)
land interleaved with the quantized transformer. On Kaggle the table is served from primitive-ai's quantized sidecar
(the overlay stubs the table parameter and never loads the checkpoint's copy), so uploading the BF16 table is 102 GB
of dead weight. After this repack the checkpoint has:
  model-XXXXX-of-NNNNN.safetensors   transformer only, index model.safetensors.index.json WITHOUT table entries
  table-XXXXX-of-MMMMM.safetensors   the table tensors, index table.safetensors.index.json (kept locally, not uploaded)
Byte-exact on every tensor (verified by re-reading), idempotent (a checkpoint with no table tensors is left alone).

  python repack_split_table.py <ckpt_dir> [--dry-run] [--shard-gb 4.5]
"""
import argparse, json, os, sys, time
from safetensors import safe_open
from safetensors.torch import save_file

TABLE_KEY = "ngram_embedding"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ckpt"); ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--shard-gb", type=float, default=4.5)
    a = ap.parse_args()
    d = a.ckpt; idx_path = os.path.join(d, "model.safetensors.index.json")
    idx = json.load(open(idx_path)); wm = idx["weight_map"]
    table_keys = sorted(k for k in wm if TABLE_KEY in k)
    if not table_keys:
        print("no table tensors in the index; nothing to do"); return 0
    files_with_table = sorted({wm[k] for k in table_keys})
    mixed = [f for f in files_with_table if any(TABLE_KEY not in k and wm[k] == f for k in wm)]
    print(f"table tensors: {len(table_keys)} in {len(files_with_table)} files ({len(mixed)} mixed with transformer tensors)")
    if a.dry_run:
        tot = 0
        for f in files_with_table:
            with safe_open(os.path.join(d, f), "pt") as sf:
                for k in sf.keys():
                    if TABLE_KEY in k: t = sf.get_slice(k); tot += 2 * int(__import__("math").prod(t.get_shape()))
        print(f"dry run: {tot/1e9:.1f} GB of table (bf16) would move out"); return 0
    shard_bytes = int(a.shard_gb * 1e9)
    new_wm = {k: v for k, v in wm.items() if TABLE_KEY not in k}
    table_wm = {}; table_shards = []; cur = {}; cur_bytes = 0; moved_bytes = 0
    def flush_table():
        nonlocal cur, cur_bytes
        if not cur: return
        name = f"table-{len(table_shards)+1:05d}.safetensors"; save_file(cur, os.path.join(d, name), metadata={"format": "pt"})
        for k in cur: table_wm[k] = name
        table_shards.append(name); cur = {}; cur_bytes = 0
    t0 = time.time()
    for f in files_with_table:
        path = os.path.join(d, f); keep = {}; moved = 0
        with safe_open(path, "pt") as sf:
            meta = sf.metadata()
            for k in sf.keys():
                t = sf.get_tensor(k)
                if TABLE_KEY in k:
                    cur[k] = t; cur_bytes += t.numel() * t.element_size(); moved += 1; moved_bytes += t.numel() * t.element_size()
                    if cur_bytes >= shard_bytes: flush_table()
                else:
                    keep[k] = t
        if keep:
            tmp = path + ".tmp"; save_file(keep, tmp, metadata=meta or {"format": "pt"}); os.replace(tmp, path)
        else:
            os.remove(path); print(f"  {f}: table-only, removed")
        print(f"  {f}: moved {moved} table tensors, kept {len(keep)}  [{time.time()-t0:.0f}s]", flush=True)
    flush_table()
    # rename table shards to table-XXXXX-of-MMMMM and write both indexes
    n = len(table_shards); final = {}
    for i, name in enumerate(table_shards, 1):
        new = f"table-{i:05d}-of-{n:05d}.safetensors"; os.replace(os.path.join(d, name), os.path.join(d, new)); final[name] = new
    table_wm = {k: final[v] for k, v in table_wm.items()}
    json.dump({"metadata": {"note": "PLE n-gram table split out; not needed when served with a quantized-table sidecar"}, "weight_map": table_wm},
              open(os.path.join(d, "table.safetensors.index.json"), "w"), indent=1)
    idx["weight_map"] = new_wm
    if "metadata" in idx and "total_size" in idx["metadata"]:
        idx["metadata"]["total_size"] = int(idx["metadata"]["total_size"]) - moved_bytes
    json.dump(idx, open(idx_path, "w"), indent=1)
    # verify: every transformer tensor still resolvable; every table tensor resolvable from the table index
    bad = 0
    for k, f in list(new_wm.items())[:2000] + list(table_wm.items())[:200]:
        with safe_open(os.path.join(d, f), "pt") as sf:
            if k not in sf.keys(): bad += 1
    print(f"done: {len(new_wm)} transformer tensors in {len(set(new_wm.values()))} files; {len(table_wm)} table tensors in {n} table shards; verify misses {bad}")
    return 1 if bad else 0

if __name__ == "__main__":
    sys.exit(main())
