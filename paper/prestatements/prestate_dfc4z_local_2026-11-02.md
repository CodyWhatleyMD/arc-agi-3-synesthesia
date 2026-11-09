# Pre-statement: local dfc4z probe on the RTX PRO 6000 (2026-11-02 02:25 CST, CL2)

Why: the Kaggle pair (cpnd vs dfc4znd, diagnostics off; prestate_dflash_fair amendment 1) has sat QUEUED since 23:17 /
01:45, and a Monday submission must start by ~08:59 CST (9 h scored run ending by 17:59; the investigator), safely by ~06:00-06:30.
Decision rule (the investigator informed 02:17): unless DFlash clears its bar by ~05:30, submit candidate_pinned v1.
What: the staged dfc4z (c8bd5e0; prestate f3fdf4a: tuned drafter, K=4, SW retain, prefix unit 16, shortlist,
disable_eagle_block_drop; diagnostics ON) on the local 6000, starting when the x4 A/B's B arm (x4b2) exits (~03:45),
via ~/kaggle_local/run_synesthesia_dfz.sh (run_synesthesia_dflash.sh with the tuned drafter mounted).
Comparator (same card, 14 concurrent, diagnostics on, commit run): x4a2 = candidate_pinned x4 local (its first 40 min).
Readings, fixed now:
1. Throughput: mean generation tok/s over play minutes 10-40, dfz1 / x4a2. >= 1.05 DFlash serves faster; 0.95-1.05 not
   resolved; <= 0.95 MTP faster.
2. Cache (f3fdf4a's criteria, from the diagnostics with scripts/dflash_followup_hits.py): follow-up recompute median <=
   3,500 and zero/low-hit share <= 1.0% = the block-drop fix works.
3. Acceptance per 5-min window vs dfc4b (2.94-3.18; < 2.98 = a real cost).
Local is ~5% faster than Kaggle early in a run for both stacks; the ratio, not the level, is the reading.
