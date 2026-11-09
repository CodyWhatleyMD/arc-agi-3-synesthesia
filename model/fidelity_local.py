#!/usr/bin/env python3
"""Local side: teacher-force a checkpoint (our quant, or any HF path) on the API's greedy continuation
and record top-20 logprobs at every continuation position. Thinking prefix matched to what the API
did (--thinking auto: on if the API's first token contains '<think>', else off). Alignment check:
the API's token strings re-tokenized must give the same count, else the prompt is marked misaligned."""
import argparse, json, os, sys, torch
from transformers import AutoConfig, AutoTokenizer, AutoModelForImageTextToText
ap = argparse.ArgumentParser()
ap.add_argument("--ckpt", required=True); ap.add_argument("--api", default="runs/flashnext/fidelity_api.jsonl")
ap.add_argument("--calib", default="/media/ignaz/model-storage-2/flashnext_calib/calib.jsonl"); ap.add_argument("--holdout", type=int, default=512)
ap.add_argument("--out", default=""); ap.add_argument("--top", type=int, default=20); ap.add_argument("--batch", type=int, default=8)
ap.add_argument("--thinking", choices=["auto", "on", "off"], default="auto"); ap.add_argument("--device", default="cuda:0")
ap.add_argument("--tiny", action="store_true", help="self-test on a random 2-layer model (no checkpoint load)")
a = ap.parse_args(); out = a.out or f"runs/flashnext/fidelity_local_{os.path.basename(a.ckpt.rstrip('/'))}.jsonl"
tok = AutoTokenizer.from_pretrained(a.ckpt if not a.tiny else "/media/ignaz/model-storage-1/Qwen3.8-Flash-Next")
if a.tiny:
    cfg = AutoConfig.from_pretrained("/media/ignaz/model-storage-1/Qwen3.8-Flash-Next"); t = cfg.text_config
    t.num_hidden_layers = 2; t.layer_types = ["linear_attention", "full_attention"]; t.ple_layer_ids = []; t.num_experts = 8; t.num_experts_per_tok = 2
    t.hidden_size = 64; t.moe_intermediate_size = 16; t.shared_expert_intermediate_size = 16; t.intermediate_size = 32; t.num_attention_heads = 4; t.num_key_value_heads = 2; t.head_dim = 16
    for k, v in (("linear_num_value_heads", 4), ("linear_num_key_heads", 2), ("linear_key_head_dim", 16), ("linear_value_head_dim", 16)):
        if hasattr(t, k): setattr(t, k, v)
    cfg.vision_config.hidden_size = 64; cfg.vision_config.depth = 1; cfg.vision_config.out_hidden_size = 64
    torch.manual_seed(0); model = AutoModelForImageTextToText.from_config(cfg).float().eval(); dev = torch.device("cpu")
else:
    from compressed_tensors.offload import load_offloaded_model
    with load_offloaded_model(AutoModelForImageTextToText):
        model = AutoModelForImageTextToText.from_pretrained(a.ckpt, dtype=torch.bfloat16, device_map="auto_offload").eval()
    dev = torch.device(a.device)
prompts = open(a.calib).read().splitlines()[-a.holdout:]
recs = [json.loads(l) for l in open(a.api) if l.strip()]
print(f"api records {len(recs)} | ckpt {a.ckpt}", flush=True)
def build(rec):
    text = json.loads(prompts[rec["i"]])["text"]; cont = "".join(p["token"] for p in rec["tokens"]) if rec.get("tokens") else (rec.get("content") or "")
    think = (a.thinking == "on") or (a.thinking == "auto" and bool(rec.get("reasoning")))
    pre = tok.apply_chat_template([{"role": "user", "content": text}], add_generation_prompt=True, tokenize=False, enable_thinking=think)
    p_ids = tok(pre, add_special_tokens=False)["input_ids"]; c_ids = tok(cont, add_special_tokens=False)["input_ids"]
    return p_ids, c_ids, (len(c_ids) == len(rec["tokens"])) if rec.get("tokens") else (len(c_ids) > 0), think
with open(out, "w") as fo:
    B = a.batch; n = 0; mis = 0
    for s in range(0, len(recs), B):
        chunk = recs[s:s+B]; built = [build(r) for r in chunk]
        seqs = [p + c for p, c, _, _ in built]; L = max(len(x) for x in seqs); pad = tok.pad_token_id or 0
        ids = torch.tensor([x + [pad] * (L - len(x)) for x in seqs]); am = torch.tensor([[1] * len(x) + [0] * (L - len(x)) for x in seqs])
        with torch.no_grad(): logits = model(input_ids=ids.to(dev), attention_mask=am.to(dev), use_cache=False).logits.float()   # use_cache=True builds a DynamicCache this arch's indexer rejects
        for r, (p, c, ok, think), lg in zip(chunk, built, logits):
            if not ok: mis += 1
            lp = torch.log_softmax(lg[len(p)-1: len(p)-1+len(c)], dim=-1)          # predicts c[0..]
            tv, ti = torch.topk(lp, a.top, dim=-1)
            fo.write(json.dumps({"i": r["i"], "aligned": ok, "thinking": think, "n": len(c),
                                 "ref_token_logprob": [float(lp[j, c[j]]) for j in range(len(c))],
                                 "top": [[(tok.decode([int(i)]), float(v)) for v, i in zip(tv[j], ti[j])] for j in range(len(c))]}, ensure_ascii=False) + "\n"); n += 1
        print(f"  {n}/{len(recs)} (misaligned {mis})", flush=True)
print(f"DONE local: {n} prompts, {mis} misaligned, out={out}", flush=True)
