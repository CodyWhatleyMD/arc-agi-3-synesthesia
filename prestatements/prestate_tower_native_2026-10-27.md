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
