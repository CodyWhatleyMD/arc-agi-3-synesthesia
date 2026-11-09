#!/usr/bin/env python3
"""Serve our quant from an extracted vLLM image runtime with the Arm B serving line, then check it.

The command is the serving line Arm B actually ran (notes/hansolo_arms_2026-10-05/recovered/armB/
watchdog.json): Han Solo's line plus --enable-mm-embeds, limit-mm image:0 and max_pixels 1048576.
Only the model path, the chat template path and the port are substituted. The environment is the
harness's (rt_env.build_env): RecoverSSM on, Triton GDN decode, his 32k draft vocabulary.

The run refuses to start unless the target GPU (by PCI bus id) has no compute process other than
gnome-remote-desktop, and it selects the card with CUDA_DEVICE_ORDER=PCI_BUS_ID.

Request suite (greedy everywhere, so two runtimes see the same requests and token counts):
  smoke       his setup's smoke request (thinking off, 96 tokens)
  single      one stream, 512 tokens with ignore_eos (decode tok/s)
  embeds      one request with a student image_embeds part (1024 rows x 2560)
  c11/c13/c14 11, 13 and 14 concurrent streams, 512 tokens each (the exact M44/M52/M56 graphs)
  c14_embeds  14 concurrent image_embeds requests, 256 tokens each
  multiturn   a long shared prefix, then two follow-up turns; cached_tokens per turn
Spec-decode and prefix-cache counters are read from /metrics before and after the suite.

usage: serve_validate.py --runtime-root R --manifest M --model DIR --draft-vocab F --embeds-part P
                         --out-dir O --label L [--bus 04:00.0] [--port 18234] [--env K=V ...]
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import re
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
import rt_env  # noqa: E402

ARMB_WATCHDOG = REPO / "notes/hansolo_arms_2026-10-05/recovered/armB/watchdog.json"
SERVED = "primitive-ai/Qwen3.8-Flash-Next-mixed-NVFP4-FP8"
ALLOWED_GPU_TENANTS = ("gnome-remote-desktop",)

PROMPTS = [
    "Explain how a hash map handles collisions, with a worked example.",
    "Describe the water cycle step by step for a ten-year-old.",
    "Write a short story about a lighthouse keeper who finds a map.",
    "List the main differences between TCP and UDP and when to use each.",
    "Explain the proof that there are infinitely many prime numbers.",
    "Summarize the causes and consequences of the French Revolution.",
    "How does a transformer neural network process a sentence?",
    "Give a recipe for bread and explain the role of each ingredient.",
    "Explain what a Fourier transform is and why it is useful.",
    "Describe how vaccines train the immune system.",
    "Plan a three-day hiking trip, including gear and safety checks.",
    "Explain the rules of chess to a complete beginner.",
    "How do compilers turn source code into machine instructions?",
    "Describe the life cycle of a star from nebula to remnant.",
]


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def gpu_tenants(bus: str) -> list[str]:
    out = subprocess.run(
        ["nvidia-smi", "--query-compute-apps=gpu_bus_id,pid,process_name", "--format=csv,noheader"],
        capture_output=True, text=True, check=True).stdout
    rows = [r.strip() for r in out.splitlines() if r.strip()]
    return [r for r in rows if bus.lower() in r.lower()]


def cuda_index_for_bus(bus: str) -> int:
    out = subprocess.run(["nvidia-smi", "--query-gpu=index,pci.bus_id,name", "--format=csv,noheader"],
                         capture_output=True, text=True, check=True).stdout
    for row in out.splitlines():
        idx, pci, _name = [x.strip() for x in row.split(",", 2)]
        if pci.lower().endswith(bus.lower()):
            return int(idx)  # nvidia-smi enumerates in PCI bus order, = CUDA_DEVICE_ORDER=PCI_BUS_ID
    raise SystemExit(f"no GPU on bus {bus}")


def build_command(model: Path, port: int) -> list[str]:
    cmd = list(json.loads(ARMB_WATCHDOG.read_text())["command"])
    assert cmd[1:4] == ["-m", "vllm.entrypoints.cli.main", "serve"], cmd[:4]
    old_model = cmd[4]
    cmd[0] = "/usr/bin/python3"
    cmd[4] = str(model)
    cmd[cmd.index("--chat-template") + 1] = str(model / "chat_template.jinja")
    cmd[cmd.index("--port") + 1] = str(port)
    assert not any(old_model in c for c in cmd), "an old model path survived"
    return cmd


def request_json(url: str, payload: dict | None = None, timeout: float = 600) -> dict:
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def scrape_metrics(base: str) -> dict[str, float]:
    with urllib.request.urlopen(f"{base}/metrics", timeout=60) as r:
        text = r.read().decode()
    want = re.compile(r"^(vllm:(?:spec_decode_[a-z_]+|prefix_cache_[a-z_]+|request_success_total|"
                      r"generation_tokens_total|prompt_tokens_total|num_preemptions_total))(\{[^}]*\})? "
                      r"([0-9.eE+-]+)$")
    vals: dict[str, float] = {}
    for line in text.splitlines():
        m = want.match(line)
        if not m or m.group(1).endswith("_created"):
            continue
        labels = dict(re.findall(r'(\w+)="([^"]*)"', m.group(2) or ""))
        key = m.group(1)
        for label in ("position", "finished_reason"):
            if label in labels:
                key += f"[{label}={labels[label]}]"
        vals[key] = vals.get(key, 0.0) + float(m.group(3))
    return vals


def chat(base: str, messages: list, max_tokens: int, ignore_eos: bool = False, thinking: bool = False,
         timeout: float = 1800) -> dict:
    payload = {"model": SERVED, "messages": messages, "temperature": 0.0, "max_tokens": max_tokens,
               "chat_template_kwargs": {"enable_thinking": thinking}}
    if ignore_eos:
        payload["ignore_eos"] = True
    t0 = time.perf_counter()
    r = request_json(f"{base}/v1/chat/completions", payload, timeout=timeout)
    dt = time.perf_counter() - t0
    msg = r["choices"][0]["message"]
    usage = r.get("usage") or {}
    return {"seconds": round(dt, 3), "completion_tokens": usage.get("completion_tokens"),
            "prompt_tokens": usage.get("prompt_tokens"),
            "cached_tokens": (usage.get("prompt_tokens_details") or {}).get("cached_tokens"),
            "finish_reason": r["choices"][0].get("finish_reason"),
            "content": (msg.get("content") or "")[:400],
            "reasoning": (msg.get("reasoning_content") or msg.get("reasoning") or "")[:200]}


def concurrent_chats(base: str, jobs: list[tuple[list, int]]) -> dict:
    t0 = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(len(jobs)) as ex:
        results = list(ex.map(lambda j: chat(base, j[0], j[1], ignore_eos=True), jobs))
    wall = time.perf_counter() - t0
    toks = sum(r["completion_tokens"] or 0 for r in results)
    return {"n": len(jobs), "wall_seconds": round(wall, 3), "completion_tokens": toks,
            "aggregate_tok_per_s": round(toks / wall, 2),
            "finish_reasons": sorted({r["finish_reason"] for r in results}),
            "per_request_seconds": [r["seconds"] for r in results],
            "first_content": results[0]["content"][:200]}


def run_repeats(base: str, embeds_part: dict, repeats: int) -> dict:
    """Throughput-only rounds: C14 text and C14 image_embeds, alternating, `repeats` times each."""
    rounds = []
    for k in range(repeats):
        text_jobs = [([{"role": "user", "content": PROMPTS[i % len(PROMPTS)] + f" (variant {i})"}], 512)
                     for i in range(14)]
        emb_jobs = [([{"role": "user", "content": [
            {"type": "text", "text": f"Board {i}: describe the layout of the colours in one paragraph."},
            embeds_part]}], 256) for i in range(14)]
        t = concurrent_chats(base, text_jobs)
        e = concurrent_chats(base, emb_jobs)
        rounds.append({"c14": t["aggregate_tok_per_s"], "c14_embeds": e["aggregate_tok_per_s"]})
        log(f"repeat {k + 1}/{repeats}: c14 {t['aggregate_tok_per_s']} tok/s, c14_embeds {e['aggregate_tok_per_s']} tok/s")
    return {"rounds": rounds}


def run_suite(base: str, embeds_part: dict) -> dict:
    out: dict = {}
    out["smoke"] = chat(base, [{"role": "user", "content": "Answer in one short sentence: what is 2 + 2?"}], 96)
    log(f"smoke: {out['smoke']['content']!r}")
    out["single"] = chat(base, [{"role": "user", "content": PROMPTS[0]}], 512, ignore_eos=True)
    s = out["single"]
    s["tok_per_s"] = round((s["completion_tokens"] or 0) / s["seconds"], 2)
    log(f"single stream: {s['completion_tokens']} tokens in {s['seconds']}s = {s['tok_per_s']} tok/s")
    emb_msg = [{"role": "user", "content": [
        {"type": "text", "text": "This is a 64x64 game board. Which colours appear on it? Answer briefly."},
        embeds_part]}]
    out["embeds"] = chat(base, emb_msg, 128)
    log(f"embeds: prompt_tokens={out['embeds']['prompt_tokens']} -> {out['embeds']['content'][:160]!r}")
    for n in (11, 13, 14):
        jobs = [([{"role": "user", "content": PROMPTS[i % len(PROMPTS)] + f" (variant {i})"}], 512) for i in range(n)]
        out[f"c{n}"] = concurrent_chats(base, jobs)
        log(f"c{n}: {out[f'c{n}']['completion_tokens']} tokens in {out[f'c{n}']['wall_seconds']}s = "
            f"{out[f'c{n}']['aggregate_tok_per_s']} tok/s")
    jobs = [([{"role": "user", "content": [
        {"type": "text", "text": f"Board {i}: describe the layout of the colours in one paragraph."},
        embeds_part]}], 256) for i in range(14)]
    out["c14_embeds"] = concurrent_chats(base, jobs)
    log(f"c14_embeds: {out['c14_embeds']['aggregate_tok_per_s']} tok/s, finish {out['c14_embeds']['finish_reasons']}")
    # multi-turn prefix reuse: a ~6k-token shared prefix, then two follow-up turns
    filler = " ".join(f"Rule {k}: a tile of colour {k % 16} next to colour {(k * 7) % 16} scores {k % 9} points."
                      for k in range(400))
    history = [{"role": "system", "content": "You are a careful game analyst. " + filler},
               {"role": "user", "content": "Which colour pairs score the most? Answer in two sentences."}]
    turns = []
    for t in range(3):
        r = chat(base, history, 128)
        turns.append({k: r[k] for k in ("prompt_tokens", "cached_tokens", "completion_tokens", "seconds")})
        history = history + [{"role": "assistant", "content": r["content"]},
                             {"role": "user", "content": f"Follow-up {t + 1}: and which pair scores the least?"}]
    out["multiturn"] = turns
    log(f"multiturn: {turns}")
    return out


LOG_PATTERNS = {
    "kv_memory": r"Available KV cache memory[^\n]*",
    "kv_tokens": r"GPU KV cache size[^\n]*",
    "max_concurrency": r"Maximum concurrency[^\n]*",
    "model_loading": r"Model loading took[^\n]*",
    "weights_loading": r"Loading weights took[^\n]*",
    "init_engine": r"init engine[^\n]*took[^\n]*",
    "graph_capture": r"Graph capturing finished[^\n]*",
    "capture_sizes": r"[^\n]*cudagraph_capture_sizes[^\n]*",
    "recoverssm": r"[^\n]*RecoverSSM[^\n]*",
    "sm120_gemm": r"[^\n]*SM120 GEMM[^\n]*",
    "draft_vocab": r"[^\n]*MTP drafts over[^\n]*",
    "weight_filter": r"[^\n]*Checkpoint weight filter selected[^\n]*",
    "pinned_embedding": r"[^\n]*input embedding kept in pinned host memory[^\n]*",
    "ple": r"[^\n]*Initialized PLE embedding[^\n]*",
    "block_size": r"[^\n]*[Ss]etting attention block size[^\n]*",
    "spec_metrics": r"[^\n]*SpecDecoding metrics[^\n]*",
    "gdn_kernel": r"[^\n]*GDN decode kernel[^\n]*",
    "hc_down_silu": r"[^\n]*hc_down_silu[^\n]*|[^\n]*HC down\+SiLU[^\n]*",
    "errors": r"[^\n]*(?:Traceback|\bERROR\b|Exception|CUDA error|illegal memory)[^\n]*",
}


def scan_log(text: str) -> dict:
    """Pick the key lines out of a server log; errors count only before the driver's own shutdown."""
    cut = text.find("[shutdown]")
    if cut >= 0:
        cut = text.rfind("\n", 0, cut) + 1
    serving, shutdown = (text[:cut], text[cut:]) if cut > 0 else (text, "")
    found = {"n_errors_during_shutdown": len(re.findall(LOG_PATTERNS["errors"], shutdown))}
    text = serving
    for key, pat in LOG_PATTERNS.items():
        hits = re.findall(pat, text)
        found[key] = hits if key in ("errors", "spec_metrics", "recoverssm") else hits[:6]
    found["n_errors"] = len(found["errors"])
    found["errors"] = found["errors"][:40]
    found["spec_metrics_last"] = found["spec_metrics"][-3:]
    found["n_spec_metric_lines"] = len(found["spec_metrics"])
    found.pop("spec_metrics")
    return found


def scan_connects(text: str) -> dict:
    """Classify connect() calls from strace: loopback/unix are local, anything else is network."""
    calls = [line for line in text.splitlines() if "connect(" in line]
    inet = [c for c in calls if "AF_INET" in c]
    remote = [c for c in inet if not re.search(r'inet_addr\("127\.|inet_pton\(AF_INET6, "::1"|"::ffff:127\.', c)]
    proxy = [c for c in inet if "htons(9)" in c]
    summary = (f"{len(calls)} connect() calls, {len(inet)} inet, {len(remote)} to non-loopback addresses, "
               f"{len(proxy)} to the blackhole proxy port 9")
    return {"summary": summary, "non_loopback": remote[:50], "blackhole_proxy": proxy[:50]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runtime-root", type=Path, required=True)
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--model", type=Path, required=True)
    ap.add_argument("--draft-vocab", required=True)
    ap.add_argument("--embeds-part", type=Path, required=True)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--bus", default="04:00.0")
    ap.add_argument("--port", type=int, default=18234)
    ap.add_argument("--ready-timeout", type=int, default=3600)
    ap.add_argument("--env", action="append", default=[], help="extra KEY=VALUE for the server")
    ap.add_argument("--strace-connect", type=Path, default=None,
                    help="run the server under strace -f --seccomp-bpf -e trace=connect and report every "
                         "non-loopback connect() (the Kaggle submission run has no network)")
    ap.add_argument("--repeat", type=int, default=0,
                    help="after the suite, N alternating rounds of C14 text and C14 image_embeds")
    ap.add_argument("--cache-root", type=Path, default=None,
                    help="vLLM/Triton/TMPDIR cache root; keep it short (ZMQ IPC paths max 107 chars)")
    ap.add_argument("--server-arg", action="append", default=[],
                    help="extra argument appended to the recorded serve line (repeat per token), for stress "
                         "variants only, e.g. --server-arg=--kv-cache-memory-bytes --server-arg=19500000000")
    args = ap.parse_args()

    tenants = [t for t in gpu_tenants(args.bus) if not any(a in t for a in ALLOWED_GPU_TENANTS)]
    if tenants:
        raise SystemExit(f"REFUSING: GPU {args.bus} has compute processes: {tenants}")
    index = cuda_index_for_bus(args.bus)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    log_path = args.out_dir / f"{args.label}.server.log"
    manifest = json.loads(args.manifest.read_text())
    cache_root = args.cache_root or args.runtime_root.with_name(args.runtime_root.name + "-cache")
    if len(str(cache_root / "tmp")) + 37 > 107:
        raise SystemExit(f"cache root {cache_root} is too long for ZMQ IPC socket paths")
    env = rt_env.build_env(args.runtime_root, manifest, args.draft_vocab, cache_root)
    env.update({"CUDA_DEVICE_ORDER": "PCI_BUS_ID", "CUDA_VISIBLE_DEVICES": str(index)})
    for kv in args.env:
        k, v = kv.split("=", 1)
        env[k] = v
    cmd = build_command(args.model, args.port) + list(args.server_arg)
    if args.strace_connect:
        cmd = ["strace", "-f", "--seccomp-bpf", "-qq", "-e", "trace=connect", "-o", str(args.strace_connect)] + cmd
    (args.out_dir / f"{args.label}.command.json").write_text(json.dumps(
        {"command": cmd, "env": {k: env[k] for k in sorted(env) if k.startswith(
            ("VLLM_", "CUDA_", "PYTORCH_", "TORCH_", "HF_", "TRANSFORMERS_"))}}, indent=1))
    log(f"GPU {args.bus} = CUDA index {index} under PCI_BUS_ID; launching {args.label}")
    t_launch = time.time()
    with log_path.open("w") as lf:
        proc = subprocess.Popen(cmd, env=env, stdout=lf, stderr=subprocess.STDOUT, start_new_session=True)
    base = f"http://127.0.0.1:{args.port}"
    result: dict = {"label": args.label, "bus": args.bus, "cuda_index": index, "pid": proc.pid}
    try:
        deadline = time.time() + args.ready_timeout
        while True:
            if proc.poll() is not None:
                raise RuntimeError(f"server exited with {proc.returncode} before ready")
            try:
                request_json(f"{base}/v1/models", timeout=5)
                break
            except Exception:
                if time.time() > deadline:
                    raise TimeoutError("server not ready")
                time.sleep(5)
        result["ready_seconds"] = round(time.time() - t_launch, 1)
        log(f"ready after {result['ready_seconds']}s")
        smi = subprocess.run(["nvidia-smi", "--query-compute-apps=gpu_bus_id,pid,process_name,used_memory",
                              "--format=csv,noheader"], capture_output=True, text=True).stdout
        result["nvidia_smi_compute_apps"] = smi.strip().splitlines()
        before = scrape_metrics(base)
        embeds_part = json.loads(args.embeds_part.read_text())
        result["suite"] = run_suite(base, embeds_part)
        if args.repeat:
            result["repeats"] = run_repeats(base, embeds_part, args.repeat)
        time.sleep(12)  # let the periodic stats logger print the last SpecDecoding line
        after = scrape_metrics(base)
        result["metrics_delta"] = {k: round(after.get(k, 0) - before.get(k, 0), 3) for k in sorted(after)}
        md = result["metrics_delta"]
        drafts = md.get("vllm:spec_decode_num_drafts_total", 0)
        draft_toks = md.get("vllm:spec_decode_num_draft_tokens_total", 0)
        acc = md.get("vllm:spec_decode_num_accepted_tokens_total", 0)
        if drafts:
            result["mtp_mean_acceptance_length"] = round(1 + acc / drafts, 3)
            result["mtp_draft_acceptance_rate"] = round(acc / draft_toks, 4) if draft_toks else None
            result["mtp_per_position_acceptance"] = [
                round(md.get(f"vllm:spec_decode_num_accepted_tokens_per_pos_total[position={i}]", 0) / drafts, 4)
                for i in range(3)]
        result["server_alive_after_suite"] = proc.poll() is None
    except Exception as e:  # recorded, then the server is stopped and the log scanned
        result["failure"] = repr(e)
        log(f"FAILURE: {e!r}")
    finally:
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(timeout=90)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait(timeout=30)
        result["log_scan"] = scan_log(log_path.read_text(errors="replace"))
        if args.strace_connect and args.strace_connect.exists():
            result["network"] = scan_connects(args.strace_connect.read_text(errors="replace"))
            log(f"network: {result['network']['summary']}")
        (args.out_dir / f"{args.label}.result.json").write_text(json.dumps(result, indent=1))
        log(f"wrote {args.out_dir / (args.label + '.result.json')}")
        for _ in range(60):
            left = [t for t in gpu_tenants(args.bus) if not any(a in t for a in ALLOWED_GPU_TENANTS)]
            if not left:
                break
            time.sleep(2)
        log(f"GPU {args.bus} tenants after stop: {left or 'none'}")


if __name__ == "__main__":
    main()
