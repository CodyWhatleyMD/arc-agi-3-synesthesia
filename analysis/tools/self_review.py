#!/usr/bin/env python3
"""The model reviews its own run (the investigator, 2026-10-18): after a COMMIT run, each game's full trajectory -- the
harness's instructions, the model's reasoning, the code it ran, the tool results and the game's responses -- is
sent back to the same served model at as much context as fits, with a request to find what limited the score and
what would improve it. A final call reads every game's review and ranks improvements across the run.

Never runs in a competition rerun (the notebook gates it; hidden-run outputs are invisible and the 9 h belong to
play). Inputs: the job dir (benchmark.json + <game>_p<k>_requests.jsonl, written when save_request_logs is on).
Outputs: <job>/self_review/<game>.md, <game>.reasoning.md, SUMMARY.md, SUMMARY.reasoning.md, review_meta.json.

usage: self_review.py --job-dir DIR --base-url URL --model NAME [--budget-s S] [--concurrency N]
                      [--max-model-len T] [--max-tokens T]
"""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import pathlib
import time
import urllib.request

CHARS_PER_TOKEN = 3.0          # conservative for code/JSON-heavy text; the server's usage is recorded per call

GAME_PROMPT = """You are reviewing a transcript of your OWN attempt to play one ARC-AGI-3 game inside an agent harness.
The transcript below is reconstructed from the harness's request logs, in order: the harness's instructions to you,
then every turn -- your reasoning, the Python you ran, the tool results, and what the game did. A results table
with the human action baselines comes first. Some long tool outputs or turns may be shortened; that is marked.

Find what limited your score on this game and what would raise it. Be concrete and cite turns or quotes.

Answer in this structure:
1. The game: the mechanics and goal you eventually understood (or failed to), in a few lines.
2. Timeline: where levels were cleared, where you stalled, and the decisive mistakes -- wasted actions, wrong
   hypotheses held too long, misread boards, resets, tool misuse.
3. What you lacked or what misled you: information, tools, instructions, perception, time.
4. Improvements, ranked by expected score gain, each tied to evidence above:
   (a) to the harness and its tools, (b) to the instructions you were given, (c) to your own strategy.
Keep it under 1,500 words."""

SUMMARY_PROMPT = """Below are your own reviews of your play on every game of one run, each after that game's results.
Across all games, rank the top 10 improvements to the harness, its tools, its instructions, and your strategy by
expected total score gain. For each: what to change, which games' evidence supports it, how to implement it, how to
measure it, and any risk. Then list anything that looked like a harness or infrastructure fault rather than a
playing mistake. Keep it under 2,500 words."""


def text_of(content) -> str:
    """Text of a message's content; image parts (logged with their base64 elided) become a short marker."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    out = []
    for part in content:
        if isinstance(part, dict) and part.get("type") == "text":
            out.append(part.get("text", ""))
        elif isinstance(part, dict):
            out.append(f"[{part.get('type', 'part')}]")
    return "\n".join(out)


def clip(s: str, cap: int | None) -> str:
    if cap is None or len(s) <= cap:
        return s
    head = cap * 2 // 3
    return f"{s[:head]}\n[... {len(s) - cap:,} chars omitted ...]\n{s[-(cap - head):]}"


def load_messages(requests_path: pathlib.Path) -> tuple[str, list[dict]]:
    """Every distinct message across a game's request log, in order of first appearance (= chronological):
    each request repeats the history, so a message's first appearance is when it was new."""
    system, seen, ordered = "", set(), []
    with requests_path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                req = json.loads(line)
            except json.JSONDecodeError:
                continue
            for msg in req.get("messages") or []:
                if msg.get("role") == "system":
                    system = system or text_of(msg.get("content"))
                    continue
                key = hashlib.sha1(json.dumps(msg, sort_keys=True, default=str).encode()).hexdigest()
                if key not in seen:
                    seen.add(key)
                    ordered.append(msg)
    return system, ordered


def render(msg: dict, tool_cap, user_cap, reason_cap) -> str:
    role = msg.get("role")
    if role == "assistant":
        parts = []
        reasoning = msg.get("reasoning_content") or msg.get("reasoning") or ""
        if reasoning:
            parts.append("[your reasoning]\n" + clip(str(reasoning), reason_cap))
        if text_of(msg.get("content")).strip():
            parts.append("[your reply]\n" + text_of(msg.get("content")))
        for call in msg.get("tool_calls") or []:
            fn = (call or {}).get("function") or {}
            args = fn.get("arguments")
            try:
                args = json.loads(args) if isinstance(args, str) else (args or {})
            except json.JSONDecodeError:
                args = {"raw": args}
            if isinstance(args, dict) and "code" in args:
                plan = args.get("plan")
                parts.append(f"[your {fn.get('name', 'tool')} call]" + (f" plan: {plan}" if plan else "")
                             + "\n" + str(args["code"]))
            else:
                parts.append(f"[your {fn.get('name', 'tool')} call]\n{json.dumps(args)[:4000]}")
        return "ASSISTANT\n" + "\n".join(parts)
    if role == "tool":
        return "TOOL RESULT\n" + clip(text_of(msg.get("content")), tool_cap)
    return f"{str(role).upper()}\n" + clip(text_of(msg.get("content")), user_cap)


def build_transcript(system: str, msgs: list[dict], budget_chars: int) -> tuple[str, str]:
    """The trajectory at the largest fidelity that fits: shrink tool and harness messages first, then long
    reasoning, then drop middle turns (keeping the opening and the most recent play)."""
    body: list[str] = []
    for level, (tool_cap, user_cap, reason_cap) in enumerate(
            [(None, None, None), (2500, 3000, None), (900, 1200, None), (600, 800, 6000), (400, 500, 2500)]):
        body = [render(m, tool_cap, user_cap, reason_cap) for m in msgs]
        text = "\n\n".join(body)
        if len(system) + len(text) <= budget_chars:
            return "HARNESS INSTRUCTIONS (system prompt)\n" + system + "\n\n" + text, f"fidelity {level}"
    keep_head = budget_chars // 4 - len(system)
    keep_tail = budget_chars - len(system) - max(0, keep_head) - 200
    head, tail, size = [], [], 0
    for b in body:
        if size + len(b) > keep_head:
            break
        head.append(b); size += len(b) + 2
    size = 0
    for b in reversed(body[len(head):]):
        if size + len(b) > keep_tail:
            break
        tail.append(b); size += len(b) + 2
    tail.reverse()
    dropped = len(body) - len(head) - len(tail)
    text = "\n\n".join(head) + f"\n\n[... {dropped} middle messages omitted to fit the context ...]\n\n" + "\n\n".join(tail)
    return "HARNESS INSTRUCTIONS (system prompt)\n" + system + "\n\n" + text, f"middle dropped ({dropped} messages)"


def results_table(run: dict) -> str:
    apl = run.get("actions_per_level") or []
    base = run.get("base_actions_per_level") or []
    rows = [f"game {run.get('game_id')}: state {run.get('state')}, levels {run.get('levels_completed')}/"
            f"{len(base) or '?'}, final score {run.get('final_score')}, stop reason {run.get('stop_reason', '?')}"]
    for i, b in enumerate(base):
        a = apl[i] if i < len(apl) else 0
        rows.append(f"  level {i + 1}: your actions {a or '-'} vs human baseline {b}"
                    + ("" if (a and i < int(run.get('levels_completed') or 0)) else " (not cleared)"))
    return "\n".join(rows)


def count_tokens(base_url: str, model: str, messages: list[dict]) -> int | None:
    """Exact prompt length from vLLM's /tokenize (chat template applied); None if the endpoint is unavailable."""
    root = base_url.rstrip("/").removesuffix("/v1")
    body = json.dumps({"model": model, "messages": messages}).encode()
    req = urllib.request.Request(root + "/tokenize", data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return int(json.loads(resp.read().decode()).get("count"))
    except Exception:
        return None


def chat(base_url: str, model: str, messages: list[dict], max_tokens: int, timeout: float) -> dict:
    body = json.dumps({"model": model, "messages": messages, "max_tokens": max_tokens,
                       "temperature": 0.6, "top_p": 0.95}).encode()
    req = urllib.request.Request(base_url.rstrip("/") + "/chat/completions", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--job-dir", required=True)
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--budget-s", type=float, default=2400.0)
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--max-model-len", type=int, default=147072)
    ap.add_argument("--max-tokens", type=int, default=20000)
    a = ap.parse_args()

    job = pathlib.Path(a.job_dir)
    out = job / "self_review"
    out.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    deadline = started + a.budget_s
    runs = {r["game_id"]: r for r in json.loads((job / "benchmark.json").read_text()).get("game_runs", [])}
    prompt_budget_chars = int((a.max_model_len - a.max_tokens - 3000) * CHARS_PER_TOKEN)
    meta = {"games": {}, "budget_s": a.budget_s, "concurrency": a.concurrency, "prompt_budget_chars": prompt_budget_chars}

    def review(game_id: str) -> tuple[str, str]:
        if time.monotonic() > deadline - 120:
            meta["games"][game_id] = {"skipped": "review budget exhausted"}
            return game_id, ""
        logs = sorted(job.glob(f"{game_id}_p*_requests.jsonl"))
        if not logs:
            meta["games"][game_id] = {"skipped": "no request log"}
            return game_id, ""
        system, msgs = load_messages(logs[0])
        table = results_table(runs[game_id])
        limit = a.max_model_len - a.max_tokens - 512
        chars = prompt_budget_chars - len(table) - len(GAME_PROMPT)
        tokens = None
        for _ in range(4):   # exact length from the server's tokenizer; shrink and rebuild until it fits
            transcript, fidelity = build_transcript(system, msgs, chars)
            messages = [{"role": "system", "content": GAME_PROMPT},
                        {"role": "user", "content": table + "\n\n" + transcript}]
            tokens = count_tokens(a.base_url, a.model, messages)
            if tokens is None or tokens <= limit:
                break
            chars = int(min(chars, len(transcript)) * limit / tokens * 0.97)   # scale the ACTUAL size, not the budget
        t0 = time.monotonic()
        try:
            resp = chat(a.base_url, a.model, messages, a.max_tokens, timeout=max(60.0, deadline - time.monotonic()))
        except Exception as exc:
            meta["games"][game_id] = {"error": repr(exc), "fidelity": fidelity, "prompt_chars": len(transcript)}
            return game_id, ""
        msg = resp["choices"][0]["message"]
        content = msg.get("content") or ""
        reasoning = msg.get("reasoning_content") or msg.get("reasoning") or ""
        (out / f"{game_id}.md").write_text(f"# Self-review: {game_id}\n\n{table}\n\n{content}\n", encoding="utf-8")
        if reasoning:
            (out / f"{game_id}.reasoning.md").write_text(reasoning, encoding="utf-8")
        meta["games"][game_id] = {"fidelity": fidelity, "messages": len(msgs), "prompt_chars": len(transcript),
                                  "tokenize_count": tokens,
                                  "usage": resp.get("usage"), "seconds": round(time.monotonic() - t0, 1),
                                  "finish_reason": resp["choices"][0].get("finish_reason")}
        print(f"ARC3 review: {game_id} done ({fidelity}, {len(msgs)} messages, "
              f"{(resp.get('usage') or {}).get('prompt_tokens', '?')} prompt tokens, "
              f"{time.monotonic() - t0:.0f} s)", flush=True)
        return game_id, content

    order = sorted(runs, key=lambda g: -float(runs[g].get("final_score") or 0))
    reviews: dict[str, str] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, a.concurrency)) as pool:
        for game_id, content in pool.map(review, order):
            if content:
                reviews[game_id] = content

    if reviews and time.monotonic() < deadline - 60:
        joined = "\n\n".join(f"=== {g}\n{results_table(runs[g])}\n\n{reviews[g]}" for g in order if g in reviews)
        cap = prompt_budget_chars - len(SUMMARY_PROMPT)
        limit = a.max_model_len - a.max_tokens - 512
        for _ in range(4):
            messages = [{"role": "system", "content": SUMMARY_PROMPT}, {"role": "user", "content": clip(joined, cap)}]
            tokens = count_tokens(a.base_url, a.model, messages)
            if tokens is None or tokens <= limit:
                break
            cap = int(min(cap, len(messages[1]["content"])) * limit / tokens * 0.97)
        try:
            resp = chat(a.base_url, a.model, messages, a.max_tokens, timeout=max(60.0, deadline - time.monotonic()))
            msg = resp["choices"][0]["message"]
            (out / "SUMMARY.md").write_text("# Self-review: the whole run\n\n" + (msg.get("content") or ""), encoding="utf-8")
            if msg.get("reasoning_content") or msg.get("reasoning"):
                (out / "SUMMARY.reasoning.md").write_text(msg.get("reasoning_content") or msg.get("reasoning"), encoding="utf-8")
            meta["summary"] = {"usage": resp.get("usage"), "finish_reason": resp["choices"][0].get("finish_reason")}
        except Exception as exc:
            meta["summary"] = {"error": repr(exc)}
    meta["seconds"] = round(time.monotonic() - started, 1)
    meta["reviewed"] = len(reviews)
    (out / "review_meta.json").write_text(json.dumps(meta, indent=1, default=str), encoding="utf-8")
    print(f"ARC3 review: {len(reviews)}/{len(runs)} games reviewed, summary "
          f"{'written' if (out / 'SUMMARY.md').exists() else 'not written'}, {meta['seconds']:.0f} s", flush=True)


if __name__ == "__main__":
    main()
