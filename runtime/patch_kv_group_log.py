#!/usr/bin/env python3
"""Diagnostic post-install patch: log each KV cache group's layers, spec type, block size, page size and the pool
bytes per block (vLLM 0.31.0 ARC3 runtime, our overlay's kv_cache_utils.py). Logging only; behaviour unchanged.

Written to find out why the KV pool halves (1,501,360 -> 801,730 tokens at the same 20.9 GiB) when the DFlash2
drafter's five sliding-window layers are added: the server reports 7 groups instead of MTP's 5 without saying what
is in them. Usage: python3 -I patch_kv_group_log.py DIST_PACKAGES   (hash-pinned; refuses any other file)
"""
import hashlib
import os
import sys
from pathlib import Path

TARGET = 'vllm/v1/core/kv_cache_utils.py'
OLD = '''    logger.info("kv cache group sizes %s", group_block_sizes)
'''
NEW = '''    logger.info("kv cache group sizes %s", group_block_sizes)
    # ARC3 diagnostic (patch_kv_group_log.py): what each group holds.
    for _gi, _g in enumerate(groups):
        _spec = _g.kv_cache_spec
        _first = getattr(_spec, "first_spec", _spec)
        logger.info(
            "ARC3 kv group %d: %d layers, %s/%s, block_size=%s, page_bytes=%s, layers=%s",
            _gi, len(_g.layer_names), type(_spec).__name__, type(_first).__name__,
            getattr(_spec, "block_size", None), getattr(_spec, "page_size_bytes", None),
            [n.rsplit(".", 3)[-3] if n.count(".") >= 3 else n for n in _g.layer_names][:12],
        )
    logger.info("ARC3 kv pool: num_blocks=%s", kv_cache_config.num_blocks)
'''


def main() -> None:
    target = Path(sys.argv[1]) / TARGET
    text = target.read_text()
    if "ARC3 diagnostic (patch_kv_group_log.py)" in text:
        print(f"ARC3 KV group log: already patched {target}")
        return
    if text.count(OLD) != 1:
        raise SystemExit(f"ARC3 KV group log: anchor occurs {text.count(OLD)} times in {target}; nothing written")
    tmp = target.with_name(f".{target.name}.arc3-kvlog.tmp")
    tmp.write_text(text.replace(OLD, NEW, 1))
    os.chmod(tmp, target.stat().st_mode & 0o7777)
    os.replace(tmp, target)
    print(f"ARC3 KV group log: installed {target} ({hashlib.sha256(target.read_bytes()).hexdigest()[:12]})")


if __name__ == "__main__":
    main()
