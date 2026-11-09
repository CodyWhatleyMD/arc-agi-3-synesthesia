"""NATIVES for the python sandbox (09-27, findings 107). Opus 5.5 rebuilt the same four helpers on
76% of its 2,340 calls -- objs() 296x, a frame diff 411x, a lattice downsample 158x, an act-until
loop 693x -- because Duck's sandbox stops one step short of them and is ephemeral by contract.
The 27B mostly does not build them (34% of its calls define anything). This cell provides them
natively and persists the model's OWN top-level defs across turns, so a helper written once stays.

Mechanism (monkeypatch only; the vendored harness stays byte-identical):
  - ToolAgent._run_python_tool: prepend NATIVES_SRC + the model's stored defs (each in try/except)
    to the snippet; after the call, harvest top-level def/class sources from the ORIGINAL snippet
    (ast) into a per-agent store; correct `<python_tool>` line numbers in the result by the
    preamble length so the model's own numbering still holds.
  - _PYTHON_TOOL_DESCRIPTION + the `code` parameter text: say what exists and that defs persist.
Enable with DUCK_NATIVES=1 (helpers) and DUCK_PERSIST_DEFS=1 (persistence) -- two switches, two arms:
helpers and a persistent namespace are different interventions (the forensics fork's point).
Shared exec namespace with the other cells (findings 79): every module-level name is _nat_*.
"""
import os as _nat_os, ast as _nat_ast, re as _nat_re, json as _nat_json
import inference.agent.tool_agent as _nat_ta

_NAT_SRC = '''# --- natives (provided by the harness) ---
def objs(frame=None, min_pixels=1, color=None):
    """Objects of a frame as dicts: id,color,pixels,hash,r0,c0,r1,c1,h,w,cr,cc,children (from .segmentation)."""
    f = frame if frame is not None else current_frame
    out = []
    for n in f.segmentation['nodes']:
        if n['pixels'] < min_pixels or (color is not None and n['color'] != color):
            continue
        b = n['boundary']; rs = [p[0] for p in b]; cs = [p[1] for p in b]
        r0, c0, r1, c1 = min(rs), min(cs), max(rs), max(cs)
        out.append({'id': n['id'], 'color': n['color'], 'pixels': n['pixels'], 'hash': n['hash'],
                    'r0': r0, 'c0': c0, 'r1': r1, 'c1': c1, 'h': r1 - r0 + 1, 'w': c1 - c0 + 1,
                    'cr': (r0 + r1) / 2, 'cc': (c0 + c1) / 2, 'children': list(n.get('children', []))})
    return out
def diff(a=None, b=None, limit=400):
    """Changed cells between two frames (default previous_frame -> current_frame): changed, cells [(r,c,old,new)], pairs {'old>new': n}, rows, cols, bbox."""
    A = a if a is not None else previous_frame; B = b if b is not None else current_frame
    if A is None or B is None:
        return {'changed': 0, 'cells': [], 'pairs': {}, 'rows': [], 'cols': [], 'bbox': None, 'note': 'no previous frame'}
    ra = A.ascii.split('\\n'); rb = B.ascii.split('\\n'); cells = []; pairs = {}
    for i in range(min(len(ra), len(rb))):
        x = ra[i]; y = rb[i]
        for j in range(min(len(x), len(y))):
            if x[j] != y[j]:
                cells.append((i, j, x[j], y[j])); k = x[j] + '>' + y[j]; pairs[k] = pairs.get(k, 0) + 1
    rows = sorted(set(c[0] for c in cells)); cols = sorted(set(c[1] for c in cells))
    return {'changed': len(cells), 'cells': cells[:limit], 'pairs': pairs, 'rows': rows, 'cols': cols,
            'bbox': (rows[0], cols[0], rows[-1], cols[-1]) if cells else None}
def grid(cell=4, frame=None, r0=0, c0=0):
    """Coarse view: one character per cell x cell block (top-left sample), as a list of strings. Try cell=4 or 3; shift with r0/c0."""
    f = frame if frame is not None else current_frame
    return [row[c0::cell] for row in f.ascii.split('\\n')[r0::cell]]
def act_until(actions, stop=('level_completed', 'game_over', 'done'), max_steps=None):
    """Run actions one at a time; stop early when last_action_result has any `stop` flag. Returns steps, stopped_on, result, diff()."""
    seq = list(actions)
    if max_steps is not None:
        seq = seq[:max_steps]
    n = 0; stopped = None
    for a in seq:
        action([a]); n += 1
        r = last_action_result or {}
        hit = [k for k in stop if r.get(k)]
        if hit:
            stopped = hit[0]; break
    return {'steps': n, 'stopped_on': stopped, 'result': last_action_result, 'diff': diff()}
'''
_NAT_DOC = (" NATIVES: `objs(frame=None, min_pixels=1, color=None)` -> objects with bbox/centre; `diff(a=None, b=None)` -> changed cells "
            "between previous_frame and current_frame; `grid(cell=4)` -> a coarse one-char-per-cell view; `act_until(actions, stop=(...))` "
            "-> run a sequence and stop on level_completed/game_over.")
_NAT_DOC_PERSIST = " Top-level functions and classes you define PERSIST across your later python calls in this game (redefine to replace)."

def _nat_harvest(code):
    """Top-level def/class sources from the model's own snippet, keyed by name (latest wins)."""
    out = {}
    try:
        tree = _nat_ast.parse(code)
    except SyntaxError:
        return out
    for node in tree.body:
        if isinstance(node, (_nat_ast.FunctionDef, _nat_ast.AsyncFunctionDef, _nat_ast.ClassDef)):
            seg = _nat_ast.get_source_segment(code, node)
            if seg:
                out[node.name] = seg
    return out

_NAT_V2 = _nat_os.environ.get("DUCK_NATIVES_V2", "0") == "1"
def _nat_v2_path():
    for c in (_nat_os.environ.get("DUCK_NATIVES_V2_SRC"),
              _nat_os.path.join(_nat_os.path.dirname(_nat_os.path.abspath(__file__)), "natives_v2_src.py") if "__file__" in globals() else None,
              "notebooks_duck/natives_v2_src.py", "/home/ignaz/github/arc-prize-2026/notebooks_duck/natives_v2_src.py"):
        if c and _nat_os.path.exists(c): return c
    raise FileNotFoundError("natives_v2_src.py not found: set DUCK_NATIVES_V2_SRC (the Kaggle notebook sets it to BUNDLE_DIR/natives_v2_src.py)")
_NAT_SRC_V2 = open(_nat_v2_path()).read() if _NAT_V2 else ""
_NAT_DOC_V2 = (" V2 NATIVES: geometry over objs -- `overlap(a,b)`, `touching(a,b)`, `supported(a, others, gravity)`, `aligned(a,b,axis)`, `dist(a,b)`; "
               "memory -- `attempts(action)` (every past transition), `tried(action)` (outcomes of this action from THIS board: [] = never tried here), `sig(frame, mask_rows)`; "
               "`contrast(good_frames, bad_frames)` -> the cells that differ consistently between situations that worked and ones that did not; "
               "`plan(predict, actions, goal, max_depth, limit)` -> shortest action sequences under YOUR predict(state, action) model; "
               "`moved()` / `report()` -> what the last action changed, object by object.")
def _nat_preamble(store):
    parts = [_NAT_SRC] + ([_NAT_SRC_V2 + "\n"] if _NAT_V2 else [])
    for name, src in store.items():
        body = "\n".join("    " + ln for ln in src.split("\n"))
        parts.append(f"try:  # persisted: {name}\n{body}\nexcept Exception:\n    pass\n")
    parts.append("# --- your code ---\n")
    return "".join(parts)

def _nat_fix_lines(text, offset):
    def sub(m):
        n = int(m.group(2)); return m.group(1) + str(n - offset if n > offset else n)
    return _nat_re.sub(r'(<python_tool>", line )(\d+)', sub, _nat_re.sub(r'(<python_tool>:)(\d+)', sub, text))

_nat_orig_run = _nat_ta.ToolAgent._run_python_tool
_NAT_PERSIST = _nat_os.environ.get("DUCK_PERSIST_DEFS", "0") == "1"
def _nat_run_python_tool(self, state_path, arguments):
    store = self.__dict__.setdefault("_nat_defs", {}) if _NAT_PERSIST else {}
    code = str((arguments or {}).get("code", "")).rstrip()
    pre = _nat_preamble(store); offset = pre.count("\n")
    if _nat_os.environ.get("DUCK_NATIVES_DEBUG") == "1":
        print(f"NATIVES call: preamble {offset} lines, persisted defs {sorted(store)}, model code {len(code)} chars, uses natives: {[n for n in ('objs(', 'diff(', 'grid(', 'act_until(') if n in code]}", flush=True)
    res = _nat_orig_run(self, state_path, {**(arguments or {}), "code": pre + code})
    if _NAT_PERSIST:
        store.update(_nat_harvest(code))
    txt = getattr(res, "content", None) if not isinstance(res, str) else res
    if isinstance(txt, str) and "<python_tool>" in txt:
        fixed = _nat_fix_lines(txt, offset)
        try:
            res = (type(res)(fixed, getattr(res, "step_executed", False)) if not isinstance(res, str) else fixed)   # 10-01: keep step_executed (xgame-finish found the drop: an executed-then-raised call no longer broke the turn loop)
        except Exception:
            pass
    return res

_nat_orig_tools = _nat_ta.ToolAgent._tools
def _nat_tools(self, state_path):
    tools = _nat_orig_tools(self, state_path)
    for t in tools:
        fn = t.get("function", {}) if isinstance(t, dict) else {}
        if fn.get("name") == "python":
            fn["description"] = (fn.get("description") or "") + _NAT_DOC + (_NAT_DOC_V2 if _NAT_V2 else "") + (_NAT_DOC_PERSIST if _NAT_PERSIST else "")
            p = fn.get("parameters", {}).get("properties", {}).get("code", {})
            if _NAT_PERSIST and "ephemeral" in p.get("description", ""):
                p["description"] = "Python code to run. Your top-level functions and classes persist across calls in this game; other variables do not."
    return tools

if _nat_os.environ.get("DUCK_NATIVES", "0") == "1":
    _nat_ta.ToolAgent._run_python_tool = _nat_run_python_tool
    _nat_ta.ToolAgent._tools = _nat_tools
    d = _nat_ta._PYTHON_TOOL_DESCRIPTION + _NAT_DOC + (_NAT_DOC_V2 if _NAT_V2 else "")
    if _NAT_PERSIST:
        d = d.replace("Run one ephemeral Python snippet", "Run one Python snippet") + _NAT_DOC_PERSIST
    _nat_ta._PYTHON_TOOL_DESCRIPTION = d
    if _NAT_PERSIST:   # the system prompt's own 'ephemeral' sentence lives in prompts.py constants; keep it consistent with the tool
        import inference.agent.prompts as _nat_pr
        for _k in dir(_nat_pr):
            _v = getattr(_nat_pr, _k)
            if isinstance(_v, str) and "ephemeral" in _v:
                setattr(_nat_pr, _k, _v.replace("ephemeral", "persistent-for-your-defs"))
                if hasattr(_nat_ta, _k): setattr(_nat_ta, _k, getattr(_nat_pr, _k))
    print(f"NATIVES installed: objs/diff/grid/act_until; v2 (geometry/memory/contrast/plan/report): {'ON' if _NAT_V2 else 'off'}; persisted defs: {'ON' if _NAT_PERSIST else 'off'}; tool description updated", flush=True)
else:
    print("NATIVES available but off (DUCK_NATIVES=1 enables)", flush=True)
