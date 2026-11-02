# Pre-statement: DFlash vs MTP with diagnostics off (2026-11-01 ~23:40 CST, kasoti)

Why: Codex (notes/codex_review_dflash_throughput_2026-11-01.md) found the commit-run comparison tilted: test-only cache
diagnostics are on in every commit run and were ~10x larger for DFlash (3.0-3.3 GB vs 0.36 GB); scored runs never enable
them. On decode-only batches DFlash already breaks even per emitted token; the remaining loss is cache reuse (84% more
uncached prompt tokens per generated token at K=7). Cody: the throughput gap is a problem to solve, not a verdict.

Design: two commit runs pushed together (same hour, two Kaggle sessions), harness candidate-dflash 255503f (adds
ARM_CACHE_DIAGNOSTICS, default on; both runs set it 0), candidate_pinned's flags in both:
- cpnd  = MTP (DFlash switches unset) = candidate_pinned served like a scored run.
- dfnd4 = dfc4b's DFlash switches (tuned drafter, K=4, SW retain, prefix unit 16).
Reading, fixed now: primary = generated tokens/s (job wallclock), dfnd4 / cpnd. Same-config throughput varies about
+/-5% across runs and hosts (candidate 866, candidate_pinned 834, start-retry 800, v37 754), so:
  ratio >= 1.05: DFlash serves faster than MTP here -> a Monday contender if criterion-1 clean;
  0.95 < ratio < 1.05: not resolved (no switch to DFlash on this evidence);
  ratio <= 0.95: MTP serves faster.
Also reported: acceptance, prefix hits (server counters), uncached prompt tokens per generated token, score (not gated).
Invalid if either errors before its soft end, or either log shows diagnostics on.
