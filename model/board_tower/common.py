"""Shared pieces of the board tower (plan S2c, 2026-10-03): constants, board hashing, the game split,
target shards and the manifest. No torch import at module level beyond what the shard IO needs.

Layout under TARGET_ROOT (default /media/ignaz/claude-extra/board_tower/targets):
  boards.npz          cells uint8 (N,64,64) in record order           (phase 1, host: make_targets.py enumerate)
  boards.json         per-board meta, same order, + holdout games     (phase 1)
  train_NNNN.safetensors / eval_NNNN.safetensors                      (phase 2, docker GPU 0: make_targets.py record)
      targets  bf16 (n, K, 2560)   K = n_tokens(px) (the full board) or --train-cells rows
      cell_idx int16 (n, K)        which TEACHER TOKEN each target row is (0..n_tokens(px)-1, ascending)
      cells    uint8 (n, 64, 64)   the board itself

  A token is one cell only at px=32 (n_tokens == N_CELLS == 4096, row-major k = r*64+c). At px=16 it is a
  2x2 CELL BLOCK, row-major over the 32x32 block grid -- so `cell_idx` is a token index, and the manifest's
  config.px_per_cell / config.tokens_per_board say which. See n_tokens() below and finding 177.
  manifest.json       boards (sha1 -> shard, index, game, level, split, kind), shards, holdout, recorder facts
                      An augmented root (make_targets.py augment) adds boards of kind "dihedral" with `aug` (the D4
                      element) and `parent_sha1`; its original shards are symlinks into the source root, and
                      manifest["augmentation"] says where they came from and what was added.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import pathlib
import random

import numpy as np

BOARD_H = BOARD_W = 64
N_CELLS = BOARD_H * BOARD_W          # 4096
N_COLOURS = 16
HIDDEN = 2560                        # Flash-Next out_hidden_size == text hidden_size (deepstack off)
PX = 32                              # DEFAULT px per cell -> one merged token per cell (grid [1,128,128])
PATCH, MERGE = 16, 2                 # tower geometry: 16-px patches, 2x2 patch merge
                                     # (make_targets.record asserts these against s0_record_table's)
HOLDOUT_SEED = 20261003
N_HOLDOUT = 5
DEFAULT_TARGET_ROOT = pathlib.Path(os.environ.get("BOARD_TOWER_TARGETS", "/media/ignaz/claude-extra/board_tower/targets"))
DEFAULT_CKPT_DIR = pathlib.Path(os.environ.get("BOARD_TOWER_CKPT_DIR", "/media/ignaz/claude-extra/board_tower/ckpt"))


def board_sha1(cells: np.ndarray) -> str:
    b = np.asarray(cells)
    if b.shape != (BOARD_H, BOARD_W):
        raise ValueError(f"board must be {BOARD_H}x{BOARD_W}, got {b.shape}")
    return hashlib.sha1(b.astype(np.uint8).tobytes()).hexdigest()


def choose_holdout(public_games: list[str], seed: int = HOLDOUT_SEED, n: int = N_HOLDOUT) -> list[str]:
    """Deterministic: seeded shuffle of the SORTED public game ids, first n. Named in the manifest."""
    g = sorted(set(public_games))
    rng = random.Random(seed)
    rng.shuffle(g)
    return sorted(g[:n])


def token_side(px: int = PX) -> int:
    """Tokens per SIDE the real tower emits for a 64x64 board rendered at `px` px/cell: the board is
    BOARD_H*px pixels per side, PATCH-px patches, MERGE x MERGE merge -> BOARD_H*px/(PATCH*MERGE) == 2*px."""
    side_px = BOARD_H * px
    if side_px % (PATCH * MERGE):
        raise ValueError(f"{px} px/cell -> {side_px} px per side, not a multiple of PATCH*MERGE={PATCH * MERGE}")
    return side_px // (PATCH * MERGE)


def n_tokens(px: int = PX) -> int:
    """Teacher tokens per board = token_side(px)**2 == (2*px)**2. This is the STUDENT'S OUTPUT length and the
    number of rows in a full target matrix; it equals N_CELLS (the student's INPUT length) only at px=32.
    4096 / 1024 / 400 / 256 / 64 at px 32 / 16 / 10 / 8 / 4 -- finding 177's measured table, which was read
    off `prompt_token_ids`, i.e. this arithmetic reproduces the measurement."""
    return token_side(px) ** 2


def cells_per_token_side(px: int = PX) -> int:
    """Board cells per side covered by ONE token: 1 at px=32 (a token per cell), 2 at px=16 (a token per
    2x2 cell block), 4 at px=8. Raises when the token grid does not divide the 64x64 cell grid -- px=10
    gives 20 tokens/side and 64/20 is not an integer (the "misaligned" N=10 of finding 177)."""
    ts = token_side(px)
    if ts > BOARD_H or BOARD_H % ts:
        raise ValueError(f"{px} px/cell -> {ts} tokens per side, which does not divide the {BOARD_H}-cell grid")
    return BOARD_H // ts


# ----------------------------------------------------------------------------- dihedral group (augmentation)
# The 8 elements of D4 on a square board, the SAME definitions and names as notebooks_duck/perceptual_variants/
# transforms.py (its obs_fn; rot90 = clockwise, the top-left corner goes to the top-right). A transformed BOARD is a
# new board the teacher must see for itself: the tower's output is not equivariant under these, so the targets of a
# transformed board come from a fresh teacher forward, never from permuting the original's rows.
DIHEDRAL = {
    "identity": lambda a: a,
    "rot90": lambda a: a[::-1, :].T,
    "rot180": lambda a: a[::-1, ::-1],
    "rot270": lambda a: a[:, ::-1].T,
    "flip_h": lambda a: a[:, ::-1],
    "flip_v": lambda a: a[::-1, :],
    "transpose": lambda a: a.T,
    "antitranspose": lambda a: a[::-1, ::-1].T,
}
DIHEDRAL_NON_IDENTITY = tuple(k for k in DIHEDRAL if k != "identity")


def dihedral(cells: np.ndarray, name: str) -> np.ndarray:
    """A C-contiguous uint8 copy of `cells` under D4 element `name` (so sha1 / tobytes see the transformed layout)."""
    b = np.asarray(cells)
    if b.shape != (BOARD_H, BOARD_W):
        raise ValueError(f"board must be {BOARD_H}x{BOARD_W}, got {b.shape}")
    return np.ascontiguousarray(DIHEDRAL[name](b)).astype(np.uint8)


def stratified_cap(items: list[dict], cap: int | None, seed: int) -> list[dict]:
    """Round-robin over levels (seeded order within a level) until `cap` boards: a per-game cap that keeps
    every level represented instead of the first N frames of level 1."""
    if cap is None or len(items) <= cap:
        return list(items)
    rng = random.Random(seed)
    by_level: dict = {}
    for it in items:
        by_level.setdefault(it.get("level"), []).append(it)
    queues = []
    for lvl in sorted(by_level, key=lambda x: (x is None, x)):
        q = list(by_level[lvl]); rng.shuffle(q); queues.append(q)
    out = []
    while len(out) < cap and any(queues):
        for q in queues:
            if q and len(out) < cap:
                out.append(q.pop())
    return out


def now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


# ----------------------------------------------------------------------------- shards
def shard_name(split: str, i: int) -> str:
    return f"{split}_{i:04d}.safetensors"


def write_shard(path: pathlib.Path, targets, cell_idx, cells) -> dict:
    """targets bf16 (n,K,2560), cell_idx int16 (n,K), cells uint8 (n,64,64). Returns the shard record."""
    import torch
    from safetensors.torch import save_file
    assert targets.dtype == torch.bfloat16 and targets.ndim == 3 and targets.shape[2] == HIDDEN, targets.shape
    assert cell_idx.shape == targets.shape[:2] and cell_idx.dtype == torch.int16
    assert cells.shape == (targets.shape[0], BOARD_H, BOARD_W) and cells.dtype == torch.uint8
    tmp = path.with_suffix(".tmp")
    save_file({"targets": targets.contiguous(), "cell_idx": cell_idx.contiguous(), "cells": cells.contiguous()}, str(tmp))
    os.replace(tmp, path)
    return {"file": path.name, "n": int(targets.shape[0]), "cells_per_board": int(targets.shape[1]),
            "bytes": os.path.getsize(path)}


class ShardReader:
    """Lazy, mmap-backed reads of one board from a shard (safetensors get_slice: no full-shard load)."""

    def __init__(self, root: pathlib.Path):
        self.root = pathlib.Path(root)
        self._open: dict = {}

    def _f(self, name: str):
        if name not in self._open:
            from safetensors import safe_open
            self._open[name] = safe_open(str(self.root / name), "pt", device="cpu")
        return self._open[name]

    def board(self, name: str, i: int):
        f = self._f(name)
        return (f.get_slice("targets")[i], f.get_slice("cell_idx")[i], f.get_slice("cells")[i])

    def close(self):
        self._open.clear()


# ----------------------------------------------------------------------------- manifest
def load_manifest(root: pathlib.Path) -> dict | None:
    p = pathlib.Path(root) / "manifest.json"
    return json.load(open(p)) if p.is_file() else None


def save_manifest(root: pathlib.Path, m: dict) -> None:
    p = pathlib.Path(root) / "manifest.json"
    tmp = p.with_suffix(".tmp")
    json.dump(m, open(tmp, "w"), indent=1)
    os.replace(tmp, p)


def manifest_boards(m: dict, split: str | None = None) -> list[dict]:
    return [b for b in m["boards"] if split is None or b["split"] == split]
