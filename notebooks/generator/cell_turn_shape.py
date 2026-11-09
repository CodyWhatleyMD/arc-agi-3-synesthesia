# ---- TURN-SHAPE SHIM (opt-in; embedded only when the notebook is built with TURN_SHAPE=ref) --------------------
# Pairs with LOCAL_ANALYZER_YIELD_SECONDS=0 + LOCAL_ANALYZER_TOOL_STEPS=12 (cell 8). Two things the 60 s yield was
# silently doing at a 32k window that the reference arms (64k window) never needed:
#
# (a) LONE-TURN TRIM GUARD. _drop_oldest_history_block (tool_agent.py:1608) drops a whole user-block. Without the
#     yield one turn = U + up to 11 assistant/tool exchanges; when that block alone exceeds the 32k budget the
#     trimmer drops U itself, _drop_until_first_user_message empties the list, the request goes out as [system]
#     only, the Flash-Next template raises "No user query found in messages." -> RequestException -> retryable
#     failure -> the turn's history is reverted. Replayed on the Vercel turns: 82 requests in 22 of 1167 turns.
#     Guard: when the oldest block is the CURRENT one (no later user message), drop its oldest assistant message
#     and that message's tool results, keeping U (task + world model) and the newest evidence.
#
# (b) PER-REQUEST CLOCK. solver.py:300 computes request_timeout_seconds ONCE per analyze() call. With the yield,
#     analyze() is re-entered every <=60 s so the per-game deadline is re-read (q25 overrun past 7920 s: median
#     2 s, max 44 s). Without it, request 12 carries the timeout computed at request 1. Re-read the solver's own
#     request_timeout_seconds() before every request, via should_stop.__self__.
#
# Not functools.wraps on _chat_completion: cell_breaker.py skips installing when _chat_completion has __wrapped__.
# Exec LAST in cell 14 (after cell_breaker / cell_recall).
import os as _os
import inference.agent.tool_agent as _ta

if _os.environ.get("DUCK_TURN_GUARD", "0") != "1":
    print("TURN-SHAPE SHIM: off (DUCK_TURN_GUARD != 1)", flush=True)
elif getattr(_ta.ToolAgent, "_turn_shape_installed", False):
    print("TURN-SHAPE SHIM: already installed", flush=True)
else:
    _ts_stats = {"guard_drops": 0, "clock_refresh": 0}
    _orig_drop = _ta.ToolAgent._drop_oldest_history_block

    def _drop_guarded(self, history, *, preserve_recent):
        if (history and str(history[0].get("role", "")).strip() == "user"
                and not any(str(m.get("role", "")).strip() == "user" for m in history[1:])):
            if len(history) - 1 <= max(1, preserve_recent):
                return False                      # only U + the newest message left: caller stops trimming
            history.pop(1)                        # oldest assistant message of the current turn
            while len(history) > 1 + preserve_recent and str(history[1].get("role", "")).strip() == "tool":
                history.pop(1)                    # its tool results go with it (no orphaned tool messages)
            _ts_stats["guard_drops"] += 1
            return True
        return _orig_drop(self, history, preserve_recent=preserve_recent)

    _ta.ToolAgent._drop_oldest_history_block = _drop_guarded
    _orig_analyze = _ta.ToolAgent.analyze

    def _analyze_stash(self, *args, **kwargs):
        self._ts_clock = getattr(kwargs.get("should_stop"), "__self__", None)   # per-game solver run
        try:
            return _orig_analyze(self, *args, **kwargs)
        finally:
            self._ts_clock = None

    _ta.ToolAgent.analyze = _analyze_stash
    _orig_cc = _ta.ToolAgent._chat_completion

    def _cc_fresh_clock(self, messages, **kw):
        clock = getattr(self, "_ts_clock", None)
        if clock is not None and hasattr(clock, "request_timeout_seconds"):
            try:
                fresh = clock.request_timeout_seconds()
                if fresh is not None:
                    old = kw.get("request_timeout_seconds")
                    kw["request_timeout_seconds"] = fresh if old is None else min(float(old), float(fresh))
                    _ts_stats["clock_refresh"] += 1
            except Exception:
                pass
        return _orig_cc(self, messages, **kw)

    _ta.ToolAgent._chat_completion = _cc_fresh_clock
    _ta.ToolAgent._turn_shape_installed = True
    _ta._turn_shape_stats = _ts_stats
    print(f"TURN-SHAPE SHIM INSTALLED: guard + per-request clock | yield={_ta._LOCAL_ANALYZER_YIELD_SECONDS} "
          f"tool_steps={_ta._LOCAL_ANALYZER_TOOL_STEPS} max_output={_ta._LOCAL_ANALYZER_MAX_OUTPUT}", flush=True)
