"""RULES AS CODE for the Duck harness (10-03; design: notes/design_rules_as_code_2026-10-03.md). Opt-in: DUCK_FIT=1.
Unset/0: this cell changes nothing (tests/rules_as_code/test_shim_inert.py asserts every patched name is identical).

What it adds to the python sandbox: `fit(predict)`. The model writes the game's rule as code,
`predict(board, action) -> next_board`, and the harness replays EVERY transition it has recorded for this game through it
on CPU and answers either "fits all N" or the FIRST transition the rule gets wrong ("your rule says 9 at (36,44) after move
25; the game shows 8"). The game itself is the doubter (plan_hypothesis_elimination.md S2/S5; the doubter prompt could not
supply this discipline from the same weights). The 09-19 red-team showed exact board equality is the wrong test: a
cost meter driven by a hidden counter makes the TRUE ft09 rule score 23.5% exact and 100% once the meter row is masked.
So the replay learns the per-game nuisance regions from the recorded transitions (thin changes that recur in one row/col
band and drift one way = a meter frontier; cells that flip on most moves regardless of action) and scores the rest; the
report names what is not scored. The blanket outer-border rule is NOT used (it invents conflicts on ar25 and misses sk48
row 53 / sc25 cols 62-63; red-team required change 2).

Mechanism (monkeypatch only; the vendored harness stays byte-identical; names are _fit_*, findings 79):
  - python_tool_sandbox._SANDBOX_BOOTSTRAP (read by run_sandboxed_python at call time): asserted text edits insert the
    fit core at module level, bind `fit` into the sandbox globals, read the per-step flags the host ships, and expose
    `frame.grid` (the raw board already travels in every frame payload; the bootstrap kept it private as `_grid`).
    The raw board is what makes `predict(board, action)` writable at all (red-team S5 blocker, plan item 3).
  - ToolAgent._compact_action_result: records this game-pass's step results (action_num -> flags: level_completed,
    game_over, done, board_changed) on the agent; tool_agent.run_sandboxed_python: ships that record into the sandbox
    as `fit_steps` so fit() can skip terminal transitions (a game-over or level-end frame is not the rule's job).
  - ToolAgent._run_python_tool: one log line per python call that mentions fit( (DUCK_FIT_LOG, default
    <runtime dir>/fit_log.jsonl) so a GPU run can be audited for how often fit was called and what it answered.
  - _PYTHON_TOOL_DESCRIPTION / _tools / prompts.*: the tool description gains the fit contract (short, no game lore);
    the "raw numeric grid is not available/intentionally not exposed" sentences are replaced by the `frame.grid` fact.
The core (_FIT_CORE) is one string so that the SAME code runs inside the sandbox subprocess (stdlib only, no numpy: the
sandbox starts python -I -S) and in the host for the CPU tests (tests/rules_as_code/).
"""
import os as _fit_os, re as _fit_re, json as _fit_json, time as _fit_time, threading as _fit_threading
from pathlib import Path as _fit_Path

_FIT_CORE = r'''
# ---- fit core (provided by the harness; identical in the sandbox and in the host tests) ----
import re as _fit_re, time as _fit_time
_FIT_HEX = "0123456789abcdef"

def _fit_changed(a, b):
    """Cells (r, c) where boards a and b differ (row lists compared first: fast when most rows are equal)."""
    out = []
    for r in range(min(len(a), len(b))):
        ra = a[r]; rb = b[r]
        if ra != rb:
            for c in range(min(len(ra), len(rb))):
                if ra[c] != rb[c]:
                    out.append((r, c))
    return out

def _fit_components(cells):
    """8-connected components of a set of cells."""
    todo = set(cells); comps = []
    while todo:
        start = todo.pop(); comp = [start]; stack = [start]
        while stack:
            r, c = stack.pop()
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    n = (r + dr, c + dc)
                    if n in todo:
                        todo.discard(n); comp.append(n); stack.append(n)
        comps.append(comp)
    return comps

def _fit_drifts(xs, tol, max_step=3):
    """A meter frontier CREEPS: >= 3 distinct positions, a typical (median) advance of at most `max_step` cells between
    ticks, and at most `tol` reversals against the main direction, where a jump back to the band's home end (a refill on
    reset, level change or life lost) is not a reversal. my_agent.py _monotone, generalised to creep + refills. The first
    form (any jump over half the band = refill, no creep test) masked seven gameplay rows on ar25 (objects stepping 3-6
    cells both ways) and missed ls20's meter (its refills are shorter than half the band)."""
    if len({round(x) for x in xs}) < 3:
        return False
    steps = [b - a for a, b in zip(xs, xs[1:]) if b != a]
    if len(steps) < 2:
        return False
    mags = sorted(abs(s) for s in steps)
    if mags[len(mags) // 2] > max_step:
        return False
    small = [s for s in steps if abs(s) <= 3 * max_step]
    fwd = sum(1 for s in small if s > 0); back = sum(1 for s in small if s < 0)
    direction = 1 if fwd >= back else -1
    home = min(xs) if direction > 0 else max(xs)
    rev = 0
    for a, b in zip(xs, xs[1:]):
        s = b - a
        if s == 0 or (s > 0) == (direction > 0) or abs(b - home) <= 2:
            continue
        rev += 1
    return rev <= tol

def _fit_is_break(t):
    act, b, a, l0, l1, step, fl = t
    return act.strip().upper() == "RESET" or l0 != l1 or bool(fl.get("level_completed")) or bool(fl.get("game_over")) or bool(fl.get("done"))

def _fit_learn_mask(ts, min_hits=3, frac=0.10, cell_frac=0.5, cell_min_hits=8, thin=8, one_way=0.75):
    """Per-game nuisance regions from the recorded transitions (every level; meters persist across levels).
    (1) bands: a changed component of <= `thin` cells whose bounding box is at most 2 rows (or 2 columns) high is a thin
        change in that row band (column band). A band hit in >= max(min_hits, frac*n) transitions is a meter frontier when
        its position CREEPS one way (_fit_drifts: median tick <= 3 cells, refills to the home end allowed) and its cells
        CONVERT one way (>= `one_way` of the changed cells share one old->new colour pair and the reverse pair is rare):
        a frontier turns unspent cells into spent ones; a small object moving one cell per move vacates cells (object ->
        background) and occupies others (background -> object) in the same tick, and is left scored. Every cell of a
        frontier's rows (columns) is unscored, because the frontier will reach cells it has not changed yet.
    (2) cells: a cell that changed ALONE (in a component of <= 4 cells) in >= cell_frac of the transitions and >= cell_min_hits
        times, under >= 2 distinct action names when the game used >= 2, is a blinker/counter -> unscored. Conservative on
        purpose: no public-game recording in tests/rules_as_code/fixtures needed it (every meter there is a band), and over a
        5-move record the path cells of a 2x2 object bouncing in place look exactly like blinkers.
    Transitions that are breaks (reset, level change, game over) contribute nothing but raise the reversal tolerance.
    Known failure modes (design note): a 1-2 px object that only ever ADVANCES and whose trail is repainted elsewhere is
    masked (the report names the band; the model can pass mask=None or its own mask); a meter that has not ticked >= 3
    times yet is not masked (the first mismatch lands in the meter band and says so)."""
    n = 0; breaks = 0; cell_hits = {}; cell_acts = {}; rband = {}; cband = {}; names = set()
    for k, t in enumerate(ts):
        if _fit_is_break(t):
            breaks += 1; continue
        act, b, a = t[0], t[1], t[2]
        cells = _fit_changed(b, a)
        if not cells:
            continue
        n += 1; name = act.split("(")[0].strip().upper(); names.add(name)
        for comp in _fit_components(cells):
            if len(comp) <= 4:
                for rc in comp:
                    cell_hits[rc] = cell_hits.get(rc, 0) + 1; cell_acts.setdefault(rc, set()).add(name)
            if len(comp) > thin:
                continue
            rs = [r for r, c in comp]; cs = [c for r, c in comp]
            r0, r1, c0, c1 = min(rs), max(rs), min(cs), max(cs)
            pairs = [(b[r][c], a[r][c]) for r, c in comp]
            if r1 - r0 <= 1:
                e = rband.setdefault((r0, r1), {}); h = e.setdefault(k, [0.0, 0, []]); h[0] += sum(cs); h[1] += len(cs); h[2] += pairs
            if c1 - c0 <= 1:
                e = cband.setdefault((c0, c1), {}); h = e.setdefault(k, [0.0, 0, []]); h[0] += sum(rs); h[1] += len(rs); h[2] += pairs
    need = max(min_hits, frac * n); tol = 1 + breaks; rows = set(); cols = set(); ev = {}

    def frontier(hits):
        """(positions in time order, one per transition) if the band's thin changes creep one way and convert one way."""
        xs = [hits[k][0] / hits[k][1] for k in sorted(hits)]
        if len(xs) < need or not _fit_drifts(xs, tol):
            return None
        cnt = {}
        for e in hits.values():
            for pr in e[2]:
                cnt[pr] = cnt.get(pr, 0) + 1
        tot = sum(cnt.values()); (o, nw), top = max(cnt.items(), key=lambda kv: kv[1])
        if top < one_way * tot or cnt.get((nw, o), 0) > 0.1 * tot:
            return None
        return xs, (o, nw)
    for (r0, r1), hits in rband.items():
        f = frontier(hits)
        if f:
            rows.update(range(r0, r1 + 1)); ev["rows %d-%d" % (r0, r1) if r1 > r0 else "row %d" % r0] = "%d of %d moves, one way, %s->%s" % (len(f[0]), n, f[1][0], f[1][1])
    for (c0, c1), hits in cband.items():
        f = frontier(hits)
        if f:
            cols.update(range(c0, c1 + 1)); ev["cols %d-%d" % (c0, c1) if c1 > c0 else "col %d" % c0] = "%d of %d moves, one way, %s->%s" % (len(f[0]), n, f[1][0], f[1][1])
    cells = []
    if n:
        for rc, h in cell_hits.items():
            if rc[0] in rows or rc[1] in cols:
                continue
            if h >= max(cell_min_hits, cell_frac * n) and (len(names) < 2 or len(cell_acts[rc]) >= 2):
                cells.append(rc)
    cells.sort()
    if cells:
        ev["%d cells" % len(cells)] = "flip on >= %d%% of moves regardless of action" % int(100 * cell_frac)
    return {"rows": sorted(rows), "cols": sorted(cols), "cells": [list(rc) for rc in cells], "text": _fit_mask_text(sorted(rows), sorted(cols), cells), "evidence": ev, "moves": n}

def _fit_runs(xs):
    out = []
    for x in xs:
        if out and out[-1][1] == x - 1: out[-1][1] = x
        else: out.append([x, x])
    return out

def _fit_mask_text(rows, cols, cells):
    parts = []
    if rows: parts.append("rows " + ", ".join(("%d-%d" % (a, b)) if b > a else str(a) for a, b in _fit_runs(rows)) if len(rows) > 1 else "row %d" % rows[0])
    if cols: parts.append("cols " + ", ".join(("%d-%d" % (a, b)) if b > a else str(a) for a, b in _fit_runs(cols)) if len(cols) > 1 else "col %d" % cols[0])
    if cells: parts.append(("cells " + ",".join("(%d,%d)" % tuple(rc) for rc in cells[:6]) + (" +%d more" % (len(cells) - 6) if len(cells) > 6 else "")))
    return "; ".join(parts) if parts else "none"

def _fit_norm_mask(mask, ts):
    """mask: "auto" (learned), None (score every cell), a dict {"rows": [...], "cols": [...], "cells": [[r, c], ...]},
    or a list of (r, c) cells. -> (rows set, cols set, cells set, text, learned dict|None)."""
    if mask == "auto":
        m = _fit_learn_mask(ts)
        return set(m["rows"]), set(m["cols"]), {tuple(rc) for rc in m["cells"]}, m["text"], m
    if mask is None:
        return set(), set(), set(), "none (every cell scored)", None
    if isinstance(mask, dict):
        rows = {int(r) for r in mask.get("rows", [])}; cols = {int(c) for c in mask.get("cols", [])}
        cells = {(int(rc[0]), int(rc[1])) for rc in mask.get("cells", [])}
    else:
        rows, cols = set(), set(); cells = {(int(rc[0]), int(rc[1])) for rc in mask}
    return rows, cols, cells, _fit_mask_text(sorted(rows), sorted(cols), sorted(cells)) + " (yours)", None

def _fit_validate(p, truth):
    """None if p is a board of the truth's shape, else a short description of what predict returned."""
    if p is None:
        return "returned None"
    try:
        n = len(p)
    except TypeError:
        return "returned %s, not a board" % type(p).__name__
    if n != len(truth):
        return "returned %d rows (board has %d)" % (n, len(truth))
    for r in range(n):
        try:
            if len(p[r]) != len(truth[r]):
                return "row %d has %d cells (board rows have %d)" % (r, len(p[r]), len(truth[r]))
        except TypeError:
            return "row %d is %s, not a list" % (r, type(p[r]).__name__)
    return None

def _fit_cell(v):
    try:
        v = int(v)
    except (TypeError, ValueError):
        return "?"
    return _FIT_HEX[v] if 0 <= v < 16 else "?"

def _fit_crop(p, a, cells, size):
    rs = [r for r, c in cells]; cs = [c for r, c in cells]
    r0, c0 = min(rs), min(cs); r1 = min(max(rs), r0 + size - 1); c1 = min(max(cs), c0 + size - 1)
    lines = ["yours | game, rows %d-%d, cols %d-%d:" % (r0, r1, c0, c1)]
    for r in range(r0, r1 + 1):
        lines.append("".join(_fit_cell(p[r][c]) for c in range(c0, c1 + 1)) + " | " + "".join(_fit_cell(a[r][c]) for c in range(c0, c1 + 1)))
    if max(rs) > r1 or max(cs) > c1:
        lines.append("(window cut at %dx%d; the differences reach row %d, col %d)" % (size, size, max(rs), max(cs)))
    return lines

def _fit_run(predict, ts, mask="auto", level=None, budget_s=8.0, crop=8):
    """Replay transitions `ts` (tuples: action, before, after, level_before, level_after, step, flags) through predict.
    Scores the cells outside the mask; stops at the time budget; the FIRST mismatch is reported in full.
    -> dict: ok, fit, checked, skipped, mask, first (None or dict), text (what the model reads), stopped_early."""
    rows, cols, cells, mtext, learned = _fit_norm_mask(mask, ts)
    sel = [(k, t) for k, t in enumerate(ts) if level is None or t[3] == level]
    n_fit = n_checked = 0; skipped = {"level change": 0, "reset": 0, "end of game": 0}
    first = None; stopped = False; t0 = _fit_time.monotonic()
    for k, t in sel:
        act, b, a, l0, l1, step, fl = t
        if act.strip().upper() == "RESET":
            skipped["reset"] += 1; continue
        if l0 != l1 or fl.get("level_completed"):
            skipped["level change"] += 1; continue
        if fl.get("game_over") or fl.get("done"):
            skipped["end of game"] += 1; continue
        if _fit_time.monotonic() - t0 > budget_s:
            stopped = True; break
        n_checked += 1
        board = [list(r) for r in b]
        try:
            p = predict(board, act)
        except Exception as e:
            first = {"k": k, "step": step, "action": act, "error": "raised %s: %s" % (type(e).__name__, str(e)[:100])}
            break
        bad = _fit_validate(p, a)
        if bad:
            first = {"k": k, "step": step, "action": act, "error": bad}
            break
        diff = [(r, c) for (r, c) in _fit_changed(p, a) if r not in rows and c not in cols and (r, c) not in cells]
        if not diff:
            n_fit += 1
            continue
        if first is None:
            rs = [r for r, c in diff]; cs = [c for r, c in diff]; r, c = diff[0]
            first = {"k": k, "step": step, "action": act, "n_cells": len(diff), "bbox": [min(rs), min(cs), max(rs), max(cs)],
                     "cell": [r, c], "yours": p[r][c], "game": a[r][c], "crop": _fit_crop(p, a, diff, crop)}
    lv = "" if level is None else " of level %d" % level
    sk = ", ".join("%d %s%s" % (v, k, "s" if v > 1 and k != "end of game" else "") for k, v in skipped.items() if v)
    tail = " (not scored: %s)" % mtext + (("; skipped " + sk) if sk else "") + (("; stopped at the time budget after %d" % n_checked) if stopped else "")
    if n_checked == 0 and first is None and stopped:
        text = "fit: ran out of time (budget %.1f s) before replaying any move%s." % (budget_s, tail.replace("; stopped at the time budget after 0", ""))
    elif n_checked == 0 and first is None:
        text = "fit: no recorded moves%s to replay yet%s." % (lv, tail)
    elif first is None:
        text = "fit: your rule reproduces %s%s%s." % (("the 1 recorded move" if n_checked == 1 else "all %d recorded moves" % n_checked), lv, tail)
    elif "error" in first:
        text = "fit: your rule %s at move %d (transitions[%d], %s); %d of %d reproduced before that%s." % (
            first["error"], first["step"], first["k"], first["action"], n_fit, n_checked, tail)
    else:
        bb = first["bbox"]
        text = ("fit: %d of %d recorded moves%s reproduced; first miss at move %d (transitions[%d], %s): %d cell%s differ%s in rows %d-%d, cols %d-%d, "
                "e.g. (%d,%d) yours %s, game %s%s.\n" % (n_fit, n_checked, lv, first["step"], first["k"], first["action"], first["n_cells"],
                "s" if first["n_cells"] > 1 else "", "" if first["n_cells"] > 1 else "s", bb[0], bb[2], bb[1], bb[3], first["cell"][0], first["cell"][1], first["yours"], first["game"], tail)
                + "\n".join(first["crop"]))
    return {"ok": first is None and n_checked > 0, "fit": n_fit, "checked": n_checked, "skipped": skipped, "mask": mtext,
            "mask_detail": learned, "first": first, "stopped_early": stopped, "text": text}

def _fit_tuples(transitions, steps=None):
    """Sandbox TransitionViews -> plain tuples (action, before, after, level_before, level_after, step, flags)."""
    out = []; steps = steps or {}
    for t in transitions:
        bf = getattr(t, "before_frame", None); af = getattr(t, "after_frame", None)
        if bf is None or af is None:
            continue
        b = getattr(bf, "grid", None) or getattr(bf, "_grid", None); a = getattr(af, "grid", None) or getattr(af, "_grid", None)
        if not b or not a:
            continue
        step = int(getattr(af, "step", 0) or 0)
        fl = steps.get(str(step)) or steps.get(step) or {}
        out.append((str(getattr(t, "action", "") or ""), b, a, int(getattr(bf, "level", 0) or 0), int(getattr(af, "level", 0) or 0), step, dict(fl)))
    return out

def _fit_bind(rg):
    def fit(predict, transitions=None, mask="auto", level="current", budget_s=8.0):
        """Replay this game's recorded moves through predict(board, action) -> board. Returns a dict; read its 'text'.
        mask="auto" learns the unscored region from the record; None scores every cell; or give {"rows": [...], "cols": [...]}.
        level="current" replays the current level's moves; None replays every level."""
        tv = transitions if transitions is not None else (rg.get("transitions") or [])
        ts = _fit_tuples(tv, rg.get("_fit_steps") or {})
        lv = level
        if level == "current":
            cf = rg.get("current_frame"); lv = int(getattr(cf, "level", 0) or 0) if cf is not None else None
            lv = lv or None
        return _fit_run(predict, ts, mask=mask, level=lv, budget_s=budget_s)
    return fit
# ---- end fit core ----
'''
_fit_ns = {}
exec(compile(_FIT_CORE, "cell_duck_fit.py/_FIT_CORE", "exec"), _fit_ns)
_fit_run, _fit_learn_mask, _fit_tuples, _fit_changed = _fit_ns["_fit_run"], _fit_ns["_fit_learn_mask"], _fit_ns["_fit_tuples"], _fit_ns["_fit_changed"]

_FIT_DOC = (" FIT: write the game's rule as a function `predict(board, action) -> board` (board = list of 64 rows of 64 ints, exactly "
            "`frame.grid`; action = the string in `transitions[*].action`, e.g. 'UP' or 'MOUSE(row=3, col=7)'; return the board after the action) "
            "and call `fit(predict)`: it replays every recorded move of this game through your function and returns a dict whose 'text' says "
            "either that it reproduces all of them or the first move it gets wrong (which cells differ, yours vs the game's). Cells that change "
            "on their own (a counter strip) are detected from the record and not scored; the report names them. `fit(predict, mask=None)` "
            "scores every cell; `mask={'rows': [63]}` sets the unscored cells yourself; `level=None` replays every level, not only the current one.")
_FIT_GRID_SENTENCE = "`frame.grid` is the board as a list of rows of ints (colours 0-15); `.ascii` and `.segmentation` are views of it."
_FIT_OLD_TOOL = "The raw numeric grid is not available."
_FIT_OLD_PROMPT = "The raw numeric grid is intentionally not exposed."
_fit_tls = _fit_threading.local()


def _fit_patch_bootstrap(src):
    """The four asserted edits on _SANDBOX_BOOTSTRAP (indentation taken from the anchors, never assumed)."""
    def one(pattern):
        ms = list(_fit_re.finditer(pattern, src, _fit_re.M))
        if len(ms) != 1:
            raise RuntimeError("cell_duck_fit: anchor %r matched %d times in _SANDBOX_BOOTSTRAP (harness changed?)" % (pattern, len(ms)))
        return ms[0]
    m = one(r"^def main\(\):\n"); src = src[:m.start()] + _FIT_CORE.lstrip("\n") + "\n" + src[m.start():]
    m = one(r"^([ \t]*)runtime_globals\[\"action\"\] = action\n"); src = src[:m.end()] + m.group(1) + 'runtime_globals["fit"] = _fit_bind(runtime_globals)\n' + src[m.end():]
    m = one(r"^([ \t]*)runtime_globals\[\"last_action_result\"\] = action_result\n"); src = src[:m.end()] + m.group(1) + 'runtime_globals["_fit_steps"] = state_payload.get("fit_steps") or {}\n' + src[m.end():]
    m = one(r"^([ \t]*)self\._grid = grid\n"); src = src[:m.end()] + m.group(1) + "self.grid = grid\n" + src[m.end():]
    compile(src, "<sandbox bootstrap + fit>", "exec")   # fail here, loudly, not in the first game
    return src


def _fit_steps_of(agent, state_path):
    """This game-pass's step record on the agent (one ToolAgent = one game; reset when the state path changes)."""
    key = str(state_path) if state_path is not None else None
    if agent.__dict__.get("_fit_steps_path") != key:
        agent.__dict__["_fit_steps_path"] = key; agent.__dict__["_fit_steps"] = {}
    return agent.__dict__["_fit_steps"]


def _fit_install():
    import inference.agent.tool_agent as ta
    import inference.agent.python_tool_sandbox as ps
    import inference.agent.prompts as pr
    ps._SANDBOX_BOOTSTRAP = _fit_patch_bootstrap(ps._SANDBOX_BOOTSTRAP)

    orig_compact = ta.ToolAgent._compact_action_result
    def _fit_compact_action_result(self, payload):
        compact = orig_compact(self, payload)
        try:
            if compact.get("executed") and compact.get("action_num") is not None:
                steps = _fit_steps_of(self, getattr(_fit_tls, "state_path", None))
                steps[str(compact["action_num"])] = {k: bool(compact.get(k)) for k in ("level_completed", "game_over", "done", "run_complete", "board_changed")}
                steps[str(compact["action_num"])]["level"] = compact.get("level")
        except Exception:
            pass
        return compact
    ta.ToolAgent._compact_action_result = _fit_compact_action_result

    orig_rsp = ta.run_sandboxed_python
    def _fit_run_sandboxed_python(*, code, timeout_seconds, initial_state, action_handler):
        agent = getattr(_fit_tls, "agent", None)
        def steps():
            return dict(_fit_steps_of(agent, getattr(_fit_tls, "state_path", None))) if agent is not None else {}
        def handler(actions):
            r = action_handler(actions)
            if isinstance(r, dict):
                r = dict(r); r["state"] = dict(r.get("state") or {}, fit_steps=steps())
            return r
        return orig_rsp(code=code, timeout_seconds=timeout_seconds, initial_state=dict(initial_state or {}, fit_steps=steps()), action_handler=handler)
    ta.run_sandboxed_python = _fit_run_sandboxed_python

    orig_run = ta.ToolAgent._run_python_tool
    def _fit_run_python_tool(self, state_path, arguments):
        _fit_tls.agent = self; _fit_tls.state_path = state_path
        code = str((arguments or {}).get("code", ""))
        try:
            return orig_run(self, state_path, arguments)
        finally:
            _fit_tls.agent = None
            if "fit(" in code:
                try:
                    res = None
                    import sys as _s
                    exc = _s.exc_info()[1]
                    log = _fit_os.environ.get("DUCK_FIT_LOG") or str(_fit_Path(state_path).parent / "fit_log.jsonl")
                    with open(log, "a") as fh:
                        fh.write(_fit_json.dumps({"t": _fit_time.time(), "game": _fit_Path(state_path).stem, "steps": len(_fit_steps_of(self, state_path)),
                                                  "code_chars": len(code), "error": repr(exc)[:200] if exc else None}) + "\n")
                except Exception:
                    pass
    ta.ToolAgent._run_python_tool = _fit_run_python_tool

    orig_tools = ta.ToolAgent._tools
    def _fit_tools(self, state_path):
        tools = orig_tools(self, state_path)
        for t in tools:
            fn = t.get("function", {}) if isinstance(t, dict) else {}
            if fn.get("name") == "python":
                d = fn.get("description") or ""
                if _FIT_DOC not in d:
                    fn["description"] = d.replace(_FIT_OLD_TOOL, _FIT_GRID_SENTENCE) + _FIT_DOC
        return tools
    ta.ToolAgent._tools = _fit_tools
    ta._PYTHON_TOOL_DESCRIPTION = ta._PYTHON_TOOL_DESCRIPTION.replace(_FIT_OLD_TOOL, _FIT_GRID_SENTENCE) + _FIT_DOC
    n = 0
    for k in dir(pr):
        v = getattr(pr, k)
        if isinstance(v, str) and _FIT_OLD_PROMPT in v:
            setattr(pr, k, v.replace(_FIT_OLD_PROMPT, _FIT_GRID_SENTENCE)); n += 1
            if hasattr(ta, k): setattr(ta, k, getattr(pr, k))
    return n


if _fit_os.environ.get("DUCK_FIT", "0") == "1":
    _fit_n = _fit_install()
    print(f"FIT installed: fit(predict) in the sandbox, frame.grid exposed, step flags shipped, tool description updated ({_fit_n} prompt constant(s) amended)", flush=True)
else:
    print("FIT available but off (DUCK_FIT=1 enables)", flush=True)
