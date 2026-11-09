#!/usr/bin/env python3
"""Run a command inside an extracted vLLM image runtime, with the harness's environment.

Mirrors build_image_runtime_env() of the Arm B / TAAF setup script (PYTHONPATH, PATH,
LD_LIBRARY_PATH, CUDA_HOME, cache roots, offline flags, the ARC3 runtime switches) so a local
check runs the runtime the way the Kaggle notebook does.

usage: rt_env.py RUNTIME_ROOT MANIFEST_JSON [--draft-vocab FILE] -- CMD [ARGS...]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def prepend(existing: str, entries: list[Path]) -> str:
    return os.pathsep.join([str(e) for e in entries] + ([existing] if existing else []))


def build_env(root: Path, manifest: dict, draft_vocab: str | None, cache_root: Path) -> dict[str, str]:
    dist = root / manifest["dist_packages"]
    cuda_home = root / Path(manifest["nvcc"]).parent.parent
    env = os.environ.copy()
    caches = {
        "VLLM_CACHE_ROOT": cache_root / "vllm",
        "TRITON_CACHE_DIR": cache_root / "triton",
        "FLASHINFER_WORKSPACE_BASE": cache_root / "flashinfer",
        "B12X_COMPILE_CACHE_DIR": cache_root / "b12x" / "compile",
        "TMPDIR": cache_root / "tmp",
    }
    for p in caches.values():
        p.mkdir(parents=True, exist_ok=True)
    for k in ("PYTORCH_ALLOC_CONF", "VLLM_PLE_CPU_OFFLOAD", "VLLM_PLE_OFFLOAD_READY_TIMEOUT",
              "VLLM_PREFIX_CACHE_RETENTION_INTERVAL"):
        env.pop(k, None)
    env["PYTHONPATH"] = prepend(env.get("PYTHONPATH", ""), [dist / "nvidia_cutlass_dsl" / "dsl_packages", dist])
    env["PATH"] = prepend(env.get("PATH", ""), [cuda_home / "bin", root / "usr" / "local" / "bin"])
    libs = [cuda_home / "targets" / "x86_64-linux" / "lib", dist / "torch" / "lib",
            *sorted(dist.glob("nvidia/*/lib")), *sorted(dist.glob("nvidia/cu13/*/lib")),
            Path("/usr/local/nvidia/lib64")]
    env["LD_LIBRARY_PATH"] = prepend(env.get("LD_LIBRARY_PATH", ""), [p for p in libs if p.is_dir()])
    env.update({k: str(v) for k, v in caches.items()})
    env.update({
        "USE_TF": "0", "TRANSFORMERS_NO_TF": "1", "TRANSFORMERS_NO_TORCHVISION": "1",
        "VLLM_NO_USAGE_STATS": "1", "CUDA_HOME": str(cuda_home), "CUDACXX": str(cuda_home / "bin" / "nvcc"),
        "TORCH_CUDA_ARCH_LIST": "12.0", "VLLM_ENABLE_CUDA_COMPATIBILITY": "0",
        "VLLM_MEMORY_PROFILER_ESTIMATE_CUDAGRAPHS": "1", "VLLM_WORKER_MULTIPROC_METHOD": "spawn",
        "PYTORCH_CUDA_ALLOC_CONF": "expandable_segments:False", "HF_HUB_OFFLINE": "1",
        "HF_DATASETS_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "TOKENIZERS_PARALLELISM": "false",
    })
    env.setdefault("VLLM_ARC3_GDN_RECOVERSSM", "1")
    env["VLLM_GDN_DECODE_KERNEL"] = "triton"
    env.pop("VLLM_QWEN4_EXP_DRAFT_VOCAB", None)
    if draft_vocab:
        env["VLLM_QWEN4_EXP_DRAFT_VOCAB"] = draft_vocab
    return env


def main() -> None:
    argv = sys.argv[1:]
    if "--" not in argv:
        raise SystemExit(__doc__)
    split = argv.index("--")
    ap = argparse.ArgumentParser()
    ap.add_argument("root", type=Path)
    ap.add_argument("manifest", type=Path)
    ap.add_argument("--draft-vocab")
    ap.add_argument("--cache-root", type=Path)
    args = ap.parse_args(argv[:split])
    cmd = argv[split + 1:]
    manifest = json.loads(args.manifest.read_text())
    cache_root = args.cache_root or args.root.with_name(args.root.name + "-cache")
    env = build_env(args.root, manifest, args.draft_vocab, cache_root)
    os.execvpe(cmd[0], cmd, env)


if __name__ == "__main__":
    main()
