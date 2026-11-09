"""Host-only test of `make_targets.py augment` (dihedral augmentation, 2026-10-08): a fake RECORDED root (6 boards:
2 eval, 4 train incl. a solid board and a flip_v-symmetric one; K=16 rows of bf16 (16, 2560)) -> augment -> the
original shards are symlinks, the manifest's boards/shards are verbatim, the eval set is unchanged, every added board
is kind=dihedral with the right cells/sha1/parent, symmetric boards are deduplicated, the result is deterministic.
Then a hand-written "recorded" dihedral shard (as `record --resume` would add, with a different K) and 3 CPU steps of
train.py on the augmented root. No GPU, no docker, ~30 s.  Run: python scripts/board_tower/tests/test_augment.py"""
import json
import os
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _common import PY, TEST_DIR, WT, run  # noqa: E402

sys.path.insert(0, str(WT))
import numpy as np                                   # noqa: E402
import torch                                         # noqa: E402
from scripts.board_tower import common as C          # noqa: E402

rng = np.random.default_rng(0)
rb = lambda: rng.integers(0, 16, (64, 64)).astype(np.uint8)  # noqa: E731
half = rb()
sym = np.concatenate([half[:32], half[:32][::-1]]).astype(np.uint8)          # flip_v-symmetric: flip_v == identity
assert np.array_equal(C.dihedral(sym, "flip_v"), sym)
src_boards = [(rb(), "cd82", 1, "eval"), (rb(), "m0r0", 2, "eval"),
              (rb(), "ls20", 1, "train"), (rb(), "vc33", 3, "train"),
              (np.full((64, 64), 3, np.uint8), "ls20", 2, "train"), (sym, "vc33", 1, "train")]

src = TEST_DIR / "aug_src"; src.mkdir(parents=True, exist_ok=True)
K = 16
meta = {"n_boards": 6, "n_train": 4, "n_eval": 2, "holdout_games": ["cd82", "m0r0"], "created": "t", "boards": []}
m = {"created": "t", "config": {"px_per_cell": 16, "tokens_per_board": 1024, "cells_per_token_side": 2, "patch": 16, "merge": 2,
                                "hidden": C.HIDDEN, "train_cells": K, "shard_boards": 32, "batch": 1},
     "holdout_games": ["cd82", "m0r0"], "boards": [], "shards": [], "recorder": {"checkpoint": "/model", "fake": True}}
for split, items in (("eval", [b for b in src_boards if b[3] == "eval"]), ("train", [b for b in src_boards if b[3] == "train"])):
    name = C.shard_name(split, 0)
    T = torch.randn(len(items), K, C.HIDDEN).to(torch.bfloat16)
    I = torch.stack([torch.tensor(sorted(np.random.default_rng(j).choice(1024, K, replace=False).tolist()), dtype=torch.int16) for j in range(len(items))])
    B = torch.from_numpy(np.stack([b[0] for b in items]))
    sh = C.write_shard(src / name, T, I, B); sh["split"] = split; m["shards"].append(sh)
    for j, (cells, game, level, _) in enumerate(items):
        e = {"sha1": C.board_sha1(cells), "game": game, "level": level, "kind": "event", "source": "x", "line": j, "split": split}
        meta["boards"].append(dict(e)); m["boards"].append(dict(e, shard=name, index=j))
np.savez_compressed(src / "boards.npz", cells=np.stack([b[0] for b in meta_b] if (meta_b := None) else [b[0] for b in [x for s in ("eval", "train") for x in src_boards if x[3] == s]]))
json.dump(meta, open(src / "boards.json", "w")); C.save_manifest(src, m)

out = TEST_DIR / "aug_out"
rc, text, log = run([PY, WT / "scripts/board_tower/make_targets.py", "augment", "--src", src, "--out", out], "augment.log", timeout=300)
assert rc == 0, f"augment failed, see {log}\n{text[-2000:]}"
ma = C.load_manifest(out); meta_a = json.load(open(out / "boards.json")); cells_a = np.load(out / "boards.npz")["cells"]
assert ma["boards"] == m["boards"] and ma["shards"] == m["shards"] and ma["config"] == m["config"], "manifest not verbatim"
assert ma["recorder"] == {} and ma["recorder_source"] == m["recorder"]
aug = ma["augmentation"]
assert aug["n_added"] == 17 and aug["n_source_train"] == 4 and aug["n_source_eval"] == 2, aug
assert aug["per_transform"] == {"rot90": 3, "rot180": 3, "rot270": 3, "flip_h": 2, "flip_v": 2, "transpose": 2, "antitranspose": 2}, aug["per_transform"]
assert aug["skipped"] == {"equals_existing_board": 8, "equals_earlier_transform": 3}, aug["skipped"]
for sh in m["shards"]:
    p = out / sh["file"]
    assert p.is_symlink() and p.resolve() == (src / sh["file"]).resolve(), p
rd = C.ShardReader(out)
t, ci, cells = rd.board("eval_0000.safetensors", 1)
assert tuple(t.shape) == (K, C.HIDDEN) and np.array_equal(cells.numpy(), src_boards[1][0])
assert meta_a["n_boards"] == 23 == len(meta_a["boards"]) == cells_a.shape[0] and meta_a["n_train"] == 21 and meta_a["n_eval"] == 2
assert meta_a["boards"][:6] == meta["boards"]
src_by_sha = {b["sha1"]: i for i, b in enumerate(meta["boards"])}
src_cells = np.load(src / "boards.npz")["cells"]
train_sha = {b["sha1"] for b in meta["boards"] if b["split"] == "train"}
eval_sha = {b["sha1"] for b in meta["boards"] if b["split"] == "eval"}
seen = set(src_by_sha)
for i, b in enumerate(meta_a["boards"][6:], start=6):
    assert b["kind"] == "dihedral" and b["split"] == "train" and b["parent_sha1"] in train_sha and b["aug"] in C.DIHEDRAL_NON_IDENTITY, b
    parent = src_cells[src_by_sha[b["parent_sha1"]]]
    assert np.array_equal(cells_a[i], C.dihedral(parent, b["aug"])) and C.board_sha1(cells_a[i]) == b["sha1"] and b["sha1"] not in seen, b
    pb = meta["boards"][src_by_sha[b["parent_sha1"]]]
    assert (b["game"], b["level"]) == (pb["game"], pb["level"])
    seen.add(b["sha1"])
assert {b["sha1"] for b in meta_a["boards"] if b["split"] == "eval"} == eval_sha, "eval set changed"
assert not any(b.get("aug") for b in meta_a["boards"] if b["split"] == "eval")
# determinism
out2 = TEST_DIR / "aug_out2"
rc, text, log = run([PY, WT / "scripts/board_tower/make_targets.py", "augment", "--src", src, "--out", out2], "augment2.log", timeout=300)
assert rc == 0, text[-2000:]
meta_b = json.load(open(out2 / "boards.json"))
assert meta_b["boards"] == meta_a["boards"] and np.array_equal(np.load(out2 / "boards.npz")["cells"], cells_a)
# refuses to clobber without --force
rc, text, log = run([PY, WT / "scripts/board_tower/make_targets.py", "augment", "--src", src, "--out", out], "augment3.log", timeout=300)
assert rc != 0 and "--force" in text, text[-500:]

# a "recorded" dihedral shard with a different K, appended as record --resume would, then 3 CPU training steps
added = meta_a["boards"][6:10]; K2 = 8
T = torch.randn(4, K2, C.HIDDEN).to(torch.bfloat16)
I = torch.stack([torch.tensor(sorted(np.random.default_rng(9 + j).choice(1024, K2, replace=False).tolist()), dtype=torch.int16) for j in range(4)])
B = torch.from_numpy(np.stack([cells_a[6 + j] for j in range(4)]))
name = C.shard_name("train", 1)
sh = C.write_shard(out / name, T, I, B); sh["split"] = "train"; ma["shards"].append(sh)
for j, b in enumerate(added):
    ma["boards"].append({"sha1": b["sha1"], "game": b["game"], "level": b["level"], "split": "train", "kind": "dihedral",
                         "source": b["source"], "line": b["line"], "shard": name, "index": j, "aug": b["aug"], "parent_sha1": b["parent_sha1"]})
C.save_manifest(out, ma)
os.environ["BOARD_TOWER_GPU"] = ""                      # CPU: _common.env_now() -> CUDA_VISIBLE_DEVICES=""
ck = TEST_DIR / "aug_ckpt"
rc, text, log = run([PY, WT / "scripts/board_tower/train.py", "--targets", out, "--out", ck, "--max-steps", "3", "--batch", "2", "--dim", "32",
                     "--depth", "1", "--heads", "2", "--eval-every", "0", "--warmup", "1", "--log-every", "1", "--loader-threads", "2"], "train_aug.log", timeout=600)
assert rc == 0, f"train failed, see {log}\n{text[-3000:]}"
assert "train boards 8 (K per shard [8, 16])" in text and "'dihedral': 4" in text and "'event': 4" in text, text[-3000:]
assert "EVAL held-out games: boards 2" in text and (ck / "best.pt").is_file() and "RLIMIT_NOFILE" in text, text[-1500:]
print(f"test_augment OK: 4 train boards -> {aug['n_added']} dihedral boards ({aug['per_transform']}), skipped {aug['skipped']}; "
      f"{len(m['shards'])} shards symlinked, eval set unchanged, deterministic; 3 CPU steps on the mixed-K augmented root; outputs {TEST_DIR}")
