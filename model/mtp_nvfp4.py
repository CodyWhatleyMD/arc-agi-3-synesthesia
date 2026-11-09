#!/usr/bin/env python
"""
mtp_nvfp4.py (2026-10-13): quantize the Flash-Next MTP head's 512 routed experts to NVFP4 (W4A4, group 16),
weights-only, as a post-step on a finished compressed-tensors checkpoint (ours v2.1 -> v2.2).

Why. transformers' Qwen4Exp model ignores ^mtp.* on load, so llm-compressor never sees the MTP head and
quantize.py passes Qwen's BF16 MTP shard through untouched: 4,800 MiB of expert weights on the GPU. At
gpu_memory_utilization 0.98 on Kaggle's 96 GB card that is ~3.4 GiB of KV pool (-15%: 1,259,304 vs 1,479,912
tokens; findings 2026-10-13). Han Solo's checkpoint (primitive-ai mixed-NVFP4-FP8 + its mtp_nvfp4 draft) ships
the same experts as NVFP4 with input_global_scale = 1.0 on every expert (checked 2026-10-13: weights-only RTN,
no activation statistics), and vLLM's W4A4 MoE path loads it. We produce the same layout from OUR checkpoint's
MTP shard (Qwen's original BF16 weights) with the recipe's expert weight observer (nvfp4_expanded_mse),
gate/up sharing one weight_global_scale per expert (vLLM requires w1 == w3), input_global_scale = 1.0
(no activations flow through the MTP head during calibration; the per-16-group activation scales are dynamic).

Output layout, per expert e and proj in gate_proj / up_proj / down_proj (identical to his draft):
  mtp.layers.0.mlp.experts.{e}.{proj}.weight_packed        U8       [out, in/2]
  mtp.layers.0.mlp.experts.{e}.{proj}.weight_scale         F8_E4M3  [out, in/16]
  mtp.layers.0.mlp.experts.{e}.{proj}.weight_global_scale  F32      [1]
  mtp.layers.0.mlp.experts.{e}.{proj}.input_global_scale   F32      [1]   (= 1.0)
The other MTP tensors (attention, shared expert, router, fc_*, norms, hyper-connections) stay BF16 in a carry shard.
config.json: the recipe's blanket ignore 're:^mtp.*' becomes a finer set (self_attn, shared_expert, mlp.gate, fc_*,
hyper_connection, hc_norm, norm, indexer) so vLLM resolves the MTP experts to the NVFP4 MoE scheme and leaves the
rest of the MTP head unquantized -- the same shape as primitive-ai's mtp_nvfp4/config.json. vLLM names the draft's
modules 'mtp.layers.48.*' (mtp_start_layer_idx = num_hidden_layers); the regexes are anchored on '^mtp\\.'.

Usage:
  python mtp_nvfp4.py --src-dir /path/v21 --out-dir /path/v22 [--sidecar-dir /path/v22_sidecar] [--compare his.safetensors]
Unchanged files are hard-linked into --out-dir (same filesystem) so the full checkpoint costs ~1.5 GB of new disk.
"""
import argparse
import json
import os
import re
import struct
import sys
import time

import torch
from safetensors import safe_open
from safetensors.torch import save_file

from compressed_tensors.compressors.nvfp4.base import NVFP4PackedCompressor
from compressed_tensors.quantization import QuantizationArgs, QuantizationScheme
from compressed_tensors.quantization.utils.helpers import calculate_qparams, generate_gparam
from llmcompressor.observers import Observer  # noqa: F401  (registers the observers)

ap = argparse.ArgumentParser()
ap.add_argument("--src-dir", required=True, help="finished compressed-tensors checkpoint (e.g. v2.1)")
ap.add_argument("--out-dir", required=True, help="new checkpoint dir; unchanged files hard-linked")
ap.add_argument("--mtp-shard", default="model_mtp.safetensors")
ap.add_argument("--mtp-prefix", default="mtp.layers.0.mlp.experts")
ap.add_argument("--observer", default="nvfp4_expanded_mse", help="weight observer (the recipe's group_1 observer)")
ap.add_argument("--device", default="cuda:0")
ap.add_argument("--compare", default="", help="another NVFP4 MTP-experts safetensors (e.g. primitive-ai's) to score against the same BF16 source")
ap.add_argument("--sidecar-dir", default="", help="also write ONLY the changed files (config, index, new shards) here")
ap.add_argument("--limit", type=int, default=0, help="debug: quantize only the first N experts (output is then NOT a valid checkpoint)")
a = ap.parse_args()

EXPERTS_SHARD = "model-mtp-experts-nvfp4.safetensors"
CARRY_SHARD = "model-mtp-carry-bf16.safetensors"
MTP_IGNORE = [  # replaces 're:^mtp.*'; mirrors primitive-ai's mtp_nvfp4/config.json, anchored on the draft's prefix
    "re:^mtp\\.fc_.*",
    "re:^mtp\\..*self_attn.*",
    "re:^mtp\\..*shared_expert.*",
    "re:^mtp\\..*mlp\\.gate$",
    "re:^mtp\\..*hyper_connection.*",
    "re:^mtp\\..*hc_norm.*",
    "re:^mtp\\..*norm.*",
    "re:^mtp\\..*indexer.*",
]

W_ARGS = QuantizationArgs(num_bits=4, type="float", strategy="tensor_group", group_size=16, symmetric=True,
                          dynamic=False, observer=a.observer)
A_ARGS = QuantizationArgs(num_bits=4, type="float", strategy="tensor_group", group_size=16, symmetric=True,
                          dynamic="local")
SCHEME = QuantizationScheme(targets=["re:.*mlp\\.experts\\.\\d+\\.(gate_proj|up_proj|down_proj)$"],
                            weights=W_ARGS, input_activations=A_ARGS, format="nvfp4-pack-quantized")


def ct_match(pattern: str, name: str) -> bool:
    """compressed-tensors / vLLM name matching: 're:' -> re.match (anchored at start), else exact."""
    return bool(re.match(pattern[3:], name)) if pattern.startswith("re:") else pattern == name


def selftest_config(ignore: list, targets: list) -> None:
    """The MTP experts must resolve to the NVFP4 group; every other MTP linear must be ignored."""
    quantized = ["mtp.layers.48.mlp.experts.0.gate_proj", "mtp.layers.48.mlp.experts.0.up_proj",
                 "mtp.layers.48.mlp.experts.0.down_proj", "mtp.layers.48.mlp.experts.511.down_proj"]
    ignored = ["mtp.layers.48.self_attn.q_proj", "mtp.layers.48.self_attn.o_proj",
               "mtp.layers.48.self_attn.indexer.index_qk_proj", "mtp.layers.48.mlp.shared_expert.gate_proj",
               "mtp.layers.48.mlp.shared_expert.down_proj", "mtp.layers.48.mlp.shared_expert_gate",
               "mtp.layers.48.mlp.gate", "mtp.fc_embedding", "mtp.fc_hidden",
               "mtp.layers.48.attn_hyper_connection.input_mix_weight_down",
               "mtp.layers.48.mlp_hyper_connection.block_inject_weight", "mtp.hyper_connection_mixer.input_mix_weight_up",
               "lm_head"]
    for n in quantized:
        assert not any(ct_match(p, n) for p in ignore), f"selftest: {n} is ignored"
        assert any(ct_match(p, n) for p in targets), f"selftest: {n} matches no target"
    for n in ignored:
        assert any(ct_match(p, n) for p in ignore), f"selftest: {n} is NOT ignored"
    # the main model must be untouched by the new regexes
    for n in ["model.language_model.layers.3.mlp.experts.0.gate_proj", "model.language_model.layers.3.self_attn.q_proj"]:
        assert not any(ct_match(p, n) for p in MTP_IGNORE), f"selftest: {n} caught by an MTP regex"


def observe(w: torch.Tensor):
    obs = Observer.load_from_registry(a.observer, base_name="weight", args=W_ARGS)
    obs(w)
    st = obs.get_statistics()
    return st["min_vals"], st["max_vals"]


def absmax_of(*stats) -> torch.Tensor:
    m = None
    for mn, mx in stats:
        v = torch.max(mx.max(), -mn.min())
        m = v if m is None else torch.max(m, v)
    return m.reshape(1)


def pack(w: torch.Tensor, mn: torch.Tensor, mx: torch.Tensor, gs: torch.Tensor) -> dict:
    scale, _zp = calculate_qparams(mn, mx, W_ARGS, global_scale=gs)
    # vLLM dequantizes with the stored e4m3 scale: quantize with exactly that value
    scale = scale.to(torch.float8_e4m3fn).to(torch.float32)
    out = NVFP4PackedCompressor.compress({"weight": w, "weight_scale": scale, "weight_global_scale": gs}, SCHEME)
    out["input_global_scale"] = torch.ones(1, dtype=torch.float32)
    out["weight_global_scale"] = gs.to(torch.float32)
    return {k: v.detach().to("cpu").contiguous() for k, v in out.items()}


def dequant(sd: dict, dtype=torch.float32) -> torch.Tensor:
    d = NVFP4PackedCompressor.decompress({"weight_packed": sd["weight_packed"], "weight_scale": sd["weight_scale"],
                                          "weight_global_scale": sd["weight_global_scale"]}, SCHEME)
    return d["weight"].to(dtype)


def rel_rmse(ref: torch.Tensor, approx: torch.Tensor) -> float:
    ref = ref.to(torch.float32); approx = approx.to(torch.float32)
    return float(torch.linalg.vector_norm(approx - ref) / torch.linalg.vector_norm(ref))


def header_total_bytes(path: str) -> int:
    with open(path, "rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        h = json.loads(f.read(n))
    return sum(v["data_offsets"][1] - v["data_offsets"][0] for k, v in h.items() if k != "__metadata__")


def main() -> int:
    t0 = time.time()
    src, out = os.path.abspath(a.src_dir), os.path.abspath(a.out_dir)
    assert os.path.isdir(src), src
    os.makedirs(out, exist_ok=True)
    dev = torch.device(a.device)

    cfg = json.load(open(os.path.join(src, "config.json")))
    q = cfg["quantization_config"]
    assert "re:^mtp.*" in q["ignore"], "config.json ignore has no 're:^mtp.*' -- is this our checkpoint?"
    targets = [t for g in q["config_groups"].values() for t in g["targets"]]
    new_ignore = [x for x in q["ignore"] if x != "re:^mtp.*"] + MTP_IGNORE
    selftest_config(new_ignore, targets)

    idx = json.load(open(os.path.join(src, "model.safetensors.index.json")))
    wm = idx["weight_map"]
    mtp_keys = sorted(k for k, v in wm.items() if v == a.mtp_shard)
    assert mtp_keys, f"no tensors mapped to {a.mtp_shard}"
    k_gu, k_dn = f"{a.mtp_prefix}.gate_up_proj", f"{a.mtp_prefix}.down_proj"
    assert k_gu in mtp_keys and k_dn in mtp_keys, (k_gu, k_dn, mtp_keys[:5])

    f = safe_open(os.path.join(src, a.mtp_shard), framework="pt", device="cpu")
    gate_up = f.get_tensor(k_gu)   # [E, 2I, H]  (HF: linear(x, gate_up[e]).chunk(2) -> gate rows first, then up)
    down = f.get_tensor(k_dn)      # [E, H, I]
    E, two_i, H = gate_up.shape
    I = two_i // 2
    assert down.shape == (E, H, I), down.shape
    assert gate_up.dtype == torch.bfloat16 and down.dtype == torch.bfloat16, (gate_up.dtype, down.dtype)
    print(f"MTP experts: E={E} H={H} I={I} gate_up {tuple(gate_up.shape)} down {tuple(down.shape)} "
          f"({(gate_up.numel()+down.numel())*2/2**20:.0f} MiB BF16)", flush=True)
    carry = {k: f.get_tensor(k) for k in mtp_keys if k not in (k_gu, k_dn)}
    print(f"carry (stays BF16): {len(carry)} tensors, {sum(t.numel()*t.element_size() for t in carry.values())/2**20:.1f} MiB", flush=True)

    his = None
    if a.compare:
        his = safe_open(a.compare, framework="pt", device="cpu")

    n_exp = a.limit or E
    tensors, errs, errs_his = {}, {"gate_proj": [], "up_proj": [], "down_proj": []}, {"gate_proj": [], "up_proj": [], "down_proj": []}
    gs_log = []
    for e in range(n_exp):
        g = gate_up[e, :I, :].to(dev)
        u = gate_up[e, I:, :].to(dev)
        d = down[e].to(dev)
        sg, su, sd_ = observe(g), observe(u), observe(d)
        if e == 0:
            print(f"observer stats shape gate {tuple(sg[0].shape)} (expect {(I, H // 16)})", flush=True)
            assert tuple(sg[0].shape) == (I, H // 16), sg[0].shape
        gs13 = generate_gparam(-absmax_of(sg, su), absmax_of(sg, su))   # shared by gate and up: vLLM requires w1 == w3
        gs2 = generate_gparam(-absmax_of(sd_), absmax_of(sd_))
        packed = {"gate_proj": pack(g, *sg, gs13), "up_proj": pack(u, *su, gs13), "down_proj": pack(d, *sd_, gs2)}
        for proj, sd in packed.items():
            for name, t in sd.items():
                tensors[f"{a.mtp_prefix}.{e}.{proj}.{name}"] = t
        # fidelity vs the BF16 source, ours and (optionally) his, same reference
        for proj, ref in (("gate_proj", g), ("up_proj", u), ("down_proj", d)):
            errs[proj].append(rel_rmse(ref, dequant(packed[proj]).to(dev)))
            if his is not None:
                pre = f"{a.mtp_prefix}.{e}.{proj}."
                hsd = {n: his.get_tensor(pre + n) for n in ("weight_packed", "weight_scale", "weight_global_scale")}
                errs_his[proj].append(rel_rmse(ref, dequant(hsd).to(dev)))
        gs_log.append((float(gs13), float(gs2)))
        if e % 64 == 0 or e == n_exp - 1:
            print(f"  expert {e:3d}/{n_exp}: gs13 {float(gs13):9.1f} gs2 {float(gs2):9.1f} "
                  f"relRMSE gate {errs['gate_proj'][-1]:.4f} up {errs['up_proj'][-1]:.4f} down {errs['down_proj'][-1]:.4f}"
                  + (f" | his {errs_his['gate_proj'][-1]:.4f} {errs_his['up_proj'][-1]:.4f} {errs_his['down_proj'][-1]:.4f}" if his else ""),
                  flush=True)

    # layout check against the proven layout
    e0 = f"{a.mtp_prefix}.0."
    exp_shapes = {"gate_proj.weight_packed": ((I, H // 2), torch.uint8), "gate_proj.weight_scale": ((I, H // 16), torch.float8_e4m3fn),
                  "down_proj.weight_packed": ((H, I // 2), torch.uint8), "down_proj.weight_scale": ((H, I // 16), torch.float8_e4m3fn),
                  "gate_proj.weight_global_scale": ((1,), torch.float32), "gate_proj.input_global_scale": ((1,), torch.float32)}
    for n, (shp, dt) in exp_shapes.items():
        t = tensors[e0 + n]
        assert tuple(t.shape) == shp and t.dtype == dt, (n, tuple(t.shape), t.dtype, shp, dt)
    if his is not None:
        for n in exp_shapes:
            ht = his.get_tensor(e0 + n)
            assert tuple(ht.shape) == tuple(tensors[e0 + n].shape) and ht.dtype == tensors[e0 + n].dtype, n
        print("layout identical to the compared file (shapes + dtypes of expert 0)", flush=True)

    # write shards
    save_file(tensors, os.path.join(out, EXPERTS_SHARD), metadata={"format": "pt"})
    save_file(carry, os.path.join(out, CARRY_SHARD), metadata={"format": "pt"})
    # hard-link everything else
    skip = {a.mtp_shard, "model.safetensors.index.json", "config.json", EXPERTS_SHARD, CARRY_SHARD}
    linked = 0
    for fn in sorted(os.listdir(src)):
        if fn in skip or fn.startswith("."):
            continue
        s, d_ = os.path.join(src, fn), os.path.join(out, fn)
        if os.path.isdir(s):
            continue
        if os.path.exists(d_):
            os.remove(d_)
        try:
            os.link(s, d_)
        except OSError:
            import shutil
            shutil.copyfile(s, d_)
        linked += 1
    # index
    new_wm = {k: v for k, v in wm.items() if v != a.mtp_shard}
    for k in carry:
        new_wm[k] = CARRY_SHARD
    for k in tensors:
        new_wm[k] = EXPERTS_SHARD
    shards = sorted(set(new_wm.values()))
    total = sum(header_total_bytes(os.path.join(out, s)) for s in shards)
    new_idx = {"metadata": {**idx.get("metadata", {}), "total_size": total}, "weight_map": dict(sorted(new_wm.items()))}
    json.dump(new_idx, open(os.path.join(out, "model.safetensors.index.json"), "w"), indent=2)
    # config
    q["ignore"] = new_ignore
    json.dump(cfg, open(os.path.join(out, "config.json"), "w"), indent=2)
    if a.sidecar_dir:
        os.makedirs(a.sidecar_dir, exist_ok=True)
        for fn in (EXPERTS_SHARD, CARRY_SHARD, "model.safetensors.index.json", "config.json"):
            s, d_ = os.path.join(out, fn), os.path.join(a.sidecar_dir, fn)
            if os.path.exists(d_):
                os.remove(d_)
            try:
                os.link(s, d_)
            except OSError:
                import shutil
                shutil.copyfile(s, d_)

    def summ(v):
        t = torch.tensor(v)
        return {"mean": float(t.mean()), "median": float(t.median()), "max": float(t.max()), "n": len(v)}
    report = {
        "src_dir": src, "out_dir": out, "observer": a.observer, "experts": n_exp, "input_global_scale": 1.0,
        "experts_shard_bytes": os.path.getsize(os.path.join(out, EXPERTS_SHARD)),
        "carry_shard_bytes": os.path.getsize(os.path.join(out, CARRY_SHARD)),
        "mtp_bf16_shard_bytes": os.path.getsize(os.path.join(src, a.mtp_shard)),
        "linked_files": linked, "index_total_size": total,
        "rel_rmse_ours": {p: summ(v) for p, v in errs.items()},
        "rel_rmse_compared": ({p: summ(v) for p, v in errs_his.items()} if his is not None else None),
        "compared_file": a.compare or None,
        "ours_better_fraction": ({p: float(torch.mean((torch.tensor(errs[p]) < torch.tensor(errs_his[p])).float())) for p in errs} if his is not None else None),
        "weight_global_scale_range": {"gs13": [min(x[0] for x in gs_log), max(x[0] for x in gs_log)], "gs2": [min(x[1] for x in gs_log), max(x[1] for x in gs_log)]},
        "new_ignore_tail": MTP_IGNORE, "seconds": round(time.time() - t0, 1),
    }
    json.dump(report, open(os.path.join(out, "mtp_nvfp4_report.json"), "w"), indent=2)
    print(json.dumps(report, indent=1), flush=True)
    saved = report["mtp_bf16_shard_bytes"] - report["experts_shard_bytes"] - report["carry_shard_bytes"]
    print(f"\nGPU bytes saved: {saved/2**30:.2f} GiB  (MTP shard {report['mtp_bf16_shard_bytes']/2**30:.2f} -> "
          f"{(report['experts_shard_bytes']+report['carry_shard_bytes'])/2**30:.2f} GiB); {report['seconds']} s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
