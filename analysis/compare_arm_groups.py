#!/usr/bin/env python3
"""Compare an arm's runs with a control's runs on one platform: the pre-stated statistic.

notes/prestate_batch_a_2026-10-26.md: per game, the mean score over the arm's runs minus the mean over the
control's runs; over the games, the mean of those differences with a 95% paired bootstrap CI (10,000 resamples of
games) and the sign test. Reads each run's log with compare_benchmark_logs.parse_log, so scores are read the way
the two-run comparison reads them. Only games that took an action in every run are compared.

usage: compare_arm_groups.py --arm LOG [LOG ...] --control LOG [LOG ...] [--boot 10000] [--seed 0]
                             [--json OUT] [--coin-flip G [G ...]] [--bottom G [G ...]]
"""
from __future__ import annotations

import argparse
import json
import pathlib
import random
import statistics
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from compare_benchmark_logs import bootstrap, parse_log, sign_test  # noqa: E402


def group_means(runs: list[dict], games: list[str], metric: str) -> dict[str, float]:
    return {g: statistics.mean(r["per_game"][g][metric] for r in runs) for g in games}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--arm", nargs="+", required=True)
    ap.add_argument("--control", nargs="+", required=True)
    ap.add_argument("--boot", type=int, default=10000)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--json")
    ap.add_argument("--coin-flip", nargs="*", default=[], help="exploratory: fraction of runs scoring >= 50")
    ap.add_argument("--bottom", nargs="*", default=[], help="exploratory: mean levels cleared")
    ap.add_argument("--cluster", action="store_true",
                    help="two-stage bootstrap: resample runs within each group, then games (the run-level CI)")
    a = ap.parse_args()

    arm, ctl = [parse_log(p) for p in a.arm], [parse_log(p) for p in a.control]
    runs = arm + ctl
    games = sorted(set.intersection(*(set(r["per_game"]) for r in runs)))
    started = [g for g in games if all(r["per_game"][g]["actions"] for r in runs)]
    skipped = sorted(set(games) - set(started))

    out = {"arm": a.arm, "control": a.control, "games": started, "skipped_not_started": skipped}
    print(f"arm runs: {len(arm)}   control runs: {len(ctl)}   games compared: {len(started)}"
          + (f"   skipped (not started in every run): {skipped}" if skipped else ""))
    for r in runs:
        print(f"  {pathlib.Path(r['path']).name:42} mean score {statistics.mean(r['per_game'][g]['score'] for g in started):6.2f}")
    rng = random.Random(a.seed)
    for metric in ("score", "levels"):
        am, cm = group_means(arm, started, metric), group_means(ctl, started, metric)
        deltas = [am[g] - cm[g] for g in started]
        mean, low, high = bootstrap(deltas, a.boot, rng)
        wins, losses, ties, p = sign_test(deltas)
        verdict = "GAIN" if low > 0 else "LOSS" if high < 0 else "not resolved at this n"
        out[metric] = {"arm_mean": statistics.mean(am.values()), "control_mean": statistics.mean(cm.values()),
                       "mean_delta": mean, "ci95": [low, high], "arm_better": wins, "control_better": losses,
                       "ties": ties, "sign_p": p, "verdict": verdict}
        print(f"{metric:6}: arm {out[metric]['arm_mean']:6.2f}  control {out[metric]['control_mean']:6.2f}  "
              f"delta {mean:+6.2f}  95% CI [{low:+.2f}, {high:+.2f}]  sign {wins}/{losses}/{ties} p={p:.3f}  -> {verdict}")
        if a.cluster and (len(arm) < 2 or len(ctl) < 2):
            out[metric]["cluster"] = {"ci95": None, "verdict": "withheld: fewer than 2 runs in a group"}
            print("        cluster (runs then games): withheld — a run-level interval needs >= 2 runs per group; "
                  "the game-only interval above overstates certainty at n = 1 (two runs of identical code "
                  "scored 54.70 and 32.22 on Kaggle, 2026-11-02)")
        elif a.cluster:
            # Two-stage bootstrap (notes/prestate_run_level_ci_2026-11-02.md): resample RUNS with replacement
            # within each group (sizes kept), then games. Games inside one run move together, so the
            # game-only interval above is too narrow whenever runs differ as wholes.
            crng = random.Random(a.seed + 1)
            boots = []
            for _ in range(a.boot):
                ra = [arm[crng.randrange(len(arm))] for _ in arm]
                rc = [ctl[crng.randrange(len(ctl))] for _ in ctl]
                bam, bcm = group_means(ra, started, metric), group_means(rc, started, metric)
                bd = [bam[g] - bcm[g] for g in started]
                boots.append(statistics.mean(bd[crng.randrange(len(bd))] for _ in bd))
            boots.sort()
            clow, chigh = boots[int(0.025 * len(boots))], boots[min(len(boots) - 1, int(0.975 * len(boots)))]
            cverdict = "GAIN" if clow > 0 else "LOSS" if chigh < 0 else "not resolved at this n"
            run_means = lambda rs: [statistics.mean(r["per_game"][g][metric] for g in started) for r in rs]
            ram, rcm = run_means(arm), run_means(ctl)
            sd = lambda xs: statistics.stdev(xs) if len(xs) > 1 else float("nan")
            out[metric]["cluster"] = {"ci95": [clow, chigh], "verdict": cverdict, "arm_run_means": ram,
                                      "control_run_means": rcm, "arm_run_sd": sd(ram), "control_run_sd": sd(rcm)}
            print(f"        cluster (runs then games): 95% CI [{clow:+.2f}, {chigh:+.2f}]  -> {cverdict}   "
                  f"run means arm {[round(x, 2) for x in ram]} sd {sd(ram):.2f} | control {[round(x, 2) for x in rcm]} sd {sd(rcm):.2f}")

    def resolve(names):
        """Game names as given (full ids or their short prefix, e.g. cn04) -> the compared games' full ids."""
        hits = [g for g in started if any(g == n or g.split("-")[0] == n for n in names)]
        missing = [n for n in names if not any(g == n or g.split("-")[0] == n for g in started)]
        if missing:
            print(f"  (not among the compared games: {missing})")
        return hits

    if a.coin_flip:
        cf = resolve(a.coin_flip)
        def rate(rs):
            hits = [r["per_game"][g]["score"] >= 50 for r in rs for g in cf]
            return sum(hits) / len(hits) if hits else float("nan")
        out["exploratory_coin_flip_rate_ge50"] = {"games": cf, "arm": rate(arm), "control": rate(ctl)}
        print(f"EXPLORATORY coin-flip games {cf}: share of runs >= 50: arm {rate(arm):.2f}, control {rate(ctl):.2f}")
    if a.bottom:
        bt = resolve(a.bottom)
        am, cm = group_means(arm, bt, "levels"), group_means(ctl, bt, "levels")
        if not bt:
            print("EXPLORATORY stable bottom: none of those games compared")
            am = cm = {"-": float("nan")}
        out["exploratory_bottom_levels"] = {"games": bt, "arm": am, "control": cm}
        print(f"EXPLORATORY stable bottom {bt}: mean levels arm {statistics.mean(am.values()):.2f}, "
              f"control {statistics.mean(cm.values()):.2f}")
    if a.json:
        pathlib.Path(a.json).write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
