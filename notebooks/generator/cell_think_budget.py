"""THINK-BUDGET shim (serving sprint 10-03, driver 3 / arm A8; measure/cwd3 only -- measure/cwd is the untouched snapshot).

Adds vLLM's per-request HARD cap `thinking_token_budget` (sampler forces </think> once the thinking reaches it; think_budget/DETAILS.md
section 3.2) to every chat request the Duck harness sends, and logs the server's usage per response (prompt/completion tokens and
completion_tokens_details.reasoning_tokens), which the original harness receives (tool_agent.py:1331-1335) but never writes anywhere
(_append_request_snapshot, tool_agent.py:780-818, has no usage field).

Gate: THINK_BUDGET=<int tokens>; unset/0 installs nothing and prints "THINK-BUDGET SHIM: off". Log: THINK_BUDGET_LOG=<path.jsonl> (optional).
Seams, both wrapper-only: (a) inference.utils.openai_compat.build_chat_payload and the name tool_agent imported -- the same seam
cell_mistral_compat.py uses (already installed underneath; inert for a non-mistral model id, it returns the vllm payload unchanged);
the budget is added only when the payload carries chat_template_kwargs, i.e. on the vllm path (openai_compat.py:65-70).
(b) ToolAgent._chat_completion for the usage log, on top of the breaker: exec this cell AFTER cell_breaker.py (ab_local.py does), so
the breaker's retry logic stays innermost and this wrapper only observes the result object (_ChatCompletionResult: message,
finish_reason, usage). A log failure never touches the request."""
import os as _os, json as _json, time as _time, functools as _ft
import inference.utils.openai_compat as _oc
import inference.agent.tool_agent as _ta

_B = int((_os.environ.get("THINK_BUDGET") or "0").strip() or 0)
_LOG = (_os.environ.get("THINK_BUDGET_LOG") or "").strip()
if _B <= 0:
    print("THINK-BUDGET SHIM: off (THINK_BUDGET unset or 0)", flush=True)
elif getattr(_oc.build_chat_payload, "__think_budget_patched__", False):
    print(f"THINK-BUDGET SHIM: already installed (thinking_token_budget={_B})", flush=True)
else:
    _orig_build = _oc.build_chat_payload

    def build_chat_payload(*a, **kw):
        p = _orig_build(*a, **kw)
        if isinstance(p, dict) and "chat_template_kwargs" in p:   # vllm path only (the mistral path pops chat_template_kwargs)
            p["thinking_token_budget"] = _B
        return p

    build_chat_payload.__think_budget_patched__ = True
    _oc.build_chat_payload = build_chat_payload
    if hasattr(_ta, "build_chat_payload"):          # tool_agent imported the name at module load; rebind there too
        _ta.build_chat_payload = build_chat_payload

    _orig_cc = _ta.ToolAgent._chat_completion

    @_ft.wraps(_orig_cc)
    def _cc(self, messages, **kw):
        t0 = _time.time()
        r = _orig_cc(self, messages, **kw)
        if _LOG:
            try:
                u = getattr(r, "usage", None) or {}
                m = getattr(r, "message", None) or {}
                reasoning = m.get("reasoning") or m.get("reasoning_content") or ""
                content = m.get("content")
                rec = {"ts": round(t0, 3), "seconds": round(_time.time() - t0, 2), "finish_reason": getattr(r, "finish_reason", None),
                       "prompt_tokens": u.get("prompt_tokens"), "completion_tokens": u.get("completion_tokens"),
                       "reasoning_tokens": (u.get("completion_tokens_details") or {}).get("reasoning_tokens"),
                       "cached_tokens": (u.get("prompt_tokens_details") or {}).get("cached_tokens"),
                       "reasoning_chars": len(reasoning) if isinstance(reasoning, str) else None,
                       "content_chars": len(content) if isinstance(content, str) else None,
                       "n_tool_calls": len(m.get("tool_calls") or []), "n_messages": len(messages), "budget": _B}
                with open(_LOG, "a", encoding="utf-8") as f:
                    f.write(_json.dumps(rec) + "\n")
            except Exception as e:   # observability only
                print(f"THINK-BUDGET SHIM: log error {e!r}", flush=True)
        return r

    _ta.ToolAgent._chat_completion = _cc
    print(f"THINK-BUDGET SHIM: INSTALLED thinking_token_budget={_B} on build_chat_payload (openai_compat + tool_agent); usage log: {_LOG or 'off'}", flush=True)
