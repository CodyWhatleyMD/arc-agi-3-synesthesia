# Pre-statement: the submission candidate's commit run (2026-11-01, before it runs)

Candidate: harness fa326e3 = time stop with the review's three fixes (7161345) + start retry/skip (4d63b91), on v37's
lineage. Notebook: pool clock, pool_stall_seconds 1500, pool_min_share_s 600, park off (the simulation's settings),
ARC3_START_ATTEMPTS=4, ARC3_START_SKIP=1. Kernel codywhatleymd/arc-agi-3-synesthesia-candidate, dataset cand-k1.
One commit run on the public 25 (a test, not a submission).

PASS (submit it in today's window, Cody's decision) only if ALL hold:
1. Clean run: no Python traceback in the notebook or harness log, no HTTP 500 from the server, the run ends by itself
   (no ERROR status, no teardown failure).
2. Switches visible: the pool-clock line, "pool time-based stop: stall_seconds=1500.0 min_share_s=600.0", and the arm's
   ARC3_START_ATTEMPTS / ARC3_START_SKIP print.
3. No starvation: all 25 games started and every one made > 0 actions (the no-stop pool clock left su15 and tr87 at 0,
   sb26 at 15 and s5i5 at 44).
4. Score inside or above the v36-config public range: mean >= 32.6 (the lowest of C1-C7; the range is 32.6-51.4 with
   v37's 51.37 at the top).

FAIL on any one of them. If it fails, today's slot gets v37 + guard (the start-retry arm) or nothing; Cody's call.
Reported alongside, not gating: levels cleared (v37 123, no-stop pool clock 89), total actions, the number of time-stall
and reserve stops, and per-game differences against v37 and the no-stop run. One run; a public-25 mean inside the range
is not evidence the candidate scores higher. That evidence is the 110-game simulation (+3.0 points, 10th-90th percentile
+0.9 to +4.9, resting on games clearing past ~65 minutes).
