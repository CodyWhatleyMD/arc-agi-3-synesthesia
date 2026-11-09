# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the vLLM project
"""ARC3 RecoverSSM for Qwen gated delta-rule (GDN) layers.

The stock speculative path writes one full recurrent state per window token
into per-draft cache blocks, so the next step can start from whichever draft
was accepted. RecoverSSM verifies the whole MTP window from the single running
state without writing it, records the per-token correction, normalized key and
scalar gate, and after sampling folds exactly the accepted prefix back into the
running state block. Crossing a mamba block boundary also writes the boundary
checkpoint, the same block the stock align postprocess copies into.

Both kernels repeat the stock ``fused_sigmoid_gating_delta_rule_update``
arithmetic operation for operation, so outputs and recovered states match the
stock per-draft states bit for bit on the same compiler. Convolution states are
not touched here; they keep the stock sliding-window layout.

The verify keeps the stock kernel's four warps, which fix how every reduction
over the key dimension is laid out; its value tile only changes how many rows
of the state one program owns. The commit has no reductions, so its tiling is
free. The launch constants were picked on SM120 for C14 decode rows.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import torch

from vllm.triton_utils import tl, triton
from vllm.v1.attention.backends.utils import NULL_BLOCK_ID

VERIFY_BLOCK_V = 64
VERIFY_NUM_WARPS = 4
VERIFY_NUM_STAGES = 3
COMMIT_BLOCK_V = 64
COMMIT_NUM_WARPS = 4
SOFTPLUS_BETA = 1.0
SOFTPLUS_THRESHOLD = 20.0


@triton.jit(do_not_specialize=["num_rows"])
def _gdn_recoverssm_verify_kernel(
    A_log,
    a,
    b,
    dt_bias,
    q,
    k,
    v,
    o,
    state,
    cu_seqlens,
    state_indices,
    correction_records,
    key_records,
    gate_records,
    scale,
    softplus_beta,
    softplus_threshold,
    num_rows,
    H: tl.constexpr,
    HV: tl.constexpr,
    K: tl.constexpr,
    V: tl.constexpr,
    BK: tl.constexpr,
    BV: tl.constexpr,
    SPEC_QUERY_LEN: tl.constexpr,
    RECORD_ROWS: tl.constexpr,
    stride_state_block: tl.constexpr,
    stride_state_indices: tl.constexpr,
):
    """Verify one row and v-head tile from the running state without storing it.

    The per-token body is the stock kernel's: exp-scaled state, delta-rule
    correction, beta scaling, rank-one update and output. Instead of the state
    it stores the correction (after beta), the L2-normalized key and the gate,
    which is all the recovery kernel needs to replay the accepted tokens.
    """
    i_v, i_nh = tl.program_id(0), tl.program_id(1)
    i_n, i_hv = i_nh // HV, i_nh % HV
    i_h = i_hv // (HV // H)
    bos = tl.load(cu_seqlens + i_n).to(tl.int64)
    eos = tl.load(cu_seqlens + i_n + 1).to(tl.int64)
    T = eos - bos
    if T == 0:

        return

    o_k = tl.arange(0, BK)
    o_v = i_v * BV + tl.arange(0, BV)
    mask_k = o_k < K
    mask_v = o_v < V
    mask_h = mask_v[:, None] & mask_k[None, :]

    p_q = q + (bos * H + i_h) * K + o_k
    p_k = k + (bos * H + i_h) * K + o_k
    p_v = v + (bos * HV + i_hv) * V + o_v
    p_a = a + bos * HV + i_hv
    p_b = b + bos * HV + i_hv
    p_o = o + (bos * HV + i_hv) * V + o_v

    state_idx = tl.load(state_indices + i_n * stride_state_indices).to(tl.int64)
    if (state_idx <= 0) | (i_n >= RECORD_ROWS):
        zero = tl.zeros([BV], dtype=tl.float32).to(p_o.dtype.element_ty)
        for _ in range(0, T):
            tl.store(p_o, zero, mask=mask_v)
            p_o += HV * V

        return

    p_h0 = state + state_idx * stride_state_block
    p_h0 = p_h0 + i_hv * V * K + o_v[:, None] * K + o_k[None, :]
    b_h = tl.zeros([BV, BK], dtype=tl.float32)
    b_h += tl.load(p_h0, mask=mask_h, other=0).to(tl.float32)

    p_correction = correction_records + ((i_n * HV + i_hv) * SPEC_QUERY_LEN) * V + o_v
    p_key = key_records + ((i_n * H + i_h) * SPEC_QUERY_LEN) * K + o_k
    p_gate = gate_records + (i_n * HV + i_hv) * SPEC_QUERY_LEN
    writes_head_records = i_v == 0
    writes_key_records = writes_head_records & (i_hv % (HV // H) == 0)

    for i_t in range(0, T):
        b_q = tl.load(p_q, mask=mask_k, other=0).to(tl.float32)
        b_k = tl.load(p_k, mask=mask_k, other=0).to(tl.float32)
        b_v = tl.load(p_v, mask=mask_v, other=0).to(tl.float32)
        b_b = tl.load(p_b).to(tl.float32)

        x = tl.load(p_a).to(tl.float32) + tl.load(dt_bias + i_hv).to(tl.float32)
        softplus_x = tl.where(
            softplus_beta * x <= softplus_threshold,
            (1 / softplus_beta) * tl.log(1 + tl.exp(softplus_beta * x)),
            x,
        )
        b_g = -tl.exp(tl.load(A_log + i_hv).to(tl.float32)) * softplus_x
        b_beta = tl.sigmoid(b_b.to(tl.float32))

        b_q = b_q * (tl.rsqrt(tl.sum(b_q * b_q) + 1e-6))
        b_k = b_k * (tl.rsqrt(tl.sum(b_k * b_k) + 1e-6))
        b_q = b_q * scale
        b_h *= tl.exp(b_g)
        b_v -= tl.sum(b_h * b_k[None, :], 1)
        b_v *= b_beta
        b_h += b_v[:, None] * b_k[None, :]
        b_o = tl.sum(b_h * b_q[None, :], 1)
        tl.store(p_o, b_o.to(p_o.dtype.element_ty), mask=mask_v)

        record_slot = i_t < SPEC_QUERY_LEN
        tl.store(p_correction + i_t * V, b_v, mask=mask_v & record_slot)
        if writes_head_records & record_slot:
            tl.store(p_gate + i_t, b_g)
        if writes_key_records & record_slot:
            tl.store(p_key + i_t * K, b_k, mask=mask_k)

        p_q += H * K
        p_k += H * K
        p_o += HV * V
        p_v += HV * V
        p_b += HV
        p_a += HV


@triton.heuristics(
    {
        "HAS_REQUEST_INDICES": lambda args: args["request_indices"] is not None,
        "ALIGN_MODE": lambda args: args["block_table"] is not None,
    }
)
@triton.jit(do_not_specialize=["num_rows"])
def _gdn_recoverssm_commit_kernel(
    state_reference,
    state_base_addrs,
    state_block_strides,
    correction_reference,
    correction_base_addrs,
    key_reference,
    key_base_addrs,
    gate_reference,
    gate_base_addrs,
    source_blocks,
    query_start_loc,
    num_sampled,
    request_indices,
    num_computed_tokens,
    block_table,
    stride_source_blocks,
    stride_block_table_row,
    block_table_width,
    num_rows,
    H: tl.constexpr,
    HV: tl.constexpr,
    K: tl.constexpr,
    V: tl.constexpr,
    BK: tl.constexpr,
    BV: tl.constexpr,
    SPEC_QUERY_LEN: tl.constexpr,
    RECORD_ROWS: tl.constexpr,
    MAMBA_BLOCK_SIZE: tl.constexpr,
    HAS_REQUEST_INDICES: tl.constexpr,
    ALIGN_MODE: tl.constexpr,
):
    """Fold the accepted prefix of one row into its running state block.

    ``num_sampled`` counts the tokens the rejection sampler emitted, i.e. the
    accepted drafts plus the bonus token, which equals the number of window
    inputs whose state the next step continues from. The replay repeats the
    verify kernel's two state operations per token; the rank-one update is an
    explicit FMA because the verify kernel contracts it the same way, while here
    the compiler could otherwise fuse the decay multiply instead. The align
    specialization replays through the first mamba block boundary and stores
    its checkpoint. The regular specialization replays the full accepted prefix.
    """
    i_v, row, i_lh = tl.program_id(0), tl.program_id(1), tl.program_id(2)
    layer = i_lh // HV
    i_hv = i_lh % HV
    i_h = i_hv // (HV // H)

    source_block = tl.load(source_blocks + row * stride_source_blocks).to(tl.int64)
    if (source_block <= 0) | (row >= RECORD_ROWS):

        return
    query_len = tl.load(query_start_loc + row + 1) - tl.load(query_start_loc + row)
    batch_row = row
    if HAS_REQUEST_INDICES:
        batch_row = tl.load(request_indices + row).to(tl.int64)
    commit_len = tl.load(num_sampled + batch_row).to(tl.int32)
    commit_len = tl.minimum(tl.maximum(commit_len, 0), query_len)
    commit_len = tl.minimum(commit_len, SPEC_QUERY_LEN)
    if commit_len <= 0:

        return

    if ALIGN_MODE:
        computed = tl.load(num_computed_tokens + batch_row).to(tl.int64)
        boundary_col = computed // MAMBA_BLOCK_SIZE
        boundary_len = ((boundary_col + 1) * MAMBA_BLOCK_SIZE - computed).to(tl.int32)
        if (boundary_len > commit_len) | (boundary_col >= block_table_width):

            return
        target_block = tl.load(
            block_table + batch_row * stride_block_table_row + boundary_col
        ).to(tl.int64)
        if (target_block <= 0) | (target_block == source_block):

            return
        replay_len = boundary_len
    else:
        target_block = source_block
        replay_len = commit_len

    o_k = tl.arange(0, BK)
    o_v = i_v * BV + tl.arange(0, BV)
    mask_k = o_k < K
    mask_v = o_v < V
    mask_h = mask_v[:, None] & mask_k[None, :]

    state_pointer = tl.load(state_base_addrs + layer).to(
        tl.pointer_type(state_reference.dtype.element_ty)
    )
    block_stride = tl.load(state_block_strides + layer)
    head_offsets = i_hv * V * K + o_v[:, None] * K + o_k[None, :]
    p_source = state_pointer + source_block * block_stride + head_offsets
    p_target = state_pointer + target_block * block_stride + head_offsets
    b_h = tl.zeros([BV, BK], dtype=tl.float32)
    b_h += tl.load(p_source, mask=mask_h, other=0).to(tl.float32)

    correction_pointer = tl.load(correction_base_addrs + layer).to(
        tl.pointer_type(correction_reference.dtype.element_ty)
    )
    key_pointer = tl.load(key_base_addrs + layer).to(
        tl.pointer_type(key_reference.dtype.element_ty)
    )
    gate_pointer = tl.load(gate_base_addrs + layer).to(
        tl.pointer_type(gate_reference.dtype.element_ty)
    )
    p_correction = correction_pointer + ((row * HV + i_hv) * SPEC_QUERY_LEN) * V + o_v
    p_key = key_pointer + ((row * H + i_h) * SPEC_QUERY_LEN) * K + o_k
    p_gate = gate_pointer + (row * HV + i_hv) * SPEC_QUERY_LEN

    for token_index in range(0, replay_len):
        b_g = tl.load(p_gate + token_index)
        b_v = tl.load(p_correction + token_index * V, mask=mask_v, other=0)
        b_k = tl.load(p_key + token_index * K, mask=mask_k, other=0)
        b_h = b_h * tl.exp(b_g)
        b_h = tl.fma(b_v[:, None], b_k[None, :], b_h)

    tl.store(p_target, b_h.to(p_target.dtype.element_ty), mask=mask_h)


@dataclass
class GDNRecoverSSMRecords:
    """Per-layer scratch that one verify writes and the same step's commit reads.

    Rows are speculative-batch rows, not request slots, so a step rewrites every
    record its commit can read and nothing survives into another step.
    """

    correction: torch.Tensor
    key: torch.Tensor
    gate: torch.Tensor

    @property
    def num_rows(self) -> int:

        return self.correction.shape[0]

    @property
    def spec_query_len(self) -> int:

        return self.correction.shape[2]

    @property
    def num_bytes(self) -> int:

        return sum(
            tensor.numel() * tensor.element_size()
            for tensor in (self.correction, self.key, self.gate)
        )


def allocate_gdn_recoverssm_records(
    num_rows: int,
    num_k_heads: int,
    num_v_heads: int,
    head_k_dim: int,
    head_v_dim: int,
    spec_query_len: int,
    device: torch.device | str | int,
) -> GDNRecoverSSMRecords:
    """Allocate one layer's FP32 correction, normalized-key and gate records."""

    return GDNRecoverSSMRecords(
        correction=torch.empty(
            (num_rows, num_v_heads, spec_query_len, head_v_dim),
            dtype=torch.float32,
            device=device,
        ),
        key=torch.empty(
            (num_rows, num_k_heads, spec_query_len, head_k_dim),
            dtype=torch.float32,
            device=device,
        ),
        gate=torch.empty(
            (num_rows, num_v_heads, spec_query_len),
            dtype=torch.float32,
            device=device,
        ),
    )


def check_verify_inputs(
    q: torch.Tensor,
    k: torch.Tensor,
    v: torch.Tensor,
    a: torch.Tensor,
    b: torch.Tensor,
    state: torch.Tensor,
    query_start_loc: torch.Tensor,
    state_indices: torch.Tensor,
    records: GDNRecoverSSMRecords,
) -> None:
    """Reject shapes, layouts and batches the verify kernel does not support."""
    if q.ndim != 4 or q.shape[0] != 1 or k.shape != q.shape:
        raise ValueError("GDN RecoverSSM q and k must have shape [1, tokens, H, K]")
    _, num_tokens, num_k_heads, head_k_dim = q.shape
    if v.ndim != 4 or v.shape[:2] != (1, num_tokens):
        raise ValueError("GDN RecoverSSM v must have shape [1, tokens, HV, V]")
    num_v_heads, head_v_dim = v.shape[2], v.shape[3]
    if num_v_heads % num_k_heads != 0:
        raise ValueError("GDN RecoverSSM needs whole v-head groups per k-head")
    if a.shape != (num_tokens, num_v_heads) or b.shape != (num_tokens, num_v_heads):
        raise ValueError("GDN RecoverSSM gates must have shape [tokens, HV]")
    if state.ndim != 4 or state.shape[1:] != (num_v_heads, head_v_dim, head_k_dim):
        raise ValueError("GDN RecoverSSM state must have shape [blocks, HV, V, K]")
    if state.stride()[1:] != (head_v_dim * head_k_dim, head_k_dim, 1):
        raise ValueError("GDN RecoverSSM state heads must be contiguous")
    num_rows = state_indices.shape[0]
    if state_indices.ndim != 1 or query_start_loc.shape[0] != num_rows + 1:
        raise ValueError("GDN RecoverSSM query metadata is incompatible")
    expected_records = (
        (records.num_rows, num_v_heads, records.spec_query_len, head_v_dim),
        (records.num_rows, num_k_heads, records.spec_query_len, head_k_dim),
        (records.num_rows, num_v_heads, records.spec_query_len),
    )
    actual_records = (records.correction.shape, records.key.shape, records.gate.shape)
    if actual_records != expected_records:
        raise ValueError("GDN RecoverSSM records do not match the layer heads")


def gdn_recoverssm_verify(
    q: torch.Tensor,
    k: torch.Tensor,
    v: torch.Tensor,
    a: torch.Tensor,
    b: torch.Tensor,
    A_log: torch.Tensor,
    dt_bias: torch.Tensor,
    state: torch.Tensor,
    query_start_loc: torch.Tensor,
    state_indices: torch.Tensor,
    records: GDNRecoverSSMRecords,
    scale: float | None = None,
) -> torch.Tensor:
    """Verify speculative windows against their running states.

    Returns the output shaped like the stock kernel's, ``[1, tokens, HV, V]``,
    and leaves ``state`` unmodified. Rows with a null state index produce
    zeros; tokens past a row's record length are verified but not recorded,
    and the commit never replays them.
    """
    check_verify_inputs(q, k, v, a, b, state, query_start_loc, state_indices, records)
    _, num_tokens, num_k_heads, head_k_dim = q.shape
    num_v_heads, head_v_dim = v.shape[2], v.shape[3]
    num_rows = state_indices.shape[0]
    output = q.new_empty(1, num_tokens, num_v_heads, head_v_dim)
    if num_tokens == 0 or num_rows == 0:

        return output
    block_k = triton.next_power_of_2(head_k_dim)
    block_v = min(triton.next_power_of_2(head_v_dim), VERIFY_BLOCK_V)
    grid = (triton.cdiv(head_v_dim, block_v), num_rows * num_v_heads)
    _gdn_recoverssm_verify_kernel[grid](
        A_log,
        a.contiguous(),
        b.contiguous(),
        dt_bias,
        q.contiguous(),
        k.contiguous(),
        v.contiguous(),
        output,
        state,
        query_start_loc,
        state_indices,
        records.correction,
        records.key,
        records.gate,
        head_k_dim**-0.5 if scale is None else scale,
        SOFTPLUS_BETA,
        SOFTPLUS_THRESHOLD,
        num_rows,
        H=num_k_heads,
        HV=num_v_heads,
        K=head_k_dim,
        V=head_v_dim,
        BK=block_k,
        BV=block_v,
        SPEC_QUERY_LEN=records.spec_query_len,
        RECORD_ROWS=records.num_rows,
        stride_state_block=state.stride(0),
        stride_state_indices=state_indices.stride(0),
        num_warps=VERIFY_NUM_WARPS,
        num_stages=VERIFY_NUM_STAGES,
    )

    return output


def collect_base_addresses(
    tensors: Sequence[torch.Tensor], device: torch.device
) -> torch.Tensor:
    """Return the tensors' data pointers as an int64 device tensor."""

    return torch.tensor(
        [tensor.data_ptr() for tensor in tensors], dtype=torch.int64, device=device
    )


@dataclass
class GDNRecoverSSMCommitContext:
    """Pointers to every GDN layer of one KV cache group for a single commit launch."""

    states: tuple[torch.Tensor, ...]
    records: tuple[GDNRecoverSSMRecords, ...]
    state_base_addrs: torch.Tensor
    state_block_strides: torch.Tensor
    correction_base_addrs: torch.Tensor
    key_base_addrs: torch.Tensor
    gate_base_addrs: torch.Tensor

    @classmethod
    def create(cls, layers: Sequence[Any]) -> "GDNRecoverSSMCommitContext":
        """Collect and check the recurrent states and records of ``layers``."""
        if not layers:
            raise ValueError("GDN RecoverSSM commit needs at least one layer")
        states = tuple(layer.kv_cache[1] for layer in layers)
        records = tuple(layer.recoverssm_records for layer in layers)
        if any(record is None for record in records):
            raise ValueError("GDN RecoverSSM layer has no records")
        reference_state, reference_records = states[0], records[0]
        if reference_state.ndim != 4:
            raise ValueError("GDN RecoverSSM state must be four-dimensional")
        _, num_v_heads, head_v_dim, head_k_dim = reference_state.shape
        for state in states:
            if (
                state.shape[1:] != reference_state.shape[1:]
                or state.dtype != reference_state.dtype
                or state.device != reference_state.device
                or state.stride()[1:] != (head_v_dim * head_k_dim, head_k_dim, 1)
            ):
                raise ValueError("GDN RecoverSSM layers need one state layout")
        for record in records:
            for tensor, reference in zip(
                (record.correction, record.key, record.gate),
                (
                    reference_records.correction,
                    reference_records.key,
                    reference_records.gate,
                ),
            ):
                if (
                    tensor.shape != reference.shape
                    or tensor.dtype != torch.float32
                    or not tensor.is_contiguous()
                    or tensor.device != reference_state.device
                ):
                    raise ValueError("GDN RecoverSSM layers need one record layout")
        if reference_records.correction.shape[1] != num_v_heads:
            raise ValueError("GDN RecoverSSM records do not match the state heads")
        device = reference_state.device

        return cls(
            states=states,
            records=records,
            state_base_addrs=collect_base_addresses(states, device),
            state_block_strides=torch.tensor(
                [state.stride(0) for state in states], dtype=torch.int64, device=device
            ),
            correction_base_addrs=collect_base_addresses(
                [record.correction for record in records], device
            ),
            key_base_addrs=collect_base_addresses(
                [record.key for record in records], device
            ),
            gate_base_addrs=collect_base_addresses(
                [record.gate for record in records], device
            ),
        )

    def commit(
        self,
        num_sampled: torch.Tensor,
        source_blocks: torch.Tensor,
        query_start_loc: torch.Tensor,
        request_indices: torch.Tensor | None = None,
        num_computed_tokens: torch.Tensor | None = None,
        block_table: torch.Tensor | None = None,
        mamba_block_size: int | None = None,
    ) -> None:
        """Recover the accepted states of every speculative row in every layer.

        ``num_sampled``, ``num_computed_tokens`` (before the step) and
        ``block_table`` are indexed by batch row; ``request_indices`` maps each
        speculative row to its batch row and is None when they coincide. The
        three align arguments must be given together.
        """
        num_rows = source_blocks.shape[0]
        if num_rows == 0:

            return
        align_arguments = (num_computed_tokens, block_table, mamba_block_size)
        if any(argument is None for argument in align_arguments) and any(
            argument is not None for argument in align_arguments
        ):
            raise ValueError("GDN RecoverSSM align metadata is incomplete")
        reference_records = self.records[0]
        if num_rows > reference_records.num_rows:
            raise ValueError("GDN RecoverSSM commit exceeds its record rows")
        if query_start_loc.shape[0] < num_rows + 1:
            raise ValueError("GDN RecoverSSM commit query metadata is too short")
        if block_table is not None and block_table.stride(1) != 1:
            raise ValueError("GDN RecoverSSM block table rows must be contiguous")
        reference_state = self.states[0]
        _, num_v_heads, head_v_dim, head_k_dim = reference_state.shape
        num_k_heads = reference_records.key.shape[1]
        block_v = min(triton.next_power_of_2(head_v_dim), COMMIT_BLOCK_V)
        grid = (
            triton.cdiv(head_v_dim, block_v),
            num_rows,
            len(self.states) * num_v_heads,
        )
        for checkpoint_only in ((True, False) if block_table is not None else (False,)):
            checkpoint_table = block_table if checkpoint_only else None
            _gdn_recoverssm_commit_kernel[grid](
                reference_state,
                self.state_base_addrs,
                self.state_block_strides,
                reference_records.correction,
                self.correction_base_addrs,
                reference_records.key,
                self.key_base_addrs,
                reference_records.gate,
                self.gate_base_addrs,
                source_blocks,
                query_start_loc,
                num_sampled,
                request_indices,
                num_computed_tokens if checkpoint_only else None,
                checkpoint_table,
                source_blocks.stride(0),
                0 if checkpoint_table is None else checkpoint_table.stride(0),
                0 if checkpoint_table is None else checkpoint_table.shape[1],
                num_rows,
                H=num_k_heads,
                HV=num_v_heads,
                K=head_k_dim,
                V=head_v_dim,
                BK=triton.next_power_of_2(head_k_dim),
                BV=block_v,
                SPEC_QUERY_LEN=reference_records.spec_query_len,
                RECORD_ROWS=reference_records.num_rows,
                MAMBA_BLOCK_SIZE=mamba_block_size or 1,
                num_warps=COMMIT_NUM_WARPS,
                num_stages=2,
            )


__all__ = [
    "GDNRecoverSSMCommitContext",
    "GDNRecoverSSMRecords",
    "NULL_BLOCK_ID",
    "allocate_gdn_recoverssm_records",
    "gdn_recoverssm_verify",
]
