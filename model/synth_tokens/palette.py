"""The engine's 16-colour palette, READ from the engine source -- never restated.

Findings 71-72 / "whose colours?" (the investigator, 2026-09-22): the first bases were built from
CSS/Flat-UI guesses at Duck's English colour names, two of them badly wrong (index 9
off by 87, index 14 off by 73 in 255-space). The ground truth lives in two places in
the repo that agree:

    runs/route_a/franzen_verbatim/src/tufa-arc-agi-framework/src/taaf/game.py   ARC_COLORS    (floats)
    runs/route_a/franzen_verbatim/src/ARC3-Inference/inference/agent/vision_context.py  ARC_COLOR_MAP (ints)

This module parses BOTH dict literals with `ast` (no import of the engine, no matplotlib
dependency), cross-checks them, and refuses to run if they disagree or are missing.
`render_board` reproduces the harness's render (vision_context.py: one pixel per cell,
NEAREST upscale) at an arbitrary px-per-cell -- exact flat blocks, no anti-aliasing.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import pathlib

import numpy as np

_TAAF = "runs/route_a/franzen_verbatim/src/tufa-arc-agi-framework/src/taaf/game.py"
_VCTX = "runs/route_a/franzen_verbatim/src/ARC3-Inference/inference/agent/vision_context.py"
_FALLBACK_ROOT = "/home/ignaz/github/arc-prize-2026"


def engine_root() -> pathlib.Path:
    """Directory that contains `runs/route_a/...`. `ARC_ENGINE_ROOT` wins; else walk up
    from this file; else the main checkout. `runs/` is git-ignored, so a fresh worktree
    does not carry it -- hence the env override."""
    env = os.environ.get("ARC_ENGINE_ROOT")
    cands = [pathlib.Path(env)] if env else []
    here = pathlib.Path(__file__).resolve()
    cands += list(here.parents) + [pathlib.Path(_FALLBACK_ROOT)]
    for c in cands:
        if (c / _TAAF).is_file() and (c / _VCTX).is_file():
            return c
    raise FileNotFoundError(
        "engine palette source not found; set ARC_ENGINE_ROOT to a checkout that has "
        f"{_TAAF} and {_VCTX}")


def _dict_literal(path: pathlib.Path, name: str) -> dict:
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        target = None
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target = node.target.id
        elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            target = node.targets[0].id
        if target == name and node.value is not None:
            return ast.literal_eval(node.value)
    raise KeyError(f"{name} not found as a dict literal in {path}")


def engine_rgb(root: pathlib.Path | None = None) -> dict[int, tuple[int, int, int]]:
    """{0..15: (r,g,b)} from the engine, cross-checked between its two sources."""
    root = root or engine_root()
    floats = _dict_literal(root / _TAAF, "ARC_COLORS")
    ints = _dict_literal(root / _VCTX, "ARC_COLOR_MAP")
    if set(floats) != set(range(16)) or set(ints) != set(range(16)):
        raise ValueError("engine palette does not have exactly indices 0..15")
    out: dict[int, tuple[int, int, int]] = {}
    for i in range(16):
        a = tuple(int(round(c * 255)) for c in floats[i])
        b = tuple(int(c) for c in ints[i])
        if a != b:
            raise ValueError(f"engine palette sources disagree at {i}: taaf {a} vs vision_context {b}")
        out[i] = b
    return out


def palette_sha(rgb: dict[int, tuple[int, int, int]]) -> str:
    return hashlib.sha256(json.dumps([list(rgb[i]) for i in range(16)]).encode()).hexdigest()


def palette_lut(rgb: dict[int, tuple[int, int, int]]) -> np.ndarray:
    return np.array([rgb[i] for i in range(16)], dtype=np.uint8)  # (16,3)


def render_board_array(board, rgb: dict[int, tuple[int, int, int]], px: int = 32) -> np.ndarray:
    """(H*px, W*px, 3) uint8. Same pixels as vision_context.grid_to_image + NEAREST resize
    (each cell is one flat block). Values outside 0..15 fall back to colour 0, as there."""
    b = np.asarray(board, dtype=np.int64)
    if b.ndim != 2:
        raise ValueError(f"board must be 2-D, got shape {b.shape}")
    b = np.where((b >= 0) & (b < 16), b, 0)
    img = palette_lut(rgb)[b]  # (H,W,3)
    if px > 1:
        img = np.repeat(np.repeat(img, px, axis=0), px, axis=1)
    return np.ascontiguousarray(img)


def render_board(board, rgb: dict[int, tuple[int, int, int]], px: int = 32):
    from PIL import Image
    return Image.fromarray(render_board_array(board, rgb, px), mode="RGB")


if __name__ == "__main__":
    r = engine_rgb()
    print("engine root:", engine_root())
    for i in range(16):
        print(f"{i:2d} {r[i]}")
    print("palette sha256:", palette_sha(r))
