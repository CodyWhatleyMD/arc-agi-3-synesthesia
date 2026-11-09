#!/usr/bin/env python3
"""Post-install patch, MEASUREMENT ONLY: emulate a task-restricted PLE table (CL2 10-30, the investigator 15:23 "measure it").
With VLLM_ARC3_PLE_MASK=<.npy bool array, one entry per PLE table row> set in the server's environment, the pinned
PLE lookup returns zeros for rows outside the mask (Qwen4ExpPLEPinnedHostEmbedding._lookup, both the sync and the
prefetch path); unset, the code is stock. Pinned to the 0.31.0 overlay member 8f5a8d02 (refused otherwise); never
part of a submission.  usage: python3 -I patch_ple_mask.py DIST_PACKAGES"""
import hashlib, os, sys
from pathlib import Path
TARGET = 'vllm/models/qwen4_exp/common/ngram_embedding.py'
PINS = {'8f5a8d0222a97ace910871004da7fe4e7127a38f7d53841e85b7d549e076edef': ('v0.31.0 overlay 4848d189', 'c100abc1071d37158ed4391b709deec128d2dfa6c7c2239a652b071399b26a32')}
EDITS = [('from abc import ABC, abstractmethod\n', 'from abc import ABC, abstractmethod\nimport os\n'), ('        self._uva_weight = get_accelerator_view_from_cpu_tensor(self.weight)\n', '        self._uva_weight = get_accelerator_view_from_cpu_tensor(self.weight)\n        # ARC3 MEASUREMENT ONLY (patch_ple_mask.py): VLLM_ARC3_PLE_MASK=<.npy bool, one per table row> emulates a\n        # task-restricted PLE table: rows outside the mask are returned as zeros. Unset = stock behaviour.\n        self._arc3_ple_mask = None\n        _mask_path = os.environ.get("VLLM_ARC3_PLE_MASK")\n        if _mask_path:\n            import numpy as _np\n            _m = _np.load(_mask_path)\n            if _m.dtype != _np.bool_ or _m.shape[0] < self.num_embeddings:\n                raise ValueError(f"VLLM_ARC3_PLE_MASK {_mask_path}: need bool[>={self.num_embeddings}], got {_m.dtype}{_m.shape}")\n            self._arc3_ple_mask = torch.from_numpy(_m[: self.num_embeddings]).to(self._uva_weight.device)\n            logger.warning("ARC3 PLE MASK ACTIVE: %s keeps %d of %d rows (%.3f%%); other rows read as zeros",\n                           _mask_path, int(_m[: self.num_embeddings].sum()), self.num_embeddings,\n                           100.0 * float(_m[: self.num_embeddings].mean()))\n'), ('                BLOCK_D=self._block_d,\n            )\n        return output\n', '                BLOCK_D=self._block_d,\n            )\n            if self._arc3_ple_mask is not None:\n                output.mul_(self._arc3_ple_mask[input_ids.long()].unsqueeze(-1).to(output.dtype))\n        return output\n')]


def main():
    target = Path(sys.argv[1]) / TARGET; data = target.read_bytes(); digest = hashlib.sha256(data).hexdigest()
    for runtime, patched in PINS.values():
        if digest == patched:
            print(f"ARC3 PLE mask patch: already patched ({runtime})"); return
    if digest not in PINS:
        raise SystemExit(f"ARC3 PLE mask patch: {target} sha256 {digest} is not pinned; nothing written")
    runtime, patched = PINS[digest]; text = data.decode()
    for old, new in EDITS:
        if text.count(old) != 1:
            raise SystemExit(f"ARC3 PLE mask patch: anchor occurs {text.count(old)} times: {old[:60]!r}")
        text = text.replace(old, new, 1)
    out = text.encode()
    if hashlib.sha256(out).hexdigest() != patched:
        raise SystemExit("ARC3 PLE mask patch: edited bytes do not match the pinned result; nothing written")
    tmp = target.with_name(f".{target.name}.arc3-plemask.tmp"); tmp.write_bytes(out)
    os.chmod(tmp, target.stat().st_mode & 0o7777); os.replace(tmp, target)
    print(f"ARC3 PLE mask patch: installed ({runtime}, {digest[:12]} -> {patched[:12]})")


if __name__ == "__main__":
    main()
