# Verification of notes/paper_long_draft_2026-11-07.md, 11-07 (CL2, lane 1; report only, applied on CL1's say)
Scope (CL1 11-07 04:06): what the 11-04 table (notes/paper_long_verification_2026-11-04.md) did not cover:
§4 as rewritten 11-07, §5.6 + every [W1], the competition quotes, the assembly. Line numbers refer to the draft as of
2425fb3. Verdicts: WRONG / UNSUPPORTED (no source supports it) / UNCLEAR (source supports less than the text says).

## Batch B: §5.6, every [W1], the competition quotes (source notes/forum_archive/755795.json; live pages re-fetched 11-07)
The competition quotes are not in §1 (unchanged since 11-04) but in §7 l.600-603 (old §8, e94f04a): verbatim against
notes/competition_pages_2026-11-07.md, which matches the live data-description and abstract pages.

| line | claim | source | verdict | suggested text |
|---|---|---|---|---|
| 349-351 (§4) | "The public winner's own account says the same of its base model: nearly all of its remaining loss sat in stages it could not solve" | W1 overview item 4 ("most of the remaining score loss"), §4.1 (18-20 of 20-23 points "from stages it could not solve at all") | UNCLEAR, the substantive one | "nearly all" is defensible from §4.1's 18-20 of 20-23 (the overview says "most"). The overreach is "says the same": §4 argues the CLOCK removes the hard levels; W1 says its model "could not solve [them] at all" with every game given the full 9 h (110 concurrent), i.e. a capability gap, which it trained for. Suggest: "The public winner's own account puts its base model's remaining loss in the same place, stages it 'could not solve at all' [W1, §4.1]; it treated that as a capability gap and trained for it, at a cost in action efficiency [W1, §4.2] (section 5.6)." |
| 532 | "against our 830 and 14 games on the same card" | none in the sentence; l.41 "848 against 834" [EC:61; HM:576], l.143 "829-863", l.308 "fourteen games" | UNSUPPORTED (no citation) | cite, e.g. "our ~830-850 [EC:61] and 14 games (section 4)". Definitions match: W1 3550043 = total generated tokens / 2 h on Kaggle; ours = generated tok/s over job wall-clock. |
| 543-544 | "the winning entry, which measured its own cuts and recovered from them" | W1 §2.1, §4.2; 3550054 | UNSUPPORTED | W1 gives no loss/recovery numbers for pruning, quantization or QPAD; the only measured side effect is RL's efficiency (16%->26%), and on RL's score gain: "I don't have enough A/B testing to quantify the actual score gain" (3550054). Suggest "which recovered from its cuts by distillation and measured its RL pass's cost in a way we did not". |
| 529 | "INT3 weights" | W1 §2.1 | UNCLEAR | only the MoE experts are INT3 (attention/GDN block-FP8): "INT3 expert weights". |
| 533 | "a reinforcement-learning pass aimed only at hard stages" | W1 §4.1 | UNCLEAR | drop "only": "aimed at hard stages". |
| 539-540 | the model does the heavy lifting and "a ton of the work is just good engineering in harness+inference" | 3551152 | UNCLEAR (drops "most"; case changed) | original: "they do most of the heavy lifting. A ton of the work is just good engineering in harness+inference." Suggest: the model does "most of the heavy lifting" and "[a] ton of the work is just good engineering in harness+inference". |
| 541-542 | "compared against the Duck lineage ours descends from, which it beat on later stages" | 3550043 | UNCLEAR (self-report stated as fact) | "which, in the author's words, 'performed noticeably better than Duck, especially when it came to clearing later stages' (no numbers are given)". |
| 546-547 | "the winning move was to serve a hundred and ten games at once and to change models when the clock said so" | 3550054 | UNCLEAR (interpretation) | the author could not isolate RL's contribution, so the switch as "the winning move" is unmeasured even by him: "its author's design answer was ...". |
| 11 (§1) | "Every entrant we have read feeds the model the board as text ... sometimes with a rendered picture beside it" | W1 §1, §3.1 (game screens, animations, view_video; board encoding not stated) | UNCLEAR (low) | "every entrant whose board encoding we could read", or leave. |
| note | notes/forum_755795_winner_2026-11-07.md, §4.1 entry quotes "...with most of the remaining score loss coming from difficult stages it could not solve" | W1 | WRONG locator (note, not draft) | that clause is the overview's item 4, not §4.1; the draft's own [W1, §4.1] cites are fine. |

OK, 31 claims: §5.6 l.528-538 (two days after the deadline; same base model; 512->320; INT5 PLE; distillation; SGLang fork;
110 concurrent; 11.7M pool; ~3,800 tok/s; reviewer at 45 min; the verbatim "already had strong game understanding and
interaction capabilities"; 20-23 / 18-20; 16%->26%; 6 h + 3 h; 3550016 = Zatravkin rank 6; 3551085 arc-code); §4 l.351
(16%->26%); §7 l.600-603 (three quotes); rule statements l.81, 307, 607 (55 of 110 private games on the public half, 9 h
per notebook, one RTX PRO 6000 / g4-standard-48); §1 "18.2-million-parameter" student (18,221,696 for px16,
notes/paper_receipts_tower_2026-10-26.md:38; 27.2M was the px32 prototype); l.700 W1 key paths exist.
Batch B: 0 WRONG in the draft, 2 UNSUPPORTED, 7 UNCLEAR, 31 OK.

## Batch A: §4 "The clock" (l.305-365), §5.0 (l.368-377), Figure 4.1
Fork-verified against primary run data; the four marked [K] were re-checked by CL2 directly.

### The two that change claims (item 1 corrected 04:31: the count stands)
1. **l.311-312 and l.373-374, "the per-game cap ended 17 to 21 of the 25 games": the draft is RIGHT; my first reading
   here was WRONG and is retracted (CL1's check, 04:29, confirmed by CL2 on all 12 runs).**
   What stands: scripts/experience_efficiency.py:25 sums the CUMULATIVE `wallclock_seconds`, a bug that would count any
   unwon game as clock-ended. What does not: my recount (15-19) used the last ACTION's timestamp, which is not the game's
   end; a game can sit without acting until the clock takes it. The end is the per-game `final_wallclock_seconds`: in
   every one of the 12 timed runs (Kaggle C1-C7 + v36 anchor, local r2/r3/r4/r6) every unwon game has it at or above
   the 3,918 s cap (none below), so clock-ended = unwon = 18/21/17/20/20/19/20/19 and 19/19/18/18, i.e. 17-21 per run, as
   written. The sum happened to give the right count here. Fix the script to `final_wallclock_seconds` so it stays
   right on runs where that isn't so. E1-E3 never read `wall`.
2. **l.343-349 + Figure 4.1 caption l.355, the survival curves "show where ut1's extra levels come from": UNCLEAR, and one
   direction REVERSES on matched games.** (fork; recomputed with experience_efficiency.py, output identical to the
   committed JSON; not re-run by CL2)
   - The untimed curves are not ut1 (which has no per-level records); they are R0 + r0rep3 + r0rep4 = 38 plays of the
     FIRST 15 games in list order, while the timed curves cover all 25 games.
   - Restricted to the same 15 games: level 5 within 3,000 actions 0.52 timed vs 0.74 untimed (direction holds), but
     **full clear within 3,000: 0.57 timed vs 0.53 untimed (reverses)**.
   - Kaplan-Meier under heavy clock censoring: timed full clear reads 0.44 against an observed 26/100; only 3 of 100
     timed games pass 1,000 actions and none reach 3,000, so every timed value "within 3,000" is a carried-forward
     estimate, not an observation. Caption should say "estimated (Kaplan-Meier, censored at the clock, the cap and
     in-progress)" and the text should compare matched games or drop the full-clear comparison.

### Other WRONG
- **l.327, the pool clock ran "with stalled games parked and resumed": WRONG.** [K] cp1 run.log has 0 "park" lines and
  prints `pool time-based stop: stall_seconds=1500.0 min_share_s=600.0`; ac1 has 342. The pool-clock arm ended stalled
  games with the time stop; parking belonged to the agent clock.
- **l.339, "five and a half times the actions for 1.4 times the levels": WRONG.** [K] ut1 58,439 actions (stdout
  "total actions: 58439") vs timed r2/r3/r4/r6 10,643 / 9,264 / 9,128 / 7,186, mean 9,055 -> **6.45x**; 5.5x is
  against r2 alone. 1.42x levels is right. Same 5.5x in the prelim note.
- **l.374, "the investigator's sentence of 10-30 ... score = throughput x quality ...": WRONG attribution.** [K] HM:531: the investigator's words
  were "Our score gains are linear until the clock runs out"; the formula is the paper sentence written from them.

### UNSUPPORTED / UNCLEAR
- l.370, "Within every run the score is linear in play time": UNSUPPORTED as cited (EC:21 asserts it; the 11-04 table
  checked it against EC, circular). Fork measured it now: cumulative levels vs elapsed run time, R^2 0.965-0.984 over
  11 timed runs (r2-r6, C1-C7), 17-24% of levels in the first tenth. Levels as the proxy, not score -> "roughly linear".
- l.328, "Six replicates of each against six of the pool clock": wording; = six agent-clock runs (ac1, ac2b, ac3-ac6)
  vs six pool-clock runs (cp1-cp6). Numbers (-1.72, [-10.60, +7.63], 11/14/0, p = 0.69) OK.
- l.334, ut1 vs "(n=4 fixed-host controls)": crosses hardware (r2 Max-Q Workstation, ut1 Server edition); name both.
  Direction holds against the Server-edition Kaggle controls too (C1-C7 4.11 levels/game vs ut1 5.96).
- l.343, "two more are running": neither repeats ut1's condition (ut1 concurrency 1; r0c14 concurrency 14; R5 native
  tower at 14), so they do not make ut1's condition n=3.
- l.350, W1 "says the same" (also in batch B): his loss is a capability gap with no clock; "locates its loss in the same
  place".
- l.322, 754693 token cost "depending on the run": the source says "using the same model but with small serving and
  prompt differences": configuration differences, not run-to-run variance.
- l.318, 1,671 s load "[source: handoff 11-01]": right number and cause; cite HM:576.
- l.376 (and 517), "draws per day ... copies per model": not the §5 headings ("5.3 Slots per day", "5.4 Forks per model").

OK, about 30 claims (l.307-321, 328-342, 344-348, 352-357, 370-373), each recomputed: 110 games, 9 h, concurrency 14,
3,918 s, 180 GB; 13.6-25.8 min (HM:558); Room S 954 / 689 / 265 s (134560b); 754206 verbatim; 753843 fair; b777921,
661602c, 61cde8d exist (61cde8d committed 11-04 08:05, before ut1 ended 11-05 12:16Z: P1 pre-stated); ut1 concurrency 1,
cap 5,184, per_game_s None, 52 h 39 m, 5.96, 17/25, 56.88; timed 4.21 / 6.5 / 42.21; paired +1.75, 18 up / 3 down / 4
tied; R0 13 finished, 11 unplayed, 6.15 vs 4.23, 66.23 vs 42.31; E1 0.25 vs 1.19; every quoted KM value reproduces;
Figure 4.1 redraws identically from the JSON.
Batch A: 4 WRONG (the clock count is withdrawn: draft right, script bug only), 1 UNSUPPORTED (now measured), 9 UNCLEAR, ~30 OK.

## Batch C: the assembly (numbering, cross-references, source key, debris)
Clean: §1-8 sequential; all 14 internal cross-references land on the right content; Figure 4.1 files exist; 31 key
prefixes used = 31 key entries (0 unused, 0 missing); all 35 HM/HD line pointers carry the claimed fact; 50 paths, 18
hashes checked (e975732 is a vLLM commit, correctly labelled).

| line | what | fix |
|---|---|---|
| 3-7 | italic assembly banner is internal (source files, "cold agent", "NOT READY", "Section 7 (the rooms)" in 11-04 numbering) | strip before submission |
| 368-377 | §5.0 is titled "The clock" like §4 and repeats it (17-21 at both 311-312 and 373-374 with different sources; R0's 13-game subset first, which §4 now demotes behind ut1) | retitle (e.g. "Why throughput"), cut to a pointer "(section 4)", one source for the clock count |
| 523 | the rule closing §5 sits before §5.6, so §5.6 hangs outside §5 | move the rule to just before §6 |
| 699-700 | W1 appended after the key's closing rule in a different format | remove the rule at 699; "- W1 = notes/forum_755795_winner_2026-11-07.md (...)" |
| 360-361 | open [PENDING: r0c14, R5 + student control, intervals on E1/E3, the E2 survival curve]; Figure 4.1 already plots E2 survival | lane 3 fills it; reword "E2 with the replicates" |
| 292 | "a hidden replicate set of three is in the late-submission plan, not yet run [LS:18-20]" is stale | "was planned as a late submission and never ran" |
| 312, 320, 329 | EC cited as a glob/truncated path ("notes/paper_evidence_clock*.md", "notes/paper_evidence_clock, commit ...") and "run logs" | [EC:<lines>] + commits; name the logs |
| 337-338 | "[source: notes/prestate_untimed_rerun; ...]" truncated, split across lines | notes/prestate_untimed_rerun_2026-10-30.md as a key entry |
| 341 / 557 / 564 | by-path or shorthand cites where keys exist (EE, RL, NR) | [EE:..], [RL:..], [NR:..] |
| 574 | "[source: dflash notes, 06095a9]": 06095a9 PLANNED the l11 block-drop-off test; the finding is notes/dflash_followup_hits_2026-11-02.md (253329b: whole-block EAGLE drop + zero-hit collapses = 53-58% of the recompute loss) | cite that note + 253329b |
| 577 | "[source: run logs c17/c20/c25; concurrency_sweep note]" | notes/concurrency_sweep_2026-10-31.md + run paths |
| 317-318 | "[source: memory handoff ... HM:558]" / "[source: handoff 11-01]" (no line) | [HM:558]; [HM:576] |
| 320-322 | forum topics cited bare though FA keys exist | [FA:754206], [FA:753843], [FA:754693] |
| 24 | by-path cite of the v4 draft | [D4:<lines>] |
| 600-603 | competition quotes cite notes/competition_pages_2026-11-07.md unkeyed (these are the quotes; §1 has none) | key entry "CP = notes/competition_pages_2026-11-07.md" |
| 125 | "(Section 3)" capitalised | lowercase |
| 376-377, 516-517 vs 423/469/489, 610-611 | two vocabularies for the four throughputs | one set |
| 162-163/471-472; 257-258/400-401 | stated twice (one submission/day; 13.8-19.9 / 7.6-8.6 lv per M tokens) | keep one, point to it (low) |
| 97 | "paper draft v4.4" is internal | "an earlier draft [D4]" |
| 692-694 (HM) | 19 cites point into the memory handoff, which no repo tracks; any edit above line 496 shifts them | snapshot into notes/ and repoint HM |
| - | notes/forum_archive/INDEX.md (11-02) lacks 755795.json | regenerate (low) |

## Batch D (04:45): §2 under the investigator's rule, "a test run under a clock measures the clock"
Rule (via CL1, 04:41): clocked arms are evidence about the instrument and the cuts, not tests of what we built; model
claims rest on the untimed series. Draft as of 6eda5dc. Sentences that read a clocked arm as a capability measurement:

| line | sentence | why it crosses the rule | suggested |
|---|---|---|---|
| 129 (table, on/off verdict) | "17 of 24 decided games lower without the channel" | a directional reading of the channel from a clocked arm | keep the count, label it "under the clock; exploratory", not a channel effect |
| 130 (table, native verdict) | "excludes a student deficit beyond ~12.9 and a student advantage beyond ~8.8" | reads as a bound on the student's capability vs the native tower; under the clock an encoder that changes pace changes the score without changing play | "bounds the clocked-score difference to [-12.9, +8.8]; the capability comparison is the planned untimed R5 against ut1" |
| 140-141 | "The on/off and native rows measure the board part together with its prompt section and its history" | "measure the board part" | "measure the clocked score with the board part, its prompt section and its history changed together" |
| 145-146 | "Across the three channel states the point estimates order none < student <~ native" | a capability ordering read off clocked, unresolved arms | drop, or "the clocked point estimates order ...; not resolved, and not a statement about the channels" |
| 114-116 | "45% of a game's score variance is run-to-run luck in the shipped configuration" | it is the variance of what a run reaches before the clock | "... in the shipped configuration under the 3,918 s clock" |
| 117-119 | "the differences ... are in how far a run gets, not whether it starts" | true, and under the rule it is the clock's signature | "how far a run gets before the clock" (this sentence then supports §4) |
| 48-51 (low) | "stuck in the first levels"; "bimodal on whether the mechanic is found early" | "early" is relative to the clock | "found early enough for the clock" |
Not flagged: §2.1-2.3 and 2.6 (instrument variance, replicates, cost of resolution) are instrument claims and hold;
l.143-145 (OFF 8% faster, "the payload saving did not become score") is already a clock statement; §2.7 already keeps
the rooms' action-efficiency reading as a hypothesis.

### §3 (the one resolved result) under the same rule: what survives
§3.6 l.284-286 already scopes the claim to "this clock". The mechanism sentences (l.273-275 "the echoed prior-turn
reasoning is the model's working memory"; l.278-280 "the cut cost 29.60 points") read beyond it. New measurement
(CL2, 04:44; working_{ne1,ne2,ne3,r2,r3,r4,r6}_9300/synesthesia/benchmark.json, actions = history entries):

| | actions/run | levels/run | levels per 100 actions |
|---|---|---|---|
| no-echo ne1-ne3 | 5,822 / 6,264 / 5,810, mean 5,965 | 58 / 52 / 53, mean 54.3 | 1.00 / 0.83 / 0.91, pooled 0.91 |
| control r2/r3/r4/r6 | 10,643 / 9,264 / 9,128 / 7,186, mean 9,055 | 103 / 108 / 104 / 106, mean 105.2 | 0.97 / 1.17 / 1.14 / 1.48, pooled 1.16 |

Levels fall 48%: 0.66 (actions, the pace the clock allows) x 0.78 (levels per action) ~ 0.52, i.e. about 63% of the
log-loss is pace and 37% is per-action. The per-action ratio is biased IN no-echo's favour (fewer actions spend more of
the run on the cheap early levels), so the per-action deficit is if anything understated. So the no-echo loss is not
only the clock: per action the agent without its echo also clears fewer levels. Suggested sentence for §3.5/3.6: "Of the
48% fall in levels, about two thirds is pace (34% fewer actions in the clock) and one third is per action (0.91 against
1.16 levels per 100 actions, a ratio that favours the arm taking fewer actions); the working-memory reading rests on the
second part." Clocked data, 3 v 4, no interval on the ratio; the untimed no-echo arm has never run.

## Batch E (05:10): §4, sentences still leaning on ut1 (or the concurrency-1 partials) as the clock test
Draft at 2dd1884. l.358-361 now say it right ("changes two things at once ... the clock test is r0c14"). Still leaning:
| line | sentence | why | suggested |
|---|---|---|---|
| 364-367 | "The price is written in the same table: 0.25 levels per hundred actions untimed against 1.19 timed. Off the clock the model spends six and a half times the actions ... and that is the experience-efficiency the benchmark says it measures" | attributes ut1's numbers to the clock alone; ut1 also removed the sharing (concurrency 1, the whole KV pool per game) | "Without the clock and the sharing (ut1), the model spends ..."; keep "the clock alone" for r0c14 when it lands |
| 380-382 | "Per action, the clock does not change how the model plays; it removes the part of the game where the hard levels are, and everything the untimed runs add comes from actions the clock never allows" | a clock conclusion drawn from curves the same paragraph says compare concurrency 1 against 14 | "Per action, the timed regime (clock and sharing together) plays as well as the untimed one ...; whether the clock alone accounts for it is r0c14's question" |
| 390 (Fig. 4.1 caption) | "Untimed: three no-clock runs, 38 games" | omits that they ran one game at a time | "three no-clock runs at concurrency 1 (R0, r0rep3, r0rep4)" |
| 367-369 (low) | "the prediction that levels per action would fall while clears rose is what the runs show" | the pre-stated prediction was checked on ut1, the two-variable contrast | add "on ut1 (clock and sharing removed)" |
Also still open from batch B (not ut1): l.382-384 "says the same ... nearly all": W1's loss is a capability gap with no clock.
