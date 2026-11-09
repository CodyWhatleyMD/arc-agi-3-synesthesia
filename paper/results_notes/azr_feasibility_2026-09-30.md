# AZR training on Qwen3.8-Flash-Next — feasibility (three-lens team, 2026-09-30)

Investigator: "can we launch a team to look into the feasibility of AZR training on 3.8 next flash?" Three agents in parallel
(stack / method / literature), read-only, ~15 min each; synthesis by CL2. Sources are in the lens reports
(session transcripts) and the literature agent's scratchpad; load-bearing citations repeated inline below.

## Verdict
**Trainable — yes, barely, on ≥8 GPUs with tooling that is days old. AZR on it — not a leaderboard path, and not
yet an experiment worth rented money.** Two $0 falsifiers come first; both are paper material whatever they show.

## 1. The stack (lens 1, verified in installed source; §5 of the literature lens)
- transformers 5.17 trains `qwen4_exp` in eager mode: fused 3-D experts autograd-clean (per-expert `F.linear` loop),
  PLE table an `nn.Embedding` (frozen trivially), GDN on the pure-torch fallback (no `fla` installed), sparse-attn
  indexer effectively frozen (top-k non-differentiable). Non-expert params **5.48 B**; experts 123.3 B; table 51.2 B.
- PEFT 0.20 wraps the fused experts via `target_parameters` but materialises the full delta per layer (+3.4 GB
  transient) and Megatron-Bridge #6233 reports no PEFT version saves a fused-expert adapter correctly. LoRA on the
  attention/GDN/shared-expert `nn.Linear`s is the safe subset.
- Frameworks: ms-swift lists Flash-Next by name (Megatron backend; GRPO-LoRA "8*135G", SFT-LoRA "8*70G"; needs
  transformers>=5.16 + mcore-bridge + TE + fla + vLLM from source). Unsloth merged training **29 Sep** (FP8 checkpoint
  on 3×B200, 38 s/step, "Only B200 was tested"). verl: issue #7653 open, PR #7749 (BF16 LoRA FSDP2, 16-H200 smoke)
  unmerged. OpenRLHF/LLaMA-Factory: nothing. Davd-b01 ran SFT→SimPO→RLVR on a 128-expert prune for ~$300 in native
  PyTorch because "Unsloth segfaults on this architecture, TRL/Axolotl would silently drop vision+MTP on save".
- Rollouts are the crux: stock vLLM 0.29 has `qwen4_exp` but no LoRA and no table offload (BF16 = 360 GB → TP8);
  the image build has both (declares `SupportsLoRA`) but is a dev fork no RL framework's weight-sync targets.
- Memory/time (LoRA, experts+table frozen, FSDP): g7e.24xlarge ~85 GB/card, 12–18 min/step, ~$400/day, ~$2k for
  500 AZR steps; 48xlarge ~$800/day at half the step time. **Our box: nothing viable beyond a 4-layer slice** —
  QLoRA over our NVFP4 is not a path (transformers decompresses compressed-tensors on the first forward).

## 2. The method (lens 2, paper read in full)
- AZR: one policy, proposer + solver, tasks (p, i, o) verified by a Python executor; deduction/abduction/induction;
  learnability reward = 1 − mean solver accuracy over G=8 samples (0 if unsolvable); TRR++ with six baselines;
  batch 64×6, 500 steps, ~1,920 generations/step; 7B on 4×A800 ≈ 60 h. Not SFT, not distillation.
- On ARC-AGI-3 the executor exists (arcengine; 25 public + 30 Gemini game programs on disk) and replaying the full
  action history verifies exactly — the red-team's 3.5% non-determinism is a property of (board, action) keys, not
  the engine. The one clean framing: **induction over mechanics** — proposer picks (game, start state, probe set),
  executor generates transitions, solver writes `predict()`, verified on executor-generated held-out transitions
  with `action_count` in the signature (no meter mask). Abduction = "find the action that produces this board" with
  the source hidden — the discriminating-test discipline as a training task. "Play a level" as the solve is 30–50×
  the paper's response length → infeasible at 180B.
- Build list before step 1 (~6 days, no GPU): headless replay wrapper, seed pool (256 triplets), proposal format +
  parser, verifier with held-out transitions, rewards/baselines; the sandbox + natives exist (S5 blocker: expose the
  numeric grid). Corpus on disk: **108,085** engine-verified transitions, **1,196** clear events (Opus's excluded).
- Overfit to the public 25: high for transition-prediction and level-solve framings; measurable for induction with
  the Gemini games + 5 held-out public games (Arm D's split).

## 3. The record (lens 3, sourced)
- Every documented ≥100B-MoE RL result is ≥64 GPUs or hosted (INTELLECT-3, AReaL-235B, verl's DeepSeek-671B/Qwen3-235B
  on "hundreds of GPUs", Tinker). AZR itself: 3–14B on 2–8×80GB over days; a replication saw ~10 pts at 3B over 200
  epochs; critiques (2510.27072, PopuLoRA 2605.16727, 2603.02218): the single agent "self-calibrates to generating
  easy problems it can reliably solve", loops "often plateau quickly". Games extensions exist (Vision-Zero, SPIRAL,
  2605.14392); **arXiv has zero hits for self-play + ARC-AGI** — a novelty opening, not a precedent.
- ARC-AGI-3 weight training to date: StochasticGoose (a 34M CNN, no LLM weights); forum reports — an SFT adapter on 31
  trajectories 25.07 vs 4.99 on 5 held-out public games (one run each, "offline ranking has not reliably predicted
  the leaderboard"); "built and validated rl training pipeline of Qwen 3.8 Next Flash … did not gain any
  performance … I used a full H200 node"; LoRA BC on the 27B "+2 on the public games … didn't translate … hidden".
  Milestone 1's own read: gains "came from better base models and introducing multi-modality". Our own week agrees:
  3.20 → 8.22 on the public 25 from serving and harness, no weights touched.
- Licences: Qwen Community License 1.0 grants "fine-tune, and create derivative works"; obligations are a notice
  above 100M MAU / $20M and a separate licence for Model-as-a-Service — internal use exempt. Alibaba Model Studio
  terms §4.48.1(d)(v): outputs may not be used "to train or develop products or services that compete with Alibaba
  Cloud" — unresolved for an ARC agent, so **no distillation from qwen3.8-max-prime**. Claude outputs: excluded (our firewall).

## 4. Decision
1. **No rented GPU on AZR-for-Flash-Next now.** No merged RL+rollout stack for the arch; the method's own record is
   plateau/collapse at small scale; every ARC-AGI-3 weight-training report sits inside run-to-run noise; the lever
   that moved us was serving. The leaderboard through the deadline is a serving/harness problem.
2. **Two $0 falsifiers, after the fidelity chain frees the 6000, in this order:**
   (a) lens 1's slice test — 4 layers (keeps PLE layer 2) BF16, PEFT LoRA on attention/GDN/shared-expert linears,
       one 2k-token harness prompt, checkpointing on, one backward + one optimizer step, assert finite grads; then two
       TRL GRPO steps with HF-generate rollouts. Any exception falsifies "trainable with public tooling"; a pass is a
       publishable fact nobody has printed (Unsloth's day-old claim is B200-only).
   (b) lens 2's one self-play iteration with no weight update on our quant: 64 proposed induction tasks × 8 solver
       samples; read the learnability histogram. Bimodal at {0,1} → AZR has nothing to work with on this task; mass in
       (0,1) → the 27B LoRA rehearsal on the box (~$200) is next. Either way it yields the first executor-verified
       mechanic-induction benchmark, which is paper material on its own (Novelty/Theory).
3. If both pass and a run is wanted: Flash-Next LoRA only via ms-swift-Megatron (8 GPUs) or Unsloth on B200s — the
   g7e's RTX PRO 6000 is untested by both; the 27B is the cheap instrument and the delta is the claim.

## 5. What this corrects in earlier statements
- "No demonstrated training stack" (retracted 09-29) → precise now: several full-weight post-trains exist (Swift 1.5,
  Tinfield-1, Davd-b01), Unsloth merged training yesterday; what does NOT exist is a merged RL framework with
  rollout weight-sync for the arch. Swift 1.5's stack/hardware are unpublished. ISTA's GSQ-RCO is pruning +
  quantization, not a fine-tune. The corpus is 108k transitions, not the red-team's stale 19k.
