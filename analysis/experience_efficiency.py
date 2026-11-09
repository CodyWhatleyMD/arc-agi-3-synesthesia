#!/usr/bin/env python3
"""Experience efficiency off the clock (pre-statement notes/prestate_experience_efficiency_2026-11-04.md).

Reads the harness's benchmark.json files (one per run) and reports, per run and per group:
  E1  levels per 100 actions
  E3  levels per game, full-clear rate
  E4  games ended by the clock (timed runs: a game that was not won and whose summed wallclock >= --clock-s * 0.95)
      or by the action cap (untimed runs: not won and actions >= --cap)
  E2  Kaplan-Meier survival of actions to FIRST level clear, per group: a game is an event at actions_per_level[0]
      if levels_completed >= 1, else censored at its total actions (cap, clock, model stop, or a killed run).
Partial runs (killed/preempted) are admitted: unplayed games are dropped, in-progress games are censored.
Usage: experience_efficiency.py --timed A.json B.json --untimed C.json ... [--clock-s 3918] [--cap 5184] [--json out]
"""
import argparse, json, os, statistics as st, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import results_index as ri


def run_label(path):
    """The run's tag (e.g. r2_9300, v36_anchor, r0x1), the same in this tree and on the original machine."""
    ident = ri.identity(path)
    if ident != str(path):
        return ident.split("/")[1]
    return str(path).split("/")[-3].replace("working_", "")


def load(path):
    b = json.load(open(path))
    games = []
    for g in b["game_runs"]:
        apl = g.get("actions_per_level") or []
        acts = int(sum(apl))
        if acts == 0 and not g.get("history"):
            continue                                   # never started (killed run)
        # the game's end on the clock is final_wallclock_seconds (history is per action; its last entry is the last
        # ACTION, and a game can sit without acting until the clock takes it). Summing history was the 11-07 bug.
        hist = g.get("history") or []
        wall = float(g.get("final_wallclock_seconds") or (hist[-1].get("wallclock_seconds", 0.0) if hist else 0.0))
        games.append({"id": g["game_id"], "levels": int(g.get("levels_completed", 0)), "total": int(g["number_of_levels"]),
                      "actions": acts, "apl": [int(x) for x in apl], "state": g.get("state"), "wall": wall,
                      "score": float(g.get("final_score") or 0.0)})
    return {"path": path, "label": b.get("label"), "end": b.get("end_time"), "games": games}


def run_measures(r, clock_s, cap, timed):
    G = r["games"]; n = len(G)
    lv = sum(g["levels"] for g in G); acts = sum(g["actions"] for g in G)
    won = sum(1 for g in G if g["state"] == "won" or g["levels"] >= g["total"])
    if timed:
        ended = sum(1 for g in G if g["state"] != "won" and g["wall"] >= 0.95 * clock_s)
    else:
        ended = sum(1 for g in G if g["state"] != "won" and g["actions"] >= cap)
    return {"games": n, "levels": lv, "lv_per_game": lv / n if n else 0.0, "clears": won, "actions": acts,
            "lv_per_100": 100 * lv / acts if acts else 0.0, "ended_by_limit": ended,
            "score": st.mean(g["score"] for g in G) if G else 0.0}


def km(pairs):
    """pairs: (t, event) -> list of (t, S(t)) after each event time, plus median."""
    pairs = sorted(pairs); S = 1.0; out = []; at_risk = len(pairs); i = 0; median = None
    while i < len(pairs):
        t = pairs[i][0]; d = 0; c = 0
        while i < len(pairs) and pairs[i][0] == t:
            if pairs[i][1]: d += 1
            else: c += 1
            i += 1
        if d:
            S *= (1 - d / at_risk); out.append((t, S))
            if median is None and S <= 0.5: median = t
        at_risk -= d + c
    return out, median


def clear_pairs(runs, k):
    """k-th clear: event at the cumulative actions through level k if levels >= k; k='full' = all of the game's
    levels. Otherwise censored at the game's total actions."""
    pairs = []
    for r in runs:
        for g in r["games"]:
            kk = g["total"] if k == "full" else int(k)
            if g["levels"] >= kk and len(g["apl"]) >= kk:
                pairs.append((sum(g["apl"][:kk]), 1))
            else:
                pairs.append((g["actions"], 0))
    return pairs


def first_clear_pairs(runs):
    return clear_pairs(runs, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--timed", nargs="+", required=True); ap.add_argument("--untimed", nargs="+", required=True)
    ap.add_argument("--clock-s", type=float, default=3918.0); ap.add_argument("--cap", type=int, default=5184)
    ap.add_argument("--json")
    ap.add_argument("--match", action="store_true",
                    help="restrict the timed runs to the games the untimed runs played (partial untimed runs cover a prefix)")
    a = ap.parse_args()
    T = [load(p) for p in a.timed]; U = [load(p) for p in a.untimed]
    if a.match:
        ids = {g["id"] for r in U for g in r["games"]}
        T = [dict(r, games=[g for g in r["games"] if g["id"] in ids]) for r in T]
        print(f"matched: {len(ids)} games the untimed runs played; timed games kept {sum(len(r['games']) for r in T)}")
    for grp, runs in (("timed", T), ("untimed", U)):
        n = sum(len(r["games"]) for r in runs); over = sum(1 for r in runs for g in r["games"] if g["actions"] > 1000)
        print(f"{grp:8s}: {over} of {n} games have more than 1,000 actions (the curves beyond that are carried forward from these)")
    out = {"timed": [], "untimed": [], "matched": bool(a.match)}
    print(f"{'run':16s} {'games':>5s} {'lv/game':>7s} {'clears':>6s} {'actions':>7s} {'lv/100act':>9s} {'limit-ended':>11s} {'score':>6s}")
    for grp, runs, timed in (("timed", T, True), ("untimed", U, False)):
        for r in runs:
            m = run_measures(r, a.clock_s, a.cap, timed); m["run"] = run_label(r["path"])
            out[grp].append(m)
            print(f"{m['run']:16s} {m['games']:5d} {m['lv_per_game']:7.2f} {m['clears']:6d} {m['actions']:7d} {m['lv_per_100']:9.2f} {m['ended_by_limit']:11d} {m['score']:6.2f}")
        if runs:
            print(f"  {grp} mean of runs: lv/game {st.mean(m['lv_per_game'] for m in out[grp]):.2f} | lv/100act {st.mean(m['lv_per_100'] for m in out[grp]):.2f} | limit-ended {st.mean(m['ended_by_limit'] for m in out[grp]):.1f}")
    for k in (1, 3, 5, "full"):
        print(f"\nE2: actions to clear level {k} (Kaplan-Meier; censored = not reached within the game's actions)")
        for grp, runs in (("timed", T), ("untimed", U)):
            pairs = clear_pairs(runs, k); curve, med = km(pairs)
            ev = sum(e for _, e in pairs)
            def S_at(x):
                s = 1.0
                for t, v in curve:
                    if t <= x: s = v
                return s
            print(f"  {grp:8s} games {len(pairs):3d} events {ev:3d} censored {len(pairs)-ev:3d} | median actions {med} | "
                  f"reached within 100: {1-S_at(100):.2f}, 300: {1-S_at(300):.2f}, 1000: {1-S_at(1000):.2f}, 3000: {1-S_at(3000):.2f}")
            out[f"{grp}_km_{k}"] = {"n": len(pairs), "events": ev, "median": med, "curve": curve}
    if a.json:
        json.dump(out, open(a.json, "w"), indent=1); print("wrote", a.json)


if __name__ == "__main__":
    main()
