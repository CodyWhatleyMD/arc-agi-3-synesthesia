#!/usr/bin/env python3
"""Our own NVFP4 quant of Qwen/Qwen3.8-Flash-Next (09-25). Run with /home/ignaz/quant-venv.

  --tiny        : 2-layer/8-expert random model, 8 samples -> verifies the whole pipeline in ~30s (CPU)
  default       : the real 360 GB BF16 checkpoint, calibrated on OUR prompts (calib.jsonl)

What is ours here: (1) the registration -- transformers 5.17's Qwen4ExpTextExperts already satisfies
llm-compressor's fused-experts protocol (has_gate/has_bias/is_transposed/_apply_gate), so one import-path
entry suffices; verified bit-identical fused-vs-linearized MoE output on a tiny instance.
(2) the recipe (recipe.yaml): experts NVFP4 W4A4 group-16, attention/GDN/shared/PLE-projection/lm_head FP8
channel, embeddings + the 51B n-gram table + norms + vision + MTP + routers untouched.
(3) the calibration set: 4,096 of our own Duck requests (boards in our glyphs, the model's Python).

Memory: 360 GB BF16 does not fit 188 GB RAM. Loading uses accelerate device_map with disk offload
(--offload-dir) so layers page from disk; llm-compressor's sequential pipeline onloads one layer at a time
to --device. Slow but bounded. The 4-card rental does it in RAM.
"""
import argparse, json, os, sys, torch
from transformers import AutoConfig, AutoModelForImageTextToText, AutoTokenizer
from llmcompressor.modeling.moe import conversion_mappings as cm
cm.ARCH_TO_IMPORT_PATHS["qwen4_exp"] = ("transformers.models.qwen4_exp.configuration_qwen4_exp.Qwen4ExpTextConfig",
                                        "transformers.models.qwen4_exp.modeling_qwen4_exp.Qwen4ExpTextExperts")
from llmcompressor import oneshot
from datasets import Dataset, load_dataset

ap = argparse.ArgumentParser()
ap.add_argument("--src", default="/media/ignaz/model-storage-1/Qwen3.8-Flash-Next")
ap.add_argument("--out", default="/media/ignaz/model-storage-2/Qwen3.8-Flash-Next-NVFP4-ours")
ap.add_argument("--calib", default="/media/ignaz/model-storage-2/flashnext_calib/calib.jsonl")
ap.add_argument("--recipe", default=os.path.join(os.path.dirname(__file__), "recipe.yaml"))
ap.add_argument("--samples", type=int, default=512)
ap.add_argument("--max-seq", type=int, default=4096)
ap.add_argument("--device", default="cuda:0", help="calibration device (CUDA_VISIBLE_DEVICES selects the card)")
ap.add_argument("--offload-dir", default="/media/ignaz/model-storage-2/flashnext_offload")
ap.add_argument("--cpu-mem", default="140GiB"); ap.add_argument("--gpu-mem", default="70GiB")
ap.add_argument("--tiny", action="store_true")
ap.add_argument("--layers", type=int, default=0, help="real-weights SLICE: keep only the first N decoder layers (plan step 2); 0 = full model")
ap.add_argument("--mtp-nvfp4", action="store_true", help="post-step (v2.2, 2026-10-13): quantize the MTP head's routed experts to NVFP4 with mtp_nvfp4.py (the HF model ignores ^mtp.* so oneshot never sees them); default off = the BF16 MTP head of v2.1")
ap.add_argument("--seq-targets", default="", help="comma-separated sequential_targets (P1a); empty = llm-compressor default (the decoder layer)")
a = ap.parse_args()

# ---- P1b: keep the 102 GB n-gram table on the CPU during calibration ---------------------------
# The sequential pipeline calls set_onload_device(model, GPU) for every offloaded module. The
# transformers forward gathers on the table's own device and moves the result to the ids' device
# (modeling_qwen4_exp.py: `self.ngram_embedding(ngram_ids.to(execution_device)).to(ngram_ids.device)`),
# so pinning ONLY the nn.Embedding to CPU keeps the gather on the host and everything else on the card.
import llmcompressor.pipelines.sequential.pipeline as _sp
_orig_set_onload = _sp.set_onload_device
def _set_onload_pin_ple(model, onload_device):
    out = _orig_set_onload(model, onload_device); pinned = []
    for name, mod in model.named_modules():
        if name.endswith("ple_embedding.ngram_embedding") and hasattr(mod._parameters, "onload_device"):
            mod._parameters.onload_device = torch.device("cpu"); mod._buffers.onload_device = torch.device("cpu"); pinned.append(name)
    print(f"P1b: PLE table pinned to CPU for {pinned or 'NO MODULE (nothing matched)'}", flush=True)
    return out
_sp.set_onload_device = _set_onload_pin_ple

tok = AutoTokenizer.from_pretrained(a.src)
if a.tiny:
    cfg = AutoConfig.from_pretrained(a.src); t = cfg.text_config
    t.num_hidden_layers = 2; t.layer_types = ["linear_attention", "full_attention"]; t.ple_layer_ids = []
    t.num_experts = 8; t.num_experts_per_tok = 2; t.hidden_size = 64; t.moe_intermediate_size = 16; t.shared_expert_intermediate_size = 16
    t.intermediate_size = 32; t.num_attention_heads = 4; t.num_key_value_heads = 2; t.head_dim = 16
    for k, v in (("linear_num_value_heads", 4), ("linear_num_key_heads", 2), ("linear_key_head_dim", 16), ("linear_value_head_dim", 16)):
        if hasattr(t, k): setattr(t, k, v)
    cfg.vision_config.hidden_size = 64; cfg.vision_config.depth = 1; cfg.vision_config.out_hidden_size = 64
    torch.manual_seed(0); model = AutoModelForImageTextToText.from_config(cfg).float()
    ds = Dataset.from_dict({"input_ids": [tok("the quick brown fox " * 16)["input_ids"][:64] for _ in range(8)]}).map(lambda r: {"attention_mask": [1] * len(r["input_ids"])})
    a.samples, a.max_seq, a.out = 8, 64, a.out + "-tiny"
else:
    from compressed_tensors.offload import load_offloaded_model
    cfg = AutoConfig.from_pretrained(a.src)
    if a.layers:
        t = cfg.text_config; t.num_hidden_layers = a.layers; t.layer_types = t.layer_types[:a.layers]
        t.ple_layer_ids = [i for i in t.ple_layer_ids if i < a.layers]
        a.out = a.out + f"-slice{a.layers}"
    # compressed-tensors' own offload: CPU fills first, the remainder goes to disk (its cache dir);
    # weights are read from the checkpoint by the loader, never duplicated into our offload folder.
    with load_offloaded_model(AutoModelForImageTextToText):
        os.makedirs(a.offload_dir, exist_ok=True)
        model = AutoModelForImageTextToText.from_pretrained(a.src, config=cfg, dtype=torch.bfloat16, device_map="auto_offload", offload_folder=a.offload_dir)  # 09-30: the full model spills to disk; the slice never did
    n_ple = sum(1 for n, _ in model.named_modules() if n.endswith("ple_embedding.ngram_embedding"))
    print(f"loaded: layers={cfg.text_config.num_hidden_layers} ple_layer_ids={cfg.text_config.ple_layer_ids} ngram_embedding modules={n_ple}", flush=True)
    raw = load_dataset("json", data_files=a.calib, split="train").shuffle(seed=7).select(range(a.samples))
    ds = raw.map(lambda r: tok(r["text"], truncation=True, max_length=a.max_seq), remove_columns=raw.column_names)
print(f"quantize: src={a.src} out={a.out} samples={a.samples} max_seq={a.max_seq} tiny={a.tiny}", flush=True)
# ---- P2d: router utilization, free on the calibration pass ------------------------------------
# Hook every MoE router (the `mlp.gate` Linear); count top-k expert selections per layer over the
# calibration tokens. Tells which experts our task never routes to -- the pruning lever for serving.
import collections, threading
_route = collections.defaultdict(lambda: torch.zeros(model.config.text_config.num_experts, dtype=torch.long))
_topk = int(model.config.text_config.num_experts_per_tok)
def _router_hook(name):
    def h(mod, inp, out):                     # Qwen4ExpTextTopKRouter.forward -> (logits, routing_weights, selected_experts)
        idx = out[2].reshape(-1).to("cpu", torch.long)
        _route[name] += torch.bincount(idx, minlength=_route[name].numel())
    return h
_hooks = [m.register_forward_hook(_router_hook(n)) for n, m in model.named_modules() if type(m).__name__ == "Qwen4ExpTextTopKRouter"]
print(f"P2d: router hooks on {len(_hooks)} layers", flush=True)
def _rss_timeline(path, stop):
    import time, resource
    with open(path, "a") as f:
        while not stop.is_set():
            rss = int(open("/proc/self/status").read().split("VmRSS:")[1].split()[0]) // 1024
            f.write(f"{time.time():.0f} rss_mb={rss}\n"); f.flush(); stop.wait(20)
_stop = threading.Event(); threading.Thread(target=_rss_timeline, args=(a.out + ".rss.log", _stop), daemon=True).start()
kw = {"sequential_targets": [x for x in a.seq_targets.split(",") if x]} if a.seq_targets else {}
oneshot(model=model, processor=tok, dataset=ds, recipe=a.recipe, output_dir=a.out, num_calibration_samples=a.samples, max_seq_length=a.max_seq, **kw)
_stop.set()
for h in _hooks: h.remove()
if _route:
    rep = {n: {"counts": c.tolist(), "never_selected": int((c == 0).sum()), "top_k_covering_99pct": int((torch.cumsum(torch.sort(c, descending=True).values, 0) <= 0.99 * c.sum()).sum()) + 1} for n, c in _route.items()}
    json.dump(rep, open(os.path.join(a.out, "router_utilization.json"), "w"))
    never = [r["never_selected"] for r in rep.values()]; cov = [r["top_k_covering_99pct"] for r in rep.values()]
    print(f"P2d: experts never selected per layer min/median/max {min(never)}/{sorted(never)[len(never)//2]}/{max(never)} of {_route[next(iter(_route))].numel()} | experts covering 99% of routes: median {sorted(cov)[len(cov)//2]}", flush=True)
qc = json.load(open(os.path.join(a.out, "config.json")))["quantization_config"]
# oneshot() re-saves the tokenizer through transformers (10-08: tokenizer.json came back with the calibration's
# `truncation: max_length 4096` and flipped ByteLevel decoder flags; tokenizer_config.json re-serialized) and writes
# no image/video processor configs (vLLM then cannot build the image processor). Ship the SOURCE checkpoint's
# non-weight files verbatim, except our config.json (carries quantization_config) and our weight index.
import shutil as _sh
for _f in sorted(os.listdir(a.src)):
    if _f.endswith(".safetensors") or _f in ("config.json", "model.safetensors.index.json"):
        continue
    if os.path.isfile(os.path.join(a.src, _f)):
        _sh.copyfile(os.path.join(a.src, _f), os.path.join(a.out, _f))
        print(f"source file restored verbatim: {_f}", flush=True)
print("DONE:", a.out, "| quant_method", qc.get("quant_method"), "| format", qc.get("format"), "| groups", list(qc["config_groups"]), flush=True)

# ---- v2.2 post-step (2026-10-13): NVFP4 MTP experts. The HF model class ignores ^mtp.* on load, so the MTP head is
# never inside oneshot(); it is copied through as Qwen's BF16 shard (4,800 MiB of experts = ~15% of the KV pool on a
# 96 GB card). mtp_nvfp4.py rewrites it into a sibling dir (hard links for the unchanged shards); see findings 212.
if a.mtp_nvfp4 and not a.tiny:
    import subprocess as _sp
    _out22 = a.out.rstrip("/") + "-mtp-nvfp4"
    _sp.check_call([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "mtp_nvfp4.py"),
                    "--src-dir", a.out, "--out-dir", _out22, "--device", a.device])
    print(f"mtp_nvfp4 post-step done -> {_out22}", flush=True)

