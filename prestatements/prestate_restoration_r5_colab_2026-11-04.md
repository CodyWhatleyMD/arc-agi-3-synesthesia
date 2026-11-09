# Pre-statement: restoration R5 (perception restored, no clock) and its control, on Colab (2026-11-04 08:45 CST)

The investigator, 08:35: "yes sak you can use colab like a ragdoll - please, deplete it." The question (08:01): "show what might
have been without time constraints and the weird loading times." Written before either run starts.

## Design
Two untimed runs of the anchor harness (commit 8552964, dataset arc3-synesthesia-harness-r0, our v22 model), 25 public
games, max 5,184 actions per game, NO per-game clock, NO job budget (ARM_MAX_RUNTIME_S=0), both on Colab G4 (RTX PRO
6000, 97.9 GB; fit confirmed by c3 on 11-02), concurrency 14:
- R5  = native vision tower on (ARM_B_STUDENT_TOWER=0, 16 px/cell PNG, 1,024 image tokens, server image limit 143,
        exactly the na1c-na3c arm's switches, notes/tower_native_local_result_2026-10-28.md), untimed.
- R0c = the student tower (the anchor), untimed, same concurrency. The clean pair for R5 on the same platform.
R0 (local 6000, 10-31) was concurrency 1 and is NOT the control for R5: concurrency changes throughput and KV pressure.
Under no clock, concurrency does not change a game's action budget; it can change per-token latency and KV eviction
(c25 collapsed at 25; 14 is the anchor's and held in every control). Reported as a sensitivity against R0, not pooled.

## Measures (prestate_experience_efficiency_2026-11-04.md)
E3 levels per game and full-clear rate; E1 levels per 100 actions; E2 actions-to-clear survival curve; per game, then
run-level. R5 vs R0c is one pair (n=1 vs 1): reported with the sign, the per-game differences and NO resolution
claim. R5 vs the timed native arm (na1c-na3c, 9,300 s) and R0c vs R0/r0rep4/ut1 give the two "clock removed" contrasts.

## Predictions, first
P1. R0c levels per game >= 5.5 (R0 local: 6.15 on 13 finished games; timed controls 4.23); if R0c comes in under the
    timed controls the untimed claim is in trouble and I say so.
P2. R5 - R0c levels per game within +/-1.0: the native tower and the student are indistinguishable untimed as they were
    timed (+2.07 [-8.80, +12.88] run-level). A difference beyond +/-1.5 either way on one pair is a direction to replicate,
    not a result.
P3. Both runs finish inside one Colab session (<= 24 h); if either is cut by the platform it is reported as censored at
    the cut, like a clocked run, and that fact goes in section 4.

## Not claimed
Anything about the hidden set; anything resolved from one pair. Cost: the investigator's Colab credits (his word, 08:35).

## Amendment 1 (2026-11-07 01:35 CST, before either run starts): platform
Colab is out: the 11-04 sessions expired at 24 h with their pollers dead in the workstation crash; nothing was
retrieved. R5 and R0c move to the GCP server (g4-standard-48 Spot, RTX PRO 6000, the Kaggle-shaped host), one after
the other through the replicate queue (r5 first, then r0c14), paid from the investigator's cloud credit (his word, 11-07 01:28:
"cloud is paid up"). The local 6000 (Max-Q) runs its own r0c14 since 11-07 00:55 CST: same notebook, different host,
reported as a sensitivity beside the server pair, never pooled with it. ut1 (server, concurrency 1, 56.88, 5.96
levels/game, notes/untimed_ut1_result_2026-11-07.md) is the second untimed run of the anchor and the server-side
reference for R0c14's concurrency sensitivity. Predictions P1-P3 stand; P3's "one Colab session" becomes "one Spot
lease": a preempted run is re-run from scratch by the queue, and a run cut by the deadline is reported censored.

## Amendment 2 (2026-11-07 03:50 CST, before any rented box plays): untimed replicates on rented RTX PRO 6000s
The investigator put $200 on vast.ai ("200 in the girls pocket", 03:39). Up to four single-card boxes, Kaggle's card family
(RTX PRO 6000; Server edition where offered, WS/Max-Q editions otherwise — same chip, different power limit; under NO
clock the edition changes only wall time), host RAM >= 180 GB (the pinned PLE table + the worker need ~130-170 GB),
CUDA >= 13.2, the Kaggle GPU image as the instance image, papermill as on the server (~/kaggle_local/vast_run.sh).
Arms, same notebooks as the server (nb/r5.ipynb, nb/r0c14.ipynb): r5x1..r5xN = R5 (native tower, untimed, c14);
r0x1..r0xN = R0c (student, untimed, c14). Target by the paper deadline: untimed anchor n>=4 (ut1, r0c14 local,
r0c14s server, r0x*), native untimed n>=3 (r5s, r5x*). Comparisons stay as pre-stated: run-level, paired by game,
NOT RESOLVED unless the interval excludes zero; platform (GCP server / vast box / local Max-Q) is recorded per run
and reported as a sensitivity, never pooled across the timed controls (which stay on the local 6000).
Predictions, first: P4 the rented boxes reproduce ut1's levels/game within +/-1.0 (same harness, same weights, no
clock); P5 the native arm's untimed levels/game sits within +/-1.0 of the student's (as timed, +2.07 unresolved).
Stop rule: any run not finished by 11-09 12:00 CST is reported censored at its last snapshot.

## Amendment 3 (2026-11-07 05:08 CST, CL1), before any of these runs started
The investigator, 05:06: "just do whatever - the money is spent" = go inside the $200 vast credit. The batch, all untimed at the
anchor's concurrency 14 (the clock test holds the sharing and the KV pool; see memory feedback-hold-the-design-not-
the-last-message): r0x1 (vast 55911915, France, Server) and r0x2 (52632728, France, Server) = r0c14 replicates
(nb/r0c14.ipynb); r5x1 (53005989, Virginia, Server) and r5x2 (59063712, UK, Server) = r5 replicates (nb/r5.ipynb,
native tower, c14, untimed); the GCP server resumes r5s then r0c14s; r0c14 on the 6000 (started 01:13) continues.
CL2 runs the vast lane (kas_vast_box.sh, one detached runner per box; inputs pushed from home; destroy only after
DONE + benchmark.json + run.log are local). KV pool: by the same memory math as the anchor on the same card type
(ut1 1,501,360 vs r2 1,502,892 tokens, 0.1%); no pin needed on RTX PRO 6000 Server/WS at 0.98.
What counts: r0c14 group = {r0c14, r0c14s, r0x1, r0x2} (target n=4) against the twelve timed runs, paired by game,
run-level interval; r5 group = {r5s, r5x1, r5x2} (target n=3) against the r0c14 group (the tower off the clock, same
concurrency). A run cut by preemption/deadline is reported partial on matched games, never scaled. The shelved R5 at
concurrency 1 (r5p) is not in this batch. Stop rule: the deadline (Mon 11-09 17:59 CST) or the credit; no second batch
without the investigator's word. Expected wall time per run ~13-15 h at c14 (r0c14's pace: 15,201 actions at 3 h).
