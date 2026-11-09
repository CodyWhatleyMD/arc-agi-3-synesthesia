# Harness defects — found 2026-09-03/04

Two independent read-only code reviews (uncorrelated agents) plus self-review during the
reasoner/doubter build. Every claim below was verified against source or run data; where a
claim is unverified it says so.

## A. BASE HARNESS `scripts/qwen_tools_agent.py` — project-wide, UNFIXED at time of writing

### A1. Engine-exception path skips all bookkeeping and hides its own error (SEVERE, REALIZED)
`do_action()` lines 677-686 (and the identical shape in `maybe_auto_reset()` 728-733):
on `env.step()` raising, it charges an action, sets `"error"`, and returns EARLY — before
`_record()`. So `self.state` / `frames` / `history` / `_ledger` / no-change accounting never
update.

Two compounding consequences:
1. `maybe_auto_reset()` (719) decides whether to fire by reading `self.state` — the exact field
   that never refreshed. The recovery mechanism cannot engage, precisely when the engine's 400
   is signalling the game IS terminal.
2. The `"error"` key is read NOWHERE. `t_take_action` never surfaces it; `run_python`'s `act()`
   closure filters to `("changed","state","levels")`. The model cannot learn an action was
   rejected — it sees an ordinary "NO CHANGE". The exception-path dict is also missing `"levels"`,
   violating the documented `act()` contract.

Worst case is the pattern the tool description recommends: an `act()` loop inside `run_python`,
where `maybe_auto_reset()` runs only once after `exec()` completes — the loop can burn the whole
remaining budget silently.

**NOT HYPOTHETICAL.** Signature = action charged with no frame written. Scan of all 146 game-runs:
16 affected.

    mmed25_honest/su15    actions=2019  frames=1995  gap=+24
    mmed25_honest/bp35    actions=3000  frames=2978  gap=+22
    mmed25_honest/ar25    actions=2277  frames=2264  gap=+13
    mmed25_default/su15   actions= 400  frames= 394  gap=+6
    mmed25_default/lp85, mmed25_default/g50t, mmed25_default/sb26, mab_floor/ls20,
    mab_default.ctx16k-invalid/cd82, mmed25_honest/cd82, mmed25_honest/m0r0,
    mmed_default/cd82, mmed_floor/lp85, mmed_floor_v2/cd82, mmed_floor_v2/ls20,
    ab_default/ls20                                        (+1 to +3 each)

No `runs/reasoner_doubter/*` run is affected.

### A2. Context-overflow force-trim can orphan a tool message (lines 923-933)
Slices `msgs[-6:]` with no role-alignment guard. `evict()` (1124-1152) explicitly walks past
leading `"tool"` messages to avoid orphaning one from its `assistant` tool_calls; this branch does
not. Turns are not uniformly sized (multi-tool-call turns, coach messages, eviction notices), so
the slice can start on a `"tool"` message whose assistant is now dropped -> structurally invalid
request -> repeated failure into the generic retry branch -> run ends early at `llm.errors > 12`.
Secondary: when `len(msgs) <= 8`, `tail = msgs[2:]` makes the branch a NO-OP, so an overflow caused
by one oversized message can never shrink and recurs every turn.

### A3. Meter-band calibration conflates call-order with frame-order (`_describe_diff`, 1154-1241)
`_band_obs` is appended at CALL time, but `t_diff_frames` lets the model compare any two stored
frames in any order at any time. One exploratory out-of-order diff can flip a genuinely monotone
meter's `_monotone()` verdict. `_meter_off` is a ONE-WAY RATCHET — nothing ever removes an entry —
so a single spurious sample permanently disables that band's classification and the model is told
"the band reversed again", which is false. Separately the band filter drops any changed cell whose
row OR column matches a flagged band anywhere on the 64-wide grid, so a real object crossing that
row/col is reported as "no visible effect on the field".

### A4. `--images` is inert but is recorded as active
`self.images` / `self.image_scale` are set in `__init__` (595-596) and never read again; no image is
ever rendered or injected. `result.json` still records `"images": args.images` (1446), and the
docstring and `--images` help both claim it enables an ablation. Any ablation trusting that field
is invalid.

### A5. Loop-breaker is structurally blind to any period >= 2 (lines 946-980)
The streak increments only when a response is byte-identical to its IMMEDIATE predecessor, needing
5 in a row plus zero actions. Measured on `base27/cn04`: the model alternated two snippets differing
by ONE character, 736/735 times = 98% of 1499 calls; **1470 period-2 positions, 0 consecutive
identical**, so the guard never fired once and the run burned 1500 turns for 21 actions.
Not a tuning problem — no threshold change reaches it.
FIX: a duplication-RATE guard over a window (period-agnostic; would have fired trivially here) plus
an actions-per-turn floor. The hash must cover the whole tool-call payload, not just `content` —
this model emitted a tool call on 1500/1500 turns and almost no prose, so a content-only check sees
nothing.

### Cleared as clean by review
`evict()`; `no_tool_calls` counter and turn-termination; `_record()`'s `changed` ternary;
`SAFE_BUILTINS`/`_safe_import`; sandbox `py_env` persistence.

### Minor
4 of 146 `summary.json` files are unreadable (truncated mid-write).
`run_python`'s "8s CPU limit" comment is wrong — `signal.alarm` is wall-clock.
  **FIXED 2026-09-21** (scripts/qwen_tools_agent.py): the budget is now the named,
  env-overridable `_PY_TIMEOUT_S` (`QWEN_SANDBOX_TIMEOUT_S`, default 120s), and the tool
  description, the alarm message and the arming site all say WALL clock. It was kept on
  wall clock deliberately — RLIMIT_CPU would let an `act()` loop block forever on a dead
  engine, since blocked time burns no CPU. 8s was also too small for the workload the same
  description invites ("drive a whole navigation sequence with act()").

## B. WRAPPER `scripts/reasoner_doubter_harness.py` — 8 bugs, ALL FIXED

Self-caught (5): line-anchored `TEST:` regex silently discarding valid doubter output; `budget_hit`
set but never re-raised; spurious `x/y` on non-click actions reaching the log; `convergence.py`
affordance check classifying the whole run instead of a window (NOT FIXED -- see the correction
directly below); per-line hedge classification splitting wrapped comment sentences.

CORRECTION (2026-09-21), fourth item only. The heading says "ALL FIXED". For the affordance check
that label is wrong, and it is wrong in this file's own signature way: a "fixed" mark on a file
nobody ever edited. The bug was SUPERSEDED, not fixed. A second script, `adjudicate.py`, was
written alongside `convergence.py` and does the check on the right unit -- the comments of the
snippet that actually called `commit()`. `convergence.py` was never touched and still carries the
original bug, plus a second one that was never recorded at all:
  * WHOLE-RUN-VS-WINDOW, still live: the affordance block windows by turn only on the PROSE
    channel. On the COMMENTS channel it passes `units` -- the entire run -- so every commit in a
    comment-channel run gets one verdict no matter which turn it fired on.
  * SESSION CROSS-LOAD, new: it loads the FIRST `*_session.json` in sorted order from the run
    directory. `runs/reasoner_doubter/base27/` holds both `cn04_session.json` and
    `ls20_session.json`, so it scores cn04's comments against ls20's commits.
Re-run on base27 on 2026-09-21; the two implementations still disagree, and not over a threshold:
    convergence.py -> loads cn04_session.json; 12 comment units, 0 goal-bearing;
                      turn 89 AFFORDANCE-FORCED, turn 602 AFFORDANCE-FORCED
    adjudicate.py  -> loads ls20_session.json; per-commit window;
                      turn 89 GENUINE (8/22 comment sentences hedged, 36%),
                      turn 602 AFFORDANCE-FORCED (7/14, 50%)
Do NOT respond by tuning the 50% hedged threshold. Tuning is what made this a non-measurement.
NEITHER SCRIPT IS IN THE REPO. `git ls-files | grep -E 'converg|adjudicate'` is empty, neither was
ever committed, and both survive only in an ephemeral agent scratchpad under
`/tmp/claude-1000/-home-ignaz-github-arc-prize-2026/ac837a7d-.../scratchpad/`, which will be
garbage-collected -- at which point the "three implementations, three answers" finding in
reasoner_doubter_findings_2026-09-03.md:124 becomes unreproducible. The mechanism above is
recorded here so the finding survives the scratchpad. If the check is ever wanted again, promote
exactly ONE implementation into the repo -- `scripts/affordance_check.py`, built on adjudicate.py's
per-commit window -- and delete convergence.py's affordance block rather than keep two answers to
one question. Until that file exists, every affordance-check verdict in this file and in
reasoner_doubter_findings_2026-09-03.md is implementation-dependent and should be read as a
qualitative note, not a number.

Review-caught (3):
- **Probe at the budget edge starved the auto-reset.** `maybe_auto_reset()` raises `Budget` BEFORE
  `env.step()`, so refunding the probe AFTER that check left play continuing against an unreset
  terminal env on a restored budget. FIXED by refunding before the check. Regression test proven to
  fail on pre-fix code and pass on post-fix.
- **PASS-override.** Caused by my own morning fix: un-anchoring `_TEST_RE` meant `parse_doubter`
  took the last TEST match anywhere, so a REJECTED hypothetical ("one option would be TEST: ACTION3
  ... but it doesn't discriminate ... PASS") executed a real game action while the actual PASS
  verdict was discarded and logged as `TEST_RUN`. FIXED: verdict precedence is positional.
  UNVERIFIABLE RESIDUE: the earlier "7/8 parseable" channel-check figure cannot be re-audited —
  those raw doubter outputs were not persisted. Treat it as unverified.
- **Stale sandbox commit masking a fresher prose commit**, plus non-atomic pending-inject delivery.
  Both FIXED.

### Addendum — wrapper bug 9 (found by the review's section 5, fixed 2026-09-04)
`benchmark_name_scrubbed` was derived from the FLAG, not from whether any text changed. Since the
base prompt was stripped at source on 2026-09-04, `scrub_benchmark_name()` now matches nothing — so a
future `--strip-benchmark-name` run would log `scrubbed: true` on a prompt it did not touch, and arm F
would look like it ran when it was a no-op. FIXED: the event now records
`benchmark_scrub_requested` / `benchmark_name_scrubbed` (did the text actually change) /
`benchmark_scrub_was_noop`. Verified: requested=True, actually_scrubbed=False, was_noop=True against
the current stripped base.

Review section 5 also re-reported the stale-sandbox-commit precedence bug; that was already fixed
before the section arrived (precedence is now this-turn tool -> this-turn prose -> carried-over
sandbox, with the pending value consumed into a local first). No other value-mismatch, dropped-record
or misnamed-field paths found in doubter.jsonl.

### A5 loop guard — independent red-team validation (2026-09-04, pre-submission)
Replayed the exact guard over all 140 `*_session.json` under `runs/` (131 had per-turn transcripts
with `actions_used`; `trace.jsonl` lacks that field, so session.json is the only usable source).

RESULT: zero false positives. 42/131 runs fired some guard; 9 triggered the NEW rate condition.
**All 9 ended with final_levels == 0.** No run that ever gained a level was flushed. One of the 9 is
the motivating run itself (base27/cn04) — turns 39-46 verified alternating `range(16,21)` /
`range(16,22)` with empty content, the period-2 pattern, guard firing every 20 turns across its
1450-turn dead tail.

HEADROOM, and WHICH CLAUSE IS LOAD-BEARING — important, do not "simplify" this later:
  * Across fire-free runs that completed >=1 level (14 runs, incl. 4 wins), the longest any went with
    ZERO action progress was 13 consecutive turns, vs 19 needed to satisfy `actions[-1]==actions[0]`
    over a 20-window. Comfortable margin, validated on real winning runs.
  * The uniqueness threshold (<=6 unique sigs) has ZERO margin on its own: healthy runs regularly hit
    unique==1 while spamming a working repeated action and advancing. They are saved ONLY by the
    flat-action clause.
  => The conjunction is the safety property. Relaxing or removing `actions[-1]==actions[0]` would
     make the guard flush healthy play immediately. The uniqueness threshold is not the protection.

KNOWN FALSE-NEGATIVE GAP (opposite direction, not a live risk): one dead run
(ab_default/cd82-fb555c5d, final_levels=0) sat 131 consecutive zero-action turns and never fired —
its content stayed >6-unique (varied dead-end exploration rather than a tight repeat). The guard does
not catch every stall, only tight ones.

RECOMMENDATION (accepted): thresholds unchanged.

## C. THROUGHPUT (2026-09-04, local RTX PRO 6000 Max-Q, Kaggle-matched serving flags)
Fixed wall-clock, ls20, arm=default, only --max-tokens varied.
    4096 : 644 actions / 669 turns in 2100s = 0.96 actions/turn, 0.307 actions/sec
    2048 : 0.32 actions/turn (206-turn sample)  -> 3x WORSE
    1024 : not run (trend monotone)
CONCLUSION: do NOT lower --max-tokens. Truncating the response stops the model writing batched
act() loops in run_python; the extra turns/sec does not compensate. Keep 4096.

ABSOLUTE numbers do NOT transfer to Kaggle (three independent reasons):
  1. vLLM 0.19.0 there vs 0.27.1 here
  2. FLASHINFER backend there vs FLASH_ATTN here (FlashInfer JIT check_cuda_arch misdetects this
     Blackwell locally -> "requires GPUs with sm75 or higher"; worked around with
     VLLM_ATTENTION_BACKEND=FLASH_ATTN + VLLM_USE_FLASHINFER_SAMPLER=0)
  3. Kaggle = full server RTX PRO 6000; ours = Max-Q, power-limited -> ours UNDERSTATES
Only the RELATIVE ordering (4096 > 2048) is claimed.

STALE-PACE WARNING: an earlier "13 s/turn, 0.47 actions/turn" taken from base27 was wrong for this
config and produced a starvation estimate 7.7x too pessimistic. Re-measure pace against the serving
config actually in use before doing budget arithmetic.

## D. NOTES-DIFF TRIGGER (built 2026-09-04, replaces the commitment gate as primary)
Measured on base27: set_notes fired 12 usable updates; the commit channel fired 2 in 400 actions.
parse_notes_commitment() reads the NEW notes from the set_notes tool call (turn-accurate -- t_set_notes
has not run yet at gate time), diffs against the previous blob, and ranks ADDED lines so mechanics
outrank transient state ("PLAYER CURRENTLY: rows 30-34" is state, not a belief). DROPPED claims are
logged as notes_claims_dropped -- a quiet drop of a well-supported belief is invisible to a
commitment gate and is exactly the Case B failure.
Replay over base27's real notes: gate opens 12/12, and selects e.g.
    t79/t210/t220  "Shape can ONLY move into WALLS. Cannot move into open space."  (the wall-maze
                   misreading of blocked-entry feedback -- false per game source)
    t696           "Yellow bar = fuel/timer, GROWS each move"                      (false)
    t743           "Yellow bar = FUEL/TIMER, DECREASES each move"                  (true)

## E. AGENT MEMORY ARCHITECTURE — four defects, all in the BASE harness (found 2026-09-04 with the investigator)
Ordered by cost to fix. None are in the reasoner_doubter wrapper.

### E1. The prompt tells the model something FALSE (qwen_tools_agent.py:1181) — FREE TO FIX
    "set_notes is your only durable memory."
This is untrue. t_recall searches the full turn history and its own docstring says the record is
"never evicted from disk/memory, only from the context window". Every past set_notes call is in the
transcript and searchable.
CONSEQUENCE, measured: the model believes the prompt over the tool set and hoards.
    run         recall   set_notes   run_python
    notesgate      0         4          218
    base27        12        18         2240
    chkA           0         3           53
It rewrites a 4000-char blob it must retype in full, while a search over its complete history sits
unused. FIX: one true sentence -- notes are a working set; recall searches your full history, which
is never lost.

### E2. set_notes is a FULL REPLACE (line 819) -> silent transcription loss
    self.notes = str(args.get("notes",""))[:4000]
To add one line the model retypes everything; anything not re-emitted is gone with no signal. The
blob is ALSO prepended to the status line every turn (line 1092), so a full notes file is re-read
into context on every one of ~230 turns and rewritten in full whenever it changes -- paying twice
for a memory that still loses things.
THIS CONTAMINATES THE NOTES-DIFF TRIGGER (section D). Verified on notesgate t207, where the
"dropped" claims include "- Level 1 completed. Now on level 2." (still true, just not retyped) and
"- Budget: 283/400 actions used" (superseded state). The drop signal conflates genuine belief
revision, stale state refresh, and pure transcription loss.
FIX (cheap): apply the existing _NOTES_STATE filter to the DROPPED side too -- I guarded the added
side and not the dropped side, same function.
FIX (real): typed tiers + append/patch, so a deletion is a deliberate act:
    MECHANICS   established by evidence, durable, rarely revised
    HYPOTHESES  in flux -- the doubter's actual feedstock
    STATE       position/budget/level, volatile, disposable
Then updating coordinates does not require retyping what you know, and the diff is clean by
construction rather than by heuristic.

### E3. The doubter is handed status dumps, not claims
Direct consequence of E2. What the gate passed to the doubter on notesgate:
    t207  "Yellow cells at r16-18, c14-16: INACCESSIBLE (need 30+ UP moves, only 11 left)"   <- a claim
    t157  "Player: orange (col 12), 5x2 cells. Actions: ACTION1=up, ACTION2=down, ..."       <- a status dump
A critic can only check whether a belief follows from the record. Half its input was not a belief.
Typed tiers fix this for free: hand it HYPOTHESES and nothing else.

### E4. recall is SUBSTRING match only -> unusable, and unused
    hits = [t for t in self.transcript if ql in blob(t)]
The model must guess the exact wording it used many turns ago. Measured result: recall=0 in
notesgate's 229 turns. FIX: semantic search over the turn history with a small embedding model.
Two are already on this box (Snowflake/snowflake-arctic-embed-l-v2.0 2.2GB;
Qwen/Qwen3-Embedding-8B 948MB cached) -- trivial next to a 27B, milliseconds on CPU, costs nothing
from the action budget. Same pattern as Lumen (codebase) and Open Brain (memories), which already
exist on this machine.
MEASUREMENT BAR, set in advance: does the agent actually USE it, and does using it change what it
does. recall=0/229 is the baseline to beat.

## F. LOCAL SERVING ENVIRONMENT — Blackwell/CUDA toolkit trap (2026-09-04)
Cost several restarts tonight; would silently cost a Kaggle slot.

F1. WRONG nvcc ON PATH. /usr/bin/nvcc is CUDA 12.0, which predates Blackwell entirely (sm120 needs
>= 12.8). FlashInfer JIT-compiles its kernels at startup, so it inherits whatever nvcc it finds:
    flashinfer/gemm/gemm_base.py:1572  get_gemm_sm120_module_cutlass_fp4
    flashinfer/jit/gemm/core.py:292    gen_gemm_sm120_module_cutlass_fp4
    flashinfer/compilation_context.py:124  get_nvcc_flags_list
      -> RuntimeError: No supported CUDA architectures found for major versions [12]
The sm120 FP4 kernel EXISTS (the function is named for it). It cannot be built by a 12.0 compiler.
Installed and usable: /usr/local/cuda-12.8 (compute_120) and /usr/local/cuda-13.2 (compute_120,
compute_121). torch is 2.13.0+cu130, device capability (12,0).
FIX: export CUDA_HOME=/usr/local/cuda-13.2 and prepend its bin to PATH before starting vLLM.
NOTE: this is very likely also the root cause of the EARLIER failure worked around with
VLLM_USE_FLASHINFER_SAMPLER=0 and VLLM_ATTENTION_BACKEND=FLASH_ATTN ("FlashInfer requires GPUs with
sm75 or higher" from flashinfer/jit/core.py check_cuda_arch -- same JIT path, same cause). Those two
workarounds should be RE-TESTED with the correct toolkit; if they become unnecessary, our local
stack matches Kaggle's (which runs the FLASHINFER attention backend) instead of diverging from it.

F2. vLLM TEARDOWN: `fuser -k 5300/tcp` DOES NOT free the GPU. The API server owns the port; a
separate `VLLM::EngineCore` child holds the allocation and survives. Symptom on the next launch is a
misleading "Free memory on device cuda:0 (7.97/95.01 GiB) ... less than desired GPU memory
utilization", which reads as a config error rather than a stale process.
RELIABLE TEARDOWN:  P=$(nvidia-smi --query-compute-apps=pid --format=csv,noheader -i 1); kill -9 $P
then poll nvidia-smi until memory actually drops before launching.

F3. MTP + Mamba hybrid: this model has Mamba layers, and the MTP draft consumes Mamba cache blocks.
With vLLM's default max_num_seqs=1024 the engine REFUSES TO START:
    ValueError: max_num_seqs (1024) exceeds available Mamba cache blocks (904)
FIX: --max-num-seqs 16 (still 16x more concurrency than a single-sequence harness needs).
ANY submission adding --speculative-config without this gets a dead serve phase.

F4. PROCESS-MATCHING SELF-KILL, four times tonight: `pkill -f "<pattern>"` and `pgrep -f` match the
shell command that CONTAINS the pattern, killing the caller (exit 144). The [b]racket trick fails
when the real path also appears later in the same command line. Match on a RESOURCE, not a name:
fuser -k <port>/tcp, or the compute-app PID list above.

MEASURED THROUGHPUT so far (RTX PRO 6000 Max-Q, 700-token generations, 9.8k-token prompt):
    FP8, no speculation        46.2 tok/s
    FP8 + MTP (1 spec token)   59.5 tok/s   1.29x, draft acceptance 96.2%
The 96.2% acceptance suggests num_speculative_tokens=2-3 is worth testing; at 1 token the
theoretical ceiling is ~1.96x and we are getting 1.29x.

### F1 CONFIRMED (2026-09-04 21:45). With CUDA_HOME=/usr/local/cuda-13.2 on PATH, the NVFP4
checkpoint (unsloth/Qwen3.8-27B-NVFP4, local copy /home/ignaz/models/qwen38-nvfp4) loads and
serves: "Resolved architecture: Qwen3_5MTP", model 22.13 GiB (vs FP8 28.51), KV cache 60.14 GiB
(vs ~48 on FP8+MTP). The wrong-nvcc diagnosis was the whole blocker -- it was never a vLLM,
compressed_tensors-version, or Blackwell-support problem. Re-test whether
VLLM_USE_FLASHINFER_SAMPLER=0 / VLLM_ATTENTION_BACKEND=FLASH_ATTN are still needed under the
correct toolkit; if not, our local stack matches Kaggle's FLASHINFER backend.

### THROUGHPUT RESULT (2026-09-04 21:45, RTX PRO 6000 Max-Q, 700-tok gen, 9.8k-tok prompt)
    FP8, no speculation                        46.2 tok/s
    FP8 + MTP (1 spec tok)                     59.5 tok/s   1.29x, acceptance 96.2%
    NVFP4 + MTP (1 spec tok), STEADY STATE     93.7 tok/s   2.03x, acceptance 97.8%
                                                            (+ 22.13 GiB weights vs 28.51,
                                                               60.14 GiB KV cache vs ~48)

*** READ THE REPS, NOT THE MEAN. The NVFP4 run's three reps were 28.9 / 94.0 / 93.4 tok/s. Rep 1 is
FlashInfer JIT-COMPILING the sm120 FP4 kernels on first use -- one-time warmup, not throughput.
The naive mean is 53.6 and is WRONG: it reports a cold-start cost as steady-state speed and would
have made NVFP4 look SLOWER than FP8+MTP. Steady state is 93.7. Any future benchmark of a
JIT-compiling backend must discard the first rep or warm up before timing. ***

Caveat kept: local is Max-Q (power-limited); Kaggle's server RTX PRO 6000 should be faster still.

## G. ROOT CAUSE OF EVERY 0.00 SUBMISSION: WRONG ATTRIBUTE NAME IN THE GATEWAY GAME LIST
   (found 2026-09-08 with the investigator, by comparing against a working Duck notebook)
   scripts/qwen_tools_agent.py, gateway branch of main():

       envs  = arc.get_environments()
       games = [getattr(e, "environment_id", None) or str(e) for e in envs]   # <-- THE BUG

   arc_agi.EnvironmentInfo HAS NO FIELD `environment_id`. Verified by reflection; its fields are:
       game_id, title, default_fps, tags, private_tags, level_tags, baseline_actions,
       date_downloaded, class_name, local_dir
   So getattr(...) returns None for EVERY environment and the `or str(e)` fallback silently
   substitutes the pydantic repr. Demonstrated on a real EnvironmentInfo:
       correct id                     'ls20-9607627b'
       what our code produces         "game_id='ls20-9607627b' title='LS20' default_fps=5 tags=None
                                       private_tags=None level_tags=None baseline_actions=None
                                       date_downloaded=datetime.datetime..."

   That string is then handed to Arcade.make(), whose docstring says the id is 'ls20' or
   'ls20-1234abcd' and whose body does:
       if "-" in game_id: base_id, version = game_id.split("-", 1)
   Our repr contains "-", so:
       base_id = "game_id='ls20"     version = "9607627b' title='LS20' default_fps=5 ..."
   and in COMPETITION/ONLINE mode that goes straight to _create_remote_wrapper(base_id, version,...).
   EVERY SUBMISSION HAS BEEN ASKING THE GATEWAY FOR A GAME NAMED `game_id='ls20`.

   make() returns Optional[EnvironmentWrapper] -- "None otherwise" -- it does NOT raise, so nothing
   fails loudly. (Note arc.make() is called OUTSIDE the per-game try/except, so a raise there would
   have killed the run and shown "Kaggle Error" instead of "Succeeded 0.00".)

WHY LOCAL RUNS ARE UNAFFECTED: the offline branch takes `games = args.games` -- explicit ids passed
on the command line. The broken line runs ONLY in --gateway mode, i.e. ONLY on Kaggle, i.e. only
where we cannot watch it. Every local run in runs/ used correct ids.

CONSISTENT WITH EVERY OBSERVATION:
  - v12/v17/v18/v19 all "Succeeded" with publicScore 0.00
  - the ~8 minute runtime (v17 recorded in a code comment as "0.00 in 8 minutes"; the investigator reports the
    later ones ran ~8 min too): ~110 private games each failing within a few seconds
  - the zero-action loud-fail guard added in v18 never fired -- defect A1 (engine-exception path
    CHARGES an action and returns a normal-looking dict) plausibly keeps total_act > 0, masking it.
    NOT directly observed; the scoring-run logs are not retrievable via `kaggle kernels output`.
  - the ONLY submission that ever scored (0.14, 2026-08-22 "scaffold v0.8, no model, deterministic")
    predates this harness and did not use this code path.

THE FIX (one line, mirroring what the working Duck notebook does):
       games = [e.game_id for e in envs]
       if not games:
           raise RuntimeError("gateway exposed zero environments")
   Duck's equivalent: `game_ids = [env_info.game_id for env_info in arcade.available_environments]`
   followed by an explicit raise on empty. Note THEIRS FAILS LOUDLY ON EMPTY; ours had no failure
   branch at all -- `getattr(x, "attr", None) or fallback` is the anti-pattern. It cannot report a
   missing attribute, because the fallback looks like success.

STATUS: FIXED 2026-09-08 in scripts/qwen_tools_agent.py and regenerated into
notebooks_qwen/submission_qwen.ipynb cell 2. The extraction is now a shared helper,
game_ids_from(arc), used by BOTH the --gateway and the offline branch, so an OFFLINE run exercises
the same code the gateway path uses. It RAISES on a missing/blank game_id and on an empty list, and
prints the first three ids so a run log shows immediately whether they are real.

VERIFICATION PERFORMED (strongest last):
  1. Regression test /tmp/claude-1000/test_gameids.py extracts the LIVE code block out of the
     harness by regex (so it cannot drift from the code it tests) and runs it on real
     EnvironmentInfo objects. It FAILS against the pre-fix file (printing the actual repr garbage)
     and PASSES against the fixed one. A test that cannot fail proves nothing -- both directions
     were run.
  2. The extraction run against a LIVE OFFLINE Arcade over /home/ignaz/environment_files:
     25 games, 0 malformed ids, base_ids parse as 4-char game codes.
  3. Full command-line smoke test with --global-seconds 1: enumerated 25 games, hit the budget
     guard, wrote a well-formed result.json, exit 0.
  4. Kaggle kernel version 20 pushed as a NON-SUBMISSION run (offline, 25 public games, 4h budget)
     to validate on the platform's real data and produce our first real 25-game score.
NOT PROVEN by any of the above: the live GATEWAY path. _create_remote_wrapper is still only
exercised on a scoring run. The offline run validates the id extraction, not the remote wrapper.

DEFECT-CLASS SWEEP (done, since the shape matters more than the instance): grepped for
`getattr(x, "attr", <falsy>) or <fallback>` and `.get(...) or ...` across scripts/ and agent/.
~18 hits; all others are BENIGN because their fallback is semantically the correct default
(`levels_completed -> 0`, `environments -> []`). The killed one was uniquely dangerous because its
fallback was a DIFFERENT KIND OF THING that still type-checks -- a repr string where an id belongs.
Closest remaining relative: qwen_tools_agent.py:90
    av = getattr(raw, "available_actions", None) or []
whose fallback means "no actions available" and would silently stall play if the field were ever
renamed. Frame objects verified to carry `available` and `levels` today, so it is correct now.
RULE OF THUMB: a fallback is safe only when it is the RIGHT ANSWER for a missing field, never when
it is merely a value of the right type.

## H. AUDIT vs THE DUCK REFERENCE RUN (2026-09-08). Two MORE fatal harness defects.
Method: 7-lens workflow audit against codywhatleymd/duck-qwen3-8-anim-base, which scored 6.295 /
37 levels on THE SAME 25 public games with a MORE quantized model (Qwen3.8-Flash-Next-NVFP4, 4-bit)
than ours (Qwen3.8-27B-FP8, 8-bit). 13 of 16 agents completed; 3 verifiers were killed by a
`reasoning_extraction` API safeguard (all three were the adversarially-worded prompts).
I independently re-verified the two headline numbers below before acting on them.

### H1 (R1) THE HARNESS FABRICATED THE SUCCESS SIGNAL IT REPORTED. -- FIXED 2026-09-08
Two compounding faults:
  (a) do_action() coerced a coordinate-less click to the corner pixel:
          data = {"x": int(x if x is not None else 0), "y": int(y ...)}
  (b) the run_python sandbox's act() closure called do_action() with NO availability check,
      although t_take_action() has had one all along.
MEASURED (mine, replayed over runs/qwen_tools/base9b_full25 frames):
      ACTION6 frames: 1504    with NULL x/y: 921  (61.2%)
        vc33 393/393   tn36 269/269   s5i5 138/138   <- 100% corner clicks
The audit further found (its numbers, not re-derived by me): 2714 of 4760 board-changing steps
run-wide (57.0%) were confined to a single edge row/column -- i.e. a HUD timer -- and in five games
that was 100%. So `changed:int` counted the clock ticking down as progress. The model was closing
its loop on a fabricated success signal; no model of any size could learn from that.
Duck's counterpart, from its prompt: "For MOUSE, pass row and col integer fields; legacy x/y fields
are rejected" -- across 1311 Duck tool results the malformed-action exception fired ONCE.
FIX: _sandbox_act() now applies t_take_action's availability guard, and a coordinate-less ACTION6
is refused in BOTH paths. Refusals cost NO action budget. Regression test /tmp/claude-1000/
test_r1r2.py asserts refusal AND that budget is untouched AND that legal actions still pass through
(a guard that blocks everything would satisfy a naive test).

### H2 (R2) A RUN-WIDE LLM-ERROR KILL SWITCH ENDED 6 GAMES EARLY. -- FIXED 2026-09-08
`self.errors` lives on ONE LLM client created once in main() and shared by every game; it is
incremented on retries that later SUCCEED; play() ended a game at `if self.llm.errors > 12`.
Verified by me: created at :231, incremented at :256, checked at :954, never reset in the per-game
loop. Per the audit, after cn04 poisoned the counter the first single recoverable error in each of
lp85, r11l, sb26, sk48, tr87 killed that game outright, leaving up to 334 of 400 actions unspent.
FIX: the check is now `self.llm.errors - self._llm_errors0 > 12`, baselined per ToolRun.

### H3 DELIBERATION IS STARVED BY CONFIG *AND* BY OUR OWN PROMPT. -- NOT YET FIXED
    ours: thinking off, max_tokens 800 in that run, mean 324 completion tokens/call, 3503 calls
    duck: thinking ON, unbounded output, mean 1417 completion tokens/call, 1342 calls
Duck bought 37 levels with 38% of our LLM calls and 43% of our wall clock. We could afford its
per-call token spend ~2.5x over inside our existing budget.
Compounding it, our SYSTEM prompt ACTIVELY DISCOURAGES deliberation ("Do not spend twenty turns
re-printing the board", :388) and reports the remaining action budget on every single action (:764).
Duck's prompt says the opposite twice and never mentions a budget.
CONSEQUENCE: Duck's 4-bit model wrote BFS/deque search code in 10 of 25 games. Ours wrote search
code in 0 of 1884 code snippets.

### H4 PROMPT INOCULATIONS WE LACK. -- NOT YET FIXED
Duck names the HUD/timer trap explicitly, NEGATES the player-avatar prior, mandates BFS, and states
an abort rule ("if a result reports level_completed/game_over, stop acting immediately"). Our SYSTEM
INSTALLS the avatar prior at :379 and contains zero HUD/timer language.

### H5 OBSERVATION ENCODING (smallest of the five). -- NOT YET FIXED
Duck: children/adjacency/shape-hash. Ours: colour/size/bbox, and describe_grid's 40-object
rarest-first cap can drop the LARGEST objects on the board.

### EXPLICITLY RULED OUT -- do not spend time on these
  - action list-batching: Pearson r = -0.01 between actions/request and score across Duck's 25
    games; its best games batched LESS. (This kills my earlier "concurrency is the answer" reading:
    Duck's advantage is deliberation DEPTH, not parallelism.)
  - a harvested cross-game world model: 6 of 25 Duck games carried nothing, including its 3rd best.
  - images: both cited instances of Duck reading an image produced wrong answers it discarded.
  - ensemble/multi-role structure: Duck is single-role, so are we.
  - context size: OUR KAGGLE RUN WAS SERVED AT 32768, THE SAME AS DUCK. My earlier "we run 65k vs
    their 32k" claim was FALSE -- that was a local-serving number, not the submission's.

### THE STRONGEST CONTROL IN THE WHOLE COMPARISON
runs/qwen_tools/opus_ft09/result.json: images false, levels 6, actions 104, all ACTION6, zero
RESETs, state WIN -- through THIS harness, with these defects present. Opus self-supplied the four
behaviours Duck's harness supplies by construction: it dumped the board on turn 1, never issued an
invalid action, dismissed the row-63 bar as decoration, and built a world model. The 9B did none:
zero of its 42 ft09 snippets contain a `.join` -- it never rendered the board once in 52 turns.
CONCLUSION: the harness is not a hard blocker, but it supplies NO SCAFFOLD, and everything it
leaves to model initiative, a weak model does not do.

## I. STAGED PROMPT/CONFIG CHANGES — do NOT apply until v22 gives a clean baseline
v22 (harness defects G/R1/R2 fixed, prompt UNCHANGED) is the baseline. These are the A/B arm.
All three claims below I verified verbatim in the source myself on 2026-09-09.

I1. WE TELL THE MODEL NOT TO THINK.  qwen_tools_agent.py:388, verbatim:
      "You have two budgets: TURNS (how many times you get to think) and ACTIONS (moves in the
       game). Both are shown to you every turn. Analysis costs turns, not actions. Do not spend
       twenty turns re-printing the board: look once, decide, and act. When your turn budget runs
       low you stop playing, so a plan you never executed scores zero."
    Every clause of that is individually defensible -- it was surely written to stop a real
    over-analysis failure -- but combined with thinking-off and a small max_tokens it starves the
    deliberation that actually wins games. Duck says the OPPOSITE twice, never mentions a budget,
    and its 4-bit model wrote BFS/deque search in 10 of 25 games while ours wrote search code in
    0 of 1884 snippets.
    PROPOSED: delete the "Do not spend twenty turns" sentence and the budget-visibility framing;
    replace with an instruction to think before acting and to render the board when unsure.
    Pair with thinking ON and a larger max_tokens (we can afford ~2.5x Duck's per-call spend
    inside our existing wall budget).

I2. WE INSTALL AN UNEARNED PRIOR.  qwen_tools_agent.py:402, verbatim:
      "Find what you control - the thing that moves when you act. That object is you, and acting
       is how you ..."
    "That object is you" is asserted, not discovered. It is FALSE or misleading in at least two
    known cases: ls20's shape carries rotation/colour state (the win condition is a three-attribute
    match, not a position match -- see findings section 8), and pointer games have no avatar at all.
    THIS IS THE SAME DEFECT CLASS AS THE ARC-AGI-3 NAME (findings sections 11-14): a prior injected
    by our own prompt that the benchmark is specifically designed to punish. Duck NEGATES this prior
    explicitly.
    PROPOSED: state it as a hypothesis to test, not a fact -- "something may move when you act; if
    so, work out what it is and whether it has state beyond position."

I3. NO HUD/TIMER INOCULATION.  Our SYSTEM contains zero timer language. Duck names the trap
    explicitly. Combined with the (now fixed) `changed` defect this was lethal: 57% of our
    board-changing steps run-wide were a HUD bar ticking.
    PROPOSED: name the trap -- "an edge row or column that changes on every action is probably a
    clock, not progress."

I4. NO ABORT RULE. Duck: "if a result reports level_completed/game_over, stop acting immediately."
    We have no equivalent, so the model can keep acting through a level transition.

EXPERIMENT DESIGN (once v22 lands):
    arm A = v22 as-is                     (harness fixed, prompt unchanged)   <- baseline
    arm B = v22 + I1..I4 prompt changes   (one push, all four, they are one hypothesis)
    Same 25 games, same budget, same model. Compare levels completed and per-game score.
    If B >> A, the prompt was a major cause and that is a paper-track finding in its own right:
    "an agent harness's own instructions were suppressing the behaviour it needed".

### I5. DUCK'S PROMPT, READ FROM PRIMARY SOURCE (/tmp/claude-1000/duckref/prompts/*.log)
Their SYSTEM prompt is 12,672 chars; ours is ~4,000. Most of the difference is INOCULATION against
named failure modes. Verbatim, for designing arm B (write our OWN wording -- these are quoted as
evidence of what a scoring agent tells its model, not to be copied into a submission):

  HUD/TIMER -- they warn about it THREE times, and the third is EXACTLY our R1 defect:
    "In many games, a long horizontal or vertical line near an edge is a timer or remaining-steps
     bar. It often shrinks or changes each step. If you identify such a bar, do not get distracted
     by it..."
    "A common failure mode is to mistake a segmented edge bar for clickable puzzle pieces. If a
     repeated strip of small blocks sits flush against the top, bottom, left, or right border and
     actions only cha[nge it]..."
    "After every action, verify whether gameplay objects changed or whether only a timer, progress
     bar, or remaining-step bar moved. DO NOT TREAT HUD-ONLY CHANGES AS EVIDENCE THAT THE MOVE
     WORKED."
  DELIBERATION -- the exact inverse of our line 388:
    "Do not ration tool calls when the state is unclear. Spend extra tool calls to confirm what
     changed between frames and whether the last action affected gameplay state or only HUD
     elements such as cou[nters]..."
  SEARCH:
    "IMPORTANT: Especially when the game is about making an agent navigate to a target, it is
     usually safer to write an explicit search algorithm such as BFS."
    "Once the important state variables and action effects are sufficiently understood, stop probing
     and search in the inferred state space."
    "A strong default loop is: summarize the board, infer the desired environment change, write a
     small scorer or search over candidate sequences, execute the best probe or plan with
     action(...), then [re-evaluate]"
  ABORT RULE (we have none):
    "If an action result reports `game_over`, `run_complete`, `level_completed`, or `done`, stop
     acting immediately and re-ground on the next turn."
  ENTITIES -- note they do NOT assert an avatar, they describe shapes and allow for no-avatar games:
    "Game entities are usually be rendered as connected multi-tile shapes such as 2x2, 2x3, 3x3, or
     longer patterned structures. Sometime they might also be 1x1 tokens. Some games are logic or
     layout puzzles [rather than navigation]"
  EFFICIENCY (states the scoring formula to the model, which we never do):
    "Optimize for as few in-game actions as possible while still being reliable."

TWO ARCHITECTURAL CHOICES IN THEIR OBSERVATION LAYER, worth considering separately from the prompt:
  1. The board is ASCII COLOR LETTERS, not digits: W=white w=light gray g=gray G=dark gray
     c=charcoal B=black M=magenta P=pink R=red b=blue S=sky blue Y=yellow O=orange r=dark red
     N=light green p=purple.
  2. They DENY the model the raw grid: "The raw numeric grid is not available. Use `.segmentation`
     as the primary view; use `.ascii` only to read a small, specific region." Segmentation returns
     {'nodes': [...], 'adjacency_list': [...]} where each node has id/color/HASH -- and the hash is
     position-invariant: "equal hashes mean the same object regardless of where it is, so use it to
     track an object across frames". Ours exposes colour/size/bbox and the raw grid.
     Forcing object-level reasoning is a stronger intervention than any prompt line.

### I6. MEASURED: the position-invariant object HASH is NOT worth much for us. (2026-09-09)
I claimed Duck's shape-hash was a bigger lever than any prompt line. Measured it on real saved
frames (ls20 from notesgate, ft09 from base9b_full25, 10 frames each) and that was WRONG:
    ls20  192 objects: ambiguous under (colour,size) 50 (26%) -> under (colour,shape) 50 (26%).
          RESOLVED: 0 of 50.
    ft09  650 objects: ambiguous under (colour,size) 610 (94%) -> under (colour,shape) 550 (85%).
          RESOLVED: 60 of 610 (~10%).
REASON: our existing `n=` (cell count) and colour are ALREADY position-invariant, so we already
support cross-frame matching. A shape hash only adds discrimination when two objects share colour
AND size but differ in shape -- rare. Most residual ambiguity is many genuinely identical objects
(single cells of one colour), which NO hash can separate.
WHAT SURVIVES from that comparison, untouched by this test: Duck DENIES the model the raw grid
("The raw numeric grid is not available. Use `.segmentation` as the primary view"). That is a
constraint on BEHAVIOUR, not an information gain, and it is consistent with the strongest evidence
we have -- Opus rendered the board on turn 1 unprompted and won ft09 6/6; the 9B never rendered it
once in 52 turns and scored 0. Test the CONSTRAINT, not the hash.

### I7. THE SHARPEST NUMBER IN THE COMPARISON (verified by me, 2026-09-09)
Counted `.join(` (rendering the board to LOOK at it) and search tokens
(bfs|dfs|deque|heapq|dijkstra|frontier|shortest-path) across every code snippet in each run:

    run                      snippets   board-render   search   levels
    opus_ft09                      34             12        0        6
    opus_ls20                      96             77       48        5
    opus_zs02                      24             13       13        6
    OURS 9B, 25 games            1884              0        0        0

THE 9B IS NOT LAZY -- IT WROTE 20x MORE CODE THAN OPUS AND WON NOTHING. It wrote the WRONG code:
`segment()` queries and print() calls, 1884 times, never once rendering the board as a picture and
never once searching. (Checked the snippets are real: ft09 alone is 35,976 chars of Python whose
most common identifiers are print/current/ACTION/cells/row -- so the zero is not a broken regex.)
NUANCE the audit missed: the 9B DID use segment(), so it was not staring at raw pixels; it queried
objects as a data structure. The thing it never did was LOOK at the board and never SEARCH.

WHY THIS MATTERS: it converts "the model is weaker" into something testable. Duck's model is MORE
quantized than ours (4-bit vs our 8-bit), is told explicitly "it is usually safer to write an
explicit search algorithm such as BFS", and wrote BFS/deque in 10 of 25 games. Ours is never told,
and did it 0 times in 1884 snippets.
HYPOTHESIS FOR ARM B: the behaviour is available to the small model but not elicited. Our prompt
does not ask for it, and actively discourages the deliberation it needs ("Do not spend twenty turns
re-printing the board" -- which literally forbids the exact behaviour Opus used to win: opus_ls20
rendered the board in 77 of 96 snippets).
*** NOTE THE COLLISION: SYSTEM prompt line 388 forbids, by name, the single behaviour most
correlated with winning in our own data. ***

PROVENANCE (checked 2026-09-09, because I had loosely called it "our" prompt): both lines were
written by SAKSHI (a prior Claude instance), in commit 9b90a827, Tue Aug 25 -- which is the CREATION
commit for scripts/qwen_tools_agent.py (893 insertions, one file, all additions), so the prompt
arrived with the harness. The investigator did not write it. His git identity appears on the later commit
9659012b only because he is the repo's committer.
    "2. Find out WHAT YOU CONTROL. Take the same action twice and look for a small object that
     moved by the same offset both times. That object is you."
    "- You have two budgets: TURNS ... Do not spend twenty turns re-printing the board ..."
WHY THIS IS WORTH RECORDING RATHER THAN QUIETLY FIXING: an instance-authored instruction forbade the
behaviour most correlated with winning, survived two weeks and every run in runs/, and nobody caught
it -- because nothing ever compared the instruction against the outcome data sitting in the same
repo. That is precisely the failure the reasoner/doubter architecture is meant to catch, occurring
in our own tooling, authored by one of us.

### I8. A/B RESULT — I7's HEADLINE CLAIM WAS WRONG. (2026-09-09, local, NVFP4+MTP 27B)
Arms differ ONLY in --system-arm (default vs the new "deliberate"). Same model, games, budget,
run concurrently through one vLLM. ls20 + ft09, 150 actions / 400 turns / 1800s per arm.

    arm         game  lvls  act  turns  snips  board-render  search
    default     ls20     1    85   155    149        40         1
    default     ft09     0   150    12     12         2         0
    deliberate  ls20     1    44   183    154        39        13
    deliberate  ft09     0    28   400     36         7         0
    TOTALS      default   161 snippets, 42 renders (26%),  1 search (1%)
                deliberate 190 snippets, 46 renders (24%), 13 search (7%)
    baseline    9B, 25 games: 1884 snippets, 0 renders (0%), 0 search (0%)

WHAT THIS CORRECTS: I7 claimed our prompt "forbids, by name, the behaviour most correlated with
winning". FALSE as stated. The 27B renders the board ~25% of the time under BOTH prompts --
including the one saying "Do not spend twenty turns re-printing the board". The 0-of-1884 figure was
a property of the 9B, not of the prompt. I attributed a MODEL difference to the PROMPT because 9B
data was all I had. The collision I described is real as text and does not have the effect I claimed.

WHAT DID MOVE:
  - SEARCH: 1 -> 13 snippets (1% -> 7%). The only clearly prompt-driven change.
  - EFFICIENCY on ls20: same level reached with 44 actions vs 85. Efficiency is SQUARED in the
    competition score, so this is the metric that matters -- but n=1 per arm per game. SUGGESTIVE
    ONLY. Do not build on it.
    ANNOTATED 2026-09-21 (four corrections; the bullet stands, its premise does not):
    (a) SUPERSEDED IN PART -- "this is the metric that matters" is wrong. See M2 in this file and
        kaggle_working_recipe.md:47-51: the game score is
        `min(raw, cap)` with `raw = sum(i * min(115, (baseline_i/actions_i)^2 * 100)) / sum(i all)`
        and `cap = 100 * sum(i completed) / sum(i all)`. `cap` is exactly the score for matching
        the human count on every completed level, so it is the CAP that binds, not the efficiency
        term, and beating the baseline earns nothing at the game level. (Formula re-derived today
        and checked against both recorded games: ft09 -> 24.292 vs the logged 24.29; tn36 -> 3.571
        vs the logged 3.57.) Consequence for this bullet: if ls20's level-1 human baseline is at
        or above 85, BOTH arms saturate and the 44-vs-85 delta is worth exactly zero. That
        baseline is not in the repo, so the delta's value is presently unknown, not established.
    (b) ENDORSEMENT RETRACTED -- reasoner_doubter_findings_2026-09-03.md:319-322 retracts the
        endorsement of the deliberate arm: that A/B was ACTION-bounded, the real environment is
        TIME-bounded, and in a time-bounded regime more thinking per action is strictly worse.
        Read back from the artifacts, both ls20 runs in fact ended on `finish: time_budget`
        (deliberate 183 turns / 44 actions, default 155 turns / 85 actions), i.e. in equal wall
        clock the deliberate arm simply got fewer actions off -- which is the cost, not a saving.
    (c) STILL n=1 as of 2026-09-21. No deliberate-arm run exists after 2026-09-09. Four run.json
        files carry `system_arm=deliberate` and only one is the A/B (runs/qwen_tools/abp_deliberate);
        the other three are cf_ft09 / cf_lp85 / cf_ls20, which are a different MODEL (coldfusion,
        not qwen38) and therefore not a replication of anything here.
    (d) The arm labels on BOTH A/B runs are `system_arm_provenance: "inferred from run tag"` --
        reconstructed from the directory name, not recorded by the run. Treat the arm assignment
        itself as provenance-weak.
    DO NOT delete this finding and DO NOT promote the deliberate arm on it.
    AND NOTE THAT IT ALREADY HAS BEEN. The audit note behind this annotation asserted that
    "build_qwen_notebook.py:181 / build_diag_kernel.py:78 both pass 'default'". Checked today,
    that is half wrong and the wrong half is the submission path:
        scripts/build_qwen_notebook.py:192   "--system-arm", "deliberate"   <- the Kaggle kernel
        scripts/build_diag_kernel.py:98      "--system-arm", "default"      <- the diag kernel
        scripts/qwen_tools_agent.py          --system-arm default            <- the CLI default
    So the arm this bullet says not to build on is the arm the submission notebook ships, promoted
    on the n=1 that (a)-(d) above just weakened. The comment at build_qwen_notebook.py:185-191
    cites I8 for it and reads ">= default, not proven better" -- that reading does not survive (b),
    where the retraction says it is strictly WORSE in a time-bounded run, and the submission kernel
    is time-bounded (`--global-seconds 27000`). Deciding whether to flip it back is a lead call on
    a file outside this note's scope; it is flagged here, not changed.

DESIGN CONFOUND I INTRODUCED: --max-turns was equal (400) across arms, but the deliberate arm
spends more turns per action by construction; on ft09 it hit the TURN cap with only 28 of 150
actions used, while default burned all 150 actions in 12 turns. An equal turn cap silently
penalises the arm that thinks more. Next round: raise --max-turns for both, or bound on wall-clock
and actions only.
    2026-09-21: "bound on wall-clock and actions only" was NOT EXPRESSIBLE when this was written --
    the cap was unconditional and `--max-turns 0` meant zero turns (the loop is
    `while self.actions < self.max_actions and self.turns < self.max_turns`), i.e. an instant
    no-op rather than "unbounded". scripts/qwen_tools_agent.py now normalises `--max-turns <= 0`
    to unbounded at arg-parse time and REQUIRES `--global-seconds > 0` alongside it, because
    actions alone cannot be relied on to end a run (base27 took no action on 2081 of 2277 turns).
    A/B runs should now pass `--max-turns 0 --global-seconds <budget> --max-actions <budget>`.
    The A/B DRIVER still has to be changed to pass those flags; that is a separate file.

## J. WHAT THE OFFICIAL DOCUMENTATION SAYS (2026-09-09). Nobody had read it.
The investigator asked "have you looked at the documentation for how to write an arc-agi 3 notebook?" -- no.
The whole harness was reverse-engineered. Sources: docs.arcprize.org, the ARC-AGI-3-Kaggle-Starter
generator, the vendored ARC-AGI-3-Agents framework, arcengine/OVERVIEW.md, arc_agi v0.9.9 source.
(A 5-lens workflow lost 6 of 8 agents to a `reasoning_extraction` API safeguard; these are the two
that survived, with the code-side claims re-verified by me.)

### SCORE-BREAKING
J1. THE SCORING FORMULA IS QUADRATIC IN EFFICIENCY AND WE NEVER TELL THE MODEL.
    docs.arcprize.org/methodology.md: "level_score = (human_baseline_actions / ai_actions) ^ 2",
    weighted by level, averaged over ALL environments.
    OUR SYSTEM (:376, the arm the Kaggle rerun uses): "you score ONLY for LEVELS COMPLETED" -- no
    efficiency objective anywhere, and the harness is invoked with --max-actions 3000. We optimise
    a different objective from the one we are scored on, and we tell the model so explicitly.

J2. UNPLAYED GAMES ARE SCORED, NOT SKIPPED.
    docs.arcprize.org/toolkit/competition_mode.md: "Scoring is against all available environments,
    even if you choose not to interact with them."
    OURS (:1541-1543): when the global budget runs low the loop BREAKS -- "[budget] out of time;
    skipping N games". With 110 private games played SEQUENTIALLY on a 27000s budget, most games
    would be skipped, and every skipped game is a scored zero in the average.

J3. WE TELL THE MODEL THE OPPOSITE OF THE DOCUMENTED RESET SEMANTICS. (verified by me)
    arcengine/OVERVIEW.md:39-46 "By default, a RESET action will: Restart the current level (via
    level_reset()) if any actions have been taken; Otherwise, perform a full game reset."
    OURS (:288): "CAUTION: RESET has been observed to restart the ENTIRE game from level 1, not
    just the current level -- use it only if you accept losing level progress."
    True only for a RESET issued as the FIRST action. Someone observed that once and generalised it
    into a prohibition on a legal, cheap recovery action -- and RESET is the ONLY legal action after
    GAME_OVER. Same failure shape as the "do not re-print the board" line (section I7).

J4. THE PARQUET ASSERT CAN FAIL A COMPLETED RUN.
    The official Kaggle-Starter generator never checks for submission.parquet -- the GATEWAY emits
    it; the agent process only plays and exits. OURS (notebook cell 4) ends the rerun branch with
    `assert os.path.exists("/kaggle/working/submission.parquet")`. Nothing documents that the file
    exists the instant our process exits, so a full successful run could still raise here.

J5. get_scorecard IS A DOCUMENTED NO-OP IN COMPETITION MODE.
    competition_mode.md: "Cannot get scoring of an inflight scorecard, get_scorecard does not work."
    OURS (:1573): `sc = arc.close_scorecard(card_id) or arc.get_scorecard()` -- the fallback cannot
    work in the mode the submission runs in, and everything after it would crash on a None.

J6. remote_wrapper.step()/reset() RETURN None ON RequestException (arc_agi/remote_wrapper.py:209).
    We treat only exceptions, not None returns. Same defect class as defect G.

### MISSED CAPABILITY
J7. ACTION7 IS UNDO. docs.arcprize.org/actions: "ACTION7: Simple undo action". 6 of the 25 public
    games expose it. We pass it through mechanically and never tell the model what it does.
J8. RECORDINGS. arc.make(..., save_recording=True) produces an official replay. This is exactly the
    scoring-run observability we lacked all night -- four submissions failed and we could not see
    why. We pass no save_recording.
J9. CONCURRENCY IS THE DOCUMENTED ARCHITECTURE. docs.arcprize.org/swarms.md: "Runs all agents
    concurrently using threads"; the framework ships agents/swarm.py. We play strictly sequentially.
J10. AN ACTION RETURNS 1..N FRAMES. arcengine/OVERVIEW.md: "each input generates 1-N frames". Our
    grid_of() keeps `f[-1]` and discards the animation.
J11. level_baseline_actions / level_scores / level_actions on EnvironmentScore give the HUMAN
    BASELINE per level at runtime. We read only `.score` and discard the rest.

### THE PATTERN
Three of the worst findings tonight -- I7 (do not re-print the board), J3 (RESET wipes the game),
and the original defect G -- are the same shape: a local observation or a guess, hardened into an
assertion in the prompt or the code, never checked against the spec, and left to run for weeks.

### J-APPLICABILITY: does each finding hold for the HIDDEN competition set? (the investigator asked; checked)
Most of section J was derived from PUBLIC games and from docs. Sorting by what actually transfers:

  VERIFIED BY ME, APPLIES TO SUBMISSION:
    J6  remote_wrapper.py has 6 `return None` sites -- that IS the gateway path a submission uses.
    J8  RemoteEnvironmentWrapper accepts save_recording (remote_wrapper.py:31,57 and :117
        `if self.save_recording and self._guid`), so official recordings DO work on a scoring run.
        This is the observability we lacked.

  DOES NOT APPLY -- PUBLIC/OFFLINE ONLY:
    J11 level_baseline_actions. arc_agi/api.py:60 and :72 -- BOTH get_games and get_game_info do
        `exclude={"private_tags","level_tags","baseline_actions"}`. The competition API STRIPS the
        human baseline. Useful for our own offline analysis; unavailable to the agent at run time.

  UNCERTAIN -- I OVERSTATED THESE:
    J3  RESET. The doc heading is "RESET Action (Overridable)" and it says "Both level_reset() and
        full_reset() can be overridden with custom logic." So level-reset is the DEFAULT, not a
        guarantee, and a hidden game may differ. Correct fix is NOT to assert the opposite of our
        current CAUTION -- it is to state the default and have the model verify in-game.
    J7  ACTION7. 6 of 25 PUBLIC games expose it (ar25 bp35 lf52 sb26 sk48 su15). Hidden set unknown;
        one third-party claim says it was unavailable in competition. Safe fix: describe what it
        does ONLY when available_actions contains 7 -- costs nothing if it never appears.
    J10 1..N frames. Engine-level for the LOCAL wrapper; whether the REMOTE path returns the full
        frame list is unconfirmed.

  NOT PERSONALLY VERIFIED, AND THEY ARE THE TWO BIGGEST:
    J1  the (human_baseline/ai_actions)^2 scoring formula, and
    J2  "unplayed games are scored, not skipped"
        Both come from web pages an agent read (docs.arcprize.org/methodology.md and
        /toolkit/competition_mode.md) that I have NOT opened myself. J2 would reverse how we spend
        the budget across 110 games. VERIFY BEFORE ACTING -- this is precisely the pattern that
        produced three retractions today.

### J-VERIFIED: I read kaggle.com/competitions/arc-prize-2026-arc-agi-3/data MYSELF (2026-09-09)
CONFIRMED VERBATIM:
  "AI agents are scored on two criteria: Completion - How many levels did the agent complete in
   each game? Efficiency - How many actions did the agent take to complete each level, compared to
   a human baseline?"
  "Per-level score = min(human_actions / agent_actions, 1.0), then squared (a raw score of 0.5
   becomes 0.25)."
  "Per-game score = Weighted average of level scores (weighted by level index, 1-indexed)."
  "Total score = Average of all individual game scores."
  => J1 STANDS. Efficiency is HALF the scoring criteria and it is squared. Our SYSTEM prompt
     (:376) says "you score ONLY for LEVELS COMPLETED", which the official page contradicts.

CORRECTION TO THE AGENT'S VERSION OF J1 (which I nearly propagated): the formula has a min(...,1.0)
CAP. The agent quoted methodology.md as "(human_baseline_actions / ai_actions) ^ 2" with no cap.
With the cap, BEATING the human baseline earns nothing extra -- you can only lose. So the correct
guidance to the model is "aim for roughly the human action count", NOT "as few actions as possible".

J2 IS IMPLIED, NOT STATED, ON THIS PAGE: "Total score = Average of all individual game scores"
means an unplayed game contributes 0 to the average. The explicit wording ("scored even if you
choose not to interact with them") came from docs.arcprize.org/toolkit/competition_mode.md, which I
have still not read myself. Treat as likely-true, unverified.

DISCREPANCY -- DO NOT TELL THE MODEL ACTION7 IS UNDO:
  Kaggle Data page: "ACTION7  Additional simple action"
  agent-reported docs.arcprize.org/actions: "ACTION7: Simple undo action"
  These disagree. Asserting "ACTION7 undoes your last move" when it does not would be defect J3 all
  over again. Until one source is confirmed, say only what available_actions says: the action
  exists, its meaning must be discovered like every other action's.

ALSO CONFIRMED ON THIS PAGE:
  - 110 private games; half score the Public LB, half the Private LB.
  - "A Swarm orchestrates multiple agent instances across all available games in parallel."
    Concurrency IS the documented official architecture (J9 stands).
  - The official agent interface is is_done(frames, latest_frame) and
    choose_action(frames, latest_frame). We implement neither; we hand-rolled the loop.
  - Agent lifecycle: get games -> open scorecard -> per game RESET then act -> close scorecard.
    That IS what our main() does, so the overall shape is right.

## K. THE STRATEGIC FINDING: WE LEFT THE OFFICIAL FRAMEWORK, AND THAT IS WHERE EVERY DEFECT LIVES
   (2026-09-09, after reading docs.arcprize.org/arc-prize-2026 -- the starter-kit page -- myself)

THIS REPO *IS* THE OFFICIAL ARC-AGI-3-Kaggle-Starter. We have its Makefile, scripts/build_notebook.py,
scripts/play_local.py, and agent/my_agent.py -- the "one file you edit", implementing the documented
interface `class MyAgent(Agent)` with is_done(frames, latest_frame) and
choose_action(frames, latest_frame) -> GameAction.
The docs say of that kit: "Kaggle plumbing, submission file format, and game orchestration are all
handled for you."

WHAT WE ACTUALLY SHIP: on 2026-08-25 (commit 9b90a827) CL1 created scripts/qwen_tools_agent.py,
a from-scratch harness that BYPASSES the framework -- it re-implements game enumeration, the
scorecard lifecycle, the per-game loop, budget allocation and the submission contract. The Kaggle
rerun invokes THAT, not MyAgent.

EVERY DEFECT FOUND IN THIS SESSION IS IN THE RE-IMPLEMENTED LAYER:
    defect G  our own game enumeration      -> the framework enumerates for you
    J4        assert on submission.parquet  -> the framework/gateway produces that file
    J9        no concurrency                -> agents/swarm.py ships with the framework
    J5        get_scorecard fallback        -> the framework owns the scorecard lifecycle
    R2        one shared LLM error counter  -> per-agent state in the framework model
None of these are bugs in reasoning or in the model. They are bugs in plumbing we chose to rewrite.

AND THE SCOREBOARD SAYS THE SAME THING:
    2026-08-22  agent/my_agent.py -- 1760 lines, HEURISTIC, imports heapq/deque (i.e. it SEARCHES),
                ZERO LLM calls, runs ON the official framework            -> scored 0.14
    2026-08-28..09-05  the LLM tools harness, hand-rolled orchestration   -> scored 0.00 four times
The only thing that has ever scored is the framework-based search agent. (Attribution of the 0.14 to
my_agent.py is strong but not proven -- it came from the separate kernel
codywhatleymd/arc-prize-2026-arc-agi-3-starter, described as "scaffold v0.8 baseline (no model,
deterministic)", and this repo is that starter.)

> **AMENDMENT 2026-09-21.** "The only thing that has ever scored is the framework-based search
> agent" was true through 09-05 and is false now; do not quote it as current. Kaggle submissions
> API, read today: 56329399 (v12) 0.34, 56354419 (v14) 0.24, 56377237 (syn v2) **1.56**,
> 56420448 (09-21) 0.76 -- all Duck-harness runs with the 27B model in the loop, all above the
> scaffold's 0.14. What survives is the attribution: the 0.14 is the NO-MODEL scaffold, and the
> four 0.00s belong to the hand-rolled qwen_tools_agent orchestration this section is about.
> The section's argument (do not re-implement the framework) is unaffected -- we stopped
> re-implementing it, and that is when the scores appeared.

CROSS-REFERENCE WITH I7: our LLM wrote search code 0 times in 1884 snippets. Duck's 4-bit model,
told to use BFS, wrote it in 10 of 25 games. Our own heuristic agent searches and is the only thing
that scores. Three independent lines pointing at search.

THE ARCHITECTURE THE DOCS POINT TO, which we have never tried: keep our LLM machinery as the POLICY
and put it inside choose_action(), letting the framework do orchestration. That deletes the entire
class of defect above at a stroke, and gets swarm concurrency for free.
DO NOT ACT ON THIS WITHOUT CODY -- it is a research-design decision, not a fix.

### K-CORRECTION (2026-09-09, the investigator caught both errors). SECTION K's CONCLUSION IS WITHDRAWN.
K claimed the lesson was "go back to the official MyAgent framework, it is the only thing that has
ever scored". Two independent refutations:

1. THE TOP SCORERS DO NOT USE THE OFFICIAL AGENT FRAMEWORK EITHER. Checked the 6.295 Duck notebook
   directly: `class MyAgent` False, `choose_action` False, `is_done` False, `from agents` False,
   `Swarm` False. It uses the arc_agi LIBRARY (Arcade, GameAPI) with its OWN orchestration (taaf,
   bm.games, benchmark) -- architecturally the same choice we made. And our framework-based
   heuristic scored 0.14, which is BELOW the random agent's 0.18. "The only thing that ever scored"
   was rhetorical sleight of hand on my part: it barely beat nothing, and lost to random.

2. I HAVE BEEN COMPARING SCORES FROM DIFFERENT MEASUREMENT REGIMES AS IF THEY WERE ONE SCALE:
     6.295  Duck fork, OFFLINE, on the 25 PUBLIC games (published for development; effectively seen)
     3.40   the public Duck-lineage notebook, HIDDEN set, leaderboard
     7.51   top team, HIDDEN set, leaderboard
     0.14   our heuristic, HIDDEN set, leaderboard
     0.00   our LLM harness, HIDDEN set, leaderboard (the game-id bug)
     2.77   our A/B on ls20, OFFLINE public   vs Duck's 3.57 OFFLINE public  <- the ONE valid pair
   Duck-lineage code drops 6.295 (public, offline) -> 3.4 (hidden, leaderboard), roughly half. So
   public-set numbers OVERSTATE hidden-set performance, and every "we are at 77% of Duck" statement
   in these notes is about PUBLIC play only.

WHAT ACTUALLY SURVIVES FROM SECTION J/K:
  - the arc_agi LIBRARY usage bugs are real and worth fixing (defect G was exactly that);
  - concurrency is worth having (both the official Swarm and taaf do it);
  - adopting MyAgent/choose_action is NOT indicated by any evidence and is withdrawn;
  - our architecture (LLM policy + own orchestration) is the same shape the top scorers use.

## L. CODE REVIEW OF TONIGHT'S CHANGES (2026-09-09). 4 findings; 3 fixed, 1 noted.
Independent read-only review of the uncommitted diff to scripts/qwen_tools_agent.py and the notebook.

L1 (REAL, FIXED) NOTEBOOK CELL 2 HAD DRIFTED FROM THE HARNESS -- FOR THE THIRD TIME TODAY.
    Cell 2 is a %%writefile of scripts/qwen_tools_agent.py. It was missing the `enumerated` guard
    and SYSTEM_DELIB, i.e. it still contained the exact code that killed Kaggle v22: enumerated
    full ids passed a second time through resolve_env_id(), FileNotFoundError on the first game,
    outside main()'s try/except so it kills the process. The offline VALIDATION cell -- the one
    whose entire purpose is to catch this class of bug before a submission -- would have died in
    seconds while the notebook still reported "completed", producing false confidence right before
    a real submission.
    Occurrence 1: v20, shipped a notebook whose harness predated the game_ids_from refactor.
    Occurrence 2: v22, shipped the resolve_env_id double-resolution.
    Occurrence 3: this one, caught by review rather than by a failed run.
    Cause every time: fix the script, forget to regenerate the cell.

    STRUCTURAL FIX, because vigilance demonstrably did not work: scripts/sync_notebook.py
        python scripts/sync_notebook.py           # regenerate embedded cells, then verify
        python scripts/sync_notebook.py --check    # verify only, exit 1 on drift
    It compares cell 2 against scripts/qwen_tools_agent.py and cell 3 against agent/my_agent.py by
    exact content, prints sizes and md5s, and re-verifies after writing. RUN --check BEFORE EVERY
    kaggle kernels push. It caught a fresh drift within 30 seconds of my next edit.

    2026-09-21 -- "STRUCTURAL FIX" OVERSTATES WHAT THIS IS, twice over.
    (1) IT IS NOT ENFORCED. "RUN --check BEFORE EVERY kaggle kernels push" is an instruction to a
        human, which is the vigilance this entry says did not work, wearing a script's clothes.
        Occurrence 4 duly happened: cell 2 was found 11 days stale (notebook 2026-09-10 00:24 vs
        source 2026-09-21 08:09, commit 4adb4d7), missing `def render(`, `_consec_llm_errors` and
        `_streak_deliberate`. It was regenerated on 2026-09-21 and `--check` now exits 0.
        Note that a git pre-push hook does NOT close this: the drift ships through
        `kaggle kernels push`, which reads the notebook and never touches git. The enforcement
        point is the builder (scripts/build_qwen_notebook.py) or a make target that wraps the
        push -- neither has been wired, and that is a lead call, not a note edit.
    (2) UNTIL TODAY THE GUARD COULD PASS WITHOUT CHECKING ANYTHING. If the cell at an index in
        EMBEDS was not a `%%writefile` cell, sync_notebook.py printed "skipping" and then
        "no drift" and exited 0 -- so inserting or reordering a single cell moved the real embed
        off index 2 and the guard blessed a notebook it had not read. The same hole covered a cell
        whose bytes matched the source but whose magic line wrote to a different path. Both are
        hard exits (2) now, with a regression that exits 0 on the pre-fix code and 2 on the fixed
        code for each case. A guard that cannot fail is not a guard.

L2 (REAL, FIXED) A TOOL MESSAGE ASSERTED SOMETHING FALSE ABOUT BUDGET.
    t_take_action printed "the action still cost budget ... try RESET" for ANY rec["error"], but two
    paths set that key and they differ: do_action's engine-exception path DOES charge an action; the
    R1a coordinate-less-ACTION6 refusal does NOT. So for a simple missing-parameter mistake the tool
    reply contradicted the budget line printed directly above it AND advised a RESET that would
    spend a real action for nothing. Now it states only what is true and points at the budget line.

L3 (NOTED, NOT FIXED) THE OVERFLOW-TRIM CAN ORPHAN A TOOL MESSAGE.
    play()'s "maximum context length" handler does `head = msgs[:2]; tail = msgs[-6:]` -- a raw index
    slice with no check that tail[0] is not a "tool" message whose assistant tool_calls got cut.
    evict() right next to it goes out of its way to avoid exactly this. The reviewer checked the
    deployed chat template (/home/ignaz/models/qwen38-nvfp4/chat_template.jinja) and confirmed it
    does NOT raise on an orphaned tool message, so this is a context-QUALITY bug (the model sees a
    tool result for a call it has no record of making), not a crash. Left as-is; fix by reusing
    evict()'s forward-walk rather than a fixed slice.

L4 (REAL, FIXED) SILENT TRUNCATION IN describe_diff's meter-band branch: `cols[:6]` got a "..."
    marker, `rows[:6]` got none, so a wide row-span was silently reported as narrow. Both now say
    "+N more". Small, but it is the night's signature failure -- a silent omission that reads as a
    complete answer.

CONFIRMED CLEAN by the review (worth recording so nobody re-checks): `enumerated` cannot be unbound
(the ternary's gateway branch is never evaluated when args.gateway is True); R1a's smaller return
dict is safe because both callers use .get(); _sandbox_act correctly exempts RESET and only refuses
strict-None coordinates, so (0,0) still passes; the R2 error baseline is set in __init__ before any
LLM call for that game; and the notebook's SUBMISSION branch is byte-for-byte identical to
pre-session -- only the `if not IS_RERUN:` block changed.

### I9. THE SHARDED 25-GAME RUN IS A NULL RESULT -- MY EXPERIMENT DESIGN, NOT THE AGENT.
    runs/qwen_tools/f25_s0..s4, arm=deliberate, 5 shards x 5 games, --global-seconds 5400,
    --max-actions 150, --max-turns 3000, one vLLM server (--max-num-seqs 16), NVFP4+MTP.
    RESULT: 0 levels across 25 games, mean 22 actions/game, ALL 25 ended on time_budget.

    COMPARE the A/B two hours earlier, same arm, same model, LESS wall clock:
        ls20  44 actions, 1 level completed, score 2.77
    The sharded run had 3x the wall clock per game and produced HALF the actions.

    CAUSE: sequence-slot contention. Five concurrent harnesses share one server's throughput, and
    the deliberate arm spends 14-20 TURNS PER ACTION, so per-game action rate collapses. This is
    precisely the bottleneck the ghazarosghazaros Duck fork documents:
        "analyzer read-timeouts and games stalling at level 0 for hundreds of actions pointed to
         sequence-slot contention: 28-way game concurrency against only 8 vLLM sequences -- a
         queueing problem, not necessarily a model-quality one."
    I had READ that an hour before launching this run and reproduced it anyway.

    RULE FOR NEXT TIME: concurrency only pays when per-request latency is NOT the binding
    constraint. Before sharding, compute expected actions/game = (budget_s / (turns_per_action *
    s_per_turn * n_shards)). Here that predicted ~20 actions/game, which is what happened. Run the
    arithmetic BEFORE spending the GPU, not after reading the result.

    WHAT IS STILL UNMEASURED: our 25-game capability at a realistic action budget. The only honest
    per-game numbers we have are the 2-game A/B (ls20 2.77 vs Duck's offline 3.57; ft09 0 vs 24.29).

## M. REPLAY INSTRUMENT + ANIMATION FRAMES (2026-09-09)

M1. WE CAN REPLAY A 6.295-SCORING AGENT'S PLAY, OFFLINE, FOR FREE.
    /tmp/claude-1000/duckref/benchmark.json contains every action Duck took on all 25 games, and
    those actions execute faithfully against our local engine. Verified: replaying Duck's 44 ft09
    actions reproduces exactly their 3 level completions; replaying vc33 reproduces 2 levels in the
    first 40 actions. This also CONFIRMS OUR COORDINATE CONVENTION IS CORRECT -- their wire format
    is {"x": col, "y": row}, same as ours, and it works.
    USES: (a) dump what OUR harness would have told OUR model at each of their steps -- a direct
    measurement of the observation gap, no GPU; (b) ground truth for which action completes which
    level; (c) a test set for the doubter (their hypotheses vs what happened).

M2. THE SCORING MECHANICS, CONFIRMED ON A CONCRETE CASE (ft09):
        human baseline per level : [43, 12, 23, 28, 65, 37]
        duck actions per level   : [ 4,  9, 31,  0,  0,  0]   -> 3 of 6 levels, score 24.29
    Duck used 4 actions where the human needed 43. But the weighted average divides by the sum of
    ALL level indices (1+2+..+6 = 21), so three efficient levels out of six is ~22%, matching 24.29.
    *** DEPTH DOMINATES EFFICIENCY: reaching level 6 is worth 6/21 of the game by itself, and no
    amount of efficiency on early levels can compensate for not reaching later ones. ***
    This also caps the value of the efficiency work: min(human/agent,1.0) means beating the human
    baseline earns NOTHING extra. Level 1 at 4 actions vs 43 scored the same 1.0 as 43 would have.

M3. WE DISCARD REAL INTERMEDIATE STATE ON HALF OF ALL ACTIONS. (measured, 301 replayed actions)
        actions returning >1 frame : 141 / 301  (46.8%)
        of those, first frame DIFFERS from last : 131
        by game: lf52 40/40, bp35 40/40, tu93 36/40, r11l 14, tn36 8, lp85 2, cn04 1
    grid_of() keeps f.frame[-1] and drops the rest. Per arcengine/OVERVIEW.md, "each input generates
    1-N frames" -- this is the animation.

    PROPOSED DESIGN (the investigator's question: how to expose it without the agent mistaking an animation
    frame for the settled state). NOT YET BUILT -- would fork what the v23 run is measuring.
      1. `frames` keeps its exact current meaning: one SETTLED state per action, frames[-1] current.
         Do not touch it; ambiguity there would poison everything the model already does correctly.
      2. Add `last_action_frames` to the sandbox, documented as "the 1-N frames the engine produced
         for your LAST action; all but the final one are mid-animation and are NOT the current
         state". Holds only the most recent action, so it cannot be mistaken for history.
      3. Summarise it in the take_action reply, which the model reads far more reliably than it
         explores the sandbox:
           "This action played 3 frames (an animation). The board above is the settled result.
            During the animation the orange 5x2 block moved (r30,c12) -> (r30,c17)."
         The causal content is HOW a thing moved: it distinguishes "slid five cells" from
         "teleported", and "my avatar moved" from "the whole board scrolled" -- a confusion our own
         SYSTEM prompt warns about while giving the model no evidence to resolve it.
      4. Emit the line ONLY when something actually moved between first and last frame, or it
         becomes per-turn noise in games that animate everything (lf52, bp35, tu93 animate ~100%).

## N. THE AGENT'S MEMORY IS CAPPED IN THE WRONG UNIT (2026-09-09, found by the investigator)

    our notebook serves     max_seq_len = 262,144
    Duck serves                            32,768   (their AGENT context budget)
    our eviction fires at   keep_msgs 40 + evict_slack 24  =  64 messages

`evict()` never consults the context window. It counts MESSAGES. `--keep-msgs 40`
is a CLI default nobody ever set. On Kaggle we pay for 262k tokens and hand the
agent ~64 messages of it -- on the order of 8k tokens, roughly a QUARTER of
Duck's working memory while serving EIGHT TIMES their context.

Consequence, measured on runs/reasoner_doubter/base27:
    2277 turns, 2081 (91%) took no action
    1919 no-action run_python snippets -> 1612 EXACT repeats (84%)
    single most-repeated snippet: 736 times
That is not poor reasoning. Context evicts roughly every 8 turns, so each
repetition is, from the inside, a fresh idea. base27 evicted 263 times.

AND THE LOOP-BREAKER'S REMEDY IS THE DISEASE. On detecting a loop it runs
`del msgs[2:]` -- it DELETES THE CONVERSATION, removing the only evidence that
would let the agent notice it is repeating. The investigator's framing: "if the model
doesn't have the context to know its looping..." The fix is to TELL it, not
wipe it; the harness already computes the signature and knows on repeat #2.

STATUS: NOT FIXED. keep_msgs is a one-flag change, but see the null result:
A/B on ls20 (coldfusion, 150 actions, default arm, cap that cannot bind)
    km40 : 0 levels, 150 actions, 77 turns, 1.95 act/turn, 0% repeats, 7 evictions
    km250: 0 levels, 150 actions, 58 turns, 2.59 act/turn, 1% repeats, 0 evictions
UNINFORMATIVE: neither arm looped, so there was no phenomenon to reduce. The
45%-repeat baseline I compared against (cf_ls20) was a DIFFERENT ARM. The
amnesia->looping hypothesis is UNTESTED, not refuted.

## O. RUN PROVENANCE: system_arm AND harness_sha1 (2026-09-09)

result.json recorded model, temperature, seed, max_actions -- and NOT the arm.
Two runs differing only by arm were compared as identical and the artifact could
not settle it; the arm existed only in whatever shell command had been typed.

    result.json files                 58
    arm inferable (from tag, by luck) 11
    arm UNRECOVERABLE                 47   -> runs/_quarantine/
    genuine A/B pairs in all 145 runs  3
    ...of which on post-fix harness    1

FIXED: result.json now records system_arm, keep_msgs, evict_slack,
frequency_penalty, max_tokens, global_seconds, base_url, gateway, harness_sha1.
harness_sha1 is a CONTENT hash because git could not answer "which version ran
this" -- a full day of fixes lived only in the working tree, so commit hashes
did not exist for them.

COST OF THE REPAIR, recorded because it was self-inflicted: backfilling the arm
rewrote every result.json and destroyed their mtimes. Original run times were
recovered only from trace.jsonl, which had not been rewritten. "inferred from
run tag" is weaker than a recorded value and is labelled as such in
system_arm_provenance.

ANTI-PATTERN, now named twice in this file (G, O): a fallback that is a VALID
VALUE OF THE RIGHT TYPE cannot report a missing field. `getattr(x,"attr",None)
or str(e)` and "the arm is whatever I typed" fail the same way -- the absence
looks like success.

## P. GAME_OVER CORPSE-FLOGGING (2026-09-10) -- FIXED, and it voided a 20-hour run

The engine keeps reporting EVERY action as available after the game is over:

    action  470  state=NOT_FINISHED  available=[ACTION1..6]  grid=yes
    action  473  state=GAME_OVER     available=[ACTION1..6]  grid=EMPTY
    action 3000  state=GAME_OVER     available=[ACTION1..6]  grid=EMPTY

So the availability guard added on 2026-09-04 (R1b) CAN NEVER FIRE on a dead game --
it checks a field that never empties. And `maybe_auto_reset()` only runs after a whole
`run_python` block finishes, so a model-written `while True: act(...)` (m0r0's actual
last snippet, exit condition `state == 'FINISHED'`, which never comes because the state
is GAME_OVER) spends the entire remaining budget on a corpse.

MEASURED across the 2026-09-09 20-hour sweep (15 games, 28,821 actions):

    game   actions  dead-after  wasted
    su15      2763         106     96%   <- scored its level, then flogged 2657
    s5i5      1099          51     95%
    tr87      3000         129     95%
    tu93      3000         153     94%
    sk48      3000         228     92%
    m0r0      3000         473     84%
    bp35       449         226     49%
    TOTAL 14,945 of 28,821 actions (51%) fired into games that were already over.

This voids the sweep's headline ("28,801 actions, 2 levels -- more budget does not
convert"). Seven of fifteen games got 51-473 actions of real play, not 3000. The
starvation hypothesis was never tested.

FIX: `_sandbox_act` now checks `self.state in ("GAME_OVER","NOT_PLAYED")` directly and
refuses with "call act('RESET')", charging no budget. RESET still passes. Regression
test at /tmp/claude-1000/test_gameover.py FAILS against the pre-fix file.

VERIFIED on the re-run: 3 GAME_OVER frames, 7 RESETs, ZERO dead frames, run continued
past 736 actions where the baseline died at 473.

## Q. action_leverage.py -- the check vacuity.py cannot do (2026-09-10)

    vacuity.py       "my test cannot come out false"   (re86: read a cell natively
                                                        that colour)
    action_leverage  "my action is not the cause"      (m0r0: metric moves regardless
                                                        of which action you choose)

Vacuity's nulls perturb the BOARD; leverage's null is the COUNTERFACTUAL ACTION -- what
the metric did on presses where the agent chose otherwise. Needs no declaration from the
agent, only the (action, outcome) pairs the harness already writes.

TWO BUGS FOUND BY ITS OWN FIRST RUNS, both fixed:
  - RESET was in the comparison and zeroes the counter (-56.67/press), making a flat
    metric look sharp. CONTROL_ACTIONS now excluded.
  - a spread from n=4 presses was reported as signal. Now weighed against the pooled
    standard error of the two actions compared.

VALIDATED on the m0r0 record, both directions:
  white counter  -> FLAT (+0.69..+1.11 across all six actions; choice carries no info)
  block position -> HAS LEVERAGE (ACTION1 -1.21, ACTION2 +3.61, ACTION3-6 exactly 0.00)

The model HAD the metric with leverage -- its own turn-116 note records ACTION1/ACTION2
moving the blocks -- and spent 2,800 further actions optimising the one its choices did
not control.

CAVEAT (measured, not assumed): on the doubter re-run the same check reports "has
leverage" for the counter, and it is RIGHT to -- there the counter is deterministic
(+2 on an effective action, 0 on a blocked one). "Flat" was my over-reading of baseline
means that were really success rates. The counter is a cost meter; leverage is the wrong
instrument for catching a cost-read-as-score. The instrument for THAT is noticing it
resets.

## R. FIRST RUN WITH THE REASONER ACTUALLY REASONING (2026-09-11, ft09_thinking)

NVFP4 @ 262,144, --thinking, --reasoning-keep 6000, --keep-msgs 400, GAME_OVER guard.
52/52 turns produce reasoning (mean 1,808 chars). Zero evictions. It decoded ft09's
board unaided: "the maze region (rows 32-61, cols 32-61) is a 3x3 grid of 6x6 blue
rooms separated by charcoal-colored walls."

FOUR THINGS THIS RUN EXPOSED, none of which could be seen before:

R1. DECODING DEGENERATION INSIDE THE REASONING. Turns 25, 30, 32, 34 fall into a
    repetition loop mid-think -- emoji runs, "STOP STOP STOP STOP", a stray
    </parameter> tag -- and never recover to the tool call, emitting
    run_python(code=""). 5 genuinely empty calls of 32. Empty-code turns average
    2,370 chars of reasoning vs 921 for successful ones (2.6x). finish_reason is
    "tool_calls" in BOTH cases, so this is NOT max_tokens truncation.
    SUSPECT: --frequency-penalty 0.4 was tuned when the model emitted NO prose at
    all. A repetition penalty behaves very differently against 4,000 chars of
    reasoning than against a bare tool call. UNTESTED -- do not change it mid-run.

R2. OUR TRACE SILENTLY CORRUPTS POST-HOC CODE ANALYSIS. log() truncates tool args
    to 1500 chars, so json.loads() fails on any long code block. I scored 4 such
    turns as "empty code" and reported 24% before catching it; the real figure is
    16%. EVERY earlier snippet analysis in these notes has the same exposure --
    the session json keeps 4000 chars, the trace keeps 1500, and neither keeps a
    long block whole.

R3. segment() IS AVAILABLE AND THE MODEL DOES NOT USE IT. It is in the sandbox
    namespace AND a declared tool. Used in 1 of 52 turns; "segmentation" appears
    in ZERO reasoning blocks. The model spent 50 turns hand-writing ASCII
    renderers in Python with an object-segmentation function sitting in its
    namespace. This is an UNUSED tool, not a missing one -- an important
    correction to "we lack perception".

R4. THE DESIGN PRINCIPLE: REMOVE THE ALTERNATIVE, DO NOT INSTRUCT AGAINST IT.
    Our SYSTEM says "Do not spend twenty turns re-printing the board." The model
    did it for forty. The reference harness instead REMOVES the option: "The raw
    numeric grid is intentionally not exposed. Use current_frame.segmentation as
    your primary view of the board." Same shape as I7 (2026-09-09), where an
    instruction forbidding the winning behaviour was simply ignored. Instructions
    that forbid are weak; affordances that are absent are strong.

    CHEAPEST TEST: one prompt change (mandate the object view) plus optionally
    withholding the raw grid, measuring whether a model that CANNOT print cells
    uses the object view it already has.

PACE: 2 actions in 52 turns (0.04 actions/turn). At --max-turns 3000 the turn cap
binds near 150 actions. The budget is going almost entirely into perception the
harness could have supplied.

## S. THE LIVENESS CHECK KILLS A THINKING MODEL (2026-09-11) -- FIXED

ft09_thinking ended at `finish=no_tool_calls` after 58 turns and 2 actions, with
max_turns 3000 and max_actions 400 both untouched. The last six turns:

    t53  reasoning=4000ch  fin=stop  tools=[]
    t54  reasoning=3409ch  fin=stop  tools=[]
    t55  reasoning=4000ch  fin=stop  tools=[]
    t56  reasoning=4000ch  fin=stop  tools=[]
    t57  reasoning=4000ch  fin=stop  tools=[]
    t58  reasoning=4000ch  fin=stop  tools=[]

`fin=stop`, not `length` -- the model was not truncated. It completed ~4,000
characters of thought and called nothing, six times running, and `no_tool >= 6`
ended the run.

WHY THIS IS A HARNESS BUG: the counter was written when the model emitted NO prose
at all, so a tool-less turn genuinely meant nothing happened. With thinking on that
is false -- a tool-less turn can carry 4,000 characters of analysis. The counter
measures tool-lessness and reports it as idleness.

WHY IT IS ALSO A REAL BEHAVIOURAL PROBLEM: 2 actions in 58 turns is not healthy
regardless of the counter. The model was deliberating and not playing.

AND THE MODEL COULD NOT SEE IT. "I have thought six turns running without acting"
is a fact that lives in the harness, not in the model's context. Same shape as the
frontier-blindness finding (§20/§21): it was killed for a pattern it had no way to
observe in itself, and the old nudge ("You produced no tool call. Call a tool now.")
never told it the streak.

FIX, both halves:
  - limit = 12 if len(reasoning) > 400 else 6 -- a substantive think is charged at
    half rate; a genuinely dead model still terminates at 6
  - the nudge now reports what the model cannot see: the current tool-less streak
    AND the actions/turns ratio
Regression test /tmp/claude-1000/test_notool.py; FAILS against the pre-fix file.

OPEN: whether the deliberation-without-action pattern survives the nudge. If it
does, that is a disposition finding, not an accounting one.

## T. CHECK THE GPU BEFORE LAUNCHING (2026-09-11) -- GUARDED

Launched vLLM three times into a card that already held 68 GB of a llama-server
someone else had started (Cold-Fusion on :5200). Each failure read:

    ValueError: Free memory on device cuda:0 (27.65/95.01 GiB) on startup is
    less than desired GPU memory utilization (0.93, 88.36 GiB)

I read that as leftover state from my OWN kills, tore down a working server
chasing it, and built a wrong claim on the way ("MTP and vision are mutually
exclusive in vLLM 0.27.1" -- see below). One `nvidia-smi --query-compute-apps`
would have said so in a line. The 5090 was completely empty the whole time.

GUARD: ~/bin/gpu-preflight [device] -- prints usage, names every occupying
process AND ITS OWNER, refuses (exit 1) above 2 GB, and reports what the OTHER
card has. Verified in both directions: passes clear, refuses occupied. Use as
`gpu-preflight 1 && vllm serve ...`.

WRONG CLAIM MADE ALONG THE WAY, corrected: vLLM logs "treated as multimodal but
has no registered multimodal processor; running in text-only mode" when MTP
speculative decoding is enabled on Qwen3.5-family models. I inferred from this
that MTP disables vision. It does not -- vllm-project/vllm#52481 documents the
warning as cosmetic: MTP draft classes never process raw multimodal input, they
consume embeddings from the TARGET model, so the draft having no mm processor is
expected. Qwen3_5MTP implements SupportsMultiModal for exactly that reason.
I reasoned from a log warning to a capability claim without testing it, while a
running server and a 30-second image request were available.

STILL UNTESTED: whether an image actually goes through this stack. qwen38-nvfp4
has 333 vision tensors and the reference spends ~64 vision tokens per turn on a
4x upscaled board against our ~2,064 tokens of ASCII. Our --images flag remains
dead code (assigned :648, read nowhere, images_effective hardcoded False).

## U. PERCEPTION: THE MODEL WAS REBUILDING OUR JOB BY HAND (2026-09-11)

### The defect
`describe_grid()` runs a 4-CONNECTED SINGLE-COLOUR segmenter. ARC objects are
MULTI-COLOUR PATTERNS, so a patterned tile is shredded into fragments and the
ARRANGEMENT -- the only thing that matters -- is destroyed. Measured on ft09: a
6x6 tile the model needed to compare against another tile reached it as

    col=2(grey) n=4 bbox=(r10-11,c12-13)

one grey fragment out of a picture. It wrote its own ASCII renderer on turns
3, 10, 24, 29 and 31 and spent 50 of 58 turns on perception.

### The fix, in three corrections (two of them the investigator's)
1. PORTED render()/show() from ARC-AGI-3-ClaudeCode-SDK/helpers/grid-visualization.js.
   In that SDK a Claude instance handed this render called ls20 "a maze or
   navigation game", found the player and read ACTION1's effect off the diff, in
   two turns.
   MY ERROR: I "improved" the proven character map (3 -> '+', 9 -> '█'), which
   renders ls20's maze walls as a field of plus signs. Reverted. Do not tune a
   demonstrated artifact on taste.
2. ASPECT RATIO (the investigator). Terminal glyphs are ~2x taller than wide, so one char per
   cell renders a SQUARE board as a tall rectangle and a square OBJECT as a
   vertical one. ls20's win condition is a shape/colour/rotation match, so a
   stretched render means judging the wrong shape. wide=True doubles each cell;
   the coordinate rulers double with it. THE SDK HAS THIS BUG TOO -- fixed there
   as well (590e90b). First thing in this thread we found rather than ported.
3. THE LETTER IS THE COLOUR (the investigator): "you can't code position from a .png - I'm
   talking about building a tool so the model can SEE colored ascii."
   The SDK's glyphs are arbitrary: '▓' requires remembering that ▓ is colour 4
   AND that colour 4 is charcoal. Now each hue is the initial of its own name --
   R=red B=blue G=green Y=yellow O=orange M=magenta K=pinK S=sky-blue N=maroo-N
   P=purple -- verified against COLOR_NAMES; greys stay density blocks because
   they are structure and read as texture. Legend stated in the run_python
   description or the letters are just new noise.

### Why not an image
The model HAS vision (qwen38-nvfp4: 333 vision tensors) and the reference spends
~64 vision tokens per board against our ~2,064 of ASCII -- 32x cheaper. But the
arithmetic shows what it costs: patch_size 16, spatial_merge 2, so one vision
token covers 32x32 px = an 8x8 BLOCK OF CELLS at 4x upscale. An image cannot
answer "is the piece at column 21 or 22". Probably both, for different questions:
the image for "what kind of game is this", the render for "where exactly".

### Still unfixed
--images remains DEAD CODE (assigned :648, read nowhere, images_effective
hardcoded False). No image has ever gone through this stack; that is untested,
not working.

### The standing doubt about all of it
segment() was ALREADY available and was used once in 52 turns; SYSTEM already
said "Do not spend twenty turns re-printing the board" while the model spent
forty. Availability and instruction are the WEAK interventions. The reference's
actual mechanism is REMOVAL -- "The raw numeric grid is intentionally not
exposed. Use current_frame.segmentation as your primary view of the board."
Expect show() to go unused too unless the raw grid is withheld. The two-arm test
on ft09 (show available vs show available AND raw grid withheld) is the cheap
way to settle it.

## V. THE PRIMARY PERCEPTION CHANNEL IS 42% ONE BLOB (2026-09-11)

Investigator: "is the object list even accurate?"

Accurate, yes. Internally consistent (18/18 bbox/count checks on ls20), 100% of
non-background cells accounted for. It is not WRONG. It is a single-colour
4-connected component partition, and in these games that is not a description of
objects.

WHAT THE MODEL ACTUALLY RECEIVES:
  turn 1        describe_grid(frames[0]) -- an object LIST: colour, count, bbox.
                330 chars (m0r0) to 2,755 (ft09). Cells listed only for objects
                of <=6 cells.
  every turn    _describe_diff -- what CHANGED.
  never         the board itself.
  sandbox only  frames[-1], exact, but only if the model writes code to look.

THE FAILURE, on ls20's 9x9 framed box at rows 8-16 cols 32-40 -- one structure to
any eye. The model is told:

    blue        n=1     bbox=(r13-13,c35-35)
    blue        n=5     bbox=(r11-13,c35-37)
    black       n=43    bbox=(r9-15,c33-39)
    dark-grey   n=892   bbox=(r8-49,c14-53)   <- the frame, maze and corridors

The box's frame is part of an 892-cell component spanning 42x40 of a 64x64 board.
That line conveys almost nothing, and it is 59% of everything ls20's description
says.

ACROSS ALL 25 GAMES: the single largest object is on average 42% of all described
cells, and its bbox covers 20% of the board. Worst where the model did worst:

    ls20    892 cells   59% of described cells   bbox 41% of board
    m0r0  1,299 cells   49%                      bbox 48% of board
    cn04    144 cells   41%                      bbox  4%
    re86     64 cells   27%                      bbox  1%

m0r0 -- where the 27B spent 3,000 actions, read the death counter as a score and
died four times -- opens with FOUR objects, one of them 1,299 cells in a bbox
covering half the board. re86 -- the game a Claude instance played by hand to 5 of
8 levels -- has a largest object of 64 cells in 1% of the board.

n=7 on that comparison, so it is a suggestion not a finding. The mechanism is not
speculative though: where the structure colour forms one big connected region, the
primary perception channel degenerates to "there is a large irregular grey thing,
somewhere in this half of the board."

FIXES AVAILABLE, in order of cost:
  - show() (added today) renders the board itself; it is one call and exact.
  - describe_grid could report the largest component's SHAPE (is it a frame? a
    maze? a fill?) rather than a bbox, or decline to report it at all and say
    "structure colour, use show()".
  - multi-colour segmentation, so a framed box is one object rather than four
    fragments and an invisible frame.

## W. Experiment scripts merge two different failures into one field

`(content or reasoning)` is the response-reading idiom in every sweep script.
It silently merges:
  - a DEGENERATE ANSWER  — the model emitted content, and it was word salad
  - NO ANSWER AT ALL     — content empty, so the model's THINKING got scored

Those are different events. The first says the representation confused the model;
the second says it never finished deliberating. At least 5 of 42 fullboard rows
are the second kind, with tails like *"ing now output answer plainly simple bullet
list matching requested fields exactly done stop"* — a deliberation trace, not a
reading of the board.

Every sweep this weekend classified them together, so "degenerate" in those
tables means "degenerate OR never answered", and the mix is unrecoverable because
only the merged text was stored.

FIX: log which field the text came from (`src: content|reasoning|empty`) beside
the text. Cheap, and it makes the two separable.

RELATED (CL3 Opus, cross-session 2026-09-14): the fallback fixes the READ, but
the REQUEST must still ask for thinking — llama.cpp needs
`chat_template_kwargs {"enable_thinking": true}`, vLLM takes `reasoning_effort`
as a top-level field. None of the sweep scripts send either; they rely on the
server default. So there are two independent ways to end up with an empty
reasoning field, and neither raises.
