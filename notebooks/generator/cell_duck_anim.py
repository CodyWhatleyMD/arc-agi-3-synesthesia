"""ANIMATION FRAMES (comparison #7, 10-02). Opt-in DUCK_ANIM=1; unset or 0: this cell changes NOTHING (it only defines
_anim_* functions; no harness attribute is touched and nothing is printed except the one "off" line).

Why. The engine returns 1-N frames per action and Duck keeps only the last (taaf game.py:170 GameState.frame =
raw.frame[-1]; solver.py:93 _grid_from_state; game.py:173 animation_frames is never read). Replaying the recorded actions
of q25 (Kaggle 09-30, v5 config; 2,923 actions, every board equal to the recording) through arcengine:
  - 'hidden' (126 actions, 4.3%): the board inside the 4-cell HUD border is UNCHANGED while cells changed and changed
    back during the action -- sp80 SPACE (the pour: 448 cells over 22 frames; q25/v10: "SPACE caused only HUD
    change"), tn36/ft09/s5i5/r11l/su15/dc22 clicks, cd82 SPACE, bp35, ls20, sc25, lf52. The frames show what played; they
    do NOT show that the game changed: replaying each one from its recorded prefix (review 10-03), 105/126 changed no
    later outcome of any action (cd82 SPACE, s5i5, ft09, tn36, sp80 SPACE, ls20 wall bumps); bp35 (8/8) and some
    lf52/r11l/su15/sc25 did change hidden state.
  - 'outside' (101, 3.5%): cells away from the area the action finally changed on the board changed and changed back (su15
    pulse ring, cd82 stamp, sb26 SPACE, sc25/lf52 clicks, tu93, sk48).
  - 'level' (38 wins): the board the winning move produced is never displayed (the next prompt shows the new level; findings
    153 "win credit"). 2-frame wins (most games): frames[0] IS that board. Longer wins (tr87 22-51 states, sb26 59, lf52
    22, r11l 12, g50t 8, tu93 7-14, cd82 14-16, su15 4): the move's own animation and/or a win effect follow, so no single
    frame is "the solved board" -- the pointer names frames[:-1] and says so. A run_complete win with 1 frame shows its
    final board already and gets nothing.
Franzen's public WRITEUP.md, "Animations" section: the deduplicated frames + a compact timeline exposed in the
REPL was "the strongest benefit" of his perception changes; he hints only when the animation has "transient pixels"
(changed more than once from start to final frame); composite animation images HURT some games and automatic timeline
insertion showed no clear gain. So this cell sends NO frames and no timeline into the prompt. Its hint criterion is
NARROWER than his: transient pixels only inside the finally changed area ('trail', a moving object's path: 293 q25
actions, g50t/tu93/sk48/bp35/lf52/sb26) or only in the HUD border stay silent (frames still available via animation()).

What the model gets (DUCK_ANIM=1):
  1. python tool description (+1 sentence, constant): `animation(n=None)` and what it returns. (Review 10-03: the first
     version also said "an action that animated is not a no-op"; replaying every 'hidden' action from the recorded prefix
     showed that 105/126 (q25) and 102/130 (B) of them changed NOTHING in the game -- cd82 SPACE 33/33, s5i5 clicks 16/16,
     ft09 8/8, tn36, sp80 SPACE, ls20 wall bumps -- so the cell no longer claims it, in the doc, the line or the note.)
  2. `animation(n=None)` inside the sandbox -> {'action','action_num','kind','explain','before','frames','timeline',
     'level'}: FrameViews (same class as current_frame: .ascii/.segmentation/.shape) of every DISTINCT state action n
     passed through (runs of identical frames collapsed; frames[-1] = the board after it; after a level win frames[:-1]
     = the old level after the move) plus a compact per-frame change list. Fetched on call over the sandbox pipe (a
     reserved action message the host answers without stepping the engine), so nothing is transferred unless the model
     asks and the data is always current, also right after an action() inside the same snippet. The newest
     DUCK_ANIM_KEEP (8) animated actions of a game keep their frames.
  3. ONLY for an action whose frames hid something (kinds below), a short note in that action's result
     (last_action_result['animation']) and ONE line in the next user prompt, right after "Executed actions: ...".
       hidden  : final board unchanged inside the 4-cell border, but interior cells changed and changed back
       outside : interior cells away from (bbox+1 of) the final INTERIOR change changed and changed back
       level   : the action completed a level -> pointer to the never-shown old-level frames (2 frames: frames[0])
     Silent kinds (frames still available through animation()): motion (every cell changed at most once: the final board
     shows it all), trail (changed-and-back cells only inside the finally changed area: something moved through them),
     hud (only border cells flickered), reshape. RESET (model or auto) is never recorded, so the fatal action's frames
     survive the auto-reset.
Cost per request (served model's tokenizer + chat template; tests/cmp_fixes/f7-anim/measure_cost.py -> cost_f7.json):
  THE COST IS THE GROSS FIGURE = the cell's tokens the model reads in each request: the doc sentence on every request + one
  line per firing action still in the window (+ its note in a displayed tool result); see cost_f7.json for the numbers of
  the current text (review 10-03 rewording: the doc sentence lost its 17-token "not a no-op" claim, 67 -> 50). The "net" P(anim) -
  P(off) through the real analyze() + shipped 32k trim is near 0 only because once the window is full the trim drops
  older history to make room (-0.08 assistant messages per window): history displaced, not a saving. On dense-turn
  replays (scripted model, ~14 user turns in the window vs ~7 on Kaggle) the gross reached su15 mean +383, cd82 +539.

Mechanism (monkeypatch only; the vendored harness is never edited):
  - inference.framework.solver._HarnessGameSession._execute_action: pre-board + engine frames -> one record per action
    (numpy; ~1 ms); step_env: one note per action() call (the most informative of its actions); play (and every action)
    links the session onto its analyzer (agent._anim_sess), which is how the agent-side wrappers find the records -- NOT
    through agent._step_env_callback.__self__, which another shim's wrapped step_env (f5-ledger) hides.
  - ToolAgent._compact_action_result carries the note; ToolAgent._build_user_prompt inserts the line.
  - ToolAgent._run_python_tool (outermost wrapper) marks the calling agent in a thread-local; tool_agent's module-global
    run_sandboxed_python is wrapped: it prepends a small preamble (one top-level try block: it cannot raise; it sits
    BELOW the natives layer, so their def-harvest, which reads only the model's code, never sees it) that defines
    animation(), answers its reserved message, strips the reserved replies from action_results, and shifts traceback
    line numbers back by the preamble's length (frames inside the preamble are dropped), so the model's numbering is
    exactly what it is without this cell. A snippet with a __future__ import that would stop compiling behind the
    preamble runs without it.
  - _PYTHON_TOOL_DESCRIPTION (module global, read at call time) gets the doc sentence once.
Fail-open: any exception in a wrapper is logged once per site and the unpatched result is returned (review 10-03: also
the session lookups at the top of step_env and run_sandboxed_python, which used to sit outside the try); the install reads
every name it needs before the first patch, so a drifted harness gets nothing installed (TRUE_SUBMISSION: print and ship
stock; otherwise raise). Shared exec namespace (findings 79): every module-level name here is _anim_* / _ANIM_*. Load
AFTER cell_duck_natives / the arm cell / breaker / recall (it wraps whatever _run_python_tool is installed). Composes with
f1-effects / f2-wm / f5-ledger / f6-sandbox all on (tests/cmp_fixes/f7-anim/test_compose.py).
Optional: DUCK_ANIM_LOG=<path> appends one JSON line per prompt line emitted ({"game", "range": [lo, hi], "line"}).
DUCK_ANIM_KEEP: a malformed value falls back to 8 (never raises at exec).
Known limits: a top-level `animation` the model defines itself is persisted by the natives and shadows the harness's for
the rest of the game (as any natives name would); animation() with no argument returns the latest action that ANIMATED,
which can be older than the latest action (its 'action_num' says which); traceback line numbers are shifted back only in
the indented frame lines of the sandbox's traceback (never inside the exception message).
"""
import os as _anim_os

_ANIM_ON = (_anim_os.environ.get("DUCK_ANIM", "0") or "0").strip() == "1"
_ANIM_BORDER = 4          # HUD border, same width as Franzen's ARC3_NOOP_GUARD_BORDER and the effects digest
_ANIM_MARGIN = 1          # "outside" = beyond the final change's bbox grown by this many cells
try:   # animated actions per game whose frames are kept; a malformed value must not raise at exec (review 10-03)
    _ANIM_KEEP = max(1, int((_anim_os.environ.get("DUCK_ANIM_KEEP", "8") or "8").strip()))
except ValueError:
    _ANIM_KEEP = 8
_ANIM_MAX_FRAMES = 96     # distinct states sent by one animation() call (sb26 verify: 59)
_ANIM_TIMELINE = 30       # timeline entries (first 15 + last 15 beyond that)
_ANIM_MARK = "__duck_animation__"
_ANIM_FIRES = ("level", "hidden", "outside")
_ANIM_EXPLAIN = {
    "hidden": "the board after this action looks unchanged inside the 4-cell border, but cells changed and changed back while it played",
    "outside": "cells outside the area this action finally changed changed and changed back while it played",
    "level": ("this action completed a level: frames[:-1] are the old level after the move (never shown; with 2 frames "
              "frames[0] is the board as solved), frames[-1] is the next level"),
    "trail": "cells changed and changed back only inside the area the action finally changed (something moved through them)",
    "motion": "every cell changed at most once: the final board shows the whole effect",
    "hud": "only cells in the 4-cell border changed and changed back",
    "reshape": "the frame shape changed while it played",
}
_ANIM_DOC = (" `animation(n=None)` -> the frames action n played (default: the latest that animated): dict with 'kind', "
             "'before', 'frames' (views like current_frame; frames[-1] = the board after it) and 'timeline'.")
# The sandbox preamble. ONE top-level try block (natives harvest only top-level def/class), no class statement (the
# sandbox has no __build_class__), no import. `action` is the bootstrap's own function here (the preamble runs first),
# so its __globals__ are the bootstrap module's: _send/_recv are the pipe, _frame_from_payload builds a FrameView.
_ANIM_PREAMBLE = (
    "try:  # harness: animation(n) -- DUCK_ANIM (cell_duck_anim.py)\n"
    "    def animation(n=None, _g=action.__globals__):\n"
    "        try:\n"
    "            _g['_send']({'type': 'action', 'actions': [{'action': '" + _ANIM_MARK + "', 'n': n}]})\n"
    "            _r = _g['_recv']() or {}\n"
    "            if _r.get('type') != 'action_result':\n"
    "                return {'error': str(_r.get('error') or 'animation() failed in the sandbox host')}\n"
    "            _d = dict((_r.get('state') or {}).get('duck_animation') or {})\n"
    "            _f = _g['_frame_from_payload']\n"
    "            if isinstance(_d.get('before'), dict): _d['before'] = _f(_d['before'])\n"
    "            if isinstance(_d.get('frames'), list): _d['frames'] = [_f(_x) for _x in _d['frames']]\n"
    "            return _d\n"
    "        except Exception as _e:\n"
    "            return {'error': 'animation() failed: ' + str(_e)[:200]}\n"
    "except Exception:\n"
    "    pass\n"
)
_ANIM_PRE_LINES = _ANIM_PREAMBLE.count("\n")
_anim_errors = {}


def _anim_err(where, exc):
    if where not in _anim_errors:
        print(f"ANIMATION: {where} failed ({type(exc).__name__}: {exc}); falling back to the unpatched behaviour", flush=True)
    _anim_errors[where] = _anim_errors.get(where, 0) + 1


# ------------------------------------------------------------------------------------------------ pure analysis (host)
def _anim_chain(pre, frames):
    """The pre-action board, then each DISTINCT state the action passed through (runs of identical frames collapsed;
    non-adjacent repeats stay). Prepending the pre-board is what makes X -> Y -> X register as changed-and-back."""
    import numpy as np
    out = [np.asarray(pre, dtype=np.int8)]
    for f in frames or ():
        a = np.asarray(f, dtype=np.int8)
        if a.shape == out[-1].shape and np.array_equal(a, out[-1]):
            continue
        out.append(a)
    return out


def _anim_classify(chain, won=False, border=_ANIM_BORDER, margin=_ANIM_MARGIN):
    """-> {'kind', 'states', and for hidden/outside: 'cells', 'bbox' (r0,c0,r1,c1), 'census' [((old,new), n)], 'span'}."""
    import numpy as np
    S = len(chain) - 1
    if S < 2:
        return {"kind": None, "states": S}
    if won:
        return {"kind": "level", "states": S}
    if len({c.shape for c in chain}) > 1:
        return {"kind": "reshape", "states": S}
    A = np.stack(chain)
    T = (A[1:] != A[:-1]).sum(axis=0) >= 2          # changed at least twice along pre -> frames = changed and changed back
    if not T.any():
        return {"kind": "motion", "states": S}
    H, W = T.shape
    inner = np.zeros_like(T)
    inner[border:H - border, border:W - border] = True
    net = A[0] != A[-1]
    if not (net & inner).any():
        rep = T & inner
        if not rep.any():
            return {"kind": "hud", "states": S}
        kind = "hidden"
    else:
        rs, cs = np.nonzero(net & inner)              # the area the action changed ON THE BOARD (a HUD tick is no area)
        box = np.zeros_like(T)
        box[max(0, rs.min() - margin):rs.max() + margin + 1, max(0, cs.min() - margin):cs.max() + margin + 1] = True
        rep = T & inner & ~box
        if not rep.any():
            return {"kind": "trail", "states": S}
        kind = "outside"
    rs, cs = np.nonzero(rep)
    vals = A[:, rs, cs]                               # (S+1, n): each reported cell through the chain
    m = vals != vals[0][None, :]
    first = vals[np.argmax(m, axis=0), np.arange(len(rs))]   # the first colour it showed that it did not start with
    pairs = {}
    for a, b in zip(vals[0].tolist(), first.tolist()):
        pairs[(a, b)] = pairs.get((a, b), 0) + 1
    steps = np.nonzero(m.any(axis=1))[0]
    return {"kind": kind, "states": S, "cells": int(len(rs)),
            "bbox": (int(rs.min()), int(cs.min()), int(rs.max()), int(cs.max())),
            "census": sorted(pairs.items(), key=lambda kv: (-kv[1], kv[0])), "span": (int(steps.min()), int(steps.max()))}


def _anim_chars():
    try:
        import inference.utils.grid_utils as gu   # the LIVE carrier (the glyph cell rebinds it)
        return gu.ARC_COLOR_CHARS
    except Exception:
        return "0123456789abcdef"


def _anim_ch(v, chars):
    return chars[v] if 0 <= v < len(chars) else str(v)


def _anim_where(b):
    r0, c0, r1, c1 = b
    return (f"row {r0}" if r0 == r1 else f"rows {r0}-{r1}") + ", " + (f"col {c0}" if c0 == c1 else f"cols {c0}-{c1}")


def _anim_census(rec, chars, k=2):
    return ", ".join(f"{_anim_ch(a, chars)}>{_anim_ch(b, chars)} {n}" for (a, b), n in (rec.get("census") or [])[:k])


def _anim_note(rec, chars=None):
    """The note on the action result (only for the firing kinds), else None."""
    if not rec or rec.get("kind") not in _ANIM_FIRES:
        return None
    n = rec.get("n")
    if rec["kind"] == "level":
        if rec["states"] == 2:
            return f"2 frames; animation({n})['frames'][0] is the board as solved (never shown)"
        return f"{rec['states']} frames; animation({n})['frames'][:-1] = the old level after this move (never shown)"
    cells = rec.get("cells", 0)
    if rec["kind"] == "hidden":
        return f"{rec['states']} frames; {cells} cells changed and changed back; animation({n})"
    return f"{rec['states']} frames; {cells} cells outside the final change changed and changed back; animation({n})"


def _anim_pick(recs):
    """The most informative firing record (level > hidden > outside; the latest within a kind)."""
    rank = {"level": 3, "hidden": 2, "outside": 1}
    fire = [r for r in recs if r and r.get("kind") in rank]
    return max(fire, key=lambda r: (rank[r["kind"]], r.get("n") or 0)) if fire else None


def _anim_line(recs, chars=None):
    """ONE prompt line for the actions of the previous sequence, or None when none of them hid anything."""
    best = _anim_pick(recs)
    if best is None:
        return None
    chars = chars if chars is not None else _anim_chars()
    n, act = best.get("n"), best.get("act")
    if best["kind"] == "level":
        if best["states"] == 2:   # the winning move's result, then the new level (the common 2-frame win)
            line = (f"Animation: a{n} {act} completed the level; the solved board was never shown: "
                    f"animation({n})['frames'][0] is it (frames[1] = the new level) -- compare it with previous_frame.")
        else:                     # the move and its own animation, possibly a win effect: no single frame is 'the' solved board
            line = (f"Animation: a{n} {act} completed the level; the old level's last {best['states'] - 1} states after it "
                    f"were never shown: animation({n})['frames'][:-1] (frames[0] right after the move, frames[-2] the last), "
                    f"frames[-1] = the new level.")
    else:
        what = (f"played {best['states']} frames in which {best['cells']} cells changed and changed back"
                if best["kind"] == "hidden" else
                f"played {best['states']} frames in which {best['cells']} cells outside the area it finally changed "
                f"changed and changed back")
        cen = _anim_census(best, chars)
        tail = "; the final board is unchanged" if best["kind"] == "hidden" else ""
        line = f"Animation: a{n} {act} {what} ({_anim_where(best['bbox'])}{'; ' + cen if cen else ''}){tail}. animation({n}) returns the frames."
    others = [r for r in recs if r is not best and r and r.get("kind") in _ANIM_FIRES]
    if others:
        ids = ", ".join(f"a{r.get('n')}" for r in others[-3:])
        line += f" Also animated: {ids}" + (f" and {len(others) - 3} earlier." if len(others) > 3 else ".")
    return line


def _anim_insert(text, line):
    """`text` with `line` as its own line right after Duck's "Executed actions..." line (else before "Current state: step",
    else first). Pure: the prompt wrapper and tests/cmp_fixes/f7-anim/measure_cost.py both use it."""
    i = text.find("\nExecuted actions")
    j = text.find("\n", i + 1) if i >= 0 else -1
    if j < 0:
        j = text.find("\nCurrent state: step ")
    return text[:j] + "\n" + line + text[j:] if j >= 0 else line + "\n" + text


def _anim_timeline(chain, chars=None, cap=_ANIM_TIMELINE):
    """One short string per distinct state: what changed vs the state before it (index i = frames[i])."""
    import numpy as np
    chars = chars if chars is not None else _anim_chars()
    out = []
    for i in range(1, len(chain)):
        a, b = chain[i - 1], chain[i]
        if a.shape != b.shape:
            out.append(f"{i - 1}: shape {a.shape[0]}x{a.shape[1]} -> {b.shape[0]}x{b.shape[1]}")
            continue
        rs, cs = np.nonzero(a != b)
        if not len(rs):
            continue
        olds = a[rs, cs].tolist(); news = b[rs, cs].tolist()
        head = f"{i - 1}: {len(rs)} cells, {_anim_where((int(rs.min()), int(cs.min()), int(rs.max()), int(cs.max())))}: "
        if len(rs) <= 6:
            out.append(head + " ".join(f"{_anim_ch(o, chars)}>{_anim_ch(v, chars)}@({r},{c})"
                                       for r, c, o, v in zip(rs.tolist(), cs.tolist(), olds, news)))
        else:
            cnt = {}
            for o, v in zip(olds, news):
                cnt[(o, v)] = cnt.get((o, v), 0) + 1
            top = sorted(cnt.items(), key=lambda kv: (-kv[1], kv[0]))[:3]
            out.append(head + ", ".join(f"{_anim_ch(o, chars)}>{_anim_ch(v, chars)} {k}" for (o, v), k in top)
                       + (" ..." if len(cnt) > 3 else ""))
    if len(out) > cap:
        h = cap // 2
        out = out[:h] + [f"... {len(out) - 2 * h} more frames ..."] + out[-h:]
    return out


def _anim_fix_tb(text, m):
    """Sandbox traceback text (python_tool_sandbox._sanitize_exception: a "Traceback (most recent call last):" line, indented
    frame lines, then "Type: message"): in the FRAME lines only, drop frames inside the preamble and shift the rest back by
    its m lines. The exception message is never touched (review 10-03: a message quoting 'File "<python_tool>", line N' was
    rewritten)."""
    import re
    keep, in_tb = [], False
    for ln in text.split("\n"):
        if ln.startswith("Traceback (most recent call last):"):
            in_tb = True
        elif in_tb and not ln[:1].isspace():
            in_tb = False                                  # the exception line: the message starts here
        elif in_tb:
            mm = re.match(r'(\s+File "<python_tool>", line )(\d+)(.*)$', ln)
            if mm:
                k = int(mm.group(2))
                if k <= m:
                    continue
                ln = f"{mm.group(1)}{k - m}{mm.group(3)}"
        keep.append(ln)
    return "\n".join(keep)


# ------------------------------------------------------------------------------------------------ install (DUCK_ANIM=1)
def _anim_state(sess):
    st = sess.__dict__.get("_anim_state")
    if st is None:
        import collections
        st = sess.__dict__["_anim_state"] = {"recs": {}, "chains": collections.OrderedDict(), "seq": 0, "last": None}
    return st


def _anim_sess_of(agent):
    """The game session an agent plays for. Primary: the link the session sets on its analyzer (play / _execute_action);
    fallback: the bound step_env Duck stores. The fallback alone breaks when another shim hands analyze() a WRAPPED step_env
    (f5-ledger does: a plain closure has no __self__), which silently switched this cell off in the composed build."""
    d = getattr(agent, "__dict__", None)
    s = d.get("_anim_sess") if d is not None else None
    if s is None:
        s = getattr(getattr(agent, "_step_env_callback", None), "__self__", None)
    return s if s is not None and hasattr(s, "__dict__") else None


def _anim_link(sess):
    an = getattr(sess, "analyzer", None)
    if an is not None and hasattr(an, "__dict__") and an.__dict__.get("_anim_sess") is not sess:
        an.__dict__["_anim_sess"] = sess


def _anim_answer(sess, query):
    """The host side of animation(n): the frames of action n as FrameView payloads (same format as current_frame)."""
    import inference.agent.tool_agent as ta
    from inference.agent.runtime_state import Frame
    st = sess.__dict__.get("_anim_state") if sess is not None else None
    n = query.get("n") if isinstance(query, dict) else None
    try:
        n = None if n is None else int(n)
    except (TypeError, ValueError):
        return {"error": f"animation(n): n must be an action number, got {n!r}"}
    if st is None or (n is None and st["last"] is None):
        return {"action_num": n, "frames": [], "note": "no action has played an animation in this game yet"}
    n = st["last"] if n is None else n
    rec = st["recs"].get(n)
    if rec is None:
        return {"action_num": n, "frames": [], "note": f"no record for action {n} (RESET and actions before the first are not recorded)"}
    base = {"action": rec.get("act"), "action_num": n, "kind": rec.get("kind"), "explain": _ANIM_EXPLAIN.get(rec.get("kind"), ""),
            "level": rec.get("level")}
    if rec.get("kind") is None:
        return {**base, "frames": [], "note": f"action {n} played a single frame (no animation)"}
    kept = st["chains"].get(n)
    if kept is None:
        return {**base, "frames": [], "note": f"the frames of action {n} are no longer kept (the latest {_ANIM_KEEP} animated actions are)"}
    stack, lvl_before, lvl_after = kept
    chain = [stack[i] for i in range(stack.shape[0])]
    fr = chain[1:]
    if len(fr) > _ANIM_MAX_FRAMES:
        fr = fr[:_ANIM_MAX_FRAMES // 2] + fr[-_ANIM_MAX_FRAMES // 2:]
        base["note"] = f"{len(chain) - 1 - _ANIM_MAX_FRAMES} middle frames omitted"
    def view(a, step, level):
        return ta._ascii_frame_view_payload(Frame(grid=tuple(tuple(r) for r in a.tolist()), step=step, level=level))
    return {**base, "before": view(chain[0], n - 1, lvl_before),
            "frames": [view(a, n, lvl_before if i < len(fr) - 1 else lvl_after) for i, a in enumerate(fr)],
            "timeline": _anim_timeline(chain)}


def _anim_install():
    import json, threading
    import numpy as np
    import inference.agent.tool_agent as ta
    import inference.framework.solver as sv
    S, T = sv._HarnessGameSession, ta.ToolAgent
    if getattr(S, "_anim_installed", False):
        return "already installed"
    tls = threading.local()
    log_path = _anim_os.environ.get("DUCK_ANIM_LOG", "")
    o_exec, o_step, o_play = S._execute_action, S.step_env, S.play
    o_compact, o_bup, o_run = T._compact_action_result, T._build_user_prompt, T._run_python_tool
    o_sbx = ta.run_sandboxed_python
    desc = ta._PYTHON_TOOL_DESCRIPTION   # read before the first patch: a missing attribute must leave the harness untouched
    from inference.agent.runtime_state import Frame  # noqa: F401  (these are used at call time; a drifted harness fails
    sv._level_number, ta._ascii_frame_view_payload   # noqa: B018   HERE, before anything is patched)

    def play(self, *a, **k):
        try:
            _anim_link(self)   # before the first prompt: animation() exists from the game's first python call
        except Exception as e:
            _anim_err("link", e)
        return o_play(self, *a, **k)

    def _execute_action(self, action, *a, **k):
        try:
            _anim_link(self)
            if getattr(getattr(action, "id", None), "name", "") == "RESET":
                return o_exec(self, action, *a, **k)   # never recorded: the fatal action's frames survive the auto-reset
            pre = np.array(self.game.current_state.raw.frame[-1], dtype=np.int8, copy=True)
            lvl0 = sv._level_number(self.game)
        except Exception as e:
            _anim_err("pre-board", e)
            return o_exec(self, action, *a, **k)
        payload = o_exec(self, action, *a, **k)
        try:
            chain = _anim_chain(pre, list(self.game.current_state.raw.frame))
            won = bool(payload.get("level_completed") or payload.get("run_complete"))
            rec = _anim_classify(chain, won)
            st = _anim_state(self)
            st["seq"] += 1
            rec.update(n=int(payload.get("action_num")), act=str(payload.get("action_display") or action.id.name),
                       level=payload.get("level"), over=bool(payload.get("game_over")), seq=st["seq"])
            st["recs"][rec["n"]] = rec
            while len(st["recs"]) > 512:
                st["recs"].pop(next(iter(st["recs"])))
            if rec["kind"] is not None:
                st["chains"][rec["n"]] = (np.stack(chain), lvl0, payload.get("level"))
                st["last"] = rec["n"]
                while len(st["chains"]) > max(1, _ANIM_KEEP):
                    st["chains"].popitem(last=False)
            note = _anim_note(rec)
            if note:
                payload["animation"] = note
        except Exception as e:
            _anim_err("record", e)
        return payload

    def step_env(self, arguments):
        try:
            st = _anim_state(self)
            s0 = st["seq"]
        except Exception as e:   # review 10-03: was outside any try (every action() would have failed)
            _anim_err("step_env state", e)
            return o_step(self, arguments)
        out = o_step(self, arguments)
        try:
            if isinstance(out, dict) and out.get("executed"):
                recs = sorted((r for r in st["recs"].values() if r.get("seq", 0) > s0), key=lambda r: r["seq"])
                best = _anim_pick(recs)
                if best is None:
                    out.pop("animation", None)
                else:
                    out["animation"] = f"a{best['n']}: " + _anim_note(best)
        except Exception as e:
            _anim_err("step_env", e)
        return out

    def _compact_action_result(self, payload):
        c = o_compact(self, payload)
        try:
            if isinstance(payload, dict) and payload.get("animation") and isinstance(c, dict):
                c["animation"] = str(payload["animation"])
        except Exception as e:
            _anim_err("compact", e)
        return c

    def _build_user_prompt(self, *a, **k):
        text = o_bup(self, *a, **k)
        try:
            summ = k.get("previous_step_summary") if "previous_step_summary" in k else None
            sess = _anim_sess_of(self)
            st = sess.__dict__.get("_anim_state") if sess is not None else None
            if summ and st and isinstance(text, str):
                lo, hi = summ.get("start_action_num"), summ.get("end_action_num")
                if isinstance(lo, int) and isinstance(hi, int) and lo <= hi:
                    line = _anim_line([st["recs"][n] for n in range(lo, hi + 1) if n in st["recs"]])
                    if line:
                        text = _anim_insert(text, line)
                        if log_path:
                            with open(log_path, "a", encoding="utf-8") as fh:
                                fh.write(json.dumps({"game": getattr(getattr(sess.game, "game_run", None), "game_id", None),
                                                     "range": [lo, hi], "line": line}, ensure_ascii=False) + "\n")
        except Exception as e:
            _anim_err("prompt", e)
        return text

    def _run_python_tool(self, state_path, arguments):
        prev = getattr(tls, "agent", None)
        tls.agent = self
        try:
            return o_run(self, state_path, arguments)
        finally:
            tls.agent = prev

    def run_sandboxed_python(*, code, timeout_seconds, initial_state, action_handler, **kw):
        try:   # review 10-03: was outside any try (a failure here crashed the game)
            agent = getattr(tls, "agent", None)
            sess = _anim_sess_of(agent) if agent is not None else None
        except Exception as e:
            _anim_err("session lookup", e)
            sess = None
        if sess is None:
            return o_sbx(code=code, timeout_seconds=timeout_seconds, initial_state=initial_state, action_handler=action_handler, **kw)
        full = _ANIM_PREAMBLE + code
        if "__future__" in code:
            try:
                compile(full, "<python_tool>", "exec")
            except SyntaxError:   # a __future__ import must be first: run this one snippet exactly as without the cell
                return o_sbx(code=code, timeout_seconds=timeout_seconds, initial_state=initial_state, action_handler=action_handler, **kw)

        def handler(actions):
            if (isinstance(actions, list) and len(actions) == 1 and isinstance(actions[0], dict)
                    and actions[0].get("action") == _ANIM_MARK):
                try:
                    data = _anim_answer(sess, actions[0])
                except Exception as e:
                    _anim_err("answer", e)
                    data = {"error": f"animation() failed in the host: {type(e).__name__}"}
                return {"action_result": {_ANIM_MARK: True}, "state": {"duck_animation": data}}
            return action_handler(actions)

        res = o_sbx(code=full, timeout_seconds=timeout_seconds, initial_state=initial_state, action_handler=handler, **kw)
        try:
            res = dict(res)
            ar = res.get("action_results")
            if isinstance(ar, list):
                res["action_results"] = [x for x in ar if not (isinstance(x, dict) and _ANIM_MARK in x)]
            if isinstance(res.get("error"), str) and "<python_tool>" in res["error"]:
                res["error"] = _anim_fix_tb(res["error"], _ANIM_PRE_LINES)
        except Exception as e:
            _anim_err("sandbox result", e)
        return res

    for f, o in ((play, o_play), (_execute_action, o_exec), (step_env, o_step), (_compact_action_result, o_compact),
                 (_build_user_prompt, o_bup), (_run_python_tool, o_run), (run_sandboxed_python, o_sbx)):
        f.__wrapped__ = o
    S.play, S._execute_action, S.step_env = play, _execute_action, step_env
    T._compact_action_result, T._build_user_prompt, T._run_python_tool = _compact_action_result, _build_user_prompt, _run_python_tool
    ta.run_sandboxed_python = run_sandboxed_python
    if _ANIM_DOC not in desc:
        ta._PYTHON_TOOL_DESCRIPTION = desc + _ANIM_DOC
    S._anim_installed = True
    return ("installed (solver.play/_execute_action/step_env, ToolAgent._compact_action_result/_build_user_prompt/_run_python_tool, "
            f"tool_agent.run_sandboxed_python, tool description +1 sentence); keep={_ANIM_KEEP} border={_ANIM_BORDER}")


if _ANIM_ON:
    try:   # everything that can fail (imports, attribute reads) happens before the first patch is assigned
        print(f"ANIMATION -- {_anim_install()}", flush=True)
    except Exception as _anim_e:
        if not bool(globals().get("TRUE_SUBMISSION", False)):   # a validation run fails loudly
            raise
        print(f"ANIMATION: NOT INSTALLED ({type(_anim_e).__name__}: {_anim_e}) -- TRUE_SUBMISSION: the shipped harness runs unchanged", flush=True)
else:
    print("ANIMATION available but off (DUCK_ANIM=1 enables)", flush=True)
