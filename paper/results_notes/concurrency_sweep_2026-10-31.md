# Concurrency bisection on the pool-clock build (local RTX 6000, 25 public games), 2026-10-31

Method (the investigator): overshoot, then bisect between 14 (shipped) and the overshoot; broad to narrow; each arm one variable
(solver concurrency + vLLM max_num_seqs via ARM_MAX_NUM_SEQS, harness 6091476); 5-min windows of prefill tok/s, generation
tok/s, running/waiting, KV use and prefix-cache hit, against the local 14-game MTP runs r2/r6. Throughput, not score.

## c25 (container arc3-local-c25, server log ~/kaggle_local/c25_server_1031.log; KV pool 1,489,104 tokens)
| window | 14 games (r2/r6) | 25 games |
|---|---|---|
| 0-10 min | gen ~950-995 tok/s, hit 89-93% | gen 1,191-1,215 (+25%), hit 87%, KV 64 -> 94% |
| 10-15 min | gen ~935-945, hit ~92% | gen 383, KV 98.6%, hit 74.5%, waiting 3.1 |
| 20-25 min | gen ~880-920, hit ~91-92% | gen 350, hit 57.5%, waiting 6.7 |
| 35-40 min | gen ~870-880, hit ~91% | gen 249, hit 43.4%, waiting 11.0 |
Reading: 25 is past the break. +25% throughput until the KV pool fills (~10 min), then the findings-196a collapse
(prefixes evicted, prompt recompute 8-10k tok/s, generation down to a third, requests queueing). Same shape as DFlash l6/l9.
Next: c20 (built: notebooks_duck/kaggle_staged/synesthesia_c20), then ~17 or ~22-23 by the bisection rule.

## c20 (local, 10-31 ~21:10-22:20, pool-clock harness 6091476, ARM_MAX_NUM_SEQS=20)

Collapses the same way as c25, from minute 10 (5-minute windows, pool 1,493,700 tokens):

| window | prompt tok/s | gen tok/s | KV | prefix hit | samples with requests waiting |
|---|---|---|---|---|---|
| 0-5 m | 2,277 | 1,088 | 53.3% | 87.9% | 0/30 |
| 5-10 m | 1,746 | 1,174 | 80.2% | 91.5% | 0/30 |
| 10-15 m | 5,865 | 690 | 91.6% | 84.4% | 17/30 |
| 15-20 m | 9,388 | 392 | 77.9% | 74.0% | 30/30 |
| 20-25 m | 9,593 | 313 | 92.0% | 65.7% | 30/30 |

10-minute generation over the whole run: 1,092 / 568 / 301 / 271 / 285 / 316 / 275 tok/s; acceptance 2.74-2.82
throughout (speculation is not the problem; the cache is). 14 streams hold ~880-995 tok/s with 89-93% hits (r2/r6).
Verdict: 20 is past the break. Next bisection step: 17. Log kept as ~/kaggle_local/c20_server_1031.log.

## c17 (local, 10-31 ~22:40, pool-clock harness 6091476, ARM_MAX_NUM_SEQS=17)

Arm: c20 with 17. Staged notebooks_duck/kaggle_staged/synesthesia_c17, built with c20's flags (`--commit 6091476
--pool-clock --concurrency 17 --env ARM_MAX_NUM_SEQS=17 --dataset-slug codywhatleymd/arc3-syn-harness-sweep-k1`).
The rebuilt harness folder ~/kaggle_local/datasets/arc3-syn-harness-sweep-k1 is byte-identical to c20's (sha256 of all
92 files, before vs after). Launched like c20 (`HARNESS_SLUG=arc3-syn-harness-sweep-k1 run_synesthesia_dflash.sh c17
...`), same 25 public games, same 6000. The notebook differs from c20's only in the 20 -> 17 spots (title, banner,
ARM_* names, ARM_MAX_NUM_SEQS, `bm.solver.concurrency`) and in cell 4: d620f27 (builder, 21:13, after c20 was staged)
looks for the competition wheelhouse at two paths. Its first candidate is the path c20 hard-coded, which exists in the
local mount, so it should resolve the same wheelhouse. I will check that in the run log, not assume it.

**Pre-statement (written and committed before launch).** Read with ~/kaggle_local/kvtier_windows.py: 5-minute windows
from the first row with generation > 5 tok/s. For each window, hit and KV are the last sample (as in the c20 table),
gen and prompt are window means, and "waited" counts samples with Waiting > 0. 17 **holds** if, in each of the
windows 10-15, 15-20, 20-25 and 25-30:
(a) prefix hit >= 85.0%;
(b) waited <= half the window's samples (<= 15 of 30);
(c) gen >= the lower of r2/r6 in the same window: 935 / 800 / 881 / 865 tok/s. Those are r2 945/800/922/865 and
r6 935/888/881/911. r2/r6 hits in those windows are 90.7-93.5%, and they waited in 1-4 of 30 samples.
Any of (a)-(c) failing in any of the four windows refutes "17 holds": the next steps are then 15, then 16. If 17 holds,
the next step is 18 or 19. If play stops before minute 30 (crash, OOM), there is no verdict, and I report what
happened. I run about 40 minutes of play. Windows 30-35 and 35-40 are read with the same three tests and reported.
A failure there does not change the 10-30 verdict, but I name it in the verdict line as a late break. The scored run
lasts ~9 h, so I would then advise treating 17 as not holding.
Expectation (not the criterion): r2/r6 sit at 75-90% KV with 14 streams. Scaled by 17/14 that is 91-109% of the pool,
so I expect 17 to overflow and fail, but later than c20, which crossed ~92% KV in its 10-15 window.

### c17 result: 17 collapses like 20 and 25, from minute 12.5

Launched 22:34:34. Play ran from 22:39:43 CDT (log 03:39:43 UTC), and I stopped the container at 31 min of play
(23:11). Pool 1,498,296 tokens. Checked in the run: banner `ARM_MAX_NUM_SEQS=17`, server `--max-num-seqs 17
--max-cudagraph-capture-size 72`, `POOL CLOCK on ... concurrency 17, 25 games`. Cell 4 resolved
`/kaggle/input/competitions/arc-prize-2026-arc-agi-3/arc_agi_3_wheels (exists=True)`, and its pip lines (arc-agi 0.9.8,
arcengine 0.9.3) are identical to c20's. The cell-4 difference was inert here.

| window | prompt tok/s | gen tok/s | KV | prefix hit | waited | (a) hit / (b) waited / (c) gen vs floor |
|---|---|---|---|---|---|---|
| 0-5 m | 2,246 | 1,003 | 51.6% | 88.7% | 0/30 | not tested |
| 5-10 m | 1,680 | 1,064 | 82.9% | 92.5% | 1/30 | not tested |
| 10-15 m | 5,019 | 738 | 81.4% | 88.1% | 11/30 | pass / pass / **fail** (738 < 935) |
| 15-20 m | 9,899 | 284 | 91.6% | 78.4% | 30/30 | fail / fail / fail (284 < 800) |
| 20-25 m | 9,291 | 297 | 90.9% | 71.1% | 30/30 | fail / fail / fail (297 < 881) |
| 25-30 m | 9,991 | 279 | 94.7% | 64.7% | 30/30 | fail / fail / fail (279 < 865) |
| 30-35 m (10 samples) | 9,205 | 333 | 91.3% | 63.1% | 10/10 | reported only |

10-minute generation (throughput_windows.py):
- c17: 1,015 / 526 / 288 tok/s; 30-40 is 324 from 11 rows.
- c20: 1,092 / 568 / 301 / 271 / 285.
- r2: 949 / 870 / 894 / 891 / 894.
- r6: 953 / 916 / 892 / 849 / 869.

Acceptance was 2.69-2.81 throughout, so speculation is not what breaks, as in c20.

Onset, from the 10-second samples:
- Minutes 9-12.3 are healthy: gen 867-1,209 tok/s, 0 waiting, KV climbing from 69% to 94.9%.
- At 12.5, KV reaches 98.0% and prompt jumps to 8,051 tok/s (recompute).
- From 12.8, gen sits at 210-300 tok/s with 1-4 requests waiting. KV peaks at 99.8% at minute 13.2.

By the same measure (first sample after minute 5 with prompt > 6,000 tok/s), the onset came at minute 9.2 for c25,
11.7 for c20 and 12.5 for c17. Going down from 20 to 17 buys 0.8 min. Before the pool fills, 17 streams give +6-8% generation over r2/r6; c20 gave +15-19% and c25 +25%.

**The logged hit rate lags.** vLLM 0.31's "Prefix cache hit rate" is token-weighted over the last 1,000 requests
(`CachingMetrics(max_recent_requests=1000)`, read in the run's own vllm/v1/metrics). It stayed at 90-93% for over a
minute after recompute began and first fell below 85% at minute 16.4. That is why 10-15 passes test (a) while
generation has already halved. Generation, prompt and waiting react within one 10-second sample.

**Pool headroom.** Per 10-second sample over minutes 10-45, the 14-stream runs peak at 94.5% KV (r2) and 92.9% (r6),
with medians of 83.2% and 81.3%. They never reach 95%. c17 (minutes 10-31) peaked at 99.8%, with 24 of 130 samples at
or above 95%; c20 peaked at 99.9%, with 46 of 210. Scaling the 14-stream peaks linearly (crude, an expectation only),
15 streams reach ~99-101% and 16 reach ~106-108%. So 15 is a real test, and I expect 16 to fail.

**Conditions.** Another agent's `scripts/pool_timestop_sim.py --workers 4` (nice 19) ran from ~22:49:35, play minute
~9.9, through at least 22:52, minute ~12.5, which covers the onset. It was gone by 23:12, and I did not determine
when it ended. I did not measure its effect. The host was not newly saturated by it: load was already 12-14 at
minutes 5-6, before it started, on 24 CPUs. A single-core `vibe-rs` process (up 12 days) ran throughout, as it did
during c20. The break itself follows the KV ceiling, as in c20 and c25.

**Deviation from the pre-statement.** I stopped at 31 min of play instead of ~40. Windows 30-40 were only a late-break
check for the case where 10-30 held. With 10-30 failed, they could not change the verdict.

**Record bug.** RUN_CONFIG.json `serving.max_num_seqs` reads 14 in c17 and in c20, although their servers ran 17 and
20. SERVER_CMD.json carries the real value. Read the sweep arms' max_num_seqs from SERVER_CMD.json.

**Verdict.** 17 does not hold. It fails test (c) at 10-15 and all three tests at 15-20, 20-25 and 25-30. The
expectation held: the pool overflows. But the onset came only 0.8 min later than c20's. Next bisection step: **15**,
then 16 if 15 holds. Log kept as ~/kaggle_local/c17_server_1031.log. After the stop, the 6000 showed 8 MiB, 0%
utilization and no compute processes, with no arc3 containers present.
