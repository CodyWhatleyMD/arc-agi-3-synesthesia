#!/usr/bin/env python3
"""Regenerate the vLLM 0.31.0 ARC3 overlay sources from Han Solo's e975732 overlay and vLLM's git history.

For every member of his overlay (plus the files his changes moved into) this replays the recipe in
recipe/plan.json: a 3-way merge (base = e975732, ours = his bytes, theirs = v0.31.0), the recorded
conflict resolutions (recipe/resolutions) and adaptations (recipe/edits). A "drop" must merge to
v0.31.0 byte for byte, i.e. upstream already carries his change; a "keep" requires v0.31.0's file
to equal e975732's. With --check the result must match the committed overlay/ tree exactly.

usage: port_overlay.py --his-overlay TAR --vllm-repo GIT_DIR [--out DIR] [--check]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
RECIPE = HERE / "recipe"
OVERLAY = HERE / "overlay"
HIS_OVERLAY_SHA256 = "e3a6fe0d9f010bc1fb66e53e7dc6fde43272824d5200da5a49b5c4456065e0cb"


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def git_show(repo: Path, rev: str, path: str) -> bytes | None:
    r = subprocess.run(["git", "-C", str(repo), "-c", "gc.auto=0", "show", f"{rev}:{path}"], capture_output=True)
    return r.stdout if r.returncode == 0 else None


def load_py(path: Path, name: str):
    ns: dict = {}
    exec(path.read_text(), ns)
    return ns[name]


def merge3(his: bytes, base: bytes, v031: bytes) -> tuple[str, int]:
    with tempfile.TemporaryDirectory() as d:
        paths = []
        for name, data in (("his", his), ("base", base), ("v031", v031)):
            p = Path(d) / name
            p.write_bytes(data)
            paths.append(str(p))
        r = subprocess.run(["git", "merge-file", "-p", "--diff3", "-L", "his", "-L", "e975732", "-L", "v0.31.0",
                            *paths], capture_output=True)
        if r.returncode < 0 or r.returncode > 127:
            raise SystemExit(f"git merge-file failed: {r.stderr.decode()}")
        return r.stdout.decode(), r.returncode


def resolve(text: str, res: list) -> str:
    lines = text.splitlines(keepends=True)
    out, i, k = [], 0, 0
    while i < len(lines):
        if lines[i].startswith("<<<<<<< "):
            parts: dict[str, list[str]] = {"his": [], "base": [], "v031": []}
            i += 1
            for key, stop in (("his", "||||||| "), ("base", "======="), ("v031", ">>>>>>> ")):
                while not lines[i].startswith(stop):
                    parts[key].append(lines[i])
                    i += 1
                i += 1
            r = res[k]
            k += 1
            out += parts[r] if isinstance(r, str) else [r[1]]
            continue
        out.append(lines[i])
        i += 1
    if k != len(res):
        raise SystemExit(f"{k} conflicts, {len(res)} resolutions")
    return "".join(out)


def apply_edits(text: str, edits: list[tuple[str, str]], label: str) -> str:
    for n, (old, new) in enumerate(edits):
        if text.count(old) != 1:
            raise SystemExit(f"{label}: edit {n} anchor occurs {text.count(old)} times")
        text = text.replace(old, new, 1)
    return text


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--his-overlay", type=Path, required=True)
    ap.add_argument("--vllm-repo", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=None, help="write the regenerated tree here")
    ap.add_argument("--check", action="store_true", help="require equality with the committed overlay/")
    args = ap.parse_args()

    tar_bytes = args.his_overlay.read_bytes()
    if sha(tar_bytes) != HIS_OVERLAY_SHA256:
        raise SystemExit(f"his overlay sha256 {sha(tar_bytes)} != {HIS_OVERLAY_SHA256}")
    his: dict[str, bytes] = {}
    with tarfile.open(args.his_overlay) as tf:
        for m in tf.getmembers():
            stream = tf.extractfile(m) if m.isfile() else None
            if stream is None:
                raise SystemExit(f"his overlay member {m.name!r} is not a regular file")
            his[m.name] = stream.read()
    plan = json.loads((RECIPE / "plan.json").read_text())
    base_rev, v031_rev = plan["base_commit"], plan["target_commit"]
    planned_his = {f["target"] for f in plan["files"] if f["action"] != "new"}
    if planned_his != set(his):
        raise SystemExit(f"plan/overlay mismatch: {sorted(planned_his ^ set(his))}")

    generated: dict[str, bytes] = {}
    summary = []
    for f in plan["files"]:
        t, action = f["target"], f["action"]
        base = git_show(args.vllm_repo, base_rev, t) or b""
        v031 = git_show(args.vllm_repo, v031_rev, t)
        res = load_py(RECIPE / "resolutions" / f["resolution"], "RES") if f.get("resolution") else []
        edits = [e for name in f.get("edits", []) for e in load_py(RECIPE / "edits" / name, "EDITS")]
        if action == "new":
            if v031 is None:
                raise SystemExit(f"{t}: a new member must start from a v0.31.0 file")
            text = apply_edits(v031.decode(), edits, t)
            generated[t] = text.encode()
            n_conf = 0
        else:
            text, n_conf = merge3(his[t], base, v031 or b"")
            if n_conf:
                text = resolve(text, res)
            elif res:
                raise SystemExit(f"{t}: resolutions given but the merge is clean")
            text = apply_edits(text, edits, t)
            if action == "keep":
                if (v031 or b"") != base:
                    raise SystemExit(f"{t}: keep requires v0.31.0 == e975732")
                if text.encode() != his[t]:
                    raise SystemExit(f"{t}: keep must reproduce his bytes")
                generated[t] = his[t]
            elif action == "port":
                generated[t] = text.encode()
            elif action == "drop":
                if text.encode() != v031:
                    raise SystemExit(f"{t}: drop requires the merge to equal v0.31.0")
            else:
                raise SystemExit(f"{t}: unknown action {action}")
        summary.append({"target": t, "action": action, "conflicts": n_conf,
                        "his_sha256": sha(his[t]) if t in his else None,
                        "stock_v031_sha256": sha(v031) if v031 is not None else None,
                        "ported_sha256": sha(generated[t]) if t in generated else None})
        print(f"{action:5s} conflicts={n_conf} {t}")

    if args.out:
        for t, data in generated.items():
            p = args.out / t
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
        (args.out / "PORT_SUMMARY.json").write_text(json.dumps(summary, indent=1) + "\n")
    if args.check:
        committed = {str(p.relative_to(OVERLAY)): p.read_bytes() for p in OVERLAY.rglob("*") if p.is_file()}
        diff = sorted(set(committed) ^ set(generated)) + sorted(
            t for t in set(committed) & set(generated) if committed[t] != generated[t])
        if diff:
            raise SystemExit(f"overlay/ differs from the recipe output: {diff}")
        print(f"check OK: overlay/ ({len(committed)} files) equals the recipe output")
    counts = {a: sum(1 for s in summary if s["action"] == a) for a in ("keep", "port", "drop", "new")}
    print(f"{len(summary)} entries: {counts}; overlay members: {len(generated)}")


if __name__ == "__main__":
    sys.exit(main())
