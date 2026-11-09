#!/usr/bin/env python3
"""Figure: fraction of games that reached level k within N actions, timed vs untimed (Kaplan-Meier, 1 - S).

Input: the JSON written by scripts/experience_efficiency.py (keys <group>_km_<k>); the paper's figure 4.1 uses the
MATCHED one (`experience_efficiency.py --match`: the timed runs restricted to the games the untimed runs played).
Output: OUT.svg, OUT.png and OUT.json (the series drawn, the counts and the subtitle), so the figure can be diffed.
Every count in the subtitle and the labels is read from the input; nothing about the cohort is hard-coded.
Palette: dataviz reference categorical slots 1-2 (validated, light surface #fcfcfb).

usage: plot_survival.py EFFICIENCY_JSON OUT_STEM
"""
import collections, json, os, sys, textwrap
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import results_index as ri

src, out = sys.argv[1], sys.argv[2]
D = json.load(open(src))
PLACE = {"kaggle": "on Kaggle", "local": "on our card", "vast": "on rented cards", "server": "on the GCP server",
         "archive": "in the archive", None: "on an unrecorded platform"}


def cohort_text(D):
    """The subtitle, from the counts in the input."""
    t_runs = [r["run"] for r in D["timed"]]; u_runs = [r["run"] for r in D["untimed"]]
    where = collections.Counter(ri.platform_of(r) for r in t_runs)
    split = ", ".join(f"{n} {PLACE.get(p, p)}" for p, n in sorted(where.items(), key=lambda kv: (-kv[1], str(kv[0]))))
    n_t, n_u = D["timed_km_1"]["n"], D["untimed_km_1"]["n"]
    per_run = sorted({r["games"] for r in D["timed"]})
    per = str(per_run[0]) if len(per_run) == 1 else f"{per_run[0]} to {per_run[-1]}"
    if D.get("matched"):
        scope = f"matched to the games the untimed runs played ({per} per run): {n_t} games"
    else:
        scope = f"every game each run played ({per} per run): {n_t} games"
    return [f"Timed = {len(t_runs)} runs with the per-game clock ({split}), {scope}.",
            f"Untimed = {len(u_runs)} no-clock runs, {n_u} games. Dashed = no games of that group left at risk."]


SUB_PARTS = cohort_text(D)
SUB = " ".join(SUB_PARTS)
SURF, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e6e5e1"
COL = {"timed": "#2a78d6", "untimed": "#eb6834"}
LAB = {"timed": "timed (per-game clock)", "untimed": "untimed (action cap only)"}
panels = [("1", "level 1"), ("3", "level 3"), ("5", "level 5"), ("full", "every level")]
data = {"matched": bool(D.get("matched")), "subtitle": SUB,
        "timed_runs": [r["run"] for r in D["timed"]], "untimed_runs": [r["run"] for r in D["untimed"]], "panels": {}}
fig, axes = plt.subplots(2, 2, figsize=(9.6, 6.6), facecolor=SURF, sharex=True, sharey=True)
for ax, (k, title) in zip(axes.flat, panels):
    ax.set_facecolor(SURF)
    ends = {}; data["panels"][k] = {}
    for grp in ("timed", "untimed"):
        km = D[f"{grp}_km_{k}"]; xs = [1.0]; ys = [0.0]
        for t, s in km["curve"]:
            xs += [t, t]; ys += [ys[-1], 1 - s]
        # solid where the group still has games at risk; dashed beyond its last event (Kaplan-Meier carry-forward)
        ax.plot(xs, ys, color=COL[grp], lw=2, solid_capstyle="round")
        ax.plot([xs[-1], 6000], [ys[-1], ys[-1]], color=COL[grp], lw=1.4, ls=(0, (2, 3)))
        ends[grp] = (ys[-1], km["n"])
        data["panels"][k][grp] = {"n": km["n"], "events": km["events"], "median": km["median"], "end_fraction": ys[-1],
                                  "reached": [[t, 1 - s] for t, s in km["curve"]]}
    # direct labels at the right end; stacked when the two ends sit within 0.05 of each other
    yt, yu = ends["timed"][0], ends["untimed"][0]
    pos = {"timed": yt, "untimed": yu}
    if abs(yt - yu) < 0.05:
        hi, lo = ("untimed", "timed") if yu >= yt else ("timed", "untimed")
        mid = (yt + yu) / 2; pos[hi] = min(1.0, mid + 0.035); pos[lo] = mid - 0.035
    for grp in ("timed", "untimed"):
        ax.text(6300, pos[grp], f"{grp} {ends[grp][0]:.2f}  (n={ends[grp][1]})", color=INK2, fontsize=8.5, va="center")
    ax.set_xscale("log"); ax.set_xlim(8, 6000); ax.set_ylim(0, 1.02)
    ax.set_title(f"reached {title}", loc="left", fontsize=10.5, color=INK, pad=6)
    ax.grid(True, which="major", color=GRID, lw=0.6); ax.grid(False, which="minor")
    for s in ("top", "right"): ax.spines[s].set_visible(False)
    for s in ("left", "bottom"): ax.spines[s].set_color(GRID)
    ax.tick_params(colors=INK2, labelsize=8.5, length=0)
    ax.set_xticks([10, 100, 1000, 5000]); ax.set_xticklabels(["10", "100", "1,000", "5,000"])
for ax in axes[1]: ax.set_xlabel("actions in the game (log scale)", color=INK2, fontsize=9)
for ax in axes[:, 0]: ax.set_ylabel("fraction of games", color=INK2, fontsize=9)
fig.suptitle("Same model, same harness: the clock removes the tail of the game", x=0.02, ha="left", fontsize=12, color=INK)
sub_lines = ["Fraction of games that had reached each level after N actions."] + [l for part in SUB_PARTS for l in textwrap.wrap(part, 150)]
for i, line in enumerate(sub_lines):
    fig.text(0.02, 0.935 - 0.023 * i, line, fontsize=8.5, color=INK2)
handles = [Line2D([], [], color=COL[g], lw=2, label=LAB[g]) for g in ("timed", "untimed")]
fig.legend(handles=handles, loc="lower right", bbox_to_anchor=(0.98, 0.0), ncol=2, frameon=False, fontsize=9, labelcolor=INK2)
fig.tight_layout(rect=(0, 0.04, 0.93, 0.95 - 0.023 * len(sub_lines)))
fig.savefig(out + ".svg", facecolor=SURF); fig.savefig(out + ".png", dpi=160, facecolor=SURF)
json.dump(data, open(out + ".json", "w"), indent=1)
print("wrote", out + ".svg", out + ".png", out + ".json")
print("subtitle:", SUB)
