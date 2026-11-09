# Hidden-path audit, load and setup (2026-11-01)

Fork of CL1, one of three. Scope: the code that loads the model and sets up a hidden-set rerun:
`harness/setup_commands.json` at anchor 8552964 (what runs), `harness/src/ARC3-Inference/inference/framework/kaggle.py`
at 8552964 (the generator it was rendered from), and v37's notebook cells (d620f27,
`notebooks_duck/kaggle_staged/synesthesia/synesthesia.ipynb`). Read-only; nothing fixed, nothing committed.
Every claim is labelled **measured** (from code read or run artifacts) or **inferred**.

Evidence used: the files above, extracted to scratch; the 12 Kaggle runs on harness 8552964 under
`~/kaggle_local/kaggle_runs/` (A1-A3, C2-C7, Gc, Gs, NE): their `vllm-shard-prefetch.json`, `vllm-openai-server.log`,
`vllm-watchdog.log`, `metrics/host_memory.jsonl` and the papermill logs; the 0.31 runtime overlay
`/mnt/data/arc3_runtime313/dataset/arc3_vllm_v0310_arc3_overlay.tar.blob` (extracted to scratch). v37 differs from
v36 only in cell 4, so its load path is the one those runs exercised.

## What runs vs what gets read

`setup_commands.json` is one shell command holding a 77 KB Python setup script. It writes the vLLM watchdog to
`/kaggle/working/vllm-watchdog.py` from a string constant, `WATCHDOG_SCRIPT_TEXT`.
- That string is byte-identical to kaggle.py's `_DUCK_VLLM_WATCHDOG_SCRIPT` template (measured: extracted both, `diff` empty).
- The setup then rewrites one function of it at run time (`_ARC3_PF_OLD -> _ARC3_PF_NEW`, setup script lines 46-52):
  `read_file_into_page_cache` becomes 8 interleaved readers per file. The swap raises if the old text is not found
  exactly once (measured: count = 1 at 8552964; C7's log prints "ARC3 parallel prefetch: watchdog reader replaced").
- The setup script itself differs from kaggle.py's `_DUCK_VLLM_SETUP_SCRIPT` by the ten documented patches in
  `notes/harness_v8_as_code_2026-10-26.md` (runtime pins to our 0.31 build, ARM_* switches, KV-copy hook, the
  prefetch swap). kaggle.py is not re-rendered; it is the upstream source, not what runs.

No patch in the load path can fail silently: the prefetch swap, the runtime overlay applier and the KV-copy patch
each raise on failure (measured, setup script lines 50-51, 370-371, 820-821).

## Findings, ranked by likely impact

### 1. The prefetcher's memory premise does not hold for our checkpoint; the remaining load lag tracks memory headroom

- **Where:** watchdog `GpuShardPrefetcher` (template kaggle.py:297 onward; runs from `WATCHDOG_SCRIPT_TEXT`),
  class docstring and `_submit_window`; plus our 8-reader swap.
- **Claims:** "Keep the GPU shards a bounded window ahead of vLLM's single-stream loader... after the pinned PLE
  table the page cache holds about 20 GiB, so pages far ahead were evicted before the loader got there."
  `start_vllm_server`'s docstring: prefetch runs "a bounded window ahead of each weight load".
- **Does:** `_submit_window` always submits the shard being loaded, in full
  (`self._submitted_position == self._passed_position or ...`). Our four GPU shards are 14.7-18.7 GiB, larger
  than the 8 GiB window, so the window bounds nothing for them. Our swap reads that whole shard with 8 streams at
  about 0.6 GiB/s (shard 1: 18.66 GiB in 31 s, C7), 2-3x faster than the loader consumes shards 2-3 (C7: 63 s and
  103 s).
- **Evidence (measured):**
  - vLLM logs "Available RAM" at load start of 8.66-9.85 GiB in all 12 runs (server log, `weight_utils.py:1068`),
    not ~20 GiB. One big shard is about twice that.
  - The PLE table is allocated in pinned host memory as BF16 before the progress bar
    (`ngram_embedding.py:443-449`; C7 log 06:08:31). Cgroup usage jumps from 50 to 167 GiB of a 175 GiB limit at
    06:08:05-06:08:35 (C7 `host_memory.jsonl`).
  - Loader idle after a big shard's read finished (`loader_passed - prefetch_finished`, shards 2-4 summed) against
    the cgroup's available memory during those shards:

    | run | idle s | cgroup available, median GiB (min) |
    |---|---|---|
    | A1 | 459.0 | 5.5 (4.3) |
    | C2 | 331.6 | 5.7 (4.9) |
    | Gs | 255.1 | 5.9 (5.6) |
    | C3 | 236.5 | 5.4 (5.0) |
    | Gc | 135.7 | 6.8 (5.1) |
    | C7 | 106.1 | 5.5 (5.1) |
    | A2 | 91.1 | 8.9 (5.7) |
    | NE | 88.0 | 7.6 (4.8) |
    | C4 | 68.2 | 7.9 (4.8) |
    | C6 | 64.2 | 7.6 (4.9) |
    | A3 | 0.8 | 21.3 (11.2) |
    | C5 | 1.0 | 23.9 (15.1) |

    The only two runs without lag are the only two with more than 9 GiB of headroom. Shard 1 is never late
    (0.0-0.5 s in 12/12).
  - Window alignment caveat: load start is taken from the last timestamped server-log line before the 0/28 bar
    (a few seconds' error), and samples are every 15 s (n = 5-39 per run).
- **Inferred mechanism:** pages the readers bring in ahead of the loader are evicted under the cgroup limit before
  the loader reaches them, so the loader re-reads them itself through one stream. Not shown directly; a mincore
  residency sample of the current shard during the load would confirm or kill it.
- **Hidden path:** yes, the watchdog runs in every run. Host-memory sampling is off in hidden reruns
  (`is_test_run()`), so there is no hidden-run evidence either way.
- **Impact:** 0-459 s of load per run (measured range). Unknown what makes headroom differ between runs: all start
  at about 9 GiB, A3 and C5 gained room during shards 2-4.

### 2. The PLE prefix bug (known): it never overlaps the big shards, and the "fix" may slow the load

Known: `PLE_SHARD_NAME_PREFIX = 'ple-'` never matches `model-ple-NNNNN-of-00022.safetensors`, so the 22 PLE files
(95.4 GiB) are prefetched.

New, measured:
- **Order.** In 12/12 reports the first PLE prefetch starts at the instant big shard 4 is passed (e.g. C7 221.2 s
  vs 221.2 s; A1 638.3 vs 638.3). Natural sort puts `model-0000N`, then `model-mtp-*`, then `model-ple-*`.
  - So the PLE prefetch cannot cause the shards 2-4 lag in finding 1. Tonight's message to the investigator and CL2 suggesting
    it might be CL2's eviction lead is wrong on timing.
  - Under the 8 GiB window it holds at most about one 4.47 GiB PLE file ahead at a time.
- **Rate.** The PLE phase lasts 138-382 s across the 12 runs, at about 0.6 GiB/s, and is read-bound (the loader
  passes each PLE file within ~0.5 s of its prefetch finishing, C7).
- **The skip's own justification isn't in our runtime.** The docstring says "the PLE shards already arrive at
  615-923 MiB/s through its multi-threaded copy". Our 0.31 overlay's loader uses vLLM's default single iterator
  unless `enable_multithread_load` is set (`default_loader.py:181-208, 389-394`; the server command sets no
  `--model-loader-extra-config`). vLLM's own auto-prefetch is skipped ("checkpoint total size exceeds 90% of
  available RAM", all runs).

Inferred:
- With the prefix "fixed", the loader would likely read the PLE files through one stream, slowing that phase.
- The bug may currently be helping. The proposed A/B tests only the PLE phase, and its expected direction is slower.

### 3. People audit kaggle.py; setup_commands.json is what runs

- **Where:** builder `scripts/build_synesthesia_notebook.py:9` ("Nothing in it is patched at run time"); v37 cell 2,
  lines 2-3 ("run as it is; nothing is patched here").
- **Does:** true of files on disk, false of the executing code.
  - The watchdog's reader is rewritten in memory before it is written out.
  - The vLLM runtime is overlaid and KV-copy patched at setup.
- **Evidence (measured):** load test A (notes/load_thread_cap_2026-10-31.md) concluded "the deployed prefetcher is
  1 stream" from kaggle.py and was retracted (9e5e1ac).
- **Hidden path:** n/a. **Impact:** misdiagnosis risk, no runtime effect.

### 4. The prefetch report misstates concurrency

- **Where:** `_write_report`, `'threads': GPU_SHARD_PREFETCH_THREADS`.
- **Does:** records the executor's 4 workers. The real readers per file are 8 (`ARC3_PREFETCH_READERS`, default 8),
  and that count appears nowhere in the report.
- **Evidence (measured):** all 12 reports say `"threads": 4`.
- **Impact:** misleads anyone reading the reports; no runtime effect.

### 5. The 8-reader swap hides read failures

- **Where:** `_ARC3_PF_NEW` (`read_file_into_page_cache`, watchdog lines 149-183 after the swap).
- **Claims:** "the return value is unchanged".
- **Does:** an exception inside a `read_stride` thread (failed `os.open`/`os.preadv`) kills only that thread. The
  function still returns `stopped: False`, so the report says `complete` with blocks unread. The shipped reader
  raised, and the report said `failed: ...`.
- **Evidence (measured):** 0 tracebacks or eviction errors in the 12 watchdog logs, so it hasn't happened in our runs.
- **Hidden path:** yes. **Impact:** low; slower load and a wrong report, never wrong weights (the loader reads the
  file itself).

### 6. The watchdog's restart path has never run on our stack

- **Claims:** after a crash the server restarts and "games resume on their own once the new server binds the port"
  (setup `start_vllm_server` docstring).
- **Evidence (measured):** 0 restarts and 0 server exits in all 12 watchdog logs.
- **Inferred:** a restart reloads the whole model (4-15 min by the reports) while per-game clocks run.
- **Hidden path:** only on a crash. **Impact:** unknown; untested.

### 7. The hidden run's per-game clock assumes Kaggle's 9 h counts from cell 3

- **Where:** v37 cell 11, lines 45-58 (`_arc3_left = NOTEBOOK_START_EPOCH + 32400 - 600 - now`), true submission only.
- **Measured:** cells 1-2 take ~5 s (C7: BOOT at 5.9 s, cell 3 at 10.9 s). Our pushes have shown 816-1,550 s from
  push to BOOT (split-model lane).
- **Unverified:** whether Kaggle's limit counts that pre-BOOT time.
  - If it does, the fit overestimates time left by up to ~26 min against a 600 s margin, and the last wave is cut.
  - If it doesn't, the fit is fine.
  - Past hidden v36 runs completed and scored, so nothing catastrophic has been observed.
- **Impact:** at most the last wave's tail.

### 8. Silent fallbacks (low)

- **(a) v37 cell 4, lines 7-26.** The fail-fast raise only fires when `KAGGLE_KERNEL_RUN_TYPE` is set.
  - Otherwise, with no wheelhouse at either path, the run falls through to "assuming local debug dependencies are
    installed", because cell 2 already set `TAAF_KAGGLE_BUNDLE_DIR`, and dies later on arcengine.
  - Measured: `Batch` in commit runs (C7 BOOT line). Hidden rerun: unknown.
  - Only matters if both mount paths are absent.
- **(b) Setup `extract_layer`.** It falls back from pigz to single-threaded `tar -z` without logging which ran.
  Layer 100 took 86 s in C7 (10 s -> 96 s).
- **(c)** `resolve_kaggle_dataset_path` / `resolve_kaggle_model_path` return a nonexistent candidate silently, but
  setup lines 830-834 then raise `FileNotFoundError`, so that one is loud. Not a problem.

### 9. Patches that do nothing, and stale text (no runtime effect)

- **KV-copy patch.** C7 logs "ARC3 KV copy patch: already patched (v0.31.0, 36fd9aee9a36)". The overlay already
  carries it, so the hook is idempotent and inert (measured).
- **Stale "e975732 rc3 runtime" references.** Setup docstrings on the draft vocabulary and embedding offload refer
  to the old runtime.
  - Checked against our overlay: `VLLM_QWEN4_EXP_DRAFT_VOCAB` and `use_local_argmax_reduction` are implemented
    (`qwen4_exp/nvidia/mtp.py:453-549`), and `VLLM_ARC3_GDN_RECOVERSSM` is read (server log "ARC3 GDN RecoverSSM
    enabled").
  - So the settings reach the runtime; only the prose is stale.
  - `B12X_MICRO_DYNAMIC_CUTOVER_PAIRS` is unused because the MoE backend is unset.
- **Dead files.** `notebooks_duck/{synesthesia,ourstack}/bundle_setup_commands.json` (12 KB, vLLM 0.29 wheelhouse)
  are referenced by nothing in d620f27's scripts and aren't in the harness dataset (`git archive harness/`). Not in
  the hidden path.
- **Test-run only, by design.** Host-memory sampling and cache diagnostics run only in test runs. The watchdog
  docstring's "sample host RAM throughout" holds only for commit runs.

## Could not check

- Hidden-rerun environment: `KAGGLE_KERNEL_RUN_TYPE`, which competition mount path it gets, whether Kaggle's 9 h
  counts pre-BOOT attach time, and what happens at the limit.
- Whether Kaggle's `/tmp` (where the ~20 GiB vLLM runtime is unpacked) is tmpfs and so counts against the cgroup.
- What fills the ~117 GiB cgroup jump at load start, beyond the BF16 pinned PLE table.
- Finding 1's mechanism directly (needs a page-cache residency sample of the current shard during a load).
- The loader's actual single-stream PLE rate in our runtime (finding 2's direction is inferred from code).
- v37's own artifacts. I used the 12 runs on the same harness (8552964); v37 changes only cell 4.
