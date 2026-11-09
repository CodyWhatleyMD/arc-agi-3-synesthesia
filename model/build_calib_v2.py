"""Calibration set v2 (2026-10-06): CURRENT-format requests, chat-templated, window-sampled.

v1 (09-25, calib.jsonl) was 4,096 Duck requests from the low-norm-glyph era, flattened as '[SYSTEM]...' text and
truncated to the first 4,096 tokens -- so the NVFP4 experts' static activation global scales were fitted to the head
of an obsolete system prompt. v2 takes real requests from Han Solo's harness with our board tower (the Arm B v4 Kaggle
commit run: 14 games, ~2.9k requests incl. tool schemas, tool calls, thinking), renders each through the model's own
chat template (tools included; image parts dropped -- the text pipeline cannot carry embeds), and samples ONE random
4,096-token window per request so later-context activations are represented, not just the prompt head.
  python build_calib_v2.py <requests_glob> <out.jsonl> [--samples 1024] [--window 4096]
"""
import argparse, glob, json, random, sys, os
ap = argparse.ArgumentParser()
ap.add_argument("src_glob"); ap.add_argument("out")
ap.add_argument("--samples", type=int, default=1024); ap.add_argument("--window", type=int, default=4096)
ap.add_argument("--head-frac", type=float, default=0.2, help="fraction of windows forced to start at token 0 (system prompt + tool schema)")
ap.add_argument("--snapshot", default="/media/ignaz/model-storage-1/Qwen3.8-Flash-Next", help="BF16 checkpoint dir (tokenizer + chat template)")
a = ap.parse_args()
assert os.path.isfile(os.path.join(a.snapshot, "tokenizer_config.json")), f"no tokenizer at {a.snapshot}"
from transformers import AutoTokenizer
tok = AutoTokenizer.from_pretrained(a.snapshot, trust_remote_code=True)
files = sorted(glob.glob(a.src_glob)); print(f"files={len(files)} snapshot={a.snapshot}", flush=True)
reqs = []
for f in files:
    for ln in open(f):
        try: r = json.loads(ln)
        except Exception: continue
        if r.get("event") not in (None, "request") or "messages" not in r: continue
        reqs.append((r["messages"], r.get("tools")))
print(f"requests={len(reqs)}", flush=True)
random.seed(7); random.shuffle(reqs)
def strip_images(msgs):
    """Text-only, template-friendly copy: image parts dropped, content flattened to str, and OpenAI-wire
    tool_calls arguments (a JSON STRING on the wire) parsed back to dicts -- Qwen's template iterates
    `.items()` on them and raises "Can only get item pairs from a mapping" on the string form."""
    out = []
    for m in msgs:
        m = dict(m)
        c = m.get("content")
        if isinstance(c, list):
            c = [p for p in c if not (isinstance(p, dict) and p.get("type") in ("image_url", "image_embeds"))]
            c = "\n".join(p.get("text", "") for p in c if isinstance(p, dict)) if c else ""
        m["content"] = c if c is not None else ""
        if m.get("tool_calls"):
            tcs = []
            for tc in m["tool_calls"]:
                tc = json.loads(json.dumps(tc)); fn = tc.get("function") or {}
                if isinstance(fn.get("arguments"), str):
                    try: fn["arguments"] = json.loads(fn["arguments"])
                    except Exception: fn["arguments"] = {"raw": fn["arguments"]}
                tc["function"] = fn; tcs.append(tc)
            m["tool_calls"] = tcs
        out.append(m)
    return out
n_out = 0; lens = []; fails = 0
with open(a.out, "w") as fo:
    for msgs, tools in reqs:
        if n_out >= a.samples: break
        try:
            ids = tok.apply_chat_template(strip_images(msgs), tools=tools, tokenize=True, add_generation_prompt=True)
            if hasattr(ids, "input_ids"): ids = ids["input_ids"]
        except Exception as e:
            fails += 1
            if fails <= 2:
                print("template fail:", type(e).__name__, str(e)[:160], flush=True)
                bad = [ (m.get("role"), type(m.get("content")).__name__, list(m.keys())) for m in strip_images(msgs) if m.get("tool_calls") or m.get("role")=="tool"][:3]
                print("  sample tool-ish messages:", bad, flush=True)
            continue
        if len(ids) < 512: continue
        start = 0 if random.random() < a.head_frac else random.randint(0, max(0, len(ids) - a.window))
        win = ids[start:start + a.window]
        fo.write(json.dumps({"text": tok.decode(win), "src_len": len(ids), "start": start}) + "\n")
        n_out += 1; lens.append(len(ids))
        if n_out % 100 == 0: print(f"  {n_out} written", flush=True)
import statistics
print(f"DONE wrote={n_out} template_fails={fails} src_len median={statistics.median(lens) if lens else 0} "
      f"min={min(lens) if lens else 0} max={max(lens) if lens else 0}", flush=True)
