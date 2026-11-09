#!/usr/bin/env python3
"""PLE coverage on TODAY's harness, leave-one-game-out (CL2 10-30; the investigator 15:23 "measure it"). CPU only.

The October measurement (runs/flashnext/ple_hitrate.json: 0.4% of the 320M rows touched; a 1.4 GB restricted table
covered 98.9% of lookups on held-out games, findings 103) used the old Duck harness's prompts. This re-measures on the
anchor harness's real traffic: every request of the four local control runs r2, r3, r4, r6 (harness 8552964), per
game. Per game, the distinct messages of all its requests (system once, then every user / assistant (reasoning +
tool calls) / tool message in first-seen order; board image parts kept as the template's image placeholder) are
rendered through the model's own chat template and tokenizer, and hashed to PLE bucket ids by transformers'
Qwen4ExpTextNGramEmbedding with a stub table (as ple_hitrate.py), i.e. the rows the model would look up.
Leave-one-game-out: a game's lookups hit if any OTHER game touched that row; the restricted table for the hidden set
would be the union over all 25 games. Reports per-game hit rate, the share of tokens whose 8 lookups all hit, and the
union table's size."""
import argparse, glob, hashlib, json, os, sys, time
import numpy as np, torch
from transformers import AutoConfig, AutoTokenizer
import transformers.models.qwen4_exp.modeling_qwen4_exp as M

ap = argparse.ArgumentParser()
ap.add_argument("--src", default="/media/ignaz/model-storage-1/Qwen3.8-Flash-Next")
ap.add_argument("--runs", default="r2_9300,r3_9300,r4_9300,r6_9300")
ap.add_argument("--out", default="runs/flashnext/ple_coverage_harness_1030.json")
a = ap.parse_args()


class StubEmb(torch.nn.Module):          # returns the bucket ids instead of vectors (exact in float64)
    def __init__(self, n, d):
        super().__init__(); self.num_embeddings = n; self.embedding_dim = d
        self.weight = torch.nn.Parameter(torch.zeros(1), requires_grad=False)

    def forward(self, ids):
        return ids.unsqueeze(-1).to(torch.float64)


cfg = AutoConfig.from_pretrained(a.src).text_config
_orig = M.nn.Embedding; M.nn.Embedding = StubEmb
try:
    emb = M.Qwen4ExpTextNGramEmbedding(cfg, cfg.ple_embed_dim, cfg.ple_layer_ids[0], 0)
finally:
    M.nn.Embedding = _orig
emb.eval()
V = int(emb.ngram_embedding.num_embeddings); heads = int(emb.ngram_heads); row_bytes = (cfg.ple_embed_dim // heads) * 2
tok = AutoTokenizer.from_pretrained(a.src)
print(f"table rows {V:,}, {heads} heads, {row_bytes} B/row bf16", flush=True)


def conversation(path):
    seen, conv, tools = set(), [], None
    for line in open(path):
        r = json.loads(line); tools = tools or r.get("tools")
        for m in r["messages"]:
            m = dict(m)
            if isinstance(m.get("content"), list):
                m["content"] = [p if p.get("type") == "text" else {"type": "image"} for p in m["content"]]
            if "reasoning" in m and "reasoning_content" not in m:
                m["reasoning_content"] = m.pop("reasoning")
            if m.get("tool_calls"):                          # the log keeps OpenAI wire format: arguments as a JSON string;
                tcs = []                                     # the chat template iterates them as a mapping (as vLLM parses them)
                for tc in m["tool_calls"]:
                    tc = json.loads(json.dumps(tc)); fn = tc.get("function", tc)
                    if isinstance(fn.get("arguments"), str):
                        try:
                            fn["arguments"] = json.loads(fn["arguments"])
                        except json.JSONDecodeError:
                            fn["arguments"] = {"_raw": fn["arguments"]}
                    tcs.append(tc)
                m["tool_calls"] = tcs
            h = hashlib.sha1(json.dumps(m, sort_keys=True).encode()).hexdigest()
            if h in seen:
                continue
            seen.add(h); conv.append(m)
    sys_msgs = [m for m in conv if m["role"] == "system"][:1]
    return sys_msgs + [m for m in conv if m["role"] != "system"], tools


def bucket_ids(text):
    ids = tok(text, return_tensors="pt", add_special_tokens=False)["input_ids"]
    out = []
    with torch.no_grad():
        for s in range(0, ids.shape[1], 65536):           # chunk; the n-gram window crosses chunk edges by <= 2 tokens
            lo = max(0, s - 2)
            b = emb(ids[:, lo:s + 65536], None).to(torch.int64)[0, (s - lo):].reshape(-1).numpy()
            out.append(b)
    bi = np.concatenate(out); assert bi.min() >= 0 and bi.max() < V
    return bi, ids.shape[1]


per_game, t0 = {}, time.time()
for run in a.runs.split(","):
    for f in sorted(glob.glob(f"/home/ignaz/kaggle_local/working_{run}/synesthesia/*_p0_requests.jsonl")):
        game = os.path.basename(f).split("-")[0]
        conv, tools = conversation(f)
        text = tok.apply_chat_template(conv, tools=tools, tokenize=False, add_generation_prompt=False)
        bi, T = bucket_ids(text)
        u, c = np.unique(bi, return_counts=True)
        g = per_game.setdefault(game, {"tokens": 0, "lookups": [], "runs": 0})
        g["tokens"] += T; g["lookups"].append((u, c)); g["runs"] += 1
    print(f"{run}: done, {len(per_game)} games so far, {time.time() - t0:.0f}s", flush=True)

game_count = np.zeros(V, dtype=np.uint8); union = np.zeros(V, dtype=np.bool_)
game_union = {}
for game, g in per_game.items():
    u = np.unique(np.concatenate([x[0] for x in g["lookups"]])); game_union[game] = u
    game_count[u] += 1; union[u] = True
res_games = {}
for game, g in per_game.items():
    hits = looks = 0
    for u, c in g["lookups"]:
        h = game_count[u] >= 2                       # touched by at least one OTHER game
        hits += int(c[h].sum()); looks += int(c.sum())
    res_games[game] = {"runs": g["runs"], "tokens": g["tokens"], "lookups": looks, "hit_rate_from_other_games": hits / looks,
                       "rows_touched": int(game_union[game].size)}
rates = [v["hit_rate_from_other_games"] for v in res_games.values()]
res = {"runs": a.runs, "games": len(res_games), "tokens": int(sum(v["tokens"] for v in res_games.values())),
       "table_rows": V, "union_rows": int(union.sum()), "union_fraction": float(union.sum() / V),
       "union_table_MB_bf16": float(union.sum() * row_bytes / 1e6), "full_table_MB_bf16": float(V * row_bytes / 1e6),
       "leave_one_game_out_hit_rate": {"mean": float(np.mean(rates)), "min": float(np.min(rates)), "max": float(np.max(rates))},
       "per_game": res_games}
os.makedirs(os.path.dirname(a.out), exist_ok=True); json.dump(res, open(a.out, "w"), indent=1)
# the rows each game touched (all runs), so any restricted table can be built later: rows_<game> = sorted int64 ids
np.savez_compressed(a.out.replace(".json", "_rows.npz"), **{f"rows_{g}": u for g, u in game_union.items()})
print(json.dumps({k: v for k, v in res.items() if k != "per_game"}, indent=1))
print("per game hit rate:", {k: round(v["hit_rate_from_other_games"], 4) for k, v in sorted(res_games.items(), key=lambda x: x[1]["hit_rate_from_other_games"])})
