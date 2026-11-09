#!/usr/bin/env python3
"""Offline checks of the staged vLLM 0.31.0 ARC3 runtime dataset (no GPU).

  1. every image layer blob matches the size and sha256 in runtime-manifest.json, which match the
     committed registry manifest; the manifest's patch block equals PATCH_IDENTITY.json. A layer rebuilt by
     build_runtime_py313.py (index past the registry's layers; the manifest carries py313_rebuild) is checked
     against the manifest's own size and sha256 instead
  2. the overlay tar matches overlay_sha256, holds exactly the identity's members, each with its pinned
     sha256, sorted, 0644, root-owned, mtime 0, and equals scripts/runtime_0310/overlay byte for byte
  3. the stock bytes of every target, read from the layers, match stock_sha256 (None for new files)
  4. the shipped applier installs onto those stock files (installed=N), a second run writes nothing
     (already-patched=N), and every installed file equals its overlay member
  5. a target that matches neither stock nor patched makes the applier fail before ANY file is written
  6. --print-generated-sha256 --stock-file reproduces patched_target_sha256 from the stock primary file
  7. every installed module byte-compiles

usage: validate_runtime_dataset.py DATASET_DIR
"""
from __future__ import annotations

import hashlib
import json
import py_compile
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build_runtime_0310 as B  # noqa: E402


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def run_applier(dataset: Path, applier: str, site: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-I", str(dataset / applier), str(site)], capture_output=True, text=True)


def main() -> None:
    dataset = Path(sys.argv[1]).resolve()
    manifest = json.loads((dataset / "runtime-manifest.json").read_text())
    identity = json.loads((dataset / "PATCH_IDENTITY.json").read_text())
    registry = json.loads((HERE / "image" / "manifest_amd64.json").read_text())
    checks: list[str] = []
    B.DIST_PACKAGES = manifest["dist_packages"]   # census() reads overlay targets under this dataset's dist-packages

    # 1. layers
    for layer in manifest["selected_layers"]:
        blob = dataset / layer["file"]
        if layer["index"] >= len(registry["layers"]):   # rebuilt by build_runtime_py313.py, not an image layer
            assert "py313_rebuild" in manifest, f"layer {layer['index']} is not in the registry manifest"
            assert layer["size"] == blob.stat().st_size, layer["index"]
        else:
            reg = registry["layers"][layer["index"]]
            assert reg["digest"] == layer["digest"] == "sha256:" + layer["sha256"], layer["index"]
            assert reg["size"] == layer["size"] == blob.stat().st_size, layer["index"]
        assert B.sha256_file(blob) == layer["sha256"], f"layer {layer['index']} sha256"
    patch = dict(manifest["patch"])
    patch.pop("files")
    assert patch == identity, "manifest patch block != PATCH_IDENTITY.json"
    assert manifest["amd64_manifest_digest"] == B.AMD64_MANIFEST_DIGEST and manifest["vllm_version"] == "0.31.0"
    checks.append(f"layers: {len(manifest['selected_layers'])} blobs, {manifest['selected_compressed_bytes']:,} B, "
                  + ("sizes and sha256 match the registry manifest (rebuilt layers: the runtime manifest)"
                     if "py313_rebuild" in manifest else "sizes and sha256 match the registry manifest"))

    # 2. overlay tar
    tar_path = dataset / identity["artifact"]
    assert sha(tar_path.read_bytes()) == identity["overlay_sha256"]
    expected = {e["target"]: e for e in identity["overlay_files"]}
    with tarfile.open(tar_path) as tf:
        members = tf.getmembers()
        names = [m.name for m in members]
        assert names == sorted(expected), "overlay members differ from the identity (or are unsorted)"
        payloads = {}
        for m in members:
            assert m.isfile() and m.mode == 0o644 and m.uid == m.gid == 0 and m.mtime == 0, m.name
            stream = tf.extractfile(m)
            assert stream is not None
            payloads[m.name] = stream.read()
            assert sha(payloads[m.name]) == expected[m.name]["sha256"], m.name
    committed = {str(p.relative_to(HERE / "overlay")): p.read_bytes()
                 for p in (HERE / "overlay").rglob("*") if p.is_file()}
    assert committed == payloads, "overlay tar != scripts/runtime_0310/overlay"
    checks.append(f"overlay: {len(payloads)} members, sha256 {identity['overlay_sha256']}, "
                  "pinned per-file digests, equals the committed sources")

    # 3. stock bytes from the layers
    stock: dict[str, bytes | None] = {}
    for layer in manifest["selected_layers"]:
        _, whiteouts, files, _ = B.census(dataset / layer["file"], set(expected), set())
        B.apply_whiteouts(stock, whiteouts)
        stock.update(files)
    for target, entry in expected.items():
        got = sha(stock[target]) if stock.get(target) is not None else None
        assert got == entry["stock_sha256"], f"{target}: stock {got} != {entry['stock_sha256']}"
    n_new = sum(1 for e in expected.values() if e["stock_sha256"] is None)
    checks.append(f"stock: {len(expected) - n_new} targets match their pinned stock bytes in the layers, "
                  f"{n_new} new files absent from the image")

    with tempfile.TemporaryDirectory() as tmp:
        # 4. install, idempotency
        site = Path(tmp) / "site"
        for target, data in stock.items():
            if target in expected and data is not None:
                (site / target).parent.mkdir(parents=True, exist_ok=True)
                (site / target).write_bytes(data)
        first = run_applier(dataset, identity["applier"], site)
        assert first.returncode == 0, first.stderr
        assert f"installed={len(expected)}, already-patched=0" in first.stdout, first.stdout
        second = run_applier(dataset, identity["applier"], site)
        assert second.returncode == 0 and f"installed=0, already-patched={len(expected)}" in second.stdout, second.stdout
        for target, data in payloads.items():
            assert (site / target).read_bytes() == data, target
        checks.append(f"install: '{first.stdout.strip()}', then '{second.stdout.strip()}'; installed files == overlay")
        # 7. byte-compile what was installed
        for target in payloads:
            py_compile.compile(str(site / target), cfile=str(Path(tmp) / "pyc" / (target + "c")), doraise=True)
        checks.append(f"py_compile: {len(payloads)} installed modules compile")

        # 5. rejection before any write
        site2 = Path(tmp) / "site2"
        for target, data in stock.items():
            if target in expected and data is not None:
                (site2 / target).parent.mkdir(parents=True, exist_ok=True)
                (site2 / target).write_bytes(data)
        victim = sorted(t for t in expected if expected[t]["stock_sha256"])[-1]
        (site2 / victim).write_bytes(stock[victim] + b"\n# locally modified\n")
        before = {p: p.read_bytes() for p in site2.rglob("*") if p.is_file()}
        bad = run_applier(dataset, identity["applier"], site2)
        after = {p: p.read_bytes() for p in site2.rglob("*") if p.is_file()}
        assert bad.returncode != 0 and "expected pinned stock" in bad.stderr, (bad.returncode, bad.stderr[-300:])
        assert before == after, "the applier wrote files before rejecting a modified target"
        checks.append(f"rejection: a modified {victim} fails the applier with nothing written")

        # 6. generated primary hash
        primary_stock = Path(tmp) / "primary_stock.py"
        primary_stock.write_bytes(stock[identity["target"]] or b"")
        gen = subprocess.run([sys.executable, "-I", str(dataset / identity["applier"]), "--print-generated-sha256",
                              "--stock-file", str(primary_stock)], capture_output=True, text=True)
        assert gen.returncode == 0 and gen.stdout.strip() == identity["patched_target_sha256"], gen
        checks.append(f"primary: {identity['target']} stock {identity['stock_target_sha256'][:12]} -> "
                      f"patched {identity['patched_target_sha256'][:12]}")

    for c in checks:
        print("PASS", c)
    print(f"all {len(checks)} checks passed")


if __name__ == "__main__":
    main()
