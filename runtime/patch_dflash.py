#!/usr/bin/env python3
"""Post-install patch: serve a DFlash2 drafter against Qwen3.8-Flash-Next on our vLLM 0.31.0 runtime.

vLLM 0.31.0 already ships the DFlash2 drafter (DFlash2DraftModel, V2 runner speculator) but Flash-Next cannot use it:
vllm-project/vllm#56088 lists the blockers. Three apply to a stock-layout DFlash2 drafter (incoai's), and this
patch fixes those three:

1. vllm/model_executor/models/config.py -- Qwen4Exp's speculative-method allowlist is {mtp, ngram, ngram_gpu};
   add "dflash" (checked before weights load).
2. vllm/v1/worker/gpu/model_runner.py -- the V2 runner subscripts get_mtp_target_hidden_states() unguarded, and
   Qwen4Exp returns None when no MTP head is loaded; fall back to the runner's own hidden states (two sites).
3. vllm/models/qwen4_exp/nvidia/model.py (our overlay member) -- Qwen4Exp does not emit auxiliary hidden states.
   incoai/Qwen3.8-Flash-Next-DFlash2 was trained (its SGLang capture patch, patches/qwen38-dflash2-capture.patch)
   on the COMPLETED outputs of zero-based layers 5,15,25,35,45, averaged over the 4 hyper-connection streams.
   vLLM asks for target_layer_ids + 1 = (6,16,26,36,46), meaning "the stream entering layer L", i.e. the completed
   output of layer L-1. The capture materializes that stream with the layer's own HC combine (hc_combine writes a
   fresh tensor; the forward pass is unchanged) and averages the streams. The DeepSpec-only parts of PixelML's
   overlay (anchor-as-first-prediction, query_zero_predicts_next) are NOT applied: incoai's drafter uses vLLM's
   standard 1+N DFlash layout.

Run on the directory that directly contains the vllm package, after the runtime's installer:
    python3 -I patch_dflash.py DIST_PACKAGES
Each file is hash-pinned: the pinned installed bytes (patched) or the pinned patched bytes (left alone); anything
else is refused before any file is written. Writes are atomic. Inert unless the server is started with
--speculative-config '{"method": "dflash", ...}': without it no aux layers are set and every edit is a no-op path.
"""
import hashlib
import os
import sys
from pathlib import Path

MODEL_RUNNER_GUARD_1 = (
    '''            if hasattr(self.model, "get_mtp_target_hidden_states"):
                pre_hc_hidden_states = self.model.get_mtp_target_hidden_states()
                spec_hidden_states = pre_hc_hidden_states[: hidden_states.shape[0]]  # type: ignore[union-attr]
''',
    '''            if hasattr(self.model, "get_mtp_target_hidden_states"):
                pre_hc_hidden_states = self.model.get_mtp_target_hidden_states()
                # ARC3 (vllm#56088 item 2): Qwen4Exp returns None when no MTP head is loaded (method=dflash).
                if pre_hc_hidden_states is not None:
                    spec_hidden_states = pre_hc_hidden_states[: hidden_states.shape[0]]
''')
MODEL_RUNNER_GUARD_2 = (
    '''            if hasattr(self.model, "get_mtp_target_hidden_states"):
                pre_hc_hidden_states = self.model.get_mtp_target_hidden_states()
                spec_hidden_states = pre_hc_hidden_states[: draft_hidden_states.size(0)]
''',
    '''            if hasattr(self.model, "get_mtp_target_hidden_states"):
                pre_hc_hidden_states = self.model.get_mtp_target_hidden_states()
                # ARC3 (vllm#56088 item 2): Qwen4Exp returns None when no MTP head is loaded (method=dflash).
                if pre_hc_hidden_states is not None:
                    spec_hidden_states = pre_hc_hidden_states[: draft_hidden_states.size(0)]
''')

CONFIG_ALLOW = (
    '''        if spec_config is not None and spec_config.method not in {
            "mtp",
            "ngram",
            "ngram_gpu",
        }:
''',
    '''        if spec_config is not None and spec_config.method not in {
            "mtp",
            "dflash",  # ARC3: patch_dflash.py makes Qwen4Exp emit the drafter's auxiliary hidden states
            "ngram",
            "ngram_gpu",
        }:
''')

# --- our overlay model.py ---------------------------------------------------------------------------------------
MODEL_LOOP_INIT = (
    '''        block_output = None
        injection = None
        last_layer = None
        if self.start_layer < self.end_layer:
''',
    '''        block_output = None
        injection = None
        last_layer = None
        # ARC3 DFlash: aux layer L = the stream entering layer L (completed output of layer L-1), averaged over
        # the hyper-connection streams, as incoai's DFlash2 drafter was trained (empty unless method=dflash).
        aux_layers = self._arc3_aux_layers
        aux_hidden_states: list[torch.Tensor] = []
        if self.start_layer < self.end_layer:
''')
MODEL_LOOP_CAPTURE = (
    '''                hidden_states = hidden_states + deepstack_embed

        if not get_pp_group().is_last_rank:
''',
    '''                hidden_states = hidden_states + deepstack_embed
            if aux_layers and (layer_idx + 1) in aux_layers:
                completed = (
                    layer.mlp_hyper_connection.combine(hidden_states, block_output, injection)
                    if block_output is not None
                    else hidden_states
                )
                aux_hidden_states.append(
                    completed.unflatten(-1, (self.config.hc_count, self.config.hidden_size)).mean(dim=-2)
                )

        if not get_pp_group().is_last_rank:
''')
MODEL_RETURN = (
    '''            num_tokens = multi_hidden.shape[0]
            self._mtp_hidden_buffer[:num_tokens].copy_(multi_hidden)
        return sample_hidden_states
''',
    '''            num_tokens = multi_hidden.shape[0]
            self._mtp_hidden_buffer[:num_tokens].copy_(multi_hidden)
        if aux_layers:
            if len(aux_hidden_states) != len(aux_layers):
                raise RuntimeError(
                    f"ARC3 DFlash: captured {len(aux_hidden_states)} aux hidden states for layers {aux_layers}"
                )
            return sample_hidden_states, aux_hidden_states
        return sample_hidden_states
''')
MODEL_INIT_AUX = (
    '''        else:
            self._mtp_hidden_buffer = None

    def embed_input_ids(self, input_ids: torch.Tensor) -> torch.Tensor:
        return self.embed_tokens(input_ids)
''',
    '''        else:
            self._mtp_hidden_buffer = None
        self._arc3_aux_layers: tuple[int, ...] = ()

    def set_arc3_aux_layers(self, layers: tuple[int, ...]) -> None:
        """ARC3 DFlash: capture the streams entering these layers (vLLM's target_layer_ids + 1)."""
        layers = tuple(int(x) for x in layers)
        if self.start_layer != 0 or not all(0 < x <= self.end_layer for x in layers):
            raise ValueError(f"ARC3 DFlash aux layers {layers} need PP1 and 1..{self.end_layer}")
        self._arc3_aux_layers = layers

    def embed_input_ids(self, input_ids: torch.Tensor) -> torch.Tensor:
        return self.embed_tokens(input_ids)
''')
MODEL_CONDGEN = (
    '''    def get_mtp_target_hidden_states(self) -> torch.Tensor | None:
        return self.language_model.get_mtp_target_hidden_states()

    def forward(
''',
    '''    def get_mtp_target_hidden_states(self) -> torch.Tensor | None:
        return self.language_model.get_mtp_target_hidden_states()

    # ARC3 DFlash: the SupportsEagle3 members vLLM's aux-hidden-state path checks for (runtime Protocol).
    supports_eagle3 = True
    has_own_embed_tokens = False
    has_own_lm_head = False

    def set_aux_hidden_state_layers(self, layers: tuple[int, ...]) -> None:
        self.language_model.model.set_arc3_aux_layers(layers)

    def get_eagle3_default_aux_hidden_state_layers(self) -> tuple[int, ...]:
        # incoai/Qwen3.8-Flash-Next-DFlash2: target_layer_ids [5, 15, 25, 35, 45], + 1
        return (6, 16, 26, 36, 46)

    def forward(
''')

# target -> list of edits, and installed sha256 -> (runtime, patched sha256); patched hashes filled by make step.
TARGETS = {
    'vllm/model_executor/models/config.py': [CONFIG_ALLOW],
    'vllm/v1/worker/gpu/model_runner.py': [MODEL_RUNNER_GUARD_1, MODEL_RUNNER_GUARD_2],
    'vllm/models/qwen4_exp/nvidia/model.py': [MODEL_INIT_AUX, MODEL_LOOP_INIT, MODEL_LOOP_CAPTURE, MODEL_RETURN,
                                              MODEL_CONDGEN],
}
PINS = {
    'vllm/model_executor/models/config.py': {
        '03bec47631bfd2b70614bfec2b208d87cbcc3ee2a785656e3723574c51f96d03': ('v0.31.0 db9527a4', 'fcdc67b2b48c5e22269d9b051512c74cf56fa81b76c0869fbf193ab06945bcde'),
    },
    'vllm/v1/worker/gpu/model_runner.py': {
        '725c47114e148ade3a26b4cc9c5f7295588fdd387afc3cb5fdb2d16513a1bb5c': ('v0.31.0 db9527a4', 'da0e94cf04cc0bc72d1850598527d26e89ff09469bb05e7c6dbd81037328fd8c'),
    },
    'vllm/models/qwen4_exp/nvidia/model.py': {
        'eb09565f6b801f663ff156cff3f4e2bfa454f6c57e575f2682665744f3c3a3bc': ('v0.31.0 overlay 4848d189', '0a93a112f46162687871d6c2b96acfd159e3408ba6faede22781812aadee28a8'),
    },
}


def apply_edits(text: str, edits: list[tuple[str, str]], name: str) -> str:
    for old, new in edits:
        n = text.count(old)
        if n != 1:
            raise SystemExit(f"ARC3 DFlash patch: anchor occurs {n} times in {name}: {old[:70]!r}")
        text = text.replace(old, new, 1)
    return text


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch_dflash.py DIST_PACKAGES")
    root = Path(sys.argv[1])
    plan = []
    for rel, edits in TARGETS.items():
        target = root / rel
        data = target.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        pins = PINS[rel]
        if digest in {p for _, p in pins.values()}:
            print(f"ARC3 DFlash patch: already patched ({digest[:12]}) {target}")
            continue
        if digest not in pins:
            raise SystemExit(f"ARC3 DFlash patch: {target} has sha256 {digest}, neither pinned installed nor pinned "
                             "patched; nothing written")
        runtime, patched = pins[digest]
        out = apply_edits(data.decode(), edits, rel).encode()
        if hashlib.sha256(out).hexdigest() != patched:
            raise SystemExit(f"ARC3 DFlash patch: edited {rel} does not match its pinned result; nothing written")
        plan.append((target, out, runtime, digest, patched))
    for target, out, runtime, digest, patched in plan:  # every file verified before any write
        tmp = target.with_name(f".{target.name}.arc3-dflash.tmp")
        tmp.write_bytes(out)
        os.chmod(tmp, target.stat().st_mode & 0o7777)
        os.replace(tmp, target)
        print(f"ARC3 DFlash patch: installed ({runtime}, {digest[:12]} -> {patched[:12]}) {target}")


if __name__ == "__main__":
    main()
