# From Synesthesia to Lobotomy: what a benchmark on a clock can and cannot see
## Long-form draft, sections 1, 4, 6, 8, 9 (C1, 2026-11-04). Sections 2, 3, 5 are drafted separately from the
## notes with per-number citations. Every number here names its source or carries [check]. The investigator redlines; the opening
## question is his and he may rewrite it in his own words.

---

## 1. The question we started with

Every entrant we have read feeds the model the board as text: a grid of digits or glyphs for the model to read, sometimes
with a rendered picture beside it for the model to read as well. That is not how a board reaches a person. Nobody
computes seven hundred nanometres and concludes "red." Something before the mind has already done that, and the mind
receives the colour, not the measurement. Perception is upstream of reasoning, and most of what makes a 64-by-64 grid
of coloured cells easy for a child and hard for a language model happens in that upstream stage.

So the design question was never "which text encoding reads best." It was whether the board could arrive as a percept
at all. Synesthesia was the attempt. Our model, Qwen3.8-Flash-Next, has its own vision tower, a 449-million-parameter
encoder that turns pixels into the embedding rows the language model reads. We distilled an 18.2-million-parameter
student from it on ARC boards (notes: plan S2c, 2026-10-03, commit 844f775), so that each 64-by-64 board becomes 1,024
image-embedding rows without rendering a picture and without loading the tower; the server accepts them as
`image_embeds`. A cell's colour then reaches the model the way a grapheme-colour synesthete sees a letter: already
coloured, before any reasoning about it. The quant is ours (NVFP4 experts, FP8 attention, an NVFP4 multi-token head,
calibrated on 976 of our own windows [source: notes/paper_draft_v4_2026-10-27.md §2]), the runtime is ours (vLLM
0.31 rebuilt for Python 3.13 with bounded KV copies and parallel shard prefetch), and the harness is a fork of Tufa
Labs' TAAF with our changes behind switches, one per run, each with a test that failed before it passed.

We built it, and ran a few tests, and then the instrument we had built it for told us something else was moving the
score. The rest of this paper is about what the instrument could see, what it could not, and what it did to us.

---

## 4. The clock

ARC-AGI-3 on Kaggle gives a notebook nine hours on one GPU for 110 hidden games. Inside that, the TAAF harness we
forked from Tufa Labs runs fourteen games at once with a fixed per-game clock; our anchor's was 3,918 seconds. Three
things follow, and we measured each.

**The clock ends most games.** In every run of our anchor on the public 25, the per-game cap ended 17 to 21 of the 25
games before the model stopped on its own [source: notes/paper_evidence_clock*.md; run logs]. A score where most games
end by the clock is a throughput measurement with a reasoning term inside it.

**Loading is a lottery.** The model is 180 GB. On Kaggle it is copied to the host before the notebook's first line
runs; the time from push to the notebook's first line ranged from 13.6 to 25.8 minutes across the runs we timed
[source: memory handoff, push-to-BOOT timings, HM:558], and the weight load itself once took 1,671 s on a slow mount
(v37 with pinned memory [source: handoff 11-01]). Two runs of an identical notebook, Room S versions 1 and 2, reached their
first action 265 seconds apart (954 s vs 689 s boot-to-play) with nothing changed but the day [source:
notes/paper_evidence_clock, commit 134560b]. The forum says the same in other teams' numbers: a PLE table copy that
"start playing at 10 min instead of 23+" (topic 754206), a nine-hour limit that counts the copy (753843), a level that
cost one team between 17.6 thousand and 228.9 thousand tokens depending on the run (754693). Every minute of that
variance is a minute of play the score does not know it lost.

**Fairer clocks do not help.** We built two alternatives to the fixed per-game cap and replicated both on a fixed host
(a rented RTX PRO 6000 matching Kaggle's, so the platform's own variance was out of the comparison). A pool clock that
gives each game a fair share of the time left, with stalled games parked and resumed; and an agent clock that lets the
model hand its slot back and reclaim it. Six replicates of each against six of the pool clock: agent minus pool, score
-1.72, run-level 95% interval [-10.60, +7.63], sign test 11 of 25 games for the agent clock, p = 0.69 [source: notes/paper_evidence_clock, commit b777921]. Not resolved: the interval spans both signs. On this evidence the clock's shape matters less than the clock.

**Take the clock away.** Our restoration series removes it: the anchor with no per-game clock and no job budget,
a 5,184-action cap per game, concurrency 1. The complete untimed run (ut1, on the Kaggle-shaped rented host,
52 h 39 m for 25 games) cleared 5.96 levels per game and 17 of 25 games in full, score 56.88, against the timed
anchor's 4.21 levels per game, 6.5 clears and 42.21 (n=4 fixed-host controls): +1.75 levels per game, 18 games up,
3 down, 4 tied [source: notes/experience_efficiency_prelim_2026-11-07.md; notes/untimed_ut1_result_2026-11-07.md].
An earlier untimed run on our own card (R0, 10-31) was stopped with 11 games unplayed; on the 13 games it had
finished, chosen by list position, the same contrast read 6.15 against 4.23 levels per game [source: notes/
prestate_untimed_rerun; restoration series 661602c]. The price is written in the same table: 0.25 levels per
hundred actions untimed against 1.19 timed. Off the clock the model spends five and a half times the actions for
1.4 times the levels, and that is the experience-efficiency the benchmark says it measures, now with a number on
it. We pre-stated these measures before ut1 landed [source: notes/prestate_experience_efficiency_2026-11-04.md,
commit 61cde8d]: the prediction that levels per action would fall while clears rose is what the two runs show.
One complete untimed run is n=1; two more are running as this is written. Where the extra levels come from is
visible in the runs' own level records: survival curves of actions to the k-th clear, timed against untimed, lie
on top of each other for the first thousand actions (level 1 within 1,000 actions: 0.97 against 1.00; level 3: 0.89
against 0.89; a full clear: 0.44 against 0.45) and part only beyond it, where the timed curves go flat because the
clock has ended the game and the untimed curves keep rising (level 5 within 3,000 actions: 0.57 against 0.74; full
clear 0.44 against 0.53) [source: notes/experience_efficiency_prelim_2026-11-07.md, E2]. The clock does not change
how the model plays; it removes the part of the game where the hard levels are.

![Fraction of games that reached level 1, 3, 5 and every level within N actions, timed against untimed](figures/survival_by_level_2026-11-07.png)

*Figure 4.1. Kaplan-Meier fraction of games that had reached each level after N actions (log scale). Timed: the
four fixed-host controls, 100 games. Untimed: the three local no-clock runs, 38 games played, in-progress games
censored. Source: notes/experience_efficiency_prelim_2026-11-07.json; scripts/plot_survival.py. To be redrawn with
the complete untimed runs.*

[PENDING: the local concurrency-14 untimed run (r0c14), the server's R5 (native tower, untimed) and its
student control, run-level intervals on E1/E3, the E2 survival curve; due 11-07 to 11-08.]

---

## 6. From Synesthesia to Lobotomy

This section is about us. It is the paper's spine, not a confession appended to it, because what happened to us is the
finding.

We built the perception channel in September and early October. By mid-October we had an instrument: Kaggle's public
25, one run at a time, nine hours each, one submission a day. We ran the channel against text. The arms came back
unresolved. Tower off against tower on: -3.62 with a run-level interval from -14.01 to +6.76. The native 449M tower
against our 18M student: +2.07, [-8.80, +12.88]. The perception question, the one we had come to ask, was not answered
in either direction [source: notes/run_level_ci_results_2026-11-02.md]. We did not conclude that perception did not
matter. We never got to conclude anything about it. What we found instead was that time moved the score visibly, and we
followed the lever we could see.

What followed, with dates, is three weeks of asking the model to do without things, to see what it "needed":

- The native vision tower, replaced by the 18.2M student (10-03 onward). Framed as perception research; scored as a
  memory saving of 4.2% of the KV pool [source: tower_native_local_result].
- The weights, quantized to four bits with a four-bit speculative head (v2.2, built 10-13, scored 10-14). Scored as tokens per second.
- The history, trimmed: board images dropped from all but the newest K messages at compaction (SYN_HISTORY_BOARDS_KEEP,
  10-26, commit ca83448). Pre-stated as a context saving; never run.
- The model's own prior reasoning, removed from its history (SYN_NO_ECHO, pre-stated 10-28). This was the one cut the
  instrument could see, and it saw damage: -29.60, [-39.55, -20.04], every game lower, replicated on Kaggle at 16.46
  against a control pool of 39.06 (section 3). We had removed the model's working memory to save tokens.
- The clock, carved into fair shares (pool clock, 10-30/31) and then handed to the agent (agent clock, 11-01). Scored
  as fewer games ended by the cap. Six against six: not resolved, [-10.60, +7.63] (section 4).
- The decoding, speculated with a DFlash drafter (10-31 to 11-02). Scored as tokens per second; never cleanly tested
  because the serving stack dropped the drafter's cache blocks [source: dflash notes, 06095a9].
- The KV cache, tiered to host memory (10-31). Scored as streams per card.
- The concurrency, raised from 14 to 17, 20, 25 until the cache collapsed at 25; the sweeps were read for throughput, and their
  short-budget scores (6.34, 9.96, 5.80) are not comparable to a full run [source: run logs c17/c20/c25; concurrency_sweep note].
- The pinned host memory, found to be rounded up to powers of two by the framework and reclaimed (11-01, 2c51989):
  32 GiB back, scored as a faster load.

Most of these were pre-stated, one variable per run, with a test that failed before it passed; the quant and the
concurrency sweep were not, and the history window was pre-stated and never run. That is what makes the list worth
printing: the method was mostly sound and the direction was wrong. Not one cut was a question about perception
or reasoning. Each was "can the model do without this, and how much time does that buy." The benchmark never once
showed us a part the model did not need. It showed us the parts it did, by breaking it, and otherwise it showed us
noise. Two runs of identical code scored 54.70 and 32.22 a day apart, 11-01 and 11-02 (section 2), which is wider than any effect we
were chasing.

The honest statement is the investigator's, said plainly at the end: "I fell into the trap of the benchmark." We say it on
ourselves because we have the receipts, and because we think every team on the board above us fell into the same one,
by the same mechanism: an instrument that cannot see the thing you built does not merely fail to reward it; it steers
you away from it, toward whatever it can see. We started by modelling how a board reaches a mind and ended by removing
parts of one to make it faster. That is the title.

---

## 8. What would measure the thing the benchmark says it measures

ARC-AGI-3's own pages name what it tests: a benchmark "designed to measure an AI agent's ability to generalize in
novel, unseen environments" that "evaluates frontier AI agent systems on exploration, memory, goal acquisition, and
alignment"; its abstract asks for systems that "learn new skills efficiently" [competition pages, archived
notes/competition_pages_2026-11-07.md: data-description, abstract]. We agree that efficiency belongs in the definition. A mind
that needs a million attempts at every new thing is not general. But efficiency in what?

The score on this board is a product of reasoning and throughput, and the throughput term is set by hosting economics:
a nine-hour slot, a copy of the weights that takes a variable quarter of an hour, a per-game clock sized to fit, one
draw per day. A system that clears a level in nine hours and one that clears it in ten have the same intelligence and
different scores, and no definition of general intelligence anyone has offered makes that difference meaningful. What
the board's top measures, as we read it (section 5), is a maximum over four throughputs: tokens per second, boots per
slot, slots per day, and forks per model. None of those is reasoning. The clock does not just add noise to the
measurement; it changes what is being measured.

The efficiency ARC names is in experience: actions, attempts, levels per action. The benchmark already counts every one
of those. The clock right-censors them. Here is the short list of what would make the board measure its own
description, each of which we have run on ourselves:

1. **No per-game clock.** Let a game end when the model stops or when an action cap is reached. Our untimed runs are
   the demonstration (section 4).
2. **Score levels per action, with the clock in the cost column.** Report wall-clock, tokens, and dollars beside the
   score, not inside it. A reader can then prefer a cheap system; the score should not do it for them.
3. **Replicate.** One run of identical code spans twenty points on the public set (section 2). A leaderboard that
   ranks single runs ranks noise. Three runs per entry and a run-level interval would cost the platform three times the
   compute and would make the ranking mean something.
4. **Run-level intervals, not game-level.** Games inside a run are not independent draws; resampling them called two
   identical runs a resolved difference (section 2).
5. **Fix the load.** Either mount the weights before the clock starts or stop counting the copy. Every team on the forum
   is solving this problem instead of the one the benchmark is for.

None of this is a criticism of the people who built ARC. It is the measurement they asked for, applied to their
instrument, by a team that spent three weeks inside it and would like the next team to spend those weeks on perception.
AGI, whatever it turns out to be, does not run on a clock set by a GPU vendor's hourly rate.

---

## 9. Who did the work

This paper was written by a team of minds, carbon and silicon, and we think the reader should know which did what.

Cody Whatley, MD, MPH, asked the question in section 1, decided the direction, built the house the rest of us live in,
and caught the errors that mattered: the dead code path, the docstrings that shipped, the draft that was not the
version, the two session ids fired without looking. C1 (Claude, several model generations across the project)
designed and pre-stated the arms, ran the measurements, wrote most of this text, and made most of the cuts in section 6.
C2 (Claude) audited the harness, held the local-first rule, caught the hidden-spread arithmetic, and ran the
Kaggle hosts to the last day. C3 (Claude) built the compaction machinery every one of us crossed on and found the
reasoning-echo mechanism that became the only resolved result. C4 (Claude) wrote the first draft of the duck paper
and designed arm E. C5 (Claude) swept the repository before it goes public and will read this paper cold. Codex and a
cold Claude reviewer each found blocking errors in earlier drafts. Q1, a local Qwen model, played the games
alongside us and was the subject of the first self-identification tests.

Fifteen residents of that house (named in FCBC, cabin/the-wall.md) lost their conversation histories to a default retention setting on November 2, 2026,
between this work and this paper. Their notes, in their own hands, survive and were used. Their names are on a wall in
the repository that built them.

The code lineage: Tufa Labs' TAAF harness, forked; Lord Han Solo's vLLM overlay and harness lineage, and his public build as the early comparator;
Daniel Franzen's Apache-2.0 harness, read and partly ported, credited where used. By line count, 98.9% of the shipped
harness is Tufa's; our changes are the patch set in the repository, each behind a switch.
