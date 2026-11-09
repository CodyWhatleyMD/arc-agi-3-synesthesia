#!/usr/bin/env python3
"""Write harness_switch.diff: the TAAF setup script with only its runtime pins set to harness_pins.json.

The Arm B notebook's setup (setup_commands.json[0] of the frozen bundle) pins the runtime dataset
(RUNTIME_OWNER, RUNTIME_SLUG) and, through validate_prefix_cache_runtime(), three identity blocks.
This rewrites exactly those five assignments the way harness_contract_check.py does and writes the
unified diff of the script text.

usage: make_harness_switch.py SETUP_COMMANDS_JSON [--pins harness_pins.json] [--out harness_switch.diff]
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from harness_contract_check import PIN_BLOCKS  # noqa: E402


def pretty(name: str, value: dict) -> str:
    """The pin block in the setup script's own style (single quotes, 4-space indent)."""
    return f"{name} = " + json.dumps(value, indent=4).replace('"', "'").replace("null", "None") + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("setup_commands", type=Path)
    ap.add_argument("--pins", type=Path, default=HERE / "harness_pins.json")
    ap.add_argument("--out", type=Path, default=HERE / "harness_switch.diff")
    args = ap.parse_args()
    script = json.loads(args.setup_commands.read_text())[0]
    pins = json.loads(args.pins.read_text())
    new = script
    for name in ("RUNTIME_OWNER", "RUNTIME_SLUG"):
        new, n = re.subn(rf"^{name} = '[^']*'$", f"{name} = {pins[name]!r}", new, flags=re.M)
        assert n == 1, name
    for name in PIN_BLOCKS:
        pattern = re.compile(rf"^{name} = \{{\n.*?^\}}\n", re.M | re.S)
        new, n = pattern.subn(lambda _m, nm=name: pretty(nm, pins[nm]), new)
        assert n == 1, name
    diff = "".join(difflib.unified_diff(script.splitlines(True), new.splitlines(True),
                                        "setup_commands.json[0] (frozen bundle)",
                                        "setup_commands.json[0] (vLLM 0.31.0 runtime)"))
    args.out.write_text(diff)
    changed = sum(1 for line in diff.splitlines() if line[:1] in "+-" and line[:3] not in ("+++", "---"))
    print(f"wrote {args.out}: {changed} changed lines")


if __name__ == "__main__":
    main()
