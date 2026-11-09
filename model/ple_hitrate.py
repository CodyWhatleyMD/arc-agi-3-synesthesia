#!/usr/bin/env python3
"""PLE n-gram bucket hit-rate of OUR corpus (plan step 1, decides P2a). CPU only.

Instantiates transformers' Qwen4ExpTextNGramEmbedding with the real config but a stub in place of
the 320M-row table (the real one is 102 GB), so its forward returns the bucket ids it WOULD gather.
Runs every calibration sample through it and counts distinct buckets touched, per head and in total,
with a saturation curve every 512 samples. Output: runs/flashnext/ple_hitrate.json + stdout.
"""
import argparse, json, os, sys, time, torch, numpy as np
from transformers import AutoConfig, AutoTokenizer
import transformers.models.qwen4_exp.modeling_qwen4_exp as M

ap = argparse.ArgumentParser()
ap.add_argument("--src", default="/media/ignaz/model-storage-1/Qwen3.8-Flash-Next")
ap.add_argument("--calib", default="/media/ignaz/model-storage-2/flashnext_calib/calib.jsonl")
ap.add_argument("--limit", type=int, default=0); ap.add_argument("--max-seq", type=int, default=4096)
ap.add_argument("--out", default="runs/flashnext/ple_hitrate.json")
ap.add_argument("--holdout-games", default="", help="comma-separated game ids: ALL their samples are held out (leave-games-out coverage)")
ap.add_argument("--holdout", type=int, default=0, help="reserve the LAST N samples: build the touched set from the rest, then report the per-lookup hit rate on them")
a = ap.parse_args()

class StubEmb(torch.nn.Module):          # returns ids (exact in float64) instead of vectors
    def __init__(self, n, d): super().__init__(); self.num_embeddings = n; self.embedding_dim = d; self.weight = torch.nn.Parameter(torch.zeros(1), requires_grad=False)
    def forward(self, ids): return ids.unsqueeze(-1).to(torch.float64)

cfg = AutoConfig.from_pretrained(a.src).text_config
_orig = M.nn.Embedding; M.nn.Embedding = StubEmb
try: emb = M.Qwen4ExpTextNGramEmbedding(cfg, cfg.ple_embed_dim, cfg.ple_layer_ids[0], 0)
finally: M.nn.Embedding = _orig
emb.eval()
V = int(emb.ngram_embedding.num_embeddings); heads = int(emb.ngram_heads)
offs = emb.ngram_heads_offsets.tolist(); sizes = emb.ngram_heads_vocab_sizes.tolist()
print(f"padded table rows {V:,} | heads {heads} | head vocab sizes {sizes[0]:,}..{sizes[-1]:,} | dim/head {cfg.ple_embed_dim//heads}", flush=True)
touched = np.zeros(V, dtype=np.bool_)
tok = AutoTokenizer.from_pretrained(a.src)
lines = open(a.calib).read().splitlines()
if a.limit: lines = lines[:a.limit]
if a.holdout_games:
    hg=set(a.holdout_games.split(",")); rows=[json.loads(l) for l in lines]
    train=[json.dumps(r) for r in rows if r.get("game") not in hg]; test=[json.dumps(r) for r in rows if r.get("game") in hg]
    print(f"leave-games-out: held out {sorted(hg)} -> train {len(train)} test {len(test)}", flush=True)
else:
    train, test = (lines[:-a.holdout], lines[-a.holdout:]) if a.holdout else (lines, [])
n = toks = 0; t0 = time.time(); curve = []
def buckets(text):
    ids = tok(text, truncation=True, max_length=a.max_seq, return_tensors="pt")["input_ids"]
    with torch.no_grad(): b = emb(ids, None)                          # [1, T, heads] float64 bucket ids
    bi = b.to(torch.int64).reshape(-1).numpy(); assert bi.min() >= 0 and bi.max() < V, (bi.min(), bi.max(), V)
    return bi, ids.shape[1]
for line in train:
        bi, T = buckets(json.loads(line)["text"])
        touched[np.unique(bi)] = True; n += 1; toks += T
        if n % 512 == 0:
            curve.append((n, toks, int(touched.sum()))); print(f"  {n:>5} samples {toks:>10,} tokens -> {curve[-1][2]:>10,} buckets ({100*curve[-1][2]/V:.3f}%)  {time.time()-t0:.0f}s", flush=True)
hold = None
if test:
    hits = looks = 0; tok_hit_all = 0; tok_n = 0
    for line in test:
        bi, T = buckets(json.loads(line)["text"]); h = touched[bi]
        hits += int(h.sum()); looks += h.size
        tok_hit_all += int(h.reshape(T, heads).all(axis=1).sum()); tok_n += T
    hold = {"holdout_samples": len(test), "lookup_hit_rate": hits / looks, "token_all_heads_hit_rate": tok_hit_all / tok_n}
    print(f"HOLDOUT {len(test)} samples: per-lookup hit rate {100*hits/looks:.2f}% | tokens with ALL {heads} heads hit {100*tok_hit_all/tok_n:.2f}%", flush=True)
tot = int(touched.sum()); per_head = [int(touched[o:o+s].sum()) for o, s in zip(offs, sizes)]
res = {"samples": n, "tokens": toks, "table_rows": V, "touched": tot, "fraction": tot / V, "per_head_touched": per_head, "per_head_size": sizes,
       "holdout": hold, "restricted_table_MB_bf16": tot * (cfg.ple_embed_dim // heads) * 2 / 1e6, "full_table_MB_bf16": V * (cfg.ple_embed_dim // heads) * 2 / 1e6, "curve": curve}
os.makedirs(os.path.dirname(a.out), exist_ok=True); json.dump(res, open(a.out, "w"), indent=1)
print(f"DONE samples {n} tokens {toks:,} | touched {tot:,}/{V:,} = {100*tot/V:.3f}% | restricted table {res['restricted_table_MB_bf16']:.0f} MB vs full {res['full_table_MB_bf16']/1000:.0f} GB | per-head min/max {min(per_head):,}/{max(per_head):,}", flush=True)
