#!/usr/bin/env python3
"""Regenerate the paper's numbers and figures from results/ and diff them against the committed versions.

Run from the repository root: `python3 analysis/reproduce.py` (needs matplotlib; analysis/requirements.txt gives the
versions it was verified with). Writes analysis/out/. For each artefact it prints MATCH or DIFF. The comparison is
strict: the regenerated JSON must have exactly the reference's keys and list lengths; numbers must agree to 1e-6;
strings and booleans must be equal (a path-valued string is compared by the run file it names, platform/tag/file,
so a path on the machine that ran the experiments matches the same file in this tree); and at least one number must
be compared. Any failed step, missing reference or DIFF makes the exit status 1. The bootstraps are seeded, so a
faithful tree reproduces the committed JSONs exactly.
"""
import json, math, os, subprocess, sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent; ROOT = HERE.parent
sys.path.insert(0, str(HERE)); import results_index as ri
OUT = HERE / "out"; OUT.mkdir(exist_ok=True)
NOTES = ROOT / "paper" / "results_notes"; FIG = ROOT / "paper" / "figures"
PY = sys.executable
TOL = 1e-6
FAILURES = []


def run(cmd, log, env=None):
    e = dict(os.environ); e.update(env or {}); e.setdefault("MPLBACKEND", "Agg")
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, cwd=str(HERE), env=e)
    (OUT / log).write_text(r.stdout + ("\n--- stderr ---\n" + r.stderr if r.stderr else ""))
    if r.returncode:
        last = r.stderr.strip().splitlines()[-1] if r.stderr.strip() else f"exit {r.returncode}"
        print(f"  FAILED {log}: {last}"); FAILURES.append(f"{log}: command failed ({last})")
        return False
    return True


def leaves(o, p="", acc=None):
    """Every leaf of a JSON value as path -> (kind, value); empty containers are leaves too, so schemas compare."""
    acc = {} if acc is None else acc
    if isinstance(o, dict):
        if not o: acc[p] = ("{}", None)
        for k, v in o.items(): leaves(v, f"{p}.{k}", acc)
    elif isinstance(o, list):
        if not o: acc[p] = ("[]", None)
        for i, v in enumerate(o): leaves(v, f"{p}[{i}]", acc)
    elif isinstance(o, bool): acc[p] = ("bool", o)
    elif isinstance(o, (int, float)): acc[p] = ("num", float(o))
    elif o is None: acc[p] = ("null", None)
    else: acc[p] = ("str", ri.identity(o))
    return acc


def report(name, new_path, ref_path):
    """Strict diff of a regenerated JSON against its committed reference; records a failure unless it MATCHes."""
    if not ref_path or not Path(ref_path).exists():
        print(f"  {name}: DIFF  (no committed reference at {ref_path})"); FAILURES.append(f"{name}: reference missing"); return False
    if not Path(new_path).exists():
        print(f"  {name}: DIFF  (nothing regenerated at {new_path})"); FAILURES.append(f"{name}: output missing"); return False
    a, b = leaves(json.load(open(new_path))), leaves(json.load(open(ref_path)))
    problems = [f"missing {k}" for k in sorted(set(b) - set(a))] + [f"unexpected {k}" for k in sorted(set(a) - set(b))]
    kinds, worst = Counter(), 0.0
    for k in sorted(set(a) & set(b)):
        (ta, va), (tb, vb) = a[k], b[k]
        if ta != tb:
            problems.append(f"{k}: {ta} {va!r} vs {tb} {vb!r}"); continue
        kinds[ta] += 1
        if ta == "num":
            if math.isnan(va) or math.isnan(vb):
                if not (math.isnan(va) and math.isnan(vb)): problems.append(f"{k}: {va} vs {vb}")
                continue
            d = abs(va - vb); worst = max(worst, d)
            if d > TOL: problems.append(f"{k}: {va} vs {vb}")
        elif va != vb:
            problems.append(f"{k}: {va!r} vs {vb!r}")
    if kinds["num"] == 0:
        problems.append("no numbers compared")
    what = (f"{kinds['num']} numbers, {kinds['str']} strings, {kinds['bool']} booleans, "
            f"{kinds['null'] + kinds['[]'] + kinds['{}']} null/empty; max |diff| {worst:.3g}; ref {Path(ref_path).name}")
    if problems:
        print(f"  {name}: DIFF  ({len(problems)} problem(s); {what})")
        for x in problems[:5]: print(f"      {x}")
        FAILURES.append(f"{name}: DIFF"); return False
    print(f"  {name}: MATCH  ({what})"); return True


def resolve_run(name):
    """A run name as the committed JSONs record it (its tag) -> benchmark path."""
    for plat in ("local", "kaggle", "vast", "server", "archive"):
        try: return ri.benchmark(name, plat)
        except (FileNotFoundError, KeyError): pass
    raise FileNotFoundError(name)


import matplotlib, numpy  # noqa: E401  (the figure scripts need them; fail here, early, if absent)
print(f"python {sys.version.split()[0]}, matplotlib {matplotlib.__version__}, numpy {numpy.__version__}; outputs in {OUT}")

print("1. headline: untimed (concurrency 14, no clock) vs the timed controls, run-level (cluster) bootstrap")
arm = [ri.log(t, "local") for t in ("r0c14", "r0c14b")] + [ri.log(t, "vast") for t in ("r0x1", "r0x2")]
ctl = [ri.log(f"{t}_9300", "local") for t in ("r2", "r3", "r4", "r6")]
if run([PY, HERE / "compare_arm_groups.py", "--cluster", "--arm", *arm, "--control", *ctl, "--json", OUT / "untimed_c14_vs_controls_n4.json"],
       "untimed_c14_vs_controls_n4.txt"):
    report("untimed vs controls (n=4 vs 4)", OUT / "untimed_c14_vs_controls_n4.json", NOTES / "untimed_c14_vs_controls_n4_2026-11-08.json")
    J = json.load(open(OUT / "untimed_c14_vs_controls_n4.json"))
    print(f"      {len(J['arm'])} untimed runs vs {len(J['control'])} controls, {len(J['games'])} games; CI = 95%, resampling runs within each group, then games")
    for metric in ("score", "levels"):
        m = J[metric]; c = m["cluster"]
        print(f"      {metric:6s}: untimed {m['arm_mean']:6.2f}  controls {m['control_mean']:6.2f}  delta {m['mean_delta']:+6.2f}  "
              f"run-level CI [{c['ci95'][0]:+.2f}, {c['ci95'][1]:+.2f}]  -> {c['verdict']}   (sign {m['arm_better']}/{m['control_better']}/{m['ties']})")

print("2. experience efficiency (E1-E4) on the twelve timed and the untimed runs the note lists")
ee_ref = NOTES / "experience_efficiency_2026-11-07.json"; mt_ref = NOTES / "experience_efficiency_matched_2026-11-07.json"
T = U = None
if not ee_ref.exists():
    print("  reference JSON missing:", ee_ref); FAILURES.append("experience efficiency: reference missing")
else:
    ee = json.load(open(ee_ref))
    try:
        T = [resolve_run(x["run"]) for x in ee["timed"]]; U = [resolve_run(x["run"]) for x in ee["untimed"]]
    except FileNotFoundError as e:
        print(f"  a listed run is not in results/: {e}"); FAILURES.append(f"experience efficiency: run {e} missing")
if T and U:
    if run([PY, HERE / "experience_efficiency.py", "--timed", *T, "--untimed", *U, "--json", OUT / "experience_efficiency.json"], "experience_efficiency.txt"):
        report("experience efficiency, all games", OUT / "experience_efficiency.json", ee_ref)
    if run([PY, HERE / "experience_efficiency.py", "--match", "--timed", *T, "--untimed", *U, "--json", OUT / "experience_efficiency_matched.json"],
           "experience_efficiency_matched.txt"):
        report("experience efficiency, matched games (the earlier three-run untimed cohort)", OUT / "experience_efficiency_matched.json", mt_ref)
    # the survival analysis the paper's section 4 rests on: the twelve timed runs against the four COMPLETE untimed c14 runs
    try:
        U14 = [resolve_run(t) for t in ("r0c14", "r0c14b", "r0x1", "r0x2")]
    except FileNotFoundError as e:
        U14 = None; print(f"  a c14 untimed run is not in results/: {e}"); FAILURES.append(f"experience efficiency c14: run {e} missing")
    if U14 and run([PY, HERE / "experience_efficiency.py", "--match", "--timed", *T, "--untimed", *U14, "--json", OUT / "experience_efficiency_c14.json"],
                   "experience_efficiency_c14.txt"):
        if report("experience efficiency, matched, complete untimed c14 cohort (figure 4.2's input)", OUT / "experience_efficiency_c14.json",
                  NOTES / "experience_efficiency_c14_2026-11-08.json"):
            C = json.load(open(OUT / "experience_efficiency_c14.json"))
            def reached(km, x):
                s_ = 1.0
                for t, v in km["curve"]:
                    if t <= x: s_ = v
                return 1 - s_
            fr = lambda k, x: f"{reached(C['timed_km_' + k], x):.2f} / {reached(C['untimed_km_' + k], x):.2f}"
            print(f"      timed / untimed ({C['timed_km_1']['n']} / {C['untimed_km_1']['n']} games): level 5 within 1,000 actions {fr('5', 1000)}, "
                  f"within 3,000 {fr('5', 3000)}; every level within 1,000 {fr('full', 1000)}, within 3,000 {fr('full', 3000)}")

    print("3. levels cleared per tenth of the clock (the clock-ended games of the twelve timed runs)")
    if run([PY, HERE / "levels_per_tenth_of_clock.py", "--json", OUT / "levels_per_tenth_of_clock.json", *T], "levels_per_tenth_of_clock.txt"):
        report("levels per tenth of clock", OUT / "levels_per_tenth_of_clock.json", NOTES / "levels_per_tenth_of_clock_2026-11-07.json")

print("4. figure 4.3: levels per game, mean with the clock vs mean without, each regime's spread as whiskers")
if run([PY, HERE / "plot_levels_per_game.py"], "plot_levels_per_game.txt", env={"OUT": str(OUT / "levels_per_game")}):
    report("levels per game (figure data)", OUT / "levels_per_game.json", FIG / "levels_per_game.json")

print("5. figure 4.2: survival by level, drawn from the matched efficiency JSON of the complete untimed c14 cohort")
if (OUT / "experience_efficiency_c14.json").exists():
    if run([PY, HERE / "plot_survival.py", OUT / "experience_efficiency_c14.json", OUT / "survival_by_level"], "plot_survival.txt"):
        report("survival by level (figure data)", OUT / "survival_by_level.json", FIG / "survival_by_level.json")
        print("      " + json.load(open(OUT / "survival_by_level.json"))["subtitle"])
else:
    print("  FAILED: no c14 efficiency JSON to draw from"); FAILURES.append("survival figure: c14 JSON missing")

print("6. figure 4.1: mean score against minutes of play, from the runs' periodic summaries")
if run([PY, HERE / "plot_score_vs_playtime.py", "--out", OUT / "score_vs_playtime"], "plot_score_vs_playtime.txt"):
    report("score vs play time (figure data)", OUT / "score_vs_playtime.json", FIG / "score_vs_playtime.json")

print("7. move efficiency: same action window, matched cells, whole-run aggregates (section 4)")
if run([PY, HERE / "move_efficiency.py"], "move_efficiency.txt", env={"OUT": str(OUT / "move_efficiency.json")}):
    report("move efficiency (same action window, matched cells)", OUT / "move_efficiency.json", NOTES / "move_efficiency_timed_vs_untimed_2026-11-09.json")
print("8. end state of the clock-ended control games (section 4): actions into the next level, last clear as a fraction of the game's own clock")
if run([PY, HERE / "end_state.py"], "end_state.txt", env={"OUT": str(OUT / "end_state.json")}):
    report("end state of the clock-ended games", OUT / "end_state.json", NOTES / "end_state_controls_2026-11-09.json")


    S = json.load(open(OUT / "score_vs_playtime.json"))
    print(f"      slope over the first 100 minutes {S['slope_first_100_min_mean']:.2f} points/min (per run: "
          + ", ".join(f"{r['label']} {r['slope_first_100_min']:.2f}" for r in S["runs"])
          + f"); over the last 20 minutes {S['slope_last_20_min_mean']:.2f}; games ended by the clock {S['games_ended_by_clock_range'][0]} to {S['games_ended_by_clock_range'][1]} of {S['games']}")

if FAILURES:
    print(f"FAILED: {len(FAILURES)} of the checks did not reproduce: " + "; ".join(FAILURES))
    sys.exit(1)
print(f"done: every artefact MATCHes its committed version; outputs in {OUT}")
