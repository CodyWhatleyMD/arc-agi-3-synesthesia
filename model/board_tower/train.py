#!/usr/bin/env python3
"""Train the board tower by distillation (plan S2c): student(board one-hot) -> the full tower's (K, 2560) tokens.

K is the target set's tokens_per_board (manifest config.px_per_cell): 4096 at 32 px/cell, 1024 at 16 px/cell.
The student's cell_patch is DERIVED from the manifest, so a px=16 target set trains a 1024-position student and
a px=32 one trains a 4096-position student without a flag -- and a checkpoint of the wrong geometry is refused.

Data: the shards + manifest written by make_targets.py (train_*.safetensors: K rows per board, eval_*: full boards
of the 5 held-out GAMES). Loss per target row: (1 - cosine) + mse_weight * MSE / mean(target^2); both terms are
reported raw as well (cos, mse). bf16 autocast, fp32 master weights, AdamW, warmup + cosine decay, grad clip 1.

Eval (held-out games, full boards): per-cell cosine (mean / p05 / min), MSE, and the S0 sanity row -- nearest
S0-table-row colour readback (notebooks_duck/synth_tokens/table_flashnext_v1.pt, flat rows) for the STUDENT and for
the TARGET on the same cells. The target itself reads colour badly (S0: 0.12-0.67, chance 0.06), so the student is
meant to MATCH the target's readback, not beat it. Also printed: cos(target, out_pos_bias) = what a position-only
model gets, the floor the blocks must clear.

GPU: the 5090 only (env.sh pins it; this script refuses any other visible device unless --allow-any-gpu).
CPU: torch.set_num_threads(2), prefetch THREADS (--loader-threads, default 1; no multiprocess loader).

Usage (from any cwd):
  source scripts/board_tower/env.sh && nice -n 19 $BOARD_TOWER_PY scripts/board_tower/train.py \
      --targets /media/ignaz/claude-extra/board_tower/targets --out /media/ignaz/claude-extra/board_tower/ckpt \
      --max-minutes 180 [--dim 384 --depth 8 --heads 6 --batch 8 --lr 3e-4]
"""
from __future__ import annotations

import argparse
import json
import math
import os
import pathlib
import queue
import random
import sys
import threading
import time

os.environ.setdefault("CUDA_DEVICE_ORDER", "PCI_BUS_ID")      # before torch initialises CUDA (see env.sh)
import numpy as np                                            # noqa: E402
import torch                                                  # noqa: E402
import torch.nn.functional as F                               # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.board_tower import common as C                                        # noqa: E402
from scripts.board_tower.model import BoardTower, BoardTowerConfig, load_checkpoint, save_checkpoint  # noqa: E402

S0_TABLE = ROOT / "notebooks_duck" / "synth_tokens" / "table_flashnext_v1.pt"


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def pick_device(allow_any: bool) -> torch.device:
    if not torch.cuda.is_available():
        log("WARNING: no CUDA device visible; training on CPU")
        return torch.device("cpu")
    name = torch.cuda.get_device_name(0)
    if "5090" not in name and not allow_any:
        raise SystemExit(f"REFUSING: visible CUDA device 0 is '{name}', not the 5090. Source scripts/board_tower/env.sh "
                         f"(CUDA_DEVICE_ORDER=PCI_BUS_ID, CUDA_VISIBLE_DEVICES=0) or pass --allow-any-gpu.")
    log("device:", name)
    return torch.device("cuda:0")


# ----------------------------------------------------------------------------- data
class Items:
    """Train items grouped by rows-per-board K (shards may differ in --train-cells)."""

    def __init__(self, root: pathlib.Path, manifest: dict, split: str, limit: int | None = None):
        self.root = root
        k_of = {sh["file"]: sh["cells_per_board"] for sh in manifest["shards"]}
        self.items = [(b["shard"], b["index"], k_of[b["shard"]], b["game"]) for b in C.manifest_boards(manifest, split)]
        if limit is not None:
            self.items = self.items[:limit]
        self.reader = C.ShardReader(root)

    def __len__(self):
        return len(self.items)

    def batches(self, batch: int, rng: random.Random, shuffle: bool = True):
        by_k: dict = {}
        for it in self.items:
            by_k.setdefault(it[2], []).append(it)
        out = []
        for k, its in by_k.items():
            its = list(its)
            if shuffle:
                rng.shuffle(its)
            out += [its[i:i + batch] for i in range(0, len(its), batch)]
        if shuffle:
            rng.shuffle(out)
        return out

    def load(self, batch_items, reader=None) -> dict:
        T, I, B, G = [], [], [], []
        reader = reader or self.reader
        for shard, idx, k, game in batch_items:
            t, ci, cells = reader.board(shard, idx)
            T.append(t); I.append(ci); B.append(cells); G.append(game)
        return {"targets": torch.stack(T), "cell_idx": torch.stack(I).long(), "cells": torch.stack(B), "games": G}


class Prefetcher:
    """`threads` background threads keep `depth` batches ready. One thread was enough while the 44 GB target set
    lived in the page cache; the augmented set (~350 GB) does not fit, so the loader is disk-bound and several
    readers are needed to keep the GPU fed. Each thread has its own ShardReader (the handle cache is not locked).
    With threads > 1 the batch ORDER is completion order; every batch is still consumed exactly once per epoch."""

    def __init__(self, items: Items, batch_list, depth: int = 4, threads: int = 1):
        self.q: queue.Queue = queue.Queue(maxsize=depth)
        self.n = len(batch_list)
        threads = max(1, threads)
        todo: queue.Queue = queue.Queue()
        for bl in batch_list:
            todo.put(bl)
        lock = threading.Lock(); alive = [threads]

        def work():
            reader = items.reader if threads == 1 else C.ShardReader(items.root)
            while True:
                try:
                    bl = todo.get_nowait()
                except queue.Empty:
                    break
                self.q.put(items.load(bl, reader))
            with lock:
                alive[0] -= 1
                if alive[0] == 0:
                    self.q.put(None)
        self.ts = [threading.Thread(target=work, daemon=True) for _ in range(threads)]
        for t in self.ts:
            t.start()

    def __iter__(self):
        while True:
            b = self.q.get()
            if b is None:
                return
            yield b


# ----------------------------------------------------------------------------- loss / metrics
def rows_at(pred: torch.Tensor, cell_idx: torch.Tensor) -> torch.Tensor:
    """pred (B, 4096, D), cell_idx (B, K) -> (B, K, D)."""
    return torch.gather(pred, 1, cell_idx.unsqueeze(-1).expand(-1, -1, pred.shape[-1]))


def losses(pred: torch.Tensor, tgt: torch.Tensor, mse_weight: float) -> tuple[torch.Tensor, dict]:
    pred, tgt = pred.float(), tgt.float()
    cos = F.cosine_similarity(pred, tgt, dim=-1)
    cos_loss = (1 - cos).mean()
    mse = ((pred - tgt) ** 2).mean()
    energy = (tgt ** 2).mean().clamp_min(1e-8)
    loss = cos_loss + mse_weight * mse / energy
    return loss, {"loss": loss.item(), "cos": cos.mean().item(), "mse": mse.item(), "rel_mse": (mse / energy).item()}


_S0 = None


def s0_table(device) -> torch.Tensor | None:
    global _S0
    if _S0 is None and S0_TABLE.is_file():
        d = torch.load(S0_TABLE, map_location="cpu", weights_only=False)
        _S0 = F.normalize(d["table"].float(), dim=1).to(device)      # (16, 2560) flat-square rows
    return _S0


def readback_acc(tok: torch.Tensor, cells: torch.Tensor, table: torch.Tensor) -> float:
    """Nearest-S0-row colour accuracy (S0 nearest_row_eval, flat table, uncentred). tok (N, 2560), cells (N,)."""
    S = F.normalize(tok.float(), dim=1) @ table.T
    return float((S.argmax(1) == cells.to(S.device)).float().mean())


@torch.no_grad()
def evaluate(model: BoardTower, ev: Items, device, max_boards: int | None, batch: int = 4) -> dict:
    model.eval()
    rng = random.Random(0)
    bl = ev.batches(batch, rng, shuffle=False)
    if max_boards is not None:
        # Spread the subset across ALL holdout games. `ev` is ordered by game, so the old
        # `bl[:N]` took the first N boards -- every one of them cd82. `best.pt` at BOTH shipped
        # geometries was therefore selected on a single game (findings 188), which is why the
        # familiar 0.8904 / 0.8431 pair are not comparable to each other or to anything else.
        # Fixed seed, so the subset is identical across runs and the curves stay comparable.
        random.Random(12345).shuffle(bl)
        bl = bl[:max(1, max_boards // batch)]
    tab = s0_table(device)
    if tab is not None and model.cfg.cell_patch != 1:
        # cell_idx is a TOKEN index; `cells.view(B, -1)[token]` is only that token's colour when a token is a
        # cell (cell_patch=1). At cell_patch=2 a token covers a 2x2 BLOCK, so the S0 flat-square readback would
        # need restricting to uniform blocks -- skipped rather than reported wrong.
        log(f"readback: SKIPPED (cell_patch={model.cfg.cell_patch}: a token is a "
            f"{model.cfg.cell_patch}x{model.cfg.cell_patch} cell block, not a cell)")
        tab = None
    cos_all, mse_num, en_num, n_cells = [], 0.0, 0.0, 0
    rb_student = rb_target = 0.0
    per_game: dict = {}
    pos_only = []
    for b in Prefetcher(ev, bl, depth=2):
        oh = BoardTower.onehot_from_cells(b["cells"]).to(device)
        tgt = b["targets"].to(device).float()
        ci = b["cell_idx"].to(device)
        with torch.autocast(device_type=device.type, dtype=torch.bfloat16, enabled=device.type == "cuda"):
            pred = model(oh)
        pred = rows_at(pred.float(), ci)
        cos = F.cosine_similarity(pred, tgt, dim=-1)                       # (B, K)
        cos_all.append(cos.flatten().cpu())
        mse_num += float(((pred - tgt) ** 2).sum()); en_num += float((tgt ** 2).sum()); n_cells += cos.numel()
        if model.out_pos_bias is not None:
            pb = rows_at(model.out_pos_bias.float().unsqueeze(0).expand(tgt.shape[0], -1, -1), ci)
            pos_only.append(F.cosine_similarity(pb, tgt, dim=-1).flatten().cpu())
        cells_rows = torch.gather(b["cells"].view(b["cells"].shape[0], -1).long(), 1, b["cell_idx"].long())
        for j, g in enumerate(b["games"]):
            d = per_game.setdefault(g, {"cos_sum": 0.0, "n": 0, "rb_s": 0.0, "rb_t": 0.0, "boards": 0})
            d["cos_sum"] += float(cos[j].sum()); d["n"] += cos.shape[1]; d["boards"] += 1
            if tab is not None:
                s = readback_acc(pred[j], cells_rows[j], tab); t = readback_acc(tgt[j], cells_rows[j], tab)
                d["rb_s"] += s; d["rb_t"] += t; rb_student += s; rb_target += t
    cos_all = torch.cat(cos_all)
    n_boards = sum(d["boards"] for d in per_game.values())
    res = {"n_boards": n_boards, "n_cells": n_cells, "cos_mean": float(cos_all.mean()), "cos_p05": float(cos_all.quantile(0.05)),
           "cos_min": float(cos_all.min()), "mse": mse_num / max(n_cells * C.HIDDEN, 1), "rel_mse": mse_num / max(en_num, 1e-8),
           "readback_student": rb_student / max(n_boards, 1) if tab is not None else None,
           "readback_target": rb_target / max(n_boards, 1) if tab is not None else None,
           "pos_only_cos": float(torch.cat(pos_only).mean()) if pos_only else None,
           "per_game": {g: {"boards": d["boards"], "cos": d["cos_sum"] / d["n"], "readback_student": d["rb_s"] / d["boards"],
                            "readback_target": d["rb_t"] / d["boards"]} for g, d in sorted(per_game.items())}}
    model.train()
    return res


def fmt_eval(r: dict) -> str:
    s = (f"EVAL held-out games: boards {r['n_boards']} cells {r['n_cells']} | per-cell cos mean {r['cos_mean']:.4f} "
         f"p05 {r['cos_p05']:.4f} min {r['cos_min']:.3f} | mse {r['mse']:.5f} rel {r['rel_mse']:.4f}")
    if r["pos_only_cos"] is not None:
        s += f" | position-only bias cos {r['pos_only_cos']:.4f}"
    if r["readback_student"] is not None:
        s += (f"\n     S0 nearest-row colour readback: student {r['readback_student']:.3f} vs target {r['readback_target']:.3f} "
              f"(chance 0.0625; the TARGET reads colour badly by design -- S0: 0.12-0.67 -- the student should MATCH it, not beat it)")
    s += "\n     per game: " + "  ".join(f"{g} cos {d['cos']:.4f} rb {d['readback_student']:.2f}/{d['readback_target']:.2f} (n={d['boards']})"
                                        for g, d in r["per_game"].items())
    return s


# ----------------------------------------------------------------------------- train
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--targets", default=str(C.DEFAULT_TARGET_ROOT))
    ap.add_argument("--out", default=str(C.DEFAULT_CKPT_DIR))
    ap.add_argument("--dim", type=int, default=384); ap.add_argument("--depth", type=int, default=8); ap.add_argument("--heads", type=int, default=6)
    ap.add_argument("--no-pos-bias", action="store_true"); ap.add_argument("--no-rope", action="store_true")
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--lr", type=float, default=3e-4); ap.add_argument("--wd", type=float, default=0.05)
    ap.add_argument("--warmup", type=int, default=200)
    ap.add_argument("--epochs", type=int, default=None, help="epoch bound (default 20; unbounded when --max-minutes/--max-steps is given)")
    ap.add_argument("--max-minutes", type=float, default=None)
    ap.add_argument("--max-steps", type=int, default=None)
    ap.add_argument("--mse-weight", type=float, default=1.0)
    ap.add_argument("--eval-every", type=int, default=500, help="steps")
    ap.add_argument("--eval-boards", type=int, default=64, help="boards per intermediate eval (final eval uses all)")
    ap.add_argument("--train-limit", type=int, default=None, help="use only the first N train boards -- tests")
    ap.add_argument("--log-every", type=int, default=20)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--resume", default=None, help="checkpoint to continue from")
    ap.add_argument("--allow-any-gpu", action="store_true")
    ap.add_argument("--threads", type=int, default=int(os.environ.get("BOARD_TOWER_THREADS", "2")))
    ap.add_argument("--loader-threads", type=int, default=1, help="shard-reading threads for the train loader (1 = the original single prefetch thread)")
    args = ap.parse_args()

    if args.epochs is None:
        args.epochs = 10 ** 9 if (args.max_minutes or args.max_steps) else 20
    torch.set_num_threads(args.threads)
    try:                                                      # every shard stays open (mmap); an augmented root has ~2,100
        import resource                                       # of them. Soft == hard == 1,048,576 on this host, so this is a no-op here.
        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        if soft < hard:
            resource.setrlimit(resource.RLIMIT_NOFILE, (hard, hard))
        log(f"RLIMIT_NOFILE soft {soft} -> {resource.getrlimit(resource.RLIMIT_NOFILE)[0]} (hard {hard})")
    except Exception as e:                                    # pragma: no cover
        log("could not raise RLIMIT_NOFILE:", repr(e))
    torch.manual_seed(args.seed); random.seed(args.seed); np.random.seed(args.seed)
    device = pick_device(args.allow_any_gpu)
    root = pathlib.Path(args.targets); out = pathlib.Path(args.out); out.mkdir(parents=True, exist_ok=True)
    m = C.load_manifest(root)
    if m is None:
        raise SystemExit(f"no manifest.json under {root}; run make_targets.py first")
    tr = Items(root, m, "train", args.train_limit); ev = Items(root, m, "eval")
    if len(tr) == 0 or len(ev) == 0:
        raise SystemExit(f"need train and eval boards, have {len(tr)} / {len(ev)}")
    log(f"targets {root}: train boards {len(tr)} (K per shard {sorted({it[2] for it in tr.items})}), eval boards {len(ev)} "
        f"from held-out games {m['holdout_games']}; {len(m['shards'])} shards")
    from collections import Counter
    kinds = Counter(b["kind"] for b in C.manifest_boards(m, "train")); augs = Counter(b["aug"] for b in C.manifest_boards(m, "train") if b.get("aug"))
    log(f"train boards by kind: {dict(kinds)}" + (f"; dihedral per transform: {dict(augs)}" if augs else "")
        + (f"; eval kinds: {dict(Counter(b['kind'] for b in C.manifest_boards(m, 'eval')))}"))

    px = m["config"]["px_per_cell"]
    n_tok = m["config"].get("tokens_per_board", C.n_tokens(px))
    try:
        cell_patch = C.cells_per_token_side(px)      # 1 at px=32 (a token per cell), 2 at px=16 (per 2x2 block)
    except ValueError as e:
        raise SystemExit(f"REFUSING: {e}. The student patchifies CELLS into token positions, so the token grid "
                         f"must divide the 64x64 cell grid; {px} px/cell does not (see finding 177 on px=10).")
    log(f"targets recorded at {px} px/cell -> {n_tok} tokens/board -> student cell_patch={cell_patch}")
    if args.resume:
        model, extra = load_checkpoint(args.resume, device); model.train()
        step0 = int(extra.get("step", 0))
        log(f"resumed {args.resume} at step {step0}")
    else:
        cfg = BoardTowerConfig(dim=args.dim, depth=args.depth, heads=args.heads, pos_bias=not args.no_pos_bias,
                               rope=not args.no_rope, cell_patch=cell_patch)
        model = BoardTower(cfg).to(device); step0 = 0
    if model.cfg.n_pos != n_tok:                     # a 4096-position student cannot be fed 1024-token targets
        raise SystemExit(f"REFUSING: the student emits {model.cfg.n_pos} positions (cell_patch={model.cfg.cell_patch}) "
                         f"but {root} holds {n_tok} tokens/board ({px} px/cell)")
    pc = model.count_params()
    log(f"student {model.cfg} params {pc['total']:,} (blocks {pc['blocks']:,}, out_pos_bias {pc['out_pos_bias']:,})")

    decay = [p for n, p in model.named_parameters() if p.ndim >= 2 and "pos" not in n]
    no_decay = [p for n, p in model.named_parameters() if not (p.ndim >= 2 and "pos" not in n)]
    opt = torch.optim.AdamW([{"params": decay, "weight_decay": args.wd}, {"params": no_decay, "weight_decay": 0.0}],
                            lr=args.lr, betas=(0.9, 0.95))
    rng = random.Random(args.seed)
    steps_per_epoch = math.ceil(len(tr) / args.batch)
    total_steps = args.max_steps or min(steps_per_epoch * args.epochs, 10 ** 9)
    if args.max_minutes and not args.max_steps:
        # cosine schedule needs a horizon: estimate steps from the measured step time after warmup (see below)
        total_steps = None

    horizon = {"steps": total_steps}

    def lr_at(step):
        if step < args.warmup:
            return args.lr * (step + 1) / args.warmup
        if horizon["steps"] is None:
            # TIME budget: drive the cosine off elapsed time directly.
            #
            # This used to estimate a STEP horizon by sampling the rate once at warmup+50 and
            # extrapolating. That sample lands in the cold first epoch, while shards are being
            # read off the USB HDD for the first time, so the rate came out 6-10x low and the
            # horizon with it -- p reached 1.0 almost immediately and the LR sat on its 5% floor
            # for most of the run (findings 188: 76% of the px4 run, 84% of px16, 90% of n800).
            # The arm-B student therefore came from a ~30-minute effective run, not 180.
            #
            # Elapsed time is the budget, so use it. No estimate, nothing to get wrong, and it
            # self-corrects if the rate changes mid-run (which is exactly what it does).
            p = min(1.0, (time.time() - t_start) / max(1e-6, args.max_minutes * 60.0))
        else:
            p = min(1.0, (step - args.warmup) / max(1, horizon["steps"] - args.warmup))
        return args.lr * (0.05 + 0.95 * 0.5 * (1 + math.cos(math.pi * p)))

    metrics = open(out / "metrics.jsonl", "a")
    t_start = time.time(); step = step0; best = -1.0; stop = False
    curve = []

    def do_eval(final: bool):
        nonlocal best
        r = evaluate(model, ev, device, None if final else args.eval_boards)
        r.update(step=step, minutes=round((time.time() - t_start) / 60, 2), final=final)
        log(fmt_eval(r)); metrics.write(json.dumps({"eval": r}) + "\n"); metrics.flush()
        extra = {"step": step, "eval": r, "args": vars(args), "targets": str(root), "holdout_games": m["holdout_games"], "params": pc}
        save_checkpoint(out / "last.pt", model, extra)
        if r["cos_mean"] > best:
            best = r["cos_mean"]; save_checkpoint(out / "best.pt", model, extra)
        return r

    for epoch in range(args.epochs):
        bl = tr.batches(args.batch, rng)
        t_wait = 0.0; t_step = time.time()
        for b in Prefetcher(tr, bl, depth=max(4, 2 * args.loader_threads), threads=args.loader_threads):
            t0 = time.time(); t_wait += t0 - t_step
            oh = BoardTower.onehot_from_cells(b["cells"]).to(device, non_blocking=True)
            tgt = b["targets"].to(device, non_blocking=True); ci = b["cell_idx"].to(device, non_blocking=True)
            for g in opt.param_groups:
                g["lr"] = lr_at(step)
            with torch.autocast(device_type=device.type, dtype=torch.bfloat16, enabled=device.type == "cuda"):
                pred = model(oh)
            loss, st = losses(rows_at(pred.float(), ci), tgt, args.mse_weight)
            opt.zero_grad(set_to_none=True); loss.backward()
            gn = float(torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0))
            opt.step(); step += 1
            t_step = time.time()
            if step % args.log_every == 0 or step == 1:
                st.update(step=step, epoch=epoch, lr=lr_at(step), grad_norm=gn, minutes=round((time.time() - t_start) / 60, 2),
                          data_wait_s=round(t_wait, 1))
                curve.append(st); metrics.write(json.dumps({"train": st}) + "\n"); metrics.flush()
                log(f"step {step} ep {epoch} loss {st['loss']:.4f} cos {st['cos']:.4f} mse {st['mse']:.5f} rel {st['rel_mse']:.4f} "
                    f"lr {st['lr']:.2e} gn {gn:.2f} | {st['minutes']} min, data-wait {t_wait:.0f}s")
            if args.eval_every and step % args.eval_every == 0:
                do_eval(final=False)
            if (args.max_minutes and (time.time() - t_start) / 60 >= args.max_minutes) or (args.max_steps and step >= args.max_steps):
                stop = True; break
        if stop:
            break
    r = do_eval(final=True)
    summary = {"steps": step, "epochs_started": epoch + 1, "minutes": round((time.time() - t_start) / 60, 2), "params": pc,
               "config": model.cfg.to_dict(), "train_boards": len(tr), "eval_boards": len(ev), "holdout_games": m["holdout_games"],
               "final_eval": r, "best_cos": best, "curve": curve, "out": str(out)}
    json.dump(summary, open(out / "summary.json", "w"), indent=1)
    log(f"done: {step} steps in {summary['minutes']} min; best eval cos {best:.4f}; checkpoints {out}/best.pt, last.pt")


if __name__ == "__main__":
    main()
