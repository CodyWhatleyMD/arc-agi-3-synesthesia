# Upstream #58957 (d6cce94fd) serves input_mix_weight_down_block_inject with a fused CuTe-DSL
# down+SiLU kernel for M <= 48 (split-K configs tuned for SM100f). On the RTX PRO 6000 (sm_120),
# bench_hc_down.py --all-m measured, in us (median CUDA-graph replay, 336 x 10240 BF16):
#   M         1     2     4     8    16    24    32    40    44    48
#   e975732  6.40  6.40  6.77  6.91  7.28  7.63  7.93  7.53  7.64  7.73  (linear + hc_silu; his GEMM at 40-48)
#   fused    3.34  3.63  5.49  7.31  8.16 11.28 11.38 16.13 16.51 16.75
# so where Han Solo's SM120 GEMM is installed on this projection (TP1 sm_120, VLLM_ARC3_SM120_GEMM=1),
# the fused kernel serves only M <= 4 and e975732's dispatch serves the rest. Elsewhere upstream
# dispatch is unchanged.
EDITS = [
(
"from .ops.cute_dsl.hc_down_silu import MAX_FUSED_M, hc_down_silu\n",
"from .ops.cute_dsl.hc_down_silu import MAX_FUSED_M, hc_down_silu\n"
"\n"
"# ARC3: the largest M at which the fused down+SiLU kernel beats e975732's dispatch on sm_120\n"
"# (Han Solo's SM120 GEMM at its rows, the linear method below them); see the port recipe.\n"
"ARC3_SM120_MAX_FUSED_M = 4\n",
),
(
"        use_fused = (\n"
"            self._use_hc_down_silu\n"
"            and not envs.VLLM_BATCH_INVARIANT\n"
"            and 1 <= xn.shape[0] <= MAX_FUSED_M\n"
"        )\n",
"        use_fused = (\n"
"            self._use_hc_down_silu\n"
"            and not envs.VLLM_BATCH_INVARIANT\n"
"            and 1 <= xn.shape[0] <= MAX_FUSED_M\n"
"            # ARC3: with the SM120 GEMM installed on this projection, keep e975732's\n"
"            # faster dispatch above ARC3_SM120_MAX_FUSED_M rows.\n"
"            and not (\n"
"                getattr(self.input_mix_weight_down_block_inject.quant_method, \"arc3_shape\", None)\n"
"                is not None\n"
"                and xn.shape[0] > ARC3_SM120_MAX_FUSED_M\n"
"            )\n"
"        )\n",
),
]
