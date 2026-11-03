# Pre-statement: the late-submission program (hidden set, post-deadline), 2026-11-02 18:15 CST, Sakshi

The board closed 23:59 UTC. Kaggle still accepts late submissions (Cody: "not eligible to win", "we have 100"); each
one reruns the notebook on the hidden 110 games on Kaggle's scoring compute (not our GPU quota) and returns a public
and, once the private board is published, a private score. Written before any late score lands. 57925231 (Cody,
18:04 CST) is the first; its config is to be recorded when he says what it is.

## What a late score is, and is not
- It is a hidden-set measurement of a notebook version: 110 games, ~9 h, the same scorer as the counted entries.
- It is not rank-eligible and the paper says so wherever one is cited: "late submission (post-deadline, unranked)".
- The paper's Accuracy row stays the counted pair (57886730 = 23.21, 57790633 = 21.75) and their private halves.

## Order (one notebook version per entry; nothing edited between replicates)
Block 1, replicates of the two selected configs on the set that counts — the paper's noise claim where it matters:
  candidate_pinned (kernel candidate-pinned v1 = 57886730's version) and room S (363241028) alternating, until each
  has n=5 hidden scores (counted + late). Expected: hidden spread of identical code sd ~3-5, mirroring the fixed-host
  CP sd 4.50; a spread >8 means the hidden set is as lottery-like as the public 25.
Block 2, arms with no hidden replicate yet, n=3 each: no-echo, tower-off, native tower, Batch A, room G-c
  (Cody's; has one at 15.28). Expected: no-echo well below the pool on the hidden set too (local −29.6 RESOLVED);
  the others NOT RESOLVED at n=3 unless |Δ| > ~6.
Block 3 (if the count allows): v36 anchor to n=5; the untimed design cannot be submitted (the 9 h cap applies).

## Rules
- Every entry's description names the config and "LATE, unranked". Each landed score goes into the §7 table with
  that label; the paper's counted rows are never mixed with late rows in one n.
- Daily limit unknown for late entries (counted was 1/day). If parallel entries are allowed, Block 1 first, two at a
  time; if 1/day, Block 1 alternating through Nov 8 (six entries), Block 2 after the paper.
- Pre-stated comparisons use scripts/compare_arm_groups.py --cluster on per-game hidden results only if Kaggle
  exposes them (it exposes totals; per-game hidden results are not available, so hidden comparisons are run-level
  means and sds only: no paired-by-game CI on the hidden set).

## Amendment 1 (18:15 CST): Cody's hot-cache test, stated before the scores
57925231 = candidate_pinned (Cody's "replicate 4"; the 3rd hidden run of that config after 57886730, 57902610).
Cody is submitting candidate_pinned replicates 5 and 6 WHILE 4 is being scored, "seeing if a hot cache will boost
the score" (the room S v1/v2 boot-to-play gap of 265 s is the motivation). Prediction under his hypothesis: entries
scored concurrently with another copy of the same notebook reach play sooner and score higher than isolated runs.
What can be seen: hidden scores only (no logs, no boot times, no per-game results). Comparison: the concurrent set
{5, 6, and 4 if it overlaps them} vs the isolated set {57886730, 57902610}, run-level means; at sd ~4.5 and n=3 vs 2 a
boost is detectable only if it exceeds ~7 points, and host assignment of the scorer is unknown (a hot NFS cache is
per-server, so concurrency does not guarantee a shared host). A result either way is NOT RESOLVED unless the gap
exceeds the two sets' spread; the honest product is six candidate_pinned hidden scores, labelled by concurrency.

### Result 1 (2026-11-03 02:43 CST): 57925231 (candidate_pinned, LATE, unranked) = 19.37 public half
candidate_pinned on the hidden public half, n=3: 23.21 (counted), 21.90 (counted copy), 19.37 (late) — mean 21.49,
sd 1.93, range 3.84. Private column still empty for every entry (board not yet published). Replicates "5 and 6"
(Cody, 18:13, to be submitted concurrently) do not appear in the submission list: only one entry after 57902610
exists, so either they were not accepted (one late entry per day?) or not sent — Cody to say; the hot-cache test
has no concurrent entries yet.
