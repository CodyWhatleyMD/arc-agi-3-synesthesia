# Student vs native tower, local replication: RESULT (read 2026-10-28 02:30 CDT, all gates passed first)

Pre-statement: notes/prestate_tower_native_2026-10-27.md (+ Clarifications 1-2: na1 invalid, image limit raised so
the PNG path carries the same history as the student path). Statistic: scripts/compare_arm_groups.py, paired-by-game
bootstrap, Δ = NATIVE − STUDENT, both tails. JSON: notes/tower_native_local_primary_2026-10-28.json.

## Validity (before any score was read)
na1c, na2c, na3c: 0 tracebacks, 0 HTTP 400, Ending Cell 12, ARM banner, native check printed, 25/25 games played,
request logs carry image_url parts only (36,310 / 41,646 / 34,060; embeds 0), boards per request median 13 / 14 / 12
(student arm r2: 13). Disk never below 77 GB. na1 (image:1, 33,604 HTTP 400) and na1b (its chain) are INVALID and
excluded, as pre-stated.

## Primary
| run | arm | mean score | levels | actions | tokens | KV pool | slope 10-100 play-min |
| na1c | native | 44.41 | | 8,347 | 5.79M | 1,440,080 | 0.471 |
| na2c | native | 49.43 | | 9,317 | 5.93M | 1,440,080 | 0.494 |
| na3c | native | 38.23 | | 10,130 | 6.24M | 1,440,080 | 0.382 |
| r2 | student | 40.19 | | 10,643 | 6.15M | 1,502,892 | 0.352 |
| r3 | student | 44.26 | | 9,264 | 6.05M | 1,502,892 | 0.416 |
| r4 | student | 41.41 | | 9,128 | 6.16M | 1,502,892 | 0.427 |

score : NATIVE 44.02 vs STUDENT 41.96, Δ = +2.07, 95% CI [−4.65, +9.15], sign 11 up / 13 down / 1 tie (p = 0.84).
levels: 4.29 vs 4.20, Δ = +0.09 [−0.32, +0.53].
**NOT RESOLVED at n = 3 vs 3.** The 18M student is not distinguishable from the 449M native tower on this harness at
this n; with Δ = NATIVE − STUDENT, the interval excludes a native advantage (a student deficit) larger than ~9.2 points
and a student advantage larger than ~4.7. (Corrected 11-02: the first version named the student deficit on the wrong
side. Run-level interval, notes/run_level_ci_results_2026-11-02.md: [−8.80, +12.88], so ~12.9 and ~8.8.)
Taken with the on/off read (OFF − ON = −3.62 [−9.89, +3.22]): the channel's three states (none, student, native)
order none < student ≲ native at the point estimates, and no pairwise difference is resolved.

## Covariate (pre-stated): KV pool with the native tower resident 1,440,080 vs 1,502,892 (−4.2%); the native arm
took fewer actions in two of three runs (8,347 / 9,317 vs 9,128-10,643), consistent with the per-turn encoder
forward the student never pays. Generation tok/s not computed for this read (the on/off note's method was not
re-derived; label: not computed).

## Exploratory (pre-stated as exploratory, no claim)
Slopes over summaries 1-10: native 0.471 / 0.494 / 0.382 vs student 0.352 / 0.416 / 0.427 (means 0.449 vs 0.398;
the spread within each arm is as wide as the gap). Coin-flip >= 50 share and stable-bottom levels: in the JSON;
bottom five mean levels 2.07 vs 2.20.

## What this settles and what it does not
Settles: the paper may say the student stands in for the native tower with no detectable loss at n=3 (interval
stated), on matched history and matched geometry, on this harness. Does not settle: a student deficit up to ~9.2
points or a student advantage up to ~4.7 (game-only interval; run-level ~12.9 and ~8.8, see
run_level_ci_results_2026-11-02.md); anything about the hidden set; mechanism. (Corrected 11-02; the earlier
"under ~5 points in either direction" put the deficit on the wrong side.) F208b's 49.51 vs 46.26 (n=2 each, another harness)
is not contradicted and not confirmed.
