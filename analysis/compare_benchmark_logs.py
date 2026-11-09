#!/usr/bin/env python3
"""Compare two local benchmark runs on the same games: throughput parity, then score and levels per game.

Reads the benchmark summary block the notebook prints into its log ("benchmark: ..." header, totals,
"per-game (mean across passes):" rows). The block is regenerated during a run, so the LAST one in each log
is used. Runs are compared only on games that took an action in BOTH: a game with zero actions never started
(score 0 / actions 0 is missing data, not a result), and shared zeros would dilute every delta. Unstarted games
are listed per run, because a whole wave that never starts (concurrency x per-game clock > job budget) turns a
25-game benchmark into a smaller one without saying so.

The job budget (ARM_MAX_RUNTIME_S, which sets the soft end every game shares) is part of the conditions:
two runs with different budgets give their games different play time, whatever the per-game clock says.

Throughput: job wall-clock is recovered from the block's own numbers (total tokens / generated tokens per
second, which the harness computes over job wall-clock), giving actions and tokens per job-second. Parity
also checks the run conditions (games, passes, per-game clock, concurrency, action cap) and warns on any
mismatch, because a comparison across different budgets measures the budget.

Noise: a paired bootstrap over games gives a 95% interval for the mean per-game delta (B - A) in score and in
levels, and an exact sign test counts the games each run won. These capture which games moved, not
run-to-run noise. --noise A2 adds a second run of A's own config: the A vs A2 gap is the identical-run spread,
and a B - A delta inside it is not distinguishable from rerunning A. The interval is reported both ways: a
large win shows as an interval above zero exactly as a large regression shows below it.

For the per-request COUNTS (actions per cleared level, requests per action, no-ops) from job dirs, see
scripts/arc_sdk/compare_local_runs.py; this script reads only the logs' summary blocks.

usage: compare_benchmark_logs.py A.log B.log [--noise A2.log] [--json OUT] [--boot N] [--seed S]
"""
from __future__ import annotations

import argparse
import json
import math
import random
import re
import sys

ROW = re.compile(r"^\s+(\S+): score=([\d.]+), levels=([\d.]+)/(\d+), actions=(\d+), tokens=(\d+)")
FIELDS = {
    "games": int, "passes": int, "runs": str, "started": str, "ended": str, "mean score": float,
    "median score": float, "total actions": int, "total tokens": int,
    "generated tokens/sec": float, "total wallclock": float,
}
BUDGET = re.compile(r"env ARM_MAX_RUNTIME_S=(\d+)")
SOLVER = re.compile(r"max_actions_per_game=(\w+), max_runtime_s_per_game=([\d.]+), concurrency=(\d+)")


def parse_log(path: str) -> dict:
    lines = open(path, encoding="utf-8", errors="replace").read().splitlines()
    starts = [i for i, line in enumerate(lines) if line.startswith("benchmark: ") and i + 1 < len(lines)
              and lines[i + 1].startswith("solver:")]
    if not starts:
        sys.exit(f"{path}: no benchmark summary block")
    run = {"path": path, "per_game": {}, "config": {}}
    for line in lines[starts[-1]:]:
        row = ROW.match(line)
        if row:
            game, score, done, total, actions, tokens = row.groups()
            run["per_game"][game] = {"score": float(score), "levels": float(done), "levels_total": int(total),
                                  "actions": int(actions), "tokens": int(tokens)}
            continue
        key, sep, value = line.partition(":")
        key = key.strip()
        if sep and key in FIELDS and value.strip():
            if FIELDS[key] is str:
                run[key] = value.strip()
                continue
            try:
                run[key] = FIELDS[key](value.split()[0].rstrip("s"))
            except ValueError:
                run[key] = value.strip()
    run["config"] = {"games": run.get("games"), "passes": run.get("passes")}
    for line in lines:
        solver = SOLVER.search(line)
        if solver:
            run["config"].update(max_actions=solver.group(1), per_game_s=float(solver.group(2)),
                                 concurrency=int(solver.group(3)))
            break
    for line in lines:
        budget = BUDGET.search(line)
        if budget:
            run["config"]["job_budget_s"] = int(budget.group(1))
            break
    run["in_progress"] = "progress" in str(run.get("ended", ""))
    tok_s = run.get("generated tokens/sec") or 0.0
    run["job_wall_s"] = run.get("total tokens", 0) / tok_s if tok_s else float("nan")
    return run


def throughput(run: dict, games: list[str]) -> dict:
    actions = sum(run["per_game"][g]["actions"] for g in games)
    tokens = sum(run["per_game"][g]["tokens"] for g in games)
    wall = run["job_wall_s"]
    return {"actions": actions, "tokens": tokens, "job_wall_s": wall,
            "actions_per_s": run.get("total actions", 0) / wall if wall else float("nan"),
            "tokens_per_s": run.get("generated tokens/sec", float("nan")),
            "tokens_per_action": tokens / actions if actions else float("nan")}


def bootstrap(deltas: list[float], n: int, rng: random.Random) -> tuple[float, float, float]:
    if not deltas:
        return float("nan"), float("nan"), float("nan")
    means = sorted(sum(rng.choice(deltas) for _ in deltas) / len(deltas) for _ in range(n))
    return sum(deltas) / len(deltas), means[int(0.025 * n)], means[int(0.975 * n) - 1]


def sign_test(deltas: list[float]) -> tuple[int, int, int, float]:
    wins, losses = sum(d > 0 for d in deltas), sum(d < 0 for d in deltas)
    ties, n = len(deltas) - wins - losses, wins + losses
    if n == 0:
        return wins, losses, ties, 1.0
    tail = sum(math.comb(n, k) for k in range(0, min(wins, losses) + 1)) / 2 ** n
    return wins, losses, ties, min(1.0, 2 * tail)


def compare(a: dict, b: dict, n_boot: int, seed: int) -> dict:
    shared = sorted(set(a["per_game"]) & set(b["per_game"]))
    shared = [g for g in shared if a["per_game"][g]["actions"] and b["per_game"][g]["actions"]]
    rng = random.Random(seed)
    result = {"games": shared, "per_game": {}}
    for metric in ("score", "levels"):
        deltas = [b["per_game"][g][metric] - a["per_game"][g][metric] for g in shared]
        mean, low, high = bootstrap(deltas, n_boot, rng)
        wins, losses, ties, p = sign_test(deltas)
        result[metric] = {"mean_delta": mean, "ci95": [low, high], "b_better": wins, "a_better": losses,
                          "ties": ties, "sign_p": p,
                          "a_mean": sum(a["per_game"][g][metric] for g in shared) / len(shared) if shared else float("nan"),
                          "b_mean": sum(b["per_game"][g][metric] for g in shared) / len(shared) if shared else float("nan")}
    for g in shared:
        result["per_game"][g] = {k: [a["per_game"][g][k], b["per_game"][g][k]] for k in ("score", "levels", "actions", "tokens")}
    result["throughput"] = {"a": throughput(a, shared), "b": throughput(b, shared)}
    return result


def parity_warnings(a: dict, b: dict) -> list[str]:
    warnings = []
    for key in sorted(set(a["config"]) | set(b["config"])):
        va, vb = a["config"].get(key), b["config"].get(key)
        if va is None or vb is None:
            warnings.append(f"condition unknown: {key} A={va} B={vb}")
        elif va != vb:
            warnings.append(f"condition differs: {key} A={va} B={vb}")
    if set(a["per_game"]) != set(b["per_game"]):
        warnings.append(f"game sets differ: only A {sorted(set(a['per_game']) - set(b['per_game']))}, "
                        f"only B {sorted(set(b['per_game']) - set(a['per_game']))}")
    for name, run in (("A", a), ("B", b)):
        unstarted = sorted(g for g, v in run["per_game"].items() if not v["actions"])
        if unstarted:
            warnings.append(f"{name}: {len(unstarted)} of {len(run['per_game'])} games never took an action "
                            f"(not started; a job budget shorter than the waves needs?): {' '.join(unstarted)}")
        if run["in_progress"]:
            warnings.append(f"{name} is still in progress: its games have had less time, so this is NOT a valid "
                            f"comparison until both runs finish (shown on games both have started only)")
    return warnings


def report(a: dict, b: dict, result: dict, noise: dict | None) -> None:
    print(f"A = {a['path']}\nB = {b['path']}")
    for warning in parity_warnings(a, b):
        print(f"WARNING: {warning}")
    print(f"games compared: {len(result['games'])} (games that took at least one action in both runs)")
    ta, tb = result["throughput"]["a"], result["throughput"]["b"]
    print("\nthroughput (job wall-clock)        A          B        B/A")
    for key, label in (("actions_per_s", "actions / job-second"), ("tokens_per_s", "generated tokens / s"),
                       ("tokens_per_action", "tokens / action (compared games)")):
        ratio = tb[key] / ta[key] if ta[key] else float("nan")
        print(f"  {label:32s} {ta[key]:9.3f}  {tb[key]:9.3f}  {ratio:8.3f}")
    print(f"  {'job wall-clock s':32s} {ta['job_wall_s']:9.1f}  {tb['job_wall_s']:9.1f}")
    for metric in ("score", "levels"):
        r = result[metric]
        print(f"\n{metric}: A mean {r['a_mean']:.3f}  B mean {r['b_mean']:.3f}  "
              f"delta B-A {r['mean_delta']:+.3f}  95% CI [{r['ci95'][0]:+.3f}, {r['ci95'][1]:+.3f}]")
        side = ("B ahead" if r["ci95"][0] > 0 else "A ahead" if r["ci95"][1] < 0 else "interval spans zero")
        print(f"  games B better {r['b_better']}, A better {r['a_better']}, ties {r['ties']}; "
              f"sign test p={r['sign_p']:.3f}; {side}")
        if noise:
            n = noise[metric]
            print(f"  identical-run gap (A vs A2): mean delta {n['mean_delta']:+.3f} "
                  f"CI [{n['ci95'][0]:+.3f}, {n['ci95'][1]:+.3f}]; "
                  f"B-A {'exceeds' if abs(r['mean_delta']) > abs(n['mean_delta']) else 'is within'} it")
    print("\nper game                score A -> B     levels A -> B   actions A -> B")
    for g, v in result["per_game"].items():
        print(f"  {g:20s} {v['score'][0]:6.2f} -> {v['score'][1]:6.2f}   {v['levels'][0]:4.1f} -> {v['levels'][1]:4.1f}"
              f"     {v['actions'][0]:5d} -> {v['actions'][1]:5d}")


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("a")
    parser.add_argument("b")
    parser.add_argument("--noise", help="a second run of A's config (identical-run spread)")
    parser.add_argument("--json", help="write the comparison as JSON here")
    parser.add_argument("--boot", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    a, b = parse_log(args.a), parse_log(args.b)
    result = compare(a, b, args.boot, args.seed)
    noise = compare(a, parse_log(args.noise), args.boot, args.seed) if args.noise else None
    report(a, b, result, noise)
    if args.json:
        with open(args.json, "w") as out:
            json.dump({"a": args.a, "b": args.b, "warnings": parity_warnings(a, b), "result": result,
                       "noise": noise}, out, indent=1)


if __name__ == "__main__":
    main()
