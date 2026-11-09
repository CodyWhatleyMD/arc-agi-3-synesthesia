# Bounded KV block copies (arc-prize-2026, 2026-10-08). MRV2's copy_kv_cache_blocks_inplace gathered all
# N copy-on-write blocks at once (`blocks[dst] = blocks[src]` materialises blocks[src]), so a burst of
# prefix-cache resumes needed N blocks of free memory: 32 Qwen3.8 blocks are ~0.7 GiB, more than
# --gpu-memory-utilization 0.98 leaves, and a cold-start run died with OOM (e975732 has the same code and
# the same copy traffic, with a 44-block burst). Copies now run in chunks of VLLM_ARC3_KV_COPY_CHUNK blocks
# (default 4; 0 restores the single gather) with the single gather's result: there every source is read
# before any destination is written, so copies whose source is also a destination are moved into the first
# chunk (read before anything is written) and all other sources are never written. More such copies than one
# chunk holds fall back to the single gather. The copy-on-write call sites are not expected to produce such
# copies (their destinations are blocks allocated in the same step; none in 154 instrumented calls); the
# reordering keeps the result exact regardless.
EDITS = [
(
"import math\n",
"import math\n"
"import os\n",
),
(
"def copy_kv_cache_blocks_inplace(\n",
"# ARC3: copy_kv_cache_blocks_inplace gathers at most this many blocks at a time; 0 = all at once (stock).\n"
"ARC3_KV_COPY_CHUNK = int(os.environ.get(\"VLLM_ARC3_KV_COPY_CHUNK\", \"4\"))\n"
"if ARC3_KV_COPY_CHUNK < 0:\n"
"    raise ValueError(f\"VLLM_ARC3_KV_COPY_CHUNK={ARC3_KV_COPY_CHUNK}: must be >= 0\")\n"
"\n"
"\n"
"def copy_kv_cache_blocks_inplace(\n",
),
(
"    indices_np = np.array(kv_cache_block_copies, dtype=np.int64)\n",
"    indices_np = np.array(kv_cache_block_copies, dtype=np.int64)\n"
"    # ARC3: copy at most `chunk` blocks at a time, with the single gather's result. That gather reads\n"
"    # every source before writing any destination, so copies whose source is also a destination go\n"
"    # first, together in one chunk; no other source is ever written.\n"
"    chunk = ARC3_KV_COPY_CHUNK\n"
"    if chunk and len(indices_np) > chunk:\n"
"        reads_written = np.isin(indices_np[:, 0], indices_np[:, 1])\n"
"        num_first = int(reads_written.sum())\n"
"        if num_first > chunk:\n"
"            chunk = 0\n"
"        elif num_first:\n"
"            indices_np = np.concatenate(\n"
"                (indices_np[reads_written], indices_np[~reads_written])\n"
"            )\n",
),
(
"        blocks[dst] = blocks[src]\n",
"        if chunk and len(indices_np) > chunk:\n"
"            for start in range(0, len(indices_np), chunk):\n"
"                stop = start + chunk\n"
"                blocks[dst[start:stop]] = blocks[src[start:stop]]\n"
"        else:\n"
"            blocks[dst] = blocks[src]\n",
),
]
