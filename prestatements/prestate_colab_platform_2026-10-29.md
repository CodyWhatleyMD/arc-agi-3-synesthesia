# Pre-statement: Colab G4 as a platform (10-29 01:58 CDT, before any Colab score is read)

Kas's push-back (01:56), accepted: one in-range score cannot establish equivalence (any value ~30-48 "passes" against a
pool with sd ~5; the test cannot fail), and CLAUDE.md's one-platform rule applies. The matching KV pool (1,501,360 tokens)
shows the SERVING config is the same, not that play is: host CPU (sandbox + tower on CPU), clock and load time differ, and
play seconds already moved Kaggle scores.

## Rule
1. Colab is its OWN platform. Colab arms are read only against Colab controls (a Colab control pool), with the same
   parser and the same gates (benchmark "ended:" line + parquet, 25 games, 0 tracebacks, 0 HTTP 400, ARM banner,
   switches checked), play seconds recorded beside each run.
2. Pooling Colab controls into the Kaggle pool requires a pre-stated equivalence check, run only once >= 4 Colab
   controls exist: paired-by-game bootstrap of (Colab mean - Kaggle mean) over the 25 games, Kaggle n=7; pool ONLY if
   the 90% CI of that platform difference lies entirely within +/-2.0 points (TOST, two one-sided 5% tests) AND Colab
   play seconds are within 5% of the Kaggle controls' mean. Otherwise Colab stays separate and the paper states the CI.
   (Correction 01:57, Kas: "CI includes 0" rewards noise; equivalence is the whole CI inside the margin. Expected
   outcome at n=4 vs 7 with sd ~5: half-width ~5-6, so the pools likely stay separate and the claimable margin is ~+/-6.)
3. The first Colab run (c1, anchor f9af78d9 / 8552964) is a plumbing test and the first member of the Colab pool;
   its score is reported, not interpreted against Kaggle.
