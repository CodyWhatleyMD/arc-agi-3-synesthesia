#!/usr/bin/env python3
"""Levels cleared per tenth of the per-game clock, across the games the clock ended, from benchmark.json files.
A game's clock starts at its first action's wallclock; a level's clear time is the wallclock of the action that cleared
it (cumulative actions_per_level). Usage: levels_per_tenth_of_clock.py --clock-s 3918 --json OUT A.json B.json ..."""
import argparse, json
ap = argparse.ArgumentParser(); ap.add_argument("--clock-s", type=float, default=3918.0); ap.add_argument("--json")
ap.add_argument("files", nargs="+"); a = ap.parse_args()
ended = [0] * 10; won = [0] * 10; n_ended = n_won = 0
for p in a.files:
    for g in json.load(open(p))["game_runs"]:
        apl = g.get("actions_per_level") or []; hist = g.get("history") or []
        if not hist: continue
        w = [h.get("wallclock_seconds", 0.0) for h in hist]; t0 = w[0]; idx = 0; clears = []
        for x in apl[:int(g.get("levels_completed", 0))]:
            idx += int(x)
            if 0 < idx <= len(w): clears.append(w[idx - 1] - t0)
        tgt = won if g.get("state") == "won" else ended
        if g.get("state") == "won": n_won += 1
        else: n_ended += 1
        for t in clears:
            if t <= a.clock_s * 1.0001: tgt[min(9, int(10 * t / a.clock_s))] += 1
out = {"runs": len(a.files), "clock_s": a.clock_s, "clock_ended_games": n_ended, "won_games": n_won,
       "levels_per_tenth_clock_ended": ended, "levels_per_tenth_won": won}
print(json.dumps(out)); print(f"clock-ended games {n_ended}: levels per tenth {ended}, total {sum(ended)}, last fifth {ended[8]+ended[9]} "
      f"({100*(ended[8]+ended[9])/max(1,sum(ended)):.0f}%), last tenth/first tenth {ended[9]/max(1,ended[0]):.2f}")
if a.json: json.dump(out, open(a.json, "w"), indent=1)
