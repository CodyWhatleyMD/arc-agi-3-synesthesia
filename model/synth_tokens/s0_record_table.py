"""S0 -- record Flash-Next's OWN vision tower on the 16 engine colours (plan S0/S2b, 2026-10-03).

What this produces
  table_flashnext_v1.pt            16 x 2560 rows: the merged token the tower emits for a FLAT 32x32-px
                                   square of each engine colour (one merged token: grid (1,2,2)).
                                   Also the centre token / interior mean of an all-one-colour 64x64 board
                                   rendered at 32 px/cell (2048x2048 px, grid (1,128,128), 4096 tokens).
  table_flashnext_v1.provenance.json   checkpoint, tensor-bytes sha, palette source + sha, render recipe,
                                   runtime versions, attention backend, boards used, date.
  s0_results.json                  every number below, machine-readable.

What it measures (the S2b precondition, before any model test)
  (a) context-dependence of a token: cosine(flat-square token, centre token of a solid board) per colour,
      plus centre vs corner inside the same solid board (position dependence).
  (b) how context-free REAL board tokens are: three recorded boards (runs/**/artifacts/*_events.jsonl)
      through the FULL tower at 32 px/cell; per cell, cosine to the table row of that cell's colour and
      nearest-table-row accuracy (argmax over the 16 rows), overall / per colour / interior vs boundary.

How the tower is built: exactly as RT/models/qwen3_8_flash_next/nvidia/model.py:871 does --
  Qwen3_VisionTransformer(config.vision_config, norm_eps=config.text_config.rms_norm_eps, quant_config, prefix)
with quant_config=None: every model.visual.* module is in the checkpoint's quantization ignore list, so the
engine also builds them as plain BF16 linears. Weights come from the checkpoint's own shard (safetensors).
Pixels are patchified by a re-implementation of transformers' Qwen2VLImageProcessor.patchify that is
CHECKED against the real processor on the 2048x2048 board (the processor cannot be used for the 32x32
square: its min_pixels=65536 would upscale it to 64 tokens).

Run inside the serving image on one GPU: notebooks_duck/synth_tokens/run_s0_docker.sh
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import socket
import sys
import time

import numpy as np
import torch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from notebooks_duck.synth_tokens.palette import (  # noqa: E402
    engine_rgb, engine_root, palette_sha, render_board_array, _TAAF, _VCTX)

PATCH, MERGE, TEMPORAL, MEAN, STD = 16, 2, 2, 0.5, 0.5
PX = 32                      # px per cell: one merged token per cell
VIS_PREFIX = "model.visual."


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


# ----------------------------------------------------------------------------- pixels -> patches
def hf_patchify(img_u8: np.ndarray) -> tuple[torch.Tensor, list[int]]:
    """transformers 5.15.1 Qwen2VLImageProcessor: rescale 1/255, normalise (mean 0.5, std 0.5), then
    patchify: patch order (h/merge, w/merge, merge, merge), per-patch vector (C, T, P, P) with the single
    frame duplicated T=2 times. Returns ((gh*gw, C*T*P*P) float32, [1, gh, gw])."""
    H, W, C = img_u8.shape
    f = PATCH * MERGE
    if H % f or W % f:
        raise ValueError(f"image {H}x{W} is not a multiple of patch*merge={f}")
    x = torch.from_numpy(np.ascontiguousarray(img_u8)).permute(2, 0, 1).float() / 255.0
    x = (x - MEAN) / STD
    gh, gw = H // PATCH, W // PATCH
    x = x.reshape(C, gh // MERGE, MERGE, PATCH, gw // MERGE, MERGE, PATCH)
    x = x.permute(1, 4, 2, 5, 0, 3, 6)                       # (hd, wd, m, m, C, p, p)
    x = x.unsqueeze(5).expand(-1, -1, -1, -1, -1, TEMPORAL, -1, -1)
    x = x.reshape(gh * gw, C * TEMPORAL * PATCH * PATCH)
    return x.contiguous(), [1, gh, gw]


def check_patchify_against_hf(ckpt: str, img_u8: np.ndarray) -> dict:
    """The real processor on an image it will not resize (2048 px: multiple of 32, inside [65536, 16.7M] px)."""
    from PIL import Image
    from transformers import AutoImageProcessor
    proc = AutoImageProcessor.from_pretrained(ckpt)
    out = proc(images=[Image.fromarray(img_u8, mode="RGB")], return_tensors="pt")
    pv = out["pixel_values"].float()
    grid = out["image_grid_thw"].tolist()[0]
    mine, mygrid = hf_patchify(img_u8)
    ok_shape = tuple(pv.shape) == tuple(mine.shape) and grid == mygrid
    maxdiff = float((pv - mine).abs().max()) if ok_shape else float("inf")
    res = {"processor_class": type(proc).__name__, "hf_shape": list(pv.shape), "hf_grid": grid,
           "mine_shape": list(mine.shape), "mine_grid": mygrid, "max_abs_diff": maxdiff,
           "ok": bool(ok_shape and maxdiff < 1e-4)}
    if not res["ok"]:
        raise SystemExit(f"FATAL: patchify does not match the HF processor: {res}")
    return res


# ----------------------------------------------------------------------------- the tower
def build_tower(ckpt: str, device: str):
    """Caller must hold `set_current_vllm_config(...)`: the distributed init, the CustomOps built here
    (rope, norms, parallel linears) and the attention wrappers at forward time all read it."""
    from vllm.distributed import ensure_model_parallel_initialized, init_distributed_environment
    from vllm.model_executor.models.qwen3_vl import Qwen3_VisionTransformer
    from vllm.models.qwen3_8_flash_next.config import Qwen4ExpConfig

    init_distributed_environment(world_size=1, rank=0, local_rank=0, backend="nccl",
                                 distributed_init_method=f"tcp://127.0.0.1:{free_port()}")
    ensure_model_parallel_initialized(1, 1)
    try:
        cfg = Qwen4ExpConfig.from_pretrained(ckpt)
    except Exception as e:  # pragma: no cover - fallback path
        log("Qwen4ExpConfig.from_pretrained failed, using the dict constructor:", repr(e))
        cfg = Qwen4ExpConfig(**json.load(open(os.path.join(ckpt, "config.json"))))
    vcfg = cfg.vision_config
    assert list(vcfg.deepstack_visual_indexes) == [], vcfg.deepstack_visual_indexes
    assert vcfg.out_hidden_size == cfg.text_config.hidden_size == 2560
    old = torch.get_default_dtype()
    torch.set_default_dtype(torch.bfloat16)      # as vLLM's set_default_torch_dtype(model dtype)
    try:
        with torch.device(device):
            tower = Qwen3_VisionTransformer(vcfg, norm_eps=cfg.text_config.rms_norm_eps,
                                            quant_config=None, prefix="model.visual")
    finally:
        torch.set_default_dtype(old)
    tower.eval()
    return tower, cfg


def load_visual_weights(tower, ckpt: str) -> dict:
    from safetensors import safe_open
    idx = json.load(open(os.path.join(ckpt, "model.safetensors.index.json")))["weight_map"]
    vis_keys = sorted(k for k in idx if k.startswith(VIS_PREFIX))
    shards = sorted({idx[k] for k in vis_keys})
    h = hashlib.sha256()
    n_params = 0
    dtypes = set()

    def gen():
        nonlocal n_params
        for shard in shards:
            with safe_open(os.path.join(ckpt, shard), "pt", device="cpu") as f:
                for k in sorted(f.keys()):
                    if not k.startswith(VIS_PREFIX):
                        continue
                    t = f.get_tensor(k)
                    dtypes.add(str(t.dtype))
                    n_params += t.numel()
                    h.update(k.encode()); h.update(str(tuple(t.shape)).encode()); h.update(str(t.dtype).encode())
                    h.update(t.contiguous().view(torch.int16).numpy().tobytes() if t.dtype == torch.bfloat16
                             else t.contiguous().numpy().tobytes())
                    yield k[len(VIS_PREFIX):], t

    loaded = set(tower.load_weights(gen()))
    params = {n for n, _ in tower.named_parameters()}
    missing = sorted(params - loaded)
    extra = sorted(loaded - params)
    if missing:
        raise SystemExit(f"FATAL: {len(missing)} tower parameters not loaded, e.g. {missing[:8]}")
    shard_info = [{"file": s, "bytes": os.path.getsize(os.path.join(ckpt, s)),
                   "mtime": dt.datetime.fromtimestamp(os.path.getmtime(os.path.join(ckpt, s))).isoformat()}
                  for s in shards]
    return {"n_visual_tensors": len(vis_keys), "n_visual_params": n_params, "dtypes": sorted(dtypes),
            "visual_tensor_bytes_sha256": h.hexdigest(), "shards": shard_info,
            "n_loaded_param_names": len(loaded), "extra_loaded_names": extra[:8]}


@torch.no_grad()
def tower_tokens(tower, img_u8: np.ndarray) -> torch.Tensor:
    patches, grid = hf_patchify(img_u8)
    out = tower(patches.to(tower.device, tower.dtype), [grid])
    assert out.shape == (grid[1] * grid[2] // (MERGE * MERGE), 2560), out.shape
    return out.float().cpu()


# ----------------------------------------------------------------------------- metrics
def cos(a: torch.Tensor, b: torch.Tensor) -> float:
    return float(torch.nn.functional.cosine_similarity(a.flatten(), b.flatten(), dim=0))


def pairwise_cos(T: torch.Tensor) -> torch.Tensor:
    N = torch.nn.functional.normalize(T, dim=1)
    return N @ N.T


def table_stats(T: torch.Tensor) -> dict:
    norms = T.norm(dim=1)
    C = pairwise_cos(T)
    off = C[~torch.eye(16, dtype=torch.bool)]
    Tc = T - T.mean(0, keepdim=True)
    Cc = pairwise_cos(Tc)
    offc = Cc[~torch.eye(16, dtype=torch.bool)]
    D = torch.cdist(Tc, Tc)
    D.fill_diagonal_(float("inf"))
    nn_dist, nn_idx = D.min(dim=1)
    return {"norm_mean": float(norms.mean()), "norm_min": float(norms.min()), "norm_max": float(norms.max()),
            "raw_offdiag_cos_mean": float(off.mean()), "raw_offdiag_cos_min": float(off.min()),
            "raw_offdiag_cos_max": float(off.max()),
            "centred_offdiag_cos_mean": float(offc.mean()), "centred_offdiag_cos_max": float(offc.max()),
            "centred_nn_dist_min": float(nn_dist.min()), "centred_nn_dist_mean": float(nn_dist.mean()),
            "centred_nn_pairs": [[i, int(nn_idx[i]), round(float(nn_dist[i]), 3)] for i in range(16)],
            "shared_component_fraction": float((T.mean(0).norm() ** 2) / (T.norm(dim=1) ** 2).mean())}


def nearest_row_eval(tokens: torch.Tensor, cells: np.ndarray, T: torch.Tensor, centre: bool) -> dict:
    """tokens (4096,2560) row-major over the 64x64 board; cells (64,64) ints; T (16,2560)."""
    c = torch.from_numpy(cells.reshape(-1)).long()
    tok, tab = tokens, T
    if centre:
        mu = T.mean(0, keepdim=True)
        tok, tab = tokens - mu, T - mu
    S = torch.nn.functional.normalize(tok, dim=1) @ torch.nn.functional.normalize(tab, dim=1).T  # (4096,16)
    pred = S.argmax(dim=1)
    true_cos = S[torch.arange(len(c)), c]
    acc = (pred == c).float()
    # interior = every existing 4-neighbour has the same colour
    g = cells
    same = np.ones_like(g, dtype=bool)
    same[1:, :] &= g[1:, :] == g[:-1, :]
    same[:-1, :] &= g[:-1, :] == g[1:, :]
    same[:, 1:] &= g[:, 1:] == g[:, :-1]
    same[:, :-1] &= g[:, :-1] == g[:, 1:]
    interior = torch.from_numpy(same.reshape(-1))
    per_colour = {}
    for k in sorted(set(c.tolist())):
        m = c == k
        conf = torch.bincount(pred[m], minlength=16)
        conf[k] = 0
        top = int(conf.argmax()) if conf.sum() > 0 else None
        per_colour[int(k)] = {"n": int(m.sum()), "acc": float(acc[m].mean()), "cos_true_mean": float(true_cos[m].mean()),
                              "cos_true_min": float(true_cos[m].min()),
                              "top_confusion": top, "top_confusion_n": int(conf.max()) if top is not None else 0}
    return {"acc": float(acc.mean()), "cos_true_mean": float(true_cos.mean()),
            "cos_true_p05": float(true_cos.quantile(0.05)),
            "n_interior": int(interior.sum()), "acc_interior": float(acc[interior].mean()) if interior.any() else None,
            "acc_boundary": float(acc[~interior].mean()) if (~interior).any() else None,
            "per_colour": per_colour}


def within_board_colour_means(tokens: torch.Tensor, cells: np.ndarray, T_flat: torch.Tensor) -> dict:
    c = torch.from_numpy(cells.reshape(-1)).long()
    out = {}
    for k in sorted(set(c.tolist())):
        m = c == k
        mu = tokens[m].mean(0)
        tight = torch.nn.functional.cosine_similarity(tokens[m], mu.unsqueeze(0), dim=1)
        out[int(k)] = {"n": int(m.sum()), "cos_mean_vs_flat_row": cos(mu, T_flat[k]),
                       "tightness_mean": float(tight.mean()), "tightness_min": float(tight.min())}
    return out


def position_eval(tokens: torch.Tensor, cells: np.ndarray, solid_all: torch.Tensor, pos_mean: torch.Tensor) -> dict:
    """Colour x POSITION lookup: predict the real token at cell k from the solid board of colour j at the same
    cell k. solid_all (16, 4096, 2560) bf16; pos_mean (4096, 2560) = mean over the 16 colours at each cell."""
    c = torch.from_numpy(cells.reshape(-1)).long()
    tok = tokens.float()
    S = torch.einsum("kd,jkd->kj", torch.nn.functional.normalize(tok, dim=1),
                     torch.nn.functional.normalize(solid_all.float(), dim=2))            # (4096,16)
    tokc = tok - pos_mean.float()
    solc = solid_all.float() - pos_mean.float().unsqueeze(0)
    Sc = torch.einsum("kd,jkd->kj", torch.nn.functional.normalize(tokc, dim=1),
                      torch.nn.functional.normalize(solc, dim=2))
    pos_only = torch.nn.functional.cosine_similarity(tok, pos_mean.float(), dim=1)        # how much is position
    g = cells
    same = np.ones_like(g, dtype=bool)
    same[1:, :] &= g[1:, :] == g[:-1, :]; same[:-1, :] &= g[:-1, :] == g[1:, :]
    same[:, 1:] &= g[:, 1:] == g[:, :-1]; same[:, :-1] &= g[:, :-1] == g[:, 1:]
    interior = torch.from_numpy(same.reshape(-1))
    out = {}
    for name, M in (("pos_table", S), ("pos_table_centred", Sc)):
        acc = (M.argmax(1) == c).float()
        true = M[torch.arange(len(c)), c]
        per = {}
        for k in sorted(set(c.tolist())):
            m = c == k
            per[int(k)] = {"n": int(m.sum()), "acc": float(acc[m].mean()), "cos_true_mean": float(true[m].mean())}
        out[name] = {"acc": float(acc.mean()), "acc_interior": float(acc[interior].mean()), "acc_boundary": float(acc[~interior].mean()),
                     "cos_true_mean": float(true.mean()), "per_colour": per}
    out["cos_token_vs_position_mean"] = {"mean": float(pos_only.mean()), "min": float(pos_only.min()),
                                         "interior_mean": float(pos_only[interior].mean()), "boundary_mean": float(pos_only[~interior].mean())}
    return out


@torch.no_grad()
def hf_crosscheck(ckpt: str, cfg, tower, cases: dict[str, np.ndarray]) -> dict:
    """Independent implementation: transformers' Qwen3VLVisionModel on the same weights and the same patches.
    Reports per-token cosine / max abs diff against the vLLM tower for each image in `cases`."""
    from transformers.models.qwen3_vl.modeling_qwen3_vl import Qwen3VLVisionModel
    vcfg = cfg.vision_config
    try:
        hf = Qwen3VLVisionModel._from_config(vcfg, attn_implementation="sdpa", dtype=torch.bfloat16)
    except TypeError:
        hf = Qwen3VLVisionModel._from_config(vcfg, attn_implementation="sdpa", torch_dtype=torch.bfloat16)
    from safetensors import safe_open
    idx = json.load(open(os.path.join(ckpt, "model.safetensors.index.json")))["weight_map"]
    sd = {}
    for shard in sorted({v for k, v in idx.items() if k.startswith(VIS_PREFIX)}):
        with safe_open(os.path.join(ckpt, shard), "pt", device="cpu") as f:
            for k in f.keys():
                if k.startswith(VIS_PREFIX):
                    sd[k[len(VIS_PREFIX):]] = f.get_tensor(k)
    missing, unexpected = hf.load_state_dict(sd, strict=False)
    hf = hf.to(tower.device).eval()
    res = {"hf_class": type(hf).__name__, "attn_implementation": getattr(hf.config, "_attn_implementation", None),
           "missing_keys": list(missing)[:10], "unexpected_keys": list(unexpected)[:10], "cases": {}}
    for name, img in cases.items():
        patches, grid = hf_patchify(img)
        o = hf(patches.to(tower.device, torch.bfloat16), torch.tensor([grid], device=tower.device))
        # transformers 5.15: last_hidden_state = pre-merger (N_patches, 1152); pooler_output = merged (N/4, 2560)
        o = (o.pooler_output if getattr(o, "pooler_output", None) is not None else o[1]).float().cpu()
        v = tower_tokens(tower, img)
        cs = torch.nn.functional.cosine_similarity(o, v, dim=1)
        res["cases"][name] = {"n_tokens": int(o.shape[0]), "cos_min": float(cs.min()), "cos_mean": float(cs.mean()),
                              "max_abs_diff": float((o - v).abs().max()), "rel_fro": float((o - v).norm() / v.norm())}
    del hf
    torch.cuda.empty_cache()
    return res


def load_board(spec: str, repo: pathlib.Path) -> tuple[np.ndarray, dict]:
    path, line = spec.rsplit(":", 1)
    p = pathlib.Path(path)
    if not p.is_absolute():
        p = repo / p
    with open(p) as fh:
        for n, raw in enumerate(fh):
            if n == int(line):
                d = json.loads(raw)
                b = np.asarray(d["board"], dtype=np.int64)
                assert b.shape == (64, 64), b.shape
                return b, {"file": str(p), "line": int(line), "title": d.get("title"), "level": d.get("level"),
                           "game": p.name[:4], "n_colours": int(len(np.unique(b))), "board_sha1": hashlib.sha1(b.astype(np.uint8).tobytes()).hexdigest()}
    raise SystemExit(f"line {line} not in {p}")


# ----------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", default="/model")
    ap.add_argument("--out-dir", default="/work/notebooks_duck/synth_tokens")
    ap.add_argument("--scratch", default="/scratch")
    ap.add_argument("--device", default="cuda:0")
    ap.add_argument("--board", action="append", default=[],
                    help="events.jsonl path (relative to the engine root) ':' line number; repeatable")
    args = ap.parse_args()
    t0 = time.time()
    repo = engine_root()
    rgb = engine_rgb(repo)
    log("engine root", repo, "palette sha", palette_sha(rgb))
    out_dir = pathlib.Path(args.out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    scratch = pathlib.Path(args.scratch); scratch.mkdir(parents=True, exist_ok=True)

    # 1. patchify check against the real processor, on an image it will not resize
    probe_board = np.arange(64 * 64).reshape(64, 64) % 16
    probe_img = render_board_array(probe_board, rgb, PX)
    patch_check = check_patchify_against_hf(args.ckpt, probe_img)
    log("patchify vs HF processor:", patch_check)

    # 2. tower (everything from here on runs under the engine-config context vLLM's modules expect)
    from vllm.config import VllmConfig, set_current_vllm_config
    vllm_cfg = VllmConfig()
    ctx = set_current_vllm_config(vllm_cfg); ctx.__enter__()
    tower, cfg = build_tower(args.ckpt, args.device)
    wl = load_visual_weights(tower, args.ckpt)
    log("weights:", {k: v for k, v in wl.items() if k != "shards"})
    log("attn backend:", str(tower.attn_backend), "dtype", str(tower.dtype), "device", str(tower.device))

    # 3. flat 32x32 squares -> one merged token each
    flat = torch.stack([tower_tokens(tower, np.ascontiguousarray(np.broadcast_to(np.array(rgb[i], np.uint8), (PX, PX, 3))))[0]
                        for i in range(16)])                                  # (16,2560)
    log("flat table", tuple(flat.shape), "norms", [round(float(x), 2) for x in flat.norm(dim=1)])

    # 4. all-one-colour boards at 32 px/cell -> 4096 tokens; centre / interior mean / corner
    centre, interior, corner, top_mid = [], [], [], []
    solid = {}
    solid_all = []                                                                      # (16, 4096, 2560) bf16
    for i in range(16):
        tok = tower_tokens(tower, render_board_array(np.full((64, 64), i), rgb, PX))   # (4096,2560)
        solid_all.append(tok.to(torch.bfloat16))
        grid = tok.view(64, 64, -1)
        centre.append(grid[32, 32]); interior.append(grid[8:56, 8:56].reshape(-1, 2560).mean(0))
        corner.append(grid[0, 0]); top_mid.append(grid[0, 32])
        solid[i] = {"cos_flat_vs_centre": cos(flat[i], grid[32, 32]),
                    "cos_flat_vs_interior_mean": cos(flat[i], interior[-1]),
                    "cos_flat_vs_corner": cos(flat[i], grid[0, 0]),
                    "cos_centre_vs_corner": cos(grid[32, 32], grid[0, 0]),
                    "cos_centre_vs_top_mid": cos(grid[32, 32], grid[0, 32]),
                    "interior_tightness_min": float(torch.nn.functional.cosine_similarity(
                        grid[8:56, 8:56].reshape(-1, 2560), interior[-1].unsqueeze(0), dim=1).min()),
                    "norm_flat": float(flat[i].norm()), "norm_centre": float(grid[32, 32].norm())}
        log(f"colour {i:2d} rgb={rgb[i]} flat~centre {solid[i]['cos_flat_vs_centre']:.4f} "
            f"flat~interior {solid[i]['cos_flat_vs_interior_mean']:.4f} centre~corner {solid[i]['cos_centre_vs_corner']:.4f}")
    centre, interior = torch.stack(centre), torch.stack(interior)
    solid_all = torch.stack(solid_all)                                                  # (16, 4096, 2560)
    pos_mean = solid_all.float().mean(0).to(torch.bfloat16)                             # (4096, 2560)
    pos_path = scratch / "table_flashnext_pos_v1.pt"
    torch.save({"table_pos": solid_all.permute(1, 0, 2).contiguous(), "pos_mean": pos_mean,
                "meta": {"layout": "(4096 cells row-major, 16 colours, 2560) bf16: token of the all-colour-j board at cell k",
                         "px_per_cell": PX}}, pos_path)
    pos_sha = hashlib.sha256(open(pos_path, "rb").read()).hexdigest()
    log("position table saved", pos_path, os.path.getsize(pos_path) // 2**20, "MiB sha256", pos_sha[:16])
    # same-position, different-colour similarity (position dominance check): 16 colours at the centre cell
    tables = {"flat": flat, "board_centre": centre, "board_interior_mean": interior}
    stats = {k: table_stats(v) for k, v in tables.items()}
    # cross-table nearest-row consistency: is the centre token nearest to its own flat row?
    S = torch.nn.functional.normalize(centre, dim=1) @ torch.nn.functional.normalize(flat, dim=1).T
    cross = {"centre_nearest_flat_row_acc": float((S.argmax(1) == torch.arange(16)).float().mean()),
             "centre_nearest_flat_row_acc_centred": float(((torch.nn.functional.normalize(centre - flat.mean(0), dim=1)
                                                           @ torch.nn.functional.normalize(flat - flat.mean(0), dim=1).T).argmax(1)
                                                          == torch.arange(16)).float().mean())}
    log("table stats flat:", {k: (round(v, 4) if isinstance(v, float) else v) for k, v in stats["flat"].items() if k != "centred_nn_pairs"})
    log("cross:", cross)

    # 5. real boards
    boards = []
    for spec in args.board:
        cells, meta = load_board(spec, repo)
        tok = tower_tokens(tower, render_board_array(cells, rgb, PX))
        torch.save({"tokens": tok.to(torch.bfloat16), "cells": torch.from_numpy(cells), "meta": meta},
                   scratch / f"real_board_tokens_{meta['game']}_{meta['board_sha1'][:8]}.pt")
        res = {"meta": meta, "eval": {}}
        for tname, T in tables.items():
            for centred in (False, True):
                r = nearest_row_eval(tok, cells, T, centred)
                res["eval"][f"{tname}{'_centred' if centred else ''}"] = r
                log(f"board {meta['game']} line {meta['line']} ({meta['n_colours']} colours) table={tname:<19} centred={centred!s:<5} "
                    f"acc {r['acc']:.4f} (interior {r['acc_interior']}, boundary {r['acc_boundary']}) cos_true mean {r['cos_true_mean']:.4f}")
        res["colour_means_vs_flat"] = within_board_colour_means(tok, cells, flat)
        pe = position_eval(tok, cells, solid_all, pos_mean)
        res["position_eval"] = pe
        log(f"board {meta['game']} POSITION table: acc {pe['pos_table']['acc']:.4f} (interior {pe['pos_table']['acc_interior']:.4f}, "
            f"boundary {pe['pos_table']['acc_boundary']:.4f}) centred acc {pe['pos_table_centred']['acc']:.4f} "
            f"(interior {pe['pos_table_centred']['acc_interior']:.4f}, boundary {pe['pos_table_centred']['acc_boundary']:.4f}); "
            f"cos(token, position mean) {pe['cos_token_vs_position_mean']['mean']:.4f}")
        boards.append((res, cells))
    hf = None
    try:
        first_cells = boards[0][1] if boards else np.zeros((64, 64), np.int64)
        hf = hf_crosscheck(args.ckpt, cfg, tower, {
            "flat_square_colour8": np.ascontiguousarray(np.broadcast_to(np.array(rgb[8], np.uint8), (PX, PX, 3))),
            "solid_board_colour8": render_board_array(np.full((64, 64), 8), rgb, PX),
            "real_board_0": render_board_array(first_cells, rgb, PX)})
        log("HF cross-check:", {k: v for k, v in hf.items() if k != "cases"}, {k: {kk: round(vv, 5) if isinstance(vv, float) else vv for kk, vv in v.items()} for k, v in hf["cases"].items()})
    except Exception as e:  # supplementary; report, do not hide
        hf = {"error": repr(e)}
        log("HF cross-check FAILED:", repr(e))
    boards = [b for b, _ in boards]

    # 6. save
    meta = {"created": dt.datetime.now().isoformat(timespec="seconds"), "px_per_cell": PX,
            "flat_input": "32x32 px square of the colour -> grid (1,2,2) -> 1 merged token",
            "board_input": "64x64 cells x 32 px -> 2048x2048 px -> grid (1,128,128) -> 4096 tokens, row-major (k = r*64 + c)",
            "render": "palette LUT per cell, each cell one flat 32x32 block (== vision_context NEAREST upscale); "
                      "rescale 1/255, normalise mean 0.5 std 0.5, patch 16, merge 2, temporal dup 2",
            "patchify_check": patch_check,
            "tower": "vllm.model_executor.models.qwen3_vl.Qwen3_VisionTransformer(config.vision_config, "
                     "norm_eps=config.text_config.rms_norm_eps, quant_config=None, prefix='model.visual') -- "
                     "as RT/models/qwen3_8_flash_next/nvidia/model.py:871; visual.* are in the quant ignore list",
            "vision_config": {k: getattr(cfg.vision_config, k) for k in
                              ("depth", "hidden_size", "num_heads", "intermediate_size", "hidden_act", "patch_size",
                               "spatial_merge_size", "temporal_patch_size", "num_position_embeddings", "out_hidden_size",
                               "deepstack_visual_indexes", "in_channels")},
            "norm_eps": cfg.text_config.rms_norm_eps,
            "attn_backend": str(tower.attn_backend), "dtype": str(tower.dtype),
            "checkpoint": args.ckpt, "checkpoint_config_sha256": hashlib.sha256(open(os.path.join(args.ckpt, "config.json"), "rb").read()).hexdigest(),
            "weights": wl,
            "palette": {"source_files": [_TAAF, _VCTX], "sha256": palette_sha(rgb), "rgb": [list(rgb[i]) for i in range(16)]},
            "runtime": {"torch": torch.__version__, "cuda": torch.version.cuda, "gpu": torch.cuda.get_device_name(0),
                        "vllm": __import__("vllm").__version__, "transformers": __import__("transformers").__version__,
                        "docker_image_id": os.environ.get("S0_IMAGE_ID"), "git_sha_worktree": os.environ.get("S0_GIT_SHA")},
            "boards": [b["meta"] for b in boards],
            "position_table": {"path": str(pos_path), "sha256": pos_sha, "bytes": os.path.getsize(pos_path)},
            "hf_crosscheck": hf,
            "seconds": round(time.time() - t0, 1)}
    torch.save({"table": flat.contiguous(), "table_bf16": flat.to(torch.bfloat16).contiguous(),
                "table_board_centre": centre.contiguous(), "table_board_interior_mean": interior.contiguous(),
                "palette_rgb": torch.tensor([rgb[i] for i in range(16)], dtype=torch.uint8), "meta": meta},
               out_dir / "table_flashnext_v1.pt")
    json.dump(meta, open(out_dir / "table_flashnext_v1.provenance.json", "w"), indent=1)
    json.dump({"solid": solid, "table_stats": stats, "cross": cross, "boards": boards, "meta": meta},
              open(out_dir / "s0_results.json", "w"), indent=1)
    log("saved", out_dir / "table_flashnext_v1.pt", "and provenance / results; total", meta["seconds"], "s")
    ctx.__exit__(None, None, None)


if __name__ == "__main__":
    main()
