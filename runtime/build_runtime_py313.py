#!/usr/bin/env python3
"""Rebuild the vLLM 0.31.0 runtime dataset for Python 3.13, the Python of Kaggle's current GPU image.

The runtime dataset (codywhatleymd/vllm-v0310-arc3) ships six layers of the vllm/vllm-openai:v0.31.0 image:
layer 8 holds the CUDA 13.0 toolkit and gcc, and layers 20, 21, 24, 27 and 31 hold
usr/local/lib/python3.12/dist-packages. The notebook starts vLLM with the kernel's own interpreter, so those
packages only load on Python 3.12, which is why the notebook pinned a 10-06 container image. Kaggle's current
image runs Python 3.13 (checked 10-26: the RTX probe logs and gcr.io/kaggle-gpu-images/python:latest, built 10-22).

This script keeps layer 8 as it is and replaces the five Python layers with one layer holding the same package
set under usr/local/lib/python3.13/dist-packages, every package at the version the image ships:

  - packages whose recorded wheel tag (dist-info/WHEEL) is version-independent (py3-none, abi3) are copied
    unchanged from the image layers;
  - packages whose wheel tag names a CPython ABI (cp312-cp312) are replaced by their cp313 wheel at the same
    version, downloaded by --download-wheels (torch, torchvision, torchaudio, torchcodec from the PyTorch cu130
    index, the rest from PyPI). The tag is the authority, not the file names: triton, torchvision, xgrammar and
    others ship ABI-bound extensions without "cpython-312" in the name (10-26: a filename-only check missed 7);
  - vllm itself is abi3 and is copied unchanged, except its vendored DeepGEMM extension
    (third_party/deep_gemm/_C.cpython-312-*.so). vLLM 0.31.0 enables DeepGEMM on sm120 (support_deep_gemm()
    includes capability family 120) and the 10-18 Kaggle run loaded it ("DeepGEMM E8M0 enabled ... vendored
    vllm.third_party.deep_gemm"), so it must work on 3.13. The PyPI vllm 0.31.0 wheel is the same build as the
    image (its cp312 DeepGEMM module and abi3 modules are byte-identical, checked here) and also ships
    _C.cpython-313; that module replaces the cp312 one;
  - deep_ep (built from source in the image, no cp313 wheel exists) is left out. vLLM imports it only through
    has_deep_ep*() checks and the deepep_* all-to-all modules, which run only with expert parallelism across
    ranks (use_all2all_kernels needs use_ep and dp/pcp size > 1 or sequence parallel); we serve on one GPU.

The ARC3 overlay is NOT applied here: the notebook's applier verifies stock hashes and patches at startup, so the
tree must stay stock. The script checks that every overlay target matches its recorded stock hash.

Wheel installation runs inside the Kaggle image itself (docker, --kaggle-image) with that image's Python and uv,
so the interpreter that installs is the one that will import.

Usage:
  build_runtime_py313.py --src <vllm-v0310-arc3 dataset dir> --work <scratch dir> --out <new dataset dir> \
      [--download-wheels] [--kaggle-image gcr.io/kaggle-gpu-images/python:latest]
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import shutil
import subprocess
import sys
from pathlib import Path

PY312 = "usr/local/lib/python3.12/dist-packages"
PY313 = "usr/local/lib/python3.13/dist-packages"
PYTHON_LAYERS = (20, 21, 24, 27, 31)
TOOLKIT_LAYER = 8
NEW_LAYER_INDEX = 100
KEEP_ABI3_DESPITE_CP312 = {"vllm"}
DROP = {"deep_ep"}
TORCH_INDEX = "https://download.pytorch.org/whl/cu130"
TORCH_INDEX_PACKAGES = {"torch", "torchvision", "torchaudio", "torchcodec"}
PLATFORMS = ("manylinux_2_28_x86_64", "manylinux_2_27_x86_64", "manylinux_2_24_x86_64", "manylinux_2_17_x86_64",
             "manylinux2014_x86_64", "manylinux_2_5_x86_64", "manylinux1_x86_64", "linux_x86_64")


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    print("$", " ".join(cmd), flush=True)
    return subprocess.run(cmd, check=True, **kwargs)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 24), b""):
            digest.update(block)
    return digest.hexdigest()


def extract_python_layers(src: Path, manifest: dict, root: Path) -> None:
    """Unpack the Python layers in index order and replay their whiteouts, as the notebook's installer does."""
    layers = {int(layer["index"]): layer for layer in manifest["selected_layers"]}
    root.mkdir(parents=True, exist_ok=True)
    for index in PYTHON_LAYERS:
        layer = layers[index]
        for whiteout in layer.get("whiteouts", []):
            if whiteout["kind"] == "opaque" and whiteout["target"] not in ("", "."):
                shutil.rmtree(root / whiteout["target"], ignore_errors=True)
        decompressor = ["--use-compress-program=pigz"] if shutil.which("pigz") else ["-z"]
        run(["tar", "-xf", str(src / layer["file"]), "-C", str(root), "--no-same-owner", *decompressor])
        for whiteout in layer.get("whiteouts", []):
            (root / whiteout["marker"]).unlink(missing_ok=True)
            if whiteout["kind"] == "file":
                target = root / whiteout["target"]
                if target.is_dir() and not target.is_symlink():
                    shutil.rmtree(target)
                else:
                    target.unlink(missing_ok=True)


def read_packages(dist: Path) -> dict[str, dict]:
    """Name, version, RECORD file list and CPython-3.12 extension modules of every installed distribution."""
    packages = {}
    for info in sorted(dist.glob("*.dist-info")):
        name = version = None
        for line in (info / "METADATA").read_text(errors="replace").splitlines():
            if line.startswith("Name:") and name is None:
                name = line.split(":", 1)[1].strip()
            elif line.startswith("Version:") and version is None:
                version = line.split(":", 1)[1].strip()
            elif not line.strip():
                break
        record = info / "RECORD"
        files = [row[0] for row in csv.reader(io.StringIO(record.read_text())) if row] if record.exists() else []
        wheel = info / "WHEEL"
        tags = [l.split(":", 1)[1].strip() for l in wheel.read_text().splitlines() if l.startswith("Tag:")] if wheel.exists() else []
        abis = {tag.split("-")[1] for tag in tags if tag.count("-") == 2}
        packages[name] = {
            "version": version, "info": info.name, "files": files, "tags": tags,
            "cpython_abi": sorted(a for a in abis if a.startswith("cp") and a != "abi3"),
            "cp312_files": [f for f in files if "cpython-312" in f and (f.endswith(".so") or ".so." in f)],
        }
    return packages


def remove_distribution(dist: Path, package: dict) -> int:
    """Delete a distribution's recorded files that live inside dist-packages, then its dist-info directory."""
    removed = 0
    for relative in package["files"]:
        if relative.startswith("..") or relative.startswith("/"):
            continue
        path = dist / relative
        if path.is_file() or path.is_symlink():
            path.unlink()
            removed += 1
    shutil.rmtree(dist / package["info"], ignore_errors=True)
    for directory in sorted({(dist / f).parent for f in package["files"] if not f.startswith("..")},
                            key=lambda p: len(p.parts), reverse=True):
        while directory != dist and directory.is_dir() and not any(directory.iterdir()):
            directory.rmdir()
            directory = directory.parent
    return removed


def vendored_deepgemm_for_py313(packages: dict, dist: Path, wheels: Path) -> None:
    """Swap vLLM's vendored DeepGEMM extension for the cp313 build from the matching PyPI vllm wheel.

    The PyPI wheel must be the image's build: its cp312 module has to match the image's byte for byte.
    """
    version = packages["vllm"]["version"]
    found = sorted(wheels.glob(f"vllm-{version}-*.whl"))
    if len(found) != 1:
        raise SystemExit(f"need exactly one vllm-{version} wheel in {wheels} (use --download-wheels), found {found}")
    import zipfile
    stem = "vllm/third_party/deep_gemm/_C.cpython-3{}-x86_64-linux-gnu.so"
    with zipfile.ZipFile(found[0]) as wheel:
        theirs_312 = wheel.read(stem.format(12))
        ours_312 = (dist / stem.format(12)).read_bytes()
        if hashlib.sha256(theirs_312).digest() != hashlib.sha256(ours_312).digest():
            raise SystemExit("PyPI vllm wheel's cp312 DeepGEMM differs from the image's: not the same build")
        (dist / stem.format(13)).write_bytes(wheel.read(stem.format(13)))
    (dist / stem.format(12)).unlink()
    print(f"  vendored DeepGEMM: cp312 matched the PyPI vllm {version} wheel byte for byte; installed its cp313 build",
          flush=True)


def download_wheels(requirements: list[str], wheels: Path) -> None:
    wheels.mkdir(parents=True, exist_ok=True)
    platform_args = [arg for platform in PLATFORMS for arg in ("--platform", platform)]
    for requirement in requirements:
        index = ["--index-url", TORCH_INDEX] if requirement.split("==")[0].lower() in TORCH_INDEX_PACKAGES else []
        run([sys.executable, "-m", "pip", "download", "-q", "--no-deps", "--only-binary=:all:",
             "--python-version", "3.13", "--implementation", "cp", "--abi", "cp313", *platform_args, *index,
             "-d", str(wheels), requirement])


def install_wheels_in_kaggle_image(image: str, dist: Path, wheels: Path, requirements: list[str]) -> None:
    """Install the cp313 wheels into the tree with the Kaggle image's own Python 3.13 and uv, then byte-compile.

    The copied packages carry cpython-312 bytecode, which 3.13 ignores; without fresh bytecode the server's first
    start would compile vLLM and torch from source. The 3.12 bytecode is dropped and the tree is compiled by the
    same interpreter that will import it (tar keeps source mtimes, so timestamp-based .pyc stay valid).
    """
    uid_gid = f"{Path.home().stat().st_uid}:{Path.home().stat().st_gid}"
    script = ("set -e; python3 --version; "
              f"uv pip install --python /usr/bin/python3 --target /dist --no-deps --no-index --find-links /wheels "
              + " ".join(f"'{r}'" for r in requirements) + "; "
              "find /dist -name '*.cpython-312.pyc' -delete; "
              "python3 -m compileall -q -j 0 /dist > /tmp/compileall.log 2>&1 || "
              "echo \"compileall: $(grep -c . /tmp/compileall.log) lines of complaints (files that do not compile on 3.13)\"; "
              f"chown -R {uid_gid} /dist")
    run(["docker", "run", "--rm", "--entrypoint", "/bin/bash", "-v", f"{dist}:/dist", "-v", f"{wheels}:/wheels:ro",
         image, "-c", script])


def check_tree(dist: Path, manifest: dict, expected: dict[str, str]) -> dict:
    """Overlay targets still stock, every replaced package present at its version, and the cp312 leftovers."""
    stock = {"stock": 0, "changed": 0, "missing": 0, "added_by_overlay": 0}
    for overlay in manifest["patch"]["overlay_files"]:
        target = dist / overlay["target"]
        if overlay.get("stock_sha256") is None:   # a file the overlay creates: must not exist yet
            stock["added_by_overlay" if not target.exists() else "changed"] += 1
        elif not target.exists():
            stock["missing"] += 1
        elif sha256_file(target) == overlay["stock_sha256"]:
            stock["stock"] += 1
        else:
            stock["changed"] += 1
    installed = {name.lower().replace("_", "-"): p["version"] for name, p in read_packages(dist).items()}
    wrong = {name: (version, installed.get(name.lower().replace("_", "-")))
             for name, version in expected.items()
             if installed.get(name.lower().replace("_", "-")) != version}
    leftovers = sorted(str(p.relative_to(dist)) for p in dist.rglob("*cpython-312*.so*"))
    return {"overlay_targets": stock, "version_mismatches": wrong, "cp312_leftovers": leftovers,
            "distributions": len(installed)}


PATCH_BUNDLE_FILES = ("PATCH_IDENTITY.json", "PATCH_README.md")   # the applier verifies against PATCH_IDENTITY.json


def write_patch_bundle_and_readme(src: Path, out: Path, manifest: dict, requirements: list[str]) -> None:
    """Copy the overlay patch bundle unchanged (it names no Python version) and write this dataset's README."""
    for name in (manifest["patch"]["artifact"], manifest["patch"]["applier"], *PATCH_BUNDLE_FILES):
        shutil.copy2(src / name, out / name)
    (out / "README.md").write_text(
        "# vLLM 0.31.0 ARC3 runtime for Python 3.13\n\n"
        "The vllm/vllm-openai:v0.31.0 runtime of codywhatleymd/vllm-v0310-arc3, rebuilt for Python 3.13 (the Python of "
        "Kaggle's current GPU image) by scripts/runtime_0310/build_runtime_py313.py in the arc-prize-2026 repo.\n\n"
        "- layer 8: the image's CUDA 13.0 toolkit layer, unchanged.\n"
        "- layer 100: usr/local/lib/python3.13/dist-packages with the image's package set at the image's versions. "
        "Packages without CPython-3.12 extension modules are copied unchanged; these were replaced by their cp313 wheels "
        "at the same version: " + ", ".join(requirements) + ".\n"
        "- deep_ep (source-built, multi-GPU expert-parallel all-to-all only) is not included.\n"
        "- The ARC3 overlay (arc3_vllm_v0310_arc3_overlay.tar.blob + apply_vllm_v0310_arc3.py + PATCH_IDENTITY.json) "
        "is identical to vllm-v0310-arc3's and is applied at startup; every overlay target in layer 100 is stock.\n\n"
        "runtime-manifest.json records the rebuild under `py313_rebuild`.\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--src", type=Path, required=True, help="the vllm-v0310-arc3 dataset directory")
    parser.add_argument("--work", type=Path, required=True, help="scratch directory (needs ~25 GB)")
    parser.add_argument("--out", type=Path, required=True, help="output dataset directory")
    parser.add_argument("--wheels", type=Path, default=None, help="cp313 wheel directory (default: WORK/wheels)")
    parser.add_argument("--download-wheels", action="store_true")
    parser.add_argument("--kaggle-image", default="gcr.io/kaggle-gpu-images/python:latest")
    args = parser.parse_args()

    manifest = json.loads((args.src / "runtime-manifest.json").read_text())
    if manifest["dist_packages"].strip("/") != PY312:
        raise SystemExit(f"unexpected dist_packages {manifest['dist_packages']!r}")
    root = args.work / "root"
    wheels = args.wheels or args.work / "wheels"
    if root.exists():
        shutil.rmtree(root)
    extract_python_layers(args.src, manifest, root)
    dist312 = root / PY312
    packages = read_packages(dist312)

    untagged = sorted(name for name, p in packages.items() if not p["tags"])
    if untagged:
        raise SystemExit(f"distributions without a recorded wheel tag, cannot classify: {untagged}")
    replace = {name: p for name, p in packages.items() if p["cpython_abi"] and name not in DROP}
    hidden = sorted(name for name, p in packages.items() if p["cp312_files"] and not p["cpython_abi"])
    if set(hidden) - KEEP_ABI3_DESPITE_CP312:
        raise SystemExit(f"abi3/none-tagged distributions carrying cp312 modules: {hidden}")
    requirements = [f"{name}=={p['version']}" for name, p in sorted(replace.items())]
    print(f"{len(packages)} distributions; {len(replace)} to replace with cp313 wheels; drop {sorted(DROP)}; "
          f"keep abi3 {sorted(KEEP_ABI3_DESPITE_CP312)}", flush=True)
    if args.download_wheels:
        download_wheels(requirements, wheels)
        download_wheels([f"vllm=={packages['vllm']['version']}"], wheels)
    vendored_deepgemm_for_py313(packages, dist312, wheels)

    for name in sorted(replace) + sorted(DROP & set(packages)):
        removed = remove_distribution(dist312, packages[name])
        print(f"  removed {name} {packages[name]['version']}: {removed} files", flush=True)

    out_root = args.work / "py313"
    if out_root.exists():
        shutil.rmtree(out_root)
    (out_root / PY313).parent.mkdir(parents=True)
    shutil.move(str(dist312), str(out_root / PY313))
    install_wheels_in_kaggle_image(args.kaggle_image, out_root / PY313, wheels, requirements)
    for leftover in ("bin",):
        shutil.rmtree(out_root / PY313 / leftover, ignore_errors=True)

    report = check_tree(out_root / PY313, manifest, {name: p["version"] for name, p in replace.items()})
    print(json.dumps(report, indent=1), flush=True)
    if (report["overlay_targets"]["changed"] or report["overlay_targets"]["missing"] or report["version_mismatches"]
            or report["cp312_leftovers"]):
        raise SystemExit("tree check failed")

    args.out.mkdir(parents=True, exist_ok=True)
    blob = args.out / "layer-py313.tar.gz.blob"
    compressor = "pigz" if shutil.which("pigz") else "gzip"
    with blob.open("wb") as handle:
        tar = subprocess.Popen(["tar", "-cf", "-", "-C", str(out_root), "usr"], stdout=subprocess.PIPE)
        subprocess.run([compressor, "-c"], stdin=tar.stdout, stdout=handle, check=True)
        if tar.wait() != 0:
            raise SystemExit("tar failed")
    digest = sha256_file(blob)
    blob = blob.rename(args.out / f"layer-{NEW_LAYER_INDEX}-{digest}.tar.gz.blob")

    layers = {int(layer["index"]): layer for layer in manifest["selected_layers"]}
    toolkit = layers[TOOLKIT_LAYER]
    shutil.copy2(args.src / toolkit["file"], args.out / toolkit["file"])
    write_patch_bundle_and_readme(args.src, args.out, manifest, requirements)

    new_manifest = dict(manifest)
    new_manifest["dist_packages"] = PY313 + "/"
    new_manifest["python_version"] = "3.13"
    new_manifest["selected_layers"] = [toolkit, {
        "index": NEW_LAYER_INDEX, "file": blob.name, "size": blob.stat().st_size, "sha256": digest,
        "whiteouts": [], "note": "python3.13 dist-packages rebuilt from layers 20/21/24/27/31 by build_runtime_py313.py",
    }]
    new_manifest["selected_compressed_bytes"] = sum(int(layer["size"]) for layer in new_manifest["selected_layers"])
    new_manifest["py313_rebuild"] = {
        "source_layers": list(PYTHON_LAYERS), "replaced_with_cp313_wheels": requirements,
        "dropped": sorted(DROP), "kept_abi3_with_cp312_leftover": sorted(KEEP_ABI3_DESPITE_CP312),
        "installed_with_image": args.kaggle_image, "check": report,
    }
    (args.out / "runtime-manifest.json").write_text(json.dumps(new_manifest, indent=1))
    print(f"wrote {args.out}: layers {[layer['index'] for layer in new_manifest['selected_layers']]}, "
          f"{new_manifest['selected_compressed_bytes'] / 1e9:.2f} GB", flush=True)


if __name__ == "__main__":
    main()
