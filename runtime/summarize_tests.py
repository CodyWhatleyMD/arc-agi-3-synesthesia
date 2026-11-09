#!/usr/bin/env python3
"""Markdown table of run_upstream_tests.py results: one row per test file, one column per run.

usage: summarize_tests.py LABEL=tests_<label>.json [LABEL=... ...]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def cell(entry: dict | None) -> str:
    if not entry:
        return "-"
    c = entry["counts"]
    parts = [f"{c[k]} {k}" for k in ("passed", "failed", "errors", "skipped", "xfailed", "xpassed") if c.get(k)]
    if entry["rc"] == "timeout":
        parts.append("TIMEOUT")
    return ", ".join(parts) or f"rc={entry['rc']}"


def main() -> None:
    runs = [(a.split("=", 1)[0], json.loads(Path(a.split("=", 1)[1]).read_text())) for a in sys.argv[1:]]
    files = []
    for _, r in runs:
        files += [f for f in r if f not in files]
    print("| test file | " + " | ".join(label for label, _ in runs) + " |")
    print("|---|" + "---|" * len(runs))
    totals = {label: {"passed": 0, "failed": 0, "errors": 0, "skipped": 0} for label, _ in runs}
    for f in files:
        print(f"| `{f}` | " + " | ".join(cell(r.get(f)) for _, r in runs) + " |")
        for label, r in runs:
            for k in totals[label]:
                totals[label][k] += (r.get(f) or {}).get("counts", {}).get(k, 0)
    print("| **total** | " + " | ".join(
        ", ".join(f"{v} {k}" for k, v in totals[label].items() if v) for label, _ in runs) + " |")


if __name__ == "__main__":
    main()
