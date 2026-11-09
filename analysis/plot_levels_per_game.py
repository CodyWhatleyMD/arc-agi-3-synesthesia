"""Levels per game, timed controls vs untimed runs (paper figure 4.3).

For each of the 25 public games: the four timed v36 controls (r2, r3, r4, r6; 65-minute per-game clock) as a band from
their min to max with a tick at the mean, and each of the four complete concurrency-14 untimed runs (r0c14, r0c14b, r0x1,
r0x2) as a point. Games are ordered by how many of the four controls ended at the clock.
Untimed games are included only when finished (won, or at the 5,184-action cap). Reads benchmark.json files directly.
Usage: python3 -P scripts/plot_levels_per_game.py [--out notes/figures/levels_per_game_YYYY-MM-DD]
"""
import json, glob, os, sys, statistics as st, collections
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import results_index as ri
TIMED = {n: ri.benchmark(f"{n}_9300", "local") for n in ("r2", "r3", "r4", "r6")}
# The clock test only: the four complete untimed runs at the controls' own concurrency (14), two on our card and two on
# rented copies of it. The one-game-at-a-time runs (R0, r0rep3, r0rep4) change the memory each game gets and are not
# plotted here (they were until 11-09; see the paper's §4 and the handoff 01:50).
UNTIMED = {"r0c14": ri.benchmark("r0c14", "local"), "r0c14b": ri.benchmark("r0c14b", "local"),
           "r0x1": ri.benchmark("r0x1", "vast"), "r0x2": ri.benchmark("r0x2", "vast")}
CAP = 5184
TIMED_C, UNTIMED_C, INK, MUTED = "#2a78d6", "#eb6834", "#1d1d1f", "#8a8a8e"

def games(path, finished_only=False):
    out = {}
    for g in json.load(open(path))["game_runs"]:
        apl = [int(x) for x in g.get("actions_per_level") or []]; acts = sum(apl)
        if acts == 0: continue
        if finished_only and not (g.get("state") == "won" or acts >= CAP): continue
        out[g["game_id"][:4]] = (int(g.get("levels_completed", 0)), int(g["number_of_levels"]), g.get("state"), float(g.get("final_wallclock_seconds") or 0))
    return out

T = {n: games(p) for n, p in TIMED.items()}
U = {n: games(p, finished_only=True) for n, p in UNTIMED.items() if os.path.exists(p)}
ids = sorted({g for r in T.values() for g in r})
clocked = {g: sum(1 for r in T.values() if g in r and r[g][2] != "won" and r[g][3] >= 0.95 * 3918) for g in ids}
total = {g: next(r[g][1] for r in T.values() if g in r) for g in ids}
ids.sort(key=lambda g: (-clocked[g], -st.mean(r[g][0] for r in T.values() if g in r)))

fig, ax = plt.subplots(figsize=(13.5, 7.4), dpi=150)
LINE = "#c9c9cd"
for i, g in enumerate(ids):
    tv = [r[g][0] for r in T.values() if g in r]
    uv = [r[g][0] for r in U.values() if g in r]
    tm, um = st.mean(tv), (st.mean(uv) if uv else None)
    # each regime's spread as a thin whisker, slightly apart so both stay readable
    ax.plot([i - 0.09, i - 0.09], [min(tv), max(tv)], color=TIMED_C, lw=2.2, alpha=0.35, solid_capstyle="round", zorder=1)
    if uv: ax.plot([i + 0.09, i + 0.09], [min(uv), max(uv)], color=UNTIMED_C, lw=2.2, alpha=0.35, solid_capstyle="round", zorder=1)
    # the connector between the two means is the figure: what the clock cost, game by game
    if um is not None: ax.plot([i, i], sorted([tm, um]), color=LINE, lw=3, zorder=2, solid_capstyle="round")
    ax.scatter([i], [tm], s=150, color=TIMED_C, zorder=3)
    if um is not None: ax.scatter([i], [um], s=84, color=UNTIMED_C, zorder=4)
    ax.plot([i - 0.3, i + 0.3], [total[g]] * 2, color=MUTED, lw=1.1, ls=":", zorder=0)
# group brackets: how many of the four controls the clock ended
groups = []
for i, g in enumerate(ids):
    if not groups or groups[-1][0] != clocked[g]: groups.append([clocked[g], i, i])
    else: groups[-1][2] = i
ymax = max(total.values()) + 0.9
for k, a_, b_ in groups:
    label = {4: "the clock ended the game in all 4 timed runs", 3: "in 3 of 4", 2: "2 of 4", 1: "1 of 4", 0: "never"}[k]
    ax.plot([a_ - 0.35, b_ + 0.35], [ymax, ymax], color=MUTED, lw=1.1)
    ax.text((a_ + b_) / 2, ymax + 0.12, label, ha="center", va="bottom", fontsize=9.5, color=INK)
tmean = st.mean(st.mean(r[g][0] for r in T.values() if g in r) for g in ids)
umean = st.mean(st.mean(r[g][0] for r in U.values() if g in r) for g in ids if any(g in r for r in U.values()))
ax.text(len(ids) - 0.6, 0.9, f"average: {tmean:.1f} levels with the clock,\n{umean:.1f} without  (+{umean - tmean:.2f} a game)",
        ha="right", va="bottom", fontsize=11, color=INK, bbox=dict(boxstyle="round,pad=0.5", fc="white", ec=LINE))
ax.set_xticks(range(len(ids))); ax.set_xticklabels(ids, fontsize=9, color=INK)
ax.set_ylabel("levels completed", fontsize=10.5); ax.set_ylim(-0.3, ymax + 0.9); ax.set_xlim(-0.7, len(ids) - 0.3)
ax.spines[["top", "right"]].set_visible(False); ax.grid(axis="y", color="#e5e5e5", lw=0.6); ax.set_axisbelow(True)
ax.text(0.0, 1.085, "Levels per game, with and without the clock", transform=ax.transAxes, fontsize=14, fontweight="semibold", color=INK, va="bottom")
ax.text(0.0, 1.03, f"Blue: mean of the four timed controls (65-minute clock). Orange: mean of the four untimed runs ({', '.join(U)}), finished games only. "
                   "Thin whiskers: each regime's min to max. Dotted: the game's level count.", transform=ax.transAxes, fontsize=8.6, color=MUTED, va="bottom", wrap=True)
ax.scatter([], [], color=TIMED_C, s=150, label="with the clock (mean of 4 timed runs)"); ax.scatter([], [], color=UNTIMED_C, s=84, label="clock off (mean of 4 untimed runs)")
ax.legend(loc="upper right", bbox_to_anchor=(1.0, 0.9), frameon=False, fontsize=9)
out = os.environ.get("OUT", sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else "notes/figures/levels_per_game")
fig.tight_layout(); fig.savefig(out + ".png", bbox_inches="tight"); fig.savefig(out + ".svg", bbox_inches="tight")
# the numbers behind it
rows = []
for g in ids:
    tv = [r[g][0] for r in T.values() if g in r]; uv = [r[g][0] for r in U.values() if g in r]
    rows.append({"game": g, "levels": total[g], "clocked_of_4": clocked[g], "timed_mean": round(st.mean(tv), 2), "timed_min": min(tv), "timed_max": max(tv),
                 "untimed": uv, "untimed_mean": round(st.mean(uv), 2) if uv else None, "gain": round(st.mean(uv) - st.mean(tv), 2) if uv else None})
json.dump({"untimed_runs": list(U), "timed_runs": list(T), "rows": rows}, open(out + ".json", "w"), indent=1)
print(f"wrote {out}.png/.svg/.json; untimed runs {list(U)}; games with untimed data {sum(1 for r in rows if r['untimed'])}/25; "
      f"sum of gains {sum(r['gain'] for r in rows if r['gain'] is not None):+.2f}")
