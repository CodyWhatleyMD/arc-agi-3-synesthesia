"""WORLD-MODEL CHANNEL MODES for the Duck harness (10-01 design; scratch prototype, not in the repo).

DUCK_WM_MODE = stock | off | carry      (default stock = this cell installs NOTHING; every ToolAgent method is identical)

Stock channel (tool_agent.py, bundle sha256 535ee88b...):
  :1105 _update_summarized_knowledge_from_assistant(content) -- the ONLY writer; called with `content` only (:1896, :1930).
  :1113 _update_summarized_knowledge_from_step_summary()     -- on level_transition / game_over / run_complete it BLANKS
        world/goal/action model + findings/questions/plan (only cross_level_notes survives).
  :1128 _summarized_knowledge_lines()                        -- renders the block into every user prompt (:1236).
Measured (10-01): author-served Flash-Next wrote non-empty content in 13/2,981 responses -> block in 111/1,202 prompts;
our quant on Kaggle (q25) wrote content in 1,227/2,094 -> block in 1,107/1,592. q25: 38 clears, 16 game-overs, every
game-over reset the SAME level (16/16), and the block was blanked at each.

off   = no carried block; the three user-prompt sentences that demand/label it are removed. History length is NOT
        changed here (CTX / HIST_TURNS build knobs), so off-vs-stock stays one variable.
carry = (i)   no labelled World/Action/Goal model in `content` -> harvest the LAST labelled block of each from `reasoning`
              (sticky until replaced). The unlabelled final paragraph is used only as the clear-time fallback.
        (ii)  on level_completed / game_over, world/action/goal models move to a carried list tagged
              "Carried from L{n} (...; re-verify ...)" instead of being blanked; findings/questions/plan still blank.
        (iii) every rendered field carries "[unchanged for K actions]" / "[updated this turn]".
        (iv)  a harness-written level-clear record: winning action, pre-win history index, objects that changed during
              the level, "The solved configuration = pre-win frame + this action; it was never displayed."
        (v)   carry-only lines are stripped from OLDER user prompts in history (they live in the newest prompt only),
              so yield re-prompts cannot multiply them.
Monkeypatch only; vendored harness byte-identical; shared exec namespace -> every module-level name is _wm_*.
"""
import os as _wm_os, re as _wm_re, json as _wm_json, threading as _wm_threading, time as _wm_time
import inference.agent.tool_agent as _wm_ta

_WM_MODE = (_wm_os.environ.get("DUCK_WM_MODE", "stock") or "stock").strip().lower()
if _WM_MODE not in ("stock", "off", "carry"):
    raise ValueError(f"DUCK_WM_MODE must be stock|off|carry, got {_WM_MODE!r}")
_WM_FIELD_CAP = int(_wm_os.environ.get("DUCK_WM_FIELD_CAP", "900"))      # harvested median 583 chars, p75 933 (author-served)
_WM_CARRY_CAP = int(_wm_os.environ.get("DUCK_WM_CARRY_CAP", "900"))      # per carried entry
_WM_FALLBACK = _wm_os.environ.get("DUCK_WM_FALLBACK", "0") == "1"   # carry the last 3 reasoning lines when nothing labelled exists
_WM_KEEP = 2                                                              # carried entries and full records kept (newest first)
_WM_LOG = _wm_os.environ.get("DUCK_WM_LOG") or _wm_os.path.join(_wm_os.environ.get("SMOKE_JOB_DIR", "."), "wm_mode.jsonl")
_WM_CARRY_PREFIX = "- Carried from L"
_WM_RECORD_PREFIX = "- Level-clear record L"
_wm_log_lock = _wm_threading.Lock()

_WM_LABELS = {"world_model": "World model", "action_model": "Action model", "goal_model": "Goal model"}
_WM_ANY_LABEL = _wm_re.compile(r"^(?:[-*#>\s]|\d+[.)])*\**\s*(?:World model|Goal model|Action model|Recent findings|Open questions|"
                               r"Plan|Cross-level notes|Hypothesis|Next test|History check)\b[^:\n]{0,48}:", _wm_re.I)
_WM_LINE = {k: _wm_re.compile(r"^(?:[-*#>\s]|\d+[.)])*\**\s*" + _wm_re.escape(v) + r"\b[^:\n]{0,48}:\**\s*(.*)$", _wm_re.I)
            for k, v in _WM_LABELS.items()}
_WM_RETRO = _wm_re.compile(r"\b(?:solved|solution|completed?|cleared|won|win|winning)\b", _wm_re.I)   # 16 of the 25 first post-clear models in q25
_WM_BULLET = _wm_re.compile(r"^(?:[-*\u2022]\s|\d+[.)]\s)")
_WM_STAMP = _wm_re.compile(r"\[(?:unchanged for|updated)[^\]]*\]\s*", _wm_re.I)


def _wm_emit(agent, event, **kw):
    try:
        row = {"t": round(_wm_time.time(), 1), "stem": agent.__dict__.get("_wm_stem"), "mode": _WM_MODE, "event": event, **kw}
        with _wm_log_lock, open(_WM_LOG, "a", encoding="utf-8") as fh:
            fh.write(_wm_json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _wm_now(agent):
    try:
        return int((agent.__dict__.get("_last_action_result") or {}).get("action_num") or 0)
    except (TypeError, ValueError):
        return 0


def _wm_state(agent):
    d = agent.__dict__
    if "_wm_since" not in d:
        d["_wm_since"] = {}; d["_wm_carried"] = []; d["_wm_records"] = []; d["_wm_last_para"] = ""; d["_wm_retro_for"] = None
    return d


def _wm_set(agent, key, value):
    value = _WM_STAMP.sub("", str(value or "")).strip()
    if not value:
        return False
    if len(value) > _WM_FIELD_CAP:
        value = value[:_WM_FIELD_CAP].rstrip() + " ..."
    st = _wm_state(agent)
    lvl = st.get("_wm_retro_for")
    if lvl is not None and key in _WM_LABELS:                       # (ii-b) first labelled model after a clear, before the next action
        st["_wm_retro_for"] = None
        if _WM_RETRO.search(value):
            for e in st["_wm_carried"]:
                if e["kind"] == "clear" and e["level"] == lvl:
                    e["text"] = (e["text"] + " | Your own summary right after the clear: " + value[:_WM_CARRY_CAP])[: 2 * _WM_CARRY_CAP]
                    break
            else:
                st["_wm_carried"].insert(0, {"level": lvl, "kind": "clear", "action": _wm_now(agent), "written": None,
                                             "text": "Your own summary right after the clear: " + value[:_WM_CARRY_CAP]})
                del st["_wm_carried"][_WM_KEEP:]
            _wm_emit(agent, "retro", level=lvl, chars=len(value))
    if agent._summarized_knowledge.get(key) != value:
        agent._summarized_knowledge[key] = value
        st["_wm_since"][key] = _wm_now(agent)
        return True
    return False


def _wm_harvest(reasoning):
    """LAST labelled block of each of World/Action/Goal model in `reasoning`: the label line's tail plus following lines
    until a blank line or the next label (an earlier draft in the same reasoning is superseded by the later one)."""
    lines = (reasoning or "").splitlines(); out = {}
    for key, rx in _WM_LINE.items():
        last = None
        for i, ln in enumerate(lines):
            if rx.match(ln.strip()):
                last = i
        if last is None:
            continue
        head = rx.match(lines[last].strip()).group(1).strip()
        body = [head] if head else []
        for ln in lines[last + 1:]:                               # Duck strips blank lines (:866), so a block ends at
            s = ln.strip()                                          # the first line that is not a bullet ("Let me ...")
            if not s or _WM_ANY_LABEL.match(s) or not _WM_BULLET.match(s):
                break
            body.append(s)
        txt = " ".join(body).strip()
        if txt:
            out[key] = txt
    return out


def _wm_last_paragraph(reasoning, cap=400):
    lines = [ln.strip() for ln in (reasoning or "").splitlines() if ln.strip()]
    return " / ".join(lines[-3:])[-cap:] if lines else ""


# ------------------------------------------------------------------ carry (i): harvest from reasoning
def _wm_wrap_chat(orig):
    def _chat_completion(self, messages, **kw):
        res = orig(self, messages, **kw)
        try:
            msg = getattr(res, "message", None) or {}
            content = _wm_ta._normalize_message_content(msg.get("content", ""))
            reasoning = _wm_ta._extract_reasoning_text(msg)
            if _wm_ta._contains_tool_call_markup(reasoning, content):
                reasoning = _wm_ta._strip_tool_call_markup(reasoning); content = _wm_ta._strip_tool_call_markup(content)
            st = _wm_state(self)
            para = _wm_last_paragraph(reasoning)
            if para:
                st["_wm_last_para"] = para
            note = _wm_ta._extract_scientist_note(content) if content.strip() else {}
            if not any(note.get(k) for k in _WM_LABELS):
                got = _wm_harvest(reasoning)
                changed = [k for k, v in got.items() if _wm_set(self, k, v)]
                if got:
                    _wm_emit(self, "harvest", fields=sorted(got), changed=changed, action=_wm_now(self))
        except Exception as e:
            print(f"WM: harvest skipped ({type(e).__name__}: {e})", flush=True)
        return res
    _chat_completion.__wrapped__ = orig
    return _chat_completion


def _wm_update_from_assistant(self, content):
    """Stock semantics (labelled fields overwrite) + a stamp when a field changes; echoed stamps are stripped."""
    note = _wm_ta._extract_scientist_note(content)
    if not note:
        return
    for key, value in note.items():
        if value:
            _wm_set(self, key, value)


# ------------------------------------------------------------------ carry (ii): carry instead of blanking
def _wm_update_from_step_summary(self):
    s = self.__dict__.get("_last_step_summary")
    st = _wm_state(self)
    st["_wm_retro_for"] = None                                       # any executed step ends the post-clear capture window
    if not s or not (s.get("level_transition") or s.get("run_complete") or s.get("game_over")):
        return
    kind = "clear" if s.get("level_transition") else ("gameover" if s.get("game_over") else "complete")
    if kind != "complete":
        try:
            lvl_new = int(s.get("level") or 1)
        except (TypeError, ValueError):
            lvl_new = 1
        lvl = max(1, lvl_new - 1) if kind == "clear" else lvl_new
        act = s.get("end_action_num") or _wm_now(self)
        parts, oldest = [], None
        for key, label in _WM_LABELS.items():
            v = self._summarized_knowledge.get(key, "")
            if v:
                parts.append(f"{label}: {v}")
                since = st["_wm_since"].get(key)
                if since is not None and (oldest is None or since < oldest):
                    oldest = since
        src = "labelled"
        if not parts and _WM_FALLBACK and st.get("_wm_last_para"):   # off by default: see the design note on the fallback
            parts.append(f"(unlabelled excerpt of your last reasoning) {st['_wm_last_para']}"); src = "fallback"
        if parts:
            text = " | ".join(parts)
            if len(text) > _WM_CARRY_CAP:
                text = text[:_WM_CARRY_CAP].rstrip() + " ..."
            entry = {"level": lvl, "kind": kind, "action": act, "written": oldest, "text": text}
            st["_wm_carried"] = [e for e in st["_wm_carried"] if not (e["kind"] == "gameover" and e["level"] == lvl)]
            st["_wm_carried"].insert(0, entry); del st["_wm_carried"][_WM_KEEP:]
            _wm_emit(self, "carry", level=lvl, kind=kind, action=act, chars=len(text), source=src)
        if kind == "clear":
            st["_wm_retro_for"] = lvl                                   # arm: the model's first summary after the clear
    for key in ("world_model", "goal_model", "action_model", "recent_findings", "open_questions", "current_plan"):
        self._summarized_knowledge[key] = ""
        st["_wm_since"].pop(key, None)


# ------------------------------------------------------------------ carry (iv): the level-clear record
def _wm_bbox(node):
    rs = [p[0] for p in node["boundary"]]; cs = [p[1] for p in node["boundary"]]
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
    """Objects of the pre-win frame whose (shape, colour) hash is absent from the level's first frame, or present but
    elsewhere; grouped by colour+size+kind so 40 moved pixels read as one item. Thin edge bars (meters) are skipped."""
    from inference.utils.segmentation import segment_layer
    import inference.agent.python_tool_sandbox as _sb
    chars = _sb.ARC_COLOR_CHARS                                     # the carrier the model sees (lownorm patches it)
    pre = segment_layer(pre_grid, chars)["nodes"]; first = segment_layer(first_grid, chars)["nodes"]
    start = {}
    for n in first:
        start.setdefault(n["hash"], set()).add(_wm_bbox(n)[:2])
    H, W = len(pre_grid), (len(pre_grid[0]) if pre_grid else 0)
    groups, unchanged = {}, 0
    for n in pre:
        if n["pixels"] > max_px:
            continue
        r0, c0, r1, c1 = _wm_bbox(n); h, w = r1 - r0 + 1, c1 - c0 + 1
        if min(h, w) == 1 and max(h, w) >= 8 and (r0 in (0, H - 1) or c0 in (0, W - 1) or r1 == H - 1 or c1 == W - 1):
            continue
        if (r0, c0) in start.get(n["hash"], ()):
            unchanged += 1; continue
        how = "moved" if n["hash"] in start else "new/reshaped"
        g = groups.setdefault((n["color"], h, w, how), {"n": 0, "px": n["pixels"], "at": (r0, c0)})
        g["n"] += 1
    ranked = sorted(groups.items(), key=lambda kv: (kv[0][3] != "moved", -kv[1]["px"] * kv[1]["n"]))   # moved pieces first
    words = _wm_colour_words()
    out = [f"{c}{'(' + words[c] + ')' if c in words else ''} {h}x{w} {how}" + (f" x{g['n']}" if g["n"] > 1 else f" @({g['at'][0]},{g['at'][1]})")
           for (c, h, w, how), g in ranked[:limit]]
    return out, unchanged


def _wm_build_record(self, state_path, summary):
    frame, hist = _wm_ta.load_runtime_state(state_path)
    win = next((i for i in range(len(hist) - 1, 0, -1) if hist[i].frame.level > hist[i - 1].frame.level), None)
    if win is None:
        return
    pre = hist[win - 1].frame; lvl = pre.level
    j = win - 1
    while j > 0 and hist[j - 1].frame.level == lvl:
        j -= 1
    objs, unchanged = _wm_changed_objects(pre.grid, hist[j].frame.grid)
    batch = [a for a in (summary.get("executed_actions") or []) if a]
    act = summary.get("end_action_num") or win
    rec = (f"{_WM_RECORD_PREFIX}{lvl} (harness-written, exact): cleared at action {act} by `{hist[win].action}`"
           + (f" (end of the batch {', '.join(batch[-4:])})" if len(batch) > 1 else "")
           + f"; the level took {win - j} actions. Pre-win frame = history[{win - 1}].frame. Objects changed during the level: "
           + ("; ".join(objs) if objs else "none detected") + f" ({unchanged} small objects unchanged). "
           + "The solved configuration = pre-win frame + this action; it was never displayed.")
    st = _wm_state(self)
    st["_wm_records"].insert(0, {"level": lvl, "action": act, "by": hist[win].action, "text": rec})
    _wm_emit(self, "record", level=lvl, action=act, chars=len(rec), objects=len(objs))


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
                print(f"WM: record skipped ({type(e).__name__}: {e})", flush=True)
        return res
    _dispatch_tool.__wrapped__ = orig
    return _dispatch_tool


# ------------------------------------------------------------------ carry (iii): stamped rendering + carried + records
def _wm_lines_carry(self):
    st = _wm_state(self); now = _wm_now(self); k = self._summarized_knowledge
    def stamp(key):
        since = st["_wm_since"].get(key)
        if since is None:
            return ""
        return "" if now - since <= 0 else f" [unchanged for {now - since} actions]"
    entries = [("World model", "world_model"), ("Goal model", "goal_model"), ("Action model", "action_model"),
               ("Recent findings", "recent_findings"), ("Open questions", "open_questions"), ("Plan", "current_plan"),
               ("Cross-level notes", "cross_level_notes")]
    lines = [f"- {label}{stamp(key)}: {k.get(key)}" for label, key in entries if k.get(key)]
    for e in st["_wm_carried"]:
        when = (f"written before its clear at action {e['action']}" if e["kind"] == "clear"
                else f"written before GAME OVER at action {e['action']}; the same level restarted")
        age = f", oldest part {e['action'] - e['written']} actions older" if e.get("written") is not None else ""
        lines.append(f"{_WM_CARRY_PREFIX}{e['level']} ({when}{age}, carried {max(0, now - e['action'])} actions; "
                     f"re-verify on this level before relying on it): {e['text']}")
    for i, r in enumerate(st["_wm_records"]):
        lines.append(r["text"] if i < _WM_KEEP else f"{_WM_RECORD_PREFIX}{r['level']}: cleared at action {r['action']} by `{r['by']}`.")
    if not lines:
        return []
    return ["Working world model carried from earlier turns:", *lines,
            "- Revise any item above immediately if `current_frame` or `history` contradicts it."]


# ------------------------------------------------------------------ carry (v): carry-only lines live in the newest prompt only
def _wm_strip_old(text):
    if not isinstance(text, str) or (_WM_CARRY_PREFIX not in text and _WM_RECORD_PREFIX not in text):
        return text
    return "\n".join(ln for ln in text.split("\n") if not ln.startswith((_WM_CARRY_PREFIX, _WM_RECORD_PREFIX)))


def _wm_wrap_analyze(orig):
    def analyze(self, state_path, *a, **k):
        try:
            for m in self.__dict__.get("_history_messages") or []:
                if m.get("role") != "user":
                    continue
                c = m.get("content")
                if isinstance(c, str):
                    m["content"] = _wm_strip_old(c)
                elif isinstance(c, list):
                    for part in c:
                        if isinstance(part, dict) and isinstance(part.get("text"), str):
                            part["text"] = _wm_strip_old(part["text"])
        except Exception as e:
            print(f"WM: strip skipped ({type(e).__name__}: {e})", flush=True)
        return orig(self, state_path, *a, **k)
    analyze.__wrapped__ = orig
    return analyze


# ------------------------------------------------------------------ off: no block, no demand for one
_WM_OFF_DROP = (
    "Below you are provided with the current world model from the previous turn. The default behavior is to copy it and add or "
    "remove things based on the evidence that you gathered. BEFORE EXECUTING NEW ACTIONS YOU MUST ALWAYS GIVE THE REVISED VERSION OF THE WORLD MODEL.\n",
    "end of world model. \n",
    "If you include assistant text before a tool call, keep it short and use it to update the world model. Helpful optional prefixes are "
    "`World model:`, `Goal model:`, `Action model:`, `Recent findings:`, `Open questions:`, `Plan:`, and `Cross-level notes:`.\n",
)


def _wm_wrap_prompt_off(orig):
    def _build_user_prompt(self, *a, **k):
        r = orig(self, *a, **k)
        if isinstance(r, str):
            for s in _WM_OFF_DROP:
                r = r.replace(s, "")
        return r
    _build_user_prompt.__wrapped__ = orig
    return _build_user_prompt


def _wm_install():
    T = _wm_ta.ToolAgent
    if T.__dict__.get("_wm_installed"):
        return f"already installed ({T._wm_installed})"
    if _WM_MODE == "stock":
        return "stock (nothing patched)"
    if _WM_MODE == "off":
        T._summarized_knowledge_lines = lambda self: []
        T._build_user_prompt = _wm_wrap_prompt_off(T._build_user_prompt)
        probe = T(model="wm-probe", base_url="http://127.0.0.1:9/v1", provider="vllm")._build_user_prompt(1, valid_actions=["ACTION1"])
        assert "end of world model" not in probe and "MUST ALWAYS GIVE THE REVISED" not in probe and "Helpful optional prefixes" not in probe, \
            "WM off: a prompt anchor moved -- the vendored _build_user_prompt changed"
    else:
        T._chat_completion = _wm_wrap_chat(T._chat_completion)
        T._update_summarized_knowledge_from_assistant = _wm_update_from_assistant
        T._update_summarized_knowledge_from_step_summary = _wm_update_from_step_summary
        T._summarized_knowledge_lines = _wm_lines_carry
        T._dispatch_tool = _wm_wrap_dispatch(T._dispatch_tool)
        T.analyze = _wm_wrap_analyze(T.analyze)
    T._wm_installed = _WM_MODE
    return f"{_WM_MODE} installed (log {_WM_LOG})"


print(f"WM MODE: {_wm_install()}", flush=True)
