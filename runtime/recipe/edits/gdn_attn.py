EDITS = [(
    "            # Not isinstance: KDA's RecoverSSM/checkpoint metadata is per group.\n"
    "            and type(self) is GDNAttentionMetadataBuilder\n"
    "        )\n",
    "            # Not isinstance: KDA's RecoverSSM/checkpoint metadata is per group.\n"
    "            and type(self) is GDNAttentionMetadataBuilder\n"
    "            # ARC3 GDN RecoverSSM metadata is per group too: its commit rows,\n"
    "            # source blocks and layer context belong to one group, and a\n"
    "            # replace() copy would commit the first group once per group.\n"
    "            and not self.use_recoverssm\n"
    "        )\n",
)]
