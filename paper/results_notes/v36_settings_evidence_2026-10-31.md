# v36 settings: which values were ever tested on our stack (2026-10-31)

Read-only audit of code and notes. Nothing was run, nothing on GPUs, Docker or Kaggle was touched, nothing committed.

**What v36 is.** It is the anchor commit run on Kaggle (kernel version 362609521): staged notebook
`notebooks_duck/kaggle_staged/synesthesia/synesthesia.ipynb` (sha256 f9af78d91b997e3c..., the builder default build) running
harness commit 85529646 (`EXPECT_HARNESS_COMMIT`, cell 2 L7). Scores: public-25 47.37; hidden 20.90 / 21.85 / 20.44, plus one
ERROR, 57680782, recorded as "system error" (HO:342, 408, 435, 446, 546).

**Where the values come from.** None of this is set in cell 10. Cell 10 sets only `bm.solver.save_request_logs` (on for commit
runs) and `target.max_runtime_s` (commit runs only).
- Solver values come from `harness/benchmark_initial.pkl`, read here with `pickletools` and never unpickled. The file was last
  changed in d746eb8 (upstream import) and none of our commits touched it.
- `LOCAL_ANALYZER_*`, `MULTIMODAL_*` and every vLLM flag come from the setup script in `harness/setup_commands.json`.
- `ARM_*` values come from the notebook (cell 2).
- No `SYN_*` variable exists anywhere in 8552964. The SYN_* switches first appear in later arm commits (12a000d, c82ffc3, ...).
- `configs/inference.json` is a build-time input and is not read at run time. Two of its values are not what runs:
  `analyzer.timeout` 120 there vs 900 in the pickle, and `max_runtime_minutes` 45 there vs 3,918 s in the pickle.

**Citation keys.**
- NB c*N* L*m*: the anchor notebook, cell index *N* (0-based), line *m* within that cell's source.
- SETUP L*n*: line *n* of the decoded setup script (`json.load(setup_commands.json)[0]` at 8552964, 879 lines).
- PKL: `harness/benchmark_initial.pkl` field.
- TA / SV / PR / TE / SB: at 8552964, `harness/src/ARC3-Inference/inference/` +
  `agent/tool_agent.py` / `framework/solver.py` / `agent/prompts.py` / `agent/token_estimate.py` / `agent/python_tool_sandbox.py`.
- F: `notes/reasoner_doubter_findings_2026-09-03.md`. HO: `~/.claude/projects/-home-ignaz/memory/project_arc_handoff_1006.md`.

**Where-set column.** `git blame` at 8552964, and for the setup script a diff of the decoded script d746eb8 vs 8552964 (the
JSON is one line, so blame on the raw file says nothing).
- "upstream import" = ca031c1 or d746eb8. Both are recorded as unmodified imports.
- "ours 8552964" = "harness: v8's boot-patched bundle as plain code (embedding channel, ARM_* gates, our 0.31 runtime hooks)".
  8552964 changed only setup_commands.json, token_estimate.py, transcript_log.py, vision_context.py and the new
  arc3_tools/patch_kv_copy_chunked.py. tool_agent.py, solver.py, prompts.py, inference.json and both pickles are upstream as
  imported.
- Notebook lines: the first commit that introduced the line in our tree, found with `git log -S`. Every anchor-notebook line
  entered the file through 54873a5 / ab6e03f (10-26).

**Status definitions.**
- **Our stack** = model v22 (v2.2 NVFP4, Kaggle Model v22/3) + our vLLM 0.31 runtime + the TAAF later-branch harness that v36
  runs. In time that means 10-18 onward.
- **yes** = varied on our stack with a recorded score.
- **partly** = varied on our stack but bundled with other changes, measured for throughput only, or run on v22 with the
  pre-0.31 upstream runtime.
- **untested** = never varied on our stack. A test on another model (the upstream quant), another harness (Duck) or another
  team is cited as "other stack" and does not count.
- **n/a** = inert in v36, or fixed by the scored path or the model format.

**Comparators.**
- Kaggle control pool C1-C7: harness 12a000d with all switches off, i.e. the v36 config. Mean 39.06, sd 5.07, range
  32.57-45.95.
- Local controls r2 / r3 / r4 / r6: 8552964 at 9,300 s on the RTX PRO 6000. Scores 40.19 / 44.26 / 41.41 / 42.96, mean 42.21.

| # | setting | v36 value (source) | where set | tested on our stack? | evidence | what the test showed |
|---|---|---|---|---|---|---|
| 1 | Job budget (commit runs only) | ARM_MAX_RUNTIME_S "9300" (NB c2 L127), applied as target.max_runtime_s (NB c10 L20-26); soft end = start + 9,300 - 600 (NB c5 L6, c8 L1-7). A scored rerun has no soft end (NB c8 L2). Pickled default 2,100 s (deploy_target.pkl) | ours: knob 7e2e8da (10-06); value 9,300 from 39e5c30 (10-18, "stage v8 = v7 + our vLLM 0.31.0 runtime (runtime pins); commit budget 9,300 s so both public-25 waves finish") | **yes** (commit runs only; no effect on the hidden score) | HO:293-294 (r1); notes/tower_onoff_local_result_2026-10-27.md:9-11; notes/prestate_no_echo_2026-10-28.md:112 | r1 at 3,900 s: 20.52, only 14 of 25 games started. At 9,300 s: 40.19 / 44.26 / 41.41 / 42.96 (n=1 vs 4). The cause is games that never started, not the model |
| 2 | Per-game clock (commit runs) | max_runtime_s_per_game 3,918.0 (PKL; code default None, SV:1039). Each game's limit is min(clock, soft-end remaining - 60 s) (SV:329-345, :93) | upstream import (PKL d746eb8) | **partly** | notes/prestate_restoration_2026-10-30.md:52-77, 97-110 (R0, tag r0_untimed, notebook synesthesia_r0, 331b784); HO:540-541; pool-clock runs: notes/prestate_pool_clock_2026-10-31.md, HO:547 | R0 changed five things at once (no per-game clock, no job clock, concurrency 1, action cap 5,184, audit every 77 actions). On its 13 finished games: levels 6.15 vs 4.23, score 66.23 vs 42.31 against local timed r2/r3/r4/r6. n=1, NOT resolved, and not submittable as run (2.37 s/action, 25 games about 27-63 h). POOL / PARK on Kaggle: no result yet. As built, their action-based stall cuts are mis-scaled (amendment 2) |
| 3 | Scored-rerun clock fit | per-game = max(600, (start + ARC3_NOTEBOOK_LIMIT_S 32,400 - ARC3_END_MARGIN_S 600 - now) / ceil(n_games/14)), applied when that is below the pickled 3,918 (NB c11 L45-58). With 110 hidden games (8 waves) it applies whenever more than 456 s have elapsed, which is every real load | ours: f58d514 (10-18, "generator: --parallel-prefetch ... and --fit-clock (true rerun: per-game clock = time left after load / waves)") | **untested** | F:7266-7285 (216d: unit tests only; a 47-min load gives 3,623 s, a 15-min load 3,863 s); the hidden scores in the header all ran with it | No hidden run with another limit or margin. Scored-run logs are invisible, so the clock the hidden games actually got was never observed |
| 4 | Solver concurrency | 14 (PKL; code default 16, SV:1040); pool and semaphore at SV:1289, 1348 | upstream import (PKL d746eb8) | **yes** (one arm, n=1) | HO:548 (one line, no note); notebooks_duck/kaggle_staged/synesthesia_c10 (d87d646; harness 8552964; cell 10 adds only `bm.solver.concurrency = 10`). R0 used concurrency 1 inside its bundle (row 2) | c10: 39.08 vs pool 39.06 (sd 5.07); 714.6 vs 773.7 tok/s. Not resolved. By the clock arithmetic (not checked in its log), 25 games on 10 slots need 3 waves of 3,918 s in a play window of about 7.5-8.1 ks, so this arm also loses game starts |
| 5 | vLLM --max-num-seqs | 14 (SETUP L127, L578-579); cudagraph capture size ceil(14 x 4 / 8) x 8 = 56 (L551-555) | upstream import (d746eb8) | **partly** (throughput only) | notes/concurrency_sweep_2026-10-31.md:1-16 (c25: harness 6091476, ARM_MAX_NUM_SEQS=25 + solver 25, on the POOL-CLOCK build: synesthesia_c25 cell 11 sets `bm.solver.pool_clock = True`). c20 staged, not run | +25% generation tok/s until KV reaches 98.6% at about 10 min, then the 196a collapse: prefix hit 87% -> 43%, generation 250-400 tok/s, 11 requests waiting. No score |
| 6 | analyzer_timeout (per request) | 900.0 s (PKL; code default 120.0, SV:1037). Effective timeout = min(900, per-game time left, soft-end time left) (SV:358-379, :1641) | upstream import (PKL) | **untested** | none varies it. HO:547: v36's 32-40 "timeouts" per run are the per-game clock expiring (start + 3,918 s), not this cap. notes/taaf_audit_2026-10-14.md:163, 224 | - |
| 7 | max_actions_per_game | None (PKL; SV:1038) | upstream import | **partly** | prestate_restoration:64-67, 103 (R0 safety cap 5,184 = 4 x the 1,296 maximum seen in 225 timed game-runs) | Only inside R0's untimed bundle: 5 of 13 games hit 5,184 and still cleared more levels than the timed runs. In timed play the clock binds first |
| 8 | Strategy-audit cadence | STRATEGY_AUDIT_PROMPT (PR:11) is added once 25% of the game's initial effective limit has passed since the last level clear or the last delivered audit (SV:238-241, 244-250, 310, 477); about 980 s at 3,918 s | upstream import (d746eb8) | **partly** | synesthesia_r0 cell 10 (action trigger every 77 actions); prestate_restoration:68-70 | Changed only inside R0's bundle; no separate read |
| 9 | ONLY_RESET_LEVELS | "true", set before any game (NB c9 L3) | upstream notebook template (taaf_kaggle_run.ipynb at d746eb8), carried as is | **untested** | notes/findings_audit_2026-10-31.md:72, 115-117 (OPEN 181 / C4: "leaks process-wide (disables score reconciliation)"; current TAAF sets it after `arcade.make`; effect on our runs never checked) | - |
| 10 | n_passes | 1 (PKL; forced to 1 on a scored rerun, NB c11 L43) | upstream (PKL + template) | n/a (fixed by the scored path) | - | - |
| 11 | Commit-run soft-end buffers | SOFT_DEADLINE_BUFFER_S 600 (NB c5 L6); SOFT_DEADLINE_GAME_MARGIN_SECONDS 60 (SV:93) | upstream (deploy_kaggle.py generator; SV d746eb8) | **untested** (commit runs only; a scored rerun has no soft end) | - | - |
| 12 | Request context window | LOCAL_ANALYZER_CONTEXT_WINDOW 127,488 (SETUP L32, L856; code default 73,728, TA:87). Budget = 127,488 - 512 reply reserve - 512 margin = 126,464 (TA:440, 448-452) | upstream import (d746eb8) | **untested** on our stack | Other stacks only: Duck harness 32k vs 64k (A10a / A10b, levels 18 vs 17, n=1, 16 games x 42 min; runs/serving_sprint_1003/measure/RESULTS9.md "levels, FULL" row). Duck 128k with 150 turns vs 32k with 30: 6.31 vs 7.60, and no more levels per action (F:4415, 4441). R5 (target 126,463) pre-stated, not run (prestate_restoration:61-63). An ARM_ANALYZER_CONTEXT_WINDOW switch exists on branch kv-tier (281d0d0, default = v36), never run (kvtier_handoff:54-55) | - |
| 13 | vLLM --max-model-len | 147,072 (SETUP L31, L576-577) | upstream import | **untested** | every run on our stack used 147,072; the model's ceiling is 262,144 (F:4596) | - |
| 14 | Trim-back target | LOCAL_ANALYZER_TARGET_CONTEXT 81,536 (SETUP L857). Past the 126,464 ceiling the oldest turns are dropped until the request is at 81,536 (TA:453-458; F:6535-6545, 196h) | upstream import | **untested** on our stack | Other stack (upstream quant + upstream runtime, GCP twin): target 122,880 scored 28.61 at 14 streams and 39.55 at 10 streams / 15,000 s, vs controls 42.40 +- 5.04 (notes/results_table_2026-10-07.md:23; F:6129-6175, 6351-6358). R5 not run. An ARM_TARGET_CONTEXT switch exists on kv-tier (281d0d0), never run (kvtier_handoff:54-55, 62-63) | - |
| 15 | _PERSISTENT_HISTORY_ASSISTANT_TURNS | 30 (TA:118). INERT: bypassed whenever the target is below the budget (TA:1281-1283) | upstream import | n/a (inert in v36) | code read; prestate_restoration:58-59 says the same | - |
| 16 | Board history in context | Every board part stays in history until compaction drops its turn: median 13, max 48 boards per request (notes/prestate_history_window_2026-10-27.md:3-4). No knob in 8552964; SYN_HISTORY_BOARDS_KEEP exists only on syn/hist-window ca83448 | upstream behaviour; the board part is ours (8552964) | **untested** | prestate_history_window (step 0 and K=1 / K=4 arms pre-stated, no result on record); notes/payload_cost_2026-10-26.md:65-73 | - |
| 17 | Reasoning echo | preserve_thinking true, through --default-chat-template-kwargs (SETUP L602-603): prior turns' reasoning is re-rendered into the prompt | upstream import (d746eb8; already in ca031c1, prestate_no_echo:47-50) | **yes, RESOLVED** | notes/prestate_no_echo_2026-10-28.md:84-88 (Kaggle no-echo-k1, run 363302371, harness c82ffc3); :110-116 (local ne1-ne3 vs r2/r3/r4/r6) | Local: 12.61 vs 42.21, delta -29.60 [-38.43, -21.38], 0 of 25 games up; levels -2.04 [-2.46, -1.60]. LOSS, resolved at 3 vs 4. Kaggle: 16.46 vs pool 39.06 (n=1). Keep the echo |
| 18 | Budget margins | Reply reserve 512 (because MAX_OUTPUT is 0, TA:440); _REQUEST_SAFETY_MARGIN_TOKENS 512 and _CONTEXT_OVERFLOW_RETRY_TRIM_TOKENS 512 (TA:115-116) | upstream import | **untested** | - | - |
| 19 | Token-estimator ratios | 2.9 / 1.8 / 2.5 / 4.3 chars per token (TE:33-36); board parts priced at their 1,024 rows (TE `_embeds_part_tokens`) | ratios upstream (d746eb8); embeds pricing ours (8552964) | **untested** (measured, never varied) | HO:453 (CL3's consumption gate: estimate/actual prompt tokens 1.02 at 1 board, 1.10-1.16 at 3-31 boards) | The estimate runs 2-16% high, so compaction fires that much early. No arm changed the ratios |
| 20 | Yield budget | LOCAL_ANALYZER_YIELD_SECONDS 150 (SETUP L862), times min(1 + consecutive yields, 3) (TA:437, 1474-1479; code default 0 = off) | upstream import | **untested** on our stack | Duck harness only: yield 0 + 12 tool steps (TURN_SHAPE=ref) scored 4.08 vs 7.60 (F:4449-4451, F155); the A10 arms used yield 60 | - |
| 21 | Tool steps per turn | LOCAL_ANALYZER_TOOL_STEPS 0 = unlimited requests per turn (SETUP L859; TA:435; code default 12) | upstream import | **untested** on our stack | Duck only (F155, bundled with yield 0) | - |
| 22 | Reply length cap | LOCAL_ANALYZER_MAX_OUTPUT 0: no max_tokens and no thinking cap (SETUP L858; TA:438-440) | upstream import | **untested** on our stack | Duck only: A8, a thinking_token_budget of 1,024: 1,738 vs 1,018 actions and 16 vs 14 levels in a 42-min local window, n=1 (notes/stack_comparison_2026-10-06.md:23; F:4592). The 10-30 "thinking cap" cut was never in v36 (prestate_restoration:55-56) | - |
| 23 | Python tool time limit | 30 s. LOCAL_ANALYZER_TOOL_TIMEOUT 30 (SETUP L860) goes into min(30, max(1, x)), a hard CEILING (TA:436); the prompt says "hard 30-second time limit" (PR:138); CPU rlimit = timeout + 1 s (SB:479-482) | upstream import | **untested** | - | - |
| 24 | Tool output cap | 1,024 tokens = 4,096 chars, head cut (SETUP L861; TA:441-442). The prompt warns that one printed 64 x 64 board (~4,100 chars) fills the cap by itself (PR:138) | upstream import | **untested** on our stack | Other stack (upstream quant, twin): 3,072 tokens with a middle cut scored 45.89 / 37.78 vs controls 42.40, a null (F:6285-6289; results_table:24) | - |
| 25 | Yield multiplier / plan cap | _MAX_YIELD_BUDGET_MULTIPLIER 3; _MAX_PLAN_CHARS 500 (TA:117, 119) | upstream import | **untested** | - | - |
| 26 | Sandbox limits | RLIMIT_AS 768 MiB, CPU timeout + 1 s, FSIZE 1 MB, NOFILE 32 (SB:479-484); SAFE_MODULES (SB:47); the prompt lists 14 importable modules (PR:136) | upstream import | **untested** | - | - |
| 27 | Prompt text | Upstream system prompt and addenda (PR), MULTIMODAL_CONTEXT_ADDENDUM on, stock level messages | upstream import (PR unchanged by 8552964) | **yes** (several arms, none resolved) | Batch A, 11 harness/prompt switches at once (harness 12a000d): notes/batch_a_local_result_2026-10-27.md:16-17, notes/batch_a_kaggle_result_2026-10-27.md:13-17. Rooms: notes/game_room_s_local_result_2026-10-28.md:23-25; hidden scores at HO:518, 522 | Batch A: local +3.45 [-4.35, +10.92], Kaggle +0.98 [-5.80, +8.62], both 3 vs 3, not resolved. Room S: local +1.26 [-3.23, +6.01], not resolved; hidden Room S 21.75 and Room C 15.28 (n=1) vs v36's 20.90 / 21.85 |
| 28 | Temperature | 0.6 (SETUP L863; code default 1.0, TA:96; sent on every request, TA:759) | upstream import | **untested** on our stack (F:4596: "temperature has never been changed") | Other stack only, Duck harness at 32k: 0.3 (A10c) and 1.0 (A10d, A10d_r) vs 0.6 (A10a), 16 games x 42 min, n=1 each (RESULTS9.md "levels, FULL" row; F:4600) | Other stack only: levels 13 at 0.3 and 10 / 12 at 1.0, vs 18 at 0.6 (descriptive) |
| 29 | top_p / top_k | 0.95 / 20 (SETUP L864-865) | upstream import | **untested** (every arm on every stack used 0.95 / 20) | - | - |
| 30 | Other sampling | min_p 0, presence_penalty 0, repetition_penalty 1.0 (TA:762-764); seed -1 (TA:99); --generation-config vllm (SETUP L592-593) | upstream import | **untested** | - | - |
| 31 | Thinking | enable_thinking true (SETUP L866; TA:94, 786) | upstream import | **untested** on our stack (no thinking-off arm found on v22 / 0.31) | Nearest evidence is row 32 | - |
| 32 | Reasoning effort | xhigh on every request (SETUP L867; TA:95, 790) and as the server default (SETUP L602-603) | upstream import | **partly** (v2.2 = v22, but on the upstream e975732 runtime before our 0.31; same harness lineage) | F:7026-7038 (215o), 7076-7085 (215r); notebooks kaggle_armB_q25_v22_effort_low / _medium (runtime vllm-main-e975732-arc3) | xhigh 43.86 / 35.21 (n=2), medium 21.70, low 8.41 (n=1 each). Lower effort buys more actions and far fewer levels per action. Clear direction, never re-run on 0.31 |
| 33 | Board channel on | MULTIMODAL_CONTEXT current_grid (SETUP L868) with the board-tower student (ARM_B_STUDENT_TOWER 1, NB c2 L117; vision_context.py:190) | current_grid upstream (d746eb8); student branch ours (8552964; ARM_* first in 7e2e8da, 10-06) | **yes**, not resolved | notes/tower_onoff_local_result_2026-10-27.md:3, 9-15, 20-22 (OFF runs bo1b-bo3b, harness 8552964 + faab14c, vs r2-r4) | OFF - ON = -3.62 [-9.89, +3.22], sign 7 / 17 / 1, p 0.064; levels -0.24 [-0.64, +0.19]. Not resolved at 3 vs 3, leaning toward the channel helping. Readback (HO:537): cell accuracy 0.559 for the student vs 0.810 for text read by eye |
| 34 | Student vs native tower | 18.2M px16 dihedral student (checkpoint sha 5e4eb805..., NB c2 L8, L39); native tower never loaded (ARM_LIMIT_MM image:0, ARM_ENABLE_MM_EMBEDS 1: NB c2 L115-116, checked at NB c10 L92-98; SETUP L600-601, L631-632) | ours (7e2e8da; harness side 8552964) | **yes**, not resolved | notes/tower_native_local_result_2026-10-28.md:22-24 (na1c-na3c vs r2-r4) | Native - student = +2.07 [-4.65, +9.15], sign 11 / 13 / 1; levels +0.09. Native KV pool 1,440,080 vs 1,502,892. Not resolved |
| 35 | Tokens per board | 1,024 image_embeds rows (ARM_B_EXPECT_NPOS 1024, ARM_UPSCALE 16, ARM_MAX_PIXELS 1,048,576: NB c2 L113-118; asserted at NB c10 L50, L63; SETUP L87). ARM_UPSCALE is unused on the student path (NB c10 L79-80) | ours (7e2e8da); SETUP reads ARM_MAX_PIXELS since 8552964 | **partly** | notes/prestate_tower_px8_2026-10-30.md:79-83 (px8 = 256 tokens, fidelity read only); HO:534 (px8 play cancelled 10-30 14:45); HO:537 (readback) | Never played at another geometry. px8 fidelity: cos_mean 0.787 vs 0.897 at px16; readback cell accuracy 0.519 vs 0.559. Other model (upstream quant): native tower at 64 tokens 41.50 vs at 1,024 tokens 33.82, mean of 2 (results_table:16-17) |
| 36 | Board-tower host settings | BOARD_TOWER_DEVICE cpu, BOARD_TOWER_THREADS 2, BOARD_TOWER_ANY_GPU 1 (NB c2 L121-123; NB c10 L34-38) | ours (7e2e8da) | **untested** in play | notes/ref_pass_fix_2026-10-08.md:63-67 (2 threads reproduce the recorded parts byte for byte; 1 / 2 / 8 threads differ by one bf16 ulp in 0.049% of values) | - |
| 37 | Model checkpoint | arc3-flashnext-nvfp4-ours-v22, version v22/3 (NB c2 L9; SETUP L25); compressed-tensors, bf16, TP 1 (SETUP L56, L79, L33) | ours: SETUP L25 changed by 8552964 (the quant itself is F214) | **yes** (n=1, not resolved) | notes/xz_w4a16_kaggle_result_2026-10-30.md:23-27 (xz W4A16 v2, harness 2e1af90 adds the INC / PLE patch). Older runtime: v2.1 vs v2.2, 33.32 / 33.51 vs 43.86 / 35.21 (F:6709-6716) | xz 45.49 vs pool 39.06: +6.43 [-2.38, +15.72], p 0.108; levels +0.37 [-0.19, +0.93]; about 5% slower in tok/s. Not resolved |
| 38 | GPU memory utilization | 0.98 (SETUP L34, L621-622); local KV pool 1,502,892 tokens | upstream import | **untested** on our stack | memory note feedback-gpu-mem-util-no-conservative-cap.md (0.98 is the value that works on the upstream stack; our Duck-era 0.92 left about 7.7 GB, which the note puts at 5-6% of the pool). F:4446 (Duck era: vLLM's log at 0.92 said 18.97 GiB of KV was possible vs 12.5 GiB used). Never varied around 0.98 on our stack | - |
| 39 | KV cache dtype | fp8_e4m3 KV and fp8 indexer KV (SETUP L80-81, L625-628) | upstream import | **untested** on our stack | Earlier stack only (Duck harness, our earlier runtime): F:4537-4545 (163, fp8 KV failed parity), F:4565 (166), stack_comparison:32 (withdrawn) | - |
| 40 | Speculative decoding | MTP with 3 draft tokens and use_local_argmax_reduction over the 32k draft vocab (SETUP L36, L69, L616-620, L313-315) | upstream import (L69 env-readable since 8552964, same default) | **partly** (alternative drafter, throughput only) | notes/dflash2_flashnext_2026-10-31.md:40-41, 50-57, 72-74, 80-91 (DFlash2 l4-l9 local; l7 Kaggle complete, logs unread) | DFlash2 l4 was 2.3x slower (391 / 358 vs about 945 / 880 tok/s), acceptance 2.37-2.47 vs 2.73-2.83 for MTP. l9, on MTP's exact settings, matched MTP's acceptance but its prefix hits collapsed. K>3 trips the QSA ring assertion; K<3 was never run. No score |
| 41 | max_num_batched_tokens | 2048 (SETUP L78, L580-581) with chunked prefill (L583) | upstream import | **untested** | - | - |
| 42 | Prefix caching | on; --prefix-match-unit 128; --prefix-cache-retention-interval 0 (SETUP L83-85, L586, L609-615) | upstream import (L84 env-readable since 8552964, same default) | **partly** | notes/kv_tier_2026-10-31.md:24-43 (kt1: retention 8,320 + RecoverSSM off + a 32 GiB host tier, bundled). DFlash l4 / l6 used unit 64, bundled with the drafter | kt1 lost throughput: GPU prefix hits 91% -> 44% by 25 min; generation 888 -> 294 tok/s at 25-30 min. No score and no single-variable change |
| 43 | GDN RecoverSSM | VLLM_ARC3_GDN_RECOVERSSM=1 (SETUP L306; see L260) | upstream import | **partly** (one variable, throughput only) | notes/kvtier_handoff_2026-10-31.md:20-28 (kt0 = RecoverSSM off alone, local 6000, 14 streams, 20:00-20:33; committed f217dd1 at 20:37, during this audit); kt1 (bundled) at kv_tier:26-43 | kt0: pool 1,378,274 (-8%); KV 85.5% at 5-10 min vs 65-72%; generation 372 / 335 tok/s at 15-25 min (24 of 30 samples waiting) vs about 840-920 for MTP. RecoverSSM off is the expensive part (handoff:40-41). No score |
| 44 | Mamba SSM cache dtype | bfloat16 (SETUP L82, L629-630) | upstream import | **untested** | F:4620 (167: the GDN state runs in bf16 rather than the config's float32; "measurement pending") | - |
| 45 | Other serving internals | --async-scheduling, --enable-chunked-prefill, cudagraph capture 56 (step 8), GDN decode kernel triton, default MoE backend, --engram-config {cpu_offload: true} + --cpu-offload-params embed_tokens (PLE table on the host), PYTORCH_CUDA_ALLOC_CONF expandable_segments:False (SETUP L37, L57-58, L299, L582-597) | upstream import | **untested** | - | - |
| 46 | Model-format flags | tool-call parser qwen3_coder, reasoning parser qwen3, chat template from the model dir (SETUP L588-591, L633-635) | upstream import | n/a (set by the model's format) | - | - |

Counts: **yes 7** (rows 1, 4, 17, 27, 33, 34, 37), of which one is resolved (17, the reasoning echo); **partly 9** (2, 5, 7, 8, 32,
35, 40, 42, 43); **untested 27**; **n/a 3** (10, 15, 46). Left out as plumbing: ports, paths, served model name, ARM_LABEL,
save_request_logs (commit runs only), TAAF_MINIMAL_DIAGNOSTICS, cancel_drain_timeout_s 120 (PKL), periodic_save_interval_s 600
(PKL), ANALYZER_RETRY_BACKOFF_SECONDS 1.0 (SV:91).

## UNTESTED, ranked by plausible score impact

Rank is the plausible size of the score's dependence on the setting. Where evidence points one way, the direction is noted.

1. **Trim-back target 81,536 (row 14).** History is the model's working memory. The one resolved result on our stack (row 17,
   -29.6 without the echo) shows prior-turn content matters. Each compaction drains about 45k tokens (126,464 - 81,536), and 74 of
   75 game-runs compact. The only evidence is the upstream quant at a higher target (worse or null).
2. **Scored-rerun clock fit, 32,400 / 600 / ceil(n/14) waves (row 3).** It sets every hidden game's clock and decides whether
   the last wave fits under the 9 h cap. It cannot be seen on public runs, and no hidden A/B exists.
3. **Context window 127,488 (row 12).** This is the ceiling where compaction fires, coupled to row 1. 14 streams x 126k is
   about 1.77M tokens against a 1.50M pool, so raising it risks the 196a saturation; lowering it changes how often the cache is
   rebuilt.
4. **max_model_len 147,072 (row 13).** It only matters together with row 12, since it caps how far the window can be raised.
5. **Temperature 0.6 (row 28).** It has never been changed on our stack and touches every generated token. The Duck-era n=1
   (0.6 best of three) is weak and comes from another harness.
6. **Yield 150 s x <=3 (row 20).** With no max_tokens and xhigh effort, this is the only per-turn bound on deliberation, and
   215r says the model is clock-bound.
7. **ONLY_RESET_LEVELS set before make (row 9).** It is documented to disable score reconciliation, and its effect on our runs
   was never checked. Its size is unknown and could be zero.
8. **Board history accumulation (row 16).** Boards are about 15% of late prompts and they drive when compaction fires. The
   window arm was pre-stated against harness variance (ICC 0.55) and never run.
9. **Thinking on (row 31).** The impact is large but almost certainly one-directional: the effort result in row 32 predicts
   turning thinking off is a loss.
10. **No max_tokens (row 22).** The effort result says thinking does work, so a cap probably costs levels. The A8 n=1 is from
    another stack.
11. **fp8 KV (row 39).** bf16 KV would roughly halve the pool and saturate it at 14 streams. fp8's quality cost on this model
    was never measured on our stack.
12. **Tool output cap of 1,024 tokens, head cut (row 24).** The prompt itself warns that one board fills it. The 3,072
    middle-cut arm was null, but on another model.
13. **Estimator ratios (row 19).** They move the compaction point by 2-16% (measured), which makes them part of lever 1.
14. **Tool time ceiling of 30 s (row 23).** Long searches die. The model is told about the limit.
15. **analyzer_timeout 900 (row 6).** The per-game clock binds before it does.
16. **max_num_batched_tokens 2048 (row 41).** Prefill chunking; throughput only.
17. **gpu_memory_utilization 0.98 (row 38).** Already near the ceiling. Scaling the memory note's ratio (0.06 = 5-6% of pool),
    +0.01 is about +1%.
18. **Unlimited tool steps (row 21).** The only cap tried (Duck) was worse.
19. **top_p 0.95 / top_k 20 (row 29).** Second-order sampling.
20. **min_p / penalties / seed / generation-config (row 30).** Neutral defaults.
21. **Serving internals (row 45).** Throughput only, and mostly forced by memory or kernels.
22. **Mamba SSM cache bf16 (row 44).** Numerics; 167's measurement never ran.
23. **Yield multiplier 3 / plan cap 500 (row 25).** Small.
24. **512-token margins (row 18).** Small.
25. **Sandbox limits (row 26).** They bind only on runaway snippets.
26. **Tower device and threads (row 36).** One-ulp parity effect; negligible.
27. **Commit-run soft-end buffers (row 11).** No effect on a scored run.

## Values that differ from the brief or could not be confirmed

- **All brief values confirmed in code:** 9,300; 3,918; 14 / 14; 127,488 (126,464); 81,536; 147,072; 900; None; 1,024
  tokens (4,096 chars); 150; 0; 0; 0.6 / 0.95 / 20; thinking on; xhigh; 25%; 1,024 tokens per board.
- **"TOOL_TIMEOUT 30 (hard min)" is backwards.** The code is min(30, max(1, x)) (TA:436), so 30 is a hard maximum. The env
  can only lower it.
- **"Cell 10 sets bm.solver.* and the LOCAL_ANALYZER_*, MULTIMODAL_*, SYN_* env" is not true of the anchor.** The solver
  values are the upstream pickle's; the env comes from the setup script; no SYN_* exists in 8552964. Cell 10 does set
  `bm.solver.*` in the later arm notebooks (c10, c25, r0).
- **The 3,918 s per-game clock is the commit-run value only.** A scored rerun always refits it lower (row 3; about 3,620-3,860
  s for 15-47 min loads per 216d). That assumes 110 hidden games: the code uses `len(bm.games)`, and the 110 comes from 216d
  quoting the competition page.
- **The audit interval is measured from the last level clear or delivered audit, not from game start**, and it is computed
  from the game's initial effective limit. Late-starting commit-run games therefore get a shorter interval.
- **The solver lives at `inference/framework/solver.py`**, not `inference/solver.py`.
- **Inferred, not confirmed:** c10's platform. The only record is HO:548; the Kaggle kernel slug in d87d646 and the
  comparison against the Kaggle pool imply Kaggle. 216ax also notes the student's embeddings under the Py3.13 torch were never
  compared with v8's.
