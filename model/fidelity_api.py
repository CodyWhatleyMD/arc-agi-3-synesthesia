#!/usr/bin/env python3
"""Reference side of the quant-fidelity measurement: the author-served Flash-Next through an
OpenAI-compatible gateway (OpenRouter or Vercel AI Gateway). For each held-out prompt: 32 greedy
tokens with top-20 logprobs at every position. The local side (fidelity_local.py) teacher-forces
our quant on the SAME continuation and fidelity_compare.py scores the two distributions per position.
Key: read from --key-file at call time, never printed. Precision caveat: Alibaba serves at an
unstated precision -- the reference is "author-served", not "BF16"."""
import argparse, json, os, sys, time, urllib.request, urllib.error
ap = argparse.ArgumentParser()
ap.add_argument("--base-url", default="https://openrouter.ai/api/v1")
ap.add_argument("--model", default="qwen/qwen3.8-flash")
ap.add_argument("--key-file", default=os.path.expanduser("~/.openrouter_key"))
ap.add_argument("--calib", default="/media/ignaz/model-storage-2/flashnext_calib/calib.jsonl")
ap.add_argument("--holdout", type=int, default=512, help="use the LAST N samples (the same held-out set ple_hitrate reserves)")
ap.add_argument("--limit", type=int, default=0); ap.add_argument("--max-tokens", type=int, default=32); ap.add_argument("--top", type=int, default=20)
ap.add_argument("--reasoning", choices=["openrouter", "vercel", "none"], default="openrouter", help="how to ask for thinking OFF")
ap.add_argument("--out", default="runs/flashnext/fidelity_api.jsonl")
ap.add_argument("--allow-text-only", action="store_true", help="accept references without logprobs (Vercel/Alibaba return none): token-agreement metric only")
a = ap.parse_args()
key = open(a.key_file).read().strip()
lines = open(a.calib).read().splitlines()[-a.holdout:]
if a.limit: lines = lines[:a.limit]
os.makedirs(os.path.dirname(a.out), exist_ok=True); done = set()
if os.path.exists(a.out): done = {json.loads(l)["i"] for l in open(a.out) if l.strip()}
def call(text):
    body = {"model": a.model, "messages": [{"role": "user", "content": text}], "max_tokens": a.max_tokens, "temperature": 0,
            "logprobs": True, "top_logprobs": a.top}
    variants = [dict(body)]
    if a.reasoning == "openrouter": variants[0]["reasoning"] = {"enabled": False}
    elif a.reasoning == "vercel":                       # Vercel documents the effort under reasoning.effort for Chat Completions; try both spellings
        variants[0]["reasoning_effort"] = "none"; v2 = dict(body); v2["reasoning"] = {"effort": "none"}; variants.append(v2)
    last = None
    for b in variants:
        req = urllib.request.Request(a.base_url.rstrip("/") + "/chat/completions", data=json.dumps(b).encode(),
                                     headers={"Content-Type": "application/json", "Authorization": "Bearer " + key, "HTTP-Referer": "https://github.com/CodyWhatleyMD/arc-prize-2026", "X-Title": "arc-prize fidelity"})
        for attempt in range(6):                      # the gateway throws intermittent 503s (09-28); ride them out
            try: return json.loads(urllib.request.urlopen(req, timeout=180).read())
            except urllib.error.HTTPError as e:
                last = e
                if e.code == 400: break
                if e.code in (429, 500, 502, 503, 504) and attempt < 5: time.sleep(3 * (attempt + 1)); continue
                raise
    raise last
n_ok = n_err = 0; t0 = time.time()
with open(a.out, "a") as fo:
    for i, line in enumerate(lines):
        if i in done: continue
        text = json.loads(line)["text"]
        try:
            r = call(text)
            ch = r["choices"][0]; lp = (ch.get("logprobs") or {}).get("content") or []
            if not lp or "top_logprobs" not in lp[0]:
                if not a.allow_text_only:
                    print(f"ABORT: gateway returned no top_logprobs (choice keys {list(ch)}; logprobs={ch.get('logprobs')!r:.120}) -- this gateway/provider does not pass logprobs through; pass --allow-text-only for the token-agreement metric", flush=True); sys.exit(2)
                lp = None   # text-only reference: the local side tokenizes `content`; compare scores top-1 agreement + ref-token logprob only (no KL)
            rec = {"i": i, "prompt_tokens_api": (r.get("usage") or {}).get("prompt_tokens"), "provider": r.get("provider"), "model": r.get("model"),
                   "finish": ch.get("finish_reason"), "content": ch["message"].get("content"), "reasoning": ch["message"].get("reasoning") or ch["message"].get("reasoning_content"),
                   "text_only": lp is None,
                   "tokens": ([{"token": p["token"], "logprob": p["logprob"], "top": [(q["token"], q["logprob"]) for q in p["top_logprobs"]]} for p in lp] if lp else [])}
            fo.write(json.dumps(rec, ensure_ascii=False) + "\n"); fo.flush(); n_ok += 1
        except Exception as e:
            n_err += 1; print(f"  err {i}: {repr(e)[:200]}", flush=True)
            if n_err > 200: print("ABORT: too many errors", flush=True); sys.exit(3)
        if (n_ok + n_err) % 50 == 0: print(f"  {n_ok} ok / {n_err} err  {time.time()-t0:.0f}s", flush=True)
print(f"DONE api: {n_ok} ok, {n_err} err, out={a.out}", flush=True)
