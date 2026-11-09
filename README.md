# From Synesthesia to Lobotomy: What a Benchmark on a Clock Can and Cannot See

ARC Prize 2026, Paper Track entry. Same model, same harness, clock off: on ARC-AGI-3 this model's score is bounded by time
before it is bounded by capability. This repository is the record behind that claim, less the project's working log: every run we made from September 3 to the
deadline, the scripts that turn those runs into the paper's numbers and figures, the pre-statements written before the
numbers landed, the notebooks that ran on Kaggle, the harness, and the paper itself.

## The finding, in one paragraph

Under the submission setup (a 65-minute clock per game, fourteen games sharing one GPU), three of every four games
end at the clock; the median such game cleared its last level three-quarters of the way through its time, and 45% cleared one in the final fifth. Take the clock away and change nothing else, and the same model
clears 13 to 16 of the 25 public games instead of 6 or 7: +1.88 levels per game, 95% CI [+1.17, +2.63] (paired by
game, resampled over runs then games), with the score itself +15.3 [+5.2, +25.2], at n = 4 untimed runs against 4
timed controls. Within the first thousand actions the two regimes reach each level at the same rate (level 5: 0.64 against 0.64, 300 and 100 games); the
difference lives in the actions the clock never allows. Every configuration change we tested under the clock, including
the one the paper is named for, came back NOT RESOLVED inside run-to-run noise that moves identical code by 20 points.
The one resolved result is negative: remove the model's echoed prior reasoning and it loses 30 points, so that echo is
the agent's working memory. The paper is `paper/paper.md`; the 1,500-word Kaggle write-up is `paper/writeup.md`.

## Layout

```
paper/            paper.md (long form), writeup.md (Kaggle, 1,500 words), figures/, cover/,
                  prestatements/ (what we said would count, before each result), results_notes/ (the lab notebook the
                  paper's source key cites, file by file)
results/          MANIFEST.json + one directory per run: results/<platform>/<tag>/
                    local/    this workstation's RTX PRO 6000 (Max-Q), the controls and every arm
                    vast/     rented RTX PRO 6000 boxes (the untimed replicates)
                    kaggle/   our Kaggle sessions (the submissions, their controls, the rooms, no-echo, xz)
                    archive/  September 3 to October: model comparisons, the board-tower runs, the A/Bs, the proofs
                  each run: synesthesia/benchmark.json (per-game results and the action history), stdout.log and the
                  launcher log (the periodic summaries), the executed notebook (out.ipynb), the switch/serving/commit
                  records (taaf_setup_env.json, vllm-watchdog.json, git_status.txt). Logs over 1 MB are gzipped.
                  Left behind, listed per run in the manifest: per-game request logs, pickles, cache diagnostics,
                  transcripts (tens of GB; available on request).
analysis/         the scripts that produced every number and figure in the paper, repointed at results/ through
                  results_index.py; `reproduce.py` regenerates them into analysis/out/
notebooks/        generator/ (build_synesthesia_notebook.py and its cells: one generator, switches per arm) and
                  staged/ (the notebooks the counted runs used, as pushed to Kaggle)
harness/          the game-playing harness: Tufa Labs' tufa-arc-agi-framework and ARC3-Inference (MIT), with the
                  changes recorded in git_status.txt per run, bundled exactly as the Kaggle dataset the runs mounted
runtime/          the vLLM 0.31 overlay (Han Solo's lineage, rebuilt for Python 3.13) and its patch set; no wheels
model/            the quantization scripts and calibration set for our v22 build of Qwen3.8-Flash-Next (the weights These are the scripts as they ran on the build host; the absolute paths in them (/home/...) are that host's and are left as they ran.
                  are a Kaggle model, 180 GB; not in git)
```

## Reproducing the numbers

```
python3 analysis/reproduce.py         # from the repository root; writes analysis/out/ (comparisons JSON, figures PNG/SVG/JSON); exits 1 unless all MATCH; versions in analysis/requirements.txt
```

`results_index.py` maps each run tag to its directory and transparently gunzips what it needs into `results/.cache/`.
The headline comparison is `compare_arm_groups.py --cluster` on the runs' `stdout.log` files; the per-game figure and
the clock curves read `benchmark.json` and the launcher logs. Every figure's data is also committed as JSON beside it.

## Scoring, and what the runs are

ARC-AGI-3 scores each level by (human actions / agent actions)² and each game by the level-index-weighted mean of
those with unreached levels counting zero, so a game ended early loses the weight of every level it never reached. Our runs play the 25 public games; the hidden
set is what Kaggle scores. Tags: `r2_9300`, `r3_9300`, `r4_9300`, `r6_9300` are the timed controls (the submission
configuration, 9,300 s job budget); `r0c14`, `r0c14b` (local) and `r0x1`, `r0x2` (vast) are the same configuration
with the clock removed; `r5*` runs use the model's own vision tower instead of the student; `bo*`, `na*`, `ne*`, `ba*`,
`gs*` are the arms of §3 (tower off, native, no-echo, Batch A, the game rooms). `results/MANIFEST.json` gives every
run's games, score, actions, harness commit and the switch line the notebook printed at start.

## Who did the work

Cody Whatley, MD, MPH, the investigator, asked the question, decided the direction, ran the Kaggle account and paid
for the compute. The harness, analysis, notebooks and paper were designed, built and written with him by two Claude
instances (Anthropic) running in persistent sessions over the project (tiered-compact and a custom MCP memory
server); the paper refers to them as CL1 and CL2, to a
third instance whose review produced the reasoning-echo hypothesis as CL3, and to two instances with one contribution
each as CL4 and CL5 (CL, so that the labels cannot be read as the Kaggle control-run tags C1–C7). Reviewer instances (Codex; Claude instances reading cold) are credited in the changelogs under
`paper/results_notes/`. A local Qwen model (Q1) played the games in August's self-identification tests. These labels
are how the published text refers to the AI participants; the code and the raw run logs under `results/` carry the
sessions' own names (the room texts are keyed `cody` and `sakshi` in the harness prompts, and run tags such as
`room-s-k1` descend from them). The labels are contribution credit, not legal authorship. The harness lineage is Tufa
Labs (framework) to Lord Han Solo (vLLM overlay, public build) to us; the Milestone 2 code released by dfranzen is the
notebook our early submissions copied, as the paper's §5 records.

## License

MIT, see `LICENSE`. The harness is Tufa Labs' under the MIT License its package metadata declares; everything else
is © 2026 Cody Whatley under the same terms.

## Pre-statement history

The `main` branch is a publication snapshot; its commit history is a publication log. The branch `prestatement-history` carries the lab repository's dated commits for the forty pre-statement files in `paper/prestatements/` (150 commits, 2026-10-26 to 2026-11-08, as written, the collaborators' names included), with the published versions as its final commit. `git log --diff-filter=A --format=%ci -- prestatements/<file>` on that branch gives the date a pre-statement was first written.
