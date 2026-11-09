"""Board-tower student output under two torch builds (findings-audit item 8, notes/tower_torch_compare_2026-10-31.md).

  run      <tower_dir> <boards.npz> <out_dir> <tag>   -- run the student exactly as the notebook kernel does (CPU,
                                                          set_num_threads(2), interop 1, export_embeds.load_student(),
                                                          st.tokens(board)) and save the bf16 outputs + a meta record
  compare  <out_dir> <tagA> <tagB>                     -- bitwise + per-token cosine comparison of two runs

Needs only numpy + torch (+ the tower dataset's own code). The bf16 output is stored as raw uint16 bits, so the comparison
sees exactly the bytes the notebook would have put on the wire.
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import platform
import sys
import time


def run(tower_dir: str, boards_npz: str, out_dir: str, tag: str, threads: int = 2) -> None:
    import numpy as np
    import torch
    torch.set_num_threads(threads)                 # the notebook's BOARD_TOWER_THREADS
    try:
        torch.set_num_interop_threads(1)
    except Exception:
        pass
    os.environ["BOARD_TOWER_DEVICE"] = "cpu"       # production: the GPU belongs to the server
    os.environ["BOARD_TOWER_ANY_GPU"] = "1"
    os.environ["BOARD_TOWER_CKPT"] = str(pathlib.Path(tower_dir) / "ckpt_px16_dih" / "best.pt")
    sys.path.insert(0, tower_dir)
    from scripts.board_tower import export_embeds as bt
    st = bt.load_student()
    cells = np.load(boards_npz)["cells"]
    n = cells.shape[0]
    out = pathlib.Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    arr = np.lib.format.open_memmap(out / f"emb_{tag}.npy", mode="w+", dtype=np.uint16, shape=(n, st.n_pos, 2560))
    shas, ms = [], []
    for i in range(n):
        t0 = time.perf_counter()
        e = st.tokens(cells[i].astype(np.int64))
        ms.append((time.perf_counter() - t0) * 1000.0)
        assert e.dtype == torch.bfloat16 and tuple(e.shape) == (st.n_pos, 2560), (e.dtype, e.shape)
        bits = e.view(torch.int16).numpy().view(np.uint16)
        arr[i] = bits
        shas.append(hashlib.sha256(bits.tobytes()).hexdigest())
    arr.flush()
    cpu = next((l.split(":", 1)[1].strip() for l in open("/proc/cpuinfo") if l.startswith("model name")), "?")
    meta = {
        "tag": tag, "python": platform.python_version(), "torch": torch.__version__, "torch_file": torch.__file__,
        "numpy": np.__version__, "device": str(st.device), "out_dtype": "bfloat16",
        "param_dtype": str(next(st.model.parameters()).dtype), "threads": torch.get_num_threads(),
        "interop_threads": torch.get_num_interop_threads(), "cpu_model": cpu,
        "cpu_capability": torch.backends.cpu.get_cpu_capability(), "mkldnn": torch.backends.mkldnn.is_available(),
        "ckpt": str(st.path), "ckpt_tag": st.tag, "n_pos": st.n_pos, "n_boards": n,
        "fwd_ms_median": float(np.median(ms)), "board_sha256": shas,
    }
    (out / f"meta_{tag}.json").write_text(json.dumps(meta, indent=1))
    print(json.dumps({k: v for k, v in meta.items() if k != "board_sha256"}), flush=True)


def _widen(bits):
    import numpy as np
    return (bits.astype(np.uint32) << 16).view(np.float32)


def compare(out_dir: str, a: str, b: str) -> dict:
    import numpy as np
    out = pathlib.Path(out_dir)
    ma, mb = (json.loads((out / f"meta_{t}.json").read_text()) for t in (a, b))
    A = np.load(out / f"emb_{a}.npy", mmap_mode="r")
    B = np.load(out / f"emb_{b}.npy", mmap_mode="r")
    assert A.shape == B.shape, (A.shape, B.shape)
    n = A.shape[0]
    bitwise = [x == y for x, y in zip(ma["board_sha256"], mb["board_sha256"])]
    bmin, bmean, bmaxabs, bfrac = [], [], [], []
    all_cos = []
    for i in range(n):
        xa = _widen(np.asarray(A[i])).astype(np.float64)
        xb = _widen(np.asarray(B[i])).astype(np.float64)
        num = (xa * xb).sum(1)
        den = np.linalg.norm(xa, axis=1) * np.linalg.norm(xb, axis=1)
        cos = num / den
        all_cos.append(cos)
        bmin.append(float(cos.min()))
        bmean.append(float(cos.mean()))
        bmaxabs.append(float(np.abs(xa - xb).max()))
        bfrac.append(float((np.asarray(A[i]) != np.asarray(B[i])).mean()))
    all_cos = np.concatenate(all_cos)
    q = lambda v, p: float(np.quantile(np.asarray(v), p))
    res = {
        "a": {k: ma[k] for k in ("tag", "python", "torch", "device", "param_dtype", "out_dtype", "threads", "cpu_capability")},
        "b": {k: mb[k] for k in ("tag", "python", "torch", "device", "param_dtype", "out_dtype", "threads", "cpu_capability")},
        "boards": n, "boards_bitwise_identical": int(sum(bitwise)),
        "token_cos_min": float(all_cos.min()), "token_cos_mean": float(all_cos.mean()),
        "board_min_cos": {"min": min(bmin), "p01": q(bmin, .01), "p50": q(bmin, .5), "max": max(bmin)},
        "board_mean_cos": {"min": min(bmean), "p50": q(bmean, .5), "max": max(bmean)},
        "board_max_abs_diff": {"min": min(bmaxabs), "p50": q(bmaxabs, .5), "p99": q(bmaxabs, .99), "max": max(bmaxabs)},
        "board_frac_elems_differ": {"min": min(bfrac), "p50": q(bfrac, .5), "max": max(bfrac)},
        "refuted": bool(all_cos.min() < 0.999 or all_cos.mean() < 0.9999),
    }
    print(json.dumps(res, indent=1), flush=True)
    return res


if __name__ == "__main__":
    if sys.argv[1] == "run":
        run(*sys.argv[2:6], **({"threads": int(sys.argv[6])} if len(sys.argv) > 6 else {}))
    elif sys.argv[1] == "compare":
        compare(*sys.argv[2:5])
    else:
        raise SystemExit(__doc__)
