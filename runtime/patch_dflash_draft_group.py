#!/usr/bin/env python3
"""Post-install patch: let vLLM 0.31.0 identify a DFlash drafter's own KV cache group(s), so that only they get the
EAGLE last-block prefix-cache drop (our vLLM 0.31.0 runtime, overlay kv_cache_utils.py).

Why. With a speculative method that uses target hidden states (eagle, eagle3, mtp, dflash, dspark), vLLM drops the
last block of a prefix-cache hit in the drafter's KV groups ("EAGLE block drop"). _annotate_eagle_groups finds those
groups by two rules: (1) a spec carrying non_causal_multi_token_decode (DSpark only) and (2) the group holding the
last registered layer, enabled only for MTP and DeepseekV4 (_uses_trailing_mtp_layers). A DFlash drafter matches
neither, so the server logs "Speculative decoding (method=dflash) is enabled but no KV cache group could be
identified as the draft model's" and KVCacheCoordinator.__init__ (kv_cache_coordinator.py L104-110) then flags ALL
groups: the target's MLA group and every Mamba (GDN) group get the drop as well. On Flash-Next + incoai's DFlash2
drafter the groups are 0-3 Mamba, 4 circular buffer, 5 MLA, 6 the drafter's 5 sliding-window layers (48-52).

Fix. For method == "dflash" when neither rule flagged a group: a DFlash drafter is loaded after the target, so its
layers register last, and DFlashQwen3ForCausalLM names them layers.{target_layers + i} (its start_layer_id). The
patch takes the last num_hidden_layers (drafter config) entries of kv_cache_spec, checks each carries that index and
that the groups partition the layers exactly, and flags every group holding one of them; it logs which. If any check
fails, nothing is flagged and vLLM's own warning and all-groups fallback apply unchanged. Inert for every other
method, and when the block drop is disabled (_annotate_eagle_groups returns before the rules).

Run on the directory that directly contains the vllm package, after the runtime's installer (the setup script runs
it only with ARM_SPEC_METHOD=dflash and ARM_DFLASH_DRAFT_GROUP=1):
    python3 -I patch_dflash_draft_group.py DIST_PACKAGES
Hash-pinned: the pinned installed bytes are patched, the pinned patched bytes are left alone, anything else is
refused before anything is written. The write is atomic. patch_kv_group_log.py (ARM_KV_GROUP_LOG=1) may edit the
same file afterwards; its anchor is untouched by this patch.
"""
import hashlib
import os
import sys
from pathlib import Path

TARGET = 'vllm/v1/core/kv_cache_utils.py'

HELPER = (
    '''def _annotate_eagle_groups(
    vllm_config: VllmConfig,
    kv_cache_spec: dict[str, KVCacheSpec],
    kv_cache_groups: list[KVCacheGroupSpec],
    use_trailing_layer_fallback: bool = False,
) -> None:
''',
    '''def _arc3_flag_dflash_draft_groups(
    vllm_config: VllmConfig,
    kv_cache_spec: dict[str, KVCacheSpec],
    kv_cache_groups: list[KVCacheGroupSpec],
) -> None:
    """ARC3 (scripts/runtime_0310/patch_dflash_draft_group.py): flag the groups holding a DFlash drafter's layers.

    Neither rule of _annotate_eagle_groups finds a DFlash drafter, and the coordinator then gives EVERY group the
    EAGLE block drop. The drafter is loaded after the target, so its layers register last, and
    DFlashQwen3ForCausalLM names them layers.{target_layers + i} (start_layer_id). Both are checked here; if a check
    fails nothing is flagged and vLLM's own warning and fallback apply unchanged.
    """
    names = list(kv_cache_spec)
    try:
        n_draft = int(vllm_config.speculative_config.draft_model_config.hf_config.num_hidden_layers)
        n_target = int(vllm_config.model_config.get_total_num_hidden_layers())
    except (AttributeError, TypeError, ValueError) as exc:
        logger.warning("ARC3 DFlash draft group: layer counts unavailable (%r); not identified", exc)
        return
    draft = names[-n_draft:] if 0 < n_draft <= len(names) else []
    if not draft or not all(
        f".layers.{n_target + i}." in f".{name}" for i, name in enumerate(draft)
    ):
        logger.warning(
            "ARC3 DFlash draft group: the last %d KV layers %s are not drafter layers %d..%d; not identified",
            n_draft, draft, n_target, n_target + n_draft - 1,
        )
        return
    if not _groups_partition_layers_exactly(kv_cache_spec, kv_cache_groups):
        logger.warning("ARC3 DFlash draft group: the groups do not partition the KV layers exactly; not identified")
        return
    draft_set = set(draft)
    flagged = [i for i, g in enumerate(kv_cache_groups) if draft_set.intersection(g.layer_names)]
    for i in flagged:
        kv_cache_groups[i].is_eagle_group = True
    shared = sorted(n for i in flagged for n in kv_cache_groups[i].layer_names if n not in draft_set)
    logger.info(
        "ARC3 DFlash draft group: KV cache group(s) %s hold the drafter's %d layers %s; only they get the EAGLE "
        "last-block drop%s",
        flagged, n_draft, draft, f" (they also hold target layers {shared})" if shared else "",
    )


def _annotate_eagle_groups(
    vllm_config: VllmConfig,
    kv_cache_spec: dict[str, KVCacheSpec],
    kv_cache_groups: list[KVCacheGroupSpec],
    use_trailing_layer_fallback: bool = False,
) -> None:
''')
RULE = (
    '''            group.is_eagle_group = True

    if not use_trailing_layer_fallback:
        return
''',
    '''            group.is_eagle_group = True

    # ARC3 (patch_dflash_draft_group.py): a DFlash drafter matches neither rule; flag its own group(s) rather than
    # leave the coordinator to flag every group (the target's MLA and Mamba groups included).
    if spec_config.method == "dflash" and not any(g.is_eagle_group for g in kv_cache_groups):
        _arc3_flag_dflash_draft_groups(vllm_config, kv_cache_spec, kv_cache_groups)

    if not use_trailing_layer_fallback:
        return
''')
EDITS = [HELPER, RULE]
# installed sha256 -> (what it is, patched sha256)
PINS = {
    'ec59a62aa78811f52d766503c44ecaa5c6dda3d875ec8fa1c3cd1ee424db0021': (
        'v0.31.0 overlay 4848d189', 'bb793cf0bad6a80719e73b5dfdc94227596a8e317493821a4bb6bfbc12b1cd9d'),
}


def apply_edits(text: str) -> str:
    for old, new in EDITS:
        n = text.count(old)
        if n != 1:
            raise SystemExit(f"ARC3 DFlash draft group patch: anchor occurs {n} times in {TARGET}: {old[:70]!r}")
        text = text.replace(old, new, 1)
    return text


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch_dflash_draft_group.py DIST_PACKAGES")
    target = Path(sys.argv[1]) / TARGET
    data = target.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest in {patched for _, patched in PINS.values()}:
        print(f"ARC3 DFlash draft group patch: already patched ({digest[:12]}) {target}")
        return
    if digest not in PINS:
        raise SystemExit(f"ARC3 DFlash draft group patch: {target} has sha256 {digest}, neither pinned installed nor "
                         "pinned patched; nothing written")
    runtime, patched = PINS[digest]
    out = apply_edits(data.decode()).encode()
    if hashlib.sha256(out).hexdigest() != patched:
        raise SystemExit(f"ARC3 DFlash draft group patch: edited {TARGET} does not match its pinned result; "
                         "nothing written")
    tmp = target.with_name(f".{target.name}.arc3-dflash-group.tmp")
    tmp.write_bytes(out)
    os.chmod(tmp, target.stat().st_mode & 0o7777)
    os.replace(tmp, target)
    print(f"ARC3 DFlash draft group patch: installed ({runtime}, {digest[:12]} -> {patched[:12]}) {target}")


if __name__ == "__main__":
    main()
