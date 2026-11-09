"""Unit test for the S2b request builder. Run: python3 -m pytest notebooks_duck/synth_tokens/test_synth_embeds.py -q
(or python3 notebooks_duck/synth_tokens/test_synth_embeds.py). Needs torch + the S0 table file; no server."""
import json
import pathlib
import sys

import numpy as np
import pytest
import torch

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
from notebooks_duck.synth_tokens import synth_embeds as se  # noqa: E402

FIXTURE = HERE / "fixtures" / "board_vc33_l40.json"


@pytest.fixture(scope="module")
def board():
    d = json.load(open(FIXTURE))
    b = np.asarray(d["board"], dtype=np.int64)
    assert b.shape == (64, 64) and d["n_colours"] >= 8
    return b


@pytest.fixture(scope="module")
def table():
    return se.load_table()


def test_table_shape_dtype(table):
    assert table.shape == (16, 2560) and table.dtype == torch.bfloat16
    # rows separate: no two colours identical
    assert (table.float()[:, None, :] - table.float()[None, :, :]).abs().sum(-1).fill_diagonal_(1).min() > 0


def test_part_shapes_and_dtype(board, table):
    part = se.build_image_embeds(board, table)
    assert part["type"] == "image_embeds" and set(part["image_embeds"]) == {"image_embeds", "image_grid_thw"}
    emb = se.decode_b64_tensor(part["image_embeds"]["image_embeds"])
    grid = se.decode_b64_tensor(part["image_embeds"]["image_grid_thw"])
    assert emb.shape == (4096, 2560) and emb.dtype == torch.bfloat16 and emb.is_contiguous()
    assert grid.shape == (3,) and grid.tolist() == [1, 128, 128] and grid.dtype == torch.int64
    assert (grid.prod() // 4).item() == emb.shape[0]
    # round trip equals a direct gather, row-major
    ref = table[torch.from_numpy(board.reshape(-1)).long()]
    assert torch.equal(emb, ref)
    r, c = 17, 42
    assert torch.equal(emb[r * 64 + c], table[int(board[r, c])])
    raw = se.part_payload_bytes(part)
    assert 20_000_000 < raw < 30_000_000          # ~21 MB tensor, base64 -> ~28 MB


def test_uuid_deterministic(board, table):
    a = se.build_image_embeds(board, table)
    b = se.build_image_embeds(board.copy(), table)
    assert a["uuid"] == b["uuid"] == se.board_uuid(board)
    assert a["uuid"].startswith("board-") and len(a["uuid"]) == len("board-") + 40
    other = board.copy(); other[0, 0] = (other[0, 0] + 1) % 16
    assert se.build_image_embeds(other, table)["uuid"] != a["uuid"]


def test_one_cell_change_changes_exactly_one_row(board, table):
    other = board.copy()
    r, c = 31, 7
    other[r, c] = (other[r, c] + 3) % 16
    a = se.decode_b64_tensor(se.build_image_embeds(board, table)["image_embeds"]["image_embeds"])
    b = se.decode_b64_tensor(se.build_image_embeds(other, table)["image_embeds"]["image_embeds"])
    diff_rows = (a != b).any(dim=1).nonzero().flatten().tolist()
    assert diff_rows == [r * 64 + c]


def test_token_accounting():
    ids = se.placeholder_token_ids()
    assert len(ids) == 4098 and ids[0] == 248053 and ids[-1] == 248054
    assert ids[1:-1].count(248056) == 4096
    assert se.token_budget(1) == 4098 and se.token_budget(3) == 3 * 4098
    assert se.mrope_position_advance(1) == 64


def test_request_body(board, table):
    body = se.build_request(board, "Which row changed?", table=table, seed=7, max_tokens=8)
    assert body["model"] == "flashnext" and body["seed"] == 7 and body["max_tokens"] == 8
    content = body["messages"][0]["content"]
    assert [p["type"] for p in content] == ["text", "image_embeds", "text"]
    assert json.dumps(body)  # serialisable


def test_shape_guards_reject(board, table):
    emb = se.gather_embeds(board, table)
    good = se.grid_thw_tensor()
    with pytest.raises(ValueError):
        se.assert_request_shapes(emb, good.unsqueeze(0))            # (1,3)
    with pytest.raises(ValueError):
        se.assert_request_shapes(emb.float(), good)                 # dtype
    with pytest.raises(ValueError):
        se.assert_request_shapes(emb[:4095], good)                  # row count
    with pytest.raises(ValueError):
        se.assert_request_shapes(torch.cat([emb, emb[:, :1]], 1).contiguous(), good)  # width
    with pytest.raises(ValueError):
        se.assert_request_shapes(emb, torch.tensor([2, 128, 128]))  # t != 1
    with pytest.raises(ValueError):
        se.board_cells(np.full((64, 64), 16))                       # colour out of range
    with pytest.raises(ValueError):
        se.board_cells(np.zeros((63, 64), dtype=int))               # size


def test_position_table_gather(board):
    pos = torch.randn(4096, 16, 2560).to(torch.bfloat16)
    emb = se.gather_embeds(board, pos)
    k = 5 * 64 + 9
    assert torch.equal(emb[k], pos[k, int(board[5, 9])])


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
