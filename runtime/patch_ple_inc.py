#!/usr/bin/env python3
"""Post-install patch: load the PLE table of an AutoRound (INC) checkpoint unquantized (vLLM 0.31.0 ARC3 runtime).

Qwen4ExpPLEEmbeddingMethod.from_quant_config (vllm/models/qwen4_exp/common/ngram_embedding.py, our 0.31.0
overlay member) picks the PLE table's format from the model's quantization config. It handles
compressed-tensors, an FP8 table dtype, no config, ModelOpt and Fp8Config, and raises NotImplementedError for
anything else. vLLM 0.31.0 serves an AutoRound checkpoint (quant_method "auto-round") as INCConfig
(quantization/inc/inc.py), which is none of those, so model construction fails. AutoRound exports of
Qwen3.8-Flash-Next leave the PLE table in BF16 ("ple" in ignore_layers), so the edit adds one branch: an INC
config gets the unquantized method, the same one a compressed-tensors checkpoint gets. Every other config
takes its old path; on our compressed-tensors checkpoint the edit is inert.

Run it on the directory that directly contains the vllm package, after the runtime's own installer (and after
patch_kv_copy_chunked.py) and before the server starts:  python3 -I patch_ple_inc.py DIST_PACKAGES
Hash-pinned: the file must be the 0.31.0 overlay member (patched) or its pinned patched form (left alone,
"already patched"); anything else, Han Solo's e975732 runtime included, is refused before writing.
The write is atomic.
"""
import hashlib
import os
import sys
from pathlib import Path

TARGET = 'vllm/models/qwen4_exp/common/ngram_embedding.py'
# installed sha256 -> (runtime, patched sha256)
PINS = {
    '8f5a8d0222a97ace910871004da7fe4e7127a38f7d53841e85b7d549e076edef': ('v0.31.0 overlay 4848d189', '70f3e7758839f1987e2d7f77ddc44839aef3647642eb350631b82ca5286b4696'),
}
EDITS = [
    ('        if embedding_dtype == "float8_e4m3fn":\n            return Qwen4ExpPLEFp8EmbeddingMethod()\n', '        if embedding_dtype == "float8_e4m3fn":\n            return Qwen4ExpPLEFp8EmbeddingMethod()\n        # ARC3: AutoRound (INC) checkpoints keep the PLE table in BF16 ("ple" is in their ignore_layers),\n        # so it loads unquantized; without this branch INCConfig reaches the NotImplementedError below.\n        if quant_config is not None and quant_config.get_name() == "inc":\n            return Qwen4ExpPLEUnquantizedEmbeddingMethod()\n'),
]


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch_ple_inc.py DIST_PACKAGES")
    target = Path(sys.argv[1]) / TARGET
    data = target.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    for runtime, patched in PINS.values():
        if digest == patched:
            print(f"ARC3 PLE/INC patch: already patched ({runtime}, {digest[:12]}) {target}")
            return
    if digest not in PINS:
        raise SystemExit(f"ARC3 PLE/INC patch: {target} has sha256 {digest}, neither the pinned installed nor the "
                         "pinned patched file; nothing written")
    runtime, patched = PINS[digest]
    text = data.decode()
    for old, new in EDITS:
        if text.count(old) != 1:
            raise SystemExit(f"ARC3 PLE/INC patch: anchor occurs {text.count(old)} times: {old[:60]!r}")
        text = text.replace(old, new, 1)
    out = text.encode()
    if hashlib.sha256(out).hexdigest() != patched:
        raise SystemExit("ARC3 PLE/INC patch: edited bytes do not match the pinned result; nothing written")
    tmp = target.with_name(f".{target.name}.arc3-pleinc.tmp")
    tmp.write_bytes(out)
    os.chmod(tmp, target.stat().st_mode & 0o7777)
    os.replace(tmp, target)
    print(f"ARC3 PLE/INC patch: installed ({runtime}, {digest[:12]} -> {patched[:12]}) {target}")


if __name__ == "__main__":
    main()
