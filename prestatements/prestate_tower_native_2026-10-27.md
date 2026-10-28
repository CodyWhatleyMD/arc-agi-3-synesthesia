# Pre-statement: student embeds vs the native vision tower, same harness, same hardware (written 2026-10-27 ~18:35 CDT, before any run)

Cody, 18:27: "for the thesis - don't we need to show that?" Yes. Today's on/off replication tested the visual channel
against nothing (notes/tower_onoff_local_result_2026-10-27.md: −3.62 [−9.89, +3.22] without it, not resolved, leaning
toward the channel). The Synesthesia claim proper is that the 18.2M student standing in for the 449M native tower is
an adequate substitute. The only evidence is F208b (native 49.51 vs student 46.26, n=2 each, an 8-GPU BF16 box, not
our harness, retracted as a ranking). This runs that comparison here.

## Arms
- **STUDENT (control for this test):** the v8 anchor notebook (f9af78d9), the board as 1,024 image_embeds tokens from
  the student tower; r2, r3, r4 (9,300 s, valid). n=3, already run.
- **NATIVE (treatment):** the anchor built with `--board-channel native`: ARM_B_STUDENT_TOWER=0 so the harness takes
  its own PNG path (vision_context.current_grid_image_part -> image_url, 16 px per cell = 1,024 x 1,024 px), with the
  server allowed one image per prompt (ARM_LIMIT_MM image:1) and max_pixels 1,048,576 so the native tower produces
  1,024 tokens per board: MATCHED GEOMETRY. MULTIMODAL_CONTEXT stays current_grid; the system prompt's image section
  is identical. The evidence gate flips: ≥1 image_url part at 1,024 tokens and ZERO image_embeds parts; the request
  logs are checked for the same after the run. Nothing else changes. Tags na1, na2, na3; 9,300 s; GPU 1; disk-gated.
- One variable: who turns the board's pixels into 1,024 tokens, the student (CPU, 18.2M) or the native tower (GPU,
  449M). Everything downstream of the tokens is the same code.

## Known cost of the treatment, pre-stated as a covariate, not a confound to hide
The native tower must be resident on the GPU, so the KV pool is smaller than the student arm's 1,501,360 tokens. The
pool size is read from each NATIVE log at boot and reported beside the result. If the native arm loses, the reader
must be told how much pool it gave up; if it wins, the student's memory saving is the thing it buys for nothing.

## Primary outcome
Mean public-25 score, NATIVE (n=3) − STUDENT (n=3), scripts/compare_arm_groups.py, paired-by-game bootstrap 95% CI.
Resolved if the CI excludes 0; otherwise NOT RESOLVED at n with the interval. Both tails: native better = the student
lost fidelity that matters; native worse or equal = the student is at least an adequate substitute at 1/25 the size.
Levels, actions per job-second, slopes over summaries 1-10 (play min 10-100) and the 60/90/100 checkpoints as in the
on/off pre-statement (secondary / exploratory). The stable top four and bottom five per game, exploratory.

## My prior (stated so it can be wrong)
NOT RESOLVED at 3 vs 3; |delta| < 4. If anything resolves I expect NATIVE slightly ahead (it is the teacher), by less
than the on/off gap, with the pool cost showing as fewer actions late in long games.

## Invalid-run criteria (decided before any score is read)
Any harness traceback outside a 'sandbox ... stderr follows:' block; any HTTP 400 (an image_url rejected by the
server is exactly that); disk < 3 GB during the run; ARM banner or the board-channel check missing; the flipped
evidence gate failing (an image_embeds part, or no image_url part, means it is not the NATIVE arm); fewer than 25
games started; job budget not 9,300 s; the native tower's token count per board not 1,024 (geometry mismatch). An
invalid run is replaced, not patched.

## What this does not test
The hidden set; Batch A; the channel vs nothing (today's other test). It tests the student against its teacher.

## Clarification 1 (19:20 CDT; na1 stopped at 19:19, no score read)
- na1 is INVALID: 33,617 requests in 45 min, 33,604 rejected HTTP 400. The harness keeps TWO image_url boards per
  request (the current and the previous), and ARM_LIMIT_MM image:1 made the server reject every two-board request;
  the harness retried in a loop. My error: I set the limit from the student arm's "one board" picture without
  measuring the PNG path's own history policy. The chain was halted before na2.
- The confound a side agent flagged, now measured: the shipped STUDENT arm carries a median of 13 boards per request
  (min 1, max 48; r2's 2,817 requests) because the history stripper recognises only text and image_url parts
  (vision_context.py:164) and image_embeds parts are invisible to it; the PNG path keeps 2 (na1: median 2, max 2).
  "Only the encoder differs" was false as designed: the arms would also have differed in board history, 13-48 vs 2.
- This also annotates today's on/off result: the ON arm there was the shipped student arm WITH its 13-48-board
  history; the channel it measured includes that history. Noted in the on/off result file.
- Redesign, before any further run: MATCHED HISTORY. Both arms keep the harness's designed TWO boards per request.
  NATIVE: ARM_LIMIT_MM image:2 (the server accepts two), PNG path as before. STUDENT-2: a new harness switch that
  applies the same two-board policy to image_embeds parts (the fix the stripper always needed), built into its own
  dataset like faab14c, default off = shipped behaviour. r2/r3/r4 are NOT the controls for this test (they carry
  13-48 boards); the test is three STUDENT-2 runs vs three NATIVE-2 runs, six runs, ~16 h. The shipped 13-48-board
  student arm vs STUDENT-2 is a separate, exploratory question (the history window), not decided here.
- Primary outcome, prior, gates unchanged, with the gate's image_url count now "max 2 per request" for NATIVE and
  "max 2 image_embeds per request" for STUDENT-2, both checked in the request logs after each run.

## Clarification 2 (19:25 CDT; supersedes the "two-board policy" in Clarification 1; still no score read)
- Measured in the request logs: boards per request GROW identically on both paths. r2 (student, ar25): 1, 1, 2, 2,
  3, 4, 4, 5, 6, 6, 7, 8 ... (median 13, max 48 over the run). na1 (native, ar25): 1, 1, 1, 2, 2, 2 ... stuck at 2
  because every request carrying two image_url parts was rejected (image:1) and retried. There is NO per-type history
  policy: the vision_context comment I cited ("his transcript renderer only knows text and image_url") is about the
  transcript LOG, not the model's history. The confound I described does not exist; the bug does.
- Design restored to the original: NATIVE differs from STUDENT only in who encodes the board, with the server limit
  raised so the native arm can carry the same history: ARM_LIMIT_MM image:64 (a bound above the student arm's
  observed max of 48; the request logs' per-request maximum is recorded for every NATIVE run and must stay ≤ 64 and
  show no HTTP 400). Controls r2, r3, r4 as pre-stated. Three NATIVE runs: na1b, na2b, na3b.
- Covariate: the KV pool under image:64 is read from each log (na1 under image:1 measured 1,440,080). vLLM profiles
  the encoder per batch, not per limit, so the pool should not fall much further; whatever it is, it is reported.
- The on/off annotation stands: the ON arm (and this test's STUDENT control) carries 1-48 boards of history by the
  harness's accumulation, and so will NATIVE.
