#!/usr/bin/env python3
"""Pool the replication blocks and test the arm differences.

Primary endpoint: levels completed per game-run. Test: exact two-sided PERMUTATION test on the
difference in TOTAL levels, permuting the arm label WITHIN each (game, block) stratum -- the strata
are the only thing the two arms share, since passes are independent draws at temperature 0.6.
Also reported: runs>0, a paired-by-game sign summary, and the budget columns, so a reader can see
whether the arms were given the same run.
Usage: pool_play_ab.py runs/board_tower_play runs/board_tower_play_b2
"""
import itertools, json, pathlib, statistics, sys

ROOTS = [pathlib.Path(p) for p in (sys.argv[1:] or ["runs/board_tower_play", "runs/board_tower_play_b2"])]
ARMS = ["text", "png4", "png32", "tower"]
IMG = {"text": 0, "png4": 66, "png32": 4098, "tower": 4098}

rows = {a: [] for a in ARMS}            # (block, game, levels, actions, wall, gen, score)
for bi, root in enumerate(ROOTS):
    for a in ARMS:
        f = root / a / "benchmark.json"
        if not f.is_file():
            print(f"  (missing {f})"); continue
        for gr in json.load(open(f))["game_runs"]:
            h = gr.get("history") or []
            rows[a].append((bi, gr["game_id"].split("-")[0], int(gr.get("levels_completed") or 0),
                            len(h), float(gr.get("final_wallclock_seconds") or 0.0),
                            sum(int(x.get("generated_tokens") or 0) for x in h),
                            float(gr.get("final_score") or 0.0)))

games = sorted({r[1] for a in ARMS for r in rows[a]})
nb = len(ROOTS)

print("=" * 100)
print(f"POOLED: {nb} independent block(s) x 2 passes x {len(games)} games = {len(rows['tower'])} game-runs per arm")
print("=" * 100)
h = f"{'arm':6s} {'img tok':>7s} {'runs':>4s} {'LEVELS':>6s} {'runs>0':>6s} " + \
    " ".join(f"{g:>12s}" for g in games) + f" {'actions':>7s} {'TAAF%':>7s} {'s/act':>6s} {'gen tok':>8s}"
print(h); print("-" * len(h))
for a in ARMS:
    R = rows[a]
    if not R:
        continue
    cells = []
    for g in games:
        v = [r[2] for r in R if r[1] == g]
        cells.append(f"{sum(v)} ({'+'.join(map(str, v))})")
    acts = sum(r[3] for r in R); wall = sum(r[4] for r in R)
    print(f"{a:6s} {IMG[a]:7d} {len(R):4d} {sum(r[2] for r in R):6d} {sum(1 for r in R if r[2] > 0):6d} "
          + " ".join(f"{c:>12s}" for c in cells)
          + f" {acts:7d} {sum(r[6] for r in R)/len(R):7.2f} {wall/max(acts,1):6.1f} {sum(r[5] for r in R):8d}")
print("\nper-game cell: total levels (per-game-run breakdown, in block/pass order)")

# ---------------- stratified permutation test ----------------
def perm_p(a, b, nmax=200000):
    """Exact/MC two-sided permutation test on sum(a)-sum(b), permuting the label within (block, game)."""
    A, B = rows[a], rows[b]
    strata = {}
    for r in A:
        strata.setdefault((r[0], r[1]), [[], []])[0].append(r[2])
    for r in B:
        strata.setdefault((r[0], r[1]), [[], []])[1].append(r[2])
    obs = sum(sum(v[0]) for v in strata.values()) - sum(sum(v[1]) for v in strata.values())
    pools, nA = [], []
    for k in sorted(strata):
        x, y = strata[k]
        pools.append(x + y); nA.append(len(x))
    combos = [list(itertools.combinations(range(len(p)), k)) for p, k in zip(pools, nA)]
    total = 1
    for c in combos:
        total *= len(c)
    if total > nmax:
        import random
        rng = random.Random(0)
        draws = []
        for _ in range(nmax):
            d = 0
            for p, k in zip(pools, nA):
                s = rng.sample(range(len(p)), k)
                sa = sum(p[i] for i in s); d += sa - (sum(p) - sa)
            draws.append(d)
        hits = sum(1 for d in draws if abs(d) >= abs(obs) - 1e-9)
        return obs, hits / len(draws), f"MC {nmax:,}"
    hits = n = 0
    for pick in itertools.product(*combos):
        d = 0
        for p, s in zip(pools, pick):
            sa = sum(p[i] for i in s); d += sa - (sum(p) - sa)
        n += 1; hits += abs(d) >= abs(obs) - 1e-9
    return obs, hits / n, f"exact {n:,}"

print("\n" + "=" * 100)
print("ARM DIFFERENCES -- stratified permutation test on TOTAL LEVELS (strata = block x game)")
print("=" * 100)
for a, b in (("tower", "png32"), ("tower", "text"), ("tower", "png4"),
             ("png32", "text"), ("png32", "png4"), ("png4", "text")):
    if not (rows[a] and rows[b]):
        continue
    obs, p, how = perm_p(a, b)
    print(f"  {a:6s} - {b:6s}: observed {obs:+3d} levels   p = {p:.3f}   ({how} permutations)"
          + ("   <-- the one-variable comparison" if (a, b) == ("tower", "png32") else ""))

out = {"roots": [str(r) for r in ROOTS], "rows": {a: rows[a] for a in ARMS},
       "tests": {f"{a}-{b}": dict(zip(("observed", "p", "how"), perm_p(a, b)))
                 for a, b in (("tower", "png32"), ("tower", "text"), ("tower", "png4"),
                              ("png32", "text"), ("png32", "png4"), ("png4", "text"))
                 if rows[a] and rows[b]}}
p = ROOTS[0] / "pooled.json"
json.dump(out, open(p, "w"), indent=1)
print(f"\nwrote {p}")
