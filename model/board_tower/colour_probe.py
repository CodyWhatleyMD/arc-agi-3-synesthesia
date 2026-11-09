#!/usr/bin/env python3
"""Colour probe (CL2, 2026-10-30): how much of each cell's TRUE colour can be read back out of a board token?

The investigator's question: is the teacher (Flash-Next's own vision tower) even seeing the colours, and how much of that does a
student keep? Per-token cosine to the teacher cannot answer it: 95-98% of a token's energy is a shared position /
neighbourhood code (notes/synth_tokens_s0_2026-10-03.md), so a student can score cos 0.9 and lose the colour.

Method. A token k of a px-per-cell target set covers a cp x cp block of cells (cp = 64 / sqrt(K); 2 at px16, 4 at
px8), row-major over the block grid. A LINEAR probe (2560 -> cp*cp*16 logits) is trained on the TEACHER's tokens of
every base TRAIN board (no dihedral copies) to predict the colour of each cell in its block, then scored on the 500
held-out EVAL boards (the five holdout games):
  * teacher : probe on the teacher's eval tokens  -> how much colour the parent carries, linearly
  * student : the SAME probe on a student checkpoint's tokens for the same eval boards -> how much the student kept
Reported per cell: overall accuracy, interior vs boundary (any 4-neighbour of another colour), by size of the
cell's same-colour 4-connected component (1-4, 5-55, >55 cells; S0 read small objects better), per colour (recall),
per holdout game, and the per-board majority-colour baseline. A linear probe is a LOWER bound on what is recoverable;
the language model is not linear, but it was trained on exactly these tokens.

usage: colour_probe.py --targets ROOT [--student CKPT ...] [--epochs 2] [--device cuda:0] --out JSON
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

import numpy as np
import torch
import torch.nn.functional as F
from safetensors import safe_open
from scipy import ndimage

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
N_COL = 16


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def block_labels(cells: torch.Tensor, cp: int) -> torch.Tensor:
    """cells (B,64,64) uint8 -> (B, K, cp*cp) long: the colours of the cells each token covers, row-major."""
    b = cells.shape[0]; s = 64 // cp
    x = cells.long().view(b, s, cp, s, cp).permute(0, 1, 3, 2, 4).reshape(b, s * s, cp * cp)
    return x


def iter_shards(root: pathlib.Path, split: str):
    m = json.load(open(root / "manifest.json"))
    for sh in m["shards"]:
        if sh["split"] != split:
            continue
        with safe_open(str(root / sh["file"]), "pt") as f:
            t, ci, c = f.get_tensor("targets"), f.get_tensor("cell_idx"), f.get_tensor("cells")
        k = t.shape[1]
        if not torch.equal(ci, torch.arange(k, dtype=ci.dtype).expand_as(ci)):
            raise SystemExit(f"{sh['file']}: cell_idx is not every token in order (train_cells subset?)")
        yield sh["file"], t, c


def cell_masks(cells: np.ndarray):
    """Per cell: boundary flag, and the size of its same-colour 4-connected component."""
    b = cells.shape[0]
    boundary = np.zeros(cells.shape, bool); comp = np.zeros(cells.shape, np.int32)
    for i in range(b):
        g = cells[i]
        bd = np.zeros_like(g, bool)
        bd[1:, :] |= g[1:, :] != g[:-1, :]; bd[:-1, :] |= g[:-1, :] != g[1:, :]
        bd[:, 1:] |= g[:, 1:] != g[:, :-1]; bd[:, :-1] |= g[:, :-1] != g[:, 1:]
        boundary[i] = bd
        for col in np.unique(g):
            lab, n = ndimage.label(g == col)
            if n:
                sizes = np.bincount(lab.ravel())
                m = g == col
                comp[i][m] = sizes[lab[m]]
    return boundary, comp


def unblock(pred: torch.Tensor, cp: int) -> torch.Tensor:
    """(B, K, cp*cp) -> (B, 64, 64)"""
    b = pred.shape[0]; s = 64 // cp
    return pred.view(b, s, s, cp, cp).permute(0, 1, 3, 2, 4).reshape(b, 64, 64)


_DE = None


def _de():
    """16x16 CIEDE2000 between the engine palette's colours (palette_de.py, checked against Sharma et al. 2005)."""
    global _DE
    if _DE is None:
        sys.path.insert(0, str(REPO / "scripts" / "board_tower"))
        import palette_de
        _DE = palette_de.de_matrix("2000")
    return _DE


def de_cols(pred: np.ndarray, cells: np.ndarray) -> dict:
    """Distance-scored columns beside exact match (CL1/the investigator 14:40): mean CIEDE2000 between guessed and true
    palette colour, and the share of cells within dE2000 25 (a tolerant accuracy: adjacent greys count, magenta for
    black does not)."""
    d = _de()[cells.astype(int).ravel(), pred.astype(int).ravel()]
    return {"mean_dE2000": float(d.mean()) if d.size else None, "within_dE25": float((d <= 25).mean()) if d.size else None}


def score(pred: np.ndarray, cells: np.ndarray, games: list[str]) -> dict:
    ok = pred == cells
    boundary, comp = cell_masks(cells)
    maj = np.array([np.bincount(g.ravel(), minlength=N_COL).argmax() for g in cells])
    base = (cells == maj[:, None, None])
    out = {"cells": int(ok.size), "acc": float(ok.mean()), "majority_baseline": float(base.mean()),
           "interior_acc": float(ok[~boundary].mean()), "boundary_acc": float(ok[boundary].mean()),
           "boundary_share": float(boundary.mean()),
           **de_cols(pred, cells), "interior_dE": de_cols(pred[~boundary], cells[~boundary]),
           "boundary_dE": de_cols(pred[boundary], cells[boundary])}
    cm = np.zeros((N_COL, N_COL), np.int64); np.add.at(cm, (cells.astype(int).ravel(), pred.astype(int).ravel()), 1)
    out["confusion_true_by_guess"] = cm.tolist()          # rows = true colour, cols = guessed; enough to rescore
    for name, lo, hi in (("comp_1_4", 1, 4), ("comp_5_55", 5, 55), ("comp_gt55", 56, 1 << 30)):
        m = (comp >= lo) & (comp <= hi)
        out[name] = {"acc": float(ok[m].mean()) if m.any() else None, "cells": int(m.sum()), **de_cols(pred[m], cells[m])}
    out["per_colour_recall"] = {str(c): {"acc": float(ok[cells == c].mean()), "cells": int((cells == c).sum())}
                                for c in range(N_COL) if (cells == c).any()}
    out["per_game"] = {}
    for g in sorted(set(games)):
        idx = [i for i, x in enumerate(games) if x == g]
        out["per_game"][g] = {"boards": len(idx), "acc": float(ok[idx].mean()),
                              "majority_baseline": float(base[idx].mean())}
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--targets", required=True)
    ap.add_argument("--student", action="append", default=[], help="student checkpoint(s) to score with the probe")
    ap.add_argument("--epochs", type=int, default=2)
    ap.add_argument("--batch-tokens", type=int, default=8192)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--device", default="cuda:0")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--max-train-shards", type=int, default=None, help="smoke tests only")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    torch.manual_seed(a.seed)
    root = pathlib.Path(a.targets); dev = torch.device(a.device)
    m = json.load(open(root / "manifest.json"))
    k = m["shards"][0]["cells_per_board"]; side = int(round(k ** 0.5)); cp = 64 // side
    assert side * side == k and side * cp == 64, (k, side, cp)
    log(f"targets {root}: K={k} tokens/board, block {cp}x{cp} cells/token; train boards "
        f"{sum(b['split'] == 'train' for b in m['boards'])}, eval {sum(b['split'] == 'eval' for b in m['boards'])}")

    # Closed-form RIDGE probe onto one-hot colours (bias column included), accumulated in float64 over every base
    # train shard. It converges by construction (the 10-30 12:45 SGD probe had not: train acc 0.49 < majority 0.75).
    # The ridge strength is chosen on the LAST train shard, held out of the fit for that choice only; the final
    # weights refit on all train shards. Eval boards never touch either step.
    n_out = cp * cp * N_COL
    tr_files = [sh["file"] for sh in m["shards"] if sh["split"] == "train"]
    if a.max_train_shards is not None:
        tr_files = tr_files[:a.max_train_shards]
    hold_file = tr_files[-1]

    def mats(tok, cells):
        x = tok.reshape(-1, 2560).to(dev).double()
        x = torch.cat([x, torch.ones(x.shape[0], 1, dtype=x.dtype, device=dev)], 1)
        y = F.one_hot(block_labels(cells, cp).reshape(-1, cp * cp).to(dev), N_COL).reshape(-1, n_out).double()
        return x.T @ x, x.T @ y

    XtX = torch.zeros(2561, 2561, dtype=torch.float64, device=dev); XtY = torch.zeros(2561, n_out, dtype=torch.float64, device=dev)
    hold = None; n_tr = 0; t0 = time.time()
    # SAME-GAME test set (the investigator 14:31: across-game scoring measures generalisation, not whether the colour is in the
    # token): every 10th train board is never fitted on, so it is an unseen board from the games the probe knows.
    sg_tok, sg_cells = [], []
    for name, tt, cc in iter_shards(root, "train"):
        if name not in tr_files:
            continue
        sel = torch.arange(tt.shape[0]) % 10 == 9
        sg_tok.append(tt[sel]); sg_cells.append(cc[sel]); tt, cc = tt[~sel], cc[~sel]
        a_, b_ = mats(tt, cc)
        if name == hold_file:
            hold = (tt, cc, a_, b_)
        else:
            XtX += a_; XtY += b_
        n_tr += tt.shape[0]
    log(f"ridge: accumulated {n_tr} train boards ({len(tr_files)} shards, held-out shard {hold_file}) in {time.time() - t0:.0f}s")
    scale = float(XtX.diagonal().mean())

    def solve(lam, A, B):
        return torch.linalg.solve(A + lam * scale * torch.eye(2561, dtype=A.dtype, device=dev), B).float()

    def predict_w(w, tok):
        outs = []
        for s in range(0, tok.shape[0], 16):
            xb = tok[s:s + 16].to(dev).float()
            xb = torch.cat([xb, torch.ones(*xb.shape[:-1], 1, device=dev)], -1)
            outs.append((xb @ w).view(xb.shape[0], k, cp * cp, N_COL).argmax(-1).cpu())
        return unblock(torch.cat(outs), cp).numpy()

    lam_scores = {}
    for lam in (1e-8, 1e-7, 1e-6, 1e-5, 1e-4, 1e-3, 1e-2):
        w = solve(lam, XtX, XtY)
        lam_scores[lam] = float((predict_w(w, hold[0]) == hold[1].numpy()).mean())
    lam = max(lam_scores, key=lam_scores.get)
    log("ridge: held-out-shard cell accuracy by lambda " + ", ".join(f"{l:g}: {s:.4f}" for l, s in lam_scores.items())
        + f" -> lambda {lam:g}")
    W = solve(lam, XtX + hold[2], XtY + hold[3])

    # eval boards, in manifest order, with their games
    ev_tok, ev_cells = [], []
    for name, t, c in iter_shards(root, "eval"):
        ev_tok.append(t); ev_cells.append(c)
    ev_tok = torch.cat(ev_tok); ev_cells = torch.cat(ev_cells)
    from scripts.board_tower import common as C
    game_of = {b["sha1"]: b["game"] for b in m["boards"] if b["split"] == "eval"}
    games = [game_of[C.board_sha1(ev_cells[i].numpy())] for i in range(ev_cells.shape[0])]   # by content, not order
    assert len(games) == len(game_of), (len(games), len(game_of))
    def predict(tok: torch.Tensor) -> np.ndarray:
        with torch.no_grad():
            return predict_w(W, tok)

    # sanity: the same probe on TRAIN boards (first 2 train shards). A train/eval gap is generalisation across
    # games; a low train accuracy with a low train loss would be a bug in the scoring path.
    tr_tok, tr_cells = [], []
    for n_sh, (name, t, c) in enumerate(iter_shards(root, "train")):
        tr_tok.append(t); tr_cells.append(c)
        if n_sh >= 1:
            break
    tr_tok = torch.cat(tr_tok); tr_cells_np = torch.cat(tr_cells).numpy()
    cells_np = ev_cells.numpy()
    res = {"targets": str(root), "tokens_per_board": k, "cells_per_token_side": cp, "ridge_lambda_rel": lam, "ridge_holdout_shard_acc": lam_scores,
           "probe": f"ridge (closed form) 2560+bias -> {cp * cp}x{N_COL} one-hot, argmax per cell", "train_boards": "all base train boards (no dihedral)",
           "eval_boards": int(ev_tok.shape[0]), "teacher": score(predict(ev_tok), cells_np, games)}
    _tp = predict(tr_tok)
    _tr_maj = np.array([np.bincount(g.ravel(), minlength=N_COL).argmax() for g in tr_cells_np])
    sg_tok = torch.cat(sg_tok); sg_cells_np = torch.cat(sg_cells).numpy()
    tr_game = {b["sha1"]: b["game"] for b in m["boards"] if b["split"] == "train"}
    sg_games = [tr_game.get(C.board_sha1(g), "?") for g in sg_cells_np]
    res["teacher_same_game"] = score(predict(sg_tok), sg_cells_np, sg_games)
    log(f"TEACHER same games, unseen boards ({sg_tok.shape[0]}): acc {res['teacher_same_game']['acc']:.4f} (majority "
        f"{res['teacher_same_game']['majority_baseline']:.4f}) interior {res['teacher_same_game']['interior_acc']:.4f} "
        f"boundary {res['teacher_same_game']['boundary_acc']:.4f} comp1-4 {res['teacher_same_game']['comp_1_4']['acc']} "
        f"comp5-55 {res['teacher_same_game']['comp_5_55']['acc']} comp>55 {res['teacher_same_game']['comp_gt55']['acc']}")
    res["teacher_train_sanity"] = {"boards": int(tr_tok.shape[0]), "acc": float((_tp == tr_cells_np).mean()),
                                   "majority_baseline": float((tr_cells_np == _tr_maj[:, None, None]).mean())}
    log(f"TEACHER on train boards (sanity): acc {res['teacher_train_sanity']['acc']:.4f} "
        f"(majority {res['teacher_train_sanity']['majority_baseline']:.4f}, {res['teacher_train_sanity']['boards']} boards)")
    log(f"TEACHER: acc {res['teacher']['acc']:.4f} (majority {res['teacher']['majority_baseline']:.4f}) "
        f"interior {res['teacher']['interior_acc']:.4f} boundary {res['teacher']['boundary_acc']:.4f} "
        f"comp1-4 {res['teacher']['comp_1_4']['acc']} comp5-55 {res['teacher']['comp_5_55']['acc']} "
        f"comp>55 {res['teacher']['comp_gt55']['acc']}")
    if a.student:
        from scripts.board_tower import export_embeds as ee
        res["students"] = {}
        for ck in a.student:
            st = ee.Student(ck, device=a.device)
            if st.n_pos != k:
                raise SystemExit(f"student {ck} emits {st.n_pos} tokens, targets have {k}")
            with torch.no_grad():
                stok = torch.stack([st.tokens(cells_np[i]).cpu() for i in range(cells_np.shape[0])])
            cos = F.cosine_similarity(stok.float(), ev_tok.float(), dim=-1).mean().item()
            r = score(predict(stok), cells_np, games); r["cos_to_teacher_mean"] = cos; r["tag"] = st.tag
            res["students"][ck] = r
            log(f"STUDENT {ck} (tag {st.tag}): cos to teacher {cos:.4f}; probe acc {r['acc']:.4f} interior "
                f"{r['interior_acc']:.4f} boundary {r['boundary_acc']:.4f} comp1-4 {r['comp_1_4']['acc']} "
                f"comp5-55 {r['comp_5_55']['acc']} comp>55 {r['comp_gt55']['acc']}")
    pathlib.Path(a.out).write_text(json.dumps(res, indent=1))
    log(f"wrote {a.out}")


if __name__ == "__main__":
    main()
