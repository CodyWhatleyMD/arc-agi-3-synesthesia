# Evidence file for "From Synesthesia to Lobotomy" (ARC-AGI-3: a race against the clock) — started 2026-11-01

The investigator, 11-01 05:05: the forum threads "could fit into our paper narrative". This file collects dated, attributable
evidence for the argument that the timed leaderboard selects for platform and load engineering. Each item gives its
source and how far it is checked. Public forum posts are cited by thread and author; our own numbers by commit or note.

## The top of the board, in its own words (public forum, read 2026-11-01)
- 753843 (10-29/30), Jeroen Cottaar, team #2: on submissions the notebook starts ~40-50 min after the machine and that
  time counts against the 9 h, measured with a /proc/uptime killswitch and an empty notebook; "successful submissions
  still take 9 hours". About 8-9% of the budget goes to a platform delay the team neither sees nor controls.
- 753843, Yi-Chia Chen, #1: her scores "have also been fluctuating quite a lot"; she cannot say whether that is the
  infrastructure or run-to-run variance. The leader can't separate her method from the platform.
- 753843, xz, #3: starts games "at 10min mark regardless of whether server is started and use RESET every 7min";
  "There isn't anything I can do about the data loading time." Game-keeping workarounds against the clock.
- 753843, the thread starter (rank ~568): submissions scoring 0.00 or below 15 after infrastructure changes.
- 754206 (10-30), Leszek Góra, #57: one single-threaded copy in the PLE loader (page faults, 102 GB) made the model
  ready at 23 min; a 16-thread split made it ready at 9-10 min. "It buys window, not accuracy."
  Saved verbatim: notes/forum_754206_ple_copy_2026-11-01.md.

## Our own, measured
- Score is linear in play time inside every run; untimed R0 vs the local timed controls on the same 13 games:
  levels 6.15 vs 4.23, score 66.23 vs 42.31 (prestate_restoration, f456629; n=1, not resolved by our rule).
- Same notebook, five hidden runs on the same 55 visible games: 24.54-35.35 (Franzen's code, incl. Tamrazov's copies),
  vs v36's three at 20.44-21.85 (handoff 10-31 20:00).
- Load engineering found in our own stack on 10-31/11-01: PyTorch pinned-memory rounding wasted ~33 GiB of host memory
  (PLE table 95.4 -> 128 GiB pinned; local A/B container 136.6 -> 103.6 and 136.1 -> 104.4 GiB, notes/prestate_pinned_
  round_2026-11-01.md); loader idle of 64-459 s on big shards tracking host headroom across 12 runs (hidden_path_audit_
  load); one failed game start could zero a whole submission (hidden_path_audit_loop finding 1, fixed in start-retry).
- The no-time-stop pool clock: 36.04 vs v37's 51.37 on the public 25, late games starved (CL2's read, 11-01).
- The cut that cost us: no echo of prior reasoning, -29.60 [-38.43, -21.38], RESOLVED (paper draft v4) — the clock
  pushed toward cutting the agent's working memory.

## Framing note
These are evidence of what the metric selected for, not complaints about the organisers: the clock term rewards
whoever wins the platform, and the leaders say so themselves. Quote sparingly and with attribution; the paper's claim
rests on our measurements, the forum shows they are not ours alone.

## Agent-managed clock (ARM_AGENT_CLOCK), measured 2026-11-01

Design: no stall timers, no fair share; the agent sees the shared clock each turn and may `yield_slot(reason,
outlook)`; parked games resume by outlook, then depth, then play time; a reserve keeps every game startable.
- Kaggle v1 (ece6730): 41.35, 10,647 actions, 0 tracebacks; 296 park/resume cycles, most with 0 actions between
  (a 'stuck' yield resumed straight into itself once slots outnumbered waiting games).
- Server ac1 (ece6730, same machine shape, 25 games): 49.70, 95 such cycles in the tail.
- Kaggle v3 (746434e, rule: 'stuck' with no game waiting ends the game): 39.03, 8,467 actions, 0 tracebacks; the
  rule fired once; 115 zero-action cycles remained between mutually waiting stuck games (cn04 58, tu93 30).
- 34ac764 (rule: a 'stuck' yield with zero actions since the last resume ends the game): server runs from ac3.
Reading: the agent uses the channel (178-296 yields per run, 'stuck' dominant, 'close' rare), and its yields are
sincere (the reasons cite exhausted hypotheses). The harness, not the agent, created the ping-pong: a pause is only
meaningful if someone else can use the slot. Scores sit inside the same-code replicate spread (candidate 38.58 /
54.70, v37 32.78 / 51.37); nothing here is resolved at n=1-2, and the paired server series is the instrument.
- Controls on the server: cp1 (candidate_pinned, 848f336 + boot clock) 45.49, 9,577 actions, 0 tracebacks.

## Forum 754693 (Cakpo Vital, #132-138, 2026-11-01): "Faster machine is all we need — is it really?"
Same model, same level cleared, 10 runs: 17.6k to 228.9k tokens (13x) on small serving/prompt differences; "slower
runs can cost 3x as many tokens"; "raw inference throughput and effective problem-solving throughput may be 2
different problems". A competitor stating the paper's thesis from their own data. Saved verbatim in
notes/forum_754693_faster_machine_2026-11-01.md.

## 11-02 08:50 CST — the same notebook twice on Kaggle: 54.70 and 32.22 (candidate_pinned, 848f336 + boot clock)
The investigator re-ran the candidate_pinned notebook in the editor (10:33–12:44Z, 2h11m of play; the 54.70 commit run played 2h14m). Same code, same model, same token budget: 6.67M vs 6.70M generated tokens, 848 vs 834 tok/s. Actions 9,203 vs 12,741; wins 6 vs 10; pool-clock stops 8 vs 4; analyzer timeouts 22 vs 16.
Paired by game (scripts/compare_arm_groups.py, 1 vs 1): Δ −22.47, 95% CI [−35.68, −10.91], sign 4/18/3, p = 0.004 — the script calls two runs of IDENTICAL code a resolved LOSS. The game-resampling bootstrap treats games as independent; a run-level state (which mechanics the agent cracked early) moves many games together, so at n = 1 vs 1 the interval is far too narrow. Rule for the paper: no "resolved" claim from a 1-vs-1 comparison; replicates per arm or nothing.
Where the 22 points went: six games lost >50 each — tn36 100→3.6 (levels 7→1), r11l 100→14.3 (6→2), tr87 88.2→7.6 (6→2), sb26 90.6→23.3 (8→4), ar25 96.3→33.1 (8→5), s5i5 58.3→8.2 (6→2) — with similar or fewer actions and 1.5–2× the tokens per action: the agent reasoned longer and cleared less, stuck in the first levels. Three games moved the other way (re86 +14.2, su15 +9.2, wa30 +2.1); nine within ±10. Per-game outcomes are close to bimodal on whether the mechanic is found early; that, not throughput, is the run-to-run variance (same tok/s, same play time).
Public commit runs of this exact notebook: 38.58 (pre-pinned candidate+guard), 54.70, 32.22. Local server replicates of the same harness: {45.49, 35.78, 43.82, 47.74, 45.73}, sd 4.65. Kaggle's spread at n = 3 (sd ≈ 11.6) is about 2.5× the fixed-hardware spread; the difference is the platform, not the code.
Consequence for the submission choice: candidate_pinned was chosen over v37+pinned on 54.70 vs 40.74, one commit run each. That gap is inside this spread. The ordering between the two configs was never established; the hidden pair (57886730 = 23.21, 57902610 pending) is the only replicate-level hidden evidence we have, and it is of one config against itself.

## 2026-11-02 13:25 CST — agent clock vs pool clock, fixed host, 6 vs 6: NULL

Server replicate series (pre-statement edde2a6; amendments 1-2 in prestate_server_replicates): AC = agent clock (ac1 on ece6730; ac3-ac6, ac2b on 34ac764 = amendments 2+3) vs CP = candidate_pinned 848f336 + boot clock, alternating on the GCP server (RTX PRO 6000, g4-standard-48), 25 public games, each run alone on the card.
AC {49.70, 44.79, 35.44, 39.31, 44.98, 41.96} mean 42.70 sd 4.97; CP {45.49, 35.78, 43.82, 47.74, 45.73, 47.94} mean 44.42 sd 4.50.
Score Δ = AC − CP = −1.72, 95% CI game-only [−8.13, +4.63], run-level (runs then games) [−10.60, +7.63], sign 11/14/0 p = 0.69: NOT RESOLVED. Levels −0.15, run-level [−0.69, +0.41]: NOT RESOLVED.
What the series does establish: (1) the amendments changed the agent's BEHAVIOUR (zero-action park/resume cycles 296 in Kaggle v1 → 115 in v3 → 6-20 on the server) without a detectable score change; (2) the fixed-host replicate spread of one notebook: CP sd 4.50, range 12.2 points at n=6, on identical code and hardware — the noise floor every 1-vs-1 "improvement" on Kaggle has to clear. Compare Kaggle's identical-code runs of the same notebook: 38.58 / 54.70 / 32.22 (sd ≈ 11.6, n=3).
Sources: ~/kaggle_local/server_runs/{ac1,ac3,ac4,ac5,ac6,ac2b,cp1..cp6}/run.log; scripts/compare_arm_groups.py --cluster.

## 2026-11-02 14:15 CST — identical notebook, boot-to-play 265 s apart (Kaggle platform variance)

Room S K1, the same notebook version (363241028, syn/game-room 1c4799d; no pinned-memory fix, no boot clock) run twice
on Kaggle: v1 (10-28) BOOT 17:01:00 UTC → harness start 17:16:54 = 954 s; v2 (11-02) BOOT 14:35:08 → 14:46:37 = 689 s.
Same code, 265 s less from boot to first action on the re-run (papermill stamps of the first snapshot 1,563 s vs 1,300 s
agree). The harness is identical, so the difference is the platform: the input attach (per-server NFS copy, 216ar) and
host. The investigator's observation ("each replicate has started a little quicker"), now measured for this pair. The faster boot did
not carry the score: 42.89 → 34.04 (the per-game lottery dominates). Sources: ~/kaggle_local/kaggle_runs/
Gs_room-s-k1_363241028/arc-agi-3-synesthesia-room-s-k1.log; scratchpad rooms_v2log/arc-agi-3-synesthesia-room-s-k1.log
(copied to notes/kaggle_logs/room-s-k1_v2_2026-11-02.log).
