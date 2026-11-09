# Pre-statement: start-retry arm (2026-11-01, before any Kaggle run)

Found by CL1's game-loop audit (notes/hidden_path_audit_loop_2026-11-01.md): taaf/benchmark.py starts all games one
after another with no per-game handling, and game_api.py raises when arcade.make returns None (arc_agi's remote wrapper
swallows exceptions and returns None). The enclosing try has only a finally, so one transient gateway failure while
starting any one of the 110 hidden games fails the whole run. Commit runs never take this path (offline envs).

Arm: v37 (harness 8552964) + ARC3_START_ATTEMPTS=4 (arcade.make retried with 5/10/20 s backoff) + ARC3_START_SKIP=1 (a
game that still cannot start is recorded crashed, score 0, and the rest play). Both unset = v37 unchanged. Branch
start-retry; tests in tests/start_retry/test_start_retry.py (helper cases; real 110-game Benchmark.run with one
unstartable game: crashed + score 0, 109 others start and finish, both diagnostics modes; without the skip it raises).

What the commit run can and cannot show: on the public 25 every start succeeds, so the new path is not exercised there.
The run checks only that nothing else changed. Pass: all 25 games start, no new tracebacks, the switches print, and the
score is inside v36's control range (32.6-51.4). It cannot show the hidden-run benefit; that rests on the code and the tests.

## Amendment before any run (01:45): the scorecard hold

CL1's review of a2e31b2 found that the skip would zero the run if the FIRST game failed: game_api finished the failed
game's run on the shared competition scorecard, dropping its count to 0 and closing it, so every later open_run raised
"already closed". Fixed in 4d63b91: under ARC3_START_SKIP a failed start holds its open run, and Benchmark releases the held
runs after the setup loop (again, idempotently, in finally). tests/start_retry/test_scorecard_hold.py (real Benchmark and
_CompetitionScorecard, counted fake arcade): first / middle / first+last / every game failing -> scorecard closes exactly
once, after the last finish; skip off raises as before. The same test fails on a2e31b2 (first fails -> all 11 others
crashed), so it discriminates. a2e31b2 never ran: its push queue was stopped after the dataset upload (sr-k1), before the
notebook push. The arm now runs 4d63b91 on dataset sr-k2.
