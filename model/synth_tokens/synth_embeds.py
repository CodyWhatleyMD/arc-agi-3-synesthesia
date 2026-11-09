"""S2b -- synthetic image tokens for a 64x64 board, as precomputed image embeddings for vLLM.

The tower collapses to a lookup for a board (plan S2b, the investigator 2026-10-03): cell colour -> one 2560-d row,
recorded once from Flash-Next's own tower (notebooks_duck/synth_tokens/s0_record_table.py). This module
turns a board into the EXACT request part the Flash-Next runtime accepts with `--enable-mm-embeds`
(audit: /scratchpad/mm_embeds/DETAILS.md section 1, read-only code audit of the served runtime):

    {"type": "image_embeds", "uuid": "board-<sha1 of the 4096 cell ids>",
     "image_embeds": {"image_embeds":   base64(torch.save(bf16 tensor (4096, 2560))),
                      "image_grid_thw": base64(torch.save(int64 tensor [1, 128, 128]))}}

  * image_embeds: (4096, 2560) bfloat16, ROW-MAJOR over the merged 64x64 grid -- row k is cell (k // 64, k % 64),
    the order the real merger emits and the order `_get_mrope_input_positions` assigns (t, h, w) = (o, o+r, o+c).
  * image_grid_thw: rank-1 (3,) = [1, 128, 128] in PATCHES (patch 16, merge 2): placeholder count = 1*128*128/4 = 4096.
    NOT (1, 3): the server stacks per-item tensors itself.
  * width 2560 is right ONLY because this model has deepstack_visual_indexes = [] (else out_hidden x (1+levels)).

The frontend does not validate width or row count for this model family; a wrong shape dies inside
execute_model and kills the engine (EngineDeadError). So `assert_request_shapes` runs before every send and
callers must not bypass it.

Token accounting (served config): the placeholder text `<|vision_start|><|image_pad|><|vision_end|>` becomes
248053, 4096 x 248056, 248054 -- 4098 prompt tokens per board; `token_budget()` gives the number to subtract
from max_model_len. M-RoPE advances the position counter by only 64 for the whole board (see the audit, §2).
"""
from __future__ import annotations

import base64
import hashlib
import io
import pathlib

import numpy as np
import torch

BOARD_H = BOARD_W = 64
PATCH, MERGE = 16, 2
GRID_THW = (1, BOARD_H * MERGE, BOARD_W * MERGE)      # (1, 128, 128) patches
N_TOKENS = BOARD_H * BOARD_W                           # 4096 merged tokens
HIDDEN = 2560                                          # out_hidden_size == text hidden_size, deepstack off
N_COLOURS = 16
IMAGE_TOKEN_ID, VISION_START_ID, VISION_END_ID = 248056, 248053, 248054
PLACEHOLDER_TEXT = "<|vision_start|><|image_pad|><|vision_end|>"
DEFAULT_TABLE = pathlib.Path(__file__).with_name("table_flashnext_v1.pt")


# ----------------------------------------------------------------------------- table
def load_table(path: str | pathlib.Path = DEFAULT_TABLE, key: str = "table") -> torch.Tensor:
    """(16, 2560) bfloat16 lookup table. `key` selects which S0 recording: 'table' (flat 32x32 square, one
    token), 'table_board_centre', 'table_board_interior_mean'."""
    d = torch.load(path, map_location="cpu", weights_only=False)
    T = d[key]
    if tuple(T.shape) != (N_COLOURS, HIDDEN):
        raise ValueError(f"table {key} has shape {tuple(T.shape)}, expected {(N_COLOURS, HIDDEN)}")
    return T.to(torch.bfloat16).contiguous()


# ----------------------------------------------------------------------------- board
def board_cells(board) -> np.ndarray:
    """Validate a 64x64 board of ints 0..15 -> uint8 array (64, 64)."""
    b = np.asarray(board)
    if b.shape != (BOARD_H, BOARD_W):
        raise ValueError(f"board must be {BOARD_H}x{BOARD_W}, got {b.shape}")
    if not np.issubdtype(b.dtype, np.integer):
        raise ValueError(f"board must be integer-valued, got dtype {b.dtype}")
    if b.min() < 0 or b.max() >= N_COLOURS:
        raise ValueError(f"board values must be in 0..{N_COLOURS - 1}, got [{b.min()}, {b.max()}]")
    return b.astype(np.uint8)


def board_uuid(cells: np.ndarray) -> str:
    """Deterministic per board content: lets the server skip hashing 21 MB per request (mm cache keyed on it)."""
    return "board-" + hashlib.sha1(board_cells(cells).tobytes()).hexdigest()


# ----------------------------------------------------------------------------- embeds
def gather_embeds(cells: np.ndarray, table: torch.Tensor) -> torch.Tensor:
    """(4096, 2560) bf16, row-major over cells. `table` is (16, 2560) [colour lookup] or (4096, 16, 2560)
    [colour x position lookup, row k = cell k]."""
    idx = torch.from_numpy(board_cells(cells).reshape(-1)).long()
    if table.ndim == 2:
        out = table[idx]
    elif table.ndim == 3 and table.shape[0] == N_TOKENS:
        out = table[torch.arange(N_TOKENS), idx]
    else:
        raise ValueError(f"unsupported table shape {tuple(table.shape)}")
    return out.to(torch.bfloat16).contiguous()


def grid_thw_tensor() -> torch.Tensor:
    return torch.tensor(GRID_THW, dtype=torch.int64)       # shape (3,), NOT (1, 3)


def assert_request_shapes(embeds: torch.Tensor, grid: torch.Tensor) -> None:
    """Client-side guard. A wrong shape here reaches execute_model on the server and kills the engine."""
    if not isinstance(embeds, torch.Tensor) or not isinstance(grid, torch.Tensor):
        raise TypeError("embeds and grid must be torch tensors")
    if embeds.dtype != torch.bfloat16:
        raise ValueError(f"image_embeds must be bfloat16 (cast to visual dtype server-side; np.load path cannot carry bf16), got {embeds.dtype}")
    if tuple(embeds.shape) != (N_TOKENS, HIDDEN):
        raise ValueError(f"image_embeds must be {(N_TOKENS, HIDDEN)}, got {tuple(embeds.shape)}")
    if not embeds.is_contiguous():
        raise ValueError("image_embeds must be contiguous")
    if not torch.isfinite(embeds.float()).all():
        raise ValueError("image_embeds has non-finite values")
    if grid.dtype not in (torch.int64, torch.int32):
        raise ValueError(f"image_grid_thw must be an integer tensor, got {grid.dtype}")
    if tuple(grid.shape) != (3,):
        raise ValueError(f"image_grid_thw must be rank-1 (3,), got {tuple(grid.shape)} -- (1,3) breaks the server's per-item stacking")
    t, h, w = (int(x) for x in grid.tolist())
    if t != 1:
        raise ValueError(f"image_grid_thw t must be 1, got {t}")
    if h % MERGE or w % MERGE:
        raise ValueError(f"grid h, w must be multiples of merge={MERGE}, got {h}, {w}")
    if (t * h * w) // (MERGE * MERGE) != embeds.shape[0]:
        raise ValueError(f"placeholder count t*h*w/merge^2 = {(t*h*w)//(MERGE*MERGE)} != rows {embeds.shape[0]}")
    if (h, w) != (GRID_THW[1], GRID_THW[2]):
        raise ValueError(f"grid must be {GRID_THW} for a 64x64 board, got {(t, h, w)}")


def b64_tensor(t: torch.Tensor) -> str:
    buf = io.BytesIO()
    torch.save(t, buf)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def decode_b64_tensor(s: str) -> torch.Tensor:
    """What the server does: pybase64.b64decode(validate=True) then torch.load(weights_only=True)."""
    return torch.load(io.BytesIO(base64.b64decode(s, validate=True)), weights_only=True, map_location="cpu")


# ----------------------------------------------------------------------------- the request part
def build_image_embeds(board, table: torch.Tensor | None = None, uuid: str | None = None) -> dict:
    """The chat content part for one 64x64 board. Returns
       {"type": "image_embeds", "uuid": ..., "image_embeds": {"image_embeds": b64, "image_grid_thw": b64}}."""
    cells = board_cells(board)
    T = table if table is not None else load_table()
    embeds = gather_embeds(cells, T)
    grid = grid_thw_tensor()
    assert_request_shapes(embeds, grid)
    return {"type": "image_embeds", "uuid": uuid or board_uuid(cells),
            "image_embeds": {"image_embeds": b64_tensor(embeds), "image_grid_thw": b64_tensor(grid)}}


def part_payload_bytes(part: dict) -> int:
    return sum(len(v) for v in part["image_embeds"].values())


# ----------------------------------------------------------------------------- token accounting
def placeholder_token_ids() -> list[int]:
    """What the prompt update puts in place of the placeholder text, for one board."""
    return [VISION_START_ID] + [IMAGE_TOKEN_ID] * N_TOKENS + [VISION_END_ID]


def token_budget(n_boards: int = 1) -> int:
    """Prompt tokens consumed by n boards (vision_start + 4096 pads + vision_end each)."""
    return n_boards * (N_TOKENS + 2)


def mrope_position_advance(n_boards: int = 1) -> int:
    """How far the position counter moves per board: max(h, w) of the LLM grid = 64 (audit §2), not 4096."""
    return n_boards * BOARD_H


def chat_content(board, text_before: str, text_after: str, table: torch.Tensor | None = None) -> list[dict]:
    """[text, image_embeds, text] -- the server emits the placeholder at the part's position."""
    parts = []
    if text_before:
        parts.append({"type": "text", "text": text_before})
    parts.append(build_image_embeds(board, table))
    if text_after:
        parts.append({"type": "text", "text": text_after})
    return parts


def build_request(board, question: str, *, model: str = "flashnext", text_before: str = "Board follows.\n",
                  max_tokens: int = 64, temperature: float = 0.0, seed: int | None = None,
                  table: torch.Tensor | None = None, extra: dict | None = None) -> dict:
    """Full /v1/chat/completions body for one board + one question (one user turn)."""
    body = {"model": model,
            "messages": [{"role": "user", "content": chat_content(board, text_before, "\n" + question, table)}],
            "max_tokens": max_tokens, "temperature": temperature}
    if seed is not None:
        body["seed"] = seed
    if extra:
        body.update(extra)
    return body
