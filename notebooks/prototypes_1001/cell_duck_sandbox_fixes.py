"""SANDBOX HYGIENE (10-01; ovf audit of q25 + findings 151). Opt-in: DUCK_SANDBOX_FIXES=1. Unset/0: this cell changes nothing.
Load AFTER cell_duck_natives.py (it rebinds natives globals that _nat_* read at call time) and BEFORE cell_duck_xgame.py and
cell_recall.py (both wrap whichever ToolAgent._run_python_tool is installed). Shared exec namespace (findings 79): names are _sbx_*.

What it changes (each item is a measured q25 failure class; q25 = our quant on Kaggle, 2,085 python calls, 182 errors):
  B1 sandbox bootstrap (asserted text edits on _SANDBOX_BOOTSTRAP, read by run_sandboxed_python at call time):
     `class` works (__build_class__ + __name__), hashlib importable, history/transition entries carry .step/.level.
  N1 natives source: the 14 safe modules + Counter/deque/defaultdict pre-imported; objs() dicts gain 'bbox' and 'centre'
     (the doc promised "bbox/centre"); diff() returns a dict whose len() is the changed-cell count, whose iteration and
     int/slice indexing go over cells (len(diff()) was the dict's 6 keys in 53 calls).
  H1 persisted defs: a def/class named `action` is saved as action_user and a def that does not compile alone is never
     saved (findings 151's two game-killers). A def named like a native still replaces it (renaming those broke 76 of
     307 replayed q25 calls that used the model's own objs/grid); the model gets a one-time note instead.
  R1 tool result: traceback/syntax-error line numbers made relative to the model's own code (the old regex never matched
     the JSON-escaped quote); step_executed kept; one-line notes (prepended to stdout) for renamed or dropped defs,
     frame-captured defaults + action(), and off-legend glyph literals (once per glyph per game).
  P1 text: the tool description carries the natives doc once (it was appended twice), the two "not saved between calls"
     prompt sentences say what actually persists.
Not done, on purpose: no persistence of module-level variables (9 of the 15 cross-call NameErrors were frame snapshots such as
`a = current_frame.ascii.split('\\n')`; persisting them turns a loud NameError into a silent stale read), and no live-proxy
current_frame (11 q25 calls keep `before = current_frame` across action() on purpose; a proxy would make every such diff empty).
"""
import os as _sbx_os

_SBX_ON = _sbx_os.environ.get("DUCK_SANDBOX_FIXES", "0") == "1"
if not _SBX_ON:
    print("SANDBOX FIXES available but off (DUCK_SANDBOX_FIXES=1 enables)", flush=True)
else:
    import re as _sbx_re, ast as _sbx_ast, json as _sbx_json, dataclasses as _sbx_dc
    import inference.agent.python_tool_sandbox as _sbx_pts
    import inference.agent.tool_agent as _sbx_ta
    import inference.agent.prompts as _sbx_pr
    import inference.utils.grid_utils as _sbx_gu
    assert _nat_ta.ToolAgent._run_python_tool is _nat_run_python_tool, \
        "cell_duck_sandbox_fixes.py must load right after cell_duck_natives.py with DUCK_NATIVES=1"

    # ---------------- B1: sandbox bootstrap --------------------------------------------------------------------------
    def _sbx_edit(text, old, new, what):
        assert text.count(old) == 1, f"sandbox fixes: anchor for {what} found {text.count(old)}x -- bootstrap drifted, refusing"
        return text.replace(old, new)
    _sbx_B = _sbx_pts._SANDBOX_BOOTSTRAP
    _sbx_B = _sbx_edit(_sbx_B, '    "zip",\n', '    "zip",\n    "__build_class__",\n', "SAFE_BUILTINS")
    _sbx_B = _sbx_edit(_sbx_B, '    "string",\n', '    "string",\n    "hashlib",\n', "SAFE_MODULES")
    _sbx_B = _sbx_edit(_sbx_B, '        "result": None,\n', '        "result": None,\n        "__name__": "__python_tool__",\n', "runtime __name__")
    _sbx_B = _sbx_edit(_sbx_B, '        self.frame = frame\n',
                       '        self.frame = frame\n        self.step = getattr(frame, "step", None)\n        self.level = getattr(frame, "level", None)\n', "HistoryEntryView")
    _sbx_B = _sbx_edit(_sbx_B, '        self.frame = after_frame\n',
                       '        self.frame = after_frame\n        self.step = getattr(after_frame, "step", None)\n        self.level = getattr(after_frame, "level", None)\n', "TransitionView")
    _sbx_pts._SANDBOX_BOOTSTRAP = _sbx_B
    _sbx_pr_mods = (_sbx_pr, _sbx_ta)

    # ---------------- N1: natives source ------------------------------------------------------------------------------
    _SBX_PREIMPORT = ("import collections, itertools, functools, heapq, bisect, math, re, json, copy, random, statistics, string, fractions, operator\n"
                      "from collections import Counter, deque, defaultdict\n")
    _sbx_N = _NAT_SRC
    _sbx_N = _sbx_edit(_sbx_N, "'cr': (r0 + r1) / 2, 'cc': (c0 + c1) / 2, ",
                       "'cr': (r0 + r1) / 2, 'cc': (c0 + c1) / 2, 'bbox': (r0, c0, r1, c1), 'centre': ((r0 + r1) / 2, (c0 + c1) / 2), ", "objs keys")
    _sbx_N = _sbx_edit(_sbx_N, "def diff(a=None, b=None, limit=400):\n", "def _diff_raw(a=None, b=None, limit=400):\n", "diff def")
    _sbx_N = _SBX_PREIMPORT + _sbx_N + '''def _diff_getitem(self, k):
    if isinstance(k, (int, slice)):
        return dict.__getitem__(self, 'cells')[k]
    return dict.__getitem__(self, k)
_Diff = type('Diff', (dict,), {'__getitem__': _diff_getitem,
                               '__iter__': lambda self: iter(dict.__getitem__(self, 'cells')),
                               '__len__': lambda self: dict.__getitem__(self, 'changed')})
def diff(a=None, b=None, limit=400):
    """Changed cells between two frames (default previous_frame -> current_frame): a dict with changed, cells [(r,c,old,new)], pairs {'old>new': n}, rows, cols, bbox. len(d) = changed; d[:k] and `for r, c, old, new in d` go over cells."""
    return _Diff(_diff_raw(a, b, limit))
'''
    _NAT_SRC = _sbx_N   # _nat_preamble reads this global at call time
    _SBX_NATIVES = set(_sbx_re.findall(r"^def (\w+)", _NAT_SRC + "\n" + _NAT_SRC_V2, _sbx_re.M))
    _SBX_RESERVED = {"action"}   # the sandbox's own function: a persisted shadow means zero env steps for the rest of the game
    _SBX_RUNTIME = {"current_frame", "previous_frame", "latest_frame", "last_action_frame", "history", "transitions", "last_transition"}

    # ---------------- H1: persisted defs ------------------------------------------------------------------------------
    def _sbx_compiles_alone(src):
        body = "\n".join("    " + ln for ln in src.split("\n"))
        try:
            compile(f"try:\n{body}\nexcept Exception:\n    pass\n", "<persist>", "exec"); return True
        except SyntaxError:
            return False
    def _sbx_harvest_full(code):
        """(store entries, renamed {old: new}, dropped [names], shadowed {native: signature}) from the model's own snippet."""
        out, renamed, dropped, shadowed = {}, {}, [], {}
        try:
            tree = _sbx_ast.parse(code)
        except SyntaxError:
            return out, renamed, dropped, shadowed
        for node in tree.body:
            if not isinstance(node, (_sbx_ast.FunctionDef, _sbx_ast.AsyncFunctionDef, _sbx_ast.ClassDef)):
                continue
            seg = _sbx_ast.get_source_segment(code, node)
            if not seg:
                continue
            name = node.name
            if name in _SBX_RESERVED:
                new = name + "_user"
                seg = _sbx_re.sub(r"^((?:async\s+)?(?:def|class)\s+)" + _sbx_re.escape(name) + r"\b", r"\g<1>" + new, seg, count=1)
                renamed[name] = new; name = new
            if not _sbx_compiles_alone(seg):
                dropped.append(name); continue
            if name in _SBX_NATIVES and isinstance(node, _sbx_ast.FunctionDef):
                shadowed[name] = f"{name}({_sbx_ast.unparse(node.args)})"
            out[name] = seg
        return out, renamed, dropped, shadowed
    def _nat_harvest(code):   # rebinds the natives' helper (looked up at call time) for anything else that calls it
        return _sbx_harvest_full(code)[0]

    # ---------------- R1: tool result ---------------------------------------------------------------------------------
    def _nat_fix_lines(text, offset):
        def sub(m):
            n = int(m.group(2)); return m.group(1) + str(n - offset if n > offset else n)
        text = _sbx_re.sub(r'(<python_tool>\\?", line )(\d+)', sub, text)        # File "<python_tool>", line N  (raw or JSON-escaped)
        text = _sbx_re.sub(r'(<python_tool>, line )(\d+)', sub, text)             # Python syntax error: ... (<python_tool>, line N)
        return _sbx_re.sub(r'(<python_tool>:)(\d+)', sub, text)

    def _sbx_legend():
        chars = str(getattr(_sbx_gu, "ARC_COLOR_CHARS", "") or "")
        names = {}
        for seg in str(getattr(_sbx_gu, "ARC_COLOR_LEGEND", "") or "").split(","):
            if "=" in seg:
                g, n = seg.split("=", 1); names[g.strip()] = n.strip()
        return chars, names
    def _sbx_is_glyph_script(ch):
        o = ord(ch)
        return 0xAC00 <= o <= 0xD7A3 or 0x4E00 <= o <= 0x9FFF or 0x0D00 <= o <= 0x0D7F or 0x1F300 <= o <= 0x1FAFF
    def _sbx_nearest(ch, chars):
        def jamo(c):
            o = ord(c) - 0xAC00
            return (o // 588, (o % 588) // 28, o % 28) if 0 <= o <= 11171 else None
        a = jamo(ch)
        def dist(g):
            b = jamo(g)
            if a is not None and b is not None:
                return (sum(x != y for x, y in zip(a, b)), abs(ord(ch) - ord(g)))
            return (3, abs(ord(ch) - ord(g)))
        return min(chars, key=dist) if chars else None
    def _sbx_glyph_literals(tree):
        """String constants the code compares against or filters with (==, !=, in, color=...)."""
        out = []
        def consts(e):
            if isinstance(e, _sbx_ast.Constant) and isinstance(e.value, str):
                yield e.value
            elif isinstance(e, (_sbx_ast.Set, _sbx_ast.List, _sbx_ast.Tuple)):
                for x in e.elts:
                    yield from consts(x)
            elif isinstance(e, _sbx_ast.Call) and isinstance(e.func, _sbx_ast.Name) and e.func.id in ("set", "frozenset", "list", "tuple") and e.args:
                yield from consts(e.args[0])
        for n in _sbx_ast.walk(tree):
            if isinstance(n, _sbx_ast.Compare):
                for e in [n.left] + list(n.comparators):
                    out.extend(consts(e))
            elif isinstance(n, _sbx_ast.Call):
                for kw in n.keywords:
                    if kw.arg in ("color", "colour", "col", "c", "ch", "colors", "colours"):
                        out.extend(consts(kw.value))
                for a in n.args:
                    if isinstance(a, _sbx_ast.Constant) and isinstance(a.value, str) and 0 < len(a.value) <= 3:
                        out.append(a.value)
            elif isinstance(n, _sbx_ast.Dict):
                for k in n.keys:
                    if k is not None:
                        out.extend(consts(k))
        return out
    def _sbx_notes(agent, code, store_before, renamed, dropped, shadowed):
        notes = []
        seen_sh = agent.__dict__.setdefault("_sbx_shadow_seen", set())
        for nm, sig in shadowed.items():
            if nm not in seen_sh:
                seen_sh.add(nm)
                notes.append(f"your `{sig}` now replaces the native `{nm}` for the rest of this game; later calls to {nm}() run yours.")
        for old, new in renamed.items():
            notes.append(f"`{old}` is the harness's own function: your version ran in this call only and is saved as `{new}` for later calls.")
        for name in dropped:
            notes.append(f"`{name}` was not saved: it does not compile on its own.")
        try:
            tree = _sbx_ast.parse(code)
        except SyntaxError:
            return notes
        acts = any(isinstance(n, _sbx_ast.Call) and isinstance(n.func, _sbx_ast.Name) and n.func.id in ("action", "act_until") for n in _sbx_ast.walk(tree))
        if acts:
            used = {n.id for n in _sbx_ast.walk(tree) if isinstance(n, _sbx_ast.Name)}
            fns = [n for n in _sbx_ast.walk(tree) if isinstance(n, _sbx_ast.FunctionDef)]
            for nm, src in store_before.items():
                if nm in used:
                    try:
                        fns += [n for n in _sbx_ast.parse(src).body if isinstance(n, _sbx_ast.FunctionDef)]
                    except SyntaxError:
                        pass
            for f in fns:
                ds = [d for d in f.args.defaults + f.args.kw_defaults if d is not None]
                hit = next((d for d in ds if {x.id for x in _sbx_ast.walk(d) if isinstance(x, _sbx_ast.Name)} & _SBX_RUNTIME), None)
                if hit is not None:
                    notes.append(f"`{f.name}(... ={_sbx_ast.unparse(hit)})` captured the board when it was defined; after action() it still reads the "
                                 f"old board. Use `=None` and `f = f or current_frame` inside.")
                    break
        chars, names = _sbx_legend()
        if chars and any(_sbx_is_glyph_script(c) for c in chars):
            seen = agent.__dict__.setdefault("_sbx_glyph_seen", set())
            for s in _sbx_glyph_literals(tree):
                for ch in s:
                    if _sbx_is_glyph_script(ch) and ch not in chars and ch not in seen:
                        seen.add(ch); g = _sbx_nearest(ch, chars)
                        notes.append(f"'{ch}' is not a board glyph (nearest: {g}={names.get(g, '?')}); a filter on it matches nothing.")
        return notes

    def _sbx_with_notes(text, notes):
        """Prepend into stdout (cell_recall's pattern): the payload stays valid JSON, and _render_tool_result_display shows
        stdout first, so the note reaches both the model and the event transcript. ensure_ascii=False keeps glyphs (findings 98)."""
        if not notes:
            return text
        block = "\n".join("note: " + n for n in notes)
        try:
            obj = _sbx_json.loads(text)
            if isinstance(obj, dict):
                obj["stdout"] = block + "\n" + (obj.get("stdout") or "")
                return _sbx_json.dumps(obj, indent=2, ensure_ascii=False)
        except Exception:
            pass
        return block + "\n" + text

    def _sbx_run_python_tool(self, state_path, arguments):
        store = self.__dict__.setdefault("_nat_defs", {}) if _NAT_PERSIST else {}
        before = dict(store)
        code = str((arguments or {}).get("code", "")).rstrip()
        pre = _nat_preamble(store); offset = pre.count("\n")
        res = _nat_orig_run(self, state_path, {**(arguments or {}), "code": pre + code})
        renamed, dropped, shadowed = {}, [], {}
        if _NAT_PERSIST:
            harvested, renamed, dropped, shadowed = _sbx_harvest_full(code)
            store.update(harvested)
        txt = getattr(res, "content", None) if not isinstance(res, str) else res
        if isinstance(txt, str):
            new = _nat_fix_lines(txt, offset) if "<python_tool>" in txt else txt
            try:
                new = _sbx_with_notes(new, _sbx_notes(self, code, before, renamed, dropped, shadowed))
            except Exception as exc:   # a note must never cost the call
                print(f"SANDBOX FIXES: notes failed: {exc!r}", flush=True)
            if new != txt:
                try:
                    res = new if isinstance(res, str) else _sbx_dc.replace(res, content=new)   # keeps step_executed
                except Exception:
                    pass
        return res
    _sbx_ta.ToolAgent._run_python_tool = _sbx_run_python_tool

    # ---------------- P1: tool description and prompt text ------------------------------------------------------------
    _SBX_DOC = (" NATIVES: `objs(frame=None, min_pixels=1, color=None)` -> list of dicts: id, color, pixels, hash, r0, c0, r1, c1, h, w, "
                "cr, cc, bbox, centre, children; `diff(a=None, b=None)` -> changed cells between previous_frame and current_frame "
                "(len(d) = changed count; d['cells'], d[:k] and `for r, c, old, new in d` give cells; also d['pairs'], d['bbox']); "
                "`grid(cell=4)` -> a coarse one-char-per-cell view; `act_until(actions, stop=(...))` -> run a sequence and stop on "
                "level_completed/game_over.")
    _sbx_d = _sbx_ta._PYTHON_TOOL_DESCRIPTION
    _sbx_ta._PYTHON_TOOL_DESCRIPTION = _sbx_edit(_sbx_d, _NAT_DOC, _SBX_DOC, "natives doc in the tool description")
    def _sbx_tools(self, state_path):
        tools = _nat_orig_tools(self, state_path)   # stock _tools reads the patched description once: no second append
        for t in tools:
            fn = t.get("function", {}) if isinstance(t, dict) else {}
            if fn.get("name") == "python" and _NAT_PERSIST:
                p = fn.get("parameters", {}).get("properties", {}).get("code", {})
                if "ephemeral" in p.get("description", ""):
                    p["description"] = "Python code to run. Your top-level functions and classes persist across calls in this game; other variables do not."
        return tools
    _sbx_ta.ToolAgent._tools = _sbx_tools
    if _NAT_PERSIST:
        _sbx_swaps = (
            ("- Every `python` tool call starts fresh. Re-import modules or re-define any custom utility logic you need.\n",
             "- Every `python` tool call runs in a fresh process. Your top-level functions and classes are saved and re-run for you; "
             "variables are not. The allowed modules and Counter, deque, defaultdict are already imported.\n"),
            ("- The `python` tool code is not saved between calls, so rewrite any custom utility logic you still need.\n",
             "- Your top-level functions and classes from earlier `python` calls are saved for this game; variables are not.\n"),
            ("call it with one persistent-for-your-defs `code` string", "call it with one `code` string"),
            ("operator, random, re, statistics, string.\n", "operator, random, re, statistics, string, hashlib.\n"),
        )
        for _old, _new in _sbx_swaps:
            _hits = 0
            for _mod in _sbx_pr_mods:
                for _k, _v in list(vars(_mod).items()):
                    if isinstance(_v, str) and _old in _v:
                        setattr(_mod, _k, _v.replace(_old, _new)); _hits += 1
            assert _hits >= 1, f"sandbox fixes: prompt sentence not found: {_old[:60]!r}"
    print("SANDBOX FIXES installed: class/hashlib/.step in the sandbox; pre-imports, objs bbox/centre, diff len/iter/slice; "
          "reserved native names + compile-alone persistence; line numbers + notes in tool results; natives doc once", flush=True)
