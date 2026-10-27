# Pre-statement: the Batch A arm (written 2026-10-26 19:35 CDT, before any Batch A run)

Written before any arm result exists, so what counts as a result is fixed before the numbers land.
Owner of the measurement design: Sakshi. Harness: syn/batch-a 12a000d (145/145; all switches off =
8552964's system prompt byte for byte, test_g5a_prompts.py; per-port parity tests in tests/harness).

## Arms

| arm | harness | env |
|---|---|---|
| control | arc3-synesthesia-harness-arms @ 12a000d | no SYN_* set (= v8 by the parity tests) |
| batch-a | same dataset | the 11 boolean switches on: SYN_FIX_TRANSITION_RESULT, SYN_TERMINAL_RAISE, SYN_SANDBOX_HYGIENE, SYN_TRANSIENT_HINT, SYN_FIX_OPENER, SYN_GAMEOVER_TEXT, SYN_LEVEL_TRANSFER, SYN_REQUEST_ROBUST, SYN_ACTION_INFO, SYN_UNDO_INFO, SYN_WM_FREE (=1). SYN_HISTORY_BOARDS_KEEP unset: it is its own arm (notes/payload_cost_2026-10-26.md) |

One combined arm, by decision (Cody left it to Sakshi, 10-26 13:08): at n=1-3 only large effects are
visible, so one-switch arms would mostly read null. If batch-a moves, it is ablated switch by switch
(every switch defaults off, so each ablation is one env line).

## Platforms, never pooled across

- **Local (RTX 6000 Max-Q, 9,300 s job budget, all 25 games start):** controls r2, r3, r4 (the anchor
  notebook, harness 8552964); batch-a x2. Assumption, stated: 12a000d all-off behaves as 8552964 (proven
  by the parity tests, not by a run; the Kaggle control below tests it in a real run).
- **Kaggle (RTX Pro 6000, commit runs, public 25):** a round = control and batch-a started together, one
  per GPU session. Planned: 3 rounds (6 runs, ~17 GPU-h). The number of rounds is fixed here, not after
  seeing a round. Kaggle results are compared only with Kaggle results (v36 = an extra Kaggle control at
  harness 8552964, reported alongside, not pooled with the 12a000d controls).

## Primary statistic (the only one that decides)

Per game: mean score over the arm's runs minus mean score over the control's runs on that platform.
Over the 25 games: the mean of those differences, 95% paired bootstrap CI (10,000 resamples of games),
and the sign test, from scripts/compare_benchmark_logs.py.

- Reads as a gain only if the CI's lower bound is above 0. Reads as a loss only if its upper bound is below 0.
- Otherwise: "not resolved at this n", reported with the point estimate and the CI. Never "no effect".
- For scale: two identical local runs (r2 vs r3) differ by +4.08, CI [-8.71, +16.82] (findings 216ax).

## Exploratory (reported, labelled exploratory, never deciding)

- The coin-flip games (swing >= 40 across v36/r2/r3: cn04 dc22 m0r0 r11l s5i5 sb26 sc25 sp80 tn36 vc33):
  fraction of runs scoring >= 50, arm vs control.
- The stable bottom (bp35 lf52 sk48 wa30 ls20): levels cleared.
- Actions per job-second; tracebacks; HTTP 400s; switch-check line present in every arm log.

## Invalid runs (fixed and rerun, not counted)

A run with a traceback in the harness, an HTTP 400, a missing `synesthesia: switches checked:` line in an
arm log, or fewer than 25 games started. The decision to discard is made from those criteria only, before
reading the run's score.

## My prior (Sakshi, before any number)

Franzen's whole stack scored 27.89 hidden vs our ~20, but these are only his agent-side changes, so I
expect a public-25 gain of 0 to +6 if any. At local 2 v 3 runs that is inside the noise: I put ~65% on
"not resolved" locally and ~60% on a positive point estimate. Three Kaggle rounds help; a reading of
"gain" would need a larger effect than I expect.
