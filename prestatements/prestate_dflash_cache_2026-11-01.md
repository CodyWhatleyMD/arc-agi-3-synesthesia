# Pre-statement: DFlash drafter-cache retention and K pricing on Kaggle (dflash-cache lane, kasoti fork, 2026-11-01 ~07:45 CST)

Harness: branch dflash-cache 5509581 (= 55e7f3e, the l10 harness, + three default-off switches):
- ARM_DFLASH_SW_RETAIN=1 -> scripts/runtime_0310/patch_dflash_sw_retain.py: SlidingWindowManager keeps the reachable
  tail at a prompt's EXTENSION replay boundary (3 blocks at window 2048 / block 1664 with the EAGLE drop) referenced
  until the request finishes, and SlidingWindowSpec's admission cap rises by those 3 blocks. Targets mechanism 2
  (notes/dflash2_flashnext_2026-10-31.md: the drafter group's blocks freed early and evicted before the follow-up's
  lookup; hits collapse from minute 10). Does NOT touch mechanism 3 (1664-token hit granularity: l9/l10 start at
  79-80% vs MTP's ~90%).
- ARM_QSA_RING_FIT=1 -> patch_qsa_ring_fit.py: QSA ring capacity 16 for K=5..8 (stock 12 does not divide 1664 and
  asserts). No-op for K <= 4.
- ARM_MTP_TOKENS=K (default 3).
Logic tests: tests/dflash/test_sw_retain.py (real extracted methods, stock as the known-bad comparator; real-held <=
the raised cap at every prompt length tried), tests/dflash/test_qsa_ring_fit.py. Neither patch has booted yet.

Arms (Kaggle commit runs, public 25, concurrency 14, --max-runtime-s 5400, otherwise l10's switches: dflash, Triton
drafter attention, ARM_DFLASH_DRAFT_GROUP=1, ARM_KV_GROUP_LOG=1, stock incoai drafter; fresh kernels and slugs):
- dfr3: ARM_DFLASH_SW_RETAIN=1, ARM_MTP_TOKENS=3.  (retention test)
- dfr7: ARM_DFLASH_SW_RETAIN=1, ARM_MTP_TOKENS=7, ARM_QSA_RING_FIT=1.  (K pricing at the drafter's native block)
- dfr4 (when a slot frees): ARM_DFLASH_SW_RETAIN=1, ARM_MTP_TOKENS=4.
References: the MTP Kaggle runs C2/C6/C7, v37 and CAND (server logs on disk: ~850-900 tok/s and hits ~90% in the
first windows); local l10 (no retention, same switches otherwise) as the collapse pattern, cross-machine (local runs
were ~5% faster early than Kaggle under MTP).

Windows: 5-min, t0 = the first server stats row with generation > 5 tok/s, through min 45 (or the end of play).
Per window: vLLM's prefix-cache hit (and window-exact from metrics/vllm_cache_diagnostics_*.jsonl when present, via
scripts/kvtier_windows_exact.py --diag), generation tok/s, mean acceptance length, KV usage, waiting requests.

Verdicts, fixed now:
RETENTION (dfr3):
- VOID if stdout lacks "ARC3 DFlash SW retain patch: installed", or the server dies/restarts, or < 30 min of play.
- HOLDS (the collapse is gone): every window 10-30 has hit >= 75% AND >= (mean of windows 0-10) - 5 points, AND
  generation >= 0.8x the MTP Kaggle reference median for that window.
- PARTIAL: the hit criterion holds but generation does not.
- REFUTED: any window 10-30 below 75% hit or more than 5 points under its windows 0-10 mean.
  Prediction (from the mechanism, not a run): HOLDS on hits at ~80-86% (mechanism 3 stays), generation within 0.8x.
K (dfr7 against dfr3; dfr4 when run):
- dfr7 VOID if the ring patch line is missing or the server does not boot (a failed boot with the patch is itself
  reported: the ring patch is then not usable as written).
- "K=7 pays" if dfr7's generation tok/s >= dfr3's in at least 4 of the 6 windows 0-30 AND its mean over 0-30 >=
  dfr3's. Acceptance length is reported per window (capped at K+1).
  Prediction: with the STOCK drafter, K=7 does not pay (acceptance ~2.8 -> ~3.0-3.3 while each step verifies 112
  instead of 56 tokens); the tuned drafter (lane drafter-tune) is what could change that, to be re-run then.
- n = 1 per arm. A difference smaller than the MTP references' own window-to-window spread is not read as an effect.
Scores are reported, not used for these verdicts (55-minute-or-so commit runs).
