# Han Solo's "mixed compressed-tensors PLE safeguard" lived in vllm/models/qwen4_exp/nvidia/ngram_embedding.py
# at e975732. Upstream #57497 (267eee54b) moved Qwen4ExpPLEEmbeddingMethod.from_quant_config into
# vllm/models/qwen4_exp/common/ngram_embedding.py unchanged, so the safeguard is re-applied there, verbatim.
EDITS = [
(
"from vllm.model_executor.layers.quantization.fp8 import Fp8Config\n",
"from vllm.model_executor.layers.quantization.compressed_tensors import (\n"
"    compressed_tensors,\n"
")\n"
"from vllm.model_executor.layers.quantization.fp8 import Fp8Config\n",
),
(
'        """Select the concrete PLE embedding format for a layer."""\n'
'        if embedding_dtype == "float8_e4m3fn":\n',
'        """Select the concrete PLE embedding format for a layer.\n'
'\n'
'        Mixed compressed-tensors checkpoints declare FP8 PLE metadata while\n'
'        storing BF16 shards without a scale, so their tables stay unquantized.\n'
'        """\n'
'        if isinstance(quant_config, compressed_tensors.CompressedTensorsConfig):\n'
'            return Qwen4ExpPLEUnquantizedEmbeddingMethod()\n'
'        if embedding_dtype == "float8_e4m3fn":\n',
),
]
