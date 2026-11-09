#!/usr/bin/env python3
"""Board -> image_embeds payload from the STUDENT board tower (plan S2c), byte-compatible with
notebooks_duck/synth_tokens/synth_embeds.py: the same {"type": "image_embeds", "uuid", "image_embeds": {...}} part,
the same bf16 row-major (n_pos, 2560) matrix, the same client-side shape assert (a wrong shape kills the engine).
Only the SOURCE of the matrix differs: student(board) instead of TABLE[cells].

GEOMETRY FOLLOWS THE CHECKPOINT (finding 177): n_pos = (64/cell_patch)**2 -- 4096 tokens / grid [1,128,128] at
cell_patch=1 (32 px/cell), 1024 tokens / grid [1,64,64] at cell_patch=2 (16 px/cell). grid = [1, 2*side, 2*side]
patches (patch 16, merge 2) with side = 64/cell_patch tokens per side. synth_embeds.assert_request_shapes is
hardwired to 4096, so this module asserts its own (assert_request_shapes_n, same checks, geometry-parametrised).

uuid: "tower-g<n_pos>-<ckpt tag>-<board sha1>". The server's multimodal cache is keyed on the uuid, so it must differ
from the synth arm's "board-<sha1>" (same board, different vectors), change with the checkpoint, and change with the
geometry (a 4096-token and a 1024-token student must never share a cache key).

CLI (from any cwd):  export_embeds.py [--ckpt best.pt] [--board fixture.json | --solid 8 | --random] [--out part.json]
Env: BOARD_TOWER_CKPT (default <ckpt dir>/best.pt), BOARD_TOWER_DEVICE (default: the visible CUDA device if any, else cpu).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import sys

os.environ.setdefault("CUDA_DEVICE_ORDER", "PCI_BUS_ID")
import numpy as np                        # noqa: E402
import torch                              # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from notebooks_duck.synth_tokens import synth_embeds as se                       # noqa: E402
from scripts.board_tower import common as C                                      # noqa: E402
from scripts.board_tower.model import BoardTower, load_checkpoint                # noqa: E402

DEFAULT_CKPT = pathlib.Path(os.environ.get("BOARD_TOWER_CKPT", str(C.DEFAULT_CKPT_DIR / "best.pt")))
LEGEND_CELLS = 8                                   # the perception script's legend: an 8x8-cell block = 64 tokens


class Student:
    """A loaded checkpoint + its tag. One instance per process (see load_student)."""

    def __init__(self, ckpt: str | pathlib.Path = DEFAULT_CKPT, device: str | None = None):
        self.path = pathlib.Path(ckpt)
        if not self.path.is_file():
            raise FileNotFoundError(f"student checkpoint not found: {self.path} (set BOARD_TOWER_CKPT)")
        dev = device or os.environ.get("BOARD_TOWER_DEVICE") or ("cuda:0" if torch.cuda.is_available() else "cpu")
        if dev.startswith("cuda") and "5090" not in torch.cuda.get_device_name(0) and not os.environ.get("BOARD_TOWER_ANY_GPU"):
            raise SystemExit(f"REFUSING: visible CUDA device is '{torch.cuda.get_device_name(0)}', not the 5090 "
                             f"(source scripts/board_tower/env.sh, or BOARD_TOWER_DEVICE=cpu, or BOARD_TOWER_ANY_GPU=1)")
        self.device = torch.device(dev)
        self.model, self.extra = load_checkpoint(self.path, self.device)
        h = hashlib.sha256()
        with open(self.path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        self.tag = h.hexdigest()[:10]
        self.step = int(self.extra.get("step", -1))

    @property
    def side(self) -> int:
        """Tokens per side: 64 at cell_patch=1, 32 at cell_patch=2."""
        return self.model.cfg.pos_grid

    @property
    def n_pos(self) -> int:
        return self.model.cfg.n_pos

    def grid_thw(self) -> torch.Tensor:
        return torch.tensor([1, self.side * se.MERGE, self.side * se.MERGE], dtype=torch.int64)

    def tokens(self, board) -> torch.Tensor:
        """(n_pos, 2560) bfloat16, row-major over the token grid (k = r*side + c; at cell_patch=2 a token is a 2x2 cell block)."""
        cells = se.board_cells(board)
        return self.model.tokens_for_board(torch.from_numpy(cells.astype(np.int64)), self.device)

    def uuid(self, cells: np.ndarray) -> str:
        return f"tower-g{self.n_pos}-{self.tag}-{C.board_sha1(cells)}"


_STUDENT: Student | None = None


def load_student(ckpt=None, device=None) -> Student:
    global _STUDENT
    if _STUDENT is None or (ckpt is not None and pathlib.Path(ckpt) != _STUDENT.path):
        _STUDENT = Student(ckpt or DEFAULT_CKPT, device)
    return _STUDENT


def assert_request_shapes_n(embeds: torch.Tensor, grid: torch.Tensor, side: int) -> None:
    """se.assert_request_shapes, parametrised on tokens-per-side (`side`): the client-side guard. A wrong shape
    reaches execute_model on the server and kills the engine, so build_* call this before every send."""
    if not isinstance(embeds, torch.Tensor) or not isinstance(grid, torch.Tensor):
        raise TypeError("embeds and grid must be torch tensors")
    if embeds.dtype != torch.bfloat16:
        raise ValueError(f"image_embeds must be bfloat16, got {embeds.dtype}")
    if tuple(embeds.shape) != (side * side, se.HIDDEN):
        raise ValueError(f"image_embeds must be {(side * side, se.HIDDEN)}, got {tuple(embeds.shape)}")
    if not embeds.is_contiguous():
        raise ValueError("image_embeds must be contiguous")
    if not torch.isfinite(embeds.float()).all():
        raise ValueError("image_embeds has non-finite values")
    if grid.dtype not in (torch.int64, torch.int32) or tuple(grid.shape) != (3,):
        raise ValueError(f"image_grid_thw must be an integer tensor of shape (3,), got {grid.dtype} {tuple(grid.shape)}")
    t, h, w = (int(x) for x in grid.tolist())
    if (t, h, w) != (1, side * se.MERGE, side * se.MERGE):
        raise ValueError(f"grid must be {(1, side * se.MERGE, side * se.MERGE)} for {side * side} tokens, got {(t, h, w)}")
    if (t * h * w) // (se.MERGE * se.MERGE) != embeds.shape[0]:
        raise ValueError("placeholder count t*h*w/merge^2 != rows")


def part_from_embeds(embeds: torch.Tensor, side: int, uuid: str) -> dict:
    """The image_embeds chat content part for an arbitrary (side*side, 2560) bf16 matrix, shape-asserted."""
    grid = torch.tensor([1, side * se.MERGE, side * se.MERGE], dtype=torch.int64)
    assert_request_shapes_n(embeds, grid, side)
    return {"type": "image_embeds", "uuid": uuid,
            "image_embeds": {"image_embeds": se.b64_tensor(embeds), "image_grid_thw": se.b64_tensor(grid)}}


def build_image_embeds(board, student: Student | None = None, uuid: str | None = None) -> dict:
    """The chat content part for one 64x64 board, from the student. Same shape/dtype/grid/assert as
    synth_embeds.build_image_embeds (at the checkpoint's geometry); only the vectors (and the uuid prefix) differ."""
    st = student or load_student()
    cells = se.board_cells(board)
    embeds = st.tokens(cells)
    grid = st.grid_thw()
    assert_request_shapes_n(embeds, grid, st.side)
    return {"type": "image_embeds", "uuid": uuid or st.uuid(cells),
            "image_embeds": {"image_embeds": se.b64_tensor(embeds), "image_grid_thw": se.b64_tensor(grid)}}


def legend_part(colour: int, student: Student | None = None, size: int = LEGEND_CELLS) -> dict:
    """An `size`x`size`-CELL block of one colour -- the perception script's legend (64 tokens at cell_patch=1). The
    student only models 64x64 boards, so this is the top-left block of its output for a SOLID 64x64 board of that
    colour: an approximation of what the tower emits for a small image, said so in the perception output.
    At cell_patch=2 the block is size/2 x size/2 tokens (16 tokens for the default 8x8 cells)."""
    st = student or load_student()
    p = st.model.cfg.cell_patch
    if size % p:
        raise ValueError(f"legend size {size} cells is not a multiple of cell_patch {p}")
    ts = size // p
    cells = np.full((C.BOARD_H, C.BOARD_W), int(colour), dtype=np.uint8)
    tok = st.tokens(cells).view(st.side, st.side, C.HIDDEN)[:ts, :ts].reshape(ts * ts, C.HIDDEN).contiguous()
    return part_from_embeds(tok, ts, f"tower-legend-g{st.n_pos}-{st.tag}-{colour}-{size}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ckpt", default=str(DEFAULT_CKPT))
    ap.add_argument("--device", default=None)
    ap.add_argument("--board", default=None, help="json with a 'board' key (64x64 ints)")
    ap.add_argument("--solid", type=int, default=None, help="a solid board of this colour")
    ap.add_argument("--random", action="store_true")
    ap.add_argument("--out", default=None, help="write the content part as json")
    args = ap.parse_args()
    if args.board:
        board = np.asarray(json.load(open(args.board))["board"], dtype=np.int64)
    elif args.solid is not None:
        board = np.full((64, 64), args.solid, dtype=np.int64)
    else:
        board = np.random.default_rng(0).integers(0, 16, (64, 64))
    st = load_student(args.ckpt, args.device)
    part = build_image_embeds(board, st)
    emb = se.decode_b64_tensor(part["image_embeds"]["image_embeds"]); grid = se.decode_b64_tensor(part["image_embeds"]["image_grid_thw"])
    print(f"student {st.path} (step {st.step}, tag {st.tag}) on {st.device}: image_embeds {tuple(emb.shape)} {emb.dtype} "
          f"grid {grid.tolist()} uuid {part['uuid']} payload {se.part_payload_bytes(part):,} B; "
          f"token norms mean {emb.float().norm(dim=1).mean():.3f} min {emb.float().norm(dim=1).min():.3f} max {emb.float().norm(dim=1).max():.3f}")
    if args.out:
        json.dump(part, open(args.out, "w")); print("wrote", args.out)


if __name__ == "__main__":
    main()
