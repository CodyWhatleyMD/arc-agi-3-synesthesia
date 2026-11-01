# Pre-statement: pinned-rounding arm (2026-11-01, written before any arm run)

**Arm:** v37 (harness 8552964) + `ARM_PINNED_ROUND_MB=1024`; harness 2c51989 on branch `pinned-round` (one change:
setup_commands.json appends `pinned_max_round_threshold_mb:1024` to the server's `PYTORCH_CUDA_ALLOC_CONF`; unset =
8552964 exactly). Kept off main and off v37's harness dataset (Cody: "keep any major alterations separate from the main").

**Why (measured before this arm):** PyTorch's pinned host allocator rounds a pinned allocation up to the next power of
two. torch 2.13.0+cu130, one pinned `torch.empty` of 8.64 GiB: unset 15.86 / 16.25 GiB of host memory; with the key in
`PYTORCH_ALLOC_CONF` 8.55 / 8.75; with the key appended to the legacy `PYTORCH_CUDA_ALLOC_CONF` 9.79; with the key in
`PYTORCH_ALLOC_CONF` while the legacy variable is set (the server's case) 18.00, i.e. ignored. The PLE table is one
pinned allocation of ~95.4 GiB (`Qwen4ExpPLEPinnedHostEmbedding.allocate_embedding_weight`), so today it takes 128 GiB.
setup_commands.json pops `PYTORCH_ALLOC_CONF` and sets `PYTORCH_CUDA_ALLOC_CONF='expandable_segments:False'`; the 10-04
fix for the same rounding was not carried into this harness. Load audit (notes/hidden_path_audit_load_2026-11-01.md,
finding 1): loader idle on big shards 2-4 tracks host headroom across 12 runs (64-459 s at 5-9 GiB available; ~1 s in
the two runs at 21-24 GiB).

**Predictions** (single runs, so only large effects are read):
1. vLLM's `Available RAM` line at the target-weight load rises by >= 25 GiB versus the comparator on the same machine
   (expected ~32.6 GiB: 128 - 95.4). REFUTED if the rise is < 15 GiB.
2. Kaggle: loader idle on big shards 2-4 (sum of loader_passed - prefetch_finished, vllm-shard-prefetch.json) <= 30 s,
   versus v37's ~128 s (shard loader/read 79/30, 29/28, 101/23 s). REFUTED if >= 60 s (the audit's lowest stalled run).
3. Kaggle: `Loading weights took` (target) shorter than v37's by roughly the idle removed. Reported, not gated.
4. Public score: no prediction. One run against v37 (51.37) and the control pool (n=7, mean 39.06, sd 5.07); a
   difference inside the pool's spread is NOT RESOLVED. Gates: 0 tracebacks, 25 games played, the server line
   `ARC3 pinned allocator: PYTORCH_CUDA_ALLOC_CONF=expandable_segments:False,pinned_max_round_threshold_mb:1024`.

**Local check first (6000, Kaggle image, local NVMe model):** anchor v37 and the arm started back to back, each stopped
after the server is ready; compared on the `Available RAM` line and host memory after `Initialized PLE embedding`.
Local disk is not Kaggle's mount, so local shard idle is not read for prediction 2.

**If it holds:** the same switch on the candidate (harness fa326e3, branch candidate-1101), one Kaggle test run before
the 17:59 CST window. Which run takes a submission slot is Cody's call.

## Local check result (2026-11-01 04:43-04:46 CST, 6000, Kaggle image, local NVMe model; recorded after the run)
Each run stopped once vLLM logged its first "Available RAM" line (the target-weight load, right after the PLE pin).
| run | vLLM "Available RAM" | host MemAvailable | container memory | allocator line |
|---|---|---|---|---|
| v37 (harness 8552964) | 46.45 GiB | 46.1 GiB | 136.1 GiB | absent |
| arm (harness 2c51989, ARM_PINNED_ROUND_MB=1024) | 73.82 GiB | 73.6 GiB | 104.4 GiB | `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:False,pinned_max_round_threshold_mb:1024` |
Prediction 1 HOLDS on this machine: +27.4 GiB available by vLLM's own line, -31.7 GiB of container memory
(expected ~32.6). n=1 each; local disk, so shard idle (prediction 2) is left to the Kaggle run.

## Amendment 1 (2026-11-01 05:05 CST, before any Kaggle run): the boot clock on the candidate only
Kas found forum topic 753843 (read 05:00): Jeroen Cottaar's team (#2) measured on 10-29/30 that on SCORED runs the
notebook starts ~40-50 min after the machine (a /proc/uptime > 20 min killswitch fired every time; an empty notebook
on the RTX 6000 now takes ~50 min to return a Kaggle error) and that the time counts against the 9 h (successful
submissions take 9 h total, not 9 h 40). Our scored-run clocks count from NOTEBOOK_START_EPOCH, so the pool clock's end
(and its reserve for unstarted games) would sit ~40-50 min past the real limit. Builder flag `--boot-clock` (default
off; the candidate rebuilt without it is byte-identical to fb88f6d's): cell 3 sets CLOCK_START_EPOCH from
/proc/uptime when 0 < uptime < 7200 s (else the notebook start) and prints `BOOT machine_uptime_s=...`; cell 11's clock
fit and pool end use it. synesthesia_candidate_pinned is rebuilt WITH it (cells 3 and 11 only). The v37 pinned arm stays
without it, a clean one-variable comparison. A commit run cannot test the boot clock: commit runs use the soft end,
and the delay was reported on scored runs only.
