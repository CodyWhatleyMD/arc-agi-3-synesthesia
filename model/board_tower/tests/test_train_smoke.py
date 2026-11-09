"""2-minute training smoke on the 5090 against the 20-board targets of test_make_targets_smoke (or BOARD_TOWER_SMOKE_TARGETS).
Asserts: the run finishes within budget, loss falls (last logged < first logged), eval runs on the held-out boards with
the S0 readback row for student AND target, best.pt/last.pt/summary.json exist and reload, and the exported part from
best.pt passes the synth_embeds shape assert. Run: python scripts/board_tower/tests/test_train_smoke.py"""
import json
import os
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _common import PY, TEST_DIR, WT, run, wait_load  # noqa: E402

targets = pathlib.Path(os.environ.get("BOARD_TOWER_SMOKE_TARGETS") or (TEST_DIR / "targets20"))
assert (targets / "manifest.json").is_file(), f"no manifest under {targets}: run test_make_targets_smoke.py first or set BOARD_TOWER_SMOKE_TARGETS"
out = TEST_DIR / "ckpt_smoke"
wait_load()
rc, text, log = run([PY, WT / "scripts/board_tower/train.py", "--targets", targets, "--out", out, "--max-minutes", "2", "--batch", "4",
                     "--eval-every", "100", "--eval-boards", "8", "--warmup", "20", "--log-every", "10", "--dim", "256", "--depth", "4", "--heads", "4"],
                    "train.log", timeout=600)
assert rc == 0, f"train failed, see {log}\n{text[-3000:]}"
s = json.load(open(out / "summary.json"))
assert s["minutes"] <= 3.5, s["minutes"]
curve = s["curve"]
assert len(curve) >= 3, len(curve)
assert curve[-1]["loss"] < curve[0]["loss"], (curve[0]["loss"], curve[-1]["loss"])
assert curve[-1]["cos"] > curve[0]["cos"], (curve[0]["cos"], curve[-1]["cos"])
fe = s["final_eval"]
assert fe["n_boards"] >= 2 and fe["readback_student"] is not None and fe["readback_target"] is not None and fe["pos_only_cos"] is not None
assert "the student should MATCH it" in text
for name in ("best.pt", "last.pt"):
    assert (out / name).is_file(), name
sys.path.insert(0, str(WT)); os.environ["BOARD_TOWER_DEVICE"] = "cpu"
from scripts.board_tower import export_embeds as bt                  # noqa: E402
from notebooks_duck.synth_tokens import synth_embeds as se           # noqa: E402
import numpy as np                                                   # noqa: E402
st = bt.load_student(out / "best.pt", "cpu")
part = bt.build_image_embeds(np.random.default_rng(1).integers(0, 16, (64, 64)), st)
se.assert_request_shapes(se.decode_b64_tensor(part["image_embeds"]["image_embeds"]), se.decode_b64_tensor(part["image_embeds"]["image_grid_thw"]))
print(f"test_train_smoke OK: {s['steps']} steps in {s['minutes']} min, params {s['params']['total']:,}; "
      f"loss {curve[0]['loss']:.4f} -> {curve[-1]['loss']:.4f}, train cos {curve[0]['cos']:.4f} -> {curve[-1]['cos']:.4f}; "
      f"held-out eval cos {fe['cos_mean']:.4f} (p05 {fe['cos_p05']:.4f}), readback student {fe['readback_student']:.3f} vs target {fe['readback_target']:.3f}, "
      f"position-only {fe['pos_only_cos']:.4f}; ckpt {out}")
