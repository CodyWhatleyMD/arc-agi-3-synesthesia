#!/usr/bin/env python3
"""Does a task-restricted PLE table change what the model says? (CL2 10-30; the investigator 15:23 "measure it")

Replays REAL requests of the five test games (cd82 m0r0 re86 s5i5 sk48; local control run r2, harness 8552964) against
the measurement server (~/kaggle_local/serve_ple_measure.sh): request indices 0, 5, 15, 40 per game = 20 prompts, the
logged body unchanged (messages incl. the board's image_embeds, tools, tool_choice; the server's default chat kwargs,
reasoning effort xhigh), greedy (temperature 0), 512 new tokens, ONE AT A TIME (no batching noise), with the chosen
tokens' logprobs. Run it against the full-table server twice (the run-to-run floor) and against the masked server
(rows touched only by the 20 OTHER games kept; the rest read as zeros) once, then `compare`:
  - first divergence: the first generated position where the token differs from the full-table pass
  - token agreement over the 512 positions, and the mean logprob of the chosen tokens
usage: ple_fidelity.py run --tag full1|full2|masked    |    ple_fidelity.py compare
"""
import argparse, glob, json, os, sys, time
import requests

OUT = "/mnt/data/ple_measure"
TEST = ["cd82", "m0r0", "re86", "s5i5", "sk48"]
IDX = [0, 5, 15, 40]
BASE = "http://127.0.0.1:1234/v1"


REPO = "/home/ignaz/github/arc-prize-2026"
STUDENT = "/media/ignaz/claude-extra/board_tower/ckpt_px16_dih/best.pt"     # the shipped px16 student (tag 5e4eb805a8)


def restore_boards(messages, board_of, student):
    """The request log elides every image_embeds payload (harness transcript_log.py). Rebuild each part from its board:
    the uuid carries the board's sha1, the game's events log carries the board, the shipped student re-encodes it."""
    sys.path.insert(0, REPO)
    from scripts.board_tower import export_embeds as ee
    n = 0
    for m in messages:
        if not isinstance(m.get("content"), list):
            continue
        for k, part in enumerate(m["content"]):
            if part.get("type") == "image_embeds" and "_elided_image_embeds_b64_bytes" in part.get("image_embeds", {}):
                sha = part["uuid"].rsplit("-", 1)[1]
                if not part["uuid"].startswith(f"tower-g1024-{student.tag}-"):
                    raise SystemExit(f"part {part['uuid']} was not made by the shipped student {student.tag}")
                new = ee.build_image_embeds(board_of[sha], student)
                if new["uuid"] != part["uuid"]:
                    raise SystemExit(f"rebuilt uuid {new['uuid']} != logged {part['uuid']}")
                m["content"][k] = new; n += 1
    return n


def prompts():
    import numpy as np
    sys.path.insert(0, REPO)
    from scripts.board_tower import export_embeds as ee, common as C
    student = ee.Student(STUDENT, device="cpu")
    out = []
    for g in TEST:
        f = glob.glob(f"/home/ignaz/kaggle_local/working_r2_9300/synesthesia/{g}-*_p0_requests.jsonl")[0]
        ev = f.replace("_requests.jsonl", "_events.jsonl").replace("/synesthesia/", "/synesthesia/artifacts/")
        board_of = {}
        for line in open(ev):
            b = json.loads(line).get("board")
            if isinstance(b, list) and len(b) == 64:
                board_of[C.board_sha1(np.asarray(b, np.uint8))] = np.asarray(b, np.int64)
        recs = open(f).read().splitlines()
        for i in IDX:
            if i < len(recs):
                r = json.loads(recs[i]); restore_boards(r["messages"], board_of, student); out.append((g, i, r))
    return out


def cmd_run(a):
    mid = requests.get(f"{BASE}/models", timeout=30).json()["data"][0]["id"]
    path = f"{OUT}/gen_{a.tag}.jsonl"; done = set()
    if os.path.exists(path):
        done = {(json.loads(l)["game"], json.loads(l)["idx"]) for l in open(path)}
    for g, i, r in prompts():
        if (g, i) in done:
            continue
        body = {"model": mid, "messages": r["messages"], "tools": r.get("tools"), "tool_choice": r.get("tool_choice", "auto"),
                "temperature": 0.0, "max_tokens": 512, "logprobs": True, "seed": 0}
        t0 = time.time(); resp = requests.post(f"{BASE}/chat/completions", json=body, timeout=3600); dt = time.time() - t0
        rec = {"game": g, "idx": i, "status": resp.status_code, "seconds": dt}
        if resp.status_code == 200:
            j = resp.json(); ch = j["choices"][0]
            toks = [(t["token"], t["logprob"]) for t in (ch.get("logprobs") or {}).get("content") or []]
            rec.update({"tokens": [t for t, _ in toks], "logprobs": [lp for _, lp in toks], "usage": j.get("usage"),
                        "finish": ch.get("finish_reason")})
        else:
            rec["error"] = resp.text[:400]
            raise SystemExit(f"{g}#{i}: HTTP {resp.status_code}: {rec['error']}")   # fail closed: no silent error rows
        with open(path, "a") as f:
            f.write(json.dumps(rec) + "\n")
        print(f"{time.strftime('%H:%M:%S')} {a.tag} {g}#{i}: {rec['status']} {dt:.0f}s prompt {((rec.get('usage') or {}).get('prompt_tokens'))} "
              f"gen {len(rec.get('tokens', []))}", flush=True)


def load(tag):
    p = f"{OUT}/gen_{tag}.jsonl"
    return {(json.loads(l)["game"], json.loads(l)["idx"]): json.loads(l) for l in open(p)} if os.path.exists(p) else {}


def cmd_compare(a):
    ref = load("full1"); res = {}
    for tag in ("full2", "masked"):
        other = load(tag); rows = []
        for k, r in ref.items():
            o = other.get(k)
            if not o or r["status"] != 200 or o["status"] != 200:
                continue
            A, B = r["tokens"], o["tokens"]; n = min(len(A), len(B))
            div = next((i for i in range(n) if A[i] != B[i]), None)
            rows.append({"game": k[0], "idx": k[1], "prompt_tokens": (r.get("usage") or {}).get("prompt_tokens"),
                         "first_divergence": div if div is not None else (n if len(A) == len(B) else n),
                         "identical": div is None and len(A) == len(B), "agree_frac": sum(A[i] == B[i] for i in range(n)) / max(n, 1),
                         "mean_lp_ref": sum(r["logprobs"]) / max(len(r["logprobs"]), 1), "mean_lp": sum(o["logprobs"]) / max(len(o["logprobs"]), 1)})
        if rows:
            res[tag] = {"prompts": len(rows), "identical": sum(x["identical"] for x in rows),
                        "first_divergence_median": sorted(x["first_divergence"] for x in rows)[len(rows) // 2],
                        "agree_frac_mean": sum(x["agree_frac"] for x in rows) / len(rows), "rows": rows}
    json.dump(res, open(f"{OUT}/compare.json", "w"), indent=1)
    for tag, v in res.items():
        print(f"{tag} vs full1: {v['prompts']} prompts, identical {v['identical']}, median first divergence {v['first_divergence_median']}, "
              f"mean token agreement {v['agree_frac_mean']:.3f}")
        for x in v["rows"]:
            print(f"   {x['game']}#{x['idx']:<3} prompt {x['prompt_tokens']}: first divergence {x['first_divergence']}, agree {x['agree_frac']:.3f}, "
                  f"mean lp {x['mean_lp_ref']:.3f} -> {x['mean_lp']:.3f}")


ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd", required=True)
r = sub.add_parser("run"); r.add_argument("--tag", required=True)
sub.add_parser("compare")
a = ap.parse_args(); {"run": cmd_run, "compare": cmd_compare}[a.cmd](a)
