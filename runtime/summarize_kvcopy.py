#!/usr/bin/env python3
"""Markdown table of the KV block-copy and autotune evidence of serve_validate.py runs.

Per run (LABEL=OUT_DIR/LABEL, reading LABEL.copies, LABEL.copies.warmup, LABEL.result.json, LABEL.server.log):
copy calls, blocks copied, the largest call, the largest copy temporary (bytes, and in blocks of the KV
storage's row size), calls whose source was also a destination, the lowest free memory before a copy,
whether the server died (OOM traceback in the log), errors before shutdown, ready time, C14 suite and repeat
throughput, MTP acceptance, the KV pool, and for kernel_warmup.flashinfer_autotune: seconds, allocator
retries/OOMs, peak reserved, tuning passes and skipped tactics.

usage: summarize_kvcopy.py OUT_DIR LABEL [LABEL ...]
"""
from __future__ import annotations

import json
import re
import statistics
import sys
from pathlib import Path

MiB = 1 << 20


def copies(path: Path) -> dict:
    rows = []
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("{"):
                rows.append(json.loads(line))
            else:  # older format: ts n free peak
                ts, n, free, *rest = line.split()
                rows.append({"n": int(n), "free": int(free), "peak": int(rest[0]) if rest else None,
                             "reads_written": None, "row_bytes": None})
    if not rows:
        return {}
    row_bytes = next((r["row_bytes"] for r in rows if r.get("row_bytes")), None)
    peak = max((r["peak"] or 0) for r in rows)
    return {
        "calls": len(rows),
        "blocks": sum(r["n"] for r in rows),
        "max_n": max(r["n"] for r in rows),
        "peak_mib": peak / MiB,
        "peak_blocks": (peak / row_bytes) if row_bytes else None,
        "row_mib": row_bytes / MiB if row_bytes else None,
        "overlap": (sum(r["reads_written"] for r in rows) if all(r.get("reads_written") is not None for r in rows)
                    else None),
        "min_free_mib": min(r["free"] for r in rows) / MiB,
        "chunk": rows[-1].get("chunk"),
    }


def warmup(path: Path) -> dict:
    if not path.exists():
        return {}
    rec = json.loads(path.read_text().splitlines()[-1])
    return rec


def server_log(path: Path) -> dict:
    text = path.read_text(errors="replace") if path.exists() else ""
    return {
        "oom": bool(re.search(r"OutOfMemoryError|CUDA out of memory", text)),
        "tuning_passes": len(re.findall(r"Tuning trtllm::fused_moe::gemm1:\s+0%", text)),
        "skipped": sorted(set(re.findall(r"Skipped (\d+) unsupported tactic\(s\) for (trtllm::fused_moe::gemm[12])", text))),
        "loaded": re.findall(r"Loaded (\d+) configs from", text),
        "seeded": bool(re.search(r"ARC3: seeded the FlashInfer autotune cache", text)),
        "alloc_fail_warnings": len(re.findall(r"memory allocation failed with OOM", text)),
    }


def result(path: Path) -> dict:
    if not path.exists():
        return {}
    r = json.loads(path.read_text())
    out = {"ready_s": r.get("ready_seconds"), "mtp": r.get("mtp_mean_acceptance_length"),
           "alive": r.get("server_alive_after_suite")}
    suite = r.get("suite") or {}
    out["c14"] = (suite.get("c14") or {}).get("aggregate_tok_per_s")
    out["c14_embeds"] = (suite.get("c14_embeds") or {}).get("aggregate_tok_per_s")
    rounds = (r.get("repeats") or {}).get("rounds") or []
    for key in ("c14", "c14_embeds"):
        vals = [x[key] for x in rounds if x.get(key) is not None]
        if vals:
            out[f"rep_{key}"] = (statistics.mean(vals), statistics.stdev(vals) if len(vals) > 1 else 0.0, len(vals))
    scan = r.get("log_scan") or {}
    out["errors"] = scan.get("n_errors")
    out["shutdown_errors"] = scan.get("n_errors_during_shutdown")
    kv = scan.get("kv_tokens") or []
    m = re.search(r"GPU KV cache size: ([\d,]+) tokens", kv[0]) if kv else None
    out["kv_tokens"] = m.group(1) if m else None
    md = r.get("metrics_delta") or {}
    err = sum(v for k, v in md.items() if "request_success_total" in k and "error" in k)
    out["error_requests"] = err
    return out


def main() -> None:
    out_dir = Path(sys.argv[1])
    labels = sys.argv[2:]
    rows = {}
    for label in labels:
        c = copies(out_dir / f"{label}.copies")
        w = warmup(out_dir / f"{label}.copies.warmup")
        s = server_log(out_dir / f"{label}.server.log")
        r = result(out_dir / f"{label}.result.json")
        rows[label] = (c, w, s, r)

    def fmt(v, spec=""):
        if v is None:
            return "-"
        return format(v, spec) if spec else str(v)

    lines = ["| | " + " | ".join(labels) + " |", "|---|" + "---|" * len(labels)]

    def add(name, fn):
        lines.append(f"| {name} | " + " | ".join(fn(*rows[l]) for l in labels) + " |")

    add("ARC3_KV_COPY_CHUNK in force", lambda c, w, s, r: fmt(c.get("chunk")))
    add("copy calls / blocks copied", lambda c, w, s, r: f"{fmt(c.get('calls'))} / {fmt(c.get('blocks'))}")
    add("largest call (blocks)", lambda c, w, s, r: fmt(c.get("max_n")))
    add("largest copy temporary", lambda c, w, s, r: (f"{c['peak_mib']:.1f} MiB = {c['peak_blocks']:.2f} blocks"
                                                      if c.get("peak_blocks") is not None else
                                                      (f"{c['peak_mib']:.1f} MiB" if c else "-")))
    add("block (largest KV storage row)", lambda c, w, s, r: fmt(c.get("row_mib"), ".3f") + " MiB" if c.get("row_mib") else "-")
    add("copies reading a written block", lambda c, w, s, r: fmt(c.get("overlap")))
    add("lowest free before a copy", lambda c, w, s, r: fmt(c.get("min_free_mib"), ".0f") + " MiB" if c else "-")
    add("server OOM", lambda c, w, s, r: "yes" if s["oom"] else "no")
    add("error log lines while serving / error requests", lambda c, w, s, r: f"{fmt(r.get('errors'))} / {fmt(r.get('error_requests'))}")
    add("error log lines after the driver's shutdown", lambda c, w, s, r: fmt(r.get("shutdown_errors")))
    add("ready (s)", lambda c, w, s, r: fmt(r.get("ready_s")))
    add("KV pool (tokens)", lambda c, w, s, r: fmt(r.get("kv_tokens")))
    add("C14 suite tok/s", lambda c, w, s, r: fmt(r.get("c14")))
    add("C14 repeats tok/s (mean ± sd, n)", lambda c, w, s, r: (f"{r['rep_c14'][0]:.1f} ± {r['rep_c14'][1]:.1f} ({r['rep_c14'][2]})"
                                                                if r.get("rep_c14") else "-"))
    add("C14 image_embeds repeats tok/s", lambda c, w, s, r: (f"{r['rep_c14_embeds'][0]:.1f} ± {r['rep_c14_embeds'][1]:.1f}"
                                                              if r.get("rep_c14_embeds") else "-"))
    add("MTP mean acceptance length", lambda c, w, s, r: fmt(r.get("mtp")))
    add("autotune: seeded / configs loaded", lambda c, w, s, r: f"{'yes' if s['seeded'] else 'no'} / {','.join(s['loaded']) or '-'}")
    add("autotune: tuning passes, skipped tactics", lambda c, w, s, r: f"{s['tuning_passes']}, " + (
        "; ".join(f"{n} {op.split('::')[-1]}" for n, op in s["skipped"]) or "none"))
    add("autotune: seconds", lambda c, w, s, r: fmt(w.get("seconds")))
    add("autotune: allocator retries / OOMs", lambda c, w, s, r: f"{fmt(w.get('alloc_retries'))} / {fmt(w.get('ooms'))}" if w else "-")
    add("autotune: peak reserved", lambda c, w, s, r: f"{w['peak_reserved'] / (1 << 30):.2f} GiB" if w else "-")
    add("autotune: free before -> after", lambda c, w, s, r: (f"{w['free_before'] / MiB:.0f} -> {w['free_after'] / MiB:.0f} MiB"
                                                              if w else "-"))
    add("allocation-failure warnings in log", lambda c, w, s, r: fmt(s["alloc_fail_warnings"]))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
