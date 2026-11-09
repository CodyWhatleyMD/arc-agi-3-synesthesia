#!/usr/bin/env python3
"""Evict a model directory's files from the page cache (posix_fadvise DONTNEED, no root needed).

Run before each serving run of a side-by-side so both runtimes load their weights cold, the way
the harness's own prefetcher evicts shards it has passed. Symlinks are followed. The kernel treats
the advice as a hint, so the script reports how much of each file stayed resident (mincore via
os.preadv is not available, so it reads /proc/meminfo's Cached before and after instead).

usage: evict_page_cache.py DIR [DIR ...]
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def cached_kib() -> int:
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("Cached:"):
            return int(line.split()[1])
    return -1


def main() -> None:
    before = cached_kib()
    n = 0
    for d in sys.argv[1:]:
        for p in sorted(Path(d).iterdir()):
            target = p.resolve()
            if not target.is_file():
                continue
            fd = os.open(target, os.O_RDONLY)
            try:
                os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_DONTNEED)
                n += 1
            finally:
                os.close(fd)
    after = cached_kib()
    print(f"evicted {n} files; page cache {before / 2**20:.1f} GiB -> {after / 2**20:.1f} GiB")


if __name__ == "__main__":
    main()
