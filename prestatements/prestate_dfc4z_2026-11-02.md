# Pre-statement: dfc4z = dfc4b + drafter shortlist + no EAGLE block drop (dflash-cache lane, 2026-11-02 ~02:20 CST)

Arm (Kaggle commit run, public 25, the candidate's clock and flags): dfc4b's switches (tuned drafter
arc3-flashnext-dflash2-ours-tuned-k1, ARM_MTP_TOKENS=4, ARM_DFLASH_SW_RETAIN=1, ARM_DFLASH_DRAFT_GROUP=1,
ARM_PREFIX_MATCH_UNIT=16, ARM_KV_GROUP_LOG=1, candidate_pinned flags) + ARM_DFLASH_SHORTLIST=1 (as in dfnd4s) +
ARM_SPEC_EXTRA_JSON={"attention_backend": "TRITON_ATTN", "disable_eagle_block_drop": true}; cache diagnostics ON
(default) so scripts/dflash_followup_hits.py can read it. Harness candidate-dflash cc62e0b (tests at 4a4e3c6: non-EAGLE
retention cases N1-N4 pass). Why: notes/dflash_followup_hits_2026-11-02.md (253329b) -- DFlash's extra recompute is
block-granular hits plus a whole-block EAGLE drop, and ~4% zero-hit collapses where the drafter group with the drop is
one block short of Mamba's sparse checkpoint; without the drop the drafter group reached Mamba's checkpoint in 100% of
follow-ups. Two variables vs dfc4b (shortlist, drop off): dfnd4s (dfc4b + shortlist, diagnostics off) isolates the
shortlist's throughput, cross-run.

Baselines (same scripts):
- Follow-up recompute (P - hit, append-only follow-ups, scripts/dflash_followup_hits.py): dfc4b median 4,856, mean
  8,120, zero/low-hit share 3.6% (98 of 2,688, hit below the boundary); dfc7b 4,976 / 8,931 / 4.3%; MTP
  candidate_pinned 2,577 / 3,387 / 0.1%.
- Acceptance per 5-min window, dfc4b (scripts/kvtier_windows_exact.py, t0 = first row with generation > 5 tok/s):
  2.94 / 3.03 / 3.09 / 3.18 / 3.13 / 3.17 / 3.16 / 3.09 / 3.03 / 3.03 / 3.10 / 3.12 (windows 0-60).
- Generation, whole run ("generated tokens/sec (job wallclock)"): dfc4b 794.7; candidate_pinned (MTP) 833.6.

Readings, fixed now:
- VOID if: the server log contains "no KV cache group could be identified" or any group is flagged for the EAGLE drop
  (the cache diagnostics' per_group "drop_eagle" true for a group, or the ARC3 draft-group line naming a group); or
  "ARC3 DFlash SW retain patch: installed" is missing; or the server dies/restarts; or < 30 min of play.
- CACHE (primary, from the diagnostics): the fix WORKS if the follow-up recompute median <= 3,500 AND the zero/low-hit
  share <= 1.0%; PARTIAL if exactly one holds; FAILS if neither. Predicted: median ~3.2k, share ~0.1-0.5%, mean near
  MTP's ~3.4k. The new boundary rule is checked directly: share of follow-ups hitting exactly floor((P_prev-1)/blk)*blk
  (predicted >= 85%).
- ACCEPTANCE (the cost the drop guards): reported per 5-min window against dfc4b; a mean over windows 0-60 below dfc4b's
  by more than 0.10 (3.08 -> < 2.98) is read as a real acceptance cost of dropping the guard.
- THROUGHPUT, the Monday bar (the investigator/CL2): generation >= 833.6 x 1.05 = 875.3 tok/s with diagnostics on = a clear win
  over MTP; between 794.7 and 875.3 = read together with tonight's diagnostics-off pair (cpnd vs dfnd4); <= 794.7 = no
  gain over dfc4b.
- n = 1; one machine draw. Scores reported, not used for these readings.

## Amendment 1 (02:05 CST, before any dfc4znd number): the read for dfc4znd (diagnostics OFF; pushed by CL2, d6a7cfa)
CL2 stopped the dfc4z queue before it pushed and pushed dfc4znd = dfc4z + ARM_CACHE_DIAGNOSTICS=0, paired with cpnd
(MTP, diagnostics off) under notes/prestate_dflash_fair_2026-11-01.md amendment 1. Without per-request diagnostics the
CACHE reading above uses scripts/dflash_recompute_nodiag.py instead:
- MEAN computed prompt tokens per request = integral of the server log's prompt throughput / harness request count
  (validated exact: candidate_pinned 1.000, dfc4b 0.997 vs the diagnostics). Baselines: candidate_pinned (MTP) 6,724;
  dfc4b (drop on) 11,140; dfc7b 12,024 (= Codex's ~12,080). Same-night MTP baseline: cpnd, same script.
- LARGE RECOMPUTES = harness history entries with uncached_input_tokens > 60k, per request (validated as a count:
  candidate_pinned 150 vs 143 requests in the diagnostics, dfc4b 195 vs 212). Baselines: MTP 4.8%, dfc4b 6.8%.
- Readings: the fix WORKS (cache) if dfc4znd's mean <= 8,000/request (>= 71% of the dfc4b-MTP gap closed; predicted
  ~7.4k = MTP + ~650/request of remaining block granularity) AND large recomputes <= 5.5% of requests; PARTIAL if
  exactly one holds; FAILS if neither. If cpnd lands, the same comparison is also reported against cpnd.
- Not available without diagnostics: the append-only median, the exact zero-hit share, the boundary-rule share; those
  wait for the diagnostics-on dfc4z if quota allows.
Acceptance and throughput readings are unchanged (server log; no diagnostics needed).
