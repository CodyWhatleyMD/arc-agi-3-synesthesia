# Pre-statement: PLE prefix A/B (2026-11-01, before any run)

Arm: anchor v37 (harness 8552964) + ARM_PLE_PREFIX=model-ple- (setup patches the watchdog's PLE_SHARD_NAME_PREFIX from
'ple-' to 'model-ple-', so the 22 PLE files are no longer prefetched; default unset = v37 unchanged). One Kaggle commit run,
compared with v37's load (vllm-shard-prefetch.json + metrics/host_memory.jsonl, aligned on the server log).

v37 baseline (already read): loader 387 s; big shards loader/read 28/28, 79/30, 29/28, 101/23 s; PLE phase 145 s;
available host memory 4.7-9.3 GiB on shards 1, 2, 4 and 13.5-23.4 GiB on read-bound shard 3; cgroup usage <= 170.8 GiB
of 175.

Predictions (kasoti): the PLE phase gets SLOWER (the loader reads the PLE files on its own, without the 8 interleaved
readers): refuted if the arm's PLE phase is <= 145 s. Big shards 2-4 are unchanged in kind (the PLE files load after them,
so the prefix cannot touch their stalls): refuted if the arm's shards 2-4 show no time beyond their reads while
available memory during them stays <= 8 GiB. Available memory during the PLE phase rises by >= 4 GiB (no prefetch window
of PLE pages): refuted if its minimum stays within 2 GiB of v37's 4.2 GiB. One run each side: host and mount variance
between Kaggle sessions is large (loader totals 250-907 s across 12 runs), so a single difference under ~30% is reported
as not resolved, not as an effect.
