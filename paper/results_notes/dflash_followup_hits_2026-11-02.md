# Where DFlash's extra prompt recompute comes from (dflash-cache lane, measured 2026-11-02 ~01:20-02:00 CST)

Question (CL2): Codex measured DFlash recomputing ~12,080 uncached prompt tokens per request vs MTP's ~6,750
(notes/codex_review_dflash_throughput_2026-11-01.md); 97.4% of consecutive requests in a game are append-only.
Hypothesis: the drafter's sliding-window blocks for DECODED tokens are not hashed/retained, so DFlash recomputes the
previous turn's generated tokens.

Method: scripts/dflash_followup_hits.py streams each run's metrics/vllm_cache_diagnostics_<enginecore pid>.jsonl, takes
each request's last cache_lookup (its admission), pairs it with its previous turn (the earlier request within 900 s
sharing the longest chained 16-token block-hash prefix), keeps append-only follow-ups (shared prefix >= 98% of the
previous prompt; P >= 4096), and reports hit - P_prev overall and per KV group. Runs: CP_candidate-pinned-k1 (MTP,
block 1664, prefix unit 128), DF_dfc4b (DFlash K=4, block 1680, unit 16), DF_dfc7b (DFlash K=7, block 1744, unit 16).

## 1. The hypothesis does not distinguish DFlash from MTP
Neither run's hit ever reaches past the previous PROMPT: 0.0% of 2,961 (MTP), 2,688 (dfc4b), 2,690 (dfc7b) append-only
follow-ups. Under MTP the binding groups are the Mamba ones (reach past P_prev in 0.0%; MLA 37.6%). Source:
KVCacheCoordinator.get_replay_boundaries derives the replay boundaries from num_prompt_tokens only, and with
prefix_cache_retention_interval 0 Mamba checkpoints and sliding-window tails are cached only there
(reachable_block_mask, cache_blocks). So decode-time drafter blocks are indeed not hashed or kept -- but neither are
decode-time Mamba states, under MTP or DFlash; both recompute the previous turn's generated tokens. Fixing only the
drafter would not extend the hit. (A positive retention interval is the general lever for that, for MTP too; not
measured here.)

## 2. The median excess: block-granular hits plus a whole-block EAGLE drop
- MTP: 97.9% of follow-ups hit exactly floor((P_prev - 1)/128)*128 - 128 (fine-grained 128-token hits, the EAGLE drop
  costs one 128 unit). P_prev - hit: median 193, mean 301. Recomputed (P - hit): median 2,577, mean 3,387.
- DFlash: 86.6% (dfc4b) / 87.4% (dfc7b) hit exactly floor(P_prev/blk)*blk - blk (the extension replay boundary): hits
  are block-granular because the SlidingWindowManager has no fine-grained lookup (coordinator disables partial hash
  hits) and the EAGLE drop costs a whole block. P_prev - hit: median 2,381 / 2,508. Recomputed: median 4,856 / 4,976.
- Counterfactual without the drop (hit at floor((P_prev - 1)/blk)*blk) on the boundary-exact follow-ups: +1,679 /
  +1,743 tokens reused per follow-up.

## 3. The mean excess: ~4% of DFlash follow-ups lose everything
3.6% (dfc4b, 98) / 4.3% (dfc7b, 116) of follow-ups hit BELOW the boundary, almost all with hit 0 (85/98, 110/116),
recomputing ~75-82k tokens each; they carry 53% / 58% of DFlash's total P_prev - hit (MTP: 4 follow-ups, 0.1%, a
different cause: Mamba reach short). In them every single group still reaches ~the boundary (medians: MLA 80,640, Mamba
78,960, drafter SW without drop 78,960, drafter SW with drop 77,280 -- one block short), and the lookup records
shared_prefix_boundary = that reach (kv_cache_manager.get_computed_blocks: hit + num_uncached). Mechanism: the
drafter group with the drop needs one block (the "peek" block) above Mamba's checkpoint; when that block is missing the
convergence loop needs a Mamba state one block lower, Mamba (sparse checkpoints, retention 0) has none there, falls back
to an older checkpoint where the drafter's blocks are long gone, and the hit converges to 0. The missing peek block:
evicted before the lookup in 82 of 291 zero-hit lookups (median 145 s earlier, eviction events keyed by hash+group),
no eviction recorded in 209 (never cached, or a different hash: cause NOT identified).
In 100% of append-only DFlash follow-ups (failed ones included), the drafter group WITHOUT the drop reaches at least
Mamba's checkpoint.

## Smallest fix (not built; config only)
disable_eagle_block_drop: true in the DFlash arm's speculative config (ARM_SPEC_EXTRA_JSON). Source: the scheduler
passes use_eagle_block_drop() (= use_eagle() and not disable_eagle_block_drop) as the KV manager's use_eagle
(scheduler.py ~L300-318), _annotate_eagle_groups returns before flagging any group, and the coordinator's all-groups
fallback needs use_eagle (kv_cache_coordinator.py ~L104-110): no group drops a block. Replay boundaries become (P - 1,),
and patch_dflash_sw_retain.py follows use_eagle (non-EAGLE tail: 2 blocks ending at floor((P-1)/blk)).
Expected from the measurements: the boundary loss falls from ~blk + (P mod blk) to ~(P mod blk) (+~1.7k reused per
follow-up), and the zero-hit collapses become hits at Mamba's checkpoint; predicted recompute median ~3.2k (MTP 2.6k),
mean near MTP's ~3.4k. Cost/risk: vLLM keeps the drop so a chunk-boundary lookahead write into the drafter's cache is
not reused (coordinator comment ~L111-118): affects draft quality/acceptance only, never target outputs (drafts are
verified). l6 ran with the drop off (confounded with an 18 GiB cap and unit 64, no retention): its 0-10 min acceptance
2.70 was level with l9's. Remaining gap to MTP after this: ~(P mod blk) vs ~64+128 tokens per follow-up (mechanism 3:
block-granular drafter hits), which only a fine-grained sliding-window lookup would remove.
