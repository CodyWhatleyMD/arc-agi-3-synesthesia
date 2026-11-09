#!/usr/bin/env python3
"""Aggregate the four-arm board-tower play run into the report table.

Sources, per arm directory under runs/board_tower_play/<arm>/:
  benchmark.json      Duck's own record: levels_completed, actions_per_level, history (per-action tokens
                      and cumulative wall clock), final_wallclock_seconds -- one entry per GAME RUN.
  board_tower.jsonl   this harness's instrumentation: student load, pre-flight, every hydration (uuids,
                      bytes), every completion (the SERVER's prompt_tokens), the end-of-run summary.
  *requests.jsonl     Duck's own request log: the independent check that an image_embeds part (and NOT an
                      image_url part) was in the messages of every request of the tower arm.
Usage: report_play_ab.py [runs/board_tower_play]
"""
import collections, glob, json, os, pathlib, statistics, sys

ROOT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "runs/board_tower_play")
ARMS = ["text", "png4", "png32", "tower"]
IMG_TOKENS = {"text": 0, "png4": 66, "png32": 4098, "tower": 4098}


def arm_rows(a: pathlib.Path):
    f = a / "benchmark.json"
    if not f.is_file():
        return None
    b = json.load(open(f))
    rows = []
    for gr in b["game_runs"]:
        hist = gr.get("history") or []
        rows.append({
            "game": gr["game_id"].split("-")[0], "game_id": gr["game_id"],
            "levels": int(gr.get("levels_completed") or 0),
            "score": float(gr.get("final_score") or 0.0),
            "state": gr.get("state"),
            "actions": len(hist),
            "gen_tokens": sum(int(h.get("generated_tokens") or 0) for h in hist),
            "wall_s": float(gr.get("final_wallclock_seconds") or 0.0),
            "n_levels": gr.get("number_of_levels"),
            "ref_l1": (gr.get("base_actions_per_level") or [None])[0],
        })
    return rows, b


def arm_trace(a: pathlib.Path):
    p = a / "board_tower.jsonl"
    out = {"summary": None, "completions": [], "hydrated": [], "preflight": None, "student": None}
    if not p.is_file():
        return out
    for l in open(p, errors="replace"):
        if not l.strip():
            continue
        try:
            r = json.loads(l)
        except Exception:
            continue
        e = r.get("event")
        if e == "summary":
            out["summary"] = r
        elif e == "completion":
            out["completions"].append(r)
        elif e == "hydrated":
            out["hydrated"].append(r)
        elif e == "preflight_ok":
            out["preflight"] = r
        elif e == "student_loaded":
            out["student"] = r
    return out


def wire_check(a: pathlib.Path):
    """Independent of our own counters: what Duck's OWN request log shows."""
    n_req = n_emb_req = n_url_req = 0
    uuids = collections.Counter()
    for p in glob.glob(str(a / "**" / "*requests.jsonl"), recursive=True):
        for l in open(p, errors="replace"):
            if not l.strip():
                continue
            try:
                r = json.loads(l)
            except Exception:
                continue
            if r.get("event") != "request":
                continue
            n_req += 1
            e = u = 0
            for m in r.get("messages", []):
                c = m.get("content")
                if isinstance(c, list):
                    for q in c:
                        if isinstance(q, dict) and q.get("type") == "image_embeds":
                            e += 1; uuids[q.get("uuid")] += 1
                        elif isinstance(q, dict) and q.get("type") == "image_url":
                            u += 1
            n_emb_req += bool(e); n_url_req += bool(u)
    return {"requests": n_req, "requests_with_embeds": n_emb_req,
            "requests_with_image_url": n_url_req, "distinct_uuids": len(uuids)}


def med(xs):
    return statistics.median(xs) if xs else float("nan")


data = {}
for name in ARMS:
    a = ROOT / name
    got = arm_rows(a)
    if got is None:
        continue
    rows, bench = got
    data[name] = {"rows": rows, "trace": arm_trace(a), "wire": wire_check(a), "bench": bench}

if not data:
    sys.exit(f"no arm with a benchmark.json under {ROOT}")

games = sorted({r["game"] for d in data.values() for r in d["rows"]})

print("=" * 108)
print("BOARD-TOWER VISION AT GAME LEVEL -- four arms, matched actions, same games, same server")
print("=" * 108)
cfg = (ROOT / list(data)[0] / "ARM_CONFIG")
if cfg.is_file():
    print("config: " + "  ".join(l.strip() for l in open(cfg) if not l.startswith(("extra", "started", "finished"))))
print()

# ---------------------------------------------------------------- primary table
hdr = f"{'arm':6s} {'img tok':>7s} {'runs':>4s} {'LEVELS':>6s} {'runs>0':>6s} " + \
      "  ".join(f"{g:>9s}" for g in games) + \
      f" {'actions':>7s} {'s/action':>8s} {'gen tok':>8s}"
print(hdr); print("-" * len(hdr))
for name in ARMS:
    if name not in data:
        continue
    rows = data[name]["rows"]
    per_game = {g: [r["levels"] for r in rows if r["game"] == g] for g in games}
    acts = sum(r["actions"] for r in rows)
    wall = sum(r["wall_s"] for r in rows)
    cells = "  ".join(f"{('+'.join(str(v) for v in per_game[g]) or '-'):>9s}" for g in games)
    print(f"{name:6s} {IMG_TOKENS[name]:7d} {len(rows):4d} {sum(r['levels'] for r in rows):6d} "
          f"{sum(1 for r in rows if r['levels'] > 0):6d} {cells} {acts:7d} "
          f"{(wall/acts if acts else float('nan')):8.1f} {sum(r['gen_tokens'] for r in rows):8d}")
print("\nper-game cells are levels completed, one number per pass (a+b = pass0+pass1).")
print("reference actions for level 1: " + ", ".join(
    f"{g}={next((r['ref_l1'] for d in data.values() for r in d['rows'] if r['game'] == g), '?')}" for g in games))

# ---------------------------------------------------------------- liveness proof
print("\n" + "=" * 108)
print("WAS THE TOWER PATH ACTUALLY LIVE?  (Duck's own request log, independent of our counters)")
print("=" * 108)
print(f"{'arm':6s} {'requests':>8s} {'w/ embeds':>9s} {'w/ img_url':>10s} {'uuids':>6s} "
      f"{'prompt_tok med':>14s} {'min':>6s} {'max':>6s} {'fallback_png':>12s} {'MB sent':>8s}")
for name in ARMS:
    if name not in data:
        continue
    w = data[name]["wire"]; t = data[name]["trace"]
    pt = [c["prompt_tokens"] for c in t["completions"] if c.get("prompt_tokens")]
    s = t["summary"] or {}
    mb = s.get("bytes_hydrated", 0) / 1e6
    print(f"{name:6s} {w['requests']:8d} {w['requests_with_embeds']:9d} {w['requests_with_image_url']:10d} "
          f"{w['distinct_uuids']:6d} {med(pt):14.0f} {(min(pt) if pt else 0):6.0f} {(max(pt) if pt else 0):6.0f} "
          f"{s.get('fallback_png', '-'):>12} {mb:8.0f}")
t = data.get("tower", {}).get("trace") or {}
if t.get("student"):
    st = t["student"]
    print(f"\nstudent: {st.get('ckpt')}  step {st.get('step')}  params {st.get('params'):,}  "
          f"n_pos {st.get('n_pos')}  device {st.get('device')}  ckpt_tag {st.get('tag')}")
    print(f"source:  {st.get('module_root')}  sha {st.get('module_sha')}")
if t.get("summary"):
    s = dict(t["summary"]); s.pop("t", None); s.pop("event", None)
    print("tower summary: " + json.dumps(s, sort_keys=True))

# ---------------------------------------------------------------- failures
print("\n" + "=" * 108)
print("FAILURE SIGNALS PER ARM")
print("=" * 108)
for name in ARMS:
    if name not in data:
        continue
    log = ROOT / name / "run.log"
    txt = log.read_text(errors="replace") if log.is_file() else ""
    co = ROOT / name / "ctx_overflow.jsonl"
    n_ovf = sum(1 for l in open(co, errors="replace") if '"context_overflow"' in l) if co.is_file() else 0
    print(f"{name:6s} analyzer_failures={txt.count('analyzer request failed'):4d} "
          f"timeouts={txt.count('analyzer timed out') + txt.count('ReadTimeout'):3d} "
          f"http500={txt.count(' 500 ')+txt.count('500 Error'):4d} "
          f"ctx_overflow={n_ovf:3d} tracebacks={txt.count('Traceback'):3d} "
          f"states={dict(collections.Counter(r['state'] for r in data[name]['rows']))}")

out = {"arms": {n: {"rows": d["rows"], "wire": d["wire"],
                    "summary": d["trace"]["summary"], "img_tokens": IMG_TOKENS[n],
                    "prompt_tokens": [c.get("prompt_tokens") for c in d["trace"]["completions"]]}
                for n, d in data.items()}}
p = ROOT / "report.json"
json.dump(out, open(p, "w"), indent=1, default=str)
print(f"\nwrote {p}")
