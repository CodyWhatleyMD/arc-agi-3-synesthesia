# The structure of the run-to-run noise (2026-10-27 20:24 CDT; from CL3's questions; six valid local runs)

Runs: r2, r3, r4 (ON = shipped student arm) and bo1b, bo2b, bo3b (OFF = no board channel), 25 public games each,
9,300 s, per-game clock 3,918 s. Computed from benchmark.json (game_runs.history wallclock per action, which counts
from the BENCHMARK start, so every time below is measured from the game's own first action).

## It is not a level-1 mixture
Clear rate (share of game-runs with >= 1 level): ON 73/75 = 0.973, OFF 73/75 = 0.973. Conditional mean score given a
clear: ON 43.10, OFF 39.38. The arm difference is entirely in HOW FAR a run gets, not whether it starts.
Only sc25 and sk48 flip clear/no-clear across the three ON runs.

## Game vs luck (three identical ON runs)
Per-game score: between-game variance 790.2, within-game (run-to-run) variance 658.1, ICC 0.55: 45% of a game's
score variance is run-to-run luck in the shipped config. OFF arm: ICC 0.68 (between 831.8, within 396.2).
A single-run leaderboard therefore ranks agents partly by the draw; this is a paper-stateable result.

## When clears happen (fraction of the game's own clock)
First clear, n=146 successful game-runs: p50 0.069, p75 0.147, p90 0.295, p95 0.509, p99 0.799, max 0.896.
Gap between consecutive clears, n=612 cleared levels: p50 0.099, p75 0.196, p90 0.370, p95 0.465, p99 0.830,
max 0.903; 19.1% of cleared levels took > 25% of the clock since the previous clear, 11.9% > 33%, 3.9% > 50%.
Terminal stalls (game ended unfinished, n=112): time since the last clear p25 0.09, p50 0.25, p75 0.56.

## Verdict on in-game restarts (the "clever move" of 20:16)
A stall trigger at 33% of the clock since the last clear would have killed 73 of 612 eventual clears to fire on 42
of 112 terminal stalls; and RESET restarts the whole game (observed 08-31), forfeiting cleared levels. A "zero levels
by X%" trigger almost never fires (97.3% clear something). Not built. The idea was a story about the variance; the
variance lives mid-game on specific mechanics, where a restart costs more than it buys.

## What survives (CL3)
- Report clear rate and conditional score separately in the paper (done above; both arms' rates are equal).
- The board-history accumulation (median 13, max 48 boards per request until compaction) makes behaviour depend on
  WHEN compaction fires: a harness-driven variance source. The history-window arm (SYN_HISTORY_BOARDS_KEEP on
  syn/batch-a; or a per-turn window) is therefore a variance experiment first and a payload experiment second.
  Pre-state it as such: primary = within-config run-to-run variance (ICC) with and without the window, score second.
- Successive halving (k short probes, continue the best) is ruled out by the competition's one-play-per-game rule.
