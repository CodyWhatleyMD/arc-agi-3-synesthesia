# S0 on Flash-Next's own vision tower: the 16-row table, and how context-free a real board token is (2026-10-03)

**Question (plan S2b).** If a board is fed as 4,096 synthetic image tokens, one per cell, taken from a 16-row
colour -> token table recorded once from the tower, do those tokens resemble what the tower actually emits for a
real board? This is the precondition the plan asked to measure *before* any model test.

**Answer: no.** The merged token the tower emits for a cell is dominated by *position* and *neighbourhood*, not
by the cell's colour. A real-board token is nearest its own colour's table row at 12-66% (chance 6%; the
"always say the majority colour" baseline is 52-53% on these boards). The S2b model test is still worth running,
for a different reason given at the end -- but "synthetic ~= PNG at the token level" is already false.

Everything below was recorded by `notebooks_duck/synth_tokens/s0_record_table.py` inside the serving image
`vllm/vllm-openai:qwen38-flash-next` (image id `fc120ece0a38`) on GPU 0, 2026-10-03 16:39 (container clock),
31.9 s wall. Numbers are quoted from `notebooks_duck/synth_tokens/s0_results.json`.

## Method (what was actually run)

* **Tower**: `vllm.model_executor.models.qwen3_vl.Qwen3_VisionTransformer(config.vision_config,
  norm_eps=config.text_config.rms_norm_eps, quant_config=None, prefix="model.visual")` -- the constructor call in
  `RT/models/qwen3_8_flash_next/nvidia/model.py:871` (the image's copy of that file has sha256
  `d900cd6f...`, identical to the runtime tree the audit read). `quant_config=None` is equivalent to serving:
  all 333 `model.visual.*` tensors are in the checkpoint's quantization ignore list, so the engine also builds
  them as plain BF16 linears. Attention backend chosen by the same runtime logic: `FLASH_ATTN`.
* **Weights**: the 333 `model.visual.*` tensors of `/media/ignaz/claude-extra/Qwen3.8-Flash-Next-NVFP4-ours/
  model-00002-of-00005.safetensors` (448,931,056 params, all BF16; sha256 over the tensor bytes
  `5c8207cd2237d0d7...`). All 333 parameter names loaded, none missing, none extra.
* **Palette**: read from the engine source by `notebooks_duck/synth_tokens/palette.py` (`taaf/game.py
  ARC_COLORS` and `vision_context.py ARC_COLOR_MAP`, cross-checked equal; sha256 `d3bddf3838ba814e...`).
  No CSS guesses (findings 71-72).
* **Pixels**: each cell one flat 32x32-px block (what `vision_context.py` produces with its NEAREST upscale),
  rescale 1/255, normalise mean/std 0.5, patch 16, merge 2, temporal frame duplicated. My patchifier was checked
  against the image's real `Qwen2VLImageProcessor` on a 2048x2048 board: same shape (16384, 1536), same grid
  [1,128,128], max abs diff 5.6e-8. (The real processor cannot be used for the 32x32 square: its
  `min_pixels=65536` would upscale it to 64 tokens.)
* **Inputs**: (a) per colour, a flat 32x32-px square -> grid (1,2,2) -> ONE merged token = the table row;
  (b) per colour, a 64x64 board entirely of that colour at 32 px/cell -> 2048x2048 -> 4,096 tokens;
  (c) three recorded boards (`runs/opus55_docker/artifacts/`: vc33 line 40, 9 colours; ls20 line 40, 9 colours;
  ft09 line 4, 8 colours) through the full tower.
* **Independent check**: transformers 5.15.1 `Qwen3VLVisionModel` (SDPA, bf16) on the same weights and patches
  agrees with the vLLM tower per token: flat square cos 0.9997; solid board mean cos 0.9968 (min 0.829);
  real board mean cos 0.9975 (min 0.840). The findings below are not an artifact of one implementation.

## 1. The table itself (flat 32x32 square, one token per colour)

Norms 1.80 (black) .. 3.36 (cyan), mean 2.86. Raw pairwise cosine between rows: mean 0.767, min 0.555, max
0.981 -- a shared "flat patch" component carries 78% of the energy (as on the 27B: findings in
`build_bases.py`). After centring: off-diagonal cosine mean -0.06, max 0.895 (greys 2 and 3); nearest-neighbour
distance min 0.616 (grey 2 <-> grey 3), mean 1.22. **All 16 colours separate** (gate of plan S0 passed as far
as the table goes; no two rows coincide).

## 2. A token in a big flat region is position, not colour

Per colour, cosine between the flat-square token and the token of the same colour inside an all-one-colour
board:

```
colour        flat~centre  flat~interior-mean  centre~corner(same board)   norm flat -> centre
 0 white        0.267          0.384               0.057                     2.46 -> 0.85
 1              0.210          0.395               0.034                     3.00 -> 0.79
 2              0.209          0.395               0.041                     3.13 -> 0.88
 3              0.226          0.387               0.036                     3.02 -> 1.02
 4              0.250          0.394               0.034                     2.81 -> 0.92
 5 black        0.322          0.415               0.056                     1.80 -> 0.88
 6              0.202          0.353               0.036                     2.76 -> 0.80
 7              0.210          0.361               0.037                     2.85 -> 0.80
 8 red          0.216          0.365               0.053                     2.81 -> 0.83
 9 blue         0.230          0.346               0.038                     3.16 -> 0.71
10              0.194          0.358               0.047                     3.36 -> 0.75
11 yellow       0.209          0.342               0.063                     2.77 -> 0.75
12              0.221          0.371               0.046                     3.15 -> 0.75
13              0.167          0.304               0.040                     2.77 -> 0.85
14 green        0.213          0.369               0.055                     3.14 -> 0.78
15              0.199          0.357               0.036                     2.71 -> 0.85
mean            0.222 [0.167, 0.322]   0.368       0.044 [0.034, 0.063]
```

* The flat-square token and the centre token of a solid board of the *same colour* have cosine 0.22. They are
  nearly orthogonal.
* Two tokens of the *same colour in the same image*, centre vs corner, have cosine 0.04. Position decides the
  token.
* The 16 centre tokens (same position, 16 different colours) have mean pairwise cosine **0.982** (min 0.945);
  97.5% of their energy is one shared vector. Colour is the remaining 2-5%. Their norms are 0.7-1.0, a third
  of the flat-square norms.
* Nearest-flat-row lookup of a centre token gives its own colour at 1/16 = chance (0.0625), raw or centred.

So "colour -> the merged token the tower produces for a flat square of that colour" is not a property of the
colour alone: the tower output for a cell inside a region is a position/region code with a small colour
component.

## 3. Real boards: nearest-table-row accuracy per cell (the S2b precondition)

For each of the 4,096 cells, cosine between the real tower token and the table row of the cell's colour, and
whether that row is the nearest of the 16. "interior" = all 4-neighbours same colour.

```
board (colours)   table                  acc    interior  boundary   mean cos(token, own row)   majority-colour baseline
vc33 (9)          flat                   0.120  0.071     0.285      0.239                      0.521
                  flat, centred          0.042  0.003     0.170      0.029
                  board interior-mean    0.249  0.184     0.472      0.586
                  colour x position      0.192  0.192     0.192      0.646
ls20 (9)          flat                   0.243  0.196     0.343      0.254                      0.520
                  flat, centred          0.114  0.064     0.219      0.091
                  board interior-mean    0.364  0.271     0.561      0.590
                  colour x position      0.217  0.222     0.207      0.639
ft09 (8)          flat                   0.665  0.740     0.590      0.310                      0.527
                  flat, centred          0.537  0.672     0.402      0.374
                  board interior-mean    0.435  0.323     0.547      0.525
                  colour x position      0.207  0.201     0.212      0.563
```

* **Flat table**: 12% / 24% / 66%. Chance for a 16-way argmax is 6%; but on vc33 and ls20 it is *below* the
  majority-colour baseline (52%). The large background regions (colours 3 and 4) collapse onto black (5):
  on vc33, 1,378 of 2,135 colour-3 cells are nearest the black row. Small objects (<= 55 cells, with boundaries)
  are read better (65-100%) -- boundaries put contrast into the token. ft09 is an outlier only because its
  majority colour is black (2,160 cells, 85% nearest the black row).
* **Colour x position table** (the solid board of each colour, same cell): 19-22%, interior == boundary. Adding
  position does not recover the colour. About 0.56-0.65 of a real token's direction is the position component
  (cos with the per-cell mean over the 16 solid boards); the remainder is the *neighbourhood*, which no
  per-cell table has.
* Centring (subtracting the table mean) makes the flat table worse on every board.

**Implication for S2b, before any model test.** The synthetic tokens will not look like real-PNG tokens to the
language model: the real token stream for a board is mostly a per-position code plus neighbourhood context,
with a 2-5% colour component; the synthetic stream is 16 distinct vectors of norm ~2.9 (3-4x the real norm)
whose colour separation (centred NN distance 0.62) is *larger* than anything the real tower emits inside a
region (0.047). Two readings, and tonight's test decides between them:

1. The LM reads colour through the tower's contextual code (the only thing it was trained on). Then the
   synthetic arm reads like text or worse, and the 28 MB/request buys nothing. The fix would be S2c (a shallow
   tower that reproduces neighbourhood tokens on board renders), not a bigger table.
2. The LM reads *any* strong colour direction placed at image positions with 2-D M-RoPE. Then the synthetic arm
   can match or beat the PNG arm on the position-free `same` task, because its tokens carry more colour than
   the real ones. That would be the paper result on its own.

Neither reading is favoured by S0; S0 only rules out the premise that the table reproduces the tower. The
decision rule and statistic are fixed in `scripts/synth_tokens_perception.py` (docstring).

## Files

* `notebooks_duck/synth_tokens/table_flashnext_v1.pt` -- `table` (16, 2560) float32 = flat-square rows (also
  `table_bf16`, `table_board_centre`, `table_board_interior_mean`, `palette_rgb`, `meta`).
* `notebooks_duck/synth_tokens/table_flashnext_v1.provenance.json`, `s0_results.json` -- all numbers above.
* Position table (4096 cells x 16 colours x 2560, bf16, 340 MiB, sha256 `b0f31a09...`) is NOT committed; it is
  at `<session scratchpad>/s0_scratch/table_flashnext_pos_v1.pt` and reproducible from the recorder.
* `notebooks_duck/synth_tokens/palette.py` (engine palette, render), `s0_record_table.py`, `run_s0_docker.sh`.
* `notebooks_duck/synth_tokens/synth_embeds.py` -- S2b request builder; `test_synth_embeds.py` (8 tests pass).
* `scripts/synth_tokens_perception.py` -- S3; `scripts/flashnext_serve/serve_mm_embeds.sh` -- the server.

## Tonight (when the 6000 is free)

```
GPU=1 scripts/flashnext_serve/serve_mm_embeds.sh          # serve_ours_sidecar.sh + --enable-mm-embeds
until curl -s localhost:5300/v1/models | grep -q flashnext; do sleep 20; done
python3 scripts/synth_tokens_perception.py --probe-only  # refuses unless image_embeds is accepted
python3 scripts/synth_tokens_perception.py --n 64 --arms png,synth,text --tasks same,row,col
```

## Caveats

* Three boards, all from one run directory (opus55_docker) and one harness; the per-cell numbers are
  consistent across them but n=3 boards.
* bf16 throughout; per-token cos between the two implementations dips to 0.83 on a few tokens of a 4,096-token
  image (kernel order), mean 0.997.
* The real-PNG arm in S3 goes through the server's own processor (same recipe, verified above), so S3's
  ceiling is the real path; S0 did not run the server.
* `serve_cap.sh` named in the task does not exist in any branch, worktree or scratchpad; the launch line is built
  on `serve_ours_sidecar.sh`, the configuration the Kaggle notebook reproduces.
