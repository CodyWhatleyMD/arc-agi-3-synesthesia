EDITS = [
(
"    def _select_recoverssm_rows(\n"
"        self,\n"
"        draft_rows_cpu: torch.Tensor,\n"
"        common_attn_metadata: CommonAttentionMetadata,\n"
"    ) -> torch.Tensor:\n"
"        \"\"\"Return the rows RecoverSSM verifies: every decode row, drafts or not.\n"
"\n"
"        A decode row without drafts continues from the running block and from\n"
"        a convolution window shifted by the previous acceptance, which only the\n"
"        speculative convolution path honours. Prefill chunks and rows longer\n"
"        than one MTP window stay on the prefill path.\n"
"        \"\"\"\n"
"        is_prefilling = common_attn_metadata.is_prefilling\n"
"        if is_prefilling is None:\n"
"\n"
"            return draft_rows_cpu\n"
"        query_lens_cpu = common_attn_metadata.query_start_loc_cpu.diff()\n"
"        decode_rows_cpu = (\n"
"            ~is_prefilling\n"
"            & (query_lens_cpu > 0)\n",
"    def _select_recoverssm_rows(\n"
"        self,\n"
"        draft_rows_cpu: torch.Tensor,\n"
"        common_attn_metadata: CommonAttentionMetadata,\n"
"        past_prefill_rows_cpu: torch.Tensor | None = None,\n"
"    ) -> torch.Tensor:\n"
"        \"\"\"Return the rows RecoverSSM verifies: every decode row, drafts or not.\n"
"\n"
"        A decode row without drafts continues from the running block and from\n"
"        a convolution window shifted by the previous acceptance, which only the\n"
"        speculative convolution path honours. Prefill chunks and rows longer\n"
"        than one MTP window stay on the prefill path.\n"
"\n"
"        ``past_prefill_rows_cpu`` marks the rows whose prefill had ended before\n"
"        the step. Model Runner V2 also runs a one-token prompt extension as a\n"
"        decode (``is_prefilling`` False), but before the prompt ends that row\n"
"        samples nothing and the commit would drop its token, so such a row stays\n"
"        off the RecoverSSM path unless it carries drafts. Without the mask,\n"
"        ``is_prefilling`` stands in.\n"
"        \"\"\"\n"
"        is_prefilling = common_attn_metadata.is_prefilling\n"
"        if past_prefill_rows_cpu is None:\n"
"            if is_prefilling is None:\n"
"\n"
"                return draft_rows_cpu\n"
"            past_prefill_rows_cpu = ~is_prefilling\n"
"        query_lens_cpu = common_attn_metadata.query_start_loc_cpu.diff()\n"
"        decode_rows_cpu = (\n"
"            past_prefill_rows_cpu\n"
"            & (query_lens_cpu > 0)\n",
),
(
"        num_decode_draft_tokens_cpu: torch.Tensor | None = None,\n"
"        fast_build: bool = False,\n"
"    ) -> GDNAttentionMetadata:\n",
"        num_decode_draft_tokens_cpu: torch.Tensor | None = None,\n"
"        fast_build: bool = False,\n"
"        recoverssm_decode_rows_cpu: torch.Tensor | None = None,\n"
"    ) -> GDNAttentionMetadata:\n",
),
(
"                spec_sequence_masks_cpu = self._select_recoverssm_rows(\n"
"                    spec_sequence_masks_cpu, m\n"
"                )\n",
"                spec_sequence_masks_cpu = self._select_recoverssm_rows(\n"
"                    spec_sequence_masks_cpu, m, recoverssm_decode_rows_cpu\n"
"                )\n",
),
]
