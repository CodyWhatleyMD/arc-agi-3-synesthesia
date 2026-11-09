#!/usr/bin/env python3
"""Markdown side-by-side of serve_validate.py result files (one column per run).

usage: summarize_runs.py LABEL=RESULT_JSON [LABEL=RESULT_JSON ...]
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def counters(md: dict) -> dict[str, float]:
    """Sum metric deltas by base name (+position), whatever label format the file used."""
    out: dict[str, float] = {}
    for k, v in md.items():
        if "_created" in k:
            continue
        base = k.split("{")[0].split("[")[0]
        pos = re.search(r'position="?(\d)', k)
        reason = re.search(r'finished_reason="?(\w+)', k)
        key = base + (f"[{pos.group(1)}]" if pos else "") + (f"[{reason.group(1)}]" if reason else "")
        out[key] = out.get(key, 0.0) + v
    return out


def first(lines: list, pattern: str) -> str:
    for line in lines or []:
        m = re.search(pattern, line)
        if m:
            return m.group(1)
    return "-"


def row_values(r: dict) -> dict[str, str]:
    s, ls, c = r.get("suite", {}), r.get("log_scan", {}), counters(r.get("metrics_delta", {}))
    drafts = c.get("vllm:spec_decode_num_drafts_total", 0)
    acc = c.get("vllm:spec_decode_num_accepted_tokens_total", 0)
    dt = c.get("vllm:spec_decode_num_draft_tokens_total", 0)
    mt = s.get("multiturn") or []
    return {
        "ready (launch -> /v1/models) s": str(r.get("ready_seconds", "-")),
        "weights load s (target, MTP)": ", ".join(first([x], r"took ([0-9.]+) seconds") for x in ls.get("weights_loading", [])),
        "model GPU memory": first(ls.get("model_loading"), r"took ([0-9.]+ GiB) memory"),
        "init engine s": first(ls.get("init_engine"), r"took ([0-9.]+) s"),
        "graph capture": "; ".join(first([x], r"finished in (\d+ secs, took [0-9.]+ GiB)") for x in ls.get("graph_capture", [])),
        "available KV cache memory": first(ls.get("kv_memory"), r"memory: ([0-9.]+ GiB)"),
        "GPU KV cache tokens": first(ls.get("kv_tokens"), r"size: ([0-9,]+) tokens"),
        "max concurrency @147,072": first(ls.get("kv_tokens"), r"request: ([0-9.]+x)"),
        "attention block size": first(ls.get("block_size"), r"size to (\d+) tokens"),
        "smoke reply": repr((s.get("smoke") or {}).get("content", "-")),
        "single stream tok/s (512 tok)": str((s.get("single") or {}).get("tok_per_s", "-")),
        "image_embeds prompt tokens": str((s.get("embeds") or {}).get("prompt_tokens", "-")),
        "C11 aggregate tok/s": str((s.get("c11") or {}).get("aggregate_tok_per_s", "-")),
        "C13 aggregate tok/s": str((s.get("c13") or {}).get("aggregate_tok_per_s", "-")),
        "C14 aggregate tok/s": str((s.get("c14") or {}).get("aggregate_tok_per_s", "-")),
        "C14 image_embeds tok/s": str((s.get("c14_embeds") or {}).get("aggregate_tok_per_s", "-")),
        "MTP mean acceptance length": f"{1 + acc / drafts:.3f}" if drafts else "-",
        "MTP draft acceptance rate": f"{acc / dt:.1%}" if dt else "-",
        "MTP per-position acceptance": ", ".join(f"{c.get(f'vllm:spec_decode_num_accepted_tokens_per_pos_total[{i}]', 0) / drafts:.3f}"
                                                for i in range(3)) if drafts else "-",
        "multi-turn cached tokens (turn 2, 3)": ", ".join(f"{t['cached_tokens']}/{t['prompt_tokens']}" for t in mt[1:]) or "-",
        "prefix cache hits / queries": f"{c.get('vllm:prefix_cache_hits_total', 0):.0f} / {c.get('vllm:prefix_cache_queries_total', 0):.0f}",
        "requests stop/length/error/abort": "/".join(f"{c.get(f'vllm:request_success_total[{k}]', 0):.0f}"
                                                   for k in ("stop", "length", "error", "abort")),
        "errors before shutdown": str(ls.get("n_errors", "-")),
    }


def main() -> None:
    runs = [(a.split("=", 1)[0], json.loads(Path(a.split("=", 1)[1]).read_text())) for a in sys.argv[1:]]
    rows = {label: row_values(r) for label, r in runs}
    keys = list(next(iter(rows.values())))
    print("| | " + " | ".join(label for label, _ in runs) + " |")
    print("|---|" + "---|" * len(runs))
    for k in keys:
        print(f"| {k} | " + " | ".join(rows[label][k] for label, _ in runs) + " |")


if __name__ == "__main__":
    main()
