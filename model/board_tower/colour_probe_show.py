#!/usr/bin/env python3
"""Show the colour probe's raw output and its grading on real boards (the investigator 14:33: "show me the output and how it's
graded - exactly"). Fits the same ridge probe as colour_probe.py (every 10th train board held out of the fit), then
prints, for one unseen board from a TRAIN game and one from a HOLDOUT game, a 16x16 window of the board:
  TRUTH  - the game's colour index per cell, written in the harness's ARC symbols (W w g G c B M P R b S Y O r N p)
  GUESS  - the probe's argmax colour per cell, same symbols
  RIGHT  - '.' where GUESS == TRUTH, 'X' where not
and the board's own score = right cells / 4096. Same functions as colour_probe.py (block_labels, unblock), so what is
shown is what is graded."""
from __future__ import annotations

import json
import pathlib
import sys

import numpy as np
import torch
import torch.nn.functional as F

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / "scripts" / "board_tower"))
import colour_probe as P  # noqa: E402
from scripts.board_tower import common as C  # noqa: E402

SYM = "WwgGcBMPRbSYOrNp"
root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "/mnt/data/board_tower/targets_px8")
dev = torch.device("cuda:0")
m = json.load(open(root / "manifest.json"))
k = m["shards"][0]["cells_per_board"]; side = int(round(k ** 0.5)); cp = 64 // side; n_out = cp * cp * P.N_COL

XtX = torch.zeros(2561, 2561, dtype=torch.float64, device=dev); XtY = torch.zeros(2561, n_out, dtype=torch.float64, device=dev)
unseen_tok = unseen_cells = None
for name, tt, cc in P.iter_shards(root, "train"):
    sel = torch.arange(tt.shape[0]) % 10 == 9
    if unseen_tok is None:
        unseen_tok, unseen_cells = tt[sel][:8], cc[sel][:8]
    x = tt[~sel].reshape(-1, 2560).to(dev).double(); x = torch.cat([x, torch.ones(x.shape[0], 1, dtype=x.dtype, device=dev)], 1)
    y = F.one_hot(P.block_labels(cc[~sel], cp).reshape(-1, cp * cp).to(dev), P.N_COL).reshape(-1, n_out).double()
    XtX += x.T @ x; XtY += x.T @ y
lam = 1e-6
W = torch.linalg.solve(XtX + lam * float(XtX.diagonal().mean()) * torch.eye(2561, dtype=XtX.dtype, device=dev), XtY).float()


def guess(tok):                                   # tok (K, 2560) -> (64, 64) colour indices
    x = torch.cat([tok.to(dev).float(), torch.ones(k, 1, device=dev)], 1)
    scores = (x @ W).view(1, k, cp * cp, P.N_COL)         # 16 scores per covered cell
    return P.unblock(scores.argmax(-1).cpu(), cp)[0].numpy()   # the highest-scoring colour, put back on the 64x64 grid


ev = next(P.iter_shards(root, "eval"))
game_of = {b["sha1"]: b["game"] for b in m["boards"]}


def show(label, tok, cells):
    truth = cells.numpy().astype(int); g = guess(tok); right = g == truth
    # the 16x16 window with the most distinct colours (where there is something to see)
    best = max(((r, c) for r in range(0, 49, 4) for c in range(0, 49, 4)),
               key=lambda rc: len(np.unique(truth[rc[0]:rc[0] + 16, rc[1]:rc[1] + 16])))
    r0, c0 = best
    print(f"\n=== {label}: game {game_of.get(C.board_sha1(truth.astype(np.uint8)), '?')}, board score "
          f"{right.sum()}/4096 = {right.mean():.3f} (majority-colour guess would score "
          f"{(truth == np.bincount(truth.ravel()).argmax()).mean():.3f}); window rows {r0}-{r0 + 15}, cols {c0}-{c0 + 15}")
    print(f"{'TRUTH':18s}{'GUESS':18s}RIGHT")
    for r in range(r0, r0 + 16):
        t = "".join(SYM[v] for v in truth[r, c0:c0 + 16]); gg = "".join(SYM[v] for v in g[r, c0:c0 + 16])
        ok = "".join("." if x else "X" for x in right[r, c0:c0 + 16])
        print(f"{t}  {gg}  {ok}")


print(f"targets {root}: {k} tokens/board, each token covers {cp}x{cp} cells; ridge lambda {lam:g} x mean diag")
show("UNSEEN board, a game the probe was fitted on", unseen_tok[0], unseen_cells[0])
show("HOLDOUT-game board (a game the probe never saw)", ev[1][0], ev[2][0])
