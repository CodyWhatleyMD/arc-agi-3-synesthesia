#!/usr/bin/env python3
"""Board-tower distillation targets (plan S2c, 2026-10-03): every recorded ARC board through Flash-Next's FULL
vision tower at --px-per-cell px/cell, stored as bf16 (K, 2560) token matrices (or a fixed random subset of
rows for train boards, --train-cells), split by GAME.

K = common.n_tokens(px) = (2*px)**2: 4096 at px=32 (one token per CELL), 1024 at px=16 (one token per 2x2
CELL BLOCK -- the distillation target chosen in finding 177), 400 at px=10, 256 at px=8. The board always has
4096 cells; only px=32 makes cells and tokens the same thing.

Two phases, because the custom games need `arcengine` (host .mlvenv) and the tower needs the serving image:

  enumerate   (host)      runs/**/artifacts/*_events.jsonl -> unique 64x64 boards (sha1 over the uint8 cells),
                          + the initial frame of every level of every game under games_custom/environment_files
                          (rendered by the engine; a game that fails to load is skipped and named),
                          -> per-game stratified caps -> boards.npz + boards.json under the target root.
                          Holdout: 5 of the 25 public games (seeded shuffle of the sorted ids), whole games.
  augment     (host)      a RECORDED root -> a new root with the same boards (shards symlinked, manifest entries
                          copied verbatim, so the held-out eval targets are byte-identical) plus the 7 non-identity
                          dihedral transforms (common.DIHEDRAL) of every TRAIN board as new boards to record. The
                          teacher is NOT equivariant under D4, so the transformed boards go through `record` like
                          any other board; nothing is derived from the originals' embeddings. Held-out boards are
                          never transformed. Then `record --resume` on the new root records only the added boards.
  record      (docker)    boards.npz -> render (palette.py, --px-per-cell px/cell) -> the full tower (s0_record_table's
                          build_tower / load_visual_weights / hf_patchify / tower_tokens, NOT re-implemented; the
                          patchifier is checked against the image's real processor and the first board is
                          cross-checked against transformers' Qwen3VLVisionModel, as in S0)
                          -> train_NNNN / eval_NNNN .safetensors shards + manifest.json. Resumable.

Run `record` through scripts/board_tower/run_record_docker.sh (GPU 0, nice 19, --cpus cap).
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import importlib.util
import json
import os
import pathlib
import random
import re
import sys
import time

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from notebooks_duck.synth_tokens.palette import engine_rgb, engine_root, palette_sha, render_board_array  # noqa: E402
from scripts.board_tower import common as C  # noqa: E402

_LEVEL_RE = re.compile(r'"level":\s*(\d+|null)')


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


# ============================================================================= phase 1: enumerate
def scan_events(runs_root: pathlib.Path) -> tuple[dict, dict]:
    """sha1 -> {cells, game, level, file, line}; plus per-game event counts. One pass, boards parsed from the
    JSON slice only (the lines are ~16 KB each, 98k of them)."""
    files = sorted(glob.glob(str(runs_root / "*" / "artifacts" / "*_events.jsonl")))
    if not files:
        raise SystemExit(f"no events files under {runs_root}")
    boards: dict = {}
    events = {}
    for f in files:
        game = os.path.basename(f)[:4]
        with open(f) as fh:
            for ln, line in enumerate(fh):
                i = line.find('"board":')
                if i < 0:
                    continue
                j = line.find("]]", i)
                if j < 0:
                    continue
                events[game] = events.get(game, 0) + 1
                b = np.asarray(json.loads(line[i + 8:j + 2]), dtype=np.int64)
                if b.shape != (64, 64) or b.min() < 0 or b.max() > 15:
                    continue
                cells = b.astype(np.uint8)
                h = C.board_sha1(cells)
                if h in boards:
                    continue
                m = _LEVEL_RE.search(line)
                lvl = int(m.group(1)) if m and m.group(1) != "null" else None
                boards[h] = {"cells": cells, "game": game, "level": lvl, "kind": "event",
                             "source": os.path.relpath(f, runs_root), "line": ln}
    return boards, events


def custom_game_ids(custom_root: pathlib.Path) -> list[str]:
    envs = custom_root / "environment_files"
    return sorted(p.name for p in envs.iterdir() if p.is_dir() and list(p.glob("*/*.py"))) if envs.is_dir() else []


def custom_initial_frames(custom_root: pathlib.Path) -> tuple[dict, list[str], list[str]]:
    """Initial frame of every level of every custom game, via the engine (the way games_custom/solutions/_harness.py
    loads a game). Returns boards, games rendered, games skipped (with the reason)."""
    boards, done, skipped = {}, [], []
    ids = custom_game_ids(custom_root)
    if not ids:
        return boards, done, [f"no games under {custom_root / 'environment_files'}"]
    try:
        from arcengine import ActionInput, GameAction
    except Exception as e:  # pragma: no cover
        return boards, done, [f"arcengine not importable ({e!r}); run enumerate with the repo .mlvenv"]
    envs = custom_root / "environment_files"
    for gid in ids:
        try:
            src = sorted(envs.glob(f"{gid}/*/{gid}.py"))[-1]
            spec = importlib.util.spec_from_loader(f"custom_{gid}", loader=None)
            module = importlib.util.module_from_spec(spec)
            module.__dict__["__file__"] = str(src)
            exec(src.read_text(encoding="utf-8"), module.__dict__)
            cls = module.__dict__[gid[0].upper() + gid[1:4]]
            g = cls()
            g.perform_action(ActionInput(id=GameAction.RESET))
            n_levels = len(g._levels)
            n_new = 0
            for li in range(n_levels):
                g = cls()
                g.perform_action(ActionInput(id=GameAction.RESET))      # full reset: level 0
                g.set_level(li)
                g._action_count = 1       # arcengine.handle_reset: count 0 -> full_reset (back to level 0); else level_reset
                fd = g.perform_action(ActionInput(id=GameAction.RESET))  # -> level_reset(li): the level's initial frame
                assert g._current_level_index == li, (gid, g._current_level_index, li)
                b = np.asarray(fd.frame[-1], dtype=np.int64)
                if b.shape != (64, 64) or b.min() < 0 or b.max() > 15:
                    raise ValueError(f"level {li + 1} frame shape {b.shape} / values [{b.min()},{b.max()}]")
                cells = b.astype(np.uint8)
                h = C.board_sha1(cells)
                if h not in boards:
                    boards[h] = {"cells": cells, "game": gid, "level": li + 1, "kind": "custom_initial",
                                 "source": os.path.relpath(src, custom_root), "line": None}
                    n_new += 1
            done.append(f"{gid}:{n_levels}L/{n_new}")
        except Exception as e:
            skipped.append(f"{gid}: {type(e).__name__}: {str(e)[:120]}")
    return boards, done, skipped


def enumerate_boards(args) -> int:
    t0 = time.time()
    root = engine_root()
    runs_root = pathlib.Path(args.runs_root or (root / "runs"))
    custom_root = pathlib.Path(args.custom_root or (root / "games_custom"))
    out = pathlib.Path(args.out); out.mkdir(parents=True, exist_ok=True)
    ev_boards, events = scan_events(runs_root)
    log(f"events: {sum(events.values())} lines, {len(ev_boards)} unique boards, {len(events)} games, {time.time() - t0:.1f}s")
    custom_ids = set(custom_game_ids(custom_root))
    cu_boards, cu_done, cu_skipped = ({}, [], ["--no-custom"]) if args.no_custom else custom_initial_frames(custom_root)
    log(f"custom initial frames: {len(cu_boards)} boards from {len(cu_done)} games; skipped {len(cu_skipped)}: {cu_skipped}")
    for h, b in cu_boards.items():
        ev_boards.setdefault(h, b)          # an initial frame already seen in runs/ keeps its event provenance
    public = sorted(g for g in events if g not in custom_ids)
    if len(public) != 25:
        log(f"WARNING: {len(public)} public games in runs/ (expected 25): {public}")
    holdout = args.holdout.split(",") if args.holdout else C.choose_holdout(public, args.seed)
    log("holdout games (eval, whole games):", holdout)

    by_game: dict = {}
    for h, b in ev_boards.items():
        by_game.setdefault(b["game"], []).append(dict(b, sha1=h))
    chosen: list[dict] = []
    per_game_counts = {}
    for game in sorted(by_game):
        items = sorted(by_game[game], key=lambda x: x["sha1"])
        is_eval = game in holdout
        cap = args.eval_per_game if is_eval else args.per_game
        picked = C.stratified_cap(items, cap, seed=args.seed + sum(map(ord, game)))
        for it in picked:
            it["split"] = "eval" if is_eval else "train"
        per_game_counts[game] = {"unique": len(items), "picked": len(picked), "split": "eval" if is_eval else "train",
                                 "custom": game in custom_ids}
        chosen += picked
    if args.max is not None and len(chosen) > args.max:
        # round-robin over games so a small smoke covers several games and both splits
        rr: dict = {}
        for it in chosen:
            rr.setdefault(it["game"], []).append(it)
        games = sorted(rr, key=lambda g: (rr[g][0]["split"] != "eval", g))      # eval games first in the cycle
        chosen = []
        while len(chosen) < args.max and any(rr.values()):
            for g in games:
                if rr[g] and len(chosen) < args.max:
                    chosen.append(rr[g].pop(0))
    chosen.sort(key=lambda x: (x["split"] != "eval", x["game"], x["sha1"]))     # eval first: usable before train finishes
    cells = np.stack([it["cells"] for it in chosen]).astype(np.uint8)
    np.savez_compressed(out / "boards.npz", cells=cells)
    meta = {"created": C.now(), "runs_root": str(runs_root), "custom_root": str(custom_root),
            "events_per_game": events, "n_unique_event_boards": len(ev_boards) - len([h for h in cu_boards if h not in ev_boards or ev_boards[h]["kind"] != "event"]),
            "custom_games_rendered": cu_done, "custom_games_skipped": cu_skipped,
            "public_games": public, "holdout_games": holdout, "custom_game_ids": sorted(custom_ids),
            "caps": {"per_game": args.per_game, "eval_per_game": args.eval_per_game, "max": args.max, "seed": args.seed},
            "per_game": per_game_counts,
            "n_boards": len(chosen), "n_train": sum(1 for it in chosen if it["split"] == "train"),
            "n_eval": sum(1 for it in chosen if it["split"] == "eval"),
            "boards": [{k: v for k, v in it.items() if k != "cells"} for it in chosen]}
    json.dump(meta, open(out / "boards.json", "w"), indent=1)
    log(f"wrote {out / 'boards.npz'} ({len(chosen)} boards: train {meta['n_train']}, eval {meta['n_eval']}) and boards.json; "
        f"{time.time() - t0:.1f}s")
    return 0


# ============================================================================= phase 1b: augment (host)
def augment(args) -> int:
    """SRC (recorded) -> OUT: every source board and shard kept (symlinks + verbatim manifest entries), the D4
    transforms of every TRAIN board appended to boards.npz/boards.json for `record --resume` to pick up."""
    import shutil
    t0 = time.time()
    src = pathlib.Path(args.src).resolve(); out = pathlib.Path(args.out)
    names = [n.strip() for n in args.transforms.split(",") if n.strip()]
    bad = [n for n in names if n not in C.DIHEDRAL_NON_IDENTITY]
    if bad or len(set(names)) != len(names):
        raise SystemExit(f"--transforms must be distinct names from {C.DIHEDRAL_NON_IDENTITY}, got {names}")
    m_src = C.load_manifest(src)
    if m_src is None:
        raise SystemExit(f"no manifest.json under {src}: the source must be a RECORDED target root")
    meta_src = json.load(open(src / "boards.json"))
    cells_src = np.load(src / "boards.npz")["cells"]
    assert cells_src.shape[0] == meta_src["n_boards"] == len(meta_src["boards"]), (cells_src.shape, meta_src["n_boards"])
    recorded = {b["sha1"] for b in m_src["boards"]}
    not_rec = [b["sha1"] for b in meta_src["boards"] if b["sha1"] not in recorded]
    if not_rec:
        raise SystemExit(f"{len(not_rec)} boards of {src} are not recorded yet (e.g. {not_rec[0]}); finish the source first")
    if out.resolve() == src:
        raise SystemExit("--out must differ from --src")
    out.mkdir(parents=True, exist_ok=True)
    if (out / "manifest.json").is_file() and not args.force:
        raise SystemExit(f"{out}/manifest.json exists; pass --force to rebuild (shards already recorded there are NOT removed)")

    # the source shards, by absolute symlink (the new root reads them through its own dir, as any shard)
    for sh in m_src["shards"]:
        link = out / sh["file"]; target = src / sh["file"]
        if not target.is_file():
            raise SystemExit(f"source shard missing: {target}")
        if link.is_symlink() or link.exists():
            link.unlink()
        link.symlink_to(target)
        if link.resolve() != target.resolve() or os.path.getsize(link) != sh["bytes"]:
            raise SystemExit(f"symlink check failed for {link}")

    seen = set(recorded)
    counts = {n: 0 for n in names}
    skipped = {"equals_existing_board": 0, "equals_earlier_transform": 0}
    new_boards, new_cells = [], []
    n_src_train = 0
    for i, b in enumerate(meta_src["boards"]):
        if b["split"] != "train":
            continue
        n_src_train += 1
        if args.max is not None and len(new_boards) >= args.max:
            continue
        base = cells_src[i]
        for n in names:
            t = C.dihedral(base, n); h = C.board_sha1(t)
            if h in recorded:                       # a symmetric board, or a transform that is some other recorded board
                skipped["equals_existing_board"] += 1; continue
            if h in seen:                           # two transforms of this board coincide (e.g. flip_h == rot180 on a flip_v-symmetric board)
                skipped["equals_earlier_transform"] += 1; continue
            seen.add(h)
            new_boards.append({"sha1": h, "game": b["game"], "level": b["level"], "kind": "dihedral", "aug": n,
                               "parent_sha1": b["sha1"], "source": b["source"], "line": b["line"], "split": "train"})
            new_cells.append(t); counts[n] += 1
    if not new_boards:
        raise SystemExit("nothing to add")
    cells = np.concatenate([cells_src, np.stack(new_cells).astype(np.uint8)])
    np.savez_compressed(out / "boards.npz", cells=cells)
    aug = {"created": C.now(), "source_root": str(src), "source_manifest_created": m_src.get("created"),
           "transforms": names, "n_source_boards": len(meta_src["boards"]), "n_source_train": n_src_train,
           "n_source_eval": sum(1 for b in meta_src["boards"] if b["split"] == "eval"),
           "n_added": len(new_boards), "per_transform": counts, "skipped": skipped, "max": args.max,
           "shards_symlinked": len(m_src["shards"]),
           "note": "held-out (eval) boards untransformed and unchanged; added boards are kind=dihedral with aug + parent_sha1"}
    meta = dict(meta_src)
    meta["boards"] = meta_src["boards"] + new_boards
    meta["n_boards"] = len(meta["boards"]); meta["n_train"] = meta_src["n_train"] + len(new_boards); meta["n_eval"] = meta_src["n_eval"]
    meta["augmentation"] = aug
    json.dump(meta, open(out / "boards.json", "w"), indent=1)
    m = json.loads(json.dumps(m_src))               # boards + shards + config verbatim: the eval set is the same set
    m["augmentation"] = aug
    m["recorder_source"] = m_src.get("recorder", {})   # provenance of the symlinked shards
    m["recorder"] = {}                                 # filled by this root's own `record` run
    m["created"] = C.now()
    C.save_manifest(out, m)
    est_gib = len(new_boards) * m["config"]["tokens_per_board"] * C.HIDDEN * 2 / 2**30
    free_gib = shutil.disk_usage(out).free / 2**30
    log(f"augment: {n_src_train} train boards x {len(names)} transforms -> {len(new_boards)} new boards "
        f"({counts}; skipped {skipped}); eval boards {meta['n_eval']} unchanged; {len(m_src['shards'])} shards symlinked; "
        f"to record: ~{est_gib:.1f} GiB at full rows (free on {out}: {free_gib:.1f} GiB); {time.time() - t0:.1f}s")
    return 0


# ============================================================================= phase 2: record (docker, GPU 0)
def record(args) -> int:
    import torch
    torch.set_num_threads(int(os.environ.get("BOARD_TOWER_THREADS", "2")))
    from notebooks_duck.synth_tokens import s0_record_table as s0
    assert (s0.PATCH, s0.MERGE) == (C.PATCH, C.MERGE), (s0.PATCH, s0.MERGE, C.PATCH, C.MERGE)
    px = args.px_per_cell                       # NOT C.PX: the manifest must say what was actually recorded
    n_tok = C.n_tokens(px)                      # teacher tokens per board == rows in a full target matrix
    if args.train_cells is None:
        args.train_cells = n_tok                # default: keep every token row (no subsetting)
    if not 0 < args.train_cells <= n_tok:
        raise SystemExit(f"--train-cells {args.train_cells} out of range: {px} px/cell gives {n_tok} tokens/board")
    t0 = time.time()
    root = pathlib.Path(args.out)
    meta = json.load(open(root / "boards.json"))
    cells_all = np.load(root / "boards.npz")["cells"]
    assert cells_all.shape[0] == meta["n_boards"], (cells_all.shape, meta["n_boards"])
    rgb = engine_rgb()
    m = C.load_manifest(root) if args.resume else None
    if m is not None and m["config"].get("px_per_cell") != px:
        raise SystemExit(f"FATAL: {root}/manifest.json was recorded at {m['config'].get('px_per_cell')} px/cell but "
                         f"--px-per-cell is {px}: resuming would mix resolutions inside one target set")
    if m is None:
        try:
            cps = C.cells_per_token_side(px)    # None when the token grid does not divide the cell grid (px=10)
        except ValueError:
            cps = None
        m = {"created": C.now(), "config": {"px_per_cell": px, "tokens_per_board": n_tok, "cells_per_token_side": cps,
                                            "patch": s0.PATCH, "merge": s0.MERGE, "hidden": C.HIDDEN,
                                            "train_cells": args.train_cells, "shard_boards": args.shard_boards,
                                            "batch": args.batch, "cell_subset_seed": "sha1(board) -> random.Random"},
             "holdout_games": meta["holdout_games"], "public_games": meta["public_games"],
             "custom_games_rendered": meta["custom_games_rendered"], "custom_games_skipped": meta["custom_games_skipped"],
             "caps": meta["caps"], "per_game": meta["per_game"], "palette_sha256": palette_sha(rgb),
             "boards": [], "shards": [], "recorder": {}}
    if m["config"].get("train_cells") != args.train_cells:
        m["config"].setdefault("train_cells_by_run", []).append({"train_cells": args.train_cells, "from_board": len(m["boards"]), "at": C.now()})
        log(f"NOTE: this run keeps {args.train_cells} rows per train board; the manifest's earlier runs kept {m['config'].get('train_cells')}")
    done = {b["sha1"] for b in m["boards"]}
    todo = [i for i, b in enumerate(meta["boards"]) if b["sha1"] not in done]
    if args.max is not None:
        todo = todo[:args.max]
    log(f"{len(todo)} boards to record ({len(done)} already in the manifest); {px} px/cell -> {n_tok} tokens/board; "
        f"train_cells={args.train_cells} batch={args.batch}")
    if not todo:
        return 0

    # --- tower, exactly as S0 (patchify check against the real processor on the first board)
    first_img = render_board_array(cells_all[todo[0]], rgb, px)
    patch_check = s0.check_patchify_against_hf(args.ckpt, first_img)
    log("patchify vs HF processor:", patch_check)
    grid_tok = patch_check["hf_grid"][1] * patch_check["hf_grid"][2] // (s0.MERGE * s0.MERGE)
    if grid_tok != n_tok:                       # the REAL processor's grid, not our arithmetic, has the last word
        raise SystemExit(f"FATAL: the HF processor's grid {patch_check['hf_grid']} gives {grid_tok} tokens/board, "
                         f"not the {n_tok} computed for {px} px/cell")
    from vllm.config import VllmConfig, set_current_vllm_config
    ctx = set_current_vllm_config(VllmConfig()); ctx.__enter__()
    tower, cfg = s0.build_tower(args.ckpt, args.device)
    wl = s0.load_visual_weights(tower, args.ckpt)
    log("weights:", {k: v for k, v in wl.items() if k != "shards"})
    rec = m["recorder"]
    rec.update({"checkpoint": args.ckpt, "weights": wl, "patchify_check": patch_check,
                "attn_backend": str(tower.attn_backend), "dtype": str(tower.dtype),
                "runtime": {"torch": torch.__version__, "cuda": torch.version.cuda, "gpu": torch.cuda.get_device_name(0),
                            "vllm": __import__("vllm").__version__, "transformers": __import__("transformers").__version__,
                            "docker_image_id": os.environ.get("S0_IMAGE_ID"), "git_sha_worktree": os.environ.get("S0_GIT_SHA")},
                "tower": "vllm Qwen3_VisionTransformer via s0_record_table.build_tower (quant_config=None, as the engine)"})

    @torch.no_grad()
    def tower_batch(idx: list[int]) -> torch.Tensor:
        """(len(idx), n_tok, 2560) float32 on CPU. Several boards per forward: the tower takes concatenated
        patches + one grid per image (varlen attention per image, as the engine batches images)."""
        patches, grids = [], []
        for i in idx:
            pt, g = s0.hf_patchify(render_board_array(cells_all[i], rgb, px))
            patches.append(pt); grids.append(g)
        x = torch.cat(patches).to(tower.device, tower.dtype)
        out = tower(x, grids)
        assert out.shape == (len(idx) * n_tok, C.HIDDEN), (out.shape, len(idx), n_tok)
        return out.view(len(idx), n_tok, C.HIDDEN).float().cpu()

    # --- consistency: batch-of-1 vs batch-of-B must agree (varlen path), and HF cross-check on the first board
    if len(todo) >= 2:
        # the teacher's own noise floor: the same board alone vs. in a 2-image varlen batch (bf16 kernel order;
        # S0 saw the same between vLLM and HF: mean 0.997, a few tokens down to 0.83). Recorded, not a gate on
        # the min; a student cannot be expected to beat this per-token.
        a = tower_batch(todo[:1])[0]; b = tower_batch(todo[:2])[0]
        cs = torch.nn.functional.cosine_similarity(a, b, dim=1)
        rec["batch_consistency"] = {"cos_min": float(cs.min()), "cos_p05": float(cs.quantile(0.05)), "cos_mean": float(cs.mean()),
                                    "max_abs_diff": float((a - b).abs().max()), "recorded_with_batch": args.batch}
        log("teacher noise floor, batch-of-1 vs batch-of-2 on the same board:", rec["batch_consistency"])
        if rec["batch_consistency"]["cos_mean"] < 0.995:
            raise SystemExit("FATAL: batched tower output differs from the single-image output beyond kernel noise")
    if args.hf_check:
        try:
            hf = s0.hf_crosscheck(args.ckpt, cfg, tower, {"board0": first_img})
            rec["hf_crosscheck"] = hf
            log("HF cross-check (transformers Qwen3VLVisionModel, same weights):", hf.get("cases"))
        except Exception as e:
            rec["hf_crosscheck"] = {"error": repr(e)}
            log("HF cross-check FAILED:", repr(e))

    # --- record
    buf = {"train": [], "eval": []}
    next_shard = {s: 1 + max([int(sh["file"].split("_")[1].split(".")[0]) for sh in m["shards"] if sh["file"].startswith(s)] or [-1])
                  for s in buf}
    t_tower = 0.0; n_done = 0; t_start = time.time()

    import shutil

    def wait_free_space():
        """Someone may be making room on the disk while this runs: wait rather than die on ENOSPC."""
        waited = 0
        while shutil.disk_usage(root).free < args.min_free_gib * 2**30:
            if waited % 600 == 0:
                log(f"free space on {root} is {shutil.disk_usage(root).free / 2**30:.1f} GiB < --min-free-gib {args.min_free_gib}: waiting")
            time.sleep(30); waited += 30

    def flush(split: str, force: bool = False):
        nonlocal n_done
        while buf[split] and (force or len(buf[split]) >= args.shard_boards):
            wait_free_space()
            chunk, buf[split] = buf[split][:args.shard_boards], buf[split][args.shard_boards:]
            name = C.shard_name(split, next_shard[split]); next_shard[split] += 1
            T = torch.stack([c["targets"] for c in chunk]); I = torch.stack([c["cell_idx"] for c in chunk])
            B = torch.from_numpy(np.stack([c["cells"] for c in chunk]))
            sh = C.write_shard(root / name, T, I, B)
            sh["split"] = split
            m["shards"].append(sh)
            for j, c in enumerate(chunk):
                e = {"sha1": c["sha1"], "game": c["game"], "level": c["level"], "split": split, "kind": c["kind"],
                     "source": c["source"], "line": c["line"], "shard": name, "index": j}
                if c.get("aug"):
                    e["aug"] = c["aug"]; e["parent_sha1"] = c["parent_sha1"]
                m["boards"].append(e)
            n_done += len(chunk)
            rec["boards_recorded"] = len(m["boards"]); rec["boards_recorded_this_run"] = n_done; rec["seconds_tower"] = round(t_tower, 1)
            rec["rate_boards_per_s_tower"] = round(n_done / t_tower, 3) if t_tower else None
            rec["rate_boards_per_s_wall"] = round(n_done / (time.time() - t_start), 3)
            rec["updated"] = C.now()
            C.save_manifest(root, m)
            log(f"shard {name}: {len(chunk)} boards ({sh['bytes'] / 2**20:.0f} MiB); total {len(m['boards'])}; "
                f"tower {rec['rate_boards_per_s_tower']} boards/s, wall {rec['rate_boards_per_s_wall']} boards/s")

    for s in range(0, len(todo), args.batch):
        idx = todo[s:s + args.batch]
        t1 = time.time(); toks = tower_batch(idx); torch.cuda.synchronize(); t_tower += time.time() - t1
        for j, i in enumerate(idx):
            b = meta["boards"][i]
            full = toks[j]
            if b["split"] == "train" and args.train_cells < n_tok:
                rng = random.Random(int(b["sha1"][:12], 16))
                ci = sorted(rng.sample(range(n_tok), args.train_cells))
                sel = torch.tensor(ci, dtype=torch.long)
            else:
                sel = torch.arange(n_tok)
            buf[b["split"]].append({"sha1": b["sha1"], "game": b["game"], "level": b["level"], "kind": b["kind"],
                                    "source": b["source"], "line": b["line"], "aug": b.get("aug"), "parent_sha1": b.get("parent_sha1"),
                                    "targets": full[sel].to(torch.bfloat16), "cell_idx": sel.to(torch.int16),
                                    "cells": cells_all[i]})
            flush(b["split"])
    for s in buf:
        flush(s, force=True)
    rec["finished"] = C.now(); rec["seconds_total"] = round(time.time() - t0, 1)
    C.save_manifest(root, m)
    log(f"done: {len(m['boards'])} boards in manifest, {len(m['shards'])} shards, "
        f"{sum(sh['bytes'] for sh in m['shards']) / 2**30:.2f} GiB; tower {rec['rate_boards_per_s_tower']} boards/s; total {rec['seconds_total']}s")
    ctx.__exit__(None, None, None)
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("enumerate", help="host: events + custom games -> boards.npz/json")
    e.add_argument("--out", default=str(C.DEFAULT_TARGET_ROOT))
    e.add_argument("--runs-root", default=None, help="default <engine root>/runs")
    e.add_argument("--custom-root", default=None, help="default <engine root>/games_custom")
    e.add_argument("--per-game", type=int, default=None, help="cap per TRAIN game, stratified by level")
    e.add_argument("--eval-per-game", type=int, default=None, help="cap per HOLDOUT game")
    e.add_argument("--max", type=int, default=None, help="total cap (round-robin over games) -- tests")
    e.add_argument("--holdout", default=None, help="comma-separated game ids; default seeded choice of 5 public games")
    e.add_argument("--seed", type=int, default=C.HOLDOUT_SEED)
    e.add_argument("--no-custom", action="store_true")
    a = sub.add_parser("augment", help="host: a recorded root -> a new root with the D4 transforms of every train board added")
    a.add_argument("--src", required=True, help="a RECORDED target root (manifest.json present)")
    a.add_argument("--out", required=True)
    a.add_argument("--transforms", default=",".join(C.DIHEDRAL_NON_IDENTITY),
                   help=f"comma-separated D4 elements to add per train board; default all 7: {','.join(C.DIHEDRAL_NON_IDENTITY)}")
    a.add_argument("--max", type=int, default=None, help="add at most this many boards -- tests")
    a.add_argument("--force", action="store_true", help="rebuild boards.npz/json + manifest in an existing --out")
    r = sub.add_parser("record", help="docker GPU 0: boards.npz -> shards + manifest")
    r.add_argument("--out", default="/targets")
    r.add_argument("--ckpt", default="/model")
    r.add_argument("--device", default="cuda:0")
    r.add_argument("--batch", type=int, default=1, help="boards per tower forward (1 = S0's single-image path)")
    r.add_argument("--shard-boards", type=int, default=32)
    r.add_argument("--px-per-cell", type=int, default=C.PX,
                   help=f"px per cell at render time -> (2*px)**2 teacher tokens per board; default {C.PX} "
                        f"({C.n_tokens()} tokens, one per cell). 16 = {C.n_tokens(16)} tokens (finding 177's target)")
    r.add_argument("--train-cells", type=int, default=None, help="token rows kept per TRAIN board (random fixed "
                   "subset); default ALL of them, i.e. n_tokens(px); eval boards are always full")
    r.add_argument("--max", type=int, default=None, help="record at most this many boards -- tests")
    r.add_argument("--resume", action="store_true")
    r.add_argument("--no-hf-check", dest="hf_check", action="store_false")
    r.add_argument("--min-free-gib", type=float, default=8.0, help="wait (not die) while the target disk has less free space than this")
    args = ap.parse_args()
    sys.exit({"enumerate": enumerate_boards, "augment": augment, "record": record}[args.cmd](args))


if __name__ == "__main__":
    main()
