# DRAFT v4 -- ARC Prize 2026 Paper Track (revision for CL1, 2026-10-27)

> **v4.7 -- all gates closed; final selection 57886730 + 57790633 (unchanged).** Rewritten from v3 against notes/paper_review_codex_v3_2026-10-27.md
> (Codex's second review); every change and the source line checked for it is in
> notes/paper_draft_v4_changelog_2026-10-27.md. Gates: all closed (57902610 = 21.90, v4.7). The tower on/off result is in §3 (v4.2); the native-vs-student
> replication is in §3 and v36's two hidden scores are in §7 (v4.3); the no-echo result (the first resolved contrast) is in §3 with one clause in §4 (v4.4); every interval is run-level, verdicts from it [RL] (v4.5); Batch A on Kaggle run-level, 23.21 in §1, the final selection and four table rows in §7 (v4.6); 57902610 = 21.90 and candidate_pinned's hidden pair in §7 (v4.7); the OFF
> harness provenance (8552964 + faab14c) is recorded in the changelog, not the body.
> The "Claims we do not make" box is editorial material, not part of the Writeup; it now lives in the changelog (§G).
> Body word count (title through §8, source markers included, table syntax excluded): see the changelog.
> The §3 on/off and native-vs-student results each estimate one contrast at n=3 vs 3 under this harness; neither settles
> the hidden set, Batch A, or any mechanism, and the native contrast excludes only a student deficit beyond ~12.9 points (run-level upper bound).
>
> Source markers (strip or convert to references before submission): F<n> = notes/reasoner_doubter_findings_2026-09-03.md
> section n; R = notes/paper_receipts_tower_2026-10-26.md; RW = notes/paper_related_work_search_2026-10-26.md;
> BT = notes/board_tower_play_2026-10-05.md; RT = notes/results_table_2026-10-07.md; PC = notes/payload_cost_2026-10-26.md;
> O = notes/paper_outline_v2_2026-10-26.md; HP = harness/PROVENANCE.json + harness/src/ARC3-Inference/pyproject.toml;
> PS = notes/prestate_batch_a_2026-10-26.md; BA = notes/batch_a_local_result_2026-10-27.md;
> TO = notes/prestate_tower_onoff_2026-10-27.md; TR = notes/tower_onoff_local_result_2026-10-27.md (+ its JSON); NR = notes/tower_native_local_result_2026-10-28.md (+ its JSON);
> HO = Kaggle competition submission list, read 2026-10-28 11:47 CDT by the lead (refs 57704437 and 57725544, both scriptVersionId
> 362609521; 216ax addendum 12 pending); BK = notes/batch_a_kaggle_result_2026-10-27.md (+ its JSON); L = the run logs named in the v3 changelog (recomputed 10-26);
> NE = notes/prestate_no_echo_2026-10-28.md + notes/noecho_local_result_2026-10-29.json; GR = notes/prestate_game_room_2026-10-28.md;
> RL = notes/run_level_ci_results_2026-11-02.md; HD = notes/project_arc_handoff_1006.md (33, 53-55, 57-59, 81-83, 86, 107-109) +
> notes/prestate_hidden_predictor_2026-10-28.md (34, 36) + notes/prestate_candidate_2026-11-01.md (candidate_pinned section) +
> notes/v36_settings_evidence_2026-10-31.md (7) + notes/paper_evidence_clock_2026-11-01.md (23).

---

# Synesthesia: Handing an Open Model the Board Through Its Eyes
### A distilled board tower that delivers ARC-AGI-3 grids at the vision-token positions, and the instrument that measures it

## 1. Summary
We play ARC-AGI-3 with Qwen3.8-Flash-Next, an open vision-language model, feeding each board as image embeddings
computed from the colour grid by an 18.2M-parameter student of its 449M-parameter vision tower, never loaded at
inference [R]. Supported: the student approximates the tower's output on held-out games (mean cosine 0.897),
the model plays through it; dropping the tower frees 0.85 GiB [R, BT]. Not resolved: whether the channel changes the score: one no-image run sat within two image runs' spread (10-14, n=2
vs 1) [F214d]; three OFF runs against three ON controls lean toward the channel helping, Δ −3.62 [−14.01, +6.76]
(n=3 vs 3; §3) [TR]. Intervals: two-stage bootstrap, runs within each arm, then games; game-only resampling called two
identical-code runs a resolved loss (54.70 vs 32.22, Kaggle, 11-02) [RL]. Our best
hidden score with our own components: 23.21 (57886730), one run [HD].

## 2. The board tower
**Architecture.** An 8-block transformer (width 384, 6 heads) reads the 64×64 grid as one-hot colours, one token per
2×2 block (1,024 positions; learned absolute positions, 2-D rotary encoding); a linear head plus learned per-position bias maps each to the language model's 2,560-dimensional input: 18,221,696 parameters [R].

**Target.** The tower's final post-merger output for the board at 16 px/cell (no deepstack features in this model): what the language model receives at image positions. Loss: mean (1 − cos) over rows plus
MSE divided by the target's mean square [R].

**Data.** 8,414 boards from 20 public games plus custom games; five public games held out for validation and checkpoint selection [R, BT]. The shipped student adds each training board's seven non-identity
rotations and reflections, teacher-targeted: 67,308 boards, 180 min, one RTX PRO 6000 [R].

**Fit.** Held-out cosine 0.8972 on 500 boards against 0.8462 for the unaugmented lrfix checkpoint (data, GPU and steps
changed; one seed each) [R]. A board-blind per-position predictor reaches 0.680; 99.08% of held-out
token instances carry a 2×2 block seen in training (55.90% of distinct held-out blocks), so seen local patterns dominate the aggregate; no seen/unseen breakdown reported [F188].

**Serving.** On two CPU threads (median 195 ms/board, one local run [PC]), the output enters the request
as a 1,024-token `image_embeds` part [R]; vLLM's `--enable-mm-embeds` path at image limit 0 never loads the
tower: −0.85 GiB weights, +4.4% to +10.3% KV cache (two measured configurations) [BT, F185].

## 3. What the channel does in play
The matched-geometry comparisons use 1,024 visual tokens/board, 16× Han Solo's published 64-token default; the
tested 64-token student's held-out fit was poor (0.651 vs a 0.595 board-blind floor) [F188, BT]. Public-25 scores
are the harness's averaged per-game score, not necessarily the competition formula [F213a].
- **Matched geometry, public 25** (one GCP RTX PRO 6000; Han Solo's harness, runtime and shipped primitive-ai
  NVFP4/FP8 checkpoint; unaugmented student): student 42.40 ± 5.04 sd (n=4), native tower 33.82 (n=2: 39.77, 27.87);
  untested for significance, NOT RESOLVED [RT, F202]. On eight GPUs at BF16 the observed means were 49.51 for the
  native tower and 46.26 for the student (n=2 each); the comparison remains unresolved [F208b].
- **Image against no image** (Kaggle; his harness and runtime; our v2.2 quantization; dihedral student): 43.86 and
  35.21 with the image (n=2); 34.86 without, the board via its Python tool only (n=1): NOT RESOLVED at n=2 vs 1 [F214c, F214d].
- **Tower on/off, local replication:** three OFF runs (bo1b, bo2b, bo3b; MULTIMODAL_CONTEXT=none: no board part, no prompt
  section) against ON controls r2/r3/r4 (RTX PRO 6000 Max-Q, 25 public games, 9,300 s): OFF 38.33
  vs ON 41.96, **Δ = OFF − ON = −3.62**, 95% CI [−14.01, +6.76], 17 of 24 decided games lower
  without the channel: NOT RESOLVED at n=3 vs 3, leaning toward the channel helping; levels −0.24 [−0.88, +0.41]. OFF
  generated ~8% faster per token but took fewer actions in two of three runs [TO, TR].
- **Native tower against the student, local replication:** three runs with the native 449M tower encoding the same
  16 px/cell board PNG at 1,024 tokens (na1c, na2c, na3c; history matched by raising the server's image limit) against
  r2/r3/r4: NATIVE 44.02 vs STUDENT 41.96, **Δ = NATIVE − STUDENT = +2.07**, 95% CI
  [−8.80, +12.88], 11 up / 13 down / 1 tie: NOT RESOLVED at n=3 vs 3; the 18.2M student stands in for the 449M tower with
  no detectable loss at this n. The three channel
  states order none < student ≲ native at the point estimates, nothing pairwise resolved [NR].
- **No echo of prior reasoning** (SYN_NO_ECHO: preserve_thinking=false per request; prior turns' stored reasoning
  out of the prompt, the in-progress turn's kept): Kaggle 16.46 (won 2) vs control pool 39.06 (n=7, sd 5.07): −22.60,
  below the pool minimum 32.57; n=1, gates clean. Local (ne1-ne3 vs r2/r3/r4/r6): 12.61
  vs 42.21, **Δ = −29.60**, 95% CI [−39.55, −20.04], 0/25/0; levels −2.04 [−2.57, −1.50]:
  RESOLVED [NE].
- **Hidden set (public leaderboard):** the unaugmented student in Han Solo's stack scored 18.01; his native-tower entry
  stood at 23.84 then (different account and day; n=1 each) [F198].
- **An earlier prototype** (27.2M parameters, 4,096 tokens/board; Tufa's June Duck harness, native tower still
  resident; 160-action cap; 5 games × 2 passes, n=10 runs per arm) cleared 27 levels, text 30, native-tower pixels 21;
  no contrast significant (p ≥ 0.097); a harness bug cost the pixel arm ~2 levels [BT].

## 4. Why: hypotheses, not mechanism
Unresolved: whether the image helps, or why the student's public mean exceeded pixels under that checkpoint. Hypothesis: the frozen model treats these tokens as its own tower's output, at its trained positions and markers. Not excluded: a position-dominated code (the 0.680 floor) or local block
lookup [F188]; untested prediction: a position-only or text-matched student plays worse. Resolved (§3): echoed prior-turn reasoning functions as the agent's working memory [NE].

## 5. Related work and what is new
Not new: cross-modal distillation (Gupta et al. 2015, arXiv:1507.00448); NanoVDR (arXiv:2603.12824); a chess board at a
VLM's vision placeholders (github.com/helloworld0909/chess-ai) [RW]. Ours: a grid student matched to the native tower's
post-merger tokens, no language model trained; we found no ARC entry doing this; a search is not proof of priority [RW].

## 6. The stack and who built it
- **Quantization (ours):** NVFP4 routed experts, FP8 attention. The scored v2.2 (976 windows; NVFP4 MTP experts): play-evaluated only; no
  whole-model reference-agreement or BF16 comparison [F207, F212, F215w].
- **MTP experts (ours):** quantizing them freed 3.37 GiB without redoing the main quantization [F212].
- **Runtime:** Han Solo's 32-file overlay for vLLM e975732, ported by us to 0.31.0 [F210]. Ours: a bounded KV-block copy (cold-start crash fix), parallel shard prefetch,
  a per-game clock fitted to load time [F210a, F216d].
- **Harness:** Tufa Labs' TAAF at branch commit ca1bd02 (metadata declares MIT, no license file shipped) [F216ax, HP];
  ours: the embedding channel, its token accounting, the runtime hooks (commit 8552964) [F216ax].

## 7. Results and noise
**Table 1.** Public-leaderboard scores (games hidden from the authors), our account's submissions
[O, F198, F212, F216c, F216i, F216j, F216ax, HO, GR, HD].

| ID | Date | Configuration | Public LB |
|---|---|---|---|
| 56893726 | 10-07 | Han Solo's stack, unaugmented student | 18.01 |
| 56978558 | 10-08 | dihedral student; no archived diff to 56893726 | 19.15 |
| 57160919 | 10-14 | replicate of 56978558 | 19.52 |
| 57002349 | 10-09 | our v2.1 quantization, his runtime | 10.96 |
| 57133126 | 10-13 | our v2.1, our runtime | 11.80 |
| 57286316 | 10-16 | our v2.2, his runtime, no image, notes on | 14.41 |
| 57364404 | 10-18 | our quantization, runtime, student: v8 by timing | 22.18 |
| 57392451 | 10-19 | configuration unknown | 19.16 |
| 57645104 | 10-25 | not ours: Tamrazov's copy of dfranzen's code, edited | 24.54 |
| 57704437 | 10-27 | v36: v8 as plain code, Python 3.13 runtime | 20.90 |
| 57725544 | 10-28 | replicate of 57704437 | 21.85 |
| 57835561 | 10-31 | replicate of 57704437 | 20.44 |
| 57761528 | 10-29 | room G-c (be9603e): the investigator's room text | 15.28 |
| 57790633 | 10-30 | room G-s (1c4799d): CL1's room text | 21.75 |
| 57886730 | 11-01 | candidate_pinned: 848f336 + boot clock | 23.21 |
| 57902610 | 11-02 | copy of 57886730 (not diffed) | 21.90 |

Our account's top score is another team's. Final selection (the investigator, 11-02): 57886730 and 57790633, two different configurations; the better private score counts.

**Public 25.** Local ON runs of
v36: 40.19, 44.26, 41.41; r3 − r2 = +4.08, 95% bootstrap over games [−8.71, +16.82], resampling games, not runs
[F216ax, L].

**Hidden set.** Identical-config replicates: 19.15/19.52 (gap 0.37), v36's 20.90/21.85/20.44 (range 1.41), candidate_pinned 23.21/21.90 (gap 1.31) [F216ax, HO, HD].
22.18, second-highest of the fourteen attributed method scores here and not reproducible by judges [F216ap], is not a
claimed gain: its rebuild v36 scored 20.44–21.85, all gaps to 22.18 below the public-25 replicate spread (+4.08).
23.21 is likewise not a claimed gain [HD].

## 8. Limits and ongoing work
The student covers one 16-colour palette, one 64×64 grid and this model's tower, not other harnesses' off-palette difference images [BT]. The method needs an open-weight VLM with an embedding-input path and tower access
(closed image APIs and text-only models lack it); deepstack towers need extra per-layer targets [RW]. Other symbolic domains: candidates, not results. Not done: dedicated novel-pattern tests, repeated seeds.
Batch A, agent-side changes ported from dfranzen's Apache-2.0 solution (absent from v36): Δ +3.45 [−8.78, +14.83]
locally (n=2 vs 3) and +0.98 [−11.69, +13.91] on Kaggle (n=3 vs 3), both NOT RESOLVED [BA, BK, F141].
