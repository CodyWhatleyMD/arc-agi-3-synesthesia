"""The board tower (plan S2c): a small transformer from a 64x64 board of cell colours (16-way one-hot per cell,
no pixels) to the (n_pos, 2560) token matrix Flash-Next's FULL vision tower emits for that board.

The INPUT is always 4096 cells. The OUTPUT length is the teacher's token count, which depends on the px/cell
the targets were recorded at: (2*px)**2 = 4096 at px=32, 1024 at px=16 (finding 177's distillation target).
`cell_patch` = cells per side per output position = 64 / (2*px) bridges the two -- 1 at px=32, 2 at px=16 --
and common.cells_per_token_side(px) computes it. It is a config field, not a constant, so a later retarget
(e.g. px=8 -> 256 tokens, cell_patch=4) is a flag and not an edit.

Design, against what S0 measured about the target (notes/synth_tokens_s0_2026-10-03.md):
  * one output position per cell_patch x cell_patch CELL BLOCK, the block's one-hot vectors CONCATENATED
    (cell_patch=1: one position per cell, no fold at all -- the px=32 case, unchanged). The concat mirrors the
    tower's OWN patch merger, which concatenates the 4 patches of a 2x2 group and MLPs them: at px=16 a 16-px
    patch is exactly one cell, so the teacher's merge group IS a 2x2 cell block. Folding the input this way
    rather than pooling the output means no information is discarded and the student's positions are the
    teacher's token positions by construction;
  * 2-D positions twice, as the full tower has them: a learned absolute table over the POSITION grid (the
    tower's interpolated absolute position embedding) and axial 2-D rotary in every attention (the tower's
    2-D RoPE: half the head dims rotate with the row, half with the column);
  * full attention over the positions (the target token is ~40% neighbourhood, S0 section 2-3);
  * output = linear(dim -> 2560) + a learned per-POSITION bias (n_pos x 2560): S0 found 56-65% of a real
    token's direction is a per-position code shared across colours, so the bias carries that and the blocks only
    have to produce the colour / neighbourhood residual. 10.5M of the parameters are this bias at cell_patch=1,
    2.6M at cell_patch=2.

Sizes (default dim 384, depth 8, heads 6): ~27M parameters at cell_patch=1 (~19M at 2), of which 14M are the
blocks. See count_params().
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import torch
import torch.nn as nn
import torch.nn.functional as F

GRID = 64
N_CELLS = GRID * GRID
N_COLOURS = 16
OUT_DIM = 2560


@dataclass
class BoardTowerConfig:
    dim: int = 384
    depth: int = 8
    heads: int = 6
    mlp_ratio: float = 4.0
    out_dim: int = OUT_DIM
    grid: int = GRID
    n_colours: int = N_COLOURS
    pos_bias: bool = True
    rope: bool = True
    rope_theta: float = 10000.0
    cell_patch: int = 1          # cells per SIDE per output position: 1 at 32 px/cell, 2 at 16 px/cell (1024 tokens)

    def __post_init__(self):
        if self.cell_patch < 1 or self.grid % self.cell_patch:
            raise ValueError(f"cell_patch {self.cell_patch} must be >=1 and divide grid {self.grid}")

    @property
    def pos_grid(self) -> int:
        """Output positions per side: 64 at cell_patch=1, 32 at cell_patch=2."""
        return self.grid // self.cell_patch

    @property
    def n_pos(self) -> int:
        """Output length = the teacher's tokens per board (4096 at cell_patch=1, 1024 at 2)."""
        return self.pos_grid ** 2

    def to_dict(self) -> dict:
        return asdict(self)


def rope_2d_tables(head_dim: int, grid: int, theta: float) -> tuple[torch.Tensor, torch.Tensor]:
    """cos/sin (grid*grid, head_dim): the first half of the rotary pairs follow the ROW, the second half the
    COLUMN (axial 2-D RoPE, as Qwen2/3-VL's vision rotary builds h/w frequencies and concatenates them)."""
    assert head_dim % 4 == 0, head_dim
    half = head_dim // 2                                             # dims per axis
    inv = 1.0 / theta ** (torch.arange(0, half, 2, dtype=torch.float32) / half)   # (half/2,)
    pos = torch.arange(grid, dtype=torch.float32)
    fr = torch.outer(pos, inv)                                       # (grid, half/2)
    ang = torch.cat([fr[:, None, :].expand(grid, grid, -1), fr[None, :, :].expand(grid, grid, -1)], dim=-1)
    ang = ang.reshape(grid * grid, half)                             # (N, head_dim/2): [row freqs | col freqs]
    emb = torch.cat([ang, ang], dim=-1)                              # (N, head_dim), rotate-half layout
    return emb.cos(), emb.sin()


def apply_rope(x: torch.Tensor, cos: torch.Tensor, sin: torch.Tensor) -> torch.Tensor:
    """x (B, H, N, D); cos/sin (N, D)."""
    d = x.shape[-1] // 2
    x1, x2 = x[..., :d], x[..., d:]
    rot = torch.cat([-x2, x1], dim=-1)
    return x * cos + rot * sin


class Attention(nn.Module):
    def __init__(self, dim: int, heads: int):
        super().__init__()
        assert dim % heads == 0
        self.heads, self.hd = heads, dim // heads
        self.qkv = nn.Linear(dim, 3 * dim)
        self.proj = nn.Linear(dim, dim)

    def forward(self, x: torch.Tensor, cos: torch.Tensor | None, sin: torch.Tensor | None) -> torch.Tensor:
        B, N, D = x.shape
        q, k, v = self.qkv(x).view(B, N, 3, self.heads, self.hd).permute(2, 0, 3, 1, 4)   # 3 x (B, H, N, hd)
        if cos is not None:
            q, k = apply_rope(q, cos, sin), apply_rope(k, cos, sin)
        o = F.scaled_dot_product_attention(q, k, v)                                         # (B, H, N, hd)
        return self.proj(o.transpose(1, 2).reshape(B, N, D))


class Block(nn.Module):
    def __init__(self, dim: int, heads: int, mlp_ratio: float):
        super().__init__()
        self.n1 = nn.LayerNorm(dim)
        self.attn = Attention(dim, heads)
        self.n2 = nn.LayerNorm(dim)
        hid = int(dim * mlp_ratio)
        self.mlp = nn.Sequential(nn.Linear(dim, hid), nn.GELU(), nn.Linear(hid, dim))

    def forward(self, x, cos, sin):
        x = x + self.attn(self.n1(x), cos, sin)
        return x + self.mlp(self.n2(x))


class BoardTower(nn.Module):
    def __init__(self, cfg: BoardTowerConfig | None = None):
        super().__init__()
        self.cfg = cfg or BoardTowerConfig()
        c = self.cfg
        n = c.n_pos
        self.inp = nn.Linear(c.n_colours * c.cell_patch ** 2, c.dim)  # the block's one-hot vectors -> dim
        self.pos = nn.Parameter(torch.zeros(n, c.dim))
        nn.init.normal_(self.pos, std=0.02)
        self.blocks = nn.ModuleList([Block(c.dim, c.heads, c.mlp_ratio) for _ in range(c.depth)])
        self.norm = nn.LayerNorm(c.dim)
        self.out = nn.Linear(c.dim, c.out_dim)
        nn.init.normal_(self.out.weight, std=1e-3); nn.init.zeros_(self.out.bias)   # start near zero: rel-MSE ~1, not ~350
        self.out_pos_bias = nn.Parameter(torch.zeros(n, c.out_dim)) if c.pos_bias else None
        if c.rope:
            cos, sin = rope_2d_tables(c.dim // c.heads, c.pos_grid, c.rope_theta)
            self.register_buffer("rope_cos", cos, persistent=False)
            self.register_buffer("rope_sin", sin, persistent=False)
        else:
            self.rope_cos = self.rope_sin = None

    # ------------------------------------------------------------------ inputs
    @staticmethod
    def onehot_from_cells(cells, n_colours: int = N_COLOURS) -> torch.Tensor:
        """(..., 64, 64) int -> (..., 64, 64, 16) float32 one-hot."""
        t = torch.as_tensor(cells).long()
        if t.min() < 0 or t.max() >= n_colours:
            raise ValueError(f"cell values must be in 0..{n_colours - 1}, got [{int(t.min())}, {int(t.max())}]")
        return F.one_hot(t, n_colours).float()

    def forward(self, onehot: torch.Tensor) -> torch.Tensor:
        """onehot (B, 64, 64, 16) or (B, 4096, 16) float -> (B, n_pos, 2560).

        cell_patch=1: one position per cell, row-major k = r*64 + c (the teacher's token order at 32 px/cell).
        cell_patch=p>1: one position per p x p CELL BLOCK, row-major over the (64/p, 64/p) block grid, the
        block's p*p one-hot vectors concatenated in (row, col) order within the block -- the order
        s0_record_table.hf_patchify gives a merge group, so the student's position k is the teacher's token k.
        """
        c = self.cfg
        if onehot.ndim == 3:
            B, N, K = onehot.shape
            assert N == c.grid * c.grid, onehot.shape
            onehot = onehot.reshape(B, c.grid, c.grid, K)
        B, H, W, K = onehot.shape
        assert (H, W, K) == (c.grid, c.grid, c.n_colours), onehot.shape
        p, s = c.cell_patch, c.pos_grid
        if p == 1:
            x = onehot.reshape(B, s * s, K)
        else:
            x = onehot.reshape(B, s, p, s, p, K).permute(0, 1, 3, 2, 4, 5).reshape(B, s * s, p * p * K)
        x = self.inp(x.to(self.inp.weight.dtype)) + self.pos.to(onehot.device)
        cos = sin = None
        if self.rope_cos is not None:
            cos, sin = self.rope_cos.to(x.dtype), self.rope_sin.to(x.dtype)
        for blk in self.blocks:
            x = blk(x, cos, sin)
        y = self.out(self.norm(x))
        if self.out_pos_bias is not None:
            y = y + self.out_pos_bias
        return y

    @torch.no_grad()
    def tokens_for_board(self, cells, device=None) -> torch.Tensor:
        """One board (64, 64) ints -> (n_pos, 2560) bfloat16 on CPU: the image_embeds matrix for that board."""
        dev = device or next(self.parameters()).device
        oh = self.onehot_from_cells(cells).unsqueeze(0).to(dev)
        with torch.autocast(device_type=dev.type if hasattr(dev, "type") else str(dev).split(":")[0],
                            dtype=torch.bfloat16, enabled=str(dev).startswith("cuda")):
            y = self.forward(oh)[0]
        return y.to(torch.bfloat16).cpu().contiguous()

    # ------------------------------------------------------------------ bookkeeping
    def count_params(self) -> dict:
        n_all = sum(p.numel() for p in self.parameters())
        n_blocks = sum(p.numel() for p in self.blocks.parameters())
        n_bias = self.out_pos_bias.numel() if self.out_pos_bias is not None else 0
        return {"total": n_all, "blocks": n_blocks, "out_pos_bias": n_bias, "pos": self.pos.numel(),
                "out_linear": sum(p.numel() for p in self.out.parameters()), "inp": sum(p.numel() for p in self.inp.parameters())}


# ---------------------------------------------------------------------- checkpoint IO
def save_checkpoint(path, model: BoardTower, extra: dict | None = None) -> None:
    import os
    path = str(path)
    tmp = path + ".tmp"
    torch.save({"config": model.cfg.to_dict(), "state_dict": model.state_dict(), "extra": extra or {}}, tmp)
    os.replace(tmp, path)


def load_checkpoint(path, device="cpu") -> tuple[BoardTower, dict]:
    d = torch.load(path, map_location="cpu", weights_only=False)
    model = BoardTower(BoardTowerConfig(**d["config"]))
    model.load_state_dict(d["state_dict"])
    return model.to(device).eval(), d.get("extra", {})


if __name__ == "__main__":
    for cp in (1, 2):
        m = BoardTower(BoardTowerConfig(cell_patch=cp))
        x = m.onehot_from_cells(torch.randint(0, 16, (2, 64, 64)))
        print(f"cell_patch={cp} n_pos={m.cfg.n_pos} out={tuple(m(x).shape)} params={m.count_params()}")
