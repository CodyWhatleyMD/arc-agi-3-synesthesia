# ---- PREFIX-STABLE TRIM (opt-in; embedded in cell 14 only when the notebook is built with TRIM_MODE=block or PROMPT_DETAILS=1)
# Exec LAST in cell 14 (after cell_ctx_overflow, cell_breaker, cell_recall and, when present, cell_turn_shape): it wraps
# whatever _trim_messages_for_context / _keep_recent_history_turns / _accumulate_usage_tokens / analyze are bound then.
# Monkeypatch only; the frozen bundle is untouched. Every module-level name is _pt_-prefixed (cell 14 is ONE namespace).
# DUCK_TRIM_MODE: "block" = the trim below + logging; "log" = logging only (usage/cached_tokens per response, the trim is the
# shipped one -- the CONTROL arm of an A/B); anything else = off.
#
# WHY (prefix-cache study 10-02). vLLM caches this hybrid model in 800-token blocks hashed in a chain from token 0, and a
# hit also needs a GDN/PLE state at exactly that 800 boundary. Duck's trim (tool_agent.py:1672) drops the oldest user
# block whenever the (x1.15, cell_ctx_overflow) estimate is over the budget and stops the moment it fits, so once a game's
# history reaches the 32k ceiling the message after the system prompt changes on most requests and everything after the
# shared system+tools junction (3,200 tokens) is re-prefilled. Where the cut lands does not matter (chained hashes: all
# blocks after the first changed token are cold); HOW OFTEN the front changes does.
#
# REGIME CAVEAT (review 10-02, read before expecting cache hits). Prefix stability is necessary, not sufficient. The
# state a follow-up request needs -- request N's GDN/PLE checkpoint at floor(P_N/800)*800 -- is FREED when N's decode
# starts (MambaManager align mode: get_num_skipped_tokens = n-1, remove_skipped_blocks every step), while N's attention
# blocks stay referenced until N finishes. A freed block lives in the LRU free queue for about free KV / allocation
# rate. On the deployed config (32k, 28 games, --gpu-memory-utilization 0.92) the pool is saturated all run: q25 ~10k
# free tokens at ~5k tok/s -> ~2 s, against a ~66 s decode (1,549 tokens at 23 tok/s per running request); tonight's B
# is the same. So on THAT config the hit stays at the junction whatever the trim does, and this shim is a shorter-history
# arm (mean prompt about -13%, the depth of a shipped CTX=28672 window), not a prefix-reuse arm. For reuse the
# checkpoint must outlive N's decode + the harness gap + N+1's queue wait: fewer concurrent games, more KV (the generator
# knobs KV_CACHE_GIB / GPU_MEM_UTIL exist only on branch trim-prefix-stable; cmp-fixes' generator REFUSES them), or the
# engine patch that keeps the last prompt-boundary state referenced until the request finishes (KEEP_CKPT=1, which needs
# SPLIT_FIX=1, findings 160). Verify with PROMPT_DETAILS=1: cached_tokens > 3,200 on most requests, or the mechanism never
# ran (scripts/ab_mechanism_metrics.py on branch trim-prefix-stable reads prefix_trim.jsonl and says which).
#
# WHAT.
#  (1) Trigger unchanged: the inner (shipped) trim decides IF, with the same estimate and budget, so no request is ever
#      longer than the shipped trim would send. Below the ceiling nothing is touched (append-only history).
#  (2) When the inner trim dropped anything, the prefix after the head is already invalidated for this request, so the
#      whole cut is taken now: whole older blocks are dropped, oldest first, until the estimate is DRAIN_BLOCKS x 800
#      REAL tokens under the budget (estimate units -> real tokens via a per-agent ratio calibrated from
#      usage.prompt_tokens; fallback 0.89 / CTX_ESTIMATE_SAFETY). The drain is capped at budget // 2.
#  (3) Cuts land only on TASK prompts (the per-call state prompt from _build_user_prompt), never on a follow-up nudge
#      ("You have not acted yet." / "You did not call a tool."), so a window never starts with a nudge the drain made.
#      The block of the NEWEST task prompt is never drained; at least MIN_ASSIST assistant messages are kept.
#  (4) Overflow retry (extra_safety_tokens == _CONTEXT_OVERFLOW_RETRY_TRIM_TOKENS, tool_agent.py:1840): drain to the
#      target even when the inner trim dropped nothing, instead of one 512-token shave per rejected round trip.
#  (5) Turn cap (_keep_recent_history_turns, HIST_TURNS): above the cap, cut to cap - max(4, cap // 4) at a task prompt
#      instead of re-cutting the front on every analyze() call; a token drain also coalesces the cap cut.
#  (6) Remembered cut: a reverted turn (tool_agent.py:2019) restores pre-trim history; the cut is re-applied (object
#      identity of the first kept message) so the next request starts where the server's cached prefix starts.
#  (7) No-user rescue: if the inner trim left no user message (shipped trim without the TURN_SHAPE guard, one turn over
#      the budget), the request is rebuilt as [system, newest task prompt, newest exchanges that fit the budget] instead
#      of going out as [system] ("No user query found" -> retryable failure -> reverted turn). REQUEST trims only (review
#      10-03): the end-of-turn trim inside _persistent_history_messages keeps the shipped result (persist nothing), because
#      a rescue there stored [U_prev] with no reply and the next request carried two board prompts back to back.
#  (8) Lone-turn drain, OFF by default (DUCK_TRIM_LONE_KEEP=0): with it on, when the TURN_SHAPE guard pops exchanges
#      inside the current turn, the turn's oldest exchanges are drained in one go, keeping LONE_KEEP newest. It removes
#      the current turn's own evidence, so it is its own arm, not part of this one.
#  (9) Orphan repair: a trimmed window never carries a tool message whose call is not in the preceding assistant
#      message. The TURN_SHAPE guard (cell_turn_shape.py) leaves [system, user, tool] when one exchange alone is over
#      the budget (it pops the assistant but keeps the preserved newest tool result); such tool messages are dropped. A
#      tool call WITHOUT an id (a server that omits ids: the harness then writes tool_call_id '') owns the tool results
#      after it -- ownership cannot be checked, so they are kept (review 10-03; vLLM always assigns ids today).
# (10) Logging to DUCK_TRIM_LOG (jsonl, both modes): every trim/cap/rescue event and every response's prompt_tokens and
#      prompt_tokens_details.cached_tokens (the server reports the latter only with --enable-prompt-tokens-details).
#      Every line carries mode=block|log. For a forced overflow retry, cell_ctx_overflow's ctx_overflow.jsonl records the
#      INNER trim's n_after/dropped; block then drains further -- the n_out actually sent is in prefix_trim.jsonl.
# Every wrapped path falls back to the shipped result on any exception, and the error handler itself cannot raise. Not functools.wraps on anything (cell_breaker
# checks _chat_completion for __wrapped__; this shim never touches _chat_completion).
import json as _pt_json, math as _pt_math, os as _pt_os, threading as _pt_threading, time as _pt_time
import traceback as _pt_traceback
import inference.agent.tool_agent as _pt_ta

_pt_mode = _pt_os.environ.get("DUCK_TRIM_MODE", "").strip()
if _pt_mode not in ("block", "log"):
    print(f"PREFIX TRIM SHIM: off (DUCK_TRIM_MODE={_pt_mode!r})", flush=True)
elif getattr(_pt_ta.ToolAgent, "_prefix_trim_installed", False):
    print(f"PREFIX TRIM SHIM: already installed (mode {_pt_ta.ToolAgent._prefix_trim_installed!r}; "
          f"DUCK_TRIM_MODE={_pt_mode!r} ignored)", flush=True)
else:
    def _pt_env_num(name, default, lo, hi, cast=int):
        raw = _pt_os.environ.get(name, "").strip()
        if not raw:
            return default
        try:
            v = cast(raw)
            if lo <= v <= hi:
                return v
        except ValueError:
            pass
        print(f"PREFIX TRIM SHIM: ignoring {name}={raw!r} (want {lo}..{hi}); using {default}", flush=True)
        return default

    _pt_safety = _pt_env_num("CTX_ESTIMATE_SAFETY", 1.15, 0.5, 3.0, float)
    _pt_cfg = {
        "block": _pt_env_num("DUCK_TRIM_BLOCK", 800, 16, 8192),                # engine prefix-cache block (server log)
        "drain_blocks": _pt_env_num("DUCK_TRIM_DRAIN_BLOCKS", 12, 1, 40),     # 12 x 800 = 9,600 real tokens
        "min_assist": _pt_env_num("DUCK_TRIM_MIN_ASSIST", 4, 0, 64),
        "lone_keep": _pt_env_num("DUCK_TRIM_LONE_KEEP", 0, 0, 64),            # 0 = lone-turn drain off
        "turn_drain": _pt_env_num("DUCK_TRIM_TURN_DRAIN", -1, -1, 1000),      # -1 = max(4, cap // 4)
        "recut": _pt_env_num("DUCK_TRIM_RECUT", 1, 0, 1),
        "r0": _pt_env_num("DUCK_TRIM_REAL_PER_EST", round(0.89 / _pt_safety, 4), 0.2, 2.0, float),
        "log": _pt_os.environ.get("DUCK_TRIM_LOG") or _pt_os.path.join(_pt_os.environ.get("SMOKE_JOB_DIR", "."), "prefix_trim.jsonl"),
    }
    _pt_stats = {"trim_calls": 0, "trim_events": 0, "cuts": 0, "forced": 0, "rescues": 0, "lone_drains": 0, "cap_cuts": 0,
                 "recuts": 0, "orphans_dropped": 0, "responses": 0, "prompt_tokens": 0, "cached_tokens": 0, "cached_reported": 0, "errors": 0}
    _pt_lock = _pt_threading.Lock()
    _PT_NUDGES = ("You have not acted yet.", "You did not call a tool.")   # tool_agent.py:1907-1913 follow-up prefixes

    def _pt_emit(**kw):
        kw["t"] = round(_pt_time.time(), 3)
        kw["mode"] = _pt_mode
        try:
            line = _pt_json.dumps(kw, default=str)
            with _pt_lock, open(_pt_cfg["log"], "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except Exception:
            pass

    def _pt_bump(**kw):
        with _pt_lock:
            for k, v in kw.items():
                _pt_stats[k] = _pt_stats.get(k, 0) + v

    def _pt_error(where, exc):
        try:   # review 10-03: the fallback path must never raise itself
            _pt_bump(errors=1)
            _pt_emit(event="error", where=where, error=repr(exc)[:300], tb=_pt_traceback.format_exc()[-1200:])
            if _pt_stats.get("errors", 0) <= 3:
                print(f"PREFIX TRIM SHIM: {where} failed ({exc!r}); shipped result used", flush=True)
        except Exception:
            pass

    def _pt_role(m):
        return str(m.get("role", "")).strip() if isinstance(m, dict) else ""

    def _pt_text(m):
        c = m.get("content") if isinstance(m, dict) else None
        if isinstance(c, list):
            return " ".join(str(p.get("text", "")) for p in c if isinstance(p, dict))
        return str(c or "")

    def _pt_is_task(m):
        return _pt_role(m) == "user" and not _pt_text(m).lstrip().startswith(_PT_NUDGES)

    def _pt_n_assist(msgs):
        return sum(1 for m in msgs if _pt_role(m) == "assistant")

    def _pt_drop_orphans(hist):
        """(9) Tool messages not owned by the immediately preceding assistant message's tool_calls are dropped. A call
        without an id owns every tool result after it (ownership cannot be checked; review 10-03)."""
        keep, owned, n = [], None, 0
        for m in hist:
            r = _pt_role(m)
            if r == "assistant":
                ids = [tc.get("id") for tc in (m.get("tool_calls") or []) if isinstance(tc, dict)]
                owned = {"ids": {i for i in ids if i}, "any": any(not i for i in ids)} if ids else None
            elif r == "tool":
                if owned is None or not (owned["any"] or m.get("tool_call_id") in owned["ids"]):
                    n += 1
                    continue
            else:
                owned = None
            keep.append(m)
        return (keep if n else hist), n

    def _pt_cap_keep(cap):
        td = _pt_cfg["turn_drain"]
        return max(1, cap - (max(4, cap // 4) if td < 0 else td))

    def _pt_target(self, budget):
        r = getattr(self, "_pt_r", None) or _pt_cfg["r0"]
        drain_est = int(_pt_math.ceil(_pt_cfg["drain_blocks"] * _pt_cfg["block"] / max(0.05, r)))
        return max(1, budget - min(drain_est, budget // 2)), r

    def _pt_game(self):
        return getattr(self, "_pt_game_name", None)

    _pt_inner_trim = _pt_ta.ToolAgent._trim_messages_for_context
    _pt_inner_keep = _pt_ta.ToolAgent._keep_recent_history_turns
    _pt_inner_acc = _pt_ta.ToolAgent._accumulate_usage_tokens
    _pt_inner_analyze = _pt_ta.ToolAgent.analyze
    _pt_inner_phm = _pt_ta.ToolAgent._persistent_history_messages

    def _pt_recut(self, messages):
        """(6) Re-apply the remembered cut when older history resurfaced (a reverted turn)."""
        cut = getattr(self, "_pt_cut", None)
        if not _pt_cfg["recut"] or cut is None or len(messages) < 3 or messages[1] is cut:
            return messages
        for i in range(2, len(messages)):
            if messages[i] is cut:
                if _pt_n_assist(messages[i:]) < _pt_cfg["min_assist"]:
                    return messages
                _pt_bump(recuts=1)
                _pt_emit(event="recut", agent=id(self), game=_pt_game(self), n_in=len(messages), dropped=i - 1)
                return [messages[0], *messages[i:]]
        return messages

    def _pt_rescue(self, messages, tools, budget):
        """(7) [system, newest task prompt, newest exchanges that fit]. An exchange suffix starts at an assistant
        message, so no tool message loses its call. lone_keep > 0: drain to the target, keeping >= lone_keep."""
        sysm = messages[0]
        users = [i for i in range(1, len(messages)) if _pt_is_task(messages[i])] or \
                [i for i in range(1, len(messages)) if _pt_role(messages[i]) == "user"]
        if not users:
            return None
        u = users[-1]
        tail = messages[u + 1:]
        target, _ = _pt_target(self, budget)
        lk = _pt_cfg["lone_keep"]
        kept = []
        for n, s in enumerate(reversed([i for i, m in enumerate(tail) if _pt_role(m) == "assistant"]), 1):
            cand = tail[s:]
            e = self._estimate_request_input_tokens([sysm, messages[u], *cand], tools=tools)
            if e > budget or (lk > 0 and e > target and n > lk):
                break
            kept = cand
        return [sysm, messages[u], *kept]

    def _pt_drain(self, messages, out, tools, budget, forced):
        """(2)-(5),(8) on the inner trim's result. Returns (new list, info dict)."""
        cfg = _pt_cfg
        sysm, hist = out[0], list(out[1:])
        est = lambda h: self._estimate_request_input_tokens([sysm, *h], tools=tools)
        target, r = _pt_target(self, budget)
        users = [i for i, m in enumerate(hist) if _pt_role(m) == "user"]
        tasks = [i for i in users if _pt_is_task(hist[i])]
        protect = tasks[-1] if tasks else (users[-1] if users else 0)   # newest task prompt: its block stays
        cap = int(getattr(_pt_ta, "_PERSISTENT_HISTORY_ASSISTANT_TURNS", 30) or 0)
        cap_keep = _pt_cap_keep(cap) if cap > 0 else None
        e_in = e = est(hist)
        cuts = 0
        while hist and (e > target or not _pt_is_task(hist[0])
                        or (cap_keep is not None and _pt_n_assist(hist) > cap_keep)):
            nxt = next((i for i in range(1, protect + 1) if _pt_is_task(hist[i])), None)
            if nxt is None or _pt_n_assist(hist[nxt:]) < cfg["min_assist"]:
                break
            del hist[:nxt]
            protect -= nxt
            cuts += 1
            e = est(hist)
        lone = 0
        if cfg["lone_keep"] > 0 and protect == 0 and hist and e > target:
            k = next((i for i, m in enumerate(messages) if m is hist[0]), None)
            if k is not None and (len(messages) - k) > len(hist):   # the guard already popped inside this turn
                while e > target:
                    ex = [i for i in range(1, len(hist)) if _pt_role(hist[i]) == "assistant"]
                    if len(ex) <= cfg["lone_keep"] or ex[0] != 1:
                        break
                    j = 2
                    while j < len(hist) and _pt_role(hist[j]) == "tool":
                        j += 1
                    del hist[1:j]
                    lone += 1
                    e = est(hist)
        hist, orphans = _pt_drop_orphans(hist)
        if orphans:
            e = est(hist)
        return [sysm, *hist], dict(est_in=e_in, est_out=e, target=target, r=round(r, 4), cuts=cuts, lone_pops=lone, orphans=orphans)

    def _pt_trim(self, messages, *, tools=None, preserve_recent=1, extra_safety_tokens=0):
        msgs = messages
        try:
            msgs = _pt_recut(self, messages)
        except Exception as exc:
            _pt_error("recut", exc)
            msgs = messages
        out = _pt_inner_trim(self, msgs, tools=tools, preserve_recent=preserve_recent,
                             extra_safety_tokens=extra_safety_tokens)
        try:
            _pt_bump(trim_calls=1)
            budget = max(1, self._context_budget_tokens - max(0, extra_safety_tokens))
            forced = extra_safety_tokens > 0 and extra_safety_tokens == getattr(_pt_ta, "_CONTEXT_OVERFLOW_RETRY_TRIM_TOKENS", -1)
            new, info, event = out, None, None
            if (len(msgs) > 1 and any(_pt_role(m) == "user" for m in msgs[1:]) and not any(_pt_role(m) == "user" for m in out[1:])
                    and not self.__dict__.get("_pt_persisting")):   # (7) request trims only: persist keeps the shipped result
                fixed = _pt_rescue(self, msgs, tools, budget)
                if fixed is not None:
                    new, event = fixed, "rescue"
                    _pt_bump(rescues=1)
            elif len(out) < len(msgs) or forced:
                new, info = _pt_drain(self, msgs, out, tools, budget, forced)
                event = "trim"
                _pt_bump(trim_events=1, cuts=info["cuts"], forced=int(forced), lone_drains=int(info["lone_pops"] > 0),
                         orphans_dropped=info["orphans"])
            if event is not None:
                if len(new) > 1 and _pt_role(new[1]) == "user":
                    self._pt_cut = new[1]
                _pt_emit(event=event, agent=id(self), game=_pt_game(self), n_in=len(messages), n_recut=len(msgs),
                         n_inner=len(out), n_out=len(new), budget=budget, forced=forced,
                         assist_out=_pt_n_assist(new), **(info or {}))
            out = new
        except Exception as exc:
            _pt_error("trim", exc)
        self._pt_sent = (out, len(out), tools)
        return out

    def _pt_keep(self, messages, *, max_turns):
        try:
            n = _pt_n_assist(messages)
            if max_turns > 0 and n > max_turns:
                keep = _pt_cap_keep(max_turns)
                suffix = [0] * (len(messages) + 1)                     # assistants in messages[i:]
                for i in range(len(messages) - 1, -1, -1):
                    suffix[i] = suffix[i + 1] + (_pt_role(messages[i]) == "assistant")
                cands = [i for i, m in enumerate(messages) if _pt_is_task(m)] or \
                        [i for i, m in enumerate(messages) if _pt_role(m) == "user"]
                pick = next((i for i in cands if 1 <= suffix[i] <= keep), None)
                if pick is None:
                    pick = next((i for i in cands if 1 <= suffix[i] <= max_turns), None)
                if pick is not None:
                    _pt_bump(cap_cuts=1)
                    _pt_emit(event="cap", agent=id(self), game=_pt_game(self), n_in=len(messages), n_out=len(messages) - pick,
                             assist_in=n, assist_out=suffix[pick], cap=max_turns, keep=keep)
                    return list(messages[pick:])
        except Exception as exc:
            _pt_error("keep", exc)
        return _pt_inner_keep(self, messages, max_turns=max_turns)

    def _pt_acc(self, usage):
        try:
            if isinstance(usage, dict):
                pt = usage.get("prompt_tokens")
                e = None
                sent = getattr(self, "_pt_sent", None)
                if sent is not None:
                    e = self._estimate_request_input_tokens(sent[0][:sent[1]], tools=sent[2])
                if pt and e:
                    ratio = float(pt) / float(e)
                    if 0.3 < ratio < 2.0:
                        r = getattr(self, "_pt_r", None)
                        self._pt_r = ratio if r is None else 0.7 * r + 0.3 * ratio
                det = usage.get("prompt_tokens_details")
                ct = det.get("cached_tokens") if isinstance(det, dict) else None
                _pt_bump(responses=1, prompt_tokens=int(pt or 0), cached_reported=int(ct is not None), cached_tokens=int(ct or 0))
                _pt_emit(event="usage", agent=id(self), game=_pt_game(self), prompt=pt, cached=ct,
                         completion=usage.get("completion_tokens"), est=e, r=round(getattr(self, "_pt_r", 0) or 0, 4))
        except Exception as exc:
            _pt_error("usage", exc)
        return _pt_inner_acc(self, usage)

    def _pt_phm(self, *args, **kwargs):
        """Marks the end-of-turn trim (Duck's _persistent_history_messages calls _trim_messages_for_context with the same
        arguments a request trim uses), so (7) can tell the two apart."""
        d = self.__dict__
        prev = d.get("_pt_persisting")
        d["_pt_persisting"] = True
        try:
            return _pt_inner_phm(self, *args, **kwargs)
        finally:
            if prev is None:
                d.pop("_pt_persisting", None)
            else:
                d["_pt_persisting"] = prev

    def _pt_analyze(self, state_path, *args, **kwargs):
        try:
            self._pt_game_name = getattr(state_path, "stem", None)
        except Exception:
            pass
        return _pt_inner_analyze(self, state_path, *args, **kwargs)

    if _pt_mode == "block":
        _pt_ta.ToolAgent._trim_messages_for_context = _pt_trim
        _pt_ta.ToolAgent._keep_recent_history_turns = _pt_keep
        _pt_ta.ToolAgent._persistent_history_messages = _pt_phm
    _pt_ta.ToolAgent._accumulate_usage_tokens = _pt_acc
    _pt_ta.ToolAgent.analyze = _pt_analyze
    _pt_ta.ToolAgent._prefix_trim_installed = _pt_mode
    _pt_ta._prefix_trim_cfg = _pt_cfg
    _pt_ta._prefix_trim_stats = _pt_stats
    if _pt_mode == "block":
        print(f"PREFIX TRIM SHIM INSTALLED: block={_pt_cfg['block']} drain={_pt_cfg['drain_blocks']} blocks "
              f"(~{_pt_cfg['drain_blocks'] * _pt_cfg['block']} real tok) min_assist={_pt_cfg['min_assist']} "
              f"lone_keep={_pt_cfg['lone_keep']} recut={_pt_cfg['recut']} r0={_pt_cfg['r0']} "
              f"cap={getattr(_pt_ta, '_PERSISTENT_HISTORY_ASSISTANT_TURNS', None)} "
              f"| over ctx_overflow={bool(getattr(_pt_ta, '_cc_ctx_shim', False))} "
              f"turn_guard={bool(getattr(_pt_ta.ToolAgent, '_turn_shape_installed', False))} | log={_pt_cfg['log']}", flush=True)
    else:
        print(f"PREFIX TRIM SHIM INSTALLED (log only): shipped trim untouched; per-response prompt/cached tokens -> {_pt_cfg['log']}",
              flush=True)
