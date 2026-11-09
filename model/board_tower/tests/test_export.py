"""Shape/dtype test of the export (CPU, no targets, no server): a random-init student checkpoint -> the image_embeds
part -> decoded exactly as the server decodes it -> (4096, 2560) bf16, grid [1,128,128], the synth_embeds assert,
distinct uuid prefix; the legend block (64, 2560) with grid [1,16,16]; and the perception script's `tower` arm
builds the same parts. Run: python scripts/board_tower/tests/test_export.py"""
import json
import os
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _common import TEST_DIR, WT  # noqa: E402

os.environ["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"
os.environ["BOARD_TOWER_DEVICE"] = "cpu"
sys.path.insert(0, str(WT))
import numpy as np   # noqa: E402
import torch         # noqa: E402

from notebooks_duck.synth_tokens import synth_embeds as se                      # noqa: E402
from scripts.board_tower.model import BoardTower, BoardTowerConfig, save_checkpoint   # noqa: E402
from scripts.board_tower import export_embeds as bt                             # noqa: E402

torch.set_num_threads(2)
TEST_DIR.mkdir(parents=True, exist_ok=True)
ck = TEST_DIR / "tiny_random.pt"
torch.manual_seed(0)
save_checkpoint(ck, BoardTower(BoardTowerConfig(dim=64, depth=2, heads=4)), {"step": 0})
st = bt.load_student(ck, "cpu")
fx = json.load(open(WT / "notebooks_duck" / "synth_tokens" / "fixtures" / "board_vc33_l40.json"))
board = np.asarray(fx["board"], dtype=np.int64)

part = bt.build_image_embeds(board, st)
assert part["type"] == "image_embeds" and set(part["image_embeds"]) == {"image_embeds", "image_grid_thw"}, part.keys()
emb = se.decode_b64_tensor(part["image_embeds"]["image_embeds"]); grid = se.decode_b64_tensor(part["image_embeds"]["image_grid_thw"])
assert tuple(emb.shape) == (4096, 2560) and emb.dtype == torch.bfloat16, (emb.shape, emb.dtype)
assert grid.tolist() == [1, 128, 128] and grid.dtype == torch.int64 and tuple(grid.shape) == (3,), grid
se.assert_request_shapes(emb, grid)
assert part["uuid"].startswith("tower-") and part["uuid"] != se.board_uuid(board) and part["uuid"].endswith(se.board_uuid(board)[6:]), part["uuid"]
# row order: row-major; a solid board must give the same matrix twice (deterministic), different colours differ
a = bt.build_image_embeds(np.full((64, 64), 3), st); b = bt.build_image_embeds(np.full((64, 64), 3), st); c = bt.build_image_embeds(np.full((64, 64), 9), st)
assert a["image_embeds"]["image_embeds"] == b["image_embeds"]["image_embeds"] and a["uuid"] == b["uuid"]
assert a["image_embeds"]["image_embeds"] != c["image_embeds"]["image_embeds"] and a["uuid"] != c["uuid"]
ea = se.decode_b64_tensor(a["image_embeds"]["image_embeds"]); ec = se.decode_b64_tensor(c["image_embeds"]["image_embeds"])
assert not torch.equal(ea, ec)
# legend
lg = bt.legend_part(5, st)
le = se.decode_b64_tensor(lg["image_embeds"]["image_embeds"]); lgr = se.decode_b64_tensor(lg["image_embeds"]["image_grid_thw"])
assert tuple(le.shape) == (64, 2560) and le.dtype == torch.bfloat16 and lgr.tolist() == [1, 16, 16] and int(lgr.prod()) // 4 == 64
# the perception script's arm builds the same parts without a server
sys.argv = ["x"]; os.environ["BOARD_TOWER_CKPT"] = str(ck)
import importlib.util   # noqa: E402
spec = importlib.util.spec_from_file_location("perc", WT / "scripts" / "synth_tokens_perception.py"); perc = importlib.util.module_from_spec(spec); spec.loader.exec_module(perc)
assert "tower" in perc.ARMS
parts = perc.board_parts("tower", board, "Board A")
assert parts[0]["type"] == "text" and parts[1]["type"] == "image_embeds" and parts[1]["uuid"] == part["uuid"], [p["type"] for p in parts]
lparts = perc.legend_parts("tower", 5)
assert lparts[1]["type"] == "image_embeds" and lparts[1]["uuid"] == lg["uuid"]
tr = {"task": "same", "board": board, "r1": 1, "c1": 2, "r2": 3, "c2": 4}
content = perc.question_parts("tower", tr); json.dumps(perc.body(content, 1, 16))
n = perc.payload_bytes(content)
assert n > 20_000_000, n
print(f"test_export OK: part (4096,2560) bf16 grid [1,128,128] uuid {part['uuid'][:24]}.. payload {se.part_payload_bytes(part):,} B; "
      f"legend (64,2560) grid [1,16,16]; perception `tower` arm builds {len(content)} parts, {n:,} B; student tag {st.tag}")
