"""Shim fixes for defects in the VENDORED Duck harness.

House rule: /home/ignaz/duck-harness is third-party and stays byte-identical. (kaggle-ok: prose)
Everything here is a monkeypatch installed at run start, the same way
cell_mistral_compat.py and cell_breaker.py work, so the vendored tree can be
re-extracted from the Kaggle bundle at any time without losing these.

Found by the 2026-09-21 defect audit (187 claimed, 186 verified, 121 live).

--------------------------------------------------------------------------
FIX 1 -- the model's labelled reasoning is silently discarded (22% of it)

tool_agent.py:226-260 `_extract_labeled_blocks` matches a label only when the
line begins EXACTLY with "label:" after stripping leading - and *. So the
harness keeps "World model: ..." and throws away

    **World model**: ...          1. World model: ...
    ## World model:               World model (turn 14): ...

Measured on six real transcripts from runs/alpha_games/a2.0: Duck captured 29
"World model" blocks where the model wrote 37 -- 22% discarded, one turn in
five, and that block is the state the agent carries forward.

--------------------------------------------------------------------------
FIX 2 -- a dead game holds its concurrency slot for the entire clock

solver.py:896-904 takes the semaphore for the whole game and never releases it
early, and should_stop() (246-261) has no progress test. On the hidden set that
is decisive: 110 games over 28 slots means a game that will never score keeps a
slot for 2.2h while queued games never start. Findings 49 measured the median
first clear at 23 actions and p90 at 52, and 87% of all actions are spent after
a game stops clearing. A zero-progress kill at K actions costs almost no real
clears and frees the slot.

Default K=120 (over 2x the p90 of 52) -- deliberately conservative, since the
cost of killing a slow-but-live game is a lost level and the cost of keeping a
dead one is only wasted budget. Set DUCK_DEAD_GAME_ACTIONS=0 to disable.
"""
import os as _os
import re as _re

_LOG = []


def _install_label_fix():
    import inference.agent.tool_agent as _ta
    if getattr(_ta, "_cc_label_fix", False):
        return "already installed"
    _orig = _ta._extract_labeled_blocks

    def _patched(content, labels):
        strict = _orig(content, labels)
        # only ADD what the strict pass missed; never overwrite what it found
        pats = {
            lab: _re.compile(
                rf"^(?:[-*#>\s]|\d+[.)])*\**\s*{_re.escape(lab)}\b[^:\n]{{0,48}}:\s*",
                _re.I,
            )
            for lab in labels
        }
        extra = {lab: [] for lab in labels}
        current = None
        for raw in (content or "").splitlines():
            s = raw.strip()
            hit = None
            for lab, rx in pats.items():
                m = rx.match(s)
                if m:
                    hit, rest = lab, s[m.end():].strip()
                    break
            if hit:
                current = hit
                if rest:
                    extra[current].append(rest)
                continue
            if current and s:
                extra[current].append(s)
        out = dict(strict)
        for lab, lines in extra.items():
            if not lines:
                continue
            merged = "\n".join(lines).strip()
            if len(merged) > len(out.get(lab) or ""):
                out[lab] = _ta._normalize_summary_text(merged, max_chars=None)
        return out

    _ta._extract_labeled_blocks = _patched
    _ta._cc_label_fix = True
    return "installed"


def _install_dead_game_kill(k):
    import inference.framework.solver as _sv
    if getattr(_sv, "_cc_dead_kill", False):
        return "already installed"
    _orig = _sv.GameSolver.should_stop if hasattr(_sv, "GameSolver") else None
    holder = None
    for name in dir(_sv):
        obj = getattr(_sv, name)
        if isinstance(obj, type) and hasattr(obj, "should_stop") and hasattr(obj, "action_count"):
            holder = obj
            break
    if holder is None:
        # action_count may be an instance attr; fall back to any class defining should_stop
        for name in dir(_sv):
            obj = getattr(_sv, name)
            if isinstance(obj, type) and "should_stop" in obj.__dict__:
                holder = obj
                break
    if holder is None:
        return "NOT INSTALLED (no class with should_stop found)"
    _orig = holder.should_stop

    def _patched(self):
        if _orig(self):
            return True
        try:
            run = self.game.game_run
            if run is not None and getattr(run, "levels_completed", 0) == 0 \
               and getattr(self, "action_count", 0) >= k:
                if not getattr(self, "_cc_dead_logged", False):
                    self._cc_dead_logged = True
                    print(f"DEAD-GAME KILL: 0 levels after {self.action_count} actions "
                          f"(K={k}); releasing the slot", flush=True)
                return True
        except Exception:
            pass
        return False

    holder.should_stop = _patched
    _sv._cc_dead_kill = True
    _sv._cc_holder = holder
    return f"installed on {holder.__name__} (K={k})"


def _install_level_cap(cap):
    """PER-LEVEL CAP (findings 88b, Investigator: "not games - levels"). Cut the game when the
    CURRENT level has cost more than `cap` actions. On every per-level record on disk
    (150 cleared levels, max cost 158) C=200 loses zero clears and reclaims 28% of the
    actions wasted on levels that never advanced; those long tails are the games that
    hold a hidden-set slot for hours. K (dead-game kill) still covers level 1 tighter.
    Stacks on whatever should_stop is installed already."""
    import inference.framework.solver as _sv
    holder = getattr(_sv, "_cc_holder", None)
    if holder is None:
        for name in dir(_sv):
            obj = getattr(_sv, name)
            if isinstance(obj, type) and "should_stop" in obj.__dict__:
                holder = obj; break
    if holder is None:
        return "NOT INSTALLED (no should_stop holder)"
    _prev = holder.should_stop

    def _capped(self):
        if _prev(self):
            return True
        try:
            run = self.game.game_run
            lv = int(getattr(run, "levels_completed", 0) or 0)
            ac = int(getattr(self, "action_count", 0) or 0)
            if getattr(self, "_cc_lvl_seen", None) != lv:          # level changed (or first call): reset the clock
                self._cc_lvl_seen = lv; self._cc_lvl_start = ac
            if ac - self._cc_lvl_start > cap:
                if not getattr(self, "_cc_cap_logged", False):
                    self._cc_cap_logged = True
                    print(f"LEVEL CAP: level {lv+1} has cost {ac - self._cc_lvl_start} actions (> {cap}); "
                          f"releasing the slot with {lv} level(s) cleared", flush=True)
                return True
        except Exception:
            pass
        return False

    holder.should_stop = _capped
    _sv._cc_level_cap = cap
    return f"installed on {holder.__name__} (C={cap})"


K = int(_os.environ.get("DUCK_DEAD_GAME_ACTIONS", "120"))
_LOG.append(f"label-block fix: {_install_label_fix()}")
_LOG.append(f"dead-game kill: {'disabled (K=0)' if K <= 0 else _install_dead_game_kill(K)}")
CAP = int(_os.environ.get("DUCK_LEVEL_CAP", "200"))
_LOG.append(f"level cap: {'disabled (C=0)' if CAP <= 0 else _install_level_cap(CAP)}")
print("DUCK FIXES -- " + "; ".join(_LOG), flush=True)


# --------------------------------------------------------------------------
# FIX 3 -- ACTION7 reaches the model as a bare token with no class information
#
# tool_agent.py:1222 renders "Valid actions right now: UP, DOWN, LEFT, RIGHT,
# MOUSE, ACTION7." Duck maps 1-5 to UP/DOWN/LEFT/RIGHT/MOUSE, so every other
# entry carries its class -- a direction, or a click needing coordinates.
# ACTION7 is left unmapped, so the one affordance whose behaviour is unknown is
# also the one the model is told least about. It reads as a name, not a control.
#
# Measured: six of our games offer it (ar25, bp35, lf52, sb26, sk48, su15) and
# across every recorded run the model used it ZERO times -- it echoes the list
# back and then reasons only about the actions it understands.
#
# WHAT WE DO NOT DO: say it is "undo". docs.arcprize.org/actions calls it a
# "Simple undo action", but the COMPETITION's own page says "Additional simple
# action" plus "The meaning of actions varies per game -- your agent must figure
# out what each action does through exploration" (the investigator, 2026-09-21). Writing a
# guessed semantic into the prompt is exactly the prior injection arm F
# measured and removed: the ARC-1 lore fired for 15 turns until the benchmark
# name was stripped. A wrong prior is worse than no prior, because the model
# acts on it instead of testing.
#
# So we state only what the ENGINE guarantees -- arcengine GameAction.ACTION7
# .is_simple() is True, .is_complex() is False, verified locally -- and point at
# the test. Set DUCK_DESCRIBE_ACTION7=0 to disable.
if _os.environ.get("DUCK_DESCRIBE_ACTION7", "1") != "0":
    def _install_action7_note():
        import inference.agent.tool_agent as _ta
        if getattr(_ta, "_cc_a7", False):
            return "already installed"
        _orig_fmt = _ta._format_valid_action_line

        def _fmt(valid_actions):
            line = _orig_fmt(valid_actions)
            if "ACTION7" in (line or ""):
                line += (". ACTION7 is a simple action: it takes no coordinates, like the "
                         "direction keys. What it does is specific to this game and is not "
                         "given to you -- take it once and diff the frames to find out")
            return line

        _ta._format_valid_action_line = _fmt
        _ta._cc_a7 = True
        return "installed"

    _LOG.append(f"ACTION7 described: {_install_action7_note()}")
    print("DUCK FIXES -- " + _LOG[-1], flush=True)


# ----------------------------------------------------------------------------------------------
# 09-25, from the Synesthesia v7 smoke transcript (lf52): two more vendored-harness defects.
# (a) ACTION7 is listed as valid but action_names.ENGINE_TO_MODEL_ACTION stops at ACTION6, so
#     to_engine_action("ACTION7") is None and solver raises "Unknown action at index N" -- every
#     attempt in the six games that offer it is a wasted turn (findings 60 made the model try it).
# (b) tool_agent.py json.dumps(..., ensure_ascii=True) echoes the model's own tool-call arguments
#     and rendered values back into the conversation with every non-ASCII glyph as \uXXXX. The
#     model then reasons in code points and mis-maps them (U+D0D3 sky blue read as yellow). Emoji
#     carriers become \U0001F7E5. Fix: the module's `json` name becomes a proxy forcing
#     ensure_ascii=False; the vendored file is untouched.
# ----------------------------------------------------------------------------------------------
def _install_action7_mapping():
    import inference.agent.action_names as _an
    if "ACTION7" not in _an.ENGINE_TO_MODEL_ACTION:
        _an.ENGINE_TO_MODEL_ACTION["ACTION7"] = "ACTION7"
        _an.MODEL_TO_ENGINE_ACTION["ACTION7"] = "ACTION7"
    assert _an.to_engine_action("ACTION7") == "ACTION7" and _an.to_engine_action("action7") == "ACTION7"
    return "ACTION7 mapping: installed"

def _install_unicode_tool_io():
    import json as _json, types as _types
    import inference.agent.tool_agent as _ta
    if getattr(_ta.json, "_kasoti_unicode", False):
        return "unicode tool io: already installed"
    _proxy = _types.SimpleNamespace(**{k: getattr(_json, k) for k in dir(_json) if not k.startswith("__")})
    def _dumps(obj, *a, **kw):
        kw["ensure_ascii"] = False
        return _json.dumps(obj, *a, **kw)
    _proxy.dumps = _dumps; _proxy._kasoti_unicode = True
    _ta.json = _proxy
    assert "겪" in _ta._render_scalar_value({"c": "겪"}) and "\\u" not in _ta._render_scalar_value({"c": "겪"})
    assert "🟥" in _ta._render_tool_parameter_text({"code": "x='🟥'"})
    return "unicode tool io: installed (json.dumps ensure_ascii=False inside tool_agent)"

print("DUCK FIXES (09-25) --", _install_action7_mapping(), "|", _install_unicode_tool_io(), flush=True)


# ----------------------------------------------------------------------------------------------
# UNDO (09-30, findings 141; opt-in DUCK_UNDO=1, default off so v5 is unchanged). Franzen exposes the
# engine's ACTION7 to the model as `UNDO` -- zero cost, no snapshot, no replay -- and reports it "helped
# substantially". His mapping (arc-agi-3-solution, inference/agent/action_names.py):
#     def to_model_action(name):  ... if raw in {"ACTION7", "UNDO"}: ... if mode == "on": return "UNDO"
#     def to_engine_action(name): ... if raw in {"ACTION7", "UNDO"}: return "ACTION7" if undo_exposure_mode() == "on" else None
# and his one prompt line (inference/agent/prompts.py, UNDO_INFO_ADDENDUM, appended when EXPOSE_UNDO=on):
#     "- When available, `UNDO` reverses a previous action, usually the last turn. "
#     "Check what it restores. It cannot recover a failed attempt after game over.\n"
# Engine behaviour measured offline (ar25, su15): after one move ACTION7 returns the board to the pre-move frame
# except the cost-meter cell(s) -- the action counter is NOT undone. FIX 3 above already made ACTION7 executable
# under its own name; this block renames it UNDO for the model and adds the line, in both the prompts module and
# tool_agent/solver, which bind the names at import.
# ----------------------------------------------------------------------------------------------
def _install_undo():
    import inference.agent.action_names as _an, inference.agent.prompts as _pr, inference.agent.tool_agent as _ta
    import inference.framework.solver as _sv
    _an.ENGINE_TO_MODEL_ACTION["ACTION7"] = "UNDO"
    _an.MODEL_TO_ENGINE_ACTION["UNDO"] = "ACTION7"; _an.MODEL_TO_ENGINE_ACTION["ACTION7"] = "ACTION7"
    def to_model_action(name):
        raw = str(name or "").strip().upper()
        return "UNDO" if raw in ("ACTION7", "UNDO") else _an.ENGINE_TO_MODEL_ACTION.get(raw, raw)
    def to_engine_action(name):
        raw = str(name or "").strip().upper()
        if not raw: return None
        if raw in ("ACTION7", "UNDO"): return "ACTION7"
        if raw in _an.ENGINE_TO_MODEL_ACTION: return raw
        return _an.MODEL_TO_ENGINE_ACTION.get(raw)
    def to_model_actions(names):
        out = []
        for n in names:
            lab = to_model_action(n)
            if lab and lab not in out: out.append(lab)
        return out
    _an.to_model_action, _an.to_engine_action, _an.to_model_actions = to_model_action, to_engine_action, to_model_actions
    for mod in (_ta, _sv):
        for fn in ("to_engine_action", "to_model_action", "to_model_actions"):
            if hasattr(mod, fn): setattr(mod, fn, getattr(_an, fn))
    line = ("- When available, `UNDO` reverses a previous action, usually the last turn. "
            "Check what it restores. It cannot recover a failed attempt after game over.\n")
    if "`UNDO`" not in _pr.VISUAL_GAME_ADDENDUM:
        _pr.VISUAL_GAME_ADDENDUM = _pr.VISUAL_GAME_ADDENDUM + line
        if hasattr(_ta, "VISUAL_GAME_ADDENDUM"): _ta.VISUAL_GAME_ADDENDUM = _pr.VISUAL_GAME_ADDENDUM
    assert _an.to_engine_action("UNDO") == "ACTION7" and _an.to_model_action("ACTION7") == "UNDO"
    return "UNDO: installed (ACTION7 <-> UNDO, prompt line added)"

if _os.environ.get("DUCK_UNDO", "0") == "1":
    _LOG.append(_install_undo()); print("DUCK FIXES -- " + _LOG[-1], flush=True)
else:
    print("DUCK FIXES -- UNDO available but off (DUCK_UNDO=1 enables)", flush=True)
