"""Client-side rate limit + 429 backoff for Duck against a metered API.

The investigator's NVIDIA key is capped at 40 requests/minute account-wide. Duck's harness
has NO 429 handling (grepped: none), so a burst from concurrent games would hit
the generic retry and spin. This wraps ToolAgent._chat_completion (the single
HTTP seam, tool_agent.py:1282) with a token bucket shared across all game
threads in the process, plus honour-Retry-After on a 429.

Env:
  RPM_LIMIT     bucket rate, default 34 (headroom under 40)
  RPM_BURST     bucket depth, default 6
Monkeypatch only; the vendored harness stays byte-identical.
"""
import os, time, threading
import inference.agent.tool_agent as _ta

_RL_RPM   = float(os.environ.get("RPM_LIMIT", "34"))
_RL_BURST = int(os.environ.get("RPM_BURST", "6"))
# 2026-09-23: at ~12 rpm average the bucket never engaged and NVIDIA still 429'd
# 23 of 58 requests, steadily -- so the account limit is NOT a rolling minute.
# Eight threads holding ~90s calls sync up; the signature is a per-second or
# in-flight cap. Enforce both: a ceiling on concurrent requests and a minimum
# gap between request STARTS. Defaults keep us well inside any reading of "40 rpm".
_RL_INFLIGHT = int(os.environ.get("RPM_INFLIGHT", "4"))
_RL_GAP_S    = float(os.environ.get("RPM_GAP_S", str(round(60.0/_RL_RPM, 2))))   # 34 rpm -> 1.76s
_rl_sem   = threading.Semaphore(_RL_INFLIGHT)
_rl_lock  = threading.Lock()
_rl_tokens = float(_RL_BURST); _rl_last = time.monotonic(); _rl_last_start = 0.0
_rl_stats = {"calls": 0, "waited_s": 0.0, "http429": 0}

def _rl_take():
    """Block until a request may START: bucket token AND minimum gap since the last start."""
    global _rl_tokens, _rl_last, _rl_last_start
    while True:
        with _rl_lock:
            now = time.monotonic(); _rl_tokens = min(_RL_BURST, _rl_tokens + (now - _rl_last) * _RL_RPM / 60.0); _rl_last = now
            gap_left = _RL_GAP_S - (now - _rl_last_start)
            if _rl_tokens >= 1.0 and gap_left <= 0:
                _rl_tokens -= 1.0; _rl_last_start = now; return
            need = max(gap_left, (1.0 - _rl_tokens) * 60.0 / _RL_RPM if _rl_tokens < 1.0 else 0.0, 0.05)
        _rl_stats["waited_s"] += need; time.sleep(need)

_rl_orig = _ta.ToolAgent._chat_completion
def _rl_limited(self, messages, **kw):
    for attempt in range(6):
        with _rl_sem:                       # at most _RL_INFLIGHT calls in flight
            _rl_take(); _rl_stats["calls"] += 1
            try:
                return _rl_orig(self, messages, **kw)
            except TypeError:
                import traceback, sys
                print("RATE LIMIT: TypeError inside the wrapped call -- full traceback:", file=sys.stderr, flush=True)
                traceback.print_exc(); raise
            except Exception as e:
                # Duck (tool_agent.py:1313-1328) catches requests.HTTPError and re-raises a BARE
                # requests.RequestException(message) `from exc` -- so e.response is always None and
                # this branch was dead for two days (findings 82/87). The status lives on
                # e.__cause__.response, or as the first token of the message ("429 Client Error...").
                import re as _re
                r = getattr(e, "response", None) or getattr(getattr(e, "__cause__", None), "response", None)
                code = getattr(r, "status_code", None); msg = str(e)
                if code is None:
                    m = _re.match(r"\s*(\d{3})\b", msg); code = int(m.group(1)) if m else None
                retryable = (code == 429) or (code in (500, 502, 503, 504)) or ("no choices" in msg)
                if retryable and attempt < 5:
                    key = "http429" if code == 429 else "retry_other"; _rl_stats[key] = _rl_stats.get(key, 0) + 1
                    ra = (r.headers.get("Retry-After") if r is not None and hasattr(r, "headers") else None)
                    if not (ra and str(ra).isdigit()):
                        m = _re.search(r"[Rr]etry after (\d+)\s*s", msg); ra = m.group(1) if m else None
                    _rl_pending = float(ra) + 0.5 if ra else min(60.0, 2.0 * (2 ** attempt))
                else:
                    raise
        time.sleep(_rl_pending)   # back off OUTSIDE the semaphore so the slot frees
_ta.ToolAgent._chat_completion = _rl_limited
print(f"RATE LIMIT installed: {_RL_RPM:.0f} rpm, burst {_RL_BURST}, in-flight<={_RL_INFLIGHT}, gap>={_RL_GAP_S}s, shared across threads", flush=True)
