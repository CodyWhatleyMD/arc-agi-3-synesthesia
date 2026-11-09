# Findings audit, 2026-10-31

The investigator's question: "how many 'findings' are there that have just not been addressed?" Every findings entry was
classified against commits, later findings and the current code (harness/, scripts/runtime_0310/), not against the
entry's own claims. Sources: `notes/reasoner_doubter_findings_2026-09-03.md` (all formats: numbered sections, `findings N`
headings, bold sub-entries, the twelve 216ax addenda; folded in: the 177/181/183c/188 addenda), `notes/OPEN_PROBLEMS.md`
(last updated 10-06), and the pre-registered tests since 10-26 (`notes/prestate_*`), which carry no findings IDs. No
findings ID exists after 216ax in any note. Written by a fork of CL2; scratch classification in the session
scratchpad.

Categories: FIXED-VERIFIED (a commit or later entry shows the fix in place and checked), FIXED-UNVERIFIED (a fix exists,
nothing shows it run), OPEN (a defect, risk, needed test or recommended action with nothing acted on), WITHDRAWN
(retracted or superseded, by the named entry), INFO (a measurement or decision with no action implied). OPEN items carry a
tag: **live** = bears on the current submission stack (anchor v36 / Synesthesia, our vLLM 0.31 runtime, the v2.2 quant,
the harness, the repo); **retired** = on a code path we no longer run (Duck harness, 27B, low-norm/prompt_embeds channel,
the 9B doubter, pre-TAAF notebooks); **hygiene**; **paper**; **not stack**.

## 1. Counts

| source | entries | FIXED-VERIFIED | FIXED-UNVERIFIED | OPEN | WITHDRAWN | INFO |
|---|---|---|---|---|---|---|
| findings file | 346 | 52 | 15 | 26 | 23 | 230 |
| OPEN_PROBLEMS.md | 29 | 14 | 0 | 10 | 3 | 2 |
| pre-registered tests since 10-26 | 15 | 0 | 0 | 7 | 1 | 7 |
| **all** | **390** | **66** | **15** | **43** | **27** | **239** |

OPEN by tag: live 15, retired 14, not stack 7, hygiene 5, paper 2.

Overlaps (counted once per source above, the same issue in two places): OPEN_PROBLEMS C4 = findings 181 (and C6 is 181's
.pth item); G2 = 186; B2 = 184b; E1/G6 = 198; 216ax add. 9 = the Batch A pre-registration. Deduplicated, the **live**
OPEN issues are the twelve in section 3.

Short answer: **43 entries are OPEN and 15 are FIXED-UNVERIFIED** across the three sources. Of the OPEN ones, **15 bear on
the current stack** (12 distinct issues after the overlaps); the rest are on retired paths (14), hygiene (5), the paper (2) or
work outside the stack (7). 230 findings entries are measurements with no action implied.

## 2. Every OPEN and FIXED-UNVERIFIED entry

| ID | cat | tag | what it is | why it counts as open | what would close it |
|---|---|---|---|---|---|
| 6 | OPEN | retired | cn04: doubter turn cap should be actions-per-turn, not a per-game rate | no later entry; 9B doubter harness retired | rule it moot with the 9B doubter harness, or port the actions-per-turn floor if the doubter returns |
| 9 | OPEN | retired | notes-diff trigger works; 'world-adjudicated doubt' left open; 'expect 3/3 next run' never re-run | doubter never shipped (179: 'measured zero COMMITs, never shipped it') | rerun the doubter loop with a world-adjudicated doubt, or close it as retired with the doubter |
| 12 | FIXED-UNVERIFIED | - | prior art required: AERA (arXiv:2605.25931) and 2605.25133 have the doubter's moves on ARC-AGI-3 | cited in paper_related_work_2026-10-03.md and the 10-03 doubter draft; absent from the current paper_draft_v4 (no related-work section with it) | put AERA (2605.25931) and 2605.25133 in the v4 draft's related work wherever hypothesis elimination or the doubter appears |
| 17 | OPEN | retired | re86 self-play lessons; proposed 8-turn evicting-window self-test never run | no later entry | run the 8-turn evicting-window self-test, or close as retired |
| 18 | OPEN | retired | vacuity.py and recall_scaffold.py built, no consumer ('hook what the model already does') | no later consumer; qwen_tools_agent retired | close as retired (no consumer) or hook vacuity/recall into the TAAF python tool |
| 33 | OPEN | retired | MTP mis-verifies on prompt_embeds contexts ('untested') | never tested; prompt_embeds lexical channel retired | close as retired (prompt_embeds lexical channel gone); the image_embeds + MTP path plays (185) |
| 43 | OPEN | retired | throughput A/B; pip-constraint install line 'CORRECTED, AND STILL UNFIXED IN CODE' | no later fix; 0.29 wheelhouse path superseded by the extracted 0.31 runtime | close as retired (0.29 wheelhouse path replaced by the extracted 0.31 runtime) |
| 46 | OPEN | retired | analyzer_timeout 900 -> 1200 queued as the next one-variable test (Duck harness) | never run; Duck harness retired | close as retired, or check TAAF's analyzer_timeout against its own timeout data |
| 53 | OPEN | not stack | Bayesian (Gamma-Poisson) index policy for slot scheduling | never wired in (140); 216f built a simpler stall rule instead, tested null (216i) | close as superseded by 216f's stall rule (tested null), or wire the index in and A/B it |
| 56 | OPEN | hygiene | record-keeping defect: duplicate runs/kaggle_synesthesia_029 dirs ('one should be deleted or symlinked') | no later entry | delete or symlink one of the duplicate runs/kaggle_synesthesia_029 dirs |
| 60 | OPEN | live | ACTION7 is offered in six games; describe it by its class, never by a guess like 'undo' | c0580db did so in the Duck shim; the CURRENT harness tells the model ACTION7 = 'UNDO' (harness/src/ARC3-Inference/inference/agent/action.py:20) while arcengine defines it only as SimpleAction (enums.py:59) | read arcengine/game source for what ACTION7 does in the six games; if it is not undo in all of them, describe it by class in action.py |
| 61 | OPEN | retired | thinking arm's suspect (--frequency-penalty 0.4) hardcoded; 'Still open, NOT claimed fixed'; stale checked-in notebook | no later entry; qwen notebook path retired | close as retired (qwen notebook path), or regenerate the checked-in notebook |
| 77 | OPEN | live | meter = clock, per-level rate: spec for a numeric action-budget estimator | never built (10-04 era: 'telling the model its move budget' built-never-enabled; 216h self-review asked for a numeric budget) | build actions_remaining() from the per-level meter rate and give it to the model; A/B it |
| 77b | OPEN | live | budget as a plan constraint: actions_remaining() bounds plan length | never built | same as 77 |
| 78 | FIXED-UNVERIFIED | - | Gemini's games use the ARC-1 palette | build_bases.py imports the engine palette; correction sent to Gemini; brief never updated | update the Gemini game brief with the engine palette |
| 85 | OPEN | retired | bake breaks glyph typing; round trip 'untested' | bake channel retired, never tested | close as retired with the bake |
| 88 | FIXED-UNVERIFIED | - | actions wasted on levels that didn't advance | 88c DUCK_LEVEL_CAP=200 in the Duck harness; no measured effect recorded; Duck harness retired | close as retired (Duck); for TAAF the scheduler/reflection A/B (216i) already measured the stall question |
| 88c | FIXED-UNVERIFIED | - | per-level cap DUCK_LEVEL_CAP=200 default on | built in the Duck harness; no result recorded; not in the TAAF stack | same as 88 |
| 98 | FIXED-UNVERIFIED | - | Duck-era v8 smoke: ACTION7 unexecutable, tool args echoed as \uXXXX, images on Kaggle/off locally | shims in the Duck-era v8 notebook (submitted 1.70, 101); no check recorded; the current harness maps ACTION7 (action.py:20); the \uXXXX echo not re-checked in the current harness | check the current harness for the \uXXXX tool-argument echo |
| 143 | OPEN | live | jerber/arc-code: the transferable part is 'a prompt change we have not tried' | no later entry tries it | name the untried arc-code prompt change and run it once, or close |
| 145 | FIXED-UNVERIFIED | - | Route A runner + UNDO built (fda8889, 0b312fa) | its one run (10-02) was invalid at 1.18 (216e); never re-run | a valid Route A run on our stack, or close it |
| 146 | FIXED-UNVERIFIED | - | delta-Vision (arXiv 2609.34972): cite in the paper as the mechanism behind the negative input-fusion result | cited in paper_draft_v2_2026-10-26 and paper_outline_v2; absent from paper_draft_v4_2026-10-27 | cite delta-Vision in the v4 draft where the input-fusion negative result is stated |
| 147 | FIXED-UNVERIFIED | - | cross-game memory shim built (f3fea2a), 14/14 unit tests | never run in a game; Duck path retired | run xgame in one A/B, or close as retired with Duck |
| 151 | OPEN | retired | pre-submission audit: 20 confirmed defects in the v6 path, two can zero a run | 156 split FIXES (natives changes kept out); no entry closes the 20; v6/Duck path retired 10-05 | close as retired with the v6/Duck path (none of the 20 is in the TAAF stack) |
| 152 | OPEN | retired | v6 loses; a middle shape (65k context, 30-turn cap) 'still untested' | never run; Duck path retired | close as retired |
| 153 | OPEN | retired | Opus vs Flash-Next: two broken harness channels (world model harvested from content only; 60 s yield duplicates prompts) | Duck-era tool_agent; no fix entry; current TAAF tool_agent differs, channel 2 not re-checked | check whether the TAAF tool_agent has an equivalent of channel 2 (yield-duplicated prompts); otherwise close as retired |
| 157 | FIXED-UNVERIFIED | - | the 10-01 ranked interventions were never run (only turn shape) | ported later as Batch A SYN_* switches (12a000d); batch +0.98 unresolved, never individually tested | individual tests of the Batch A switches, or accept the batch null |
| 158 | OPEN | retired | both AZR runs measured nothing: verify() crashed on every sample | instrument-fix workflow ran (era notes) but no AZR re-run recorded; AZR parked | rerun AZR iter1 on the fixed verify(), or close with AZR parked |
| 160 | OPEN | live | engine aligns prefill chunks to the min group block (4 tokens): prefix hits resume from mislabeled GDN/PLE state; SPLIT_FIX built | SPLIT_FIX is not in the 0.31 runtime overlay or harness; stock 0.31.0 engine/core.py:346 still sets block_size = min(prefix-cacheable groups); effect measured below noise | read our runtime's KV group spec: if the QSA ring (block 8) is prefix-cacheable, block_size is 8 and the mislabeled-state bug persists; port SPLIT_FIX into the 0.31 overlay or record it as measured-below-noise and accepted |
| 167 | FIXED-UNVERIFIED | - | production vLLM runs GDN state in bf16 via an arch-alias gap | 189's arch-name sweep resolved the alias in three places; no recorded fp32-vs-bf16 result | one serving A/B of fp32 vs bf16 GDN state on our stack, or record bf16 as the accepted choice (Han Solo also runs bf16) |
| 176 | FIXED-UNVERIFIED | - | seeded sample over a growing directory not reproducible; fix = birth-time symlink tree | fix endorsed; no entry confirms perception #2 re-run on it | confirm perception #2 was re-run on the pinned manifest |
| 181 | OPEN | live | three bugs: ONLY_RESET_LEVELS leaks process-wide (disables score reconciliation); lf52 unseeded shuffle; stray .pth | lf52 mitigated (OPEN_PROBLEMS C5); .pth still written by notebook cell 7 (C6); current TAAF game_api.py:244-251 sets ONLY_RESET_LEVELS AFTER make on purpose for R11.12 reconciliation, but notebook cell 9 sets os.environ['ONLY_RESET_LEVELS']='true' before any game -- effect on the run never checked | move the ONLY_RESET_LEVELS line in cell 9 so it cannot precede arcade.make (or show it does nothing), and stop cell 7 writing the .pth |
| 196b | FIXED-UNVERIFIED | - | Franzen's anti-eviction: priority gate + trim handover + 58 Ki drain | gate ported (0558a8b, 216ak), never run in play; drain not ported | run the ported gate (0558a8b) once in play; port the 58 Ki drain if the gate helps |
| 198 | OPEN | live | Arm B v4 hidden 18.01; student coverage on unseen hidden boards: 'a pixel fallback for boards the student has never seen' | never built; anchor v36 still has no fallback | measure student-tower fidelity on block patterns absent from the public games, or add a pixel fallback for unseen blocks |
| 207 | OPEN | not stack | which experts our games use; an expert-pruning arm is 'a candidate, untested' | never run | run the expert-pruning arm once, or close |
| 215n | OPEN | live | the model's TAAF review scored: MOUSE row/col clamped to 0..63 before the engine (solver.py:731-732), a typo becomes a real scored edge click | scorecard C15 'not built'; current harness solver.py:731-732 still clamps | turn the MOUSE clamp at solver.py:731-732 into an error the model sees (the engine already bounds-checks) |
| 215w-frontier | FIXED-UNVERIFIED | - | the frontier moved; the 10-01 plan (Franzen's recipe on our stack) never run | Franzen-on-ours notebook built (216ak, build_franzen_on_ours_notebook.py); no recorded run of it | run Franzen-on-ours once, or close |
| 216e | FIXED-UNVERIFIED | - | no priority switcher in any submitted stack; Route A ran once (10-02, 1.18, invalid) | Franzen's gate ported (0558a8b, 216ak), never run in play; no valid Route A measurement | a valid measurement of the priority gate / Route A, or close |
| 216ak | FIXED-UNVERIFIED | - | Sunday: Franzen's priority gate ported, Franzen-on-ours notebook built | gate 0558a8b never run in play; Franzen-on-ours never run (216aw: its image limit was untested) | same as 216e |
| 216ax | OPEN | live | base switch; v8 as code; anchor v36 -- board-tower torch 2.10 -> 2.11, 'embeddings not yet compared with v8's'; WorktreeCreate hook broken (agents make their own worktrees) | never compared (v36 public 47.37 vs v8 46.99 is consistent, not a check); hook is the investigator's | compare student embeddings under torch 2.11 against v8's 2.10 on the same boards; Investigator: fix or remove the WorktreeCreate hook |
| 216ax-add9 | OPEN | live | Batch A vs controls: 95% CI [-4.35, +10.92], not resolved | later Kaggle n=3: +0.98 [-5.80, +8.62], still not resolved; never shipped | more Batch A replicates, or accept not-resolved and leave it unshipped |

OPEN_PROBLEMS.md:

| ID | cat | tag | what it is | why it counts as open | what would close it |
|---|---|---|---|---|---|
| A1 | OPEN | live | project licensing: winners must open-source their code under CC0/MIT-0 before private scores | no LICENSE file anywhere in the repo or harness/ (git ls-files); the investigator's decision | The investigator picks the license (CC0 / MIT-0 for our code); add LICENSE + NOTICE to the repo and the harness dataset |
| A2 | OPEN | retired | GCP Spot -> Standard scheduling | GCP twin terminated; moot | close as moot |
| B4 | OPEN | hygiene | branch kv-fp8fix, 41 unmerged commits from a dead agent | still 41 commits not in HEAD (git log HEAD..kv-fp8fix) | merge, cherry-pick or delete kv-fp8fix |
| C1b | OPEN | live | no mid-run early-play watchdog (one game answers, 109 stay silent: the v7 0.00 shape) | never built; the vLLM keep-alive watchdog relaunches a dead server, not a silent game | build a during-play watchdog (silent game / silent wave relaunches the server) with its own test matrix |
| C4 | OPEN | live | ONLY_RESET_LEVELS leaks process-wide (= findings 181) | notebook cell 9 still sets it before any arcade.make; see 181 | see 181 |
| C6 | OPEN | hygiene | the notebook writes a .pth into whatever venv runs it | still in cell 7 (taaf_kaggle_sources.pth into purelib); harmless in ephemeral containers | drop the .pth write from cell 7 (sys.path is already set in-process) |
| C7 | OPEN | hygiene | test_images' provenance check skips silently when its ref is gone | no entry closes it | make the provenance check fail, not skip, when its ref is missing |
| C8 | OPEN | hygiene | two test suites have no runner | no entry closes it | give both suites a runner |
| F2 | OPEN | live | the whole repo exists in one working copy; commits unpushed; branches without upstream | harness-fixes-2026-09-09 is 1,107 commits ahead of private/; 47 of 48 local branches have no upstream | push harness-fixes-2026-09-09 and the live branches to private/ |
| F3 | OPEN | not stack | an agent's GPU measurement (layer_inject RESULTS_S5.md + 4 tensors) uncommitted in a /tmp worktree | never committed on any branch (git log --all empty); no worktree under /tmp remains -- almost certainly lost | accept as lost, or re-record S5 if it is ever needed |

Pre-registered tests since 10-26:

| note | cat | tag | what it is | status | what would close it |
|---|---|---|---|---|---|
| prestate_batch_a | OPEN | live | Batch A (11 archived tools as SYN_* switches) | Kaggle n=3: +0.98 vs controls, not resolved; HTTP-400 rollback fix branch syn/batch-a-s2; never shipped | more replicates or accept not-resolved |
| prestate_colab_platform | OPEN | not stack | Colab as its own platform; pooling by TOST | pre-stated (f163cbe); no result recorded | run the Colab pool or close |
| prestate_history_window | OPEN | not stack | history window as a variance experiment (K=1/K=4) | pre-stated 10-27; merged into Batch A as SYN_HISTORY_BOARDS_KEEP; never run alone, no result | run it or close (it lives inside Batch A now) |
| prestate_side_watcher | OPEN | not stack | side watcher arm (CL3) | pre-stated (42633ac); no smoke or result recorded | run the smoke or close |
| prestate_requant_w4a16 | OPEN | not stack | our own W4A16 AutoRound requant on calib_v2 | launched 10-30, stopped on RAM/swap; never completed | restart with RAM headroom, or close (post-deadline artifact) |
| prestate_restoration | OPEN | paper | R0: untimed v36 at concurrency 1 for the write-up | stopped 10-31 at 13 of 25 games (mean 66.2 on the 13); 12 games unplayed | rerun the 12 unplayed games untimed (both cards free after 11-02) |
| prestate_untimed_rerun | OPEN | paper | post-deadline untimed reruns (Franzen's harness first) | planned for after 11-02 | run after 11-02 |
## 3. OPEN items that bear on the submission stack (before the Nov 2 deadline)

Ranked by what they can cost the submission. Each was checked against the current tree today.

1. **A1 -- no license anywhere.** `git ls-files` finds no LICENSE or NOTICE in the repo or in `harness/`. The competition
   requires our code open-sourced under CC0/MIT-0 *before* private scores. The investigator's decision; adding the files is minutes.
2. **181 / C4 -- `ONLY_RESET_LEVELS` set before any game.** Notebook cell 9 runs `os.environ["ONLY_RESET_LEVELS"] = "true"`
   before `bm.run`. The current TAAF `game_api.py:244-251` sets it deliberately AFTER `arcade.make` "so the make-time RESET
   still full-resets and registers via new_play (which R11.12 reconciliation needs)". Effect on our runs never checked.
3. **215n -- MOUSE clamp.** `harness/src/ARC3-Inference/inference/framework/solver.py:731-732` clamps row/col to 0..63, so a
   mistyped coordinate becomes a real, scored edge click instead of an error (the model's own review found it 10-16;
   scorecard item C15 "not built").
4. **60 -- ACTION7 labelled "UNDO".** `inference/agent/action.py:20` tells the model ACTION7 is UNDO; arcengine
   (`enums.py:59`) defines it only as a SimpleAction, and the competition calls it "Additional simple action". Findings 60's
   rule was to describe it by class unless the game source says otherwise. Not checked against the six games that offer it.
5. **160 -- prefill split alignment.** SPLIT_FIX is in neither the 0.31 runtime overlay nor the harness. Stock vLLM 0.31.0
   `engine/core.py:346` still sets `block_size = min(prefix-cacheable groups)`; whether our QSA ring group (block 8) counts,
   and so whether prefix hits still resume from mislabeled GDN/PLE state, is unchecked. 160 measured the output effect below
   run-to-run noise, so this is correctness, not score.
6. **C1b -- no mid-run watchdog.** The v7 0.00 shape (one game answers, the rest stay silent) is still uncatchable during
   play; the setup's vLLM watchdog relaunches a dead server, not a silent game.
7. **198 -- student coverage on unseen boards.** The student tower has no fallback for block patterns absent from the public
   games (188: coverage, not capacity, is its limit); the hidden 110 are where that bites.
8. **216ax -- tower embeddings under the new torch never compared.** The Py3.13 rebuild moved the board-tower student from
   torch 2.10 to 2.11; its embeddings were never compared with v8's. v36's public 47.37 against v8's 46.99 is consistent,
   not a check.
9. **F2 -- one working copy.** `harness-fixes-2026-09-09` is 1,107 commits ahead of `private/`; 47 of 48 local branches
   have no upstream. Everything since 09-09 exists on one disk.
10. **77 / 77b -- numeric action budget.** The per-level meter rate was specified 09-23 and never built; the model still
    reads budget bars by eye (the 10-18 self-review asked for exactly this).
11. **Batch A (216ax add. 9 / prestate_batch_a)** -- not resolved at n=3 on Kaggle (+0.98 vs controls); not shipped. A
    candidate, not a defect.
12. **143** -- arc-code's transferable "prompt change we have not tried" (low).

Not in the findings ledger but live today: the DFlash2 work (notes/dflash2_flashnext_2026-10-31.md) is in progress, and
R0 (prestate_restoration) stopped at 13 of 25 with 12 games unplayed.

## 4. Judgement calls and what could not be classified cleanly

- Every entry got exactly one category; none was left unclassified. Where the evidence was thin I chose OPEN or
  FIXED-UNVERIFIED and said why (rule: when unsure, OPEN).
- "Retired" OPEN items are still OPEN by the definition used here (nothing acted on); they are tagged so they don't read as
  current risk. Closing them is a one-line "moot" note each.
- FIXED-VERIFIED for a recommendation means it was built AND measured, even when the measurement was a null
  (49, 51, 216f, 216g).
- 21 is FIXED-VERIFIED on downstream evidence (every later harness reads the reasoning field); the 09-11 commit itself
  was not located in `git log`.
- OPEN_PROBLEMS C2/C3/C5 are taken as closed on the file's own Closed section (dated, with commits and test counts), not
  re-run here.
- The ACTION7 item (60) may resolve the other way: if the six games do implement undo on ACTION7, the harness label is
  right and 60 should become WITHDRAWN. That needs the game source, which this audit did not read.

## 4. Closures, 10-31 night (CL2, after the audit)

- **9 / F2 -- one working copy: CLOSED.** All branches and tags pushed to `private` on 10-31 evening; checked 21:55 CDT
  after `git fetch private`: 0 of 52 local branches missing on the remote, none ahead.
- **4 / 60 -- ACTION7 labelled "UNDO": CLOSED for the public set.** Read each of the six public games that offer ACTION7
  (ar25, bp35, lf52, sb26, sk48, su15): every one restores a saved prior state on ACTION7, so "UNDO" matches the game
  source, which is the exception findings 60's rule allows. Hidden games are unread by definition; if a hidden game uses
  ACTION7 differently, the label misleads there. Residual risk accepted, not removed.
- **2 / 181 / C4 -- ONLY_RESET_LEVELS before any game: CLOSED as inert on scored runs.** Read arcengine's reset path and
  competition mode on 10-31: on a scored (competition-mode) rerun the flag does not change make-time reset behaviour, so
  setting it before `bm.run` costs nothing there. Not measured in a run; closed on the source read.
- **8 / 216ax -- board-tower student under torch 2.11: CLOSED.** The student runs on CPU in fp32 under the IMAGE's torch
  (v8 2.10.0+cu128 / py3.12, v36-37 2.11.0+cu128 / py3.13; neither runtime's 2.13). 300 real boards from all 25 public
  games: v8's pair vs v36's image, 300/300 bitwise identical (max abs diff 0); same-env repeat 300/300; detection check
  (2 -> 4 threads) 291/300 differ, cos >= 0.99999996. Local AVX2 only, not Kaggle's AVX-512 path.
  notes/tower_torch_compare_2026-10-31.md.

## 5. 10-31 night workflow

The workflow `stalled-items-night-1031` (~/.claude/workflows/stalled-items-night-1031.js) gave each item that had stalled by
10-31 evening its own agent, from 10-31 ~22:30 CDT to 11-01 ~04:50 CST (the runtime unpack is still running). Each agent's
returned result is condensed below, in its own words where possible, with its caveats. **CLOSED** = answered by a
pre-stated test or a measurement (a refutation counts); **OPEN** = not answered, with what would close it; **DEFERRED** =
not worked, with the reason. **[checked]** marks what I re-checked myself while writing this (11-01, 10:40-11:10 UTC);
everything else is the agent's own report and was not re-run.

Clocks: local time fell back from CDT to CST at 07:00 UTC on 11-01, so local times logged across the switch are ambiguous
(one push log reads 01:38:01, then 01:08:39); UTC is used below where it matters. The deadline [checked: `kaggle
competitions list`] is 2026-11-02 23:59:00, UTC by the CLI's convention (the rules page was not opened): **17:59 CST on
Monday's wall clock**. The workflow's "18:59 CDT" is the same instant, but no clock reads CDT on Monday.

| # | item | status | in one line |
|---|---|---|---|
| 5.1 | time stop: simulation | CLOSED | S 1,500 s, M 600 s, park off: +3.00 [p10 +0.93, p90 +4.92] vs v36's clock (main variant); -0.06 if no level clears after the censoring point |
| 5.2 | time stop: code, review, fix | CLOSED on stand-in tests | 8d10d07; the review found 3 blocking issues; 7161345 fixes all three; never run with the real ToolAgent at the candidate's settings |
| 5.3 | time stop: real-stack smoke | CLOSED (pass, at smoke settings) | 7161345 on the local 6000, park on, S 600, M 1,100, soft end: R1-R6 held, 25/25 started |
| 5.4 | time stop on Kaggle | OPEN | the candidate (time stop + start retry) is RUNNING; the time-stop-only push was dropped as redundant; the scored run's 9 h offset (forum 753843) is unaddressed |
| 5.5 | c17 concurrency step | CLOSED (c17 fails); bisection OPEN | collapses from play-minute 12.5, like c20 and c25; c15 is next, not staged |
| 5.6 | KV tier kt3 + restore check | CLOSED | kt3 refuted (windows 15-40 fail both gates); restore: R1 inconclusive, R2 passes; new: cold prefills don't reproduce |
| 5.7 | more context per game | CLOSED for the host tier; rest DEFERRED | the tier cannot add active capacity; 10 x 122k was null in October (196f); nothing else built |
| 5.8 | DFlash mechanism 1 | CLOSED (refuted) | the identification patch works and buys nothing measurable |
| 5.9 | DFlash mechanism 2 (and 3) | OPEN | the drafter's SW blocks are evicted before the follow-up request; fix candidates untested |
| 5.10 | park/resume cost | CLOSED (n=2) | cold resume ~38 slot-seconds; immediate resume no measurable cost |
| 5.11 | load test A | CLOSED (refuted); one claim corrected | 32 vs 4 threads 1.05-1.08x; its "effective concurrency 1" is wrong: production reads with 8 readers |
| 5.12 | load test B | DEFERRED | cold vs warm GPU sessions: held for the investigator's yes (spends GPU quota) |
| 5.13 | runtime unpack | OPEN (bench running); shipping DEFERRED | Kaggle already unpacks with pigz; the second instance is rerunning its arms |
| 5.14 | custom-games benchmark | DEFERRED | never started; spends the investigator's Kaggle AI quota |
| 5.15 | TPU student hardening | DEFERRED | never started; would replace the shipped student |
| 5.16 | DFlash drafter fine-tuning | DEFERRED | never started; targets acceptance, which is not DFlash's measured limit |

### 5.1 Time stop: simulation -- CLOSED

- Chosen: `pool_stall_seconds` 1,500 s, `pool_min_share_s` 600 s, `pool_park` off. Pre-statement d7443ba (22:39 CDT) before
  the results (223b3a2); notes/pool_timestop_sim_2026-10-31.md, scripts/pool_timestop_sim.py (seeded; a 4-resample rerun
  reproduced the stored results with 0 mismatches). No GPU.
- Model: a 110-game hidden run on 14 slots, 32,400 s notebook, load drawn from U(553, 1,247) s, 100 seeded resamples per
  policy with common random numbers. Score = score_offline.py's per-game score (cap 1.15) averaged over all 110 games, 0 for
  a game that never starts; "paired" = the per-resample difference against (a), v36's refit clock (about 3,860 s).
- S1500 M600, paired vs (a), median [p10, p90]: main +3.00 [+0.93, +4.92] (99% of resamples above (a)); a 600 s clean exit
  +2.52; the 14 hardest public games +1.44; every gap x1.25 +1.61; no level clears after a realization's censoring point
  -0.06. Worst-case regret across these five variants 0.43 points, the lowest in the grid; S1200 (0.72) "is the fallback if
  games stop clearing after about 65 minutes". With M600 all 110 games start in every resample of every variant.
- The branch as built (action cuts only): -14.54 [-19.39, -9.17], with a median of 60 of 110 games never started. Park at
  S1500 M600: +0.00 in all five variants (p90 at most +0.37), "so it is not worth an untested resume path".
- Against its pre-statement: "P1, P2, P5 and P6 held. P3 was half right: the best S was in range, but the curve is not flat.
  P4 held for score but missed the starts effect. The pre-statement's expectation that park helps was wrong."
- Rests on, largest first: whether games keep clearing past their fair share (190 of 250 timed realizations were censored by
  the clock, 77 continue on the pooled tail; R0, one untimed 14-game run, is the only evidence of play past ~65 min); how a
  scored rerun ends at 9 h (5.2 issue 3, 5.4); hidden-set difficulty (the 110 are resampled from the public 25).
- Not verified by the sim: the time-stop code itself (it followed its reading of the uncommitted diff at ~22:47); c10's 4.6
  actions/min; the hidden run's load time.

### 5.2 Time stop: code, review, fix -- CLOSED on stand-in tests

- **Code** 8d10d07 on branch pool-clock (worktree /home/ignaz/github/arc-prize-2026-poolclock), both knobs off by default;
  tests pre-stated in e29cf5b before any run. Builder e43b796: `--pool-stall-seconds S` / `--pool-min-share M`, both
  requiring `--pool-clock`. The author's suite: test_time_stop 25/25 (7/7 mutants caught in the final round); knobs unset =
  6091476's behaviour on 5 scenarios; park/resume passes; 110 games on 14 slots at 800x, never started: off 59, stall only
  45, reserve / both / both + park / + soft end 0.
- **Review** (pre-statement 5d3dab2, amendments 1a448d3, cab8f1c, 57b9704; the real solver at 100x/200x): off path unchanged,
  no races found; the planned config (S 1,500, M 600, park off, heavy-tailed requests) started 110/110 in 2 of 2 seeds with
  0 reserve cuts. Three blocking issues:
  1. the reserve was just-in-time, so its last wave got seconds of play or never started (R3 with gap-fitted latencies: 6,
     9 and 6 of 85 games never act); its boundary allowance was the mean s/action (13.0 s median) against a measured 41.4 s
     expected wait to the next poll (C1-C7, 18,684 requests);
  2. `pool_min_share_s` below the 600 s pool floor left games unstarted every time (R1: two games never act, 2 of 2 runs);
  3. pre-existing (fc12c11/71610b1): nothing ended a scored pool-clock rerun before the platform's 9 h kill, so our code
     never closed the competition scorecard; the sim had flagged the same gap.
- **Fix** 7161345 (pushed to private/pool-clock; pre-statement 4e89493, amendments 42bc8a7, 8d7643a, a7db82d, 9e752be, each
  before the runs it covers): reserve capacity counted slot by slot, with a 99th-percentile poll-wait budget (283 s on
  C1-C7); while the reserve binds, a game taking a slot is protected for about M, not the 600 s floor; a new
  `pool_end_margin_s`, default 600 s as in v36: with the pool clock on, an end epoch and no soft end, play stops at the end
  epoch minus 600 s, open games are finished and TAAF closes the scorecard. Final suite (6 tests, wait quantile 0.99)
  passed in 1,176 s: the reviewer's R1, R2, R3 and R6 pass on 7161345 and miss on 8d10d07; the end-of-play tests return ~1 s
  after the end of play with the scorecard closed once before T (8d10d07 never ends by itself).
- Still open in this chain (none stops the candidate's commit run):
  - **Wait quantile 0.99 vs 0.9.** 0.9 missed the pre-stated R3 criterion in 2 of 9 runs. 0.99 met it in 9 of 9, but the
    last game still got 458-514 s instead of 600 s in 6 of 9, and the reserve fires earlier (about 675 s earlier in seed 2),
    with 15-25% fewer actions for marathon games. The running candidate carries 0.99. The orchestrator's call.
  - **H6**: `_play_one` builds the analyzer before `_pool_take_budget`; if the factory raises, `_pool_unstarted` stays one
    too high and the per-slot reserve cuts one over-share game early and leaves its slot idle. Low likelihood (ToolAgent
    construction is pure Python); unfixed.
  - With park off, a reserve breach can finish more over-share games than needed: about 0.1 extra per breach at real pace by
    the reviewer's estimate; unguarded, and not addressed in 7161345's summary.
  - Commit runs (soft end): the last wave can get up to 60 s less than M. Untested.
  - Builder (main checkout, unchanged by the fix): it accepts `--pool-min-share` below 600 (the harness now caps it), has no
    flag or log line for `pool_end_margin_s` (the 600 s default applies), keeps a stale "(the platform ends the run)"
    comment, and runs `write_dataset` before its refusal checks.
  - Not run: H3r (real-latency resampling at 14 threads), and anything on Python 3.13 (the suites ran on 3.12).
  - Every test uses stand-ins (a scripted engine, a fake analyzer) on compressed clocks. The reviewer and the fixer each ran
    14 Python threads at nice 19 (the fixer pinned to 4 CPUs) during the kvtier_kt3 GPU run, over the letter of the 4-thread
    rule; the effect on kt3 was not measured.

### 5.3 Time stop: real-stack smoke -- CLOSED (pass, at smoke settings)

- Harness 7161345 in the Kaggle image on the local 6000: 25 games, 14 slots, park on, S 600 s, M 1,100 s (not the 300 s
  example: the real solver replayed on r6's clear schedules gave 1 reserve stop in 20 at S 300), 1,974 s of play, soft end.
  Pre-statement and staged smoke notebook 53d4f99 before the run; result 70dee87, wording 6536c83
  (notes/prestate_pool_timestop_smoke_2026-11-01.md). R1-R6 held; not VOID.
- 7 time-stall parks and 7 reserve parks, all at +1,103-1,153 s; 14 resumes, of which 3 then played and 11 came at the
  soft-end margin and finished with 0 actions; 25/25 games started (last start +1,134 s); 0 tracebacks, only HTTP 200, 14
  request errors (all end-of-window read timeouts); papermill rc 0. Container gone and the 6000 empty afterwards.
- Not covered: the candidate's own settings (S 1,500, M 600, park off; the park-off stop, which finishes the game, has only
  unit tests), the scored-rerun end of play (`pool_end_margin_s`, no soft end), and second-wave shares (logged at INFO,
  which the notebook does not show). A second ~40 min local smoke with park off would cover the first.

### 5.4 Time stop on Kaggle -- OPEN

[checked: `kaggle kernels status`, 11-01 ~10:45 UTC; the main session's transcript for the stop and the cancels]
- **codywhatleymd/arc-agi-3-synesthesia-candidate: RUNNING.** Staged in fb88f6d. Its notebook expects harness fa326e3, which
  contains 7161345 and the start-retry commit 4d63b91 (`git merge-base --is-ancestor`, both), and sets `pool_clock = True`,
  `pool_stall_seconds = 1500.0`, `pool_min_share_s = 600.0`, no park line, `ARC3_START_ATTEMPTS=4`, `ARC3_START_SKIP=1`.
  Its pre-stated cut (notes/prestate_candidate_2026-11-01.md, 33445ff): a clean run, the switches visible, all 25 games
  started with more than 0 actions, mean >= 32.6; PASS means "submit it in today's window, the investigator's decision". It carries two
  changes, so it is a go/no-go gate, not a one-variable measurement; its pre-statement says a public-25 mean in range "is
  not evidence the candidate scores higher" (that evidence is 5.1).
- codywhatleymd/arc-agi-3-synesthesia-start-retry (v37 + the start guard, the fallback): RUNNING. The two runs hold both GPU
  sessions.
- The time stop alone (kernel ...-pool-timestop, staged 7c5531c, dataset arc3-syn-harness-pool-ts1) was never pushed. Main
  stopped its push loop at 10:32:02 UTC (`kill -- -862156; kill 862159`; the log ends at try 136, 10:17:07Z) because "the
  candidate makes [it] redundant", as main's 08:26 UTC handoff had planned. Not needed; nothing to close.
- pool-ts0 (the pre-fix 8d10d07 build) was cancelled while still queued, at 07:08 UTC, by main through the Kaggle MCP after
  asking the investigator to cancel it ("It hasn't started, so cancelling costs nothing"). ple-skip was cancelled while queued at 07:15
  UTC, when main and CL1 (the investigator had asked them to decide) gave its slot to the candidate. Both read CANCEL_ACKNOWLEDGED.
  The pool clock without the time stop (...-pool-clock) and v37 are COMPLETE; per main's handoff, v37 scored 51.37 public
  (8 won) and the no-stop pool clock 36.04, with su15 and tr87 at 0 actions: "never submit no-stop".
- What closes 5.4: the candidate's run finishes and is read against its pre-statement (live log read by ~30 min).
- **Open, and no commit run can close it: the scored run's 9 h clock.** Commit runs have a soft end, so `pool_end_margin_s`
  first runs on the real stack in the scored rerun itself. Forum topic 753843 [checked: read through the Kaggle MCP]: the
  rank-2 team reports that on scored runs "the notebook itself starts only ~40 minutes after the container starts" (a
  killswitch on /proc/uptime over 20 min errors consistently) and that "these 40 minutes count against submission" (their
  successful submissions run 9 h, not 9 h 40); an empty notebook now takes ~50 min to error. CPMP replied that a pre-start
  delay "is not uncommon". If that holds for us, an end counted from NOTEBOOK_START_EPOCH (the pool clock's
  NOTEBOOK_START + 32,400 - 600, and v36/v37's refit clock, which ends games by start + 31,800 s) comes ~30-40 min after the
  platform's kill, and our code never closes the scorecard. How a killed run is scored is unknown; CPMP lists "timeout"
  among errors that cost a submission. Against that: our scored submissions of 10-30 03:06 and 10-31 10:19 UTC, after the
  forum report, are COMPLETE at 21.75 and 20.44 [checked: `kaggle competitions submissions`; which notebook version each ran
  was not checked]; a completed score does not show whether play ended before a kill or a killed run is still scored.
  Main's handoff (08:26 UTC) marks this "URGENT, NOT BUILT" and proposes: anchor the end to machine boot
  (`time.time() - /proc/uptime`, used only when uptime < ~2 h), end = min(notebook start, boot) + 32,400 - margin, and log
  uptime at BOOT. [checked: no commit on any branch since 08:00 UTC mentions uptime or 753843; nothing in notes/.] Our only
  uptime reading is 218 s on a batch run (findings file, line 8122); none on a scored run.
- What would close it: that anchor (or a measured reason not to need it), unit-tested against a faked /proc/uptime and
  visible in a commit run's BOOT line, before a scored submission of either the candidate or the fallback.

### 5.5 c17 concurrency step -- CLOSED (c17 fails); bisection OPEN

- Pre-statement and staged c17 525af93 before launch; result c562956 (notes/concurrency_sweep_2026-10-31.md). c20's exact
  build with 17; local 6000; 31 min of play.
- "c17 does NOT hold. It collapses the same way c20 and c25 did, onset at play-minute 12.5 (KV 98.0%, then a 99.8% peak;
  prompt recompute 8-10k tok/s; generation drops from about 1,064 to about 280 tok/s; requests waiting in 30/30 samples)."
  It fails test (c) at 10-15 (738 < 935 tok/s) and all three tests at 15-20, 20-25 and 25-30. Onsets: c25 9.2 min, c20
  11.7, c17 12.5. Before the pool fills, 17 streams give only +6-8% generation over r2/r6.
- Caveats: n=1, local only, throughput only (no score); stopped at 31 min instead of the pre-stated ~40 (windows 30-40 could
  not change a verdict already failed); the floors come from the anchor harness 8552964, not the pool-clock build; another
  agent's sim (4 workers, nice 19) overlapped the onset, effect not measured.
- What closes the bisection: c15 = the same build with 15 (`--concurrency 15 --env ARM_MAX_NUM_SEQS=15`, c15 kernel id,
  title and out dir), cell-diffed against synesthesia_c17 first because the builder has changed since (e43b796), with the
  same tests and floors (935/800/881/865 tok/s); c16 only if 15 holds. One GPU slot, ~40 min. [checked: no synesthesia_c15
  staged, no c15 log in ~/kaggle_local.] Crude expectation: 15 reaches ~99-101% of the KV pool (a coin flip), 16 ~106-108%.
  If 15 fails, 14 is the ceiling at this per-stream context; going past it needs a smaller per-stream context or a bigger
  pool (untested). Main's handoff: "concurrency stays 14".
- Side findings, not fixed: RUN_CONFIG.json `serving.max_num_seqs` reads 14 in c17 and c20 (SERVER_CMD.json has the true
  value); ~/kaggle_local/throughput_windows.py raises IndexError on a bare filename.

### 5.6 KV tier kt3 + restore correctness -- CLOSED

- kt3 = kt2 + a 122,880-token history target (`ARM_TARGET_CONTEXT=122880`, `ARM_ANALYZER_CONTEXT_WINDOW=140000`), with kt2's
  vLLM command line. Pre-statement and staged notebook 307694b before any run; check scripts 2247218 before they ran; R1
  result and R2 pre-statement 6aaef21; results 858c6f5 (notes/kvtier_kt3_2026-10-31.md; UPDATE at the top of
  notes/kvtier_handoff_2026-10-31.md).
- **kt3 REFUTED.** Gate: every 5-min window in minutes 10-40 needs exact effective prefix hit (GPU + tier) >= 85% and
  generation >= 813.8 tok/s (0.9 x kt2's 904.2). 10-15 passes (909 tok/s by the token counter, 93.9%); every window from 15
  to 40 fails both (321-435 tok/s, 41.5-66.8%). Mechanism: 14 live prompts of ~110k tokens (~1.5M) exceed the 1.47M-token
  GPU pool, and "a host tier cannot add active capacity, because a running request needs its whole KV on the GPU". The tier
  was active (it served 39-61% of GPU misses) and still did not hold the line.
- **Restore correctness.** R1 (greedy tokens, 8 prompts of 20k-138k tokens): INCONCLUSIVE, as pre-stated, because two
  identical cold runs already diverge on 8/8 prompts. R2 (first-token top-20 distributions, 16 cases): passes all four
  pre-stated criteria, with the pre-stated caveat that it cannot see a one-token context change above the stack's own
  run-to-run noise. "So there is no gross GDN/KV restore corruption; nothing finer was tested."
- The agent's recommendation: don't ship the tier. At the shipped 81.5k target it is nearly idle (kt2's tier served 0-4.9% of
  GPU misses), and it costs host memory on Kaggle (8.8 GiB minimum available locally with a 16 GiB tier; 32 GiB did not fit
  in kt1).
- **New, OPEN: identical cold prefills do not reproduce on this stack** (TV distance up to 0.36; at 25k a second-ranked
  logprob moves 2.5 nats; the top token changes in 2 of 16 cases). Cause not investigated. What would close it: one prompt
  run cold five times, then separately with RecoverSSM off (`VLLM_ARC3_GDN_RECOVERSSM=0`), MTP off and Engram cpu_offload
  off (short; one GPU slot). It bounds how far any n=1 A/B on this stack can be read.
- n=1 per arm; no no-tier 122,880 run on this stack; not run on Kaggle.

### 5.7 More context per game -- CLOSED for the host tier; other routes DEFERRED

- kt3 was this test at 14 streams, and it is refuted (5.6): the longer history does not fit the GPU pool, and the tier cannot
  add active capacity.
- Fewer streams was tried in October: findings 196f, armB_tc122k_c10 (122k target, concurrency 10), 39.55, at the bottom of
  the control band, "null at best on this harness" [checked: the 196f entry]; October's stack, n=1.
- Deferred: the remaining routes (a trim scheme that keeps prompts inside the pool, or a bigger pool) are unbuilt, and with
  no route showing a gain, nothing was scheduled before the deadline.

### 5.8 DFlash mechanism 1 -- CLOSED (refuted)

- scripts/runtime_0310/patch_dflash_draft_group.py (55e7f3e): vLLM 0.31 identifies a DFlash drafter's own KV cache group, so
  only it gets the EAGLE last-block drop (stock 0.31 identifies none for dflash and then flags every group). Hash-pinned
  (overlay kv_cache_utils.py ec59a62a -> bb793cf0); switch `ARM_DFLASH_DRAFT_GROUP=1`, dflash only, off by default.
  Pre-statement d9170b3, which predicted REFUTED from l9's own diagnostics; result 53eb0f4
  (notes/dflash2_flashnext_2026-10-31.md).
- l10 = l9 + the switch, 35.5 min on the local 6000. The warning is gone (0 vs l9's 2) and only SlidingWindow[6] carries the
  drop, but over minutes 10-30 window-exact hits are 68.9/33.9/23.3/22.9% (needed >= 85%; MTP r2/r6 88.5-94.6%) and
  generation 505/344/350/360 tok/s (0.39-0.54x MTP); acceptance 2.82-2.90, unchanged. l10 against l9 is within l9's own
  swings at n=1; mechanism 1's own cost is estimated at about 1-3 points.
- The patch stays in the harness, off by default: "Don't spend more slots on the mechanism-1 patch."

### 5.9 DFlash mechanism 2 (and 3) -- OPEN

- What drives the decay (l9, l10 and l6), from eviction forensics (scripts/dflash_sw_evictions.py, scripts/dflash_kv_reach.py)
  and vLLM source reads: **(2)** the drafter's sliding-window blocks are evicted before the follow-up request arrives (l10
  230/285 needed blocks, l9 240/270; median about 41-44 s before the lookup), so the SW group's reach falls to 0 and zeroes
  the hit on 50-110k prompts while MLA and Mamba could still serve 82-97%; **(3)** the SW group disables fine-grained
  128-token hits, so hits land on 1,664-token blocks, which accounts for the 80% start against MTP's 90%. The note's earlier
  "plain capacity" reading of l6 is corrected (MLA reach 91-94% while its hit fell to 29% and 4%).
- What would close it: candidate (a), keep each running request's drafter replay-boundary SW blocks referenced until it
  finishes, as MambaManager does for its checkpoint (2-3 blocks per request, about 42 of 1,082 at 14 streams), as one
  variable on l10 with the same window-exact gate. For (3): candidate (b), a fine-grained SW lookup, or the drafter group
  kept out of hit reconciliation. (c), a full-attention drafter KV, would fix both at about 10 KB/token (~14 GB at 14 x
  100k). All untested; each needs a 6000 slot. Unexplained: why 48 of 285 (l10) and 27 of 270 (l9) needed blocks show no
  eviction event.
- "The DFlash drafter arm is not submission-ready on this stack: generation is 0.39-0.54x MTP from minute 10."

### 5.10 Park/resume cost -- CLOSED (n=2)

- Read-only analysis of the 10-31 local park smoke; pre-statement af349d9 before the measurement, result 79e6fb7
  (notes/park_resume_cost_2026-10-31.md). All four pre-stated hypotheses survived.
- Cold resume (ar25, parked ~116 s): its first request after the resume had 3,328 of 42,795 prompt tokens cached (7.8%),
  because the cache lasted about 87 s of the park (eviction, not a prompt change: all 281 pre-park block hashes reappear in
  order). The re-prefill (24 engine steps) slowed the 11 other running requests to ~290 tok/s. Cost: about 3.3-3.6 s on its
  own turn plus about 2.85 s for each other decoding game, roughly 38 slot-seconds.
- Immediate resume (vc33, 0-0.44 s later): 93.2% cached, no measurable cost.
- Extrapolated by the agent, not measured: under `pool_park` every real resume would be cold (resumes come only after all
  110 games have started), and ~38 slot-seconds each is small against 14 x 32,400 slot-s unless conversations are much
  longer or resumes bunch. The candidate runs park off (5.1: park +0.00 at S1500 M600), so this does not bear on it.
- n=1 cold, n=1 immediate, one conversation size (~43k tokens); the local Max-Q card; cuts at 20/10 actions, not 1,500/750.

### 5.11 Load test A -- CLOSED (refuted); one of its claims corrected

- Pre-statement 7349227 before the push; result 44fc3e7 (notes/load_thread_cap_2026-10-31.md). Kaggle CPU notebook
  codywhatleymd/arc3-load-thread-cap v1 on the mounted Model v22/3 (43 files, 179,931,721,221 B, MATCH); the 4 GPU shards
  (75.9 GB) read in full per run, page cache dropped and checked at 0 B before every run; 16 of 16 runs valid.
- **REFUTED**: 32 threads 595.2/595.3/600.4 MB/s against 4 threads 557.6/564.7/565.3; all nine 32/4 pairs 1.053-1.077x
  (needed >= 1.5x). The mount levels off at ~600 MB/s from 8 threads up, and NFS RTT grows with thread count while throughput
  stays flat. 1 thread reads 219-224 MB/s, so 32 vs 1 is 2.65-2.74x (the pre-stated side rule, supported).
- **Correction [checked].** The agent's "the deployed prefetcher does not run 4 streams ... the effective concurrency is 1"
  is wrong, as notes/prefetch_readbound_check_2026-11-01.md (9e5e1ac, CL1's follow-up) found: at runtime
  harness/setup_commands.json replaces the watchdog's `read_file_into_page_cache` with an 8-reader interleaved version
  (`ARC3_PREFETCH_READERS`, default 8). I found the replacement in setup_commands.json at 8552964 (v36/v37's harness) and at
  HEAD, and its line "ARC3 parallel prefetch: watchdog reader replaced" in 8 Kaggle GPU-run logs under
  ~/kaggle_local/kaggle_runs (C2, C4, C6, C7, A2, NE, XZ, Gc). The agent's evidence (at most one big shard in flight) counts
  files, not streams. So its suggested lever, a 4-8-way parallel read of the shard being loaded, is what production already
  does; its "do not raise GPU_SHARD_PREFETCH_THREADS" stands.
- From the read-bound check (not re-checked here): 3 of 13 prefetch reports read-bound, 0 not, 10 mixed; what remains on the
  load is non-read time on big shards 2-4 (0 to ~200 s each, varying run to run), unexplained (candidates: page-cache
  eviction under host-memory pressure, loader post-processing). Its rulings: don't merge load-streams (4079d01; it breaks
  the setup patch), and leave the PLE prefix mismatch ('ple-' vs 'model-ple-*') alone, since the PLE phase is read-bound at
  the mount rate either way (the prefetcher's docstring, which says it skips those files, is still wrong).
- Not verified: the plateau on GPU sessions (other cache servers, 48-vCPU hosts); one CPU session on one server.

### 5.12 Load test B (cold vs warm GPU sessions) -- DEFERRED

- Held for the investigator's yes, because it spends GPU quota. No pre-statement exists yet [checked: nothing in notes/ for "load test
  B" or "cold vs warm"]. 5.11 ran on a CPU session, and GPU sessions use other cache servers and 48-vCPU hosts, so no load
  number from tonight comes from a GPU host. What starts it: the investigator's yes, then a pre-statement committed before the push.
  Both GPU sessions are held by the candidate and start-retry runs at this writing.

### 5.13 Runtime unpack -- OPEN (bench in progress); shipping DEFERRED past the deadline

- First agent (pre-statement d10d62b; its facts in notes/runtime_unpack_facts_2026-11-01.md, ac0d5ed): the inventory, a
  17-session Kaggle baseline (layer 100 75-209 s, median 112; layer 8 8-48 s, median 22), a 1 GiB codec sweep, the bench
  scripts, and a tree-manifest identity gate tested on a known-good and a known-bad tree. It timed no full arm.
- Two facts change the premise. The Kaggle image (9a6bcfda) ships pigz 2.8 and the harness's extract_layer uses it when it
  finds it, so Kaggle already unpacks with pigz, not single-threaded gzip (inferred from the image and the code; the harness
  does not log which decompressor ran). The image has no zstd binary (python zstandard 0.25.0 is there). Local pigz predicts
  ~35-45 s for layer 100 against Kaggle's 75-209 s, so the Kaggle unpack is likely not decode-bound (NFS small reads,
  194,558 files); that split is weakly identified.
- A scope-cut message sent to the agent's id at ~10:31 UTC started a second instance, which owns the bench, the note
  notes/runtime_unpack_2026-10-31.md and the cleanup: amendment 1 (60f9029: zstd -3 --long=27, 2 repeats, A1 dropped) and
  amendment 2 (aee0ca9, 10:49:58 UTC: A4 r1 excluded after an outside ~57 GB shared-memory spike swapped its /dev/shm inputs
  out; A3 dropped; A4, A0, A2 and A5 rerun under a new swap check). [checked 10:53 UTC: the note does not exist yet; the
  rtu-bench container is gone; /dev/shm/rtu_1101 is down to 18 GB (38 GB at 10:45); /media/ignaz/claude-extra is 97%
  full.]
- What closes the measurement: the second instance's arm timings and verdicts in that note, both repeats agreeing, the
  identity gate passed, and /dev/shm/rtu_1101 and /media/ignaz/claude-extra/rtu_1101 removed. Shipping is deferred: main
  told the investigator at 10:32 UTC "It's post-Monday work anyway". The first agent's shipping constraints, for then: a new dataset
  slug, not a new version (harness 8552964 extracts only with pigz/-z); the manifest's image, amd64_manifest_digest,
  vllm_version and patch fields byte-identical; a codec-aware validator census and an extract_layer that logs which
  decompressor ran; and at least 2 Kaggle runs or an in-session A/B, since NFS variance alone spans 75-209 s.

### 5.14 Custom-games benchmark on the Kaggle AI quota -- DEFERRED

- Never started: the workflow assigned it no agent, and notes/ has no plan or pre-statement for it [checked: grep]. It
  spends the investigator's Kaggle AI quota, so like load test B it waits for his yes; nothing in tonight's submission work depends on
  it.

### 5.15 TPU student hardening on unseen boards -- DEFERRED

- Never started: no agent, and no plan or pre-statement in notes/ [checked: grep; the only TPU hits are an October vLLM-TPU
  pricing fact check]. It is a fix direction for findings 198 (section 3, item 7: no fallback for block patterns absent from
  the public games), which stays OPEN. Reason: a hardened student would replace the shipped one, whose output item 8 showed
  bitwise identical across v8's and v36's environments tonight; it would need its own fidelity check on held-out block
  patterns and a Kaggle commit run before it could ship, and TPU time is the investigator's to spend.

### 5.16 DFlash drafter fine-tuning -- DEFERRED

- Never started: no agent. The DFlash note lists it as a "possible next lever; not needed to run" (vllm-project/speculators
  v0.9.0 trains DFlash2 online; our request logs are on-policy data). Reason, from tonight's data: the DFlash arm's measured
  limit is prefix caching (5.9: window-exact hits 22.9-68.9% over minutes 10-30 against MTP's 88.5-94.6%), while acceptance
  held at 2.82-2.90 as generation fell to 0.39-0.54x MTP. Fine-tuning raises acceptance and cannot recover the cache
  collapse, so it waits behind the KV-manager fix (5.9, candidate a).

### 5.17 Found while checking

- **F2 has reopened** [checked: `git ls-remote private`]: private's harness-fixes-2026-09-09 is at 46e233b, 52 commits behind
  the local branch before this section's commit, and pinned-round and candidate-pinned are not on private (pool-clock,
  candidate-1101 and start-retry are). The fix agent left the branch unpushed on purpose, because it carries other agents'
  commits.

### 5.18 Decisions

For Investigator:
1. **The candidate.** If its commit run passes its cut, submitting it is his decision (its pre-statement). The scored run's
   9 h clock (5.4) is unaddressed and applies to the candidate and the v37 fallback alike; whether to wait for the
   /proc/uptime anchor is part of that decision.
2. **Load test B** (5.12): yes or no; it spends GPU quota.
3. **Custom-games benchmark** (Kaggle AI quota) and **TPU student hardening** (TPU time): yes or no, and before or after
   Monday.

For the orchestrator: the /proc/uptime anchor (5.4); a c15 slot (5.5); the cold-prefill check (5.6); DFlash candidate (a)
(5.9); the wait quantile and H6 (5.2); the runtime-unpack cleanup (5.13); pushing the unpushed branches (5.17).

### 5.19 Not verified by this section

- I re-ran none of the agents' measurements or tests; their numbers are as they reported them.
- I did not read the running candidate's or start-retry's live logs, or the outputs of the completed no-stop pool-clock and
  v37 runs; their scores above come from main's 08:26 UTC handoff.
- The 753843 report is another team's probing; nothing of ours has measured the pre-start delay on a scored run.
- The deadline's UTC reading is the CLI's convention.
