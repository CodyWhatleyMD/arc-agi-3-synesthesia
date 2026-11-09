#!/usr/bin/env python3
"""Fidelity of a SERVED checkpoint against the author-served reference, via prompt logprobs (09-30).

Reference: runs/flashnext/fidelity_api_vercel.jsonl -- for the LAST 512 prompts of calib.jsonl, alibaba/qwen3.8-flash
(author-served, thinking off, temperature 0) produced a 32-token continuation `content`. No logprobs came back from
that gateway (findings 110), so the metric is text-only: teacher-force the reference continuation through the local
server and read, per continuation token, (a) whether the served model's argmax equals the reference token
(top-1 agreement) and (b) the logprob the served model assigns to the reference token.

Mechanism: render [{"role":"user","content":text}] with the checkpoint's own chat template (add_generation_prompt,
enable_thinking=False), tokenize prompt and continuation SEPARATELY (no boundary merges), send the concatenated ids to
/v1/completions with prompt_logprobs=1, max_tokens=1. vLLM returns, per prompt position, the top-1 token and the actual
token's logprob+rank. Continuation positions = the last len(cont_ids).

Alignment check: our rendered prompt length vs the API's reported prompt_tokens (same tokenizer family; a large gap means
the template differs and the numbers are not comparable). Resume-safe; --limit for a quick read.
"""
import argparse, json, os, sys, time, urllib.request, concurrent.futures as cf, statistics as st

ap = argparse.ArgumentParser()
ap.add_argument("--ref", default="runs/flashnext/fidelity_api_vercel.jsonl")
ap.add_argument("--calib", default="/media/ignaz/model-storage-2/flashnext_calib/calib.jsonl")
ap.add_argument("--holdout", type=int, default=512)
ap.add_argument("--tokenizer", default="/media/ignaz/claude-extra/Qwen3.8-Flash-Next-NVFP4-ours")
ap.add_argument("--url", default="http://127.0.0.1:5300/v1"); ap.add_argument("--model", default="flashnext")
ap.add_argument("--out", default="runs/flashnext/fidelity_vllm_ours.jsonl")
ap.add_argument("--limit", type=int, default=0); ap.add_argument("--workers", type=int, default=4)
ap.add_argument("--max-len", type=int, default=32768, help="server max_model_len; prompt+continuation longer than this is recorded as skipped")
a = ap.parse_args()

from transformers import AutoTokenizer
tok = AutoTokenizer.from_pretrained(a.tokenizer, trust_remote_code=True)
lines = open(a.calib).read().splitlines()[-a.holdout:]
refs = {}
for l in open(a.ref):
    if l.strip():
        r = json.loads(l)
        if r.get("content"): refs[r["i"]] = r
done = set()
if os.path.exists(a.out):
    done = {json.loads(l)["i"] for l in open(a.out) if l.strip()}
todo = [i for i in sorted(refs) if i not in done]
if a.limit: todo = todo[:a.limit]
print(f"refs {len(refs)} | done {len(done)} | todo {len(todo)} | server {a.url} model {a.model}", flush=True)

def render(i):
    text = json.loads(lines[i])["text"]
    msgs = [{"role": "user", "content": text}]
    try:
        p = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True, enable_thinking=False)
    except TypeError:
        p = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
    p_ids = tok(p, add_special_tokens=False)["input_ids"]
    c_ids = tok(refs[i]["content"], add_special_tokens=False)["input_ids"]
    return p_ids, c_ids

def one(i):
    t0 = time.time(); p_ids, c_ids = render(i)
    body = {"model": a.model, "prompt": p_ids + c_ids, "max_tokens": 1, "temperature": 0, "prompt_logprobs": 1}
    req = urllib.request.Request(f"{a.url}/completions", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    if len(p_ids) + len(c_ids) > a.max_len:          # 09-30: one 400 on an over-length prompt killed a 507/512 run
        return {"i": i, "error": f"over_length {len(p_ids)+len(c_ids)}>{a.max_len}", "prompt_tokens_ours": len(p_ids), "cont_tokens": len(c_ids)}
    try:
        d = json.loads(urllib.request.urlopen(req, timeout=1800).read())
    except urllib.error.HTTPError as e:
        return {"i": i, "error": f"http {e.code}: {e.read()[:200].decode(errors='replace')}", "prompt_tokens_ours": len(p_ids), "cont_tokens": len(c_ids)}
    pl = d["choices"][0]["prompt_logprobs"]
    assert len(pl) == len(p_ids) + len(c_ids), (len(pl), len(p_ids), len(c_ids))
    agree = []; lps = []
    for pos, tid in enumerate(c_ids):
        entry = pl[len(p_ids) + pos] or {}
        me = entry.get(str(tid))
        if me is None:                       # actual token not in the returned dict (should not happen with prompt_logprobs>=1)
            agree.append(0); lps.append(float("-inf")); continue
        agree.append(1 if me.get("rank") == 1 else 0); lps.append(float(me["logprob"]))
    return {"i": i, "prompt_tokens_ours": len(p_ids), "prompt_tokens_api": refs[i].get("prompt_tokens_api"),
            "cont_tokens": len(c_ids), "top1_agree": sum(agree) / max(len(agree), 1),
            "mean_logprob": (sum(x for x in lps if x > float("-inf")) / max(sum(1 for x in lps if x > float("-inf")), 1)),
            "secs": round(time.time() - t0, 1)}

with open(a.out, "a") as fo, cf.ThreadPoolExecutor(a.workers) as ex:
    n = 0
    for r in ex.map(one, todo):
        fo.write(json.dumps(r) + "\n"); fo.flush(); n += 1
        if "error" in r: print(f"  skip i={r['i']}: {r['error'][:80]}", flush=True); continue
        if n % 16 == 0: print(f"  {n}/{len(todo)}  agree {r['top1_agree']:.2f}  lp {r['mean_logprob']:.2f}  align {r['prompt_tokens_ours']}/{r['prompt_tokens_api']}  {r['secs']}s", flush=True)

rows_all = [json.loads(l) for l in open(a.out) if l.strip()]
rows = [r for r in rows_all if "error" not in r]; skipped = len(rows_all) - len(rows)
ag = [r["top1_agree"] for r in rows]; lp = [r["mean_logprob"] for r in rows]
al = [r["prompt_tokens_ours"] / r["prompt_tokens_api"] for r in rows if r.get("prompt_tokens_api")]
print(f"FIDELITY {a.model}: n={len(rows)} (skipped {skipped}) | top-1 agreement mean {st.mean(ag):.3f} (median {st.median(ag):.3f}) | mean logprob of reference tokens {st.mean(lp):.3f} | prompt-length alignment ours/api median {st.median(al):.3f}")
