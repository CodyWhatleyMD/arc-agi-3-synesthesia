"""ARC3 TP=1 BF16 projections selected on RTX PRO 6000 Blackwell.

Only target-model M=40/44/48/52/56/64 uses these plans, the padded MTP3 decode
rows of up to 16 sequences. Other shapes use the original linear method.
Weights are never repacked or copied. Split-K scratch is a
temporary FP32 tensor managed by the CUDA graph allocator.
Set VLLM_ARC3_SM120_GEMM=0 before server startup to retain rc1 dispatch.
"""

import os

import torch
import triton
import triton.language as tl

from vllm import envs
from vllm.logger import init_logger
from vllm.model_executor.layers.linear import UnquantizedLinearMethod
from vllm.platforms import current_platform

logger = init_logger(__name__)

GEMM_ROWS = (40, 44, 48, 52, 56, 64)
# (output width, input width), (column tile, K tile, split count, row tile).
PROJECTIONS = {
    "attn_hyper_connection.input_mix_weight_down_block_inject": (
        (336, 10240),
        (32, 64, 16, 32),
    ),
    "mlp_hyper_connection.input_mix_weight_down_block_inject": (
        (336, 10240),
        (32, 64, 16, 32),
    ),
    "attn_hyper_connection.input_mix_weight_up": ((10240, 320), (64, 64, 1, 64)),
    "mlp_hyper_connection.input_mix_weight_up": ((10240, 320), (64, 64, 1, 64)),
    "mlp.gate": ((512, 2560), (32, 64, 16, 32)),
    "mlp.shared_expert.gate_up_proj": ((1280, 2560), (64, 64, 8, 32)),
    "mlp.shared_expert.down_proj": ((2560, 640), (32, 64, 1, 32)),
    "self_attn.indexer.index_qk_proj": ((640, 2560), (32, 128, 8, 32)),
    "linear_attn.in_proj_ba": ((96, 2560), (32, 64, 16, 32)),
}


@triton.jit
def compute_partial_gemm(
    inputs,
    weights,
    partials,
    ROWS: tl.constexpr,
    COLUMNS: tl.constexpr,
    INNER: tl.constexpr,
    BLOCK_ROWS: tl.constexpr,
    BLOCK_COLUMNS: tl.constexpr,
    BLOCK_INNER: tl.constexpr,
    SPLITS: tl.constexpr,
):
    row_indices = tl.program_id(0) * BLOCK_ROWS + tl.arange(0, BLOCK_ROWS)
    column_indices = tl.program_id(1) * BLOCK_COLUMNS + tl.arange(0, BLOCK_COLUMNS)
    split_index = tl.program_id(2)
    inner_indices = split_index * BLOCK_INNER + tl.arange(0, BLOCK_INNER)
    accumulator = tl.full((BLOCK_ROWS, BLOCK_COLUMNS), 0, tl.float32)
    for chunk in range(tl.cdiv(INNER, BLOCK_INNER * SPLITS)):
        positions = inner_indices + chunk * BLOCK_INNER * SPLITS
        input_values = tl.load(
            inputs + row_indices[:, None] * INNER + positions[None, :],
            (row_indices[:, None] < ROWS) & (positions[None, :] < INNER),
            0,
        )
        weight_values = tl.load(
            weights + column_indices[None, :] * INNER + positions[:, None],
            (column_indices[None, :] < COLUMNS) & (positions[:, None] < INNER),
            0,
        )
        accumulator = tl.dot(input_values, weight_values, accumulator)
    offsets = (
        split_index * ROWS * COLUMNS
        + row_indices[:, None] * COLUMNS
        + column_indices[None, :]
    )
    tl.store(
        partials + offsets,
        accumulator,
        (row_indices[:, None] < ROWS) & (column_indices[None, :] < COLUMNS),
    )


@triton.jit
def reduce_partial_gemm(
    partials,
    output,
    ELEMENTS: tl.constexpr,
    SPLITS: tl.constexpr,
    BLOCK: tl.constexpr,
):
    offsets = tl.program_id(0) * BLOCK + tl.arange(0, BLOCK)
    accumulator = tl.full((BLOCK,), 0, tl.float32)
    for split_index in range(SPLITS):
        accumulator += tl.load(
            partials + split_index * ELEMENTS + offsets, offsets < ELEMENTS, 0
        )
    tl.store(output + offsets, accumulator, offsets < ELEMENTS)


def run_gemm(inputs, weights, plan):
    rows, inner = inputs.shape
    columns = weights.shape[0]
    block_columns, block_inner, splits, block_rows = plan
    output = torch.empty((rows, columns), device=inputs.device, dtype=inputs.dtype)
    partials = (
        output
        if splits == 1
        else torch.empty(
            (splits, rows, columns), device=inputs.device, dtype=torch.float32
        )
    )
    compute_partial_gemm[
        (triton.cdiv(rows, block_rows), triton.cdiv(columns, block_columns), splits)
    ](
        inputs,
        weights,
        partials,
        rows,
        columns,
        inner,
        block_rows,
        block_columns,
        block_inner,
        splits,
        num_warps=4,
    )
    if splits > 1:
        reduce_partial_gemm[(triton.cdiv(rows * columns, 256),)](
            partials, output, rows * columns, splits, 256
        )

    return output


class Arc3Sm120LinearMethod(UnquantizedLinearMethod):
    def __init__(self, original, shape, plan):
        self._gemm_impl = original._gemm_impl
        self.arc3_shape = shape
        self.arc3_plan = plan

    def apply(self, layer, x, bias=None):
        weight = layer.weight
        if (
            not envs.VLLM_BATCH_INVARIANT
            and bias is None
            and x.ndim == 2
            and x.shape[0] in GEMM_ROWS
            and x.shape[1] == self.arc3_shape[1]
            and tuple(weight.shape) == self.arc3_shape
            and x.dtype == weight.dtype == torch.bfloat16
            and x.is_cuda
            and weight.device == x.device
            and x.is_contiguous()
            and weight.is_contiguous()
        ):

            return run_gemm(x, weight, self.arc3_plan)

        return super().apply(layer, x, bias)


def install_sm120_projections(decoder, vllm_config, prefix):
    enabled = os.environ.get("VLLM_ARC3_SM120_GEMM", "1")
    if enabled not in ("0", "1"):
        raise ValueError("VLLM_ARC3_SM120_GEMM must be 0 or 1")
    parallel = vllm_config.parallel_config
    if (
        enabled == "0"
        or "mtp" in prefix.split(".")
        or envs.VLLM_BATCH_INVARIANT
        or parallel.tensor_parallel_size != 1
        or parallel.pipeline_parallel_size != 1
        or parallel.decode_context_parallel_size != 1
        or parallel.prefill_context_parallel_size != 1
        or not current_platform.is_cuda()
        or current_platform.get_device_capability() != (12, 0)
    ):

        return 0
    installed = 0
    for name, layer in decoder.named_modules():
        specification = PROJECTIONS.get(name)
        if (
            specification is None
            or type(getattr(layer, "quant_method", None)) is not UnquantizedLinearMethod
        ):
            continue
        shape, plan = specification
        if tuple(layer.weight.shape) != shape or layer.weight.dtype != torch.bfloat16:
            continue
        layer.quant_method = Arc3Sm120LinearMethod(layer.quant_method, shape, plan)
        installed += 1
    logger.info_once(
        "ARC3 rc3 SM120 GEMM enabled for target M=40/44/48/52/56/64; first decoder installs %d projections; set VLLM_ARC3_SM120_GEMM=0 before startup for rc1 dispatch",
        installed,
    )

    return installed
