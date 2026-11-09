#!/usr/bin/env python3
"""Score local vs reference per continuation position: top-1 agreement, mean logprob our model gives
the reference's greedy token, and KL(ref||ours) over the union of the two top-k supports (renormalised
within the support -- an approximation the paper states as such)."""
import argparse, json, math, statistics as st
ap = argparse.ArgumentParser(); ap.add_argument("--api", default="runs/flashnext/fidelity_api.jsonl"); ap.add_argument("--local", required=True); ap.add_argument("--json", default="")
a = ap.parse_args()
api = {r["i"]: r for r in (json.loads(l) for l in open(a.api) if l.strip())}
loc = [json.loads(l) for l in open(a.local) if l.strip()]
agree = []; ref_lp = []; kls = []; used = 0; skipped = 0
for L in loc:
    R = api.get(L["i"])
    if not R or not L["aligned"]: skipped += 1; continue
    used += 1
    if not R.get("tokens"):                       # text-only reference: agreement = our argmax == the reference's actual next token
        for j in range(L["n"]):
            agree.append(1.0 if L["top"][j][0][1] >= max(v for _, v in L["top"][j]) and L["ref_token_logprob"][j] >= L["top"][j][0][1] - 1e-6 else 0.0)
            ref_lp.append(L["ref_token_logprob"][j])
        continue
    for j in range(min(L["n"], len(R["tokens"]))):
        rt = R["tokens"][j]; ref_top = dict(rt["top"]); our_top = dict(L["top"][j])
        agree.append(1.0 if L["top"][j][0][0] == rt["token"] else 0.0)
        ref_lp.append(L["ref_token_logprob"][j])
        keys = set(ref_top) | set(our_top)
        def norm(d): z = sum(math.exp(v) for v in d.values()); return {k: math.exp(v) / z for k, v in d.items()}
        p, q = norm(ref_top), norm(our_top); eps = 1e-9
        kls.append(sum(p.get(k, 0.0) * math.log((p.get(k, 0.0) + eps) / (q.get(k, 0.0) + eps)) for k in keys if p.get(k, 0.0) > 0))
res = {"prompts_used": used, "prompts_skipped": skipped, "positions": len(agree), "top1_agreement": st.mean(agree) if agree else None,
       "mean_logprob_of_ref_token": st.mean(ref_lp) if ref_lp else None, "kl_ref_ours_topk_support": st.mean(kls) if kls else None, "kl_median": st.median(kls) if kls else None}
print(json.dumps(res, indent=1))
if a.json: json.dump(res, open(a.json, "w"), indent=1)
