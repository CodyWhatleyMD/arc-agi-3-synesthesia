#!/usr/bin/env python3
"""Figure 4.0: mean score on the 25 public games against minutes of play, one line per timed run.

Data: the summary block the harness prints every periodic_save_interval_s (600 s) while it plays and once at the end
("started:", "ended:", "runs: N (won: W)", "mean score:", "total wallclock:"). Source per run, the first that exists:
the launcher log (local runs: run_synesthesia_<tag>.log), the Kaggle kernel log (<kernel>.log, a JSON stream of the
notebook's output), stdout.log; all resolved through results_index, so the same command works on the machine that ran
the experiments and in the results repository. When stdout.log also exists its series is parsed and must agree.

Time of a summary: k x periodic_save_interval_s for the k-th periodic one ("ended: in progress"; the harness sleeps
the interval, then saves and prints, so the true time is later by the save time, under a minute over a run), and
ended - started for the final one. "total wallclock" is NOT elapsed time: it is the sum of the games' wallclocks
(about 14 x elapsed with fourteen games in flight); it is recorded in the JSON but is not the x axis.
The per-game clock is marked twice: a line at clock_s (the first fourteen games start at 0 and reach it there), and,
in the lower panel, the running count of games the clock ended (not won, final_wallclock_seconds >= 0.95 x clock_s,
the rule experience_efficiency.py uses), each at its started_at - benchmark start + final_wallclock_seconds, read from
the run's benchmark.json.
Slopes, points per minute: least squares over the summaries at t <= 100 min (the first ten), and over the summaries in
the run's last 20 minutes (t >= t_end - 20).

usage: plot_score_vs_playtime.py [--run LABEL=PLATFORM/TAG ...] [--clock-s 3918] [--out notes/figures/score_vs_playtime]
"""
import argparse, datetime as dt, json, os, re, statistics as st, sys, textwrap
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import results_index as ri

DEFAULT_RUNS = ["v36=kaggle/v36_anchor", "r2=local/r2_9300", "r3=local/r3_9300", "r4=local/r4_9300", "r6=local/r6_9300"]
FIELD = re.compile(r"^(started|ended|runs|mean score|total wallclock):\s+(.*?)\s*$")


def text_lines(path):
    """The log's text lines; a Kaggle kernel log (a JSON list of {stream_name, time, data}) is unpacked to its data."""
    raw = open(path, encoding="utf-8", errors="replace").read()
    if raw.lstrip().startswith("[{"):
        try:
            return "".join(e.get("data", "") for e in json.loads(raw)).splitlines()
        except json.JSONDecodeError:
            out = []
            for line in raw.splitlines():
                line = line.strip().lstrip("[,").rstrip("]")
                try:
                    out += json.loads(line).get("data", "").splitlines()
                except json.JSONDecodeError:
                    pass
            return out
    return raw.splitlines()


def summaries(path):
    """Every summary block in the log, in order: {started, ended, won, mean_score, total_wallclock_s}."""
    out, cur = [], {}
    for line in text_lines(path):
        m = FIELD.match(line)
        if not m:
            continue
        k, v = m.groups()
        if k == "started":
            cur = {"started": v}
        elif k == "ended":
            cur["ended"] = v
        elif k == "runs":
            w = re.search(r"won:\s*(\d+)", v); cur["won"] = int(w.group(1)) if w else None
        elif k == "mean score":
            cur["mean_score"] = float(v)
        elif k == "total wallclock" and "started" in cur:
            cur["total_wallclock_s"] = float(v.rstrip("s")); out.append(cur); cur = {}
    return out


def series(blocks, interval_s):
    t0 = dt.datetime.fromisoformat(blocks[0]["started"])
    rows, k = [], 0
    for b in blocks:
        final = b.get("ended", "in progress") != "in progress"
        if final:
            t = (dt.datetime.fromisoformat(b["ended"]) - t0).total_seconds() / 60
        else:
            k += 1; t = k * interval_s / 60
        rows.append({"t_min": round(t, 4), "mean_score": b["mean_score"], "won": b.get("won"),
                     "total_wallclock_s": b["total_wallclock_s"], "final": final})
    return rows


def lsq(pts):
    if len(pts) < 2:
        return None
    mx = st.mean(x for x, _ in pts); my = st.mean(y for _, y in pts)
    sxx = sum((x - mx) ** 2 for x, _ in pts)
    return sum((x - mx) * (y - my) for x, y in pts) / sxx if sxx else None


def log_for(tag, plat):
    """(chosen log, stdout.log or None): launcher log, else the kernel log, else stdout.log."""
    pref = ri.run_glob(tag, plat, f"run_synesthesia_{tag}.log")
    if not pref and plat == "kaggle":
        pref = [p for p in ri.run_glob(tag, plat, "*.log")
                if os.path.basename(p) not in ("stdout.log", "run.log", "download.log") and not os.path.basename(p).startswith("vllm-")]
    so = ri.run_glob(tag, plat, "stdout.log")
    if pref:
        return pref[0], (so[0] if so else None)
    if so:
        return so[0], None
    raise FileNotFoundError(f"no log with summaries for {plat}/{tag}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--run", action="append", help="LABEL=PLATFORM/TAG; repeat. Default: v36 and the four local controls")
    ap.add_argument("--clock-s", type=float, default=3918.0)
    ap.add_argument("--out", default=os.environ.get("OUT", "notes/figures/score_vs_playtime"))
    a = ap.parse_args()
    specs = a.run or DEFAULT_RUNS
    runs = []
    for spec in specs:
        label, pt = spec.split("=", 1); plat, tag = pt.split("/", 1)
        bpath = ri.benchmark(tag, plat); bench = json.load(open(bpath))
        interval = float(bench.get("periodic_save_interval_s") or 600.0)
        logp, so = log_for(tag, plat)
        rows = series(summaries(logp), interval)
        agrees = None
        if so and so != logp:
            agrees = series(summaries(so), interval) == rows
            if not agrees:
                sys.exit(f"{label}: the summaries in {ri.identity(logp)} and {ri.identity(so)} disagree")
        t0 = dt.datetime.fromisoformat(bench["start_time"])
        expiry = sorted(round(((dt.datetime.fromisoformat(g["started_at"]) - t0).total_seconds()
                               + float(g.get("final_wallclock_seconds") or 0)) / 60, 4)
                        for g in bench["game_runs"]
                        if g.get("state") != "won" and float(g.get("final_wallclock_seconds") or 0) >= 0.95 * a.clock_s)
        t_end = rows[-1]["t_min"]
        s100 = lsq([(r["t_min"], r["mean_score"]) for r in rows if r["t_min"] <= 100 + 1e-9])
        s20 = lsq([(r["t_min"], r["mean_score"]) for r in rows if r["t_min"] >= t_end - 20 - 1e-9])
        runs.append({"label": label, "platform": plat, "tag": tag, "log": ri.identity(logp),
                     "stdout_log_agrees": agrees, "interval_s": interval, "summaries": rows,
                     "final_mean_score": rows[-1]["mean_score"], "slope_first_100_min": s100, "slope_last_20_min": s20,
                     "games_ended_by_clock": len(expiry), "clock_expiry_min": expiry})
        print(f"{label:4s} {plat}/{tag}: {len(rows)} summaries from {ri.identity(logp)}"
              + ("" if agrees is None else " (stdout.log agrees)")
              + f"; end {t_end:.1f} min, score {rows[-1]['mean_score']:.2f}; slope first 100 min {s100:.3f}, last 20 min {s20:.3f};"
              f" {len(expiry)} games ended by the clock")
    m100 = st.mean(r["slope_first_100_min"] for r in runs); m20 = st.mean(r["slope_last_20_min"] for r in runs)
    lo, hi = min(r["games_ended_by_clock"] for r in runs), max(r["games_ended_by_clock"] for r in runs)
    n_games = len(json.load(open(ri.benchmark(runs[0]["tag"], runs[0]["platform"])))["game_runs"])
    plats = {p: sum(1 for r in runs if r["platform"] == p) for p in sorted({r["platform"] for r in runs})}
    where = ", ".join(f"{n} {'on Kaggle' if p == 'kaggle' else 'on our card' if p == 'local' else 'on ' + p}" for p, n in plats.items())
    clock_min = a.clock_s / 60
    sub = [f"Mean score against minutes of play, {len(runs)} timed runs of one configuration ({where}; solid = Kaggle, dashed = our card); "
           f"one harness summary every {runs[0]['interval_s'] / 60:g} minutes and one at the end.",
           f"Least-squares slope over the first 100 minutes {m100:.2f} points/min (runs {min(r['slope_first_100_min'] for r in runs):.2f} to "
           f"{max(r['slope_first_100_min'] for r in runs):.2f}); over each run's last 20 minutes {m20:.2f}. "
           f"By the end {lo} to {hi} of the {n_games} games had been ended by the {a.clock_s:,.0f} s ({clock_min:.1f}-minute) per-game clock."]
    print(f"mean slope first 100 min {m100:.4f}; last 20 min {m20:.4f}; games ended by the clock {lo}-{hi} of {n_games}")

    SURF, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e6e5e1"
    PAL = ["#2a78d6", "#eb6834", "#1f9e77", "#8b5cf6", "#d9437f", "#6b7280", "#b45309"]
    fig, (ax, rug) = plt.subplots(2, 1, figsize=(10.2, 7.4), facecolor=SURF, sharex=True,
                                  gridspec_kw={"height_ratios": [1, 0.42], "hspace": 0.08})
    xmax = max(r["summaries"][-1]["t_min"] for r in runs)
    for i, r in enumerate(runs):
        c = PAL[i % len(PAL)]; ls = "-" if r["platform"] == "kaggle" else "--"
        xs = [s["t_min"] for s in r["summaries"]]; ys = [s["mean_score"] for s in r["summaries"]]
        ax.plot(xs, ys, color=c, lw=2.2 if ls == "-" else 1.8, ls=ls, marker="o", ms=3.2, zorder=3)
        ex = r["clock_expiry_min"]
        rug.step([0] + ex + [xs[-1]], [0] + list(range(1, len(ex) + 1)) + [len(ex)], where="post", color=c, lw=1.6 if ls == "-" else 1.3, ls=ls)
    # direct labels at the line ends, nudged apart so none overlap (minimum gap 1.6 score points)
    ends = sorted(((r["summaries"][-1]["mean_score"], r["summaries"][-1]["t_min"], r["label"]) for r in runs))
    placed = []
    for y, x, lab in ends:
        yy = max(y, placed[-1] + 1.6) if placed else y
        placed.append(yy); ax.text(x + 1.5, yy, lab, color=INK2, fontsize=9, va="center")
    for a_ in (ax, rug):
        a_.axvline(clock_min, color=INK2, lw=0.9, ls=":", zorder=1)
        a_.set_facecolor(SURF)
        for s in ("top", "right"): a_.spines[s].set_visible(False)
        for s in ("left", "bottom"): a_.spines[s].set_color(GRID)
        a_.tick_params(colors=INK2, labelsize=9, length=0)
    ax.text(clock_min + 0.8, 1.0, f"per-game clock, {a.clock_s:,.0f} s", color=INK2, fontsize=8.5, va="bottom")
    ax.grid(True, axis="y", color=GRID, lw=0.6); ax.set_ylim(0, None)
    ax.set_ylabel(f"mean score, {n_games} public games", color=INK2, fontsize=10)
    rug.set_ylim(0, n_games); rug.set_yticks([0, 5, 10, 15, 20, 25]); rug.grid(True, axis="y", color=GRID, lw=0.6)
    rug.set_ylabel("games ended\nby the clock", color=INK2, fontsize=9)
    rug.set_xlim(0, xmax + 12); rug.set_xlabel("minutes of play (since the benchmark started)", color=INK2, fontsize=10)
    fig.suptitle("The score climbs until the games' clocks expire", x=0.02, ha="left", fontsize=13, color=INK)
    sub_lines = [l for part in sub for l in textwrap.wrap(part, 150)]
    for i, line in enumerate(sub_lines):
        fig.text(0.02, 0.93 - 0.026 * i, line, fontsize=8.5, color=INK2)
    handles = [Line2D([], [], color=INK2, lw=2, ls="-", label="Kaggle"), Line2D([], [], color=INK2, lw=1.8, ls="--", label="our card"),
               Line2D([], [], color=INK2, lw=0.9, ls=":", label="one per-game clock from the start")]
    fig.legend(handles=handles, loc="lower right", bbox_to_anchor=(0.98, 0.0), ncol=3, frameon=False, fontsize=8.5, labelcolor=INK2)
    fig.subplots_adjust(left=0.09, right=0.95, top=0.905 - 0.026 * len(sub_lines), bottom=0.12)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    fig.savefig(a.out + ".svg", facecolor=SURF); fig.savefig(a.out + ".png", dpi=150, facecolor=SURF)
    json.dump({"clock_s": a.clock_s, "games": n_games, "subtitle": sub, "slope_first_100_min_mean": m100,
               "slope_last_20_min_mean": m20, "games_ended_by_clock_range": [lo, hi], "runs": runs},
              open(a.out + ".json", "w"), indent=1)
    print("wrote", a.out + ".png", a.out + ".svg", a.out + ".json")


if __name__ == "__main__":
    main()
