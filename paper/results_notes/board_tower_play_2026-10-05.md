# Can the model PLAY ARC-AGI-3 with distilled vision? -- first game-level test of the board tower
2026-10-05, on the GCP twin. Pre-registration: `runs/board_tower_play/PREREGISTERED.md` (written before
any arm ran, with an addendum for the budget change and a declaration of replication block 2).

## The one-line answer

**UPDATED by block 3 (the real-budget run) -- read that section; the sections below it describe
blocks 1-2, whose 22-action budget was too small to produce a signal.** At 160 matched actions:
the model plays fine on distilled vision (27 levels / 10 runs, 9/10 clearing, provably live), the
distilled student BEATS the real tower on every measure (+6 levels, p = 0.269), and **the text
baseline beats both image arms on levels (30)** -- while the tower arm reaches 90% of text's levels
on 63% of the tokens and 65% of the wall clock. Which arm wins depends on whether actions, tokens or
time is the scarce resource. Nothing is statistically significant at n=10.

## The original one-line answer (blocks 1-2, 22 actions -- budget too small, see block 3)

**Yes.** The 27M student's `image_embeds` drive real play: **11 levels over 12 game-runs, 9/12 runs
scored**, with the path provably live (165/165 requests carried an embeds part, 0 carried a PNG,
61 distinct uuids, 0 fallbacks). Against the real vision tower at the SAME token count it is
**indistinguishable** (-2 levels, p = 0.72). Against the text baseline it is **+4 levels** pooled, but that is
not significant (p = 0.22) and it comes entirely from block 1 -- in block 2 tower and text tie at 4. The only nominally significant contrast in the table is real pixels
at 4096 tokens over text (+6, p = 0.045), and it does not survive correction for six tests.

Separately measured, as a matched-pair boot: **excluding the tower (`--enable-mm-embeds` +
`--limit-mm-per-prompt '{"image":0,"video":0}'`) works, keeps embeds, closes the pixel path, and buys
back 0.85 GiB of weights and +44,564 KV tokens (+10.3% pool, 13.24x -> 14.60x concurrency)** -- a real
deployment saving the play experiment could not see, because the tower was resident in every arm.

**The result is NOT negative for the tower.** It is "the distilled path works and is as good as the
thing it approximates, at an n that cannot resolve the remaining differences."

## The table

12 game-runs per arm = 2 independent blocks x 2 passes x 3 games. Budget matched in ACTIONS
(22 per game-run, so 264 actions in every arm) rather than wall clock, so the comparison is perception
and not throughput. Same server, same checkpoint, one variable per arm.

| arm   | img tok/board | runs | **LEVELS** | runs>0 | ar25 | lp85 | vc33 | actions | TAAF% | s/action | gen tokens |
|-------|--------------:|-----:|-----------:|-------:|-----:|-----:|-----:|--------:|------:|---------:|-----------:|
| text  | 0    | 12 | **7**  | 7  | 0 | 4 | 3 | 264 | 1.04 | 15.4 | 248,499 |
| png4  | 66   | 12 | **11** | 9  | 1 | 5 | 5 | 264 | 2.75 | 16.0 | 258,743 |
| png32 | 4098 | 12 | **13** | 11 | 4 | 6 | 3 | 264 | 3.21 | 16.0 | 236,600 |
| tower | 4098 | 12 | **11** | 9  | 2 | 5 | 4 | 264 | 2.74 | 15.1 | 211,661 |

`png4` = Duck's real PNG at 4 px/cell (what Kaggle ships). `png32` = the same renderer at 32 px/cell,
which the real tower turns into 4096 tokens -- the token-matched ceiling and the thing the student was
distilled to imitate. `tower` = the student's vectors through `--enable-mm-embeds`.

Stratified exact permutation test on total levels (strata = block x game, 46,656 permutations):

| contrast | observed | p |
|---|---:|---:|
| **tower - png32** (the one-variable comparison) | **-2** | **0.718** |
| tower - text  | +4 | 0.222 |
| tower - png4  |  0 | 1.000 |
| png32 - text  | +6 | **0.045** |
| png32 - png4  | +2 | 0.718 |
| png4  - text  | +4 | 0.125 |

Per block, so nobody has to take the pooling on trust -- levels (text / png4 / png32 / tower):

| block | text | png4 | png32 | tower | ordering |
|---|---:|---:|---:|---:|---|
| 1 | 3 | 4 | **7** | **7** | png32 = tower > png4 > text |
| 2 | 4 | **7** | 6 | 4 | png4 > png32 > text = tower |
| pooled | 7 | 11 | **13** | 11 | png32 > png4 = tower > text |

**The two blocks almost reverse each other.** Block 1 has tower at 7 and png4 at 4; block 2 has tower
at 4 and png4 at 7. Nothing about the ordering of the three image arms is stable at this n, and the
only thing both blocks agree on is that the image arms as a group are not worse than text. Anyone
reading the pooled row as a ranking is over-reading it; this is the honest shape of n=6 per block.

## Proof the tower path was actually live

From Duck's OWN request log, not our counters (`runs/board_tower_play*/tower/*requests.jsonl`):

| arm | requests | with image_embeds | with image_url | distinct uuids | PNG fallbacks |
|---|---:|---:|---:|---:|---:|
| tower | 165 | **165** | **0** | **61** | **0** |
| png32 | 180 | 0 | 180 | - | 0 |
| png4  | 212 | 0 | 212 | - | 0 |
| text  | 212 | 0 | 0   | - | - |

Plus: a pre-flight request (a valid 64-token embeds part) had to return 200 or the arm REFUSED to
start; the hydration step re-hashes the board and asserts the uuid matches before every send, so a
stale uuid cannot reach the server; the student built 104 board parts and 4.61 GB of embeds went over
the wire; and the server's own `prompt_tokens` sat at a median 18,620 and max 29,696, i.e. the 4,098
image positions were allocated and consumed. The live-server identity of the two 4096-token arms was
also checked directly: the same board gives `prompt_tokens` 4172 through png32 and 4172 through tower.

## Corrections to the premise this task was given

1. **The 4096-token student is 27.2M parameters, not 18.2M.** 18,221,696 is the `ckpt_px16`
   (1024-token, cell_patch=2) student; the 4096-token one is 27,247,232.
2. **Its held-out cosine is 0.9099, not 0.927.** 0.9266 is an INTERMEDIATE eval over the first 64 eval
   boards, which are all `cd82` -- and it is also the metric `best.pt` was selected on, so model
   selection used a one-game proxy. The full 500-board / 5-game eval of `best.pt`, computed here:
   **cos_mean 0.9099**, p05 0.7411, min 0.127; per game cd82 0.9264, sk48 0.9152, re86 0.9157,
   s5i5 0.9061, m0r0 0.8861. (`summary.json`'s `final_eval` 0.9052 is of the LAST weights, not best.pt.)
   Written to `runs/board_tower_play/student_best_full_eval.json`. The 1024-token student's headline
   0.8904 is the same cd82-only-64 statistic, so the 0.9266-vs-0.8904 comparison is at least like-for-like.
3. **Stock Duck attaches exactly ONE image per request, not two.** `vision_context.py` in
   `/home/ignaz/duck-harness` (what `ab_local.py` actually imports, 82 lines) has only
   `current_grid_image_part`. The diff image / animation images / game-over images are the FRANZEN fork
   (`runs/route_a/franzen_verbatim/...`, 300+ lines, gated on `ARC3_DIFF_IMAGE` which defaults off).
   So there was no previous-frame image to decide about: every arm here sends the current board and
   nothing else. Had there been one, the student could not have produced it -- the diff render uses an
   off-palette navy for unchanged cells and the student only models boards of the 16 engine colours.
4. **`export_embeds.py` supported the 4096 student with no changes, as stated** -- and it was not
   edited. It is being modified by another agent, so a frozen snapshot of
   `scripts/board_tower/{common,model,export_embeds}.py` + `notebooks_duck/synth_tokens/synth_embeds.py`
   was taken and imported via `BT_REPO_ROOT`; the sha256 of each is in every arm's log.

## Configuration -- and why the tower arm's cost is the PESSIMISTIC case

Stated, not inferred, because it bounds what the cost numbers mean:

* **ONE server session for all eight arm-runs.** Container `flashnext-rescurve` was created at
  04:20:20Z and removed at 05:48:33Z; `run_play_ab.sh` contains no server-start code (it only curls
  `/v1/models` for readiness); and the gap between consecutive arms was **0 s** within a block and 43 s
  between blocks, against a measured server boot of 209-345 s. No arm got its own boot.
* **The real 448M vision tower was RESIDENT throughout, including during the tower arm.** The server
  was launched from `/kaggle-twin/rc/work/in_container.sh` with no `--language-model-only` and no
  `image:0` limit, and the png32/png4 arms -- which ran in the same process, between the two tower
  blocks -- demonstrably turned 2048x2048 and 256x256 PNGs into 4096 and 64 image tokens. So the tower
  arm did **not** avoid the tower's weights, its profiling headroom, or its encoder-cache reservation.
  It skipped exactly one thing: the ViT forward pass. **"a 27M student replaces a 448M ViT forward" is
  a compute claim, not a deployment claim**, and the deployment saving the student exists for is
  invisible to this experiment.
* **The student ran on a DIFFERENT MACHINE from the server**: the local workstation's idle RTX PRO 6000
  Max-Q (`CUDA_VISIBLE_DEVICES=1` under `CUDA_DEVICE_ORDER=PCI_BUS_ID`; the logged `cuda:0` is the
  masked index), while the served model was on the twin's RTX PRO 6000 **Server Edition**. So the
  12.1 s of student compute contended with nothing -- and that is also unrepresentative: in a Kaggle
  submission the student would share the one card with the server.

## Can vLLM serve `image_embeds` with the vision tower NOT loaded?

**Yes -- but via `--limit-mm-per-prompt image=0`, not `--language-model-only`.** Source read of the
served runtime (`/media/ignaz/model-storage-2/flashnext_runtime/dist-packages/vllm`, the exact tree the
twin serves); **not booted**, so this is a code claim, not a measurement.

`--language-model-only` is the wrong lever and would have made this a negative result: it does drop the
tower (`self.visual = StageMissingLayer("vision_tower")`, `models/qwen3_8_flash_next/nvidia/model.py:858-864`;
`skip_prefixes=["visual."]`, `:996`) but then **hard-refuses embeddings** --
`raise ValueError("Qwen3.8-Flash-Next language_model_only does not accept multimodal embeddings")`,
`model.py:933-936`.

The supported path is `--enable-mm-embeds` together with `--limit-mm-per-prompt '{"image":0,"video":0}'`,
and it is a first-class, deliberately-built code path:

1. `MultiModalConfig.enable_mm_embeds`'s own docstring (`config/multimodal.py:123-133`): *"When enabled
   with `--limit-mm-per-prompt` set to 0 for a modality, precomputed embeddings skip count validation
   for that modality, **saving memory by not loading encoder modules** while still enabling embeddings
   as an input."*
2. Flash-Next builds its tower inside `self._mark_tower_model(vllm_config, {"image","video"})`
   (`model.py:870`), and `_mark_tower_model` (`model_executor/models/interfaces.py:300`) wraps
   construction in `no_init_weights(...)` iff
   `all(mm_config.get_limit_per_prompt(m) == 0 for m in modalities)` (`interfaces.py:336`).
3. `no_init_weights` with `targets=None` enters `torch.device("meta")` -- *"prevent weight
   initialization from using device memory"* (`model_executor/models/utils.py:728`, meta at `:750`). The 448M
   visual params (~0.9 GB bf16) are therefore never allocated, and `self.visual` becomes a
   `StageMissingLayer`.
4. `AutoWeightsLoader._load_module` returns immediately for a `StageMissingLayer` (`utils.py:316-323`),
   so the checkpoint's `visual.*` tensors are skipped with no unexpected-key error.
5. `MultiModalRegistry` keeps the MM machinery alive on purpose, with the comment *"If enable_mm_embeds
   is True, we still need MM infrastructure to process pre-computed embeddings **even though encoder
   won't run**"* (`multimodal/registry.py:131-145`), and both validators skip the count check for
   `*_embeds` at limit 0 (`multimodal/processing/context.py:475-488`, `entrypoints/chat_utils.py:651-660`).
6. `_process_image_input`'s embeds branch touches only `self.visual.dtype` and
   `self.visual.spatial_merge_size` (`model_executor/models/qwen3_vl.py:2239-2246`),
   which `StageMissingLayer.__getattr__` (`utils.py:685`) delegates to the meta module; the tower is
   never **called** (`__call__` raises, `utils.py:688`), so the pixel path is dead by construction, which is exactly
   what an embeds-only server wants.

**So the tower's deployment case is live, and this experiment measured the configuration least
favourable to it.**

### MEASURED: the matched-pair boot (06:22-06:31Z, second VM session)

Two boots of the SAME container image, SAME model, SAME everything, with `in_container_noimg.sh`
generated from `in_container.sh` by a script so it could not drift -- **exactly one functional line
differs**, the addition of `--limit-mm-per-prompt '{"image":0,"video":0}'`. Both boot logs are kept on
the twin (`/kaggle-twin/rc/out/server_final_boardtower.log`, `.../server_noimg.log`).

| boot-log quantity | tower LOADED (the play run) | tower EXCLUDED (limit 0) | delta |
|---|---:|---:|---:|
| Model loading took | **71.67 GiB** | **70.82 GiB** | **-0.85 GiB** |
| encoder profiling | "Encoder cache will be initialized with a budget of **16384 tokens**, and profiled with **1 image items of the maximum feature size**" | "**Skipping encoder profiling for embedding-only mode** (all modality limits=0 with enable_mm_embeds=True)" | pass skipped |
| Available KV cache memory | **12.51 GiB** | **13.8 GiB** | **+1.29 GiB** |
| GPU KV cache size | **433,848 tokens** | **478,412 tokens** | **+44,564 (+10.3%)** |
| Max concurrency @ 32,768 tok | 13.24x | 14.60x | +1.36x |
| init engine (profile/KV/warmup) | 29.37 s | 19.99 s | -9.4 s |

The engine confirms it read the flag: `non-default args: {... 'limit_mm_per_prompt': {'image': 0,
'video': 0}, 'enable_mm_embeds': True ...}`.

The **-0.85 GiB weights delta matches the tower exactly**: the checkpoint's recorded
`n_visual_params = 448,931,056` in bf16 is 0.836 GiB. So the 448M tower really is absent, not merely
unused.

**Runtime confirmation on that server** (`scripts`-side probe, all three on the live limit-0 server):

| request | result |
|---|---|
| text (LM alive control) | **200**, prompt_tokens 4174 |
| **`image_embeds` from the student** | **200**, prompt_tokens 4143, 28.0 MB body -- and it read the board correctly: *"green, (0,0), 64x1 / red, (8,8), 12x12 / blue, (44,36), 8x20"*, exact on all three blocks |
| **a real PNG (negative control)** | **HTTP 400** `"At most 0 image(s) may be provided in one prompt. (parameter=image)"` |

So: **embeddings accepted, pixel path closed, LM intact.** Note honestly that the PNG rejection is a
frontend COUNT validation, not a tower error -- it proves the pixel path is shut, and the weights
evidence for the tower's absence is the 0.85 GiB delta above, not the 400.

### What drops and what does NOT -- and why this is +1.29 GiB and not tens of GiB

This is the part that corrects my own earlier reading of `encoder_budget.py`:

* **The encoder CACHE sizing does NOT drop.** `encoder_compute_budget` and `encoder_cache_size` are
  computed over `active_modalities = tower_modalities | embed_only_modalities`, with the explicit
  comment *"Encoder budget is computed from all active modalities (including embedding-only ones that
  need encoder cache space)"* (`multimodal/encoder_budget.py:122-128`). Precomputed embeddings still
  occupy encoder cache, so that 16,384-token budget survives limit 0.
* **What drops is the tower's weights and the encoder PROFILING FORWARD.**
  `EncoderRunner.profile_encoder_cache` returns early when there are no tower modalities
  (`v1/worker/gpu/mm/encoder_runner.py:107-112`); the with-tower path instead runs a real dummy forward
  *"of the maximum feature size"* (`:119-126`). That dummy forward is the activation peak, and it is
  the thing that **scales with `--mm-processor-kwargs max_pixels`**.
* **Hence the size of the prize is configuration-dependent.** This server sets NO `max_pixels`
  override, so its profiling peak was modest and the total recovery is 0.85 GiB (weights) + ~0.44 GiB
  (profiling headroom) = **1.29 GiB, i.e. +10.3% KV pool**. A server configured with a large
  `max_pixels` -- the configuration in which a single `max_pixels` change was once observed to move the
  KV pool from 9.31 to 62.97 GiB -- is profiling a much larger dummy image, and skipping that pass
  should recover correspondingly more. **That last step is an inference from the code, not a
  measurement**: pricing it needs one more boot with the `max_pixels` override (~6 min, ~$0.20).

**Verdict for the programme.** On the configuration we actually ship, excluding the tower is worth
**+44,564 KV tokens (+10.3%) and +1.36x concurrency, for free, with embeds still working** -- real but
not transformative. It is a genuine deployment saving the student unlocks and the play experiment could
not see; it is not by itself "the reason to do this at all" at these numbers.

**The "tens of GiB" figure is RETRACTED.** It was quoted internally before this measurement and it does
not survive it. State the memory benefit of excluding the tower as **~0.85-1.29 GiB**: 0.85 GiB of
tower weights plus a profiling-headroom delta that depends on `max_pixels`. The 9.31 -> 62.97 GiB KV
swing that motivated the larger figure came from a server configuration we do not ship, with a large
`max_pixels`. **A one-line `--mm-processor-kwargs {"max_pixels": N}` cap captures most of that saving
without a student at all**, and the leading public stack already does exactly that
(`max_pixels 65536`). So the memory argument is not a reason to prefer the student; the student has to
be justified on perception, not on VRAM.

## What 4096 tokens per board actually costs

Affordable -- but only with a history window, and only measured with the tower loaded anyway (above).

* **4,098 prompt tokens per board = 12.5% of the 32k window.** Context peaked at 29,696 / 32,768
  (91%) and there were **0 context overflows in any arm**.
* **A window is mandatory, not an optimisation.** Stock Duck never strips history images. At 4,098
  tokens each, accumulation overflows 32k inside ~6 turns and Duck's "recovery" is to delete its own
  history. Every image arm here therefore ran `BT_IMAGE_KEEP=1` (exactly one board image per request).
  This is a deviation from what Kaggle ships and it is applied identically to png4/png32/tower.
* **28.0 MB of base64 per request**, 4.61 GB over the experiment. Over the GCP IAP tunnel that is
  ~1.4 s at ~20 MB/s (install numpy into gcloud's bundled python or it is far slower). Co-located it
  would be loopback.
* **Student compute is negligible: 105 forwards, 12.1 s of GPU total (~0.115 s/board)** on an
  otherwise-idle card, 110 MB of weights.
* **Throughput: a wash in wall clock, and the SLOWEST image arm per generated token.** Per-arm wall
  clock for a whole 6-game block: tower 1150 s, png32 1067 s, png4 1198 s, text 1085 s -- a 6.0%
  spread, which is the same magnitude this note calls noise elsewhere, so no arm is meaningfully
  faster or slower end to end. Per GENERATED TOKEN the tower arm is the slowest of the four:
  **52.9 tok/s vs png32 55.8, png4 61.4, text 61.1** (generated tokens / summed per-game-run wall
  clock). Its lower s/action (15.15 vs 16.05) is therefore NOT speed -- the model simply emitted 11%
  fewer tokens in that arm (211,661 vs png32's 236,600). An earlier draft of this note said "tower was
  the fastest arm"; that was wrong and is withdrawn.
* **A trim-estimate fix was required for fairness.** Duck estimates a request as
  `len(json.dumps(payload))//3` x1.15, i.e. it counts an image by its BASE64 LENGTH: a png32 board
  measures ~16,375 estimate units against a real 4,098, and a png4 board ~5,762 against a real 66.
  Left alone, png32 would have had its text history evicted on arithmetic while tower (reference part,
  ~240 bytes) would not. All three image arms now charge every image part its real cost
  (PNG via its IHDR + vLLM's `smart_resize` rule, verified exact at 4/8/16/32 px/cell; `image_embeds`
  as n_pos+2). Without this the png32 arm would have been silently handicapped.

## Predictions vs outcomes

| # | prediction | outcome |
|---|---|---|
| P1 | not all zeros | **right** -- every arm scored on lp85 and vc33 |
| P2 | text >= tower | **WRONG** -- tower +4 levels over text (p = 0.22) |
| P3 | tower within +-1 of png32 | **close, slightly wrong** -- -2 pooled (0 in block 1, -2 in block 2) |
| P4 | png4 <= png32 | **right** -- 11 vs 13, not significant |
| P5 | tower is the slowest arm | **RIGHT on the measure that means anything** -- slowest of the four per generated token (52.9 tok/s vs 55.8 / 61.4 / 61.1). It only *looked* wrong on wall clock, where the 6.0% spread is noise and the tower arm's lower s/action comes from the model emitting 11% fewer tokens, not from going faster. Scored WRONG in the first draft of this note on the wall-clock reading alone |
| P6 | arms not separable below ~2 levels | **right** -- only png32-text reaches p<0.05, and it dies under Bonferroni (a = 0.0083) |


## BLOCK 3 -- THE REAL-BUDGET RUN, and it changes the answer

Blocks 1-2 capped runs at 22 actions, below the median actions-to-first-cleared-level (23). Block 3
(`runs/board_tower_play_real/`) re-ran **tower / png32 / text at 160 matched actions** -- 1.48x the
corpus level-1 maximum of 108 -- on **3 trained + 2 HELD-OUT** games, 2 passes, 10 game-runs per arm,
one server session, tower resident. Pre-registration + an appended correction:
`runs/board_tower_play_real/PREREGISTERED.md`.

### HEADLINE: does the student GENERALISE, or has it memorised its training games?

This is the question that decides whether the board-tower line has a future, so it goes first.
3 trained games (vc33, lp85, ar25) vs 2 HELD OUT of the student's distillation set (cd82, m0r0);
`holdout_games` in the targets manifest is cd82/m0r0/re86/s5i5/sk48. Note png32 and text do not use
the student at all -- "held out" is a property of the STUDENT, so those two arms are the controls that
show how hard the games are in themselves.

| arm | TRAINED levels | TRAINED med a2f | **HELD-OUT levels** | **HELD-OUT med a2f** |
|---|---:|---:|---:|---:|
| text  | 23 | 15.5 | **7** | 60.5 |
| png32 | 17 | **8.5** | **4** | 47.0 |
| tower | 22 | 12.0 | **5** | **22.0** |

Per-run held-out actions-to-first-clear:
`text cd82:115, cd82:81, m0r0:25, m0r0:40` | `png32 cd82:61, cd82:>160, m0r0:32, m0r0:47` |
`tower cd82:27, cd82:>160, m0r0:19, m0r0:22`

**The student does not collapse off its training distribution.** On games whose boards it never saw
it clears the first level in a median **22 actions, against the real tower's 47 and text's 60.5** --
and it is the FASTEST of the three arms there, while on the trained games it is the real tower
(png32, 8.5) that is fastest and the student is second. If the student had merely memorised its
training boards, the held-out column is where that would show as a collapse; instead the ordering
inverts in the student's favour.

**What this is NOT.** Three clears per arm on held-out. cd82 pass-0 never cleared in either image arm.
On held-out LEVELS text still leads (7 vs 5 vs 4), so the student is fastest to the first clear but
does not accumulate the most. Two held-out games, two passes each, no significance anywhere
(tower - png32 held-out: +1 level, p = 1.000). This is an absence of evidence for memorisation, which
is the weakest form of the claim that still matters -- a collapse would have been visible at this n,
and there is none.

### Then: the result depends on which budget you match, and that IS the finding

| arm | img tok | **levels** | runs>0 | trained | HELD OUT | median a2f | actions | gen Mtok | arm wall | **lv/Mtok** | **lv/arm-hour** |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **text** | 0 | **30** | **10/10** | 23 | 7 | 22.5 | 1563 | 2.181 | 2.50 h | 13.8 | 12.0 |
| png32 | 4098 | 21 | 9/10 | 17 | 4 | 21.0 | 1497 | 1.566 | 2.51 h | 13.4 | 8.4 |
| tower | 4098 | **27** | 9/10 | 22 | 5 | **18.0** | 1600 | **1.374** | **1.62 h** | **19.6** | **16.7** |

| budget definition | ordering |
|---|---|
| matched ACTIONS (the pre-registered primary) | **text 30 > tower 27 > png32 21** |
| per GENERATED TOKEN | **tower 19.6 > text 13.8 > png32 13.4** |
| per WALL-CLOCK HOUR (what Kaggle actually constrains: a 9 h notebook) | **tower 16.7 > text 12.0 > png32 8.4** |

Stratified exact permutation test on total levels (strata = game):

| contrast | all | trained | HELD OUT |
|---|---|---|---|
| tower - png32 | **+6, p = 0.269** | +5, p = 0.333 | +1, p = 1.000 |
| tower - text | -3, p = 0.664 | -1, p = 1.000 | -2, p = 0.833 |
| png32 - text | -9, p = 0.097 | -6, p = 0.278 | -3, p = 0.500 |

**Nothing is significant.** At n=10 per arm, with p >= 0.097 everywhere, no contrast survives.

### What this does and does not say

1. **The image route does NOT beat text on levels at a matched action budget.** text scored 30 to the
   best image arm's 27 and was the only arm to clear a level in **10/10** runs. This is the negative
   result, and it is the opposite of what blocks 1-2 suggested (where the image arms led). An ordering
   that flips between a 22-action and a 160-action budget is a budget artefact in one of the two, and
   the 160-action one is the defensible budget.
2. **But text buys that with 59% more generated tokens and 54% more wall clock.** The tower arm
   produced 90% of text's levels from **63% of the tokens** and **65% of the wall clock**, so on a
   TIME budget -- the budget Kaggle actually imposes -- the tower arm is ahead by 39%. Which arm
   "wins" is therefore a function of which resource is scarce, and that should be stated in the paper
   rather than resolved by picking the flattering normalisation.
3. **tower beats png32 on every single measure**: +6 levels, faster to first clear (18 vs 21),
   half the analyzer failures (9 vs 18), 35% less wall clock, 12% fewer generated tokens. So the
   distilled 27M student does not merely approximate the real 448M tower acceptably -- on this run it
   dominates it. Still not significant (p = 0.269), and the honest reading is "no evidence the student
   is worse, some evidence it is better."
4. **The student generalises to boards it never trained on.** On the two HELD-OUT games it scored
   5 levels to png32's 4, and reached first clear FASTER than the real tower on both
   (cd82 27 vs 61; m0r0 22/19 vs 47/32). One held-out game (cd82) returned 0 levels in one pass for
   both image arms but 2 in the other, and text got 2+2 there. This is the memorisation test and the
   student passes it -- at n=2 passes x 2 games, which is very little.

### Proof the tower path was live in block 3
**831 of 850 requests carried an `image_embeds` part; 0 carried an `image_url` part; 333 distinct
uuids; 0 PNG fallbacks; 23.24 GB of embeds on the wire; 405 student forwards in 45 s of GPU.** The 19
requests without an embeds part are the ones where Duck's trim had emptied the history (see below), so
they carried no user message at all and therefore no image.

### Two defects this budget exposed that 22 actions had hidden
* **Duck empties its own history and the server rejects the request.** At 160 actions the trim reaches
  the state tool_agent.py warns about -- history drained to the system prompt alone -- and the server
  answers `400 "No user query found in messages."` Counts: **text 19, png32 17, tower 7**. It is WORST
  in the text arm, because with no image the text history grows until the trim must drain it. Blocks
  1-2 saw none of this (0 context overflows at 22 actions). Context-overflow events: text 2, png32 5,
  tower 3.
* **One png32 run WEDGED and was cut by the per-game clock.** png32's lp85 pass-0 stuck in that 400
  loop at 57 of 160 actions (0 actions in 4 minutes, measured) and was ended by `PER_GAME_S=9000`.
  Duck's solver has no retry ceiling, and `cell_breaker.py` -- which exists to cap exactly this --
  **was not installed in the image arms because this harness's token-usage wrapper set `__wrapped__`
  on `_chat_completion` and cell_breaker declines to double-wrap.** That is this instrumentation's
  bug, and it cost png32 -- the comparison arm -- roughly 2 levels, i.e. **it biases in the TOWER's
  favour.** Sensitivity: excluding lp85 from all arms gives text 18 > tower 15 > png32 13; imputing
  the censored run at its sibling's 5 levels gives png32 23. The ordering text > tower > png32 is
  unchanged either way, so the headline survives the bias, but the tower-vs-png32 margin of +6 should
  be read as roughly +4.

### Predictions vs outcomes (block 3)
| # | prediction | outcome |
|---|---|---|
| Q1 | every arm clears L1 on vc33 and lp85 in both passes | **right** (6/6 per arm) |
| Q2 | tower within +-3 of png32 | **wrong, in the tower's favour** -- +6 (roughly +4 after the censoring bias) |
| Q3 | the image advantage over text GROWS at 160 actions | **WRONG, and decisively** -- it REVERSES. text goes from behind at 22 actions to ahead at 160 |
| Q4 | tower worse than png32 on the HELD-OUT games | **wrong** -- tower +1 level and faster to first clear on both |
| Q5 | at least one held-out game returns 0 in at least one arm | **right** (cd82, one pass, both image arms) |
| Q6 | still not separable after correction | **right** -- nothing reaches p<0.05, let alone Bonferroni |

## Lord Han Solo's checkpoint shares OUR vision tower, bit for bit

Checked 2026-10-05 ~14:30Z, before any bulk download, to decide whether the student transfers to the
leading public stack (`lordhansolo/qwen3-8-flash-next-mixed-nvfp4-fp8`, PyTorch/hf-mixed-mtp-nvfp4/1,
hidden 23.84 vs our 2.55). Total cost: ~60 MB of HTTP range requests, no VM time, no 80 GB pull.

| check | ours | his | verdict |
|---|---|---|---|
| architecture | `Qwen4ExpForConditionalGeneration` | same | same |
| `vision_config` | patch 16, merge 2, depth 27, hidden 1152, out_hidden 2560, heads 16, intermediate 4304, pos_emb 2304, deepstack [] | same | **14/14 fields identical, 0 different** |
| image / vision token ids | 248056 / 248053 / 248054 | same | same |
| visual tensors in the weight index | **333** | **333** | **name sets identical, 0 on either side only** |
| quantization of the tower | 110 explicit `model.visual.*` entries in the `ignore` list | one regex, `re:.*visual.*` | both exclude the WHOLE tower |
| where the visual tensors live | BF16 | all 333 in `carry-model-bf16-00001.safetensors` | both unquantized |
| dtype + shape, all 333 | BF16 | BF16 | **0 mismatches on dtype AND shape** |
| **bytes** | - | - | **6 of 6 probed tensors byte-identical (same SHA256)** |

The six byte-compared tensors span the whole tower, including the output projection the student is
distilled to predict:

| tensor | bytes | shape | sha256[:12] |
|---|---:|---|---|
| `model.visual.patch_embed.proj.weight` | 3,538,944 | (1152, 3, 2, 16, 16) | `a0d1da5b4858` both |
| `model.visual.blocks.0.attn.qkv.weight` | 7,962,624 | (3456, 1152) | `fa403b68eedf` both |
| `model.visual.blocks.13.mlp.linear_fc1.weight` | 9,916,416 | (4304, 1152) | `bb95d9731345` both |
| `model.visual.blocks.26.attn.proj.weight` | 2,654,208 | (1152, 1152) | `dcd9fcfd504d` both |
| `model.visual.merger.linear_fc2.weight` | 23,592,960 | (2560, 4608) | `fb7b0ce30483` both |
| `model.visual.pos_embed.weight` | 5,308,416 | (2304, 1152) | `46158a506035` both |

**Consequence: his vision tower IS our vision tower, bit for bit, so the student needs NO
re-distillation to be used on his stack.** His own `PATCH_README.md` says the package involves "no
quantization change", and both checkpoints are `compressed-tensors` mixed-precision quants that carry
the tower in BF16 -- the standard recipe for this family, because the tower is small (0.85 GiB) and
sensitive. The branch point is therefore the cheap one: swapping the student in is a launch-flag change
(`--enable-mm-embeds --limit-mm-per-prompt '{"image":0,"video":0}'`, already proven here) plus the
same per-turn embeds plumbing used in blocks 1-3, not a re-distillation.

Method, if it needs repeating for another checkpoint: fetch only `config.json` and
`model.safetensors.index.json` over the Kaggle API, then range-request each tensor's exact
`data_offsets` out of the safetensors shard and compare bytes. Credentials are read at runtime from
`~/.kaggle/access_token` and never written anywhere.

## His serving config, read from source -- and what it means for arm B

From `lordhansolo/taaf-kaggle-source` (641 KB, pulled; the model was NOT needed for this):
`inference/framework/kaggle.py:1340-1412` builds the vLLM command, `configs/inference.json` supplies
the values.

| setting | his value |
|---|---|
| model | `primitive-ai/Qwen3.8-Flash-Next-mixed-NVFP4-FP8` |
| max_model_len / context_window | 147072 / 127488 (the notebook pins 123392) |
| max_num_seqs / max_num_batched_tokens | **14** ("C14") / **2048** |
| KV / indexer / mamba-ssm dtype | `fp8_e4m3` / `fp8` / `bfloat16` |
| MTP | 3 tokens, `draft_vocab_32k.json`, `use_local_argmax_reduction` |
| prefix caching | on, `prefix_match_unit 128`, `retention_interval 0` |
| gpu_memory_utilization | 0.98 |
| PLE offload | `--engram-config {"cpu_offload": true}` + `--cpu-offload-params embed_tokens` |
| **`--limit-mm-per-prompt`** | **`{"video": 0}`** -- image left UNLIMITED, so the tower is loaded and used |
| **`--mm-processor-kwargs`** | **`{"max_pixels": 65536}`**, from `(ARC_FRAME_SIDE 64 x upscale 4)**2` |
| concurrency / budget | 14 concurrent games, 45 min/game, 1 pass |

### Arm B is a two-line diff -- but it is NOT a like-for-like swap

The diff is genuinely minimal: in that one function, `json.dumps({'video': 0})` becomes
`json.dumps({'image': 0, 'video': 0})` and `'--enable-mm-embeds'` is appended. Everything else stands.

But two things follow that change what arm B measures, and both come free from the source read:

1. **His image path is 66 tokens per board, not 4096.** `upscale 4` -> a 256x256 px board ->
   `max_pixels 65536` (the processor's own minimum) -> **66 image tokens**. That is EXACTLY our `png4`
   arm. So arm A vs arm B is a **66-token real-pixel path against a 4,098-token student path: a 62x
   token change**, not a tower swap at matched cost. There is no token-matched student available --
   the 4096-token variant is the one that works, the 1024-token one (`ckpt_px16`, full-eval cos
   0.8431) is still 15x his 66, and the 800-token variant is mid-training. **The board tower's premise
   costs 62x the image tokens of the configuration currently leading the public leaderboard.**
   Directly relevant: in blocks 1-2 png4 and tower TIED (11 levels each), and block 3 dropped png4,
   so we have no 160-action png4 number -- the cheap version of this very contrast, on a stack we
   already have working, is ~3 h and no 180 GB transfer.
2. **His `max_pixels 65536` cap already captures most of the memory argument for excluding the
   tower.** The KV swing from 9.31 to 62.97 GiB that motivates the tower comes from a LARGE
   `max_pixels`, because the encoder profiling forward is sized on the maximum image
   (`encoder_runner.py:119-126`). He caps it at the processor minimum, so his profiling peak is
   already tiny. Arm B should therefore recover roughly the 0.85 GiB of tower weights plus a small
   profiling delta -- the same order as the 1.29 GiB measured here, **not tens of GiB**. A one-line
   `max_pixels` cap buys most of that saving while keeping the pixel path.

## What I could NOT establish

* **Whether tower and png32 really are equivalent.** n=12 game-runs cannot resolve 2 levels. The two
  blocks disagree on the sign. This run rules out a LARGE deficit, not a real one.
* **The play result is a FLOOR, not a ceiling, on the tower's standing.** Every arm ran with the ViT
  resident, with the student on a separate machine and contending with nothing. The configuration in
  which the student actually pays for itself (tower excluded: +1.29 GiB KV, +10.3% pool, measured
  above) was never the configuration the games were played in, and a Kaggle submission would also make
  the student share the one card. So "no wall-clock cost" is the least favourable reading available.
* **Out-of-distribution board perception.** vc33/lp85/ar25 are all in the student's TRAINING set; its
  held-out games are cd82/m0r0/re86/s5i5/sk48. cd82 and ft09 were rejected for the budget because they
  clear level 1 in only 16% / 56% of recorded passes within 40 actions, so a held-out game at this
  budget would have returned mostly zeros. **This is the biggest gap in the result.**
* **ANYTHING AT A REAL BUDGET -- and this is now the largest defect in blocks 1-2.** The 22-action cap
  is BELOW the median actions-to-first-cleared-level. findings 49 (:1388-1390) measures that statistic
  at min 6 / **median 23** / p90 52 / max 97 over the 19 games that scored in one soak, and findings
  88b (:3173, :3191) puts the corpus-wide level-1 maximum at **108**. Every run in blocks 1-2 hit the
  cap (`state=gave_up`, 12/12 in every arm), so **more than half of them would have ended before
  clearing a level even with perfect play**. The null results in blocks 1-2 are therefore a property of
  the budget, not of the arms, and no arm comparison in those blocks should be read as evidence of
  equivalence. (For scale: Franzen's 10-game run averaged ~148 actions/game.) Block 3
  (`runs/board_tower_play_real/`) re-runs tower/png32/text at **160 matched actions** -- 1.48x the
  corpus level-1 maximum -- on 3 trained + 2 HELD-OUT games, with actions-to-first-level as the primary
  endpoint. The flaw was in the specification, which asked for breadth at a small budget while the
  median-23 number was already in our own findings file. **Block 3 has now run and its section above
  supersedes blocks 1-2 for every arm comparison.**

* **Nothing in block 3 is statistically significant either.** n=10 game-runs per arm, p >= 0.097 on
  every contrast. The run rules out large differences; it does not establish any of the orderings.
* **The equal-token and equal-time orderings are POST HOC normalisations, not designed arms.** Only
  the action budget was matched by construction. An arm run under a real token or wall-clock cap
  could behave differently (e.g. text would be cut mid-game rather than simply scoring less per hour).
  The reversal between budgets is therefore a hypothesis the numbers support, not a measured result.
* **The held-out probe is 2 games x 2 passes.** cd82 and m0r0 only; re86, s5i5 and sk48 untested
  (sk48 has never scored for us in any run, so it is unusable). 5 levels vs 4 is not a generalisation
  claim, it is an absence of evidence for memorisation.
* **png32 was handicapped by this harness's own bug** (cell_breaker not installed in the image arms
  because the token-usage wrapper set `__wrapped__`), costing it ~2 levels on the wedged run. Fixed
  nowhere yet -- the wrapper should delete `__wrapped__` so cell_breaker installs on top of it. The
  bias runs in the tower's favour, which is the wrong direction for the arm under test.
* **Deeper levels.** All 30 block-3 runs still ended at the 160-action cap (`gave_up`), so nothing
  here speaks to levels past the third or fourth of each game.
* **Whether 1024 tokens would do as well.** Not tested; that is the other agent's arm.
* **A clean arm symmetry on the circuit breaker.** Installing the token-usage trace on
  `_chat_completion` set `__wrapped__`, so `cell_breaker.py` declined to install in the three image
  arms ("already wrapped") while the text arm got it. It did not matter -- **0 analyzer failures,
  0 HTTP 500s, 0 timeouts in all 8 arm-runs** -- but it is a real asymmetry and it is recorded here
  rather than discovered later. The `ab_local.py` 400-storm watchdog was armed in every arm.
* **The vc33 encoder-cache 500-storm** (findings 27) did not fire; it was accepted, not mitigated.

## Artifacts

* `runs/board_tower_play/` (block 1), `runs/board_tower_play_b2/` (block 2): per-arm `benchmark.json`,
  `*requests.jsonl`, `board_tower.jsonl` (student load + pre-flight + every hydration + every
  completion's server-side `prompt_tokens`), `ARM_CONFIG`, `run.log`.
* `runs/board_tower_play/{PREREGISTERED.md,report.json,pooled.json,liveness.json,student_best_full_eval.json}`
* `notebooks_duck/cell_board_tower_embeds.py` -- the arm. Two switches: `BT_TOWER=1` (student embeds
  instead of Duck's PNG) and `BT_IMAGE_KEEP=<n>` (history image window, both part kinds). Refuses to
  install `BT_TOWER=1` without `MULTIMODAL_CONTEXT=current_grid`, and refuses to play if the server
  rejects a pre-flight embeds request.
* `notebooks_duck/ab_local.py` -- ONE added gated line that execs the cell when either switch is set.
  Inert otherwise; no other arm's behaviour changes.
* `scripts/board_tower/run_play_ab.sh`, `report_play_ab.py`, `pool_play_ab.py`.

## Reproduce

```
gcloud compute instances start kaggle-twin --project arc-agi-510600 --zone us-central1-b
gcloud compute ssh kaggle-twin ... --command "bash /kaggle-twin/rc/work/launch_server.sh"   # already has --enable-mm-embeds
# IAP forward 127.0.0.1:15307 -> twin 127.0.0.1:5307 (install numpy into gcloud's bundled python first)
FROZEN=<frozen module tree> ROOT=runs/board_tower_play ARMS="tower png32 png4 text" \
  GAMES=vc33,lp85,ar25 PASSES=2 CONC=6 MAXACT=22 PERGAME=2700 TIMEOUT=240 \
  bash scripts/board_tower/run_play_ab.sh
.mlvenv/bin/python scripts/board_tower/pool_play_ab.py runs/board_tower_play runs/board_tower_play_b2
gcloud compute instances stop kaggle-twin --project arc-agi-510600 --zone us-central1-b
```

## Cost

VM `kaggle-twin` RUNNING in two sessions: **04:19:32Z -> 05:49:39Z (1.50 h, the four-arm play run)**
, **06:22:52Z -> 06:30:54Z (0.134 h, the matched-pair no-tower boot)** and
**06:35:06Z -> 13:21:01Z (6.77 h, block 3, the real-budget run)** = **8.40 GPU-hours** on one
RTX PRO 6000 (Spot, ~$1.79/h incl. disks) = **~$15.04**. Of that, 37 min was block 1 (4 arms), 38 min block 2, the rest
server boot (4.9 min), smoke and probes. **VM state at exit: TERMINATED** (verified by
`instances describe`: `kaggle-twin TERMINATED SPOT`); the server container was stopped and removed and
its log saved to `/kaggle-twin/rc/out/server_final_boardtower.log`; the IAP tunnel was torn down.
Stopped disks continue at ~$0.105/h, as before this run. Nothing of the measurement ran on a local
card: only the 27M student (110 MB, 12.1 s total) used the idle local RTX PRO 6000.
