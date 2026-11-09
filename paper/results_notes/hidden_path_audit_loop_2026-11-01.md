# Hidden-path audit, part: game loop and model requests (2026-11-01)

Scope: everything between "game starts" and "submission.parquet written" in a scored rerun of v36/v37
(harness 8552964; v37 differs from v36 only in notebook cell 4, the mount path). Read: `tool_agent.py`,
`python_tool_sandbox.py`, `prompts.py`, `token_estimate.py`, `solver.py`, `vision_context.py`, `action.py`,
`utils/env.py`, `utils/openai_compat.py`, and TAAF `game.py`, `game_api.py`, `benchmark.py` (all at 8552964), plus notebook
cells 8, 9 and 11. The model-load path (`kaggle.py` watchdog/prefetcher) and setup scripts are another fork's.

Nothing was fixed, nothing committed. One local Python check was run against a scratch export of the tree, with no GPU,
Kaggle or tracked-file edits.

**Paths.** TA = `harness/src/ARC3-Inference/inference/agent/tool_agent.py`, SB = `.../agent/python_tool_sandbox.py`,
PR = `.../agent/prompts.py`, TE = `.../agent/token_estimate.py`, SV = `.../framework/solver.py`,
GA = `harness/src/tufa-arc-agi-framework/src/taaf/game_api.py`, BM = `.../taaf/benchmark.py`, NB = anchor notebook
`notebooks_duck/kaggle_staged/synesthesia/synesthesia.ipynb` (cell, line).

**Evidence base for "measured" counts.** 200 game-runs on Kaggle's RTX PRO 6000, public 25 games: the v36 anchor run
(8552964) and the seven controls C1-C7 (harness 12a000d with every switch off, equal to 8552964 by parity tests, not
byte-identical). Sources are the per-game `*_metrics.jsonl` files (21,261 requests, 21,275 tool calls, 11,756 turns) and
the transcripts. **Every one of these runs used the local engine, not Kaggle's gateway.** No log of a scored rerun exists,
so nothing on the gateway path below was observed.

## Findings, ranked by plausible impact

### 1. One failed game start aborts the whole scored run (hidden path only; inferred, not observed)

- **Claim.** BM:145-147 (comment): setup "runs inside this try so the finally below tears down every game". Nothing says a
  failed start ends the run, but that is the effect.
- **Code.**
  - BM:150-153 starts all 110 games one after another, before any play: `game_copy.start_game(session)`.
  - Nothing catches a per-game failure there. The enclosing `try` (BM:148) has only a `finally`, so the exception goes on
    past teardown, which marks every started game `crashed` (BM:210-220). It then leaves `bm.run` and NB c11 L144-149,
    which has no `except`, so the notebook cell fails.
  - A start fails whenever `arcade.make` returns None: `GA:240-241 raise RuntimeError(f"arc_agi.Arcade.make(...) returned None")`.
    `arc_agi` returns None on any exception while creating the remote wrapper (checked in the arc_agi 0.9.9 source,
    `base.py` `_create_remote_wrapper`: `except Exception as e: ... return None`; Kaggle ships 0.9.8, not checked).
  - The retry for unsent requests (GA:63-85) is mounted on the env only after `make` succeeds (GA:243). The game starts
    themselves are never retried.
  - The only guard is NB c11 L29-40, which waits until `GET /api/games` answers below 500.
- **Hidden path:** yes, only there. Commit runs build offline envs from local files.
- **Impact:** inferred. With 110 sequential gateway calls, one transient failure zeroes the submission. One of v36's four
  hidden submissions (57680782) ended in "system error"; whether this was the cause cannot be checked.

### 2. Context limits are enforced on an estimate that runs ~12% high (measured; documented upstream)

- **Claim.** The window is configured as 127,488 tokens, with a ceiling of 126,464 after the 512-token reply reserve and
  512-token margin (TA:449-452) and a trim target of 81,536.
- **Code.** Both are compared against `estimate_tokens` (TE), not server counts. TE:16-23 says this is deliberate: the
  estimate is set at about the 5th percentile of the chars-per-token ratio and "runs about 10 percent high on a median one".
- **Measured** (estimated vs server `prompt_tokens`, 21,261 requests): ratio p1 0.969, p10 1.037, p50 1.122, p90 1.196,
  p99 1.256; at estimates above 100k (7,851 requests) the p50 is 1.125.
- **What the model actually gets:** compaction fires at about 112.7k real tokens and trims back to about 72.7k, not 126k
  and 81.5k. The largest real prompt seen was 137,718 tokens, past the 127,488 window but under `--max-model-len` 147,072.
- Only one overflow retry happened in 200 game-runs.
- **Hidden path:** yes, same code.
- **Impact:** inferred, medium. The trim target is the top-ranked untested setting in `v36_settings_evidence`, and working
  memory (the no-echo result, -29.6) is the one resolved lever, so its real size matters when that setting is varied.

### 3. A retried RESET after a lost reply can send the game back to level 1 (hidden path only; unmeasurable)

- **Claim.** SV:898-903 (`_execute_auto_reset` docstring): when a RESET reply is lost, "the competition server leaves the
  fresh level as it is on the next RESET but still counts that RESET".
- **Code.**
  - That only holds if the engine runs with `ONLY_RESET_LEVELS=true`. arcengine `base_game.py` `handle_reset` (0.9.3, the
    local copy) does `full_reset()`, which goes to level 0 with score 0, whenever `_action_count == 0`. A `level_reset`
    zeros that count, so a second RESET right after an applied one is a full reset.
  - The harness sets the variable only in its own process: GA:251 `os.environ["ONLY_RESET_LEVELS"] = "true"` and NB c9 L3.
    In a scored rerun the engine runs in Kaggle's gateway container, which never sees it. GA:244-250's comment describes a
    protection that exists only in commit runs.
- **Hidden path:** yes. It happens only when a RESET is applied but its reply is lost, or when the model sends RESET at the
  start of a level. The model never sent RESET in 200 game-runs (measured 0), and the auto-reset always follows at least
  one action on the level.
- **Impact:** unknown. How the gateway would score a full reset mid-game is unknown.

### 4. A lost action reply leaves the harness one action behind the server (hidden path only; unmeasurable)

- GA:277-283: `env.step` returning None raises `RuntimeError`.
- SV:832-835: `step_env` turns that into an error result, "not executed", or stops the batch with `action_error`.
- If the gateway applied the action and only its reply was lost, the model is told nothing happened. The local board and
  action count then lag the server by one until the next successful reply replaces the state. The local per-level action
  count (and so its own score bookkeeping) stays one short.
- Commit runs never exercise this path.

### 5. The 30-second tool limit is wall-clock time and includes engine calls; a timeout throws away all printed output (measured on commit runs; hidden latency unknown)

- **Claim.** PR:138: "Each call has a hard 30-second time limit"; it says nothing about losing output.
- **Code.**
  - SB:838 sets the deadline once, and SB:913-942 runs every `action(...)` call synchronously inside it. The time covers
    each engine call plus serializing the whole game history into the sandbox.
  - On timeout, SB:963-975 returns `"stdout": ""`, so everything printed is lost. Actions already executed are kept.
- **Measured:** 33 timeouts in 21,275 tool calls (1 had executed actions). On the local engine, action-call latency is
  p99 0.28 s, max 2.5 s.
- In a scored rerun every action is an HTTP call to the gateway, latency unmeasured, so a batch of N actions spends N
  round-trips of the 30 s.
- **Impact:** low on commit runs; unknown on hidden runs.

### 6. The `result` variable is dropped whenever the snippet printed anything, and a non-string `result` is never capped (measured: 3 and 0)

- **Claim.** PR:137: "`result` ... its value comes back with whatever the snippet printed", and PR:138: the response "is
  capped to about {tool_output_tokens} tokens".
- **Code.** TA:1113-1117 returns `result` only `elif` stdout is empty. TA:836-840 and TA:827-831 truncate only `str`
  values, so a dict or list `result` goes out whole.
- **Local check** (scratch export, `_render_tool_payload` called directly): a dict `result` of 20,000 chars rendered at
  20,054 chars with no truncation flag; a 6,000-int list at 28,933 chars; a 20,000-char string was cut to 4,278.
- **Measured:** 3 of 16,731 transcript snippets assign `result` and also print, so their `result` was dropped. The largest
  tool result in 21,275 calls was 4,955 chars, so the cap bypass never happened.
- **Impact:** low, latent.

### 7. Any unexpected exception in a turn ends the game, with no retry (measured 0)

- TA:1690-1697 (`except Exception`) returns None. SV:460-461 then raises "Analyzer did not return a result.", and
  SV:484-489 marks the game `crashed` and finishes it with clock left.
- Exceptions before the try are not caught at all, e.g. a board-tower error in `_build_user_message` (TA:1457, which calls
  `vision_context.py:187-191`). They take the same route to `crashed`.
- **Measured:** 0 crashed games in 200: 154 ended on `runtime_limit`, 46 won.
- Latent. In the hidden path the gateway-specific exceptions mostly go through `step_env`, which converts them (finding 4).

### 8. Smaller latent silent paths (measured 0 unless stated)

- **A multi-call reply that acts before its last call** stops at the acting call (TA:1665-1669). It also sets
  `preserve_history = False`, so the turn's reasoning, code and executed action are all rolled out of the model's history.
  The same happens on a yield in the middle of a list (TA:1672-1676). 26 multi-call responses, 0 affected.
- **Malformed tool-call JSON** becomes `arguments = {}` (TA:1639-1640), so the model is told "python requires a non-empty
  `code` string" instead of "invalid JSON". 0 malformed arguments, 2 `empty_code` errors (neither from bad JSON).
- **Non-context HTTP 400s are retried forever.** Any non-context `RequestException` returns `retryable_failure`
  (TA:1682-1688). The solver retries the same step every 1 s (SV:462-474), each time from the rolled-back history, so a 400
  caused by persisted content would repeat until the clock ends. The one 400 seen was a context-length 400, recovered by
  the overflow retry.
- **The prompt after a request-error retry** says "The previous turn executed no action." (TA:659). The model's
  rolled-back history still shows its last action. 142 of 143 request errors were read timeouts at the per-game clock end,
  which end the game, so about 0 effect.
- **A sandbox host exception is replaced by a generic message** (SB:917-929): "action failed in sandbox host.". If it
  were raised after the engine ran the actions (e.g. in `_compact_action_result`), the model would be told it failed and
  the turn would not count as executed. 0 occurrences in the transcripts.
- **MOUSE coordinates are clamped to 0..63 without a message** (SV:731-732). The clamped value shows in `executed_actions`.

### 9. Unit and setting mismatches (low)

- **Tool output cap.** The prompt and truncation note say "about 1024 tokens" (PR:138; TA:842-846). The code enforces
  `tokens * 4` = 4,096 chars per field (TA:442), separately for stdout, error and result. By the harness's own measurement
  (TE:10-11, tool results average 2.1 chars/token), 4,096 chars is about 1,950 tokens, and the estimator prices it at
  1.8 chars/token, about 2,276.
- **The sandbox memory limit is not in the prompt.** RLIMIT_AS is 768 MiB (SB:481) and is never mentioned; a breach shows
  only as "Sandbox process exited unexpectedly." (6 in 200 game-runs, at actions 13-178, so not history size).
- **`LOCAL_ANALYZER_TOOL_TIMEOUT` is silently capped:** `min(30, ...)` (TA:436) means a value above 30 is ignored.
  `utils/env.py` falls back to the default on any unparsable value without logging (documented in its docstring). v36's
  values parse; three of them are confirmed in effect from metrics (ceiling 126,464, target 81,536, 591 yields at 150 s).
- **`configs/inference.json` is not read at run time:** analyzer timeout 120 there vs 900 run; 45 min there vs 3,918 s run.
  Already in `v36_settings_evidence`.
- **Unreachable code:** the second status check after `raise_for_status` (TA:810-815). The 30-turn history cap (TA:1281-1283)
  is inert while the target is below the budget, as in v36.

## Checked and consistent (no finding)

- The sandbox's importable modules (SB:47-62) equal the prompt's list of 14 (PR:136).
- The auto-RESET counts as one action: TAAF appends it to `history` and `actions_per_level` (`game.py` 560-571), matching TA:676.
- `history` covers the whole game (grid_view `HistoryViewEncoder`). Only animations (newest 16) and old game-over boards are thinned, as PR:93/77 say.
- **Request errors:** 143 total. 142 were read timeouts and 1 a connection abort, every one when the per-game clock ran
  out, after which the game ended. A separate context-length 400 was recovered by the overflow retry.
- **Scored-rerun clock fit** (NB c11 L49-58) is computed after the model server is ready. In C7 the server was ready at
  663 s and the run cell started at 673 s, so the load is not double-counted.
  - With a hard per-game cap T and 14 slots, at least 98 games have finished by 7T, so all 110 have started by then and
    every game ends by 8T. The 8-wave fit holds as long as per-game overrun stays inside the 600 s margin.
- The vLLM watchdog never restarted the server: in 9 runs checked, each log shows only "restart 0", the initial start.
- Sampling settings from the setup env (`taaf_setup_env.json`: temperature 0.6, top_p 0.95, top_k 20, thinking on, xhigh)
  are read at import by the same mechanism whose other values are confirmed in effect. The request logs don't store
  sampling, so 0.6 on the wire is inferred, not observed.

## Could not check

- Everything on the gateway path: `make` failure rate, lost replies, gateway latency per action, whether the gateway runs
  with `ONLY_RESET_LEVELS`, how it scores a full reset, and what it writes if the notebook is killed at 9 h. No scored-rerun
  logs exist, and commit runs use the local engine.
- Kaggle's `arc_agi` 0.9.8 wheel; I read 0.9.9.
- Whether Kaggle's 9-hour clock starts before `NOTEBOOK_START_EPOCH` (NB c3 L22, about 11 s into the kernel). If it
  starts earlier, the 600 s end margin is all that covers the gap. CL2 measured fast BOOT on GPU sessions.

Out of scope, noted: the watchdog restart path in `kaggle.py` (load fork); `framework/run.py` is the CLI entry, not on the
notebook's path.
