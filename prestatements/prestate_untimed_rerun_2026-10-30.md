# Pre-statement: the clock-removal control ("From Synesthesia to Lobotomy"), 2026-10-30 16:20 CDT

The investigator, 15:33-15:51. Title his. Thesis (his words paraphrased, to be replaced by his): ARC-AGI-3 was built against
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
P1 (the investigator's): the public-LB gap between the top harnesses and ours shrinks when the clock is removed.
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

## Amendment 2 (2026-11-02 13:45 CST, CL1) — R0 replicates on the GCP server, unattended

The restoration pre-statement's item 4 ("the untimed run-to-run noise: R0 twice if the week allows") is run on the
server, which otherwise sits idle: queue entries ut1, ut2, ut3 = the R0 harness (arc3-synesthesia-harness-r0,
notebook sha 630a9c6b = R0's and r0rep3's) run one game at a time, untimed, on the GCP server (RTX PRO 6000 server
edition, g4-standard-48). Written before any of them starts.
- Same Spot rule as the replicate series: a run counts only if it exits (DONE file); a preempted run is re-run from
  scratch by the queue. The watcher stops the VM when the queue is empty.
- Host difference: R0 and r0rep3 are on the local Max-Q 6000; ut1-3 on the server edition. The untimed metric is
  levels and actions, not wall-clock, so host speed should not enter the score; if ut runs differ from the local R0
  pair beyond the local pair's own spread, the host is a candidate cause and is said so.
- Expectation: R0's untimed levels/game sit near 6 (R0: 6.15 on 13 games); ut runs land in that range with a spread
  no larger than the timed CP spread (sd 4.50 at n=6). No comparison is made before ≥2 ut runs exit.
- Budget: ~$1.10/h Spot; a pass's duration is unknown (r0rep3 is 5.5 h in at 10.7k actions); three passes are
  expected to cost on the order of the remaining $32 of credits. Investigator: "set them up and let them run" (13:39).

### Correction to amendment 2 (14:58 CST): the cost line was wrong by ~8x; ut2 and ut3 withdrawn
r0rep3 (local) after 6 h: three games, ~2-2.5 h per game (the per-game action cap is 5,184; R0's capped games ran
4-5k actions at ~2.4 s/action). A 25-game untimed pass is therefore ~2.5-3 DAYS, not hours; three passes ≈ 9 days ≈
$240 at $1.10/h, far past the Nov 9 paper and the $32 of credits. ut2 and ut3 withdrawn (DONE=skip on the VM, queue
lines removed); ut1 runs on (~3 days, ~$80; finishes ~Nov 5-6). The paper's "R0 twice" is then R0 (13 games) +
r0rep3 (local, ~Nov 5) + ut1 (server). The investigator can re-add ut2/ut3 by appending "ut2 r0" to ~/queue.txt on the VM and
removing /data/runs/ut2/DONE (and a fresh line in /data/queue.log).
