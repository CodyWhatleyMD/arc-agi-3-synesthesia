EDITS = [
(
"    num_decode_draft_tokens_cpu: torch.Tensor | None = None\n"
"\n"
"    def get_extra_common_attn_kwargs(\n",
"    num_decode_draft_tokens_cpu: torch.Tensor | None = None\n"
"    # ARC3 GDN RecoverSSM: the rows past their prefill. Model Runner V2 runs a\n"
"    # one-token prompt extension as a decode, but before the prompt ends that\n"
"    # row samples nothing, and RecoverSSM only commits sampled tokens.\n"
"    recoverssm_decode_rows_cpu: torch.Tensor | None = None\n"
"\n"
"    def get_extra_common_attn_kwargs(\n",
),
(
"        return {\n"
"            \"num_accepted_tokens\": None\n"
"            if self.num_accepted_tokens is None\n"
"            else self.num_accepted_tokens[:num_reqs],\n"
"            \"num_decode_draft_tokens_cpu\": None\n"
"            if self.num_decode_draft_tokens_cpu is None\n"
"            else self.num_decode_draft_tokens_cpu[:num_reqs],\n"
"        }\n",
"        kwargs = {\n"
"            \"num_accepted_tokens\": None\n"
"            if self.num_accepted_tokens is None\n"
"            else self.num_accepted_tokens[:num_reqs],\n"
"            \"num_decode_draft_tokens_cpu\": None\n"
"            if self.num_decode_draft_tokens_cpu is None\n"
"            else self.num_decode_draft_tokens_cpu[:num_reqs],\n"
"        }\n"
"        if self.recoverssm_decode_rows_cpu is not None and getattr(\n"
"            attn_metadata_builder, \"use_recoverssm\", False\n"
"        ):\n"
"            kwargs[\"recoverssm_decode_rows_cpu\"] = self.recoverssm_decode_rows_cpu[\n"
"                :num_reqs\n"
"            ]\n"
"        return kwargs\n",
),
(
"        num_accepted_tokens = None\n"
"        num_decode_draft_tokens_cpu = None\n"
"        if not for_capture and self.vllm_config.num_speculative_tokens > 0:\n",
"        num_accepted_tokens = None\n"
"        num_decode_draft_tokens_cpu = None\n"
"        recoverssm_decode_rows_cpu = None\n"
"        # getattr: unit tests build this state without __init__ (upstream\n"
"        # test_prepare_attn_forwards_positions); stock prepare_attn never needs it.\n"
"        if getattr(self, \"_gdn_recoverssm\", False) and not for_capture:\n"
"            recoverssm_decode_rows_cpu = torch.zeros(\n"
"                num_reqs, dtype=torch.bool, device=\"cpu\"\n"
"            )\n"
"            recoverssm_decode_rows_cpu[: input_batch.num_reqs] = torch.from_numpy(\n"
"                ~input_batch.is_prefilling_np\n"
"            )\n"
"        if not for_capture and self.vllm_config.num_speculative_tokens > 0:\n",
),
(
"        mamba_attn_metadata = MambaHybridAttnMetadata(\n"
"            is_prefilling=is_prefilling,\n"
"            num_accepted_tokens=num_accepted_tokens,\n"
"            num_decode_draft_tokens_cpu=num_decode_draft_tokens_cpu,\n"
"        )\n",
"        mamba_attn_metadata = MambaHybridAttnMetadata(\n"
"            is_prefilling=is_prefilling,\n"
"            num_accepted_tokens=num_accepted_tokens,\n"
"            num_decode_draft_tokens_cpu=num_decode_draft_tokens_cpu,\n"
"            recoverssm_decode_rows_cpu=recoverssm_decode_rows_cpu,\n"
"        )\n",
),
]
