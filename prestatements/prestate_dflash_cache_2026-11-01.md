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

## Result: dfr3 (read 2026-11-01 ~11:20 CST; kernel arc-agi-3-synesthesia-dfr3 v2, harness 8c0126b; output ~/kaggle_local/kaggle_runs/DF_dfr3_v)

RETENTION: **HOLDS.** Not VOID: "ARC3 DFlash SW retain patch: installed" (both files, hashes as pinned), draft-group
patch installed, "no KV cache group could be identified" 0 times, server ready at 1,632 s, KV pool 1,499,856 tokens,
0 tracebacks, 0 preemptions, 51m 47s of play (t0 15:03:03 UTC). Windows (scripts/kvtier_windows_exact.py --diag
metrics/vllm_cache_diagnostics_1002.jsonl; MTP reference = median of C2, C6, C7, CAND, v37 server logs, same script):

| window | hit window-exact / rolling | gen | acc | MTP gen median (0.8x) | MTP rolling hit median |
|---|---|---|---|---|---|
| 0-5 | 80.3 / 78.6 | 859 | 2.71 | 884 (707) | 88.7 |
| 5-10 | 91.1 / 86.7 | 900 | 2.76 | 946 (757) | 92.6 |
| 10-15 | 91.2 / 88.7 | 924 | 2.83 | 915 (732) | 93.2 |
| 15-20 | 85.7 / 87.8 | 764 | 2.84 | 840 (672) | 92.4 |
| 20-25 | 82.6 / 86.7 | 801 | 2.83 | 872 (698) | 92.1 |
| 25-30 | 84.4 / 86.4 | 777 | 2.85 | 871 (697) | 91.7 |
| 30-35 | 80.7 / 85.4 | 689 | 2.85 | 848 (678) | 91.6 |
| 35-40 | 82.1 / 85.1 | 816 | 2.79 | 894 (716) | 91.9 |
| 40-45 | 87.3 / 85.4 | 858 | 2.74 | 859 (687) | 91.7 |
| 45-50 | 82.9 / 85.5 | 763 | 2.78 | 864 (691) | 91.7 |

Criteria: windows 10-30 window-exact hit 91.2 / 85.7 / 82.6 / 84.4, every one >= 75 and >= 80.7 (windows 0-10 mean
85.7 - 5); generation 924 / 764 / 801 / 777 >= 0.8x MTP (732 / 672 / 698 / 697). Rolling hits pass the same test.
Against l10 (no retention, local): hits 68.9 / 33.9 / 23.3 / 22.9 and generation 505 / 344 / 350 / 360 over the same
windows. As predicted: no collapse through 50 min; hits sit ~6-8 points under MTP (mechanism 3, the 1664-token hit
granularity, untouched); generation 0.81-1.01x MTP (mean 0.91x over 10-30); acceptance 2.71-2.85 (MTP 2.67-2.84).
Score 18.32 (2 won), a 52-minute commit run: reported only. n = 1, one machine draw.

## Amendment (11:25 CST): K=7 boot fix for dfc7 -> dfc7b
dfc7 (candidate-dflash 42bae15, K=7, ring fit) died at engine init: "Invalid prefix_match_unit=128; ... group block
sizes=[1744 x6, 16]". Cause, from source: the GDN conv state holds conv_kernel_size - 1 + num_speculative_tokens rows
(mamba_utils.py gated_delta_net_state_shape), so the Mamba page grows with K; platforms/interface.py sizes the attention
block as 16 x cdiv(mamba_page, 16 x attention_page_per_token) (kernel alignment 16): 16 x 104 = 1664 at K=3, 16 x 109 =
1744 at K=7. 1664 cannot be kept at K=7 (the attention page must cover the larger Mamba page). Fix: ARM_PREFIX_MATCH_UNIT=16
(an existing switch, no harness change). kv_cache_utils.resolve_kv_cache_block_sizes checks (1) every prefix-cacheable
group block % unit == 0: 1744 % 16 == 0 (the block is always a multiple of the kernel alignment 16, at any K); (2) the hit
alignment (= the unit, with Mamba in align mode) % every prefix-cacheable spec's tokens_per_state == 0: the model's only
compression is indexer_compress_ratio 4, 16 % 4 == 0. Under DFlash fine-grained hits are already off (the
SlidingWindowManager has no fine-grained lookup), so hits stay block-granular: the unit changes only hashing granularity,
measured with vLLM's own sha256(pickle) block hash at 4.6 ms vs 1.8 ms per 100k-token prompt (+~3 ms per new request).
Retention interval is 0 (allowed at any block). Not verified until a boot: the only proof.
dfc7b = dfc7's exact flags (rebuild byte-identical to the staged dfc7) + ARM_PREFIX_MATCH_UNIT=16, fresh kernel/slug.
dfc7b readings: VOID if "kv cache group sizes" is not [1744 x6, 16] or the server does not reach ready; otherwise the
same criteria as dfc7's own pre-statement, and the boot itself is reported as the K=7 fix's verification.
