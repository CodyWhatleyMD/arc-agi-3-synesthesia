# Pre-statement: the clock-removal control ("From Synesthesia to Lobotomy"), 2026-10-30 16:20 CDT

Cody, 15:33-15:51. Title his. Thesis (his words paraphrased, to be replaced by his): ARC-AGI-3 was built against
memorization; what its scoring selected for at the top is wall-clock throughput, and the clock also shaped what we
built — a visual pathway modelled on how a brain sees a board, cut down arm by arm for speed, until the one cut that
cost points was the model's working memory (no-echo, -29.6). Our own runs are exhibit one.

## The question
Remove the clock. Which harnesses still clear levels, and does the public-leaderboard ORDER among them survive?
The finding is the REORDERING among contestants (or its absence), not our rank.

## Design
- Contestants: the publicly released top harnesses that run on our stack, as released, plus ours (v36 anchor).
  Candidates, to be confirmed by reading each repo: dfranzen (github.com/da-fr/arc-agi-3-solution; already ported
  once), Tufa Duck (the common base), Lohit (if public), xz (if released after close). Each run with the model its
  release specifies; where a release supports it, ALSO with Flash-Next v22 (ours) so one comparison isolates the
  harness. Both rows reported.
- Clock: no wall-clock budget for the job or the game. A game ends on WIN, GAME_OVER, or the benchmark's action cap.
  Server: the same vLLM 0.31 runtime for all; concurrency fixed (one game at a time per harness) so no harness gains
  from parallel scheduling.
- Metric: the benchmark's own score with the time term removed = levels completed and actions per level (the
  skill-efficiency term). Also recorded per game: wall-clock actually used, tokens, requests, so the timed score can
  be reconstructed and the two compared.
- Games: the public 25 AND the three custom held-out games (zk01, zs02, zg03; byte-unseen by every harness) reported
  separately; the hidden set is unavailable to us.
- n: at least 2 untimed runs per harness on the public 25 (ICC 0.55 says one run of 25 games orders harnesses
  roughly; two bounds the swing), 1 on the custom three. More if the week allows.
- Platform: local (RTX PRO 6000 Max-Q); all contestants on the same card, so the platform is a constant.

## Predictions, written before any run
P1 (Cody's): the public-LB gap between the top harnesses and ours shrinks when the clock is removed.
P2 (reordering): at least one pair of contestants adjacent on the public LB swaps order untimed.
P3 (working memory survives the clock): the no-echo variant of ours loses levels untimed as it did timed; the cut
was cognitive, not a throughput trade.
P4 (null form, stated so it can embarrass the title): the untimed order equals the timed order and gaps are
proportional. Then the clock measured what the games measure and the paper reports that.

## What this does NOT claim
Nothing about the hidden set; nothing about the contestants' intent (optimizing a published metric is the game);
nothing about our channel beating anything — the readback (notes/prestate_readback RESULT) already shows the image
channel does not read cell colour and the paper says so in its own section.

## Lane
Starts after the competition closes (Mon 2026-11-02 17:59 CDT): both cards free; Kaggle quota untouched. Paper due
Nov 9. Franzen's harness first (known to run), then Duck, then any other release. Porting work for the others is
unsized and is reported as such.
