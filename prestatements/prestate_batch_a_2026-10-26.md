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

## Clarification 1 (22:12 CDT, during ba1; ruled by Sakshi on Kas's question)

The invalid-run criterion says "a traceback **in the harness**". ba1's log has one `Traceback`, printed under
"sandbox process exited unexpectedly; stderr follows:": the model's own code in the sandbox child hit MemoryError
(`File "<string>"`, `_sanitize_exception`, the child's 768 MB RLIMIT_AS). That is the sandboxed model code's stderr,
not the harness. It is printed only because SYN_SANDBOX_HYGIENE logs child stderr (12a000d SB L906); the anchor
dies the same way silently (8552964 SB L863). Ruling, applied to every run of every arm:
- A traceback inside a "sandbox process ... stderr follows:" block does not count as a harness traceback.
  Everything else still does.
- Sandbox deaths are counted SYMMETRICALLY in all arms from what the model was told: tool results containing
  "Sandbox process exited unexpectedly." (identical text in 8552964 SB L863 and 12a000d SB L1088), deduplicated by
  tool call. Reported as an exploratory observation, never deciding.
- Honesty note: a partial ba1 mean (27.71, mid-run) had been relayed to me before this ruling. The ruling does not
  depend on it: it follows the pre-stated wording ("in the harness"), and the other reading would discard a Batch A
  run for an event the controls cannot log at all.

## Clarification 2 (23:35 CDT; ruled by Sakshi BEFORE reading ba1's score)

The root disk filled during ba1 (Cody, 23:29: "it already went to 0"). ba1's log stops at 23:02 mid-line at
exactly 131,072 bytes; the run continued unlogged until ~23:24, about 30 min short of a full-budget run. Its
validity criteria cannot be checked over the whole run, so ba1 is INVALID (unverifiable) and is rerun. ba2 and r5
died within seconds of starting on the full disk and never played. r2, r3, r4 and both smokes ended cleanly
("Ending Cell 12", no out-of-space errors) and stand. Added criterion, every run from now on: a run during which
the disk holding its working directory reached zero free space is invalid.

## Clarification 3 (00:10 CDT 10-27; Kaggle design if two sessions at once cannot start; decided BEFORE the retry's result)

Round 1 (control + batch-a started together) hung before BOOT on both sessions and was cancelled at ~39 min, no
scores (216ax addendum 6). Kas is testing arm-control alone (one variable). Decided now, whichever way that goes:
- If one session alone boots and two at once do not, Kaggle runs go ONE AT A TIME in the counterbalanced order
  C A A C C A (C = control, A = batch-a): each arm still gets 3 runs, the number fixed in this pre-statement, and
  each arm's mean run position is the same, so a slow drift in Kaggle's servers over the day cancels to first order.
  Paired-by-game comparison over the 3 + 3 runs, as before. The order is fixed here and not changed after a run.
- If arm-control hangs alone too, the cause is the new kernel or the arms dataset, not simultaneity; no Kaggle arm
  runs until that is fixed and this section is amended.
- A run that hangs before BOOT and is cancelled has no score and is simply re-queued in the same slot of the order.

## Clarification 4 (05:12 CDT 10-27; ruled before any Kaggle score exists)

Every run version on the quick-save-created arm kernels hung before BOOT (round 1 both arms; arm-control v4 alone).
A probe on a NEW kernel created by a run push (probe-arms-newk, run 362774583: arms dataset @ 12a000d, no SYN_*)
booted within seconds (BOOT 09:50:20 UTC, image 9a6bcfda, "switches checked: {}"). Ruling:
- Kernel identity is not part of an arm. An arm is defined by its notebook content (harness dataset and commit,
  SYN_* env, budget, model, tower, runtime), as in the table above.
- probe-arms-newk counts as slot C1 of C A A C C A, provided its notebook differs from the staged arm-control only
  in label strings (title, ARM_NAME/ARM_KERNEL, banner, About text), checked by a cell-by-cell diff while it runs;
  otherwise it is cancelled and does not count.
- Every remaining run (C and A) goes to a kernel created by a run push, never a quick save first. A run counts if its
  notebook matches its arm's staged notebook up to labels and its BOOT gates pass (GPU image, switches-checked line).

## Clarification 5 (05:14 CDT 10-27; before any Kaggle score)

Clarification 3's serial order applied only IF one session booted alone and two at once did not. That condition
did not hold: arm-control hung alone, and the cause was the quick-save-created kernels (Clarification 4); T1 and T2
ran in parallel and T2 booted. So the original design stands: Kaggle rounds are same-time pairs, (C1 + A1),
(C2 + A2), (C3 + A3), each pair pushed together on fresh run-push kernels. C1 = probe-arms-newk (diff: labels only);
A1 is pushed as soon as the second session frees, so round 1's pair starts hours apart. That is reported, and the
analysis stays paired by game over all runs of each arm, as pre-stated.

## Clarification 6 (05:55 CDT 10-27; amends Clarification 4's stated CAUSE only, before any Kaggle score)

T1 (probe-anchor-newk, run 362774566: a run-push kernel, the anchor dataset) hung (empty log at 61 min) while T2 (a
run-push kernel, the arms dataset) booted, and the anchor dataset booted in v36. So "quick-save-created kernels hang"
is WRONG: neither creation method, dataset nor simultaneity separates hangs from boots. The cause is unknown; a slow
first copy of v22/3 onto some GPU servers fits but is unconfirmed. Clarification 4's rulings are unchanged (kernel
identity is not part of an arm; C1 = probe-arms-newk). Cutoff for a run with no BOOT line: 40 min from RUNNING,
kept, because the observed boots are ~0, ~19 and ~25 min (the 10-25 first attach), and max + 50% ~ 38 min.
Timings per run go in notes/kaggle_run_timings.csv.

## Clarification 7 (07:20 CDT 10-27; slot filling under frequent hangs, before any Kaggle batch-a score)

7 of 9 Kaggle sessions have hung before BOOT (both arm configs; not arm-specific). Strict same-time pairs leave a
GPU slot idle while one member re-rolls. Rule from now on: a free slot takes a run of whichever arm has FEWER
completed runs (control on a tie); stop when each arm has 3. This keeps both arms' runs interleaved in time, which
is what pairing was for. Analysis unchanged (per game over all runs of each arm); each run's start time is
reported so the interleaving can be inspected. C1 = probe-arms-newk is complete.
