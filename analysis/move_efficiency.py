"""Move efficiency, timed controls vs untimed runs (paper section 4; the question a reviewer asks: did the clock-free
model play the same game per action, or a different one?).

Inputs: the four timed v36 controls (r2, r3, r4, r6; 65-minute per-game clock, 9,300 s job budget) and the four complete
concurrency-14 untimed runs (r0c14, r0c14b, r0x1, r0x2), read from their benchmark.json files through results_index.
For a game record, actions_per_level[k-1] is the actions spent on level k (the uncompleted level's actions are the entry
at index levels_completed), so the cost of reaching level k is sum(actions_per_level[:k]).

Statistics (all paired by game; intervals are two-stage bootstraps, runs within each arm resampled first, then games;
10,000 replicates, seed 0, percentile 95%):
  same_action_window: for each game g and timed run t, N = t's actions on g; each untimed run is read at N actions
      (levels whose cumulative cost <= N). Timed value = t's levels; untimed value = mean over untimed runs. Also per
      100 actions and pooled (sum of levels / sum of actions inside the windows).
  matched_cells: (game, level) cells every timed run cleared; per cell, the mean actions on that level across the
      timed runs and across the untimed runs that cleared it.
  aggregate: levels per 100 actions over whole runs; actions spent on levels never completed.
  raw actions per completed level (all levels; censored on the timed side), and actions to reach level k.
Usage: python3 -I scripts/move_efficiency.py [--out notes/move_efficiency_timed_vs_untimed_YYYY-MM-DD.json]
"""
import json, os, sys, statistics as st, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import results_index as ri

TIMED = {n: ri.benchmark(f"{n}_9300", "local") for n in ("r2", "r3", "r4", "r6")}
UNTIMED = {"r0c14": ri.benchmark("r0c14", "local"), "r0c14b": ri.benchmark("r0c14b", "local"),
           "r0x1": ri.benchmark("r0x1", "vast"), "r0x2": ri.benchmark("r0x2", "vast")}
BOOT, SEED = 10000, 0

def games(path):
    out = {}
    for g in json.load(open(path))["game_runs"]:
        apl = [int(x) for x in g.get("actions_per_level") or []]
        if sum(apl) == 0: continue
        out[g["game_id"][:4]] = (int(g.get("levels_completed", 0)), apl)
    return out

T = {n: games(p) for n, p in TIMED.items()}
U = {n: games(p) for n, p in UNTIMED.items()}
ids = sorted(set.intersection(*(set(r) for r in list(T.values()) + list(U.values()))))

def levels_within(rec, N):
    L, apl = rec; c = 0; k = 0
    for i in range(L):
        c += apl[i]
        if c <= N: k = i + 1
        else: break
    return k

def boot_ci(per_game_fn, reps=BOOT, seed=SEED):
    """per_game_fn(timed_runs, untimed_runs) -> {game: delta}; two-stage: runs (with replacement, per arm), then games."""
    rng = random.Random(seed); tn, un = list(T), list(U); vals = []
    for _ in range(reps):
        ts = [T[rng.choice(tn)] for _ in tn]; us = [U[rng.choice(un)] for _ in un]
        d = per_game_fn(ts, us); gs = list(d)
        vals.append(st.mean(d[rng.choice(gs)] for _ in gs))
    vals.sort(); return [round(vals[int(0.025 * reps)], 3), round(vals[int(0.975 * reps) - 1], 3)]

# ---- same action window ----
def window_deltas(ts, us, per100=False):
    d = {}
    for g in ids:
        vals = []
        for t in ts:
            L, apl = t[g]; N = sum(apl)
            uw = st.mean(levels_within(u[g], N) for u in us)
            vals.append(((uw - L) / N * 100) if per100 else (uw - L))
        d[g] = st.mean(vals)
    return d
tv = [T[t][g][0] for g in ids for t in T]
uv = [st.mean(levels_within(U[u][g], sum(T[t][g][1])) for u in U) for g in ids for t in T]
tN = [sum(T[t][g][1]) for g in ids for t in T]
dw = window_deltas(list(T.values()), list(U.values()))
same_window = {
  "design": "for each game and each timed run t, N_t = t's actions on the game; untimed runs read at N_t actions (levels whose cumulative cost <= N_t); paired by game; bootstrap runs then games",
  "levels_within_window": {"timed": round(st.mean(tv), 2), "untimed": round(st.mean(uv), 2), "delta": round(st.mean(uv) - st.mean(tv), 2),
      "ci95_runlevel": boot_ci(lambda ts, us: window_deltas(ts, us)),
      "untimed_higher_games": sum(1 for g in ids if dw[g] > 0), "untimed_lower_games": sum(1 for g in ids if dw[g] < 0)},
  "levels_per_100_actions_within_window": {"timed": round(st.mean(a / n * 100 for a, n in zip(tv, tN)), 3), "untimed": round(st.mean(a / n * 100 for a, n in zip(uv, tN)), 3),
      "delta": round(st.mean((b - a) / n * 100 for a, b, n in zip(tv, uv, tN)), 3), "ci95_runlevel": boot_ci(lambda ts, us: window_deltas(ts, us, per100=True))},
  "pooled_within_window": {"timed_per_100": round(sum(tv) / sum(tN) * 100, 3), "untimed_per_100": round(sum(uv) / sum(tN) * 100, 3), "actions_per_run_in_windows": round(sum(tN) / len(T))}}

# ---- matched cells: every timed run cleared the level ----
cells = []
for g in ids:
    kmax = min(T[t][g][0] for t in T)
    for k in range(1, kmax + 1):
        tc = st.mean(T[t][g][1][k - 1] for t in T)
        ucl = [U[u][g][1][k - 1] for u in U if U[u][g][0] >= k]
        if ucl: cells.append((g, k, tc, st.mean(ucl)))
def cell_deltas(ts, us):
    d = {}
    for g in ids:
        kmax = min(t[g][0] for t in ts); ds = []
        for k in range(1, kmax + 1):
            ucl = [u[g][1][k - 1] for u in us if u[g][0] >= k]
            if ucl: ds.append(st.mean(ucl) - st.mean(t[g][1][k - 1] for t in ts))
        if ds: d[g] = st.mean(ds)
    return d
def cell_median_deltas(ts, us):
    d = cell_deltas(ts, us); m = st.median(d.values()); return {g: m for g in d}
matched = {"cells": len(cells), "games": len({c[0] for c in cells}),
  "timed_mean": round(st.mean(c[2] for c in cells), 1), "timed_median": round(st.median(c[2] for c in cells), 1),
  "untimed_mean": round(st.mean(c[3] for c in cells), 1), "untimed_median": round(st.median(c[3] for c in cells), 1),
  "delta_mean": round(st.mean(c[3] - c[2] for c in cells), 1), "delta_mean_ci95_runlevel": boot_ci(cell_deltas),
  "delta_median": round(st.median(c[3] - c[2] for c in cells), 1), "delta_median_ci95_runlevel": boot_ci(cell_median_deltas),
  "untimed_higher_cells": sum(1 for c in cells if c[3] > c[2]), "untimed_lower_cells": sum(1 for c in cells if c[3] < c[2])}

# ---- whole-run aggregates ----
def agg(R):
    L = sum(R[r][g][0] for r in R for g in ids); A = sum(sum(R[r][g][1]) for r in R for g in ids)
    unc = sum(sum(R[r][g][1][R[r][g][0]:]) for r in R for g in ids)
    return L, A, unc
tL, tA, tU = agg(T); uL, uA, uU = agg(U)
aggregate = {"timed": round(tL / tA * 100, 3), "untimed": round(uL / uA * 100, 3), "timed_levels_actions": [tL, tA], "untimed_levels_actions": [uL, uA]}
uncompleted = {"untimed": [uU, uA], "timed": [tU, tA]}

# ---- raw actions per completed level; actions to reach level k ----
def apcl(rec):
    L, apl = rec; return (sum(apl[:L]) / L) if L > 0 else None
def raw_deltas(ts, us):
    d = {}
    for g in ids:
        a = [apcl(t[g]) for t in ts if apcl(t[g]) is not None]; b = [apcl(u[g]) for u in us if apcl(u[g]) is not None]
        if a and b: d[g] = st.mean(b) - st.mean(a)
    return d
def reach(rec, k):
    L, apl = rec; return sum(apl[:k]) if L >= k else None
def reach_deltas(k):
    def f(ts, us):
        d = {}
        for g in ids:
            a = [reach(t[g], k) for t in ts if reach(t[g], k) is not None]; b = [reach(u[g], k) for u in us if reach(u[g], k) is not None]
            if a and b: d[g] = st.mean(b) - st.mean(a)
        return d
    return f
stats = {}
d0 = raw_deltas(list(T.values()), list(U.values()))
ta = [apcl(T[t][g]) for g in ids for t in T if apcl(T[t][g]) is not None]; ua = [apcl(U[u][g]) for g in ids for u in U if apcl(U[u][g]) is not None]
ci = boot_ci(raw_deltas)
stats["actions per completed level (all levels)"] = {"timed_mean": round(st.mean(ta), 1), "untimed_mean": round(st.mean(ua), 1), "delta_untimed_minus_timed": round(st.mean(d0.values()), 1),
    "run_level_ci95": ci, "games_paired": len(d0), "untimed_higher_in": sum(1 for v in d0.values() if v > 0), "verdict": "RESOLVED" if ci[0] > 0 or ci[1] < 0 else "NOT RESOLVED", "unit": "actions",
    "note": "censored on the timed side: the clock lets only fast clears complete"}
for k in (1, 2, 3, 5):
    f = reach_deltas(k); d = f(list(T.values()), list(U.values()))
    ta = [reach(T[t][g], k) for g in d for t in T if reach(T[t][g], k) is not None]; ua = [reach(U[u][g], k) for g in d for u in U if reach(U[u][g], k) is not None]
    ci = boot_ci(f)
    stats[f"actions to reach level {k} (games both reached)"] = {"timed_mean": round(st.mean(ta), 1), "untimed_mean": round(st.mean(ua), 1), "delta_untimed_minus_timed": round(st.mean(d.values()), 1),
        "run_level_ci95": ci, "games_paired": len(d), "untimed_higher_in": sum(1 for v in d.values() if v > 0), "verdict": "RESOLVED" if ci[0] > 0 or ci[1] < 0 else "NOT RESOLVED", "unit": "actions"}

out = {"timed": list(T), "untimed": list(U), "games": ids, "bootstrap": {"reps": BOOT, "seed": SEED, "design": "runs within each arm, then games; percentile 95%"},
       "same_action_window": same_window, "matched_cells_all4_timed_cleared": matched, "aggregate_levels_per_100_actions": aggregate,
       "actions_on_uncompleted_levels": uncompleted, "stats": stats,
       "note": "Raw 'actions per completed level' is censored on the timed side: the clock lets only fast clears complete, so timed per-level costs are truncated from above. The same-action-window statistic scores both regimes over the identical actions; the matched-cells statistic restricts to (game, level) cells every timed run cleared; the aggregate levels-per-100-actions mixes efficiency with depth (most untimed actions go to levels never completed, in the capped games)."}
path = os.environ.get("OUT") or (sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else "notes/move_efficiency_timed_vs_untimed_2026-11-09.json")
json.dump(out, open(path, "w"), indent=1)
w = same_window["levels_within_window"]; p = same_window["levels_per_100_actions_within_window"]
print(f"wrote {path} | same window: levels {w['timed']} vs {w['untimed']} delta {w['delta']} CI {w['ci95_runlevel']} | per 100: {p['timed']} vs {p['untimed']} CI {p['ci95_runlevel']} | matched cells {matched['cells']}: medians {matched['timed_median']} vs {matched['untimed_median']}, delta median {matched['delta_median']} CI {matched['delta_median_ci95_runlevel']}")
