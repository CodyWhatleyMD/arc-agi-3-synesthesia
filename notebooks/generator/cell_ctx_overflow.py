# ---- CONTEXT-OVERFLOW SHIM for the vendored Duck harness -----------------------------------------
# House rule: /home/ignaz/duck-harness is third-party and stays byte-identical, so this is a
# monkeypatch installed at run start, the same way cell_mistral_compat.py / cell_duck_fixes.py are.
#
# WHAT IS WRONG UPSTREAM
# ----------------------
# tool_agent.py:1836-1853, on the analyzer's own request path:
#
#     except requests.RequestException as exc:
#         if not _is_context_length_error(exc): raise
#         trimmed_messages = self._trim_messages_for_context(
#             messages, tools=tools, extra_safety_tokens=_CONTEXT_OVERFLOW_RETRY_TRIM_TOKENS)
#         ...
#         append_transcript("ANALYZER STATUS",
#             "context_overflow_recovered: dropped older history after server rejected ...")
#
# Two defects, one diagnostic and one real:
#
# (1) `exc` IS NEVER LOGGED. The server states its own numbers in that message ("maximum context
#     length is N ... you requested M"), which is the only ground truth about how far the estimate
#     was off -- and the handler throws it away, leaving a transcript line that says recovery
#     happened and nothing about why. Every past investigation of this had to guess the magnitude.
#
# (2) THE ESTIMATE IS LOW, so the trimmer does not trim until the server has already refused.
#     _estimate_tokens (tool_agent.py:462) is literally `(len(json.dumps(payload)) + 2) // 3` --
#     characters over three. That is a rule of thumb, and on this arm's traffic it runs ~10.7%
#     UNDER the true count, while the trim budget only sits ~2.1% under the hard limit
#     (_context_budget_tokens = window - reply_reserve - safety_margin). A 10.7% error against a
#     2.1% cushion overflows, every time, and the harness's "recovery" is to delete the agent's own
#     history mid-game -- the agent loses its accumulated model of the game as a side effect of an
#     arithmetic slip.
#
# WHAT THIS SHIM DOES
# -------------------
# A. LOG IT. Wraps _is_context_length_error to record str(exc)[:300] plus the server's own
#    limit/requested numbers, and wraps _trim_messages_for_context to record len(messages), the
#    raw estimate, the adjusted estimate and the budget whenever the OVERFLOW-RETRY trim fires
#    (identified by extra_safety_tokens == _CONTEXT_OVERFLOW_RETRY_TRIM_TOKENS, which is that call
#    site's signature). Pure observation; changes nothing.
#
# B. FIX IT, the cheap correct-enough way (option (b) of the audit note, not (a)): multiply the
#    estimate by a safety factor so the trimmer's own arithmetic is conservative rather than
#    optimistic. 1.15 covers the measured 10.7% shortfall with margin, and costs only that the
#    agent carries slightly less history than it theoretically could. Option (a) -- a real
#    AutoTokenizer count on every trim decision -- is more accurate and far more expensive, and it
#    would have to tokenize the whole conversation on every turn.
#
# NOT ENV-GATED TO OFF. Both parts are ON by default. This repo has already shipped two shims that
# defaulted to their own off value and so never applied in any run; a correction that has to be
# switched on is not a correction. CTX_ESTIMATE_SAFETY can RAISE or lower the factor, and 1.0
# disables only part B, but doing so is an explicit act that shows up in the run's env.
#
# NOTE ON SCOPE: this is installed from ab_local.py, i.e. the local sweep path. cell_breaker.py is
# NOT exec'd there (only the Kaggle notebooks exec it), which is why this lives in its own cell
# rather than being bolted onto that one.
import functools as _ft, json as _json, os as _os, re as _re, time as _time
import inference.agent.tool_agent as _ta

_CTX_LOG = _os.environ.get("CTX_OVERFLOW_LOG") or _os.path.join(
    _os.environ.get("SMOKE_JOB_DIR", "."), "ctx_overflow.jsonl")
_CTX_SAFETY = float(_os.environ.get("CTX_ESTIMATE_SAFETY", "1.15"))

# the server's own sentence, e.g. "maximum context length is 65536 tokens ... you requested 66231"
_NUMS = _re.compile(r"maximum context length is (\d+).*?requested (\d+)", _re.S | _re.I)


def _ctx_emit(**kw):
    kw["t"] = _time.time()
    try:
        with open(_CTX_LOG, "a") as f:
            f.write(_json.dumps(kw, default=str) + "\n")
    except OSError:
        pass


if getattr(_ta, "_cc_ctx_shim", False):
    print("CTX OVERFLOW SHIM: already installed", flush=True)
else:
    # --- A1: the exception text, at the one place that already sees it ------------------------
    _orig_is_ctx = _ta._is_context_length_error

    @_ft.wraps(_orig_is_ctx)
    def _is_ctx(exc):
        hit = _orig_is_ctx(exc)
        if hit:
            msg = str(exc)
            m = _NUMS.search(msg)
            _ctx_emit(event="context_overflow", error=msg[:300],
                      server_limit=int(m.group(1)) if m else None,
                      requested=int(m.group(2)) if m else None,
                      over_by=(int(m.group(2)) - int(m.group(1))) if m else None)
        return hit
    _ta._is_context_length_error = _is_ctx

    # --- B: conservative estimate (must be installed BEFORE the trim wrapper reads it) --------
    _orig_est = _ta.ToolAgent._estimate_request_input_tokens
    if _CTX_SAFETY != 1.0:
        @_ft.wraps(_orig_est)
        def _est(self, messages, *, tools=None):
            return int(_orig_est(self, messages, tools=tools) * _CTX_SAFETY + 0.5)
        _ta.ToolAgent._estimate_request_input_tokens = _est

    # --- A2: what the overflow-retry trim actually saw -----------------------------------------
    _orig_trim = _ta.ToolAgent._trim_messages_for_context

    @_ft.wraps(_orig_trim)
    def _trim(self, messages, *, tools=None, preserve_recent=1, extra_safety_tokens=0):
        out = _orig_trim(self, messages, tools=tools, preserve_recent=preserve_recent,
                         extra_safety_tokens=extra_safety_tokens)
        # extra_safety_tokens == _CONTEXT_OVERFLOW_RETRY_TRIM_TOKENS is the signature of the
        # post-rejection call site (tool_agent.py:1840); every other caller passes 0.
        if extra_safety_tokens == getattr(_ta, "_CONTEXT_OVERFLOW_RETRY_TRIM_TOKENS", -1):
            _ctx_emit(event="context_overflow_trim",
                      n_messages=len(messages), n_after=len(out),
                      dropped=len(messages) - len(out),
                      estimate_raw=_orig_est(self, messages, tools=tools),
                      estimate_adjusted=self._estimate_request_input_tokens(messages, tools=tools),
                      budget=getattr(self, "_context_budget_tokens", None),
                      safety=_CTX_SAFETY)
        return out
    _ta.ToolAgent._trim_messages_for_context = _trim

    _ta._cc_ctx_shim = True
    assert _ta._is_context_length_error is _is_ctx
    assert _ta.ToolAgent._trim_messages_for_context is _trim
    print(f"CTX OVERFLOW SHIM INSTALLED  estimate_safety={_CTX_SAFETY}  "
          f"(estimate patched: {_CTX_SAFETY != 1.0})  log={_CTX_LOG}", flush=True)
