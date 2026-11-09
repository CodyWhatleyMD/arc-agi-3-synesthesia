# Pre-statement: a vocabulary shortlist for the DFlash2 drafter's candidate head (2026-11-02 ~00:15 CST, CL2 fork)

Mechanism (primary source, our vLLM 0.31 runtime contract/rt):
- MTP drafts over a 32k shortlist: models/qwen4_exp/nvidia/mtp.py `Qwen4ExpDraftVocabHead` (rows of the LM head for
  configs/draft_vocab_32k.json: 11,428 half-open ranges, 32,000 ids = 500 x 64), selected through get_top_tokens; the
  setup passes the file as VLLM_QWEN4_EXP_DRAFT_VOCAB (CP log line 122: "drafts over 32000 of 248320 tokens").
- DFlash2 scores the FULL vocabulary: model_executor/models/qwen3_dflash2.py `DFlash2Qwen3ForCausalLM.compute_candidates`
  -> LogitsProcessor.get_top_k_tokens(self.lm_head, hidden, top_k=16): logits over all 248,320 rows of the LM head
  (the TARGET's head, shared in v1/worker/gpu/spec_decode/dflash/utils.py:load_dflash_model), then top-16 ids (global)
  and their raw values (no scale, no soft cap in incoai's config). The speculator (dflash2/speculator.py:_generate_draft)
  passes the global ids to CandidateSelector (codebooks indexed by global id) and the candidate sampler, which writes
  the draft distribution over exactly those 16 candidates (draft_logits, -inf elsewhere).

Change (default off, switch ARM_DFLASH_SHORTLIST=1): after load_dflash_model shares the target LM head, copy its 32k
shortlist rows; compute_candidates then takes top-16 over the shortlist rows and maps local indices to global ids.
Target verification, the selector, the sampler and the rejection sampler are untouched.

Correctness claims (unit-checked before any GPU run; a FAIL stops the lane):
C1 the patched head proposes only shortlist ids;
C2 ids = shortlist_ids[local top-k index] (global-id mapping);
C3 where the full-vocabulary top-16 lies inside the shortlist, patched ids equal stock ids and values agree within
   bf16 GEMM tolerance (|diff| <= 1e-2 on logits of magnitude ~10-30);
C4 switch off = stock compute_candidates (no buffer built, same code path);
C5 the patch is hash-pinned on both target files, idempotent, refuses unknown bytes, and leaves nothing half-written.
Exactness of the served distribution is a property of rejection sampling with q supported on the drafter's candidates,
which the change keeps (q is still written from the same candidate scores the walk sampled from).

Measurement A (offline acceptance, 5090 only): drafter-tune's seeded paired validation (train_dflash2.py, VAL_SEED
1101, ds_full held-out games ls20 sp80 tn36 vc33), stock and tuned (full_lr1e-4 epoch 5), each without and with the
shortlist. The shortlist is applied by masking unary logits outside the 32k ids to -1e4 before speculators'
`unary_logits.topk(top_k)` (core.py:173): identical to serving's top-k over the shortlist rows, since a shortlist token's
logit does not depend on the other rows; the eal metric gates on the unary candidate set (metrics.py:252-255), so a
masked gold token cannot count. Report eal_d3/d4/d7 and esl (T=0.6). Sanity: no-shortlist eal_d3 reproduces
drafter-tune's 3.146 (stock) and 3.193 (tuned) within 0.005, else the measurement is void.
Measurement B (microbenchmark, 5090, bf16, hidden 2560): candidate head + top-16 over 248,320 rows vs over 32,000 rows
+ id gather, at 56 and 98 rows (14 requests x 4 / 7 drafts); median of 200 timed iterations after warm-up.

Reading, fixed now: the shortlist is worth a Kaggle run only if BOTH (A) tuned eal_d4 drops by <= 0.02 with the
shortlist (MTP accepts the same constraint) and (B) it saves >= 0.5 ms per draft step at 56 rows (>= ~1.2% of the
40.8 ms K=4 decode cadence Codex measured). Otherwise it is staged but not recommended.

## Result (2026-11-02 ~00:40 CST): both readings pass; staged as dfnd4s (not pushed)
Code: harness branch candidate-dflash cc62e0b (on 255503f): scripts/runtime_0310/patch_dflash_shortlist.py (+ harness/arc3_tools copy),
hash-pinned on qwen3_dflash2.py 11ac6ba8 -> dbf24fc8 and dflash/utils.py f0584417 -> bfe08bad; ARM_DFLASH_SHORTLIST=1 wired in
harness/setup_commands.json (installs the patch with the DFlash patches; passes ARC3_DFLASH_DRAFT_VOCAB = the ARM_DRAFT_VOCAB file to
the server; refuses without ARM_SPEC_METHOD=dflash). Default off: no patch, server env unchanged.
Claims: tests/dflash/test_dflash_shortlist.py, all pass: C5 (installs on the pinned files, results = pinned hashes, idempotent,
refuses one drifted file and writes neither, head built after the target LM head is shared), C4 (off = stock exactly),
C1, C2, C3 (98/98 rows with full top-16 inside the shortlist: same ids, values within 1e-2).
A, offline acceptance (seeded paired, 13,518 held-out blocks; scripts/drafter_tune/eval_shortlist.py; /mnt/data/drafter_tune/runs_sl):
| checkpoint | eal_d3 | eal_d4 | eal_d7 | esl_d3 | esl_d4 | esl_d7 |
| stock, full vocab | 3.1460 | 3.5982 | 4.4901 | 3.0856 | 3.5222 | 4.3835 |
| stock, 32k shortlist | 3.1416 | 3.5917 | 4.4785 | 3.0815 | 3.5162 | 4.3729 |
| tuned ep5, full vocab | 3.1929 | 3.6679 | 4.6333 | 3.1268 | 3.5846 | 4.5184 |
| tuned ep5, 32k shortlist | 3.1884 | 3.6616 | 4.6227 | 3.1225 | 3.5786 | 4.5083 |
Sanity holds (no-shortlist eal_d3 = drafter-tune's 3.146 / 3.193 exactly). Tuned eal_d4 drop -0.0063 (bar <= 0.02): PASS.
B, microbenchmark (RTX 5090, bf16, torch.topk; scratchpad bench_shortlist.py): full-vocab head + top-16 892 / 992 / 1030 us vs
shortlist head + top-16 + gather 161 / 172 / 177 us at 56 / 70 / 98 rows: saves 0.73 ms at 56 rows (bar >= 0.5 ms): PASS
(~1.8% of the 40.8 ms K=4 cadence; the 5090 and Kaggle's RTX PRO 6000 Server are both GB202; serving uses FlashInfer's top-k).
So, by the pre-stated reading, worth one Kaggle run. Staged: notebooks_duck/kaggle_staged/synesthesia_dfnd4s (= dfnd4 + ARM_DFLASH_SHORTLIST=1
on cc62e0b; harness dataset codywhatleymd/arc3-syn-harness-dfnd4s-k1 uploaded, ready; kernel NOT pushed). Unverified until it boots:
the vLLM log should show "ARC3 DFlash2 drafts over 32000 of 248320 tokens" and the setup "ARC3 DFlash shortlist patch: installed".
Expected size of effect: ~1-2% throughput at K=4; it does not touch the cache-reuse loss (Codex: the larger term).
