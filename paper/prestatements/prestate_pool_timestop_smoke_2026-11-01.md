# Pre-statement: local smoke of the pool-clock time stop (harness 7161345) on the RTX PRO 6000, before the run

Written 2026-11-01 ~07:20 UTC (01:20 CST; daylight time ended at 07:00 UTC today, so local clocks now read CST), before
the smoke container starts. GPU slot 2 (the 6000), checked empty first (8 MiB used, no arc3-local container).

## What runs

- Harness: pool-clock 7161345195f7121c28f41c739e816ea1654f69e5 (the review's three fixes on 8d10d07). Dataset folder
  /home/ignaz/kaggle_local/datasets/arc3-syn-harness-pool-ts1-smoke (builder `git archive`; solver.py byte-identical
  to the worktree's at 7161345). Local only: never uploaded.
- Notebook: notebooks_duck/kaggle_staged/synesthesia_pool_timestop_smoke/synesthesia.ipynb (sha256 4ab33aa7...f9777),
  built by the main checkout's builder (with the cell-4 mount fix):
  `build_synesthesia_notebook.py --commit 7161345195f7121c28f41c739e816ea1654f69e5 --pool-clock --pool-park
  --pool-stall-seconds 600 --pool-min-share 1100 --max-runtime-s 2850 --kernel-id
  codywhatleymd/arc-agi-3-synesthesia-pool-ts1-smoke --title 'ARC-AGI-3 Synesthesia pool ts1 smoke' --dataset-slug
  codywhatleymd/arc3-syn-harness-pool-ts1-smoke --out notebooks_duck/kaggle_staged/synesthesia_pool_timestop_smoke`.
  Never pushed: its kernel id only satisfies the builder.
- Launcher: ~/kaggle_local/run_synesthesia_slug.sh (run_synesthesia_r0.sh with HARNESS_SLUG, no extra dataset), tag
  ts1_smoke: Kaggle GPU image (gcr.io/kaggle-gpu-images/python:latest, 9a6bcfda6d03), papermill, the local v22/3
  model, runtime, tower and competition inputs as in every local run. It also writes run_synesthesia_ts1_smoke.log.ts,
  each log line stamped with time.time() on arrival (the "pool clock:" lines carry no time).
- 25 public games, 14 slots, a commit-run soft end: max-runtime-s 2850 -> soft end = notebook start + 2,250 s, so
  about T = 2,000 s of play after a ~250 s load (park smoke 10-31: 252 s); games stop 60 s before the soft end and TAAF
  cancels the solver at it. Action cuts left at 1,500 / 750 (they cannot fire in ~200 actions per game).

## Why these settings (S = pool_stall_seconds 600 s, M = pool_min_share_s 1,100 s, park on)

Chosen on the REAL HarnessSolver._run_games (tests/pool_clock/_pool_common.py at 7161345, 100x clock, the 600 s floor,
900 s analyzer timeout, 120 s drain, 60 s soft-end game margin and the resume workers' 5 s poll all scaled; scratch
script smoke_design_sim.py, not committed): 25 games in the notebook's order, each clearing levels at the action counts
it cleared them in the local 14-stream run r6, requests from the C1-C7 latency table (local r6 / gc1 / ne1 have the
same shape: poll-wait q99 245 / 269 / 239 s vs C1-C7 283 s), park on, soft end T, killed at T. Every run, as
(T, S, M, seed): time-stall parks / reserve parks / resume lines (of which followed by >= 1 action) / games never
started:
- 2000/300/900/1 (resume poll NOT yet scaled: 500 s): 19 / 1 / 20 (7) / 0
- 2000/300/900/1: 19 / 1 / 20 (9) / 0; 2000/450/900/1: 16 / 4 / 20 (9) / 0; 2000/600/900/1: 14 / 5 / 19 (8) / 0;
  2000/600/900/2: 12 / 7 / 19 (8) / 0; 2000/600/900/3: 11 / 6 / 17 (5) / 0
- 2000/600/1000/1: 9 / 5 / 14 (4) / 0; 2000/600/1000/2: 8 / 5 / 13 (3) / 0
- 2000/600/1100/1: 9 / 5 / 14 (4) / 0; 2000/600/1100/2: 8 / 6 / 14 (3) / 0
- 2000/450/1100/1: 11 / 3 / 14 (4) / 0; 2000/450/1100/2: 10 / 4 / 14 (4) / 0; 2200/600/1150/1: 11 / 3 / 14 (4) / 0
No traceback in any run. S 300 (the task's example) left 1 reserve stop: at the share's end most games have gone 300 s
without a clear, and the time-stall is checked first. M 1,100 > T/2: the first wave's shares end at ~0.53-0.56 T
with less than M left, so the reserve is breached there whatever the boundary wait (at M 900 it needs a wait > ~200 s).

## Expectations (not criteria)

At ~1,050-1,200 s of play the first wave's shares end: ~8-9 time-stall parks and ~5-6 reserve parks within a few
minutes; all 25 games started by ~1,250 s; ~3-4 resumes that play; ~10 more resumes at T - 60 s, each finishing a
parked game at once (soft-end margin).

## What refutes "the time stop works as designed on the real stack"

Times come from the stamped log (lag about a second), game starts and actions from the per-game metrics
(game_start, action, level_cleared, request, request_error). "The last start" = the last game_start event: from then
on no game is unstarted.

- R1 time-stall: any time-stall park line whose detail shows < 600 s without a clear, or less time in the slot than
  the share it names; or a time-stall at a moment with no game waiting (no game_start after it AND no game parked and
  not yet resumed at that moment).
- R2 reserve: any reserve park line whose "F of U unstarted" has F >= U or U < 1, or less time in the slot than the
  share; or a reserve park stamped more than 5 s after the last start.
- R3 resume: a resume stamped more than 5 s before the last start; or a resume that does not pick, among the games
  parked at that moment (from the park/resume lines in order), the deepest level, ties broken by fewest actions since
  the last clear.
- R4 starts: any of the 25 games without a game_start event or without an action before T - 60 s.
- R5 clean: any "Traceback" in the papermill log or stdout.log; any HTTP 500 in vllm-openai-server.log; any
  request_error other than a read timeout ending within 10 s of a game's soft-end stop (T - 60 s), which every timed run
  has (r6: 17, all read timeouts capped at the time left); any game state "crashed".
- R6 end: papermill does not exit 0, or out.ipynb / summary.txt is missing, or summary.txt lists fewer than 25 runs.
VOID, not a pass: no time-stall park (rule untested), no reserve park (rule untested), no resume followed by an action.
Reported, not criteria: every event count, per-line details, "pool clock: stop" lines (with park on there should be
none before the soft end), request timeouts, the server's prompt throughput, every game's level and actions.

## What it cannot show

Scores or settings: T, S and M are chosen to make both rules fire in ~30 min, not the candidate's regime (S 1,500 s, M
600 s over 9 h). The candidate runs with park OFF: its time stops finish the game ("pool clock: stop" line), a path
this smoke (park on) does not exercise on the real stack; the unit tests (U4) do. Nothing about Kaggle mounts, the
scored rerun's end of play (pool_end_margin_s applies only without a soft end) or the 110-game hidden run.

## Result (written 2026-11-01 ~08:02 UTC, after the run): PASS, no criterion refuted, not VOID

Run: container arc3-local-ts1_smoke launched 07:17:46 UTC, pool clock on 07:22:25 (load 279 s, so T = 1,974 s, not
~2,000; games stop at +1,914 s), play ended 07:54:25, papermill exited rc 0 at 07:55:42; afterwards the 6000 showed
8 MiB used, no compute process, no arc3-local container. Logs: ~/kaggle_local/run_synesthesia_ts1_smoke.log (+ .ts),
working_ts1_smoke/, copies ts1_smoke_stdout_1101.log / ts1_smoke_server_1101.log, the check's full output
ts1_smoke_analysis_1101.txt and its scripts ts1_smoke_tools/ (analyze_smoke.py, smoke_design_sim.py). Times below are
seconds after the pool clock came on.

- Events: 7 time-stall parks (+1,106..+1,153), 7 reserve parks (+1,103..+1,127), 0 action-cut parks, 0 "pool clock:
  stop" lines, 14 resumes: 3 that played (lp85 L6 at +1,143: 140 action events after it; ar25 L6 at +1,150: 6; tu93
  L4 at +1,153: 63) and 11 at +1,914-1,915, the soft-end margin, each finishing a parked game with 0 actions.
- R1 holds: every time-stall had 640-1,134 s without a clear (>= 600) and was 1,105-1,152 s into a 1,100 s share; at
  each one games were waiting (unstarted until +1,134, parked games after).
- R2 holds: the 7 reserve parks read "0 of U unstarted games fit 1100 s" with U = 11, 10, 9, 7, 5, 4, 2, each 1,103-1,126
  s into a 1,100 s share, all before the last start (+1,134). Three of them (lp85, ar25, r11l) came right after a level
  clear (0 actions since it): the reserve stops games "progressing or not", as designed.
- R3 holds: the first resume came 9 s after the last start; each resume took the deepest parked level, ties by fewest
  actions since the last clear (lp85 and ar25 both L6 / 0, lp85 parked first; tu93 L4 / 10 before vc33 L4 / 34). One pair
  is undecidable from the logs: at +1,914 r11l (L3 / 0) and m0r0 (L3 / 15) were resumed by two threads in the same
  millisecond (both stamped 1793519659.719, the two lines glued on one line of the papermill log); the papermill log
  prints r11l first, stdout.log m0r0 first, so neither print order is the pop order. Every other resume is in rule
  order in both logs.
- R4 holds: 25 game_start events, every game acted before +1,914; the last start +1,134 s; the last first action
  +1,331 s (tr87, ~197 s after taking its slot).
- R5 holds: 0 "Traceback" in the papermill log and stdout.log; the server log has 1,066 HTTP 200 and no other status;
  14 request errors (and 14 analyzer retries), all read timeouts ending within 10 s of the soft-end game stop; no
  crashed game (all 25 stop reasons runtime_limit, the soft-end margin).
- R6 holds: rc 0, out.ipynb written, summary.txt lists 25 runs (won 0, mean 14.19 over a 32-minute run: no meaning).
- Against the expectations: time-stall 7 (expected ~8-9), reserve 7 (~5-6), played resumes 3 (~3-4), end-of-run
  resumes 11 (~10), all started by +1,134 (~1,250).
Not seen, because nothing printed it: the shares the second wave took (the solver logs them at INFO, which the
notebook does not show); no game was stopped after +1,153, consistent with their being protected to the end.
Still not exercised on the real stack: the candidate's park-off path (a time stop that finishes the game).
