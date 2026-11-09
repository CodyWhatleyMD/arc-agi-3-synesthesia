#!/usr/bin/env python3
"""Run the harness's OWN runtime installer against a staged runtime dataset, with only the pins swapped.

The Arm B notebook's setup step (setup_commands.json of the TAAF bundle) unpacks the runtime
dataset's image layers, replays whiteouts, runs the dataset's applier on the extracted
dist-packages and fails closed unless the runtime and overlay identities match its pins
(validate_prefix_cache_runtime). This script takes that setup source verbatim, replaces only
RUNTIME_OWNER, RUNTIME_SLUG and the three FINE_PREFIX_CACHE_* pin blocks with harness_pins.json,
stops before the server launch, and calls install_image_runtime() and build_image_runtime_env().
A pass means the harness switches to the new runtime by changing those constants alone.

--keep-pins runs the setup script with its own pins (Han Solo's e975732 runtime). --kv-copy-patch inserts the
kv_copy_hook.HOOK the notebook uses for that runtime, so install_image_runtime() also applies
patch_kv_copy_chunked.py; afterwards the dataset's own applier is rerun on the installed tree (it must write
nothing), the patch is rerun (already patched) and validate_prefix_cache_runtime() is rerun.

usage: harness_contract_check.py --setup-commands JSON --bundle-dir DIR --dataset DIR
                                 (--pins harness_pins.json | --keep-pins) --runtime-root DIR
                                 [--work-dir DIR] [--kv-copy-patch patch_kv_copy_chunked.py]
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kv_copy_hook  # noqa: E402

PIN_BLOCKS = ("FINE_PREFIX_CACHE_RUNTIME_IDENTITY", "FINE_PREFIX_CACHE_PATCH_IDENTITY",
              "FINE_PREFIX_CACHE_REQUIRED_OVERLAYS")
LAUNCH_ANCHOR = "print(f'vLLM runtime dataset path: {RUNTIME_DATASET}', flush=True)\n"


def setup_source(setup_commands: Path, kv_copy_patch: Path | None = None) -> str:
    script = json.loads(setup_commands.read_text())[0]
    head = "\"$PYTHON\" - <<'PYSETUP'\n"
    if not script.startswith(head) or not script.rstrip().endswith("PYSETUP"):
        raise SystemExit("unexpected setup_commands layout")
    body = script[len(head):script.rstrip().rfind("PYSETUP")]
    if body.count(LAUNCH_ANCHOR) != 1:
        raise SystemExit("launch anchor not found exactly once")
    if kv_copy_patch is not None:
        assert kv_copy_hook.LAUNCH_ANCHOR == LAUNCH_ANCHOR
        body = kv_copy_hook.insert_hook(body, str(kv_copy_patch))
    return body[:body.index(LAUNCH_ANCHOR)]


def swap_pins(src: str, pins: dict) -> str:
    for name in ("RUNTIME_OWNER", "RUNTIME_SLUG"):
        src, n = re.subn(rf"^{name} = '[^']*'$", f"{name} = {pins[name]!r}", src, flags=re.M)
        if n != 1:
            raise SystemExit(f"{name}: {n} assignments")
    for name in PIN_BLOCKS:
        pattern = re.compile(rf"^{name} = \{{\n.*?^\}}\n", re.M | re.S)
        src, n = pattern.subn(lambda _m, n=name: f"{n} = {pins[n]!r}\n", src)
        if n != 1:
            raise SystemExit(f"{name}: {n} blocks")
    return src


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--setup-commands", type=Path, required=True)
    ap.add_argument("--bundle-dir", type=Path, required=True, help="TAAF bundle (for the draft vocabulary)")
    ap.add_argument("--dataset", type=Path, required=True)
    pins_arg = ap.add_mutually_exclusive_group(required=True)
    pins_arg.add_argument("--pins", type=Path)
    pins_arg.add_argument("--keep-pins", action="store_true", help="run with the setup script's own pins")
    ap.add_argument("--runtime-root", type=Path, required=True, help="where the harness unpacks the image")
    ap.add_argument("--work-dir", type=Path, default=None)
    ap.add_argument("--kv-copy-patch", type=Path, default=None, help="insert kv_copy_hook with this patch script")
    args = ap.parse_args()
    src = setup_source(args.setup_commands, args.kv_copy_patch.resolve() if args.kv_copy_patch else None)
    if args.keep_pins:
        pins = {name: ast.literal_eval(re.search(rf"^{name} = ('[^']*')$", src, re.M).group(1))
                for name in ("RUNTIME_OWNER", "RUNTIME_SLUG")}
    else:
        pins = json.loads(args.pins.read_text())
        src = swap_pins(src, pins)
    work = args.work_dir or args.runtime_root.with_name(args.runtime_root.name + "-work")
    work.mkdir(parents=True, exist_ok=True)
    os.environ.update({
        "TAAF_KAGGLE_WORKING_DIR": str(work),
        "TAAF_KAGGLE_BUNDLE_DIR": str(args.bundle_dir),
        "TAAF_KAGGLE_INPUT_PATHS": json.dumps({f"{pins['RUNTIME_OWNER']}/{pins['RUNTIME_SLUG']}": str(args.dataset)}),
        "TAAF_IMAGE_RUNTIME_ROOT": str(args.runtime_root),
    })
    ns: dict = {"__name__": "harness_setup"}
    exec(compile(src, "setup_commands.json[0]", "exec"), ns)
    if Path(ns["RUNTIME_DATASET"]) != args.dataset:
        raise SystemExit(f"harness resolved the runtime dataset to {ns['RUNTIME_DATASET']}")
    manifest = ns["install_image_runtime"]()
    env = ns["build_image_runtime_env"](manifest)
    dist = args.runtime_root / manifest["dist_packages"]
    version = (dist / "vllm/_version.py").read_text()
    print("harness install OK:", re.search(r"__version__ = version = '([^']+)'", version).group(1))
    print("harness env: VLLM_ARC3_GDN_RECOVERSSM=%s VLLM_GDN_DECODE_KERNEL=%s VLLM_QWEN4_EXP_DRAFT_VOCAB=%s" % (
        env.get("VLLM_ARC3_GDN_RECOVERSSM"), env.get("VLLM_GDN_DECODE_KERNEL"), env.get("VLLM_QWEN4_EXP_DRAFT_VOCAB")))
    print("harness PYTHONPATH head:", env["PYTHONPATH"].split(os.pathsep)[:2])
    if args.kv_copy_patch is not None:
        utils = dist / "vllm/v1/worker/utils.py"
        print("installed vllm/v1/worker/utils.py sha256:", hashlib.sha256(utils.read_bytes()).hexdigest())
        applier = args.dataset / manifest["patch"]["applier"]
        again = subprocess.run([sys.executable, "-I", str(applier), str(dist)], capture_output=True, text=True)
        print("dataset applier rerun:", again.returncode, again.stdout.strip(), again.stderr.strip())
        if again.returncode != 0 or "installed=0," not in again.stdout:
            raise SystemExit("the runtime's own applier does not accept the patched tree")
        patch = subprocess.run([sys.executable, "-I", str(args.kv_copy_patch), str(dist)],
                               capture_output=True, text=True)
        print("kv copy patch rerun:", patch.returncode, patch.stdout.strip(), patch.stderr.strip())
        if patch.returncode != 0 or "already patched" not in patch.stdout:
            raise SystemExit("the KV copy patch is not idempotent on the installed tree")
        ns["validate_prefix_cache_runtime"](manifest)
        print("validate_prefix_cache_runtime rerun: OK")


if __name__ == "__main__":
    sys.exit(main())
