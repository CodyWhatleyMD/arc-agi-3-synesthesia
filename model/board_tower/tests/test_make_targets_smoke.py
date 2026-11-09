"""20-board smoke of make_targets: enumerate on the host (.mlvenv, events + custom games), record inside the serving
image on nvidia-smi GPU 0 (the 5090). Asserts: 20 boards from >= 4 games incl. >= 2 held-out games, shards + manifest,
every target (K or 4096, 2560) bf16 finite, cell_idx ascending, the patchify check and the HF cross-check recorded,
the recording rate printed. ~3-4 min (image start + 0.9 GB tower load + 20 boards).
Run: python scripts/board_tower/tests/test_make_targets_smoke.py   (waits while 1-min load > 8)"""
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _common import PY, TEST_DIR, WT, run, wait_load  # noqa: E402

sys.path.insert(0, str(WT))
import torch                                        # noqa: E402
from safetensors import safe_open                   # noqa: E402

targets = TEST_DIR / "targets20"
targets.mkdir(parents=True, exist_ok=True)
wait_load()
rc, out, log = run([PY, WT / "scripts/board_tower/make_targets.py", "enumerate", "--out", targets, "--max", "20"], "enumerate.log", timeout=900)
assert rc == 0, f"enumerate failed, see {log}\n{out[-2000:]}"
meta = json.load(open(targets / "boards.json"))
assert meta["n_boards"] == 20 and meta["n_eval"] >= 2 and meta["n_train"] >= 2, (meta["n_boards"], meta["n_train"], meta["n_eval"])
assert len(meta["holdout_games"]) == 5 and len(meta["public_games"]) == 25, (meta["holdout_games"], len(meta["public_games"]))
games = {b["game"] for b in meta["boards"]}
assert len(games) >= 4, games
assert len(meta["custom_games_rendered"]) >= 20, meta["custom_games_rendered"]
print("enumerate:", f"{meta['n_boards']} boards from {len(games)} games; holdout {meta['holdout_games']}; custom rendered "
      f"{len(meta['custom_games_rendered'])} games, skipped {meta['custom_games_skipped']}")

wait_load()
env_extra = {"TARGETS": str(targets), "GPU": "0", "CPUS": "4", "NAME": "bt_test_record"}
import os                                           # noqa: E402
for k, v in env_extra.items():
    os.environ[k] = v
rc, out, log = run(["bash", WT / "scripts/board_tower/run_record_docker.sh", "--max", "20", "--batch", "1", "--shard-boards", "8", "--train-cells", "1024"],
                   "record.log", timeout=1800)
assert rc == 0, f"record failed, see {log}\n{out[-3000:]}"
m = json.load(open(targets / "manifest.json"))
assert len(m["boards"]) == 20, len(m["boards"])
assert {b["split"] for b in m["boards"]} == {"train", "eval"}
rec = m["recorder"]
assert rec["patchify_check"]["ok"] and rec["weights"]["n_visual_tensors"] == 333
assert rec["weights"]["visual_tensor_bytes_sha256"].startswith("5c8207cd"), rec["weights"]["visual_tensor_bytes_sha256"]
hf = rec.get("hf_crosscheck", {})
assert "cases" in hf and hf["cases"]["board0"]["cos_mean"] > 0.99, hf
n_rows = 0
for sh in m["shards"]:
    with safe_open(str(targets / sh["file"]), "pt", device="cpu") as f:
        T = f.get_tensor("targets"); I = f.get_tensor("cell_idx"); B = f.get_tensor("cells")
    assert T.dtype == torch.bfloat16 and T.shape[2] == 2560 and T.shape[0] == sh["n"], (sh, T.shape, T.dtype)
    assert T.shape[1] == (4096 if sh["split"] == "eval" else 1024), (sh["split"], T.shape)
    assert torch.isfinite(T.float()).all()
    assert I.dtype == torch.int16 and (I[:, 1:] > I[:, :-1]).all() and I.min() >= 0 and I.max() < 4096
    assert B.dtype == torch.uint8 and B.shape[1:] == (64, 64) and B.max() < 16
    norms = T.float().norm(dim=-1)
    assert 0.2 < norms.mean() < 3.0, norms.mean()          # S0: in-board token norms ~0.7-1.0
    n_rows += T.shape[0] * T.shape[1]
for b in m["boards"]:
    assert (targets / b["shard"]).is_file() and b["index"] < next(sh["n"] for sh in m["shards"] if sh["file"] == b["shard"])
print(f"test_make_targets_smoke OK: {len(m['boards'])} boards in {len(m['shards'])} shards, {n_rows:,} target rows; "
      f"tower rate {rec['rate_boards_per_s_tower']} boards/s (wall {rec['rate_boards_per_s_wall']}), "
      f"HF cross-check cos mean {hf['cases']['board0']['cos_mean']:.4f} min {hf['cases']['board0']['cos_min']:.3f}; "
      f"teacher noise floor {rec.get('batch_consistency', {})}; targets at {targets}")
