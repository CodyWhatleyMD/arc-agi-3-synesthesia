"""Optional multimodal context helpers for ARC analyzer prompts."""
from __future__ import annotations

import base64
import io
import json
import os
import pathlib
import time
from typing import Any

from PIL import Image

from inference.agent.runtime_state import Frame


ARC_COLOR_MAP: dict[int, tuple[int, int, int]] = {
    0: (255, 255, 255),
    1: (204, 204, 204),
    2: (153, 153, 153),
    3: (102, 102, 102),
    4: (51, 51, 51),
    5: (0, 0, 0),
    6: (229, 58, 163),
    7: (255, 123, 204),
    8: (249, 60, 49),
    9: (30, 147, 255),
    10: (136, 216, 241),
    11: (255, 220, 0),
    12: (255, 133, 27),
    13: (146, 18, 49),
    14: (79, 204, 48),
    15: (163, 86, 214),
}


def multimodal_context() -> str:
    return os.environ.get("MULTIMODAL_CONTEXT", "").strip().lower()


def current_grid_image_enabled() -> bool:
    return multimodal_context() == "current_grid"


def current_grid_image_upscale() -> int:
    raw = os.environ.get("MULTIMODAL_UPSCALE", "").strip()
    if not raw:
        return 16
    try:
        return max(1, int(raw))
    except ValueError:
        return 16


def frame_to_png_data_url(frame: Frame, *, upscale: int | None = None) -> str:
    rows = len(frame.grid)
    cols = max((len(row) for row in frame.grid), default=0)
    if rows <= 0 or cols <= 0:
        raise ValueError("Cannot render an empty grid as an image.")

    scale = current_grid_image_upscale() if upscale is None else max(1, int(upscale))
    image = Image.new("RGB", (cols, rows), ARC_COLOR_MAP[0])
    pixels = image.load()
    for row_idx, row in enumerate(frame.grid):
        for col_idx in range(cols):
            value = row[col_idx] if col_idx < len(row) else 0
            pixels[col_idx, row_idx] = ARC_COLOR_MAP.get(int(value), ARC_COLOR_MAP[0])
    if scale > 1:
        image = image.resize((cols * scale, rows * scale), Image.Resampling.NEAREST)

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


# ===================== ARM B: distilled student board tower ======================================
# The ONLY client-side change between arms. ARM_B_STUDENT_TOWER=1 replaces the PNG part with an
# image_embeds part produced by our 27M/18M student, which emits the native tower's output tokens
# directly. Default 0 == his exact pixel path, so this file is inert in the control arm.
_BT_LOCK = __import__("threading").Lock()
_BT = {"mod": None, "student": None, "log": None, "n_embeds": 0, "n_png": 0}


def _open_log():
    """Open the per-arm board-part side-log. Used by BOTH arms; imports nothing heavy."""
    if _BT["log"] is not None:
        return
    label = os.environ.get("ARM_LABEL", "arm")
    d = pathlib.Path(os.environ.get("TAAF_KAGGLE_WORKING_DIR", "/kaggle/working")) / label
    d.mkdir(parents=True, exist_ok=True)
    _BT["log"] = open(d / "board_parts.jsonl", "a", buffering=1)


def _log_png_part(url, frame):
    """Record the control path's ACTUAL rendered geometry, decoded from the PNG it just built.

    One merged vision token covers PATCH*MERGE = 16*2 = 32 px per side, so the implied token
    count is (w/32)*(h/32). Never trust the upscale setting for this number.
    """
    import base64 as _b64
    import struct as _struct
    w = h = None
    try:
        raw = _b64.b64decode(url.split(",", 1)[1][:120] + "===")
        if raw[:8] == b"\x89PNG\r\n\x1a\n":
            w, h = _struct.unpack(">II", raw[16:24])
    except Exception:
        pass
    tok = (w * h) // (32 * 32) if (w and h) else None
    rec = {"type": "image_url", "w": w, "h": h, "n_tokens": tok,
           "px_per_cell": (w // 64) if w else None,
           "payload_bytes": len(url),
           "level": getattr(frame, "level", None), "step": getattr(frame, "step", None),
           "t": time.time()}
    with _BT_LOCK:
        _open_log()
        _BT["n_png"] += 1
        _BT["log"].write(json.dumps(rec) + "\n")
        if _BT["n_png"] == 1:
            print(f"CONTROL path live -- MEASURED {w}x{h} px = {tok} merged tokens/board "
                  f"({(w // 64) if w else '?'} px/cell)", flush=True)


def _bt_init():
    """Import the student once. Caller holds _BT_LOCK."""
    if _BT["mod"] is not None:
        return
    import sys as _sys
    root = os.environ.get("BOARD_TOWER_REPO", "/bt")
    if root not in _sys.path:
        _sys.path.insert(0, root)
    import torch as _torch
    # Cap BEFORE the student runs: uncapped torch takes all cores and starves the vLLM server
    # that shares this container. See the patch docstring for the measured table.
    _nthreads = max(1, int(os.environ.get("BOARD_TOWER_THREADS", "2")))
    _torch.set_num_threads(_nthreads)
    try:
        _torch.set_num_interop_threads(1)
    except Exception:
        pass  # only settable before any parallel work; harmless if already fixed
    from scripts.board_tower import export_embeds as _bt_mod
    from notebooks_duck.synth_tokens import synth_embeds as _se
    _BT["mod"], _BT["se"] = _bt_mod, _se
    _BT["student"] = _bt_mod.load_student()
    st = _BT["student"]
    # Fail loudly on a geometry the arm was not configured for (the brief's n_pos trap).
    want = os.environ.get("ARM_B_EXPECT_NPOS")
    if want and int(want) != st.n_pos:
        raise RuntimeError(f"student n_pos {st.n_pos} != ARM_B_EXPECT_NPOS {want} "
                           f"(ckpt={st.path}); refusing to run a geometry-mismatched arm")
    _open_log()
    _BT["threads"] = _nthreads
    print(f"ARM B: student tower live -- ckpt={st.path} tag={st.tag} n_pos={st.n_pos} "
          f"side={st.side} device={st.device} grid_thw={st.grid_thw().tolist()} "
          f"torch_threads={_nthreads} (cap, so the student cannot starve the co-resident server)",
          flush=True)


def _student_tower_part(frame: Frame) -> dict[str, Any]:
    """The image_embeds part for this frame's board, plus a compact liveness record.

    The side-log is the authoritative embeds-on-wire count: his transcript renderer only knows
    'text' and 'image_url', so an image_embeds part is invisible to it.
    """
    with _BT_LOCK:
        _bt_init()
        bt, se, st = _BT["mod"], _BT["se"], _BT["student"]
    cells = se.board_cells(frame.grid)
    _t0 = time.perf_counter()
    embeds = st.tokens(frame.grid)
    _fwd_ms = (time.perf_counter() - _t0) * 1000.0
    part = bt.part_from_embeds(embeds, st.side, st.uuid(cells))   # asserts shape/dtype/finiteness
    rec = {"type": "image_embeds", "uuid": part["uuid"], "n_tokens": int(embeds.shape[0]),
           "hidden": int(embeds.shape[1]), "dtype": str(embeds.dtype),
           "grid_thw": st.grid_thw().tolist(), "payload_bytes": se.part_payload_bytes(part),
           "board_sha1": se.board_uuid(cells) if hasattr(se, "board_uuid") else None,
           "level": getattr(frame, "level", None), "step": getattr(frame, "step", None),
           "fwd_ms": round(_fwd_ms, 2), "threads": _BT.get("threads"),
           "t": time.time()}
    with _BT_LOCK:
        _BT["n_embeds"] += 1
        _BT["log"].write(json.dumps(rec) + "\n")
    return part


def current_grid_image_part(frame: Frame | None) -> dict[str, Any] | None:
    if frame is None or not current_grid_image_enabled():
        return None
    if os.environ.get("ARM_B_STUDENT_TOWER", "0") == "1":
        return _student_tower_part(frame)
    # his exact pixel path (control), now self-measuring -- see _log_png_part
    url = frame_to_png_data_url(frame)
    _log_png_part(url, frame)
    return {
        "type": "image_url",
        "image_url": {
            "url": url,
        },
    }
