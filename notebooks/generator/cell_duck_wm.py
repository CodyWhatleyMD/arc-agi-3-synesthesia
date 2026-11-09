"""WORLD-MODEL CARRY for the Duck harness -- fix #2 of the 10-01 Opus-vs-Flash-Next comparison (findings 153).
Design + prototype: notes/opus_vs_flashnext_2026-10-01/workflow_result.json interventions[1] (design 1, judged best by one
judge, runner-up by the other) and notebooks_duck/prototypes_1001/cell_duck_wm.py. Monkeypatch only: the vendored
tool_agent.py stays byte-identical. Shared exec namespace (findings 79): every module-level name here is _wm_*.

SWITCH  DUCK_WM_MODE  = stock | off | carry   unset or "stock" = this cell installs NOTHING (every ToolAgent attribute is the
                                              same object afterwards: tests/cmp_fixes/f2-wm/test_wm_install.py)
        DUCK_WM_PARTS = (carry only) comma list from harvest,carry,retro,stamps,record,objects
                        default "harvest,carry,retro,record" = the 10-01 design's carry minus stamps and the object list:
                        both opt-in. Stamps alone change 70.7% of requests (cost_f2.json), including prompts before any
                        clear or game over, where carry/retro/record leave the prompt stock -- they would make the A/B arms
                        differ from the first turns; the object list was judged noisy.
        DUCK_WM_HISTORY = (carry only) dedupe | strip | repeat, default dedupe: where the carry-only lines live in the
                        history window (see HISTORY below)
        DUCK_WM_FIELD_CAP (900)  chars kept of a field harvested from reasoning (content-derived fields stay uncapped, as stock)
        DUCK_WM_CARRY_CAP (900)  chars kept of one carried entry
        DUCK_WM_LOG              jsonl, one row per harvest/carry/retro/record event
                                 (default $SMOKE_JOB_DIR/wm_mode.jsonl when SMOKE_JOB_DIR is set, otherwise no log)

THE STOCK CHANNEL (tool_agent.py sha256 535ee88b..., identical in the duck-harness tree and the Kaggle bundle):
  :1105 _update_summarized_knowledge_from_assistant(content) is the ONLY writer and is called with `content` only (:1896,
        :1930) -- labelled lines in `reasoning` never reach it.
  :1113 _update_summarized_knowledge_from_step_summary BLANKS world/goal/action model, findings, questions and plan on every
        level transition, game over and run completion (only cross_level_notes survives).
  :1128 _summarized_knowledge_lines renders the block into each analyze() call's user prompt (:1236).
What the two v5-config Kaggle runs show (q25 09-30, B 10-01; tests/cmp_fixes/f2-wm/measure_tokens.py): the block is NOT
empty in general on our quant -- it is present in 70% / 72% of prompts, because the quant writes labelled `content` in
44% / 41% of responses. It is empty at game start, and blanked at all 38 / 36 clears and 16 / 15 game-overs (every
game-over restarts the SAME level). Labelled World/Goal/Action blocks that live ONLY in reasoning: 18 / 90 responses
(0.9% / 4.3%). So on this stack the lever is mostly (ii) + (iv), not (i); (i) is what the author-served run needed.

PARTS (carry):
  harvest (i)   wrap _chat_completion: a response whose content has no labelled World/Goal/Action model -> the LAST labelled
                block of each in `reasoning` (label line + the bullet lines under it; Duck strips blank lines, :866) is set
                as that field, capped at DUCK_WM_FIELD_CAP, sticky until replaced. Content labels win, as stock.
  carry   (ii)  wrap _update_summarized_knowledge_from_step_summary: on a level clear or game-over the world/action/goal
                models move into a carried entry "- Carried from L{n} (...; re-verify on this level before relying on it)"
                BEFORE stock blanks them; <=2 entries, newest first; a clear replaces that level's game-over entry.
                Findings/questions/plan are still blanked (stale plans are a documented harm: vc33, ar25, ls20/wa30).
  retro   (ii-b) the first labelled World/Goal/Action model written after a clear and before the next executed action is
                appended to that clear's entry when it reads as a retrospective (solved|cleared|won|...): q25 16/38 clears,
                which stock overwrote within 0-3 turns.
  stamps  (iii) fields render as "- World model [unchanged for K actions]: ..." (no stamp at K=0); a stamp the model copies
                back is stripped. Needs cell_duck_fixes' label fix (it is what reads "World model [..]:"), checked at install.
  record  (iv)  wrap _dispatch_tool: after a call that cleared a level, a harness-written line "- Level-clear record L{n}":
                winning action, level length, the pre-win frame's index in `history`, and "The solved configuration =
                pre-win frame + this action; it was never displayed" (re86/r11l/cn04/m0r0 misread the win: findings 153).
  objects       (opt-in) adds the prototype's object-change list to the record (judged noisy: "8x8 new/reshaped").
  The carry-only lines ("- Carried from L...", "- Level-clear record L...") sit inside the stock block, after its own lines,
  and their text is STABLE (no running counter): an entry renders the same line until it changes.

HISTORY (carry/record on; DUCK_WM_HISTORY) -- 57% of q25's analyze() calls were 60 s yields (findings 153), so a line
rendered into every prompt is copied into every retained turn. Measured on the two v5-config Kaggle runs (4,198 requests
replayed through the real analyze() + trim at 32k, Flash-Next tokenizer + template; tests/cmp_fixes/f2-wm/cost_f2.json),
default parts:
  dedupe  (DEFAULT) before each analyze() call, a line that already sits word for word in a user prompt of the history window
          that survives this call's first trim is not rendered again (survival = the installed trim run on [system, history,
          an over-sized stand-in for the new prompt]). Nothing already sent is ever rewritten. Window +272 carry tokens per
          request (mean; p90 652), newest prompt +51 (on 24% of requests, +216 there), -0.12 assistant turns of history;
          full-prefix extensions 41.4% vs stock 41.6%; computed prompt under a prompt-boundary prefix cache +40/request.
  strip   the 10-01 design's (v): drop the lines from OLDER user prompts in _history_messages before each call, so they live
          in the newest prompt only. Window +249, newest +234 -- but it rewrites the previous call's prompt, so the next
          request is no longer an extension of the last one: full-prefix extensions fall to 30.3% and, with a prompt-boundary
          checkpoint cache (SPLIT_FIX + KEEP_CKPT, findings 160), +2,390 computed prompt tokens per request (+17.5%).
  repeat  stock's own pattern for its block: a copy in every prompt, nothing rewritten. Window +1,183 (p90 2,912), -0.54
          assistant turns of history per request.
  TURN SHAPE (review 10-03): dedupe decides survival at the call's FIRST trim. Under the Kaggle shape (yield 60 s, 1.28
          requests per call) later trims of the same call drop a host prompt only rarely: 4 of 7,266 carried line-requests
          (0.06%). Under TURN_SHAPE=ref (yield 0, 12 tool steps: 3.5 requests per call -- and Duck's OWN defaults, i.e. any
          local run that sets neither LOCAL_ANALYZER_YIELD_SECONDS nor _TOOL_STEPS) 547 of 3,325 line-requests (16.5%) lacked a
          line the agent held at call start (repeat 1.5%). So the generator and ab_local REFUSE dedupe with that shape; use
          repeat there. Measured cost under ref (v6out/ref replay): newest prompt +101.6, window +234.5, net -65.0,
          prompt-boundary checkpoint +81 per request.
          The survival probe sets agent._duck_trim_probe while it runs the installed trim chain, so trims that keep stats
          or state (f5's lazy ledger cut) can tell the probe from a real request (review 10-03: the probe was counted as
          real lazy cuts). TRIM_MODE=block (stateful) is still refused with dedupe.
OFF: no carried block, and the user-prompt sentences that demand/label it are removed (history length untouched): the
three in every analyze() prompt, and (review 10-03) the "World model:/Goal model:..." sentence of Duck's "You have not
acted yet" follow-up nudge, which analyze() appends itself (removed from every outgoing request, deterministically, so a
game's requests stay extensions of each other).

Install checks: behavioural probes on a throwaway ToolAgent (the block's header/footer, stock blanking on a clear, the
label extractor, the off-mode sentences). A failed probe raises on a quota/smoke/local run and, when the exec namespace
has TRUE_SUBMISSION truthy (the hidden rerun), prints and installs NOTHING (the stock harness runs).
Load order: anywhere after cell_duck_fixes (label fix). The _chat_completion wrapper keeps its original under `_wm_orig`,
NOT `__wrapped__`, so cell_breaker's "already wrapped by cell_15c" check cannot be tripped whichever cell loads first.
"""
import os as _wm_os, re as _wm_re, json as _wm_json, threading as _wm_threading, time as _wm_time
from pathlib import Path as _wm_Path
import inference.agent.tool_agent as _wm_ta
from inference.agent.runtime_state import load_runtime_state as _wm_load_state

_WM_MODE = (_wm_os.environ.get("DUCK_WM_MODE", "stock") or "stock").strip().lower()
if _WM_MODE not in ("stock", "off", "carry"):
    raise ValueError(f"DUCK_WM_MODE must be stock|off|carry, got {_WM_MODE!r}")
_WM_ALL_PARTS = ("harvest", "carry", "retro", "stamps", "record", "objects")
_WM_DEFAULT_PARTS = "harvest,carry,retro,record"   # the design's carry minus stamps (they alter ~71% of prompts before any clear)
_WM_HISTORY_MODES = ("dedupe", "strip", "repeat")
_WM_PARTS, _WM_HISTORY, _WM_FIELD_CAP, _WM_CARRY_CAP = frozenset(), "dedupe", 900, 900
if _WM_MODE == "carry":   # the carry-only settings are read (and refused when bad) only when carry is on: stock reads nothing else
    _WM_PARTS = frozenset(p.strip().lower() for p in (_wm_os.environ.get("DUCK_WM_PARTS") or _WM_DEFAULT_PARTS).split(",") if p.strip())
    if _WM_PARTS - set(_WM_ALL_PARTS):
        raise ValueError(f"DUCK_WM_PARTS: unknown part(s) {sorted(_WM_PARTS - set(_WM_ALL_PARTS))}; known: {_WM_ALL_PARTS}")
    if "retro" in _WM_PARTS and "carry" not in _WM_PARTS:
        raise ValueError("DUCK_WM_PARTS: retro appends to a carried clear entry, so it needs carry")
    if "objects" in _WM_PARTS and "record" not in _WM_PARTS:
        raise ValueError("DUCK_WM_PARTS: objects is part of the level-clear record, so it needs record")
    _WM_HISTORY = (_wm_os.environ.get("DUCK_WM_HISTORY") or "dedupe").strip().lower()
    if _WM_HISTORY not in _WM_HISTORY_MODES:
        raise ValueError(f"DUCK_WM_HISTORY must be one of {_WM_HISTORY_MODES}, got {_WM_HISTORY!r}")
    _WM_FIELD_CAP = int(_wm_os.environ.get("DUCK_WM_FIELD_CAP", "900"))   # harvested median 583 chars, p75 933 (author-served)
    _WM_CARRY_CAP = int(_wm_os.environ.get("DUCK_WM_CARRY_CAP", "900"))   # per carried entry
_WM_KEEP = 2                                                            # carried entries / full records kept, newest first
_WM_LOG = _wm_os.environ.get("DUCK_WM_LOG") or (
    _wm_os.path.join(_wm_os.environ["SMOKE_JOB_DIR"], "wm_mode.jsonl") if _wm_os.environ.get("SMOKE_JOB_DIR") else "")
_WM_CARRY_PREFIX = "- Carried from L"
_WM_RECORD_PREFIX = "- Level-clear record L"
_WM_END_ANCHOR = "\nend of world model. "   # the line after the block in every analyze() prompt (tool_agent.py:1237)
_wm_log_lock = _wm_threading.Lock()
_wm_stats = {"harvest": 0, "carry": 0, "retro": 0, "record": 0, "stripped_lines": 0, "deduped_lines": 0, "errors": 0}

_WM_LABELS = {"world_model": "World model", "action_model": "Action model", "goal_model": "Goal model"}
_WM_BLANKED = ("world_model", "goal_model", "action_model", "recent_findings", "open_questions", "current_plan")
_WM_ANY_LABEL = _wm_re.compile(r"^(?:[-*#>\s]|\d+[.)])*\**\s*(?:World model|Goal model|Action model|Recent findings|Open questions|"
                               r"Plan|Cross-level notes|Hypothesis|Next test|History check)\b[^:\n]{0,48}:", _wm_re.I)
_WM_LINE = {k: _wm_re.compile(r"^(?:[-*#>\s]|\d+[.)])*\**\s*" + _wm_re.escape(v) + r"\b[^:\n]{0,48}:\**\s*(.*)$", _wm_re.I)
            for k, v in _WM_LABELS.items()}
_WM_RETRO = _wm_re.compile(r"\b(?:solved|solution|completed?|cleared|won|win|winning)\b", _wm_re.I)
_WM_BULLET = _wm_re.compile(r"^(?:[-*•]\s|\d+[.)]\s)")
_WM_STAMP = _wm_re.compile(r"\s*\[(?:unchanged for|updated)[^\]]*\]", _wm_re.I)
# the stock block's line labels, in render order (tool_agent.py:1129-1137)
_WM_RENDER = (("World model", "world_model"), ("Goal model", "goal_model"), ("Action model", "action_model"),
              ("Recent findings", "recent_findings"), ("Open questions", "open_questions"), ("Plan", "current_plan"),
              ("Cross-level notes", "cross_level_notes"))
_WM_HEADER = _WM_FOOTER = None   # probed from the stock renderer at install


def _wm_emit(agent, event, **kw):
    _wm_stats[event] = _wm_stats.get(event, 0) + 1
    if not _WM_LOG:
        return
    try:
        row = {"t": round(_wm_time.time(), 1), "stem": agent.__dict__.get("_wm_stem"), "event": event, **kw}
        with _wm_log_lock, open(_WM_LOG, "a", encoding="utf-8") as fh:
            fh.write(_wm_json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _wm_error(where, e):
    _wm_stats["errors"] += 1
    print(f"WM: {where} skipped ({type(e).__name__}: {e})", flush=True)


def _wm_now(agent):
    try:
        return int((agent.__dict__.get("_last_action_result") or {}).get("action_num") or 0)
    except (TypeError, ValueError):
        return 0


def _wm_state(agent):
    """Per-agent state, reset whenever Duck resets its own session (_ensure_session: a new runtime dir)."""
    d = agent.__dict__
    run_dir = d.get("_session_runtime_dir")
    if d.get("_wm_dir", 0) != run_dir or "_wm_since" not in d:
        d.update(_wm_dir=run_dir, _wm_since={}, _wm_carried=[], _wm_records=[], _wm_retro_for=None)
    return d


def _wm_retro_check(agent, key, value):
    """(ii-b) the first labelled World/Goal/Action model after a clear, before the next executed action."""
    st = _wm_state(agent)
    lvl = st.get("_wm_retro_for")
    if lvl is None or key not in _WM_LABELS:
        return
    st["_wm_retro_for"] = None
    if not _WM_RETRO.search(value):
        return
    add = "Your own summary right after the clear: " + value[:_WM_CARRY_CAP]
    for e in st["_wm_carried"]:
        if e["kind"] == "clear" and e["level"] == lvl:
            e["text"] = (e["text"] + " | " + add)[: 2 * _WM_CARRY_CAP]
            break
    else:
        st["_wm_carried"].insert(0, {"level": lvl, "kind": "clear", "action": _wm_now(agent), "written": None, "text": add})
        del st["_wm_carried"][_WM_KEEP:]
    _wm_emit(agent, "retro", level=lvl, chars=len(value))


def _wm_harvest(reasoning):
    """The LAST labelled block of each of World/Action/Goal model in `reasoning`: the label line's tail plus the bullet lines
    under it (an earlier draft in the same reasoning is superseded by the later one)."""
    lines = (reasoning or "").splitlines()
    out = {}
    for key, rx in _WM_LINE.items():
        last = None
        for i, ln in enumerate(lines):
            if rx.match(ln.strip()):
                last = i
        if last is None:
            continue
        head = rx.match(lines[last].strip()).group(1).strip()
        body = [head] if head else []
        for ln in lines[last + 1:]:                 # Duck strips blank lines (:866), so a block ends at the first line
            s = ln.strip()                           # that is not a bullet ("Let me ...") or is another label
            if not s or _WM_ANY_LABEL.match(s) or not _WM_BULLET.match(s):
                break
            body.append(s)
        txt = _WM_STAMP.sub("", " ".join(body)).strip()
        if txt:
            out[key] = txt if len(txt) <= _WM_FIELD_CAP else txt[:_WM_FIELD_CAP].rstrip() + " ..."
    return out


# ---------------------------------------------------------------- (i) harvest from reasoning
def _wm_wrap_chat(orig):
    def _chat_completion(self, messages, **kw):
        res = orig(self, messages, **kw)
        try:
            msg = getattr(res, "message", None) or {}
            content = _wm_ta._normalize_message_content(msg.get("content", ""))
            reasoning = _wm_ta._extract_reasoning_text(msg)
            if _wm_ta._contains_tool_call_markup(reasoning, content):
                reasoning = _wm_ta._strip_tool_call_markup(reasoning)
                content = _wm_ta._strip_tool_call_markup(content)
            note = _wm_ta._extract_scientist_note(content) if content.strip() else {}
            if not any(note.get(k) for k in _WM_LABELS):
                got = _wm_harvest(reasoning)
                if got:
                    st = _wm_state(self)
                    changed = []
                    for k, v in got.items():
                        if self._summarized_knowledge.get(k) != v:
                            self._summarized_knowledge[k] = v
                            st["_wm_since"][k] = _wm_now(self)
                            changed.append(k)
                            if "retro" in _WM_PARTS:
                                _wm_retro_check(self, k, v)
                    _wm_emit(self, "harvest", fields=sorted(got), changed=changed, action=_wm_now(self))
        except Exception as e:
            _wm_error("harvest", e)
        return res
    _chat_completion._wm_orig = orig          # NOT __wrapped__: cell_breaker reads that as "cell_15c already wrapped it"
    return _chat_completion


# ---------------------------------------------------------------- (iii)/(ii-b) bookkeeping on the stock content writer
def _wm_wrap_from_assistant(orig):
    def _update_summarized_knowledge_from_assistant(self, content):
        before = dict(self._summarized_knowledge)
        orig(self, content)
        try:
            k_now = self._summarized_knowledge
            st = _wm_state(self)
            for key, value in list(k_now.items()):
                if value == before.get(key):
                    continue
                if "stamps" in _WM_PARTS and isinstance(value, str) and _WM_STAMP.search(value):
                    value = _WM_STAMP.sub("", value).strip() or before.get(key, "")   # a copied-back stamp is not content
                    k_now[key] = value
                    if value == before.get(key):
                        continue
                st["_wm_since"][key] = _wm_now(self)
                if "retro" in _WM_PARTS:
                    _wm_retro_check(self, key, value)
        except Exception as e:
            _wm_error("content bookkeeping", e)
    _update_summarized_knowledge_from_assistant.__wrapped__ = orig
    return _update_summarized_knowledge_from_assistant


# ---------------------------------------------------------------- (ii) carry instead of losing at a clear / game over
def _wm_wrap_from_step_summary(orig):
    def _update_summarized_knowledge_from_step_summary(self):
        s = self.__dict__.get("_last_step_summary")
        st = None
        kind = None
        try:
            st = _wm_state(self)
            st["_wm_retro_for"] = None                                   # any executed step ends the post-clear window
            if "carry" in _WM_PARTS and s and not s.get("run_complete") and (s.get("level_transition") or s.get("game_over")):
                kind = "clear" if s.get("level_transition") else "gameover"
                try:
                    lvl_new = int(s.get("level") or 1)
                except (TypeError, ValueError):
                    lvl_new = 1
                lvl = max(1, lvl_new - 1) if kind == "clear" else lvl_new   # the clearing action reports the NEW level
                act = s.get("end_action_num") or _wm_now(self)
                parts, oldest = [], None
                for key, label in _WM_LABELS.items():
                    v = self._summarized_knowledge.get(key, "")
                    if v:
                        parts.append(f"{label}: {v}")
                        since = st["_wm_since"].get(key)
                        if since is not None and (oldest is None or since < oldest):
                            oldest = since
                if not parts and kind == "clear":   # nothing new to carry: an older game-over entry of this level is no longer
                    for e in st["_wm_carried"]:      # "the same level restarted" (review 10-03 wording)
                        if e["kind"] == "gameover" and e["level"] == lvl and e.get("cleared_at") is None:
                            e["cleared_at"] = act
                if parts:
                    text = " | ".join(parts)
                    if len(text) > _WM_CARRY_CAP:
                        text = text[:_WM_CARRY_CAP].rstrip() + " ..."
                    entry = {"level": lvl, "kind": kind, "action": act, "written": oldest, "text": text}
                    st["_wm_carried"] = [e for e in st["_wm_carried"] if not (e["kind"] == "gameover" and e["level"] == lvl)]
                    st["_wm_carried"].insert(0, entry)
                    del st["_wm_carried"][_WM_KEEP:]
                    _wm_emit(self, "carry", level=lvl, kind=kind, action=act, chars=len(text))
        except Exception as e:
            _wm_error("carry", e)
        orig(self)                                                     # stock blanking, unchanged
        try:
            if st is not None and s and (s.get("level_transition") or s.get("run_complete") or s.get("game_over")):
                for key in _WM_BLANKED:
                    if not self._summarized_knowledge.get(key):
                        st["_wm_since"].pop(key, None)
            if kind == "clear" and "retro" in _WM_PARTS:
                st["_wm_retro_for"] = lvl                                # arm: the model's first summary after the clear
        except Exception as e:
            _wm_error("carry bookkeeping", e)
    _update_summarized_knowledge_from_step_summary.__wrapped__ = orig
    return _update_summarized_knowledge_from_step_summary


# ---------------------------------------------------------------- (iv) the level-clear record
def _wm_bbox(node):
    rs = [p[0] for p in node["boundary"]]
    cs = [p[1] for p in node["boundary"]]
    return min(rs), min(cs), max(rs), max(cs)


def _wm_colour_words():
    """glyph -> colour word from the legend line the model is given (empty when the arm ships no legend)."""
    m = _wm_re.search(r"Color legend:\s*([^\n]+)", getattr(_wm_ta, "GAME_OVERVIEW_ADDENDUM", "") or "")
    out = {}
    for pair in (m.group(1).rstrip(".").split(", ") if m else []):
        k, _, v = pair.partition("=")
        if len(k.strip()) == 1 and v.strip():
            out[k.strip()] = v.strip()
    return out


def _wm_changed_objects(pre_grid, first_grid, limit=5, max_px=600):
    """(objects part) objects of the pre-win frame whose (shape, colour) hash is absent from the level's first frame, or
    present but elsewhere; grouped by colour+size+kind. Thin edge bars (meters) are skipped."""
    from inference.utils.segmentation import segment_layer
    import inference.agent.python_tool_sandbox as _sb
    chars = _sb.ARC_COLOR_CHARS                                       # the carrier the model sees (lownorm patches it)
    pre = segment_layer(pre_grid, chars)["nodes"]
    first = segment_layer(first_grid, chars)["nodes"]
    start = {}
    for n in first:
        start.setdefault(n["hash"], set()).add(_wm_bbox(n)[:2])
    H, W = len(pre_grid), (len(pre_grid[0]) if pre_grid else 0)
    groups, unchanged = {}, 0
    for n in pre:
        if n["pixels"] > max_px:
            continue
        r0, c0, r1, c1 = _wm_bbox(n)
        h, w = r1 - r0 + 1, c1 - c0 + 1
        if min(h, w) == 1 and max(h, w) >= 8 and (r0 in (0, H - 1) or c0 in (0, W - 1) or r1 == H - 1 or c1 == W - 1):
            continue
        if (r0, c0) in start.get(n["hash"], ()):
            unchanged += 1
            continue
        how = "moved" if n["hash"] in start else "new/reshaped"
        g = groups.setdefault((n["color"], h, w, how), {"n": 0, "px": n["pixels"], "at": (r0, c0)})
        g["n"] += 1
    ranked = sorted(groups.items(), key=lambda kv: (kv[0][3] != "moved", -kv[1]["px"] * kv[1]["n"]))
    words = _wm_colour_words()
    out = [f"{c}{'(' + words[c] + ')' if c in words else ''} {h}x{w} {how}"
           + (f" x{g['n']}" if g["n"] > 1 else f" @({g['at'][0]},{g['at'][1]})")
           for (c, h, w, how), g in ranked[:limit]]
    return out, unchanged


def _wm_build_record(self, state_path, summary):
    _, hist = _wm_load_state(state_path)
    win = next((i for i in range(len(hist) - 1, 0, -1) if hist[i].frame.level > hist[i - 1].frame.level), None)
    if win is None:
        return
    pre = hist[win - 1].frame
    lvl = pre.level
    j = win - 1
    while j > 0 and hist[j - 1].frame.level == lvl:
        j -= 1
    batch = [a for a in (summary.get("executed_actions") or []) if a]
    act = summary.get("end_action_num") or win
    objs = ""
    if "objects" in _WM_PARTS:
        found, unchanged = _wm_changed_objects(pre.grid, hist[j].frame.grid)
        objs = (" Objects changed during the level: " + ("; ".join(found) if found else "none detected")
                + f" ({unchanged} small objects unchanged).")
    rec = (f"{_WM_RECORD_PREFIX}{lvl} (harness-written, exact): cleared at action {act} by `{hist[win].action}`"
           + (f" (end of the batch {', '.join(batch[-4:])})" if len(batch) > 1 else "")
           + f"; the level took {win - j} actions. Pre-win frame = history[{win - 1}].frame.{objs} "
           + "The solved configuration = pre-win frame + this action; it was never displayed.")
    st = _wm_state(self)
    st["_wm_records"].insert(0, {"level": lvl, "action": act, "by": hist[win].action, "text": rec})
    _wm_emit(self, "record", level=lvl, action=act, chars=len(rec))


def _wm_wrap_dispatch(orig):
    def _dispatch_tool(self, state_path, name, arguments):
        self.__dict__["_wm_stem"] = _wm_re.sub(r"_tool_runtime_state$", "", _wm_os.path.splitext(_wm_os.path.basename(str(state_path)))[0])
        before = self.__dict__.get("_last_step_summary")
        res = orig(self, state_path, name, arguments)
        s = self.__dict__.get("_last_step_summary")
        if s is not None and s is not before and s.get("level_transition") and not s.get("run_complete"):
            try:
                _wm_build_record(self, state_path, s)
            except Exception as e:
                _wm_error("record", e)
        return res
    _dispatch_tool.__wrapped__ = orig
    return _dispatch_tool


# ---------------------------------------------------------------- (iii) stamped rendering + carried entries + records
def _wm_extra_lines(agent):
    """The carry-only lines for the current state, newest first. Their text is STABLE (no running counters): the same
    entry renders the same line on every turn, which is what lets DUCK_WM_HISTORY=dedupe recognise a copy already in
    the history window. The prompt's own "Current state: step N" gives the age of "at action A"."""
    st = _wm_state(agent)
    extra = []
    if "carry" in _WM_PARTS:
        for e in st["_wm_carried"]:
            when = (f"written before its clear at action {e['action']}" if e["kind"] == "clear"
                    else f"written before GAME OVER at action {e['action']}; the same level restarted")
            age = f", oldest part {e['action'] - e['written']} actions older" if e.get("written") is not None else ""
            if e["kind"] == "gameover" and e.get("cleared_at") is not None:   # the level was cleared later without a new model
                when = f"written before GAME OVER at action {e['action']}; L{e['level']} was cleared later, at action {e['cleared_at']}"
            extra.append(f"{_WM_CARRY_PREFIX}{e['level']} ({when}{age}; re-verify on this level before relying on it): {e['text']}")
    if "record" in _WM_PARTS:
        for i, r in enumerate(st["_wm_records"]):
            extra.append(r["text"] if i < _WM_KEEP else f"{_WM_RECORD_PREFIX}{r['level']}: cleared at action {r['action']} by `{r['by']}`.")
    return extra


def _wm_wrap_lines(orig):
    def _summarized_knowledge_lines(self):
        lines = orig(self)
        try:
            st = _wm_state(self)
            now = _wm_now(self)
            omit = self.__dict__.get("_wm_omit") or ()
            extra = [ln for ln in _wm_extra_lines(self) if ln not in omit]
            if not lines:
                return [_WM_HEADER, *extra, _WM_FOOTER] if extra else lines
            if lines[0] != _WM_HEADER or lines[-1] != _WM_FOOTER:
                return lines                                           # not the block the probe saw: leave stock untouched
            body = list(lines[1:-1])
            if "stamps" in _WM_PARTS:
                for i, ln in enumerate(body):
                    for label, key in _WM_RENDER:
                        if ln.startswith(f"- {label}: "):
                            since = st["_wm_since"].get(key)
                            if since is not None and now - since > 0:
                                body[i] = f"- {label} [unchanged for {now - since} actions]: " + ln[len(f"- {label}: "):]
                            break
            return [lines[0], *body, *extra, lines[-1]]
        except Exception as e:
            _wm_error("render", e)
            return lines
    _summarized_knowledge_lines.__wrapped__ = orig
    return _summarized_knowledge_lines


# ---------------------------------------------------------------- (v) carry-only lines live in the newest prompt only
def _wm_strip_old(text):
    if not isinstance(text, str) or (_WM_CARRY_PREFIX not in text and _WM_RECORD_PREFIX not in text):
        return text, 0
    kept = [ln for ln in text.split("\n") if not ln.startswith((_WM_CARRY_PREFIX, _WM_RECORD_PREFIX))]
    n = text.count("\n") + 1 - len(kept)
    # a block that held ONLY carry-only lines collapses to header+footer: drop those two as well
    out = "\n".join(kept)
    if _WM_HEADER and _WM_FOOTER:
        out = out.replace(_WM_HEADER + "\n" + _WM_FOOTER + "\n", "")
    return out, n


def _wm_wrap_analyze(orig):
    def analyze(self, state_path, *a, **k):
        try:
            n = 0
            for m in self.__dict__.get("_history_messages") or []:
                if m.get("role") != "user":
                    continue
                c = m.get("content")
                if isinstance(c, str):
                    m["content"], d = _wm_strip_old(c)
                    n += d
                elif isinstance(c, list):
                    for part in c:
                        if isinstance(part, dict) and isinstance(part.get("text"), str):
                            part["text"], d = _wm_strip_old(part["text"])
                            n += d
            _wm_stats["stripped_lines"] += n
        except Exception as e:
            _wm_error("strip", e)
        return orig(self, state_path, *a, **k)
    analyze.__wrapped__ = orig
    return analyze


# ---------------------------------------------------------------- (v') dedupe: one copy in the window, history never edited
def _wm_texts(content):
    if isinstance(content, str):
        yield content
    elif isinstance(content, list):
        for part in content:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                yield part["text"]


def _wm_has_line(messages, line):
    """`line` is a whole line of some user message in `messages`."""
    for m in messages:
        if isinstance(m, dict) and m.get("role") == "user":
            for t in _wm_texts(m.get("content")):
                if line in t and ("\n" + line + "\n") in ("\n" + t + "\n"):
                    return True
    return False


def _wm_wrap_analyze_dedupe(orig):
    """Before each analyze() call: a carry-only line that is already, word for word, in a user prompt of the history window
    that survives this call's first trim is NOT rendered again (_wm_omit). Survival is decided by running the installed
    trim (the same chain analyze() runs next) on [system, history, a stand-in for the new prompt]; the stand-in is the
    previous analyze prompt + the full new block + 50% of the previous prompt's length as margin, i.e. LARGER than the real
    prompt, so the real trim keeps at least what the simulation kept (it drops oldest-first while over budget). Nothing
    already sent is ever edited, so a game's requests stay pure extensions of each other wherever stock's are (prefix
    cache), and the window holds one copy. A copy that a LATER trim of the same call drops is rendered again on the next
    call. A new session (another runtime dir) is left to analyze()'s own reset."""
    def analyze(self, state_path, *a, **k):
        omit = frozenset()
        try:
            hist = self.__dict__.get("_history_messages") or []
            if hist and self.__dict__.get("_session_runtime_dir") == _wm_Path(state_path).parent:
                lines = _wm_extra_lines(self)
                present = [ln for ln in lines if _wm_has_line(hist, ln)]
                if present:
                    prev = next((t for m in reversed(hist) if isinstance(m, dict) and m.get("role") == "user"
                                 for t in _wm_texts(m.get("content")) if _WM_END_ANCHOR in t), "")
                    block = "\n".join(self._summarized_knowledge_lines())       # _wm_omit is empty here: the FULL new block
                    standin = prev + "\n" + block + "\n" + " " * (len(prev) // 2)
                    self.__dict__["_duck_trim_probe"] = True   # stateful/stat-keeping trims: this is not a real request
                    try:
                        kept = self._trim_messages_for_context(
                            [{"role": "system", "content": self._system_prompt}, *hist, {"role": "user", "content": standin}],
                            tools=self._tools(state_path), preserve_recent=1)
                    finally:
                        self.__dict__.pop("_duck_trim_probe", None)
                    omit = frozenset(ln for ln in present if _wm_has_line(kept[1:-1], ln))
                    _wm_stats["deduped_lines"] += len(omit)
        except Exception as e:
            _wm_error("dedupe", e)
            omit = frozenset()
        self.__dict__["_wm_omit"] = omit
        try:
            return orig(self, state_path, *a, **k)
        finally:
            self.__dict__["_wm_omit"] = frozenset()
    analyze.__wrapped__ = orig
    return analyze


# ---------------------------------------------------------------- off: no block, no demand for one
_WM_OFF_DROP = (
    "Below you are provided with the current world model from the previous turn. The default behavior is to copy it and add or "
    "remove things based on the evidence that you gathered. BEFORE EXECUTING NEW ACTIONS YOU MUST ALWAYS GIVE THE REVISED VERSION OF THE WORLD MODEL.\n",
    "end of world model. \n",
    "If you include assistant text before a tool call, keep it short and use it to update the world model. Helpful optional prefixes are "
    "`World model:`, `Goal model:`, `Action model:`, `Recent findings:`, `Open questions:`, `Plan:`, and `Cross-level notes:`.\n",
)


_WM_OFF_NUDGE = ("If helpful, include short world-model update lines such as `World model:`, `Goal model:`, `Action model:`, "
                 "`Recent findings:`, `Open questions:`, `Plan:`, or `Cross-level notes:`. ")   # tool_agent.py:1918 (follow-up nudge)


def _wm_wrap_chat_off(orig):
    """off: drop the nudge's world-model sentence from every outgoing user message (a pure function of the text, applied
    to every request, so the request sequence stays prefix-consistent; the history keeps Duck's own copy)."""
    def _chat_completion(self, messages, **kw):
        try:
            if any(isinstance(m, dict) and m.get("role") == "user" and isinstance(m.get("content"), str) and _WM_OFF_NUDGE in m["content"]
                   for m in messages or ()):
                messages = [dict(m, content=m["content"].replace(_WM_OFF_NUDGE, "")) if isinstance(m, dict) and m.get("role") == "user"
                            and isinstance(m.get("content"), str) and _WM_OFF_NUDGE in m["content"] else m for m in messages]
        except Exception as e:
            _wm_error("off nudge", e)
        return orig(self, messages, **kw)
    _chat_completion._wm_orig = orig          # NOT __wrapped__ (cell_breaker's check, as the carry wrapper)
    return _chat_completion


def _wm_wrap_prompt_off(orig):
    def _build_user_prompt(self, *a, **k):
        r = orig(self, *a, **k)
        if isinstance(r, str):
            for s in _WM_OFF_DROP:
                r = r.replace(s, "")
        return r
    _build_user_prompt.__wrapped__ = orig
    return _build_user_prompt


# ---------------------------------------------------------------- install
def _wm_probe_agent():
    return _wm_ta.ToolAgent(model="wm-probe", base_url="http://127.0.0.1:9/v1", provider="vllm")


def _wm_check_stock():
    """Behavioural probes of every stock semantic the carry parts rely on; returns a list of problems (empty = OK)."""
    global _WM_HEADER, _WM_FOOTER
    bad = []
    T = _wm_ta.ToolAgent
    a = _wm_probe_agent()
    a._summarized_knowledge["world_model"] = "wm-probe-x"
    ln = T._summarized_knowledge_lines(a)
    if not (isinstance(ln, list) and len(ln) == 3 and ln[1] == "- World model: wm-probe-x"):
        bad.append(f"block renderer shape changed: {ln!r}")
    else:
        _WM_HEADER, _WM_FOOTER = ln[0], ln[-1]
    a._summarized_knowledge = {k: "v" for k in a._summarized_knowledge}
    a._last_step_summary = {"level_transition": True, "game_over": False, "run_complete": False, "level": 2}
    T._update_summarized_knowledge_from_step_summary(a)
    if {k for k, v in a._summarized_knowledge.items() if v} != {"cross_level_notes"}:
        bad.append(f"stock clear-time blanking changed: {a._summarized_knowledge!r}")
    note = _wm_ta._extract_scientist_note("World model: wm-a\nAction model: wm-b")
    if not (note.get("world_model") == "wm-a" and note.get("action_model") == "wm-b"):
        bad.append(f"label extractor changed: {note!r}")
    if "stamps" in _WM_PARTS:
        n2 = _wm_ta._extract_scientist_note("- World model [unchanged for 3 actions]: wm-c")
        if n2.get("world_model") != "wm-c":
            bad.append("stamps need cell_duck_fixes' label fix (a stamped label is not read back): load cell_duck_fixes first")
    return bad


def _wm_install():
    T = _wm_ta.ToolAgent
    if T.__dict__.get("_wm_installed"):
        return f"already installed ({T._wm_installed})"
    if _WM_MODE == "stock":
        return "stock (nothing patched)"
    submission = bool(globals().get("TRUE_SUBMISSION", False))
    if _WM_MODE == "off":
        wrapped = _wm_wrap_prompt_off(T._build_user_prompt)
        try:   # review 10-03: an exception in the probe is a failed probe (fail-open under TRUE_SUBMISSION), not a dead cell
            probe = wrapped(_wm_probe_agent(), 1, valid_actions=["ACTION1"])
            bad = [s.strip()[:40] for s in ("end of world model", "MUST ALWAYS GIVE THE REVISED", "Helpful optional prefixes") if s in probe]
        except Exception as e:
            bad = [f"probe raised {type(e).__name__}: {e}"]
        if bad:
            msg = f"WM off: prompt anchor(s) moved -- the vendored _build_user_prompt changed: {bad}"
            if submission:
                return "NOT INSTALLED: " + msg
            raise RuntimeError(msg)
        try:
            nudge = _WM_OFF_NUDGE in open(_wm_ta.__file__, encoding="utf-8").read()
        except Exception:
            nudge = False
        T._summarized_knowledge_lines = lambda self: []
        T._build_user_prompt = wrapped
        if nudge:
            T._chat_completion = _wm_wrap_chat_off(T._chat_completion)
        T._wm_installed = "off"
        return f"off installed (follow-up nudge sentence {'removed' if nudge else 'not found: left as is'}; log {_WM_LOG or 'none'})"
    try:   # review 10-03: an exception in a probe is a failed probe, like f5's _ldg_install
        bad = _wm_check_stock()
    except Exception as e:
        bad = [f"stock probe raised {type(e).__name__}: {e}"]
    if bad:
        msg = "WM carry: stock harness differs from the one this cell was written against: " + "; ".join(bad)
        if submission:
            return "NOT INSTALLED: " + msg
        raise RuntimeError(msg)
    parts = _WM_PARTS
    if "harvest" in parts:
        T._chat_completion = _wm_wrap_chat(T._chat_completion)
    if parts & {"stamps", "retro", "carry"}:       # per-field "last changed at action" (stamps; carry's "oldest part" age)
        T._update_summarized_knowledge_from_assistant = _wm_wrap_from_assistant(T._update_summarized_knowledge_from_assistant)
    if parts & {"carry", "retro", "stamps"}:
        T._update_summarized_knowledge_from_step_summary = _wm_wrap_from_step_summary(T._update_summarized_knowledge_from_step_summary)
    if "record" in parts:
        T._dispatch_tool = _wm_wrap_dispatch(T._dispatch_tool)
    if parts & {"carry", "record", "stamps"}:
        T._summarized_knowledge_lines = _wm_wrap_lines(T._summarized_knowledge_lines)
    if parts & {"carry", "record"}:
        if _WM_HISTORY == "strip":
            T.analyze = _wm_wrap_analyze(T.analyze)
        elif _WM_HISTORY == "dedupe":
            T.analyze = _wm_wrap_analyze_dedupe(T.analyze)
    T._wm_installed = "carry:" + ",".join(p for p in _WM_ALL_PARTS if p in parts) + (
        f" history={_WM_HISTORY}" if parts & {"carry", "record"} else "")
    _wm_ta._wm_stats = _wm_stats
    return f"{T._wm_installed} installed (log {_WM_LOG or 'none'})"


print(f"WM MODE: {_wm_install()}", flush=True)
