# Pre-statement: Colab G4 as a platform (10-29 01:58 CDT, before any Colab score is read)

CL2's push-back (01:56), accepted: one in-range score cannot establish equivalence (any value ~30-48 "passes" against a
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
   (Correction 01:57, CL2: "CI includes 0" rewards noise; equivalence is the whole CI inside the margin. Expected
   outcome at n=4 vs 7 with sd ~5: half-width ~5-6, so the pools likely stay separate and the claimable margin is ~+/-6.)
3. The first Colab run (c1, anchor f9af78d9 / 8552964) is a plumbing test and the first member of the Colab pool;
   its score is reported, not interpreted against Kaggle.

## Amendment 1 (11-02 09:12 CST): c2 = the fit test, before it runs
c1 (10-29) reached live play and died on host memory: 137 GiB worker + 20 GiB runtime tmpfs against 176 GiB. Since
then the pinned-memory rounding fix (PYTORCH_CUDA_ALLOC_CONF, arms 2c51989/848f336) took 31.7–33.0 GiB off the
worker locally. c2 = the candidate_pinned staged notebook (848f336 + boot clock, harness candpin-k1) on a fresh G4
through colab_run.sh, unchanged otherwise. Pass = vLLM serves AND the benchmark prints its "ended:" line with 25
games played; the host peak (worker RSS + /dev/shm) is recorded either way. c2's score, if any, joins the Colab pool
under Rule 1 (reported, not compared with Kaggle). Prediction: it fits (worker ≈ 105 GiB + 20 GiB shm < 176 GiB);
if it OOMs again the next step is the runtime on disk instead of /dev/shm (c1's disk had 207 GB free), not more tuning.
The investigator's own Colab notebook (ARC_AGI_3_Synesthesia_Kitchensink) stopped at the model: per-file download over the
paginated Kaggle file list (20 per page) fetched 8 of 22 PLE shards and no index; the runner pulls with
kagglehub.model_download, which does not have that problem.

## Result, c3 (11-02 12:37 CST): the model FITS on a Colab G4 with the pinned-memory fix
c3 (candidate_pinned, candpin-k1, runtime in a 26 GB exec tmpfs, model on disk) reached play: worker RSS 100.6 GiB
(c1: 137), runtime tmpfs 20 GB, GPU 96.9 GB used, 47 GB host available, no OOM; chat completions flowing with
spec decoding (mean acceptance 2.94, ~322 tok/s generation at this moment). Prediction held (~105 + 20 < 176).
Amendment 1's pass criterion (vLLM serves AND the benchmark's "ended:" line with 25 games) is half met at 12:37; the
score, when it comes, joins the Colab pool under Rule 1. c2 (same test) was lost before its load to my own retry
trap; c3's first notebook attempt died on a cache symlink I had added; both fixed in colab_runner.py / colab_retry_nb.sh.

## RESULT (2026-11-02 14:53 CST): c3 COMPLETE on Colab G4 — the fit holds and the run scores in range
candidate_pinned (848f336 + boot clock + pinned fix), runtime in a 26 GB exec tmpfs, model on local disk: papermill RC 0,
25 games, won 10, 11,151 actions, 2h 11m 49s of play, 813-824 tok/s, mean 50.21, median 44.78, 0 tracebacks. Worker RSS
peaked ~100.6 GiB (c1 died at 137). Colab G4 (176 GiB host, RTX PRO 6000 server edition) now runs the full model.
Third platform, n=1: Kaggle 38.58 / 54.70 / 32.22, server CP 35.78-47.94 (n=6), Colab 50.21. Output: ~/kaggle_local/
colab/working_c3/ (papermill.log, out.ipynb). The Colab credits are therefore a usable second card for the paper week.
