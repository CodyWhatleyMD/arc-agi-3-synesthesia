# Pre-statement: local 100-game scale test, time stop vs capped clock (2026-11-01 ~06:25 CST, kasoti)

Question. The candidate's simulated gain over v36's 65-min clock (+3.00 [+0.93,+4.92] on 110 games,
notes/pool_timestop_sim_2026-10-31.md) rests entirely on games still clearing levels after 3,918 s of their own play
(pessimistic variant: -0.06). The candidate's public-25 commit run (CAND_candidate-k1) put +1.36 on its own mean from
such late clears (3 games; cn04 alone ~1.1). This tests it at hidden scale, on one machine.

Design. Two runs on the local RTX PRO 6000, sequential, each 25 public games x 4 passes = 100 game-runs at
concurrency 14, commit-run budget 32,400 s (soft end at 31,800 s from notebook start):
- A = candidate_pinned (harness 848f336: pool clock, stall 1500 s, min share 600 s, start retry, ARM_PINNED_ROUND_MB=1024).
- B = v37-pinned (harness 2c51989: v36's 3,918 s per-game clock, ARM_PINNED_ROUND_MB=1024).
Built by scripts/build_synesthesia_notebook.py --passes 4 --max-runtime-s 32400 on the flags that rebuild each staged
notebook byte-identical; each differs from its staged original only in name, budget and the passes block.
B's schedule fits: 100 games / 14 slots x 3,918 s = 27,985 s + load < 31,800 s, so B starts every game (as v36 does on 110).

Readings, fixed now:
1. Primary, within run A (paired, least noisy): the score A would lose if every game were cut at 3,918 s of its own
   play (levels cleared later removed; method as in 8ecc3b0's follow-up). >= +2.5 points supports the sim's main case;
   <= +1.0 supports the pessimistic case (time stop worth ~0); between is unresolved.
2. Secondary: A mean minus B mean over 100 game-runs. One run each; a 100-game mean has sd ~2.4 (from the 25-game
   control sd 5.07 / 2), so |A-B| < ~5 is not a resolved difference whatever its sign.
3. Also reported: games > 0 (of 100), levels, game-runs that never started (expected 0 for both), tracebacks/500s.
Invalid if: either run errors before its soft end, root disk < 3 GB, or the host's memory is shared with another
GPU/CPU job during either run.

Restart (09:50 CST): the first A run (tag x4_a, 06:06) was stopped at 06:49 to free the 6000 for the drafter lane (Cody's priority); it is void. Rerun as tags x4a2 then x4b2, same notebooks (sha d8fede5e70b7 for A), same readings.
