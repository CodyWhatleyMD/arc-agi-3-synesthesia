# Long paper draft: Sections 2, 3 and 5 (2026-11-04)

Working title: "From Synesthesia to Lobotomy: what a benchmark on a clock can and cannot see." Drafted by a paper-section
agent for the lead's review; not committed. Every number carries its source in a bracket after it; the key is below.
Intervals are 95% run-level (two-stage cluster bootstrap: runs with replacement within each group, then games;
10,000 resamples, seed 0 [RL:3-4]) unless the bracket says "game-only". "Not resolved" means the interval includes
zero, and is written as a result. Δ is arm minus control on the public 25 games, mean score per game.

## Source key (paths relative to the repository root unless absolute)

- RL = notes/run_level_ci_results_2026-11-02.md
- PRL = notes/prestate_run_level_ci_2026-11-02.md
- EC = notes/paper_evidence_clock_2026-11-01.md
- NE = notes/prestate_no_echo_2026-10-28.md
- NEJ = notes/noecho_local_result_2026-10-29.json
- BK = notes/batch_a_kaggle_result_2026-10-27.md
- BL = notes/batch_a_local_result_2026-10-27.md
- TR = notes/tower_onoff_local_result_2026-10-27.md
- NR = notes/tower_native_local_result_2026-10-28.md
- NS = notes/noise_structure_2026-10-27.md
- VS = notes/v36_settings_evidence_2026-10-31.md
- LT = notes/levels_per_token_2026-11-04.md
- GR = notes/prestate_game_room_2026-10-28.md
- GS = notes/game_room_s_local_result_2026-10-28.md
- HP = notes/prestate_hidden_predictor_2026-10-28.md
- XZ = notes/xz_w4a16_kaggle_result_2026-10-30.md
- EE = notes/prestate_experience_efficiency_2026-11-04.md
- LS = notes/prestate_late_submissions_2026-11-02.md
- AL = notes/hidden_path_audit_loop_2026-11-01.md
- AD = notes/hidden_path_audit_load_2026-11-01.md
- SR = notes/prestate_start_retry_2026-11-01.md
- DF = notes/prestate_dflash_fair_2026-11-01.md
- AM = notes/paper_asked_the_model_2026-10-15.md
- RC = notes/kaggle_working_recipe.md
- RG = notes/research_grid_encoder_2026-10-30.md
- F = notes/reasoner_doubter_findings_2026-09-03.md
- HD = notes/project_arc_handoff_1006.md (the repository copy; its first entry is 11-01 10:55)
- HM = /home/ignaz/.claude/projects/-home-ignaz/memory/project_arc_handoff_1006.md (the memory copy; entries from
  10-26 to 10-31 are only here)
- D4 = `git show 61d9b71:notes/paper_draft_v4_2026-10-27.md` (the 1,500-word draft, v4.7), line numbers of that blob
- FA:<id> = notes/forum_archive/<id>.json (the Kaggle MCP text result saved verbatim; archive generated 2026-11-02
  15:42 UTC [notes/forum_archive/INDEX.md:3]); comment ids are the `id` fields in that file; ranks are the file's
  `competition_ranking` field at archive time

---

## Section 2. What the instrument can see

### 2.1 The same notebook, twice

The candidate_pinned notebook (harness 848f336 plus the boot clock) was run on Kaggle as a commit run and scored 54.70
on the public 25 games; the investigator re-ran the identical notebook in the editor on 11-02 and it scored 32.22 [EC:61]. Same
code, same model, same token budget; the 32.22 re-run against the 54.70 commit run: 6.67M against 6.70M generated
tokens, 848 against 834 tokens per second, 2 h 11 m of play against 2 h 14 m [EC:61; HM:576]. What differed was play:
9,203 actions against 12,741, 6 wins against 10, 8 pool-clock stops against 4, 22 analyzer timeouts against 16 [EC:61]. Paired game by game with scripts/compare_arm_groups.py as it
then stood (games resampled, runs not), the two runs gave Δ = −22.47, 95% CI [−35.68, −10.91], sign 4/18/3,
p = 0.004: the script called two runs of identical code a resolved loss [EC:62; PRL:6-8].

Where the 22 points went is the useful part. Six games lost more than 50 points each: tn36 100 → 3.6 (levels 7 → 1),
r11l 100 → 14.3 (6 → 2), tr87 88.2 → 7.6 (6 → 2), sb26 90.6 → 23.3 (8 → 4), ar25 96.3 → 33.1 (8 → 5), s5i5
58.3 → 8.2 (6 → 2), each with similar or fewer actions and 1.5 to 2 times the tokens per action: the agent reasoned
longer and cleared less, stuck in the first levels [EC:63]. Three games moved the other way (re86 +14.2, su15 +9.2,
wa30 +2.1) and nine stayed within ±10 [EC:63]. Per-game outcomes are close to bimodal on whether the mechanic is found
early; that, not throughput, is the run-to-run variance when tokens per second and play time are matched [EC:63].

This was not the only identical-code pair on Kaggle. Room S K1, one notebook version (363241028), scored 42.89
(7,155 actions) on 10-28 and 34.04 (6,838 actions) when the investigator re-ran it on 11-02 [HD:152-154]. The second run reached
its first action 265 s sooner than the first (boot to harness start 689 s against 954 s), and the faster boot did not
carry the score [EC:77-82]. Both pairs' second runs were lower; two pairs is not evidence of a direction [HD:154]. A
third same-code pair came from the start-guard arm: v37 scored 51.37 as a commit run, and v37 with the start guard,
which cannot act on a commit run and so replays v37, scored 32.78 [HM:575].

### 2.2 Fixed-host controls, and what the platform adds

The local control series is four runs of the anchor notebook (harness 8552964) on one RTX PRO 6000, 25 public games,
9,300 s: r2 40.19, r3 44.26, r4 41.41, r6 42.96, mean 42.21 [RL:9; VS:51]. The run-mean sd of the four is 1.78 [RL:9];
of r2–r4 alone, 2.09 [RL:10]. r5 died within seconds of starting on a full disk and never played
[notes/prestate_batch_a_2026-10-26.md:78]; its rerun r5b (47.09) ran the arms notebook at 12a000d with every switch off,
was added as a fourth control after the Batch A pre-statement and before any score, and on its own moved the Batch A
estimate by about 1.3 points [BL:9-10, 21-23]. The Kaggle control pool C1–C7 (harness 12a000d, all switches off, equal
to 8552964 by parity tests) has mean 39.06, sd 5.07, range 32.57–45.95 [VS:49-50]; inside the Batch A same-time pairs
the control alone swung from 32.57 to 45.95, 13.4 points on the same code [BK:26-27].

The server series is the fixed-host noise figure for the submitted configuration. On the GCP server (RTX PRO 6000,
g4-standard-48), each run alone on the card, candidate_pinned (CP, 848f336 + boot clock) scored {45.49, 35.78, 43.82,
47.74, 45.73, 47.94}, mean 44.42, sd 4.50, range 12.2 points at n = 6 on identical code and hardware; the alternating
agent-clock arm (AC) scored {49.70, 44.79, 35.44, 39.31, 44.98, 41.96}, mean 42.70, sd 4.97 [EC:69-70; HD:119-120,
123]. Kaggle's three runs of the candidate notebook, 38.58 / 54.70 / 32.22, have sd about 11.6 at n = 3, about
2.5 times the fixed-hardware spread; the 38.58 run was the candidate before the pinned-memory fix [EC:64, 72;
HM:575-576]. The difference between the two spreads is the platform, not the code [EC:64].

### 2.3 Hidden-set replicates

Our hidden scores (the public leaderboard averages 55 of the 110 private games [HD:108]) include three
identical-configuration sets. v36 (kernel version 362609521) scored 20.90 (57704437), 21.85 (57725544) and 20.44
(57835561), range 1.41 [D4:124-126; HD:92]; a fourth submission of the same version, 57680782, ended in a "system
error" [VS:7-8]. candidate_pinned scored 23.21 (57886730) and 21.90 (57902610, the investigator's identical copy), gap 1.31
[HD:108; D4:129-130], and a post-deadline late entry, 57925231, scored 19.37, giving n = 3 on the public half with
mean 21.49, sd 1.93 [HD:177; LS:44]. An earlier pair, 19.15 / 19.52, has gap 0.37 [HD:108; D4:116-117]. The two rooms
are single hidden runs: G-s (C1's text, 1c4799d) 21.75 (57790633) and G-c (the investigator's text, be9603e) 15.28 (57761528)
[D4:127-128; HM:518, 522].

Our hidden replicate gaps (0.37 to 1.41) are tight, and that is a property of our runs, not of the hidden set:
Tamrazov's nine identical reruns of Franzen's code spanned at least 6.3 points on the same 55 games (29.01 to 35.35)
[HD:108]. Kaggle exposes hidden totals only, not per-game results, so a hidden comparison is a comparison of run means
and sds with no paired-by-game interval [LS:28-30].

### 2.4 Why game resampling called identical code a loss, and what the run-level bootstrap does

Every interval in paper draft v4.4 came from scripts/compare_arm_groups.py resampling games only [PRL:10-11]. A
run-level state (which mechanics the agent cracked early) moves many games together, so games are not independent
draws and the interval is too narrow; this is the same unit-of-analysis error as the July factorial study, trials
inside a cluster [PRL:7-10].

The fix, pre-stated on 11-02 before any interval was recomputed [PRL:3], adds a two-stage bootstrap under `--cluster`:
each resample draws runs with replacement within the arm and within the control (sizes preserved), computes per-game
group means, then draws games with replacement and takes the mean paired delta; 10,000 resamples, seed 0 [PRL:14-16].
With 3 runs per arm the run stage has 10 distinct multisets per group, so the cluster interval is coarse; it is still
the honest one [PRL:17]. At n = 1 per group the script withholds the verdict rather than print a number it cannot
support [RL:23-24]. The pre-statement predicted that no-echo would stay resolved, that on/off, native and Batch A would
stay not resolved with wider intervals, and that AC against CP would stay centred on zero; it also stated that if any
not-resolved arm became resolved under the cluster interval, that would be an implementation error, since cluster
intervals can only be wider or equal in expectation [PRL:25-28]. All predictions held; the cluster intervals came out
about 1.5 times wider [RL:5; HD:87]. The game-only statistic stays reported beside the cluster one, and no number is
removed because it points the wrong way [PRL:13, 32; RL:26-27].

How much of a game's score is the draw? From the three identical ON runs (r2, r3, r4) the per-game score has
between-game variance 790.2 and within-game (run-to-run) variance 658.1, ICC 0.55: 45% of a game's score variance is
run-to-run luck in the shipped configuration; the OFF arm has ICC 0.68 (between 831.8, within 396.2) [NS:13-14]. The
noise is not a clear/no-clear mixture: the clear rate is 73/75 game-runs in both arms, only sc25 and sk48 flip across
the three ON runs, and the differences, between arms and between runs, are in how far a run gets, not whether it
starts [NS:8-11]. One game shows the mechanism: cn04 scored 3.9 / 71.4 / 4.8 across identical runs, because the score
weights later levels and one extra deep level moves it by tens of points while the level count moves by one [HP:13-14].
A single-run leaderboard therefore ranks agents partly by the draw [NS:15].

### 2.5 Every arm, with its run-level interval

Every row but no-echo (Section 3) is not resolved. Runs are listed so that n is visible.

| arm (runs) | n | Δ | game-only 95% CI | run-level 95% CI | levels (run-level unless marked) | run means arm / control (sd) | verdict | source |
|---|---|---|---|---|---|---|---|---|
| Tower on/off: bo1b–bo3b (MULTIMODAL_CONTEXT=none) vs r2–r4 | 3 v 3 | −3.62 | [−9.89, +3.22] | [−14.01, +6.76] | −0.24 [−0.88, +0.41] | 42.66 39.89 32.44 (5.28) / 40.19 44.26 41.41 (2.09) | NOT RESOLVED; 17 of 24 decided games lower without the channel | RL:10, 16; TR:20-22 |
| Native tower: na1c–na3c vs r2–r4 | 3 v 3 | +2.07 | [−4.65, +9.15] | [−8.80, +12.88] | +0.09 [−0.57, +0.77] | 44.41 49.43 38.23 (5.61) / same | NOT RESOLVED; excludes a student deficit beyond ~12.9 and a student advantage beyond ~8.8 | RL:11, 16; NR:22-27 |
| Batch A local: ba1b, ba2b vs r2–r4 | 2 v 3 | +3.45 | [−4.35, +10.92] | [−8.78, +14.83] | +0.36 [−0.34, +1.02] | 49.23 41.58 (5.41) / same | NOT RESOLVED | RL:12, 16; BL:16-17 |
| Batch A Kaggle: A1–A3 vs C1–C3 (same-time pairs, RTX PRO 6000 hosts) | 3 v 3 | +0.98 | [−5.80, +8.62] | [−11.69, +13.91] | +0.05 [−0.72, +0.80] | 41.89 34.83 46.72 (5.98) / 41.96 32.57 45.95 (6.87) | NOT RESOLVED | RL:13, 17; BK:15-17 |
| Agent clock vs pool clock, server: AC (ac1, ac3–ac6, ac2b) vs CP (cp1–cp6) | 6 v 6 | −1.72 | [−8.13, +4.63] | [−10.60, +7.63] | −0.15 [−0.69, +0.41] | 42.70 (4.97) / 44.42 (4.50) | NOT RESOLVED; sign 11/14/0, p = 0.69 | EC:69-72; HD:119-121 |
| Room G-s local: gs1b–gs3b vs r2–r4 | 3 v 3 | +1.26 | [−3.23, +6.01] | not computed | +0.16 [−0.11, +0.45] game-only | 46.36 39.79 43.51 / 40.19 44.26 41.41 | NOT RESOLVED; sign 11/12/2 | GS:16-25 |
| Room G-c local: gc1–gc3 vs r2, r3, r4, r6 | 3 v 4 | −0.35 | [−5.63, +4.84] | not computed | +0.03 [−0.30, +0.35] game-only | 42.50 37.24 45.81 / 40.19 44.26 41.41 42.96 | NOT RESOLVED; sign 13/11/1, p = 0.839 | HM:496 |
| xz's W4A16 checkpoint in v36's harness, Kaggle, vs C1–C7 | 1 v 7 | +6.43 | [−2.38, +15.72] | withheld at n = 1 | +0.37 [−0.19, +0.93] game-only | 45.49 / 39.06 (5.07) | NOT RESOLVED; sign 17/8/0, p = 0.108 | XZ:24-26; RL:23-24 |

The run-level column for the rooms is empty because the 11-02 recomputation listed five arms (no-echo, on/off,
native, Batch A local, AC vs CP) and added Batch A on Kaggle; the rooms were not in it [PRL:21-22; RL:19]. Their
intervals here are game-only as recorded and, by the argument of 2.4, too narrow. The on/off and native rows measure
the board part together with its prompt section and its history: the ON arm carried every board since the last
compaction, median 13 and maximum 48 image_embeds parts per request, so the current board's own share is unknown
[TR:35, 40-44]. OFF generated about 8% faster (829–863 against 772–786 tokens per second), used more tokens
(6.50–6.77M against 6.05–6.16M) and took fewer actions in two of three runs; the payload saving did not become score
[TR:25-28]. Across the three channel states the point estimates order none < student ≲ native and no pairwise
difference is resolved [NR:28-29].

The amendments to the agent clock changed its behaviour
(zero-action park/resume cycles 296 in Kaggle v1, 115 in v3, 6–20 on the server) without a detectable score change at
6 v 6 [EC:72; HD:122]. The pre-statement's own prediction was "centred on zero" [HD:122].

### 2.6 What resolution would cost

The Batch A Kaggle note did the arithmetic for a small effect: resolving +1 to +3 points needs on the order of 28 runs
per arm (the on/off interval scaled); four more same-time pairs would take Kaggle to 7 v 7 and an interval of roughly
±4.6, which resolves only an effect of that size or larger; the quota then remaining (95,672 s, about 9 runs) could
buy neither [BK:38-40]. On the server, where the fixed-host sd for candidate_pinned is 4.50 at n = 6 [HD:123], the
same conclusion follows from the sd. (This sentence is our arithmetic on the cited sd, not a number from a file: the
standard error of a difference of two six-run means is 4.50 × √(2/6) ≈ 2.6 points, so a 95% interval of about ±5;
halving it needs four times the runs.) The run stage of the bootstrap is coarse below about ten runs per arm [PRL:17].
For the hidden set the instrument is weaker still: one counted submission per day [F:179], no per-game results
[LS:28-30], and a public half of 55 games on which another team's identical code spread at least 6.3 points [HD:108].
With one submission per day, a single A/B is not measurable [RC:702].

### 2.7 The rooms: an expected effect the instrument could not resolve

The game-room arm changed two things in the prompt and nothing else: a preamble telling the model it is playing a game
built to be beaten, and a praise line after each level clear [GR:14-28]. The pre-statement's prior was "NOT RESOLVED
at 3v3 (the design cannot see less than ~6 points)" and named actions per analysis step as the exploratory row where
any direction would show first [GR:36-39, 46-49]. Locally, n = 3 each. G-s against r2/r3/r4 gave +1.26, game-level 95%
CI [−3.23, +6.01], sign 11/12/2, levels +0.16 [−0.11, +0.45], as recorded [GS:23-25]; against the four-run pool,
+1.01 [−3.65, +5.61] [HM:496]. G-c against r2/r3/r4/r6 gave −0.35 [−5.63, +4.84], sign 13/11/1, p = 0.839, levels
+0.03 [−0.30, +0.35] [HM:496]. Neither is resolved and no run-level interval was computed for either. What did move
was behaviour: the G-s runs took 21,712 actions against the controls' 29,035 (−25%), analysis steps −10%, actions per
analysis step 4.90 / 5.48 / 5.09 against 6.40 / 6.14 / 6.14, tokens about equal, and level clears 309 against 296 (+4%):
fewer moves per level, not fewer levels [GS:30-32]. The praise line, read in gs1b's transcripts, drew a single python
tool call and no prose; the model played [GS:37-39]. On the hidden set each room has one run: G-s 21.75 (57790633),
G-c 15.28 (57761528) [D4:127-128]. Kaggle signs (G-c won 8 games to G-s's 7) and local signs point opposite ways:
noise [HM:496]. C2's note at the time stands: the scorer is action efficiency per level, so "fewer moves per level,
not fewer levels" is the direction the score rewards; if a later arm shows the same shape that consistency is worth
saying even without a resolved delta, but it is kept beside the exploratory row, not as a reading [GS:49-51]. An
action-efficiency reading of the rooms is therefore a hypothesis awaiting its own pre-statement: the G-s result note
says the actions-per-level row is worth pre-stating as a primary outcome for a replication [GS:45-47], and the only
pre-statement on action efficiency written since (11-04) is for timed against untimed play of the anchor, not for the
rooms, and has no result yet [EE:1-33].

---

## Section 3. The one resolved result

### 3.1 The switch, and why it was built

In the shipped harness the client stores each reply's reasoning on the history message (tool_agent.py:1587) and sends
chat_template_kwargs {enable_thinking, reasoning_effort} without preserve_thinking (utils/openai_compat.py:77); the
chat template keeps every earlier turn's reasoning when the flag is undefined, and vLLM 0.31 maps the client's
reasoning field into reasoning_content, so the template sees it [NE:4-8]. C3's fork measured 938 requests above
110K tokens: reasoning 66.9K tokens (58%), boards 17.4K (15%), tool results 11.5K, assistant text 9.0K, system 5.4K,
user 3.9K [NE:8-9]. Compaction (a 45K sawtooth, about six cliffs per game, the first at 11–20 minutes of 65) is
therefore driven mostly by replayed reasoning, not by boards [NE:10-11].

The echo was not an omission. The server is launched with --default-chat-template-kwargs preserve_thinking true
(framework/kaggle.py:1381) and all three inference configs set it true; it is in Tufa's Duck baseline as shipped
(ca031c1) and in Franzen's harness, whose CONFIGURATION.md documents an ARC3_PRESERVE_THINKING knob with default 1
[NE:47-51]. No written reason was found in either tree; the presumed reason, marked presumed, is that the model's plan
lives in its reasoning and replaying it lets a later turn continue the plan instead of re-deriving it, which is also
the mechanism by which removing it could hurt [NE:51-55].

The arm is one switch, SYN_NO_ECHO (default off = the anchor, byte-identical requests). On, the request's
chat_template_kwargs carries preserve_thinking=false; the reasoning is still stored in history and in the transcript;
nothing else changes [NE:14-17]. The token estimator stops pricing replayed reasoning under the switch, or compaction
would fire on a phantom [NE:16-17]. One correction landed during the smoke: the template (chat_template.jinja:116)
renders reasoning when preserve_thinking is undefined or true OR the message is after the last user turn, so the
switch drops only prior turns' stored reasoning and the in-progress turn's stays; the smoke's ratios (P/E_with 0.596,
P/E_without 1.328) imply about 0.23 of stored reasoning still rendered, consistent with that rule, so the arm frees
the prior turns' share, not "~58%" [NE:78-82]. The arm is not a context-length change (the window stays 127,488), not
a change to the current turn's reasoning, and not a prompt change [NE:42-44]. Temperature was 0.6 on both platforms by
code path (the notebook renders its analyzer settings from inference.json under papermill locally and on Kaggle); this
is a code-path check, not a request-field check, because the request log carries no sampling fields [NE:60-66].

### 3.2 What was predicted

C3: the switch frees about 58% of a late prompt and delays the first compaction about 2x; whether play suffers
without re-reading old chains of thought is the experiment [NE:35-36]. C1: the mechanical rows move as C3
says; score NOT RESOLVED at n = 1 v 7 or 3 v 4; if there is a direction, positive, because the games that swing 80
points between identical runs are the ones where a compaction cliff lands mid-plan, and fewer cliffs means fewer plans
lost [NE:36-39]. My prediction on direction was wrong; C3 made none [NE:35-37]. The pre-stated primary was the score/levels statistic of
compare_arm_groups, both tails, NOT RESOLVED unless the interval excludes zero; gates before scores, plus a
switch-specific gate: every request carries preserve_thinking=false and the late-prompt reasoning share is well under
58% [NE:24-28].

### 3.3 Kaggle, one run against the pool

no-echo-k1 (kernel version 363302371, harness c82ffc3) completed with every gate passed: 0 tracebacks, 0 HTTP 400,
switches {'SYN_NO_ECHO': True}, 25/25 games played, 0 sandbox deaths [NE:85-86]. The switch gate on 1,853 requests:
stored-reasoning share 68.2%, P/E_with 0.409, P/E_without 1.323, ECHO OFF [NE:86-87]. Score 16.46 (median 7.30,
2 games won) against the Kaggle control pool of seven (39.06, sd 5.07, minimum 32.57): −22.60, 4.5 pool sds below
the mean and below the pool minimum; n = 1 [NE:88-89]. Exploratory counts: 5,930 actions (controls about 6,650–8,500),
6.33M tokens (controls about 5.7–6.0M), 1,075 tower parts (others about 1,370–1,470): more generation, fewer actions
[NE:90-91]. Play time 7,739 s, about 5% under recent controls [NE:92-93]. The hypothesis recorded at that read, C3's
own caveat now with a number: without prior turns' reasoning, each turn re-derives the plan instead of continuing it;
the per-turn reasoning lengths in metrics.jsonl would test it [NE:91-92]. The decision was to run no further Kaggle
runs of the arm and let the local triple give the effect size with an interval [NE:94-95].

### 3.4 Local, three runs against four

ne1 14.01, ne2 13.75, ne3 10.08, all gates clean (Ending Cell 12, 0 tracebacks, 0 HTTP 400, ARM banner
SYN_NO_ECHO=1), against r2 40.19, r3 44.26, r4 41.41, r6 42.96 on the RTX PRO 6000, 25 public games, 9,300 s
[NE:111-112]. Score: arm 12.61, control 42.21, Δ = −29.60; game-only 95% CI [−38.43, −21.38] at 4,000 resamples
[NEJ:42-47] and [−38.33, −21.30] at 10,000 [RL:9, 19]; run-level [−39.55, −20.04] [RL:9]; sign 0/25/0, every game
lower, sign-test p = 5.96 × 10⁻⁸ [NEJ:49-52]. Levels: 2.17 against 4.21, Δ = −2.04, game-only [−2.46, −1.60]
[NEJ:55-61], run-level [−2.57, −1.50] [RL:16]. Run-mean sds: 2.20 for the arm, 1.78 for the control [RL:9]. The
run-level recomputation on 11-02 was pre-stated to leave this arm resolved ("−29.6 against run sds near 5") and did
[PRL:25; RL:5]. With Kaggle (16.46 against 39.06, n = 1) the direction and size agree on both platforms [NE:115]. It
is the first resolved result of the program, and it is a loss [NE:115-116]. Of the 46 v36 settings inventoried on
10-31, seven have been varied on our stack with a recorded score, and this is the only one resolved [VS:102].

Levels per token tell the same story from the other side: across 43 full-budget runs, timed runs span 13.8–19.9 levels
per million tokens; ne1–ne3 sit at 7.6–8.6 [LT:4, 12-13].

### 3.5 Mechanism, as measured

C2's read of the Kaggle metrics (no-echo against controls C5/C6/C7) [NE:98]: reasoning tokens per turn median 4,326
and p90 12,604 against 2,112–2,281 and 9,884–10,337 (about 2x at the median); per request median 1,846 against
1,030–1,153; requests per turn 1.86 against 1.85–1.89, unchanged; turns in the clock 1,058 against 1,405–1,463 (−27%);
prompt per request median 61.6K against about 80K, smaller as the switch should make it; generated tokens per executed
action 1,067 against C6's 751 (+42%) [NE:99-102]. Same requests per turn, twice the thinking per turn, fewer turns in
the clock: "each turn re-derives the plan" has a direct measure [NE:103]. One confound was checked and excluded: sk48
ran a snippet loop that never checked game over (13,304 action calls, 8,738 refused as previous_game_over, 8,725 of
them in one streak), but 22 of 25 games sat below the C3–C7 averages by more than 1 point (ar25 −92, vc33 −71, tr87
−57, tu93 −53), and without sk48 the comparison is 17.14 against 41.31; the drop is broad [NE:104-108].

The mechanism sentence from the pre-statement's result block is the one the paper carries: the echoed prior-turn
reasoning is the model's working memory [NE:116]; in the 1,500-word draft, "echoed prior-turn reasoning functions as
the agent's working memory" [D4:93]. An earlier observation on the previous harness (10-15) had already pointed this
way at n = 1: removing the reasoning echo, "the harshest of the three options its #5 gave (remove / cap / reorder
compaction); the only one built", halved the agent's pace, "it re-derives the game every request without its own prior
reasoning in context" (7 levels against stock's 11 / 12 in that window) [AM:55-62]. For the clock argument the reading
in the evidence file is that the clock pushed toward cutting the agent's working memory, and the cut cost 29.60 points
[EC:30-31].

### 3.6 What this establishes, and what it does not

It establishes, for this model (Qwen3.8-Flash-Next under our v2.2 NVFP4 quantization [D4:101]), this harness, the 25
public games and this clock, on two platforms, that removing prior turns' reasoning from the prompt lowers the score
on every game: by 29.60 points locally, with a run-level interval whose upper end is −20.04, and by 22.60 points on
Kaggle at n = 1 [RL:9; NE:88]. It establishes that the freed prompt space (median prompt per request 61.6K against
about 80K) did not become score [NE:101]. It establishes that the loss arrives through turns: twice the reasoning per
turn, 27% fewer turns, 42% more generated tokens per executed action [NE:99-102].

It does not establish a hidden-set number: the arm was dropped before any hidden submission [HP:40], and a hidden
replicate set of three is in the late-submission plan, not yet run [LS:18-20]. It does not say which part of the
replayed reasoning carries the memory: capping or reordering were named and not built [AM:61], and a cap is a
different arm. It does not say that more history helps: the trim-back target (81,536) and the context window (127,488)
have never been varied on our stack, and the no-echo result is the only evidence on our stack that prior-turn content
matters [VS:111-118]. It does not separate the echo from compaction timing: the exploratory rows named in the
pre-statement (first compaction time, cliffs per game, between-run divergence at compaction events) [NE:29-32] are
not reported in the result blocks [NE:84-116], so they remain open. It does not measure the share freed beyond the
smoke's estimate (about 0.23 of stored reasoning still rendered) [NE:80-81]. And it is a loss: it shows that the echo
as shipped is load-bearing, not that its size is right. The arm is closed [NE:116].

---

## Section 5. Four throughputs

### 5.0 The clock

Within every run the score is linear in play time; the untimed R0 run against the local timed controls on the same
13 games gave levels 6.15 against 4.23 and score 66.23 against 42.31 at n = 1, not resolved by our rule [EC:22-23]. R0
changed five things at once (no per-game clock, no job clock, concurrency 1, action cap 5,184, audit every 77 actions)
and is not submittable as run [VS:56]. In v36's Kaggle controls the per-game clock (3,918 s) ended 17–21 of 25 games
per run [HM:546]. The investigator's sentence of 10-30 is the frame for this section: under a fixed clock, score = throughput ×
quality; a channel that buys quality with tokens cannot win the board, only be measured [HM:531]. Four throughputs
feed the board: tokens per second on the card, boots that fit the nine hours, draws per day, and copies per model.

### 5.1 Tokens per second

Our stack's generation rate on the RTX PRO 6000, from the job logs: the ON controls r2–r4 generated at 772–786 tokens
per second and the OFF runs (no board part) at 829–863, about 8% faster [TR:9-14, 25]. On Kaggle the Batch A round-3
pair ran at 745.7 (control) and 767.2 (arm) [BK:25]; the two identical candidate_pinned runs at 848 (the 32.22 re-run) and 834 (the 54.70 commit run) [EC:61];
across four same-config runs on different hosts the rate varied about ±5% (candidate 866, candidate_pinned 834,
start-retry 800, v37 754) [DF:13]. The stack behind those numbers: our quantization, NVFP4 routed experts and FP8
attention, the scored v2.2 calibrated on 976 windows with NVFP4 MTP experts and play-evaluated only [D4:101-102];
quantizing the MTP experts freed 3.37 GiB without redoing the main quantization [D4:103]; the runtime is Han Solo's
32-file overlay for vLLM e975732 ported by us to 0.31.0, plus our bounded KV-block copy, parallel shard prefetch and a
per-game clock fitted to load time [D4:104-105]. v2.1 against v2.2 on the older runtime scored 33.32 / 33.51 against
43.86 / 35.21 [VS:91].

Levers that moved tokens per second without a score: raising max_num_seqs to 25 gave +25% generation until the KV
cache reached 98.6% at about 10 minutes, after which prefix hits fell from 87% to 43% and generation to 250–400 tokens
per second with 11 requests waiting; no score [VS:59]. The host KV tier (kt1) lost prefix hits from 91% to 44% by
25 minutes and generation from 888 to 294 [VS:96]; RecoverSSM off alone ran at 372 / 335 against about 840–920 for
MTP [VS:97]; DFlash2 l4 was 2.3 times slower than MTP (391 / 358 against about 945 / 880) [VS:94]. Concurrency 10 ran
at 714.6 against 773.7 tokens per second and scored 39.08 against the pool's 39.06, n = 1 [VS:58]. The reasoning-effort
row, on the older runtime, is the clearest statement that tokens and score are different currencies: xhigh 43.86 /
35.21 (n = 2), medium 21.70, low 8.41 (n = 1 each); lower effort buys more actions and far fewer levels per action
[VS:86].

Levels per token, across 43 full-budget runs: timed runs span 13.8–19.9 levels per million tokens, and identical code
gave 18.96 (the 54.70 run) and 14.55 (its 32.22 re-run); no-echo 7.6–8.6; untimed R0 6.69 [LT:4, 7-13]. The reading
in that note: levels per token is driven by depth and game mix, not by a lever we set; first levels are cheap and
later levels cost several times more, so a run that clears more early levels looks efficient and an untimed run that
keeps going on hard levels looks worst [LT:15-18].

The field's own numbers. Cakpo Vital, topic 754693, 11-01: "We now reach about **920 tokens/s** with all 22 lanes
busy, and around **1,260 tokens/s** in a decode-only test with 22 lanes"; across 10 runs that cleared the same level
with the same model and small serving and prompt differences, "the cost ranged from **17.6k to 228.9k tokens**";
"slower runs can cost 3× as many tokens as faster ones"; "raw inference throughput and effective problem-solving
throughput may be 2 different problems" [FA:754693, first post]. The Milestone 2 comparison, topic 744792: "All three
run Tufa Labs' Duck harness on the Tufa ARC-AGI Framework (TAAF) and serve Qwen3.8-Flash-Next" [FA:744792, first
post], with peak decode 946–1159 tokens per second [RG:86].

The one checkpoint comparison we ran: xz's public W4A16 checkpoint (Intel AutoRound, the same base model as ours) in
v36's harness on Kaggle, one commit run: 45.49 against the control pool's 39.06, Δ = +6.43, game-only [−2.38, +15.72],
sign 17/8/0, p = 0.108; levels 4.48 against 4.11, +0.37 [−0.19, +0.93]; NOT RESOLVED at n = 1 v 7, and the run-level
verdict is withheld at n = 1 [XZ:24-26; RL:23-24]. It scored below v36's own commit run (47.37) [XZ:27]. Under our
runtime it generated at 724 tokens per second against the controls' 746–785, about 5% slower, on the Marlin WNA16 MoE
kernel, with a KV pool 8% smaller (1,380,332 against 1,501,360) [XZ:9-15, 30]. It does not reproduce xz's 58.59; same
weights, our harness, 45.49: the gap is the harness and the clock [XZ:36-37].

### 5.2 Boots per nine-hour slot

A nine-hour slot buys one boot of a 180 GB model. Our model copy takes 10–28 minutes [EE:8]; the Batch A Kaggle pairs
loaded in 10.1 / 21.0 / 14.3 minutes (controls) and 21.7 / 19.7 / 15.9 (arms), and pair 1 was load-confounded: the
arm played 708 s less and tied [BK:22-24]. On 11-01 two runs with the pinned-memory fix had the same 27.1 GiB of
available host RAM at load start and still differed: candidate_pinned's server was ready at 604 s (weights 310 s),
v37+pinned's at 2,015 s (weights 1,671 s); the long load was the mount read on that session [HM:576]. The fix itself:
PyTorch's pinned-memory rounding had wasted about 33 GiB of host memory (the PLE table 95.4 → 128 GiB pinned)
[EC:25-27]; before it, vLLM logged 8.66–9.85 GiB of available RAM at load start in all twelve audited runs [AD:45-46],
and loader idle of 64–459 s on the big shards tracked host headroom [EC:27]. The same notebook version booted to first
action 265 s apart on two days (954 s and 689 s), and the faster boot scored lower (42.89 → 34.04) [EC:77-82]. Load
time feeds the per-game clock on the hidden set directly: the scored-rerun clock fit sets each game's clock to
max(600, (32,400 − 600 − elapsed) / ceil(n_games/14)), so a 47-minute load gives 3,623 s per game and a 15-minute load
3,863 s; no hidden run with another limit exists, and scored-run logs are invisible [VS:57]. At 14-way sharing an
action costs about 12 s per game (C1 11.7, v36 12.8) [HM:552].

The forum's numbers are of the same kind. xz, topic 752485, 10-25: "my inference server takes anywhere from 10 to 60
minutes to start, with the same notebook and inputs"; "the instances that start slowly also run about 10% slower
afterwards" [FA:752485, first post]. Leszek Góra, topic 754206, 10-30: a single-threaded page-fault copy of about
102 GB of PLE rows made the model ready at 23.1 minutes; split across threads, "ready at 9.1 and 10.1 min",
load_weight 1134.66 s → 297.21 s; "it buys window, not accuracy; what the recovered time is worth depends on what your
harness does with it" [FA:754206, first post]. Jeroen Cottaar (rank 2 at archive time), topic 753843, 10-29: "the
notebook itself starts only ~40 minutes after the container starts", measured by erroring out when /proc/uptime is
over 20 minutes at start; "our successful submissions (without the /proc/uptime killswitch) run for 9 hours, not 9
hours and 40 minutes"; the delay also happens for an empty notebook with no datasets attached, on both container
images, from the US and from Europe [FA:753843, comment 3546721 and reply 3547123]. xz (rank 3) in the same thread:
"I just start the games at 10min mark regardless of whether server is started and use RESET every 7min. There isn't
anything I can do about the data loading time" [FA:753843, comment 3546725]. Yi-Chia Chen (rank 1): "My scores have
also been fluctuating quite a lot. I'm not sure whether this is related to the infrastructure issues or simply high
run-to-run variance" [FA:753843, comment 3546722].

The start guard belongs here because a boot is also 110 game starts. The hidden-path audit of the game loop (11-01)
found that taaf/benchmark.py starts all 110 games one after another before any play (BM:150-153), that nothing
catches a per-game failure, that a start fails whenever arcade.make returns None, and that the enclosing try has only
a finally, so one transient gateway failure zeroes the whole submission; the finding is inferred from code, not
observed, and whether 57680782's "system error" was this cannot be checked [AL:25-42]. The arm built on it,
start-retry: ARC3_START_ATTEMPTS=4 (arcade.make retried with 5/10/20 s backoff) and ARC3_START_SKIP=1 (a game that
still cannot start is recorded crashed at score 0 and the rest play), with a scorecard hold (4d63b91) so that a failed
first game does not close the shared scorecard [SR:8-11, 17-24]. Test status: unit tests, including a real 110-game
Benchmark.run with one unstartable game (crashed + score 0, 109 others start and finish) and a scorecard test that
fails on the earlier commit a2e31b2 and passes on 4d63b91 [SR:10-11, 22-25]; on the public 25 every start succeeds, so
a commit run cannot exercise the path, and the hidden-run benefit rests on the code and the tests [SR:13-15]. It is
carried in candidate_pinned (848f336: pool clock, stall 1,500 s, minimum share 600 s, start retry,
ARM_PINNED_ROUND_MB=1024) [notes/prestate_x4_local_2026-11-01.md:10] and therefore in 57886730 and 57902610
[D4:129-130].

### 5.3 Slots per day

The rules: one submission per day, two final submissions selected at the end [F:179]. With one submission per day a
single A/B is not measurable [RC:702]. A probe run on the hidden set is a submission too, and the thread noticed what
that allows: "These probe runs doesnt sacrify the submission, right? So you can still resend next one at same day?
That is potential a huge leak of information from private set" (Grigoriy Zatravkin, rank 6) [FA:753843, reply
3546743]. A daily slot with a noisy scorer is a draw, and the board keeps a team's best. Tamrazov's "The AGI Boys"
notebook has 86 versions; V78–V86 are nine identical-code reruns, one a day, and the two visible scores are V83 =
35.35 and V86 = 29.01, so identical code spans at least 6.3 points on the hidden public half and daily resubmission
keeps the maximum: selection on noise, on the board itself [HM:553]. Sixteen public copies of Franzen's notebook are
visible; the unchanged ones score 25.33, 26.73, 27.28, 28.06, 28.41, and the lightly edited ones 24.28–32.38 [HM:553].
Our own account made the same move once, between configurations: candidate_pinned was chosen over v37+pinned on 54.70
against 40.74, one commit run each, a gap inside the identical-code spread; the ordering between the two configs was
never established [EC:65; HD:83]. The final selection (two different configurations; the better private score counts)
was made on that understanding [HD:86; D4:132]. After the deadline Kaggle accepts late entries, unranked; the first
scored 19.37 on candidate_pinned; the daily limit for late entries is unknown, and the two replicates the investigator submitted
concurrently never appeared in the list [LS:3-6, 26, 43-48; HD:177, 185]. The number of draws a team gets per day is
set by this rule and by how many accounts can submit for a team; we found no statement of a team-size rule in our
files, so that arithmetic is not written here.

### 5.4 Forks per model

The fourth throughput is the number of copies of one notebook on the board. 57645104, the top score on our account at
24.54, is Franzen's submission code via Tamrazov's copy: Kaggle's history shows the submitted version V1 as "Diff +0 -0"
against its parent, Tamrazov V86, and Tamrazov V86 against dfranzen V3 differs in three hunks, all in the commit-run
branch; the TRUE_SUBMISSION branch is identical (concurrency 120, per-game clock 532 × 60 s, n_passes 1, the same
Intel W4A16 AutoRound model and Albucino drafter, the same SGLang serving) [HM:554]. That code's visible-half runs:
24.54 (the investigator V1 via Tamrazov), 29.01 (Tamrazov V86), 33.68 (dfranzen V3 rerun), 34.30 (dfranzen V1), 35.35 (Tamrazov
V83, best of ten identical reruns), a range of 10.8 points; its lowest is above our highest (v36 20.44–21.85)
[HM:555]. The container image differs between Tamrazov and Franzen, and the write-up's 27.89 against the page's 34.30
is unexplained [HM:555]. Our account's top score is another team's [D4:132].

The public board on 10-30 (full CSV): 4,987 teams, median 1.99, p75 28.7, p90 31.3, 16 teams at or above 40, 7 at or
above 50; Chen 75.56, Tufa 70.02, xz 58.59, Turducken 56.02; Lord Han Solo, our harness lineage, 39.94 at #17; our
account #2011 at 24.54 (the Franzen copy), and our own method's best, 21.85, would sit about #2146 [HM:525]. The
roughly 2,000 teams between 22 and 32 are the Duck/Franzen fork plateau [HM:525]. On 10-17 the same board had us at
19.52, rank 1,589 of 4,403, with Tufa 68.91, Chen 67.49, Han Solo 37.07, Franzen 36.86 [HM:243]. The Milestone 2
winners, all three on the Duck harness over TAAF serving Qwen3.8-Flash-Next, held 27.89, 23.84 and 22.53 on 10-01
[FA:744792, first post]. xz's climb is in the archive: on 10-25, "I've ported my solution to Kaggle (accelerator: RTX
PRO 6000) and am testing it before the deadline" [FA:752485, first post]; on 10-29, "I can't tell since I have no
previous submission to compare with", posted at rank 3 [FA:753843, comment 3546683]; the same day, Mark Barney's
"Congratulations on the climb!" [FA:752485, comment 3546839]; 58.59 on 10-30, with the same base model as ours under
W4A16 [HM:525]. Cakpo Vital: "climbed from **2,006th to 132nd (33.77)**" by optimizing the inference stack
[FA:754693, first post].

### 5.5 The maximum

The board's top is a maximum over these four throughputs: tokens per second on the card, boots that fit the nine
hours, draws per day, and copies per model. None of the four is reasoning. That is our reading of our own
measurements and of what the leaders wrote about theirs; it is not a claim about what any individual team did to reach
its score. The thesis is already in the field's own words, "generating more tokens faster doesn't necessarily mean
solving more games faster" [FA:754693, first post], and the evidence file's framing note stands: these are evidence of
what the metric selected for, not complaints about the organisers [EC:34-36].

---

## Sources used

- notes/paper_draft_v4_2026-10-27.md at commit 61d9b71 (v4.7), via `git show`
- notes/run_level_ci_results_2026-11-02.md
- notes/prestate_run_level_ci_2026-11-02.md
- notes/paper_evidence_clock_2026-11-01.md
- notes/prestate_no_echo_2026-10-28.md
- notes/noecho_local_result_2026-10-29.json
- notes/batch_a_kaggle_result_2026-10-27.md
- notes/batch_a_local_result_2026-10-27.md
- notes/prestate_batch_a_2026-10-26.md (line 78 only)
- notes/tower_onoff_local_result_2026-10-27.md
- notes/tower_native_local_result_2026-10-28.md
- notes/noise_structure_2026-10-27.md
- notes/v36_settings_evidence_2026-10-31.md
- notes/levels_per_token_2026-11-04.md
- notes/prestate_game_room_2026-10-28.md
- notes/game_room_s_local_result_2026-10-28.md
- notes/prestate_hidden_predictor_2026-10-28.md
- notes/xz_w4a16_kaggle_result_2026-10-30.md
- notes/prestate_experience_efficiency_2026-11-04.md
- notes/prestate_late_submissions_2026-11-02.md
- notes/hidden_path_audit_loop_2026-11-01.md
- notes/hidden_path_audit_load_2026-11-01.md
- notes/prestate_start_retry_2026-11-01.md
- notes/prestate_x4_local_2026-11-01.md (line 10 only)
- notes/prestate_dflash_fair_2026-11-01.md (line 13 only)
- notes/paper_asked_the_model_2026-10-15.md (lines 55-62)
- notes/kaggle_working_recipe.md (line 702)
- notes/research_grid_encoder_2026-10-30.md (line 86)
- notes/reasoner_doubter_findings_2026-09-03.md (line 179)
- notes/project_arc_handoff_1006.md (repository copy, 11-01 onward)
- /home/ignaz/.claude/projects/-home-ignaz/memory/project_arc_handoff_1006.md (memory copy, for 10-26 to 10-31:
  lines 243, 496, 518, 522, 525, 531, 546, 552-555, 575-576)
- notes/forum_archive/INDEX.md; notes/forum_archive/753843.json, 754206.json, 754693.json, 752485.json, 744792.json
- notes/forum_754206_ple_copy_2026-11-01.md and notes/forum_754693_faster_machine_2026-11-01.md (read; the quotes above
  are taken from the JSON archive, not from these)

## Could not verify

- A team-size rule (members per team, or submissions per account per team). Looked in
  notes/reasoner_doubter_findings_2026-09-03.md §10 (lines 170-190), notes/kaggle_working_recipe.md,
  notes/paper_outline_2026-10-03.md, notes/paper_outline_v2_2026-10-26.md and the forum archive index tags. Not found;
  5.3 says so and writes no arithmetic on it.
- A run-level (cluster) interval for either room. Not in notes/run_level_ci_results_2026-11-02.md (rows 9-14) and not
  found elsewhere in notes/. The rooms' intervals are game-only as recorded.
- A result note for the local Room G-c triple (gc1-gc3). No notes/game_room_c_local_result*.md exists; the numbers
  (42.50 / 37.24 / 45.81; −0.35 [−5.63, +4.84]) come only from the memory handoff line 496 and no JSON was found.
- The handoff entries from 10-26 to 10-31. notes/project_arc_handoff_1006.md in the repository begins at 11-01 10:55;
  the earlier entries were read from the memory copy (path above), which the repository does not track.
- Cakpo Vital's rank: the archived JSON's first-message field says 38, notes/forum_754693_faster_machine_2026-11-01.md:4
  says 138 at save time, and the post body says "132nd". Not reconciled; no rank is stated for him in the text.
- Leszek Góra's rank: the archived JSON says 63, notes/paper_evidence_clock_2026-11-01.md:16 says #57. Not reconciled;
  no rank is stated for him in the text.
- Cottaar's delay: notes/paper_evidence_clock_2026-11-01.md:8 summarises it as "~40-50 min"; the post itself says
  "~40 minutes" (comment 3546721). The text quotes the post.
- xz's 58.59 and the 10-30 board figures come from the memory handoff's read of the full leaderboard CSV (HM:525); the
  CSV itself was not re-read (no network in this session) and is not in notes/.
- The no-echo pre-statement's exploratory rows (b) first compaction time and cliffs per game, and (c) between-run
  divergence at compaction events (notes/prestate_no_echo_2026-10-28.md:29-32): no result for them was found in that
  file's result blocks or in notes/noecho_local_result_2026-10-29.json.
- The cause of 57680782's "system error": notes/v36_settings_evidence_2026-10-31.md:7-8 and
  notes/hidden_path_audit_loop_2026-11-01.md:41-42 both say it cannot be checked.
- Whether the 38.58 Kaggle run is byte-identical to the 54.70 / 32.22 notebook: notes/paper_evidence_clock_2026-11-01.md:64
  lists it under "this exact notebook" with the qualifier "pre-pinned candidate+guard", and the memory handoff line 575
  names it as the candidate at fa326e3; the text treats it as the pre-fix candidate, not as a third identical run.
