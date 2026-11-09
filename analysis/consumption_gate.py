#!/usr/bin/env python3
"""Consumption gate (CL3's review 10-28, area 1): did the server COUNT the boards the client sent?

The client prices each board part at a fixed token count and reports `estimated_prompt_tokens`; the server reports the
actual `prompt_tokens`. If the server consumed the board parts, actual/estimate stays flat as boards per request grow
(1.0-1.2 at every count); if it dropped them, the ratio falls with the number of boards (to ~0.7 at 8 boards, ~0.4 at
31). Joined per game by request order: metrics/<game>_p0_metrics.jsonl (event=request: request_index, estimated,
actual) with <game>_p0_requests.jsonl (event=request: the parts in its messages).

usage: consumption_gate.py <run working dir> [more dirs...]   (e.g. ~/kaggle_local/working_r2_9300)
Exit 0 = PASS for every dir; 1 = a dir failed or had no board-carrying requests to judge.
"""
from __future__ import annotations

import glob
import json
import os
import statistics
import sys

BUCKETS = [(1, 1), (2, 4), (5, 8), (9, 16), (17, 10**6)]


def requests_boards(path):
    out = []
    for line in open(path, errors="replace"):
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        if d.get("event") != "request":
            continue
        n = 0
        for m in d.get("messages", []):
            c = m.get("content")
            if isinstance(c, list):
                n += sum(1 for p in c if p.get("type") in ("image_embeds", "image_url"))
        out.append(n)
    return out


def metrics_ratios(path):
    out = []
    for line in open(path, errors="replace"):
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        if d.get("event") != "request":
            continue
        try:
            est, act = int(d["estimated_prompt_tokens"]), int(d["prompt_tokens"])
        except (KeyError, ValueError):
            continue
        if est > 0 and act > 0:
            out.append(act / est)
    return out


def judge(workdir):
    rows = []  # (boards, ratio)
    joined = games = 0
    for req in sorted(glob.glob(os.path.join(workdir, "**", "*_p0_requests.jsonl"), recursive=True)):
        game = os.path.basename(req).replace("_requests.jsonl", "")
        met = glob.glob(os.path.join(workdir, "**", "metrics", game + "_metrics.jsonl"), recursive=True)
        if not met:
            continue
        b, r = requests_boards(req), metrics_ratios(met[0])
        games += 1
        n = min(len(b), len(r))
        if len(b) != len(r):
            print(f"  {game}: request log {len(b)} vs metrics {len(r)} requests; joining the first {n}", file=sys.stderr)
        rows += list(zip(b[:n], r[:n]))
        joined += n
    table = {}
    for lo, hi in BUCKETS:
        rs = [r for b_, r in rows if lo <= b_ <= hi]
        if rs:
            table[(lo, hi)] = (len(rs), statistics.median(rs))
    print(f"{workdir}: games {games}, requests joined {joined}")
    for (lo, hi), (n, med) in table.items():
        print(f"  boards {lo:>2}-{hi if hi < 10**6 else '+':<3} n={n:5d}  median actual/estimate = {med:.3f}")
    one = table.get((1, 1))
    heavy = [(k, v) for k, v in table.items() if k[0] >= 5 and v[0] >= 20]
    if not one or not heavy:
        print("  NO JUDGEMENT: need a 1-board bucket and a >=5-board bucket with >=20 requests")
        return None
    hk, (hn, hmed) = heavy[-1]
    ok = hmed >= 0.8 * one[1]
    print(f"  {'PASS' if ok else 'FAIL'}: {hk[0]}+ boards median {hmed:.3f} vs 1-board {one[1]:.3f} "
          f"(dropped boards would read ~{one[1] * (1 - 0.6):.2f} or lower at that count)")
    return ok


if __name__ == "__main__":
    results = [judge(d) for d in sys.argv[1:]]
    sys.exit(0 if results and all(r is True for r in results) else 1)
