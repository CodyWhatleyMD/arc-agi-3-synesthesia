"""End state of the clock-ended games in the four timed controls (paper section 4, the 'where the clock fell' numbers).

For each game the four controls (r2, r3, r4, r6; 65-minute per-game clock of 3,918 s) ended at the clock (not won, and
its wallclock from its own start within 5% of the clock), reads: actions spent on the level it never finished; the time
of its last level clear as a fraction of ITS OWN clock (the game's start is final_wallclock - 3,918 s, since a clock-ended
game ran its whole clock; second-wave games start thousands of seconds into the benchmark, so benchmark-relative
fractions overstate how late the last clear came); and whether that clear fell in the final fifth of the game's clock.
Also reports the benchmark-relative version for comparison. Usage: python3 -I scripts/end_state.py [--out path.json]
"""
import json, os, sys, statistics as st
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import results_index as ri
CLOCK = 3918.0
runs = {n: json.load(open(ri.benchmark(f"{n}_9300", "local"))) for n in ("r2", "r3", "r4", "r6")}
rows = []
for n, d in runs.items():
    for g in d["game_runs"]:
        apl = [int(x) for x in g.get("actions_per_level") or []]; L = int(g.get("levels_completed", 0)); A = sum(apl)
        fin = float(g.get("final_wallclock_seconds") or 0); h = g.get("history") or []
        if A == 0 or g.get("state") == "won": continue
        start = fin - CLOCK
        own_span = fin - start
        if fin < 0.95 * CLOCK: continue              # ended before a full clock could have elapsed: not clock-ended
        first = float(h[0]["wallclock_seconds"]) if h else start
        if first < start - 60: continue              # first action before the inferred start: not a full-clock game
        last_clear = float(h[sum(apl[:L]) - 1]["wallclock_seconds"]) if L > 0 else None
        rows.append({"run": n, "game": g["game_id"][:4], "levels": L, "actions_on_unfinished_level": A - sum(apl[:L]),
                     "game_start_s": round(start, 1), "wave": 1 if start < 600 else 2,
                     "last_clear_frac_own_clock": None if last_clear is None else round((last_clear - start) / CLOCK, 3),
                     "last_clear_frac_benchmark": None if last_clear is None else round(last_clear / fin, 3)})
own = [r["last_clear_frac_own_clock"] for r in rows if r["last_clear_frac_own_clock"] is not None]
ben = [r["last_clear_frac_benchmark"] for r in rows if r["last_clear_frac_benchmark"] is not None]
out = {"clock_s": CLOCK, "runs": list(runs), "clock_ended_games": len(rows), "second_wave": sum(1 for r in rows if r["wave"] == 2),
       "actions_into_next_level_median": st.median(r["actions_on_unfinished_level"] for r in rows),
       "last_clear_frac_own_clock": {"median": round(st.median(own), 3), "final_fifth": sum(1 for x in own if x >= 0.8), "n": len(own)},
       "last_clear_frac_benchmark_relative": {"median": round(st.median(ben), 3), "final_fifth": sum(1 for x in ben if x >= 0.8), "n": len(ben),
           "note": "the earlier, wrong basis: both times counted from the benchmark start, which overstates second-wave games"},
       "games": rows}
path = os.environ.get("OUT") or (sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else "notes/end_state_controls_2026-11-09.json")
json.dump(out, open(path, "w"), indent=1)
o, b = out["last_clear_frac_own_clock"], out["last_clear_frac_benchmark_relative"]
print(f"wrote {path} | clock-ended {len(rows)} (second wave {out['second_wave']}) | actions into next level median {out['actions_into_next_level_median']} | "
      f"last clear, own clock: median {o['median']}, final fifth {o['final_fifth']}/{o['n']} | benchmark-relative: median {b['median']}, final fifth {b['final_fifth']}/{b['n']}")
