#!/usr/bin/env python3
"""Report the real-budget board-tower run: actions-to-first-level (primary) + levels, split by whether
the game is in the student's TRAINING set or HELD OUT.

Primary endpoint is actions to the first cleared level. A run that never clears is CENSORED at the
action cap and reported as ">cap", never as the cap -- treating a censored run as `cap` would bias the
mean downward for whichever arm clears least.
Usage: report_real_ab.py [runs/board_tower_play_real]
"""
import collections, glob, itertools, json, os, pathlib, statistics, sys

ROOT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "runs/board_tower_play_real")
ARMS = ["text", "png32", "tower"]
IMG = {"text": 0, "png4": 66, "png32": 4098, "tower": 4098}
# the student's held-out games (board_tower targets manifest `holdout_games`)
HELD = {"cd82", "m0r0", "re86", "s5i5", "sk48"}

def rows(arm):
    f = ROOT / arm / "benchmark.json"
    if not f.is_file():
        return []
    out = []
    for gr in json.load(open(f))["game_runs"]:
        h = gr.get("history") or []
        apl = gr.get("actions_per_level") or []
        lv = int(gr.get("levels_completed") or 0)
        g = gr["game_id"].split("-")[0]
        out.append({
            "game": g, "held": g in HELD, "levels": lv, "actions": len(h),
            # actions_per_level[0] is the actions spent on level 1; it is the actions-to-first-clear
            # only when at least one level was cleared.
            "a2f": (int(apl[0]) if (lv >= 1 and apl) else None),
            "wall": float(gr.get("final_wallclock_seconds") or 0.0),
            "gen": sum(int(x.get("generated_tokens") or 0) for x in h),
            "score": float(gr.get("final_score") or 0.0), "state": gr.get("state"),
            "apl": apl[:4],
        })
    return out

D = {a: rows(a) for a in ARMS}
D = {a: v for a, v in D.items() if v}
if not D:
    sys.exit(f"no arm with a benchmark.json under {ROOT}")
games = sorted({r["game"] for v in D.values() for r in v}, key=lambda g: (g in HELD, g))
cap = max(r["actions"] for v in D.values() for r in v)

print("=" * 112)
print(f"REAL-BUDGET BOARD-TOWER RUN -- action cap {cap}, {len(next(iter(D.values())))} game-runs per arm")
print("=" * 112)
print("games: " + "  ".join(f"{g}{'[HELD OUT]' if g in HELD else '[trained]'}" for g in games))

print("\n--- PRIMARY: actions to first cleared level (lower is better; >cap = never cleared) ---")
h = f"{'arm':6s} " + " ".join(f"{g:>14s}" for g in games) + f" {'cleared':>8s} {'median a2f':>11s}"
print(h); print("-" * len(h))
for a in ARMS:
    if a not in D: continue
    cells = []
    for g in games:
        v = [r for r in D[a] if r["game"] == g]
        cells.append(",".join(str(r["a2f"]) if r["a2f"] is not None else f">{r['actions']}" for r in v))
    got = [r["a2f"] for r in D[a] if r["a2f"] is not None]
    print(f"{a:6s} " + " ".join(f"{c:>14s}" for c in cells)
          + f" {len(got):3d}/{len(D[a]):<4d} {(statistics.median(got) if got else float('nan')):11.1f}")

print("\n--- SECONDARY: levels completed ---")
h2 = f"{'arm':6s} {'img tok':>7s} {'LEVELS':>6s} {'runs>0':>6s} {'trained':>8s} {'HELD OUT':>9s} " + \
     " ".join(f"{g:>9s}" for g in games) + f" {'actions':>7s} {'tok/s':>6s} {'gen tok':>8s}"
print(h2); print("-" * len(h2))
for a in ARMS:
    if a not in D: continue
    R = D[a]
    tr = sum(r["levels"] for r in R if not r["held"]); he = sum(r["levels"] for r in R if r["held"])
    act = sum(r["actions"] for r in R); wall = sum(r["wall"] for r in R); gen = sum(r["gen"] for r in R)
    cells = ["+".join(str(r["levels"]) for r in R if r["game"] == g) for g in games]
    print(f"{a:6s} {IMG[a]:7d} {sum(r['levels'] for r in R):6d} {sum(1 for r in R if r['levels']>0):6d} "
          f"{tr:8d} {he:9d} " + " ".join(f"{c:>9s}" for c in cells)
          + f" {act:7d} {gen/max(wall,1):6.1f} {gen:8d}")

print("\n--- permutation test on TOTAL LEVELS (strata = game), and on trained/held-out subsets ---")
def perm(a, b, subset=None, nmax=200000):
    A = [r for r in D[a] if subset is None or r["held"] == subset]
    B = [r for r in D[b] if subset is None or r["held"] == subset]
    st = {}
    for r in A: st.setdefault(r["game"], [[], []])[0].append(r["levels"])
    for r in B: st.setdefault(r["game"], [[], []])[1].append(r["levels"])
    obs = sum(sum(v[0]) for v in st.values()) - sum(sum(v[1]) for v in st.values())
    pools, nA = [], []
    for k in sorted(st):
        x, y = st[k]; pools.append(x + y); nA.append(len(x))
    combos = [list(itertools.combinations(range(len(p)), k)) for p, k in zip(pools, nA)]
    tot = 1
    for c in combos: tot *= len(c)
    hits = n = 0
    for pick in itertools.product(*combos):
        d = 0
        for p, s in zip(pools, pick):
            sa = sum(p[i] for i in s); d += sa - (sum(p) - sa)
        n += 1; hits += abs(d) >= abs(obs) - 1e-9
    return obs, hits / n, n
for a, b in (("tower", "png32"), ("tower", "text"), ("png32", "text")):
    if not (a in D and b in D): continue
    for lbl, sub in (("all", None), ("trained", False), ("HELD OUT", True)):
        o, p, n = perm(a, b, sub)
        print(f"  {a:6s} - {b:6s}  [{lbl:8s}]: {o:+3d} levels  p = {p:.3f}  ({n:,} perms)")

print("\n--- per-run detail ---")
for a in ARMS:
    if a not in D: continue
    print(f"  {a}:")
    for r in D[a]:
        print(f"    {r['game']:5s} {'HELD' if r['held'] else 'trn ':4s} levels={r['levels']} "
              f"a2f={r['a2f'] if r['a2f'] is not None else '>'+str(r['actions']):>5} "
              f"actions={r['actions']:3d} apl={r['apl']} score={r['score']:5.2f} {r['state']}")

json.dump({a: D[a] for a in D}, open(ROOT / "report_real.json", "w"), indent=1, default=str)
print(f"\nwrote {ROOT/'report_real.json'}")
