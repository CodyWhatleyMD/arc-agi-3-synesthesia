"""SANDBOX HYGIENE (comparison #6, 10-02). Opt-in: DUCK_SANDBOX=1 or 2. Unset / 0: this cell changes NOTHING.

Source: prototype notebooks_duck/prototypes_1001/cell_duck_sandbox_fixes.py = design 0 of intervention 5 in
notes/opus_vs_flashnext_2026-10-01/workflow_result.json (both judges' pick), re-measured on five Kaggle runs of our quant
(q25, B, q25-fx, q25-ref, A: 9,547 python calls, 830 errors) and rebuilt to leave the turn RULE alone: it never replaces
ToolAgent._run_python_tool's step_executed logic (the natives wrapper keeps doing exactly what it did: the bundle copy drops
step_executed on a traceback, the repo copy keeps it), it adds no new data channel, and level 1 adds no prompt text.
What it does change in turn structure (measured, tests/cmp_fixes/f6-sandbox/cost_f6.json "turn_structure"): a call that
acted and then raised one of the errors fixed here no longer raises, so it ends the turn like any successful acting call
(the bundle let the turn continue) -- q25 10, B 23, v10 17 calls per 25-game run, of the 37 / 30 / 21 that FIXES=1's rule
change ended; and 31 calls in 9,539 replayed execute more actions (a loop that crashed now completes).
Replay of 6 recorded runs through the real chain (q25, B, v10, fx, ref, A; 9,539 calls): 317 errors fixed, 0 clean calls
turned into errors. Each python call costs +8 ms (27.6 -> 35.7 ms: the pre-imports).

DUCK_SANDBOX=1 -- RUNTIME ONLY (no prompt / tool-text change; the model sees a difference only in the result of a call that
                  touched one of these; measured cost per request: tests/cmp_fixes/f6-sandbox/cost_f6.json)
  B1 sandbox bootstrap (assert-once edits on python_tool_sandbox._SANDBOX_BOOTSTRAP, which run_sandboxed_python reads at
     call time):
       - history[i] / transitions[i] / last_transition gain .step and .level (their frame's)   57 errors in the 5 runs
       - `class` works: __build_class__ + object/super/staticmethod/classmethod/property, __name__ = "__main__"   9
       - hashlib, difflib, unicodedata importable (pure computation; pickle/sys/time/builtins stay blocked)      7
       - after every action(), every top-level FUNCTION object (a def, or a lambda bound to a name) whose DEFAULT
         argument is the pre-action current_frame / previous_frame / history / ... object gets the refreshed object
         (def f(fr=current_frame) read the old board after action(): g50t "blob stuck", sp80 "UP blocked"). Other
         variables (`before = current_frame`) are NOT touched. Deliberate consequence (review 10-03): a default meant as a
         BASELINE also follows the live frame (`def moved(base=current_frame): return diff(base, current_frame)` reads 0
         after action(), 6 on the shipped chain), and a default aliasing history[0].frame while it is previous_frame moves
         too; all 72 recorded frame-default defs (6 corpora, 10,539 calls) use the live idiom.
  N1 natives source (cell_duck_natives' _NAT_SRC, read by _nat_preamble at call time):
       - the 14 allowed modules + Counter/deque/defaultdict pre-imported                                       30 NameErrors
       - objs() dicts answer o['bbox'] (r0,c0,r1,c1), o['centre'] (cr,cc), o['boundary'] and .get() of them,
         LAZILY: the keys are not stored, so printing an objs() dict costs no extra tokens                      64 KeyErrors
       - diff(): len(d) / bool(d) = changed-cell count (was the dict's 6 keys, always truthy), `for r, c, old, new
         in d`, d[i], d[:k] go over the cells; d['pairs'][:k] works; every string key as before                ~93 KeyErrors
                                                                                                    + 53 silent "6 cells"
         Deliberate semantic change (review 10-03): iterating a diff yields CELLS, not keys, so `for k in d: d[k]` now
         raises KeyError (pointing into harness code), list(d)/sorted(d) give cells, and type(diff()) is dict / type(objs()[0])
         is dict are False (both classes are NAMED dict). In the recorded corpora: 0 uses of the key-loop pattern, 0 type()
         checks, 60+ uses of d[:20] / `for cell in d` (what the model expects). `'bbox' in o` / `'centre' in o` answer True
         (o['bbox'] is the flat tuple (r0,c0,r1,c1); code expecting ((r0,c0),(r1,c1)) gets a TypeError instead of a KeyError).
  H1 persisted defs (natives' _nat_harvest, rebound around whatever is installed -- stock or FIXES=1's):
       - a def/class named like a sandbox-bound name (action, current_frame, history, ...) is not persisted
         (findings 151: a persisted `def action` = zero env steps for the rest of the game)
       - a def that does not compile on its own (`break` outside a loop, ...) is not persisted (findings 151: every
         later call of the game was a syntax error). A def named like a NATIVE still replaces it (renaming those broke
         76 of 307 replayed q25 calls that used the model's own objs/grid).
  R1 traceback line numbers relative to the model's code: the shipped regex never matched the JSON-escaped
     `<python_tool>\\", line N` nor `(<python_tool>, line N)`, so a 10-line snippet reported line 448.
  The pre-imports run inside a try block (review 10-03): a failing import can never break every call's preamble; a
  failure in this cell's persisted-def checks returns what the wrapped harvest returned.
LOCAL A/B CAVEAT (review 10-03): ab_local execs the REPO notebooks_duck/cell_duck_natives.py, which keeps step_executed on
  a traceback; Kaggle's cell 14 execs the BUNDLE copy, which drops it. Level 1's main turn-structure change on Kaggle (an
  acting call that used to raise now runs clean and ends the turn: 17 calls on v10, 22 on B) therefore does NOT exist in a
  local run -- there those turns already end. A local f6 A/B cannot show that mechanism; only a Kaggle (bundle) run can.
DUCK_SANDBOX=2 -- level 1 plus TEXT and NOTES
  P1 the tool description carries the natives doc once (it was appended twice: findings 151, ~250 tokens per request);
     with persisted defs on, the three prompt sentences that said "starts fresh / not saved / persistent-for-your-defs"
     say what persists and that the allowed modules are pre-imported.
  N2 one-line notes prepended to the call's stdout (cell_recall's pattern: valid JSON, visible in the transcript):
     a def that was not persisted (sandbox name / does not compile), a def that replaces a native (once per name per
     game), a string literal with a glyph that is not on the board's legend (once per glyph per game), `.ascii[r][c]`
     (once per game: .ascii is one string, .ascii[r] is a character). The glyph lint reads only comparisons (==, !=, in),
     colour keyword arguments and dict keys (review 10-03: it also flagged any 1-3 character Hangul/CJK string passed
     positionally, e.g. print('세')); a replaced native's signature in a note is capped at 80 characters. Notes are
     prepended after the tool output's truncation, so a call with notes can exceed the tool-output budget by their length
     (a few dozen tokens per note, each at most once per name / glyph per game).
Not done, on purpose (the challenger's and the judges' reasons): no persistence of module-level variables (frame snapshots
would turn a loud NameError into a silent stale read), no live-proxy current_frame (11 q25 calls keep `before =
current_frame` across action() on purpose), no renaming of shadowed natives, no `time` / `pickle` / `open`.

Load order (shared exec namespace, findings 79; every module-level name here is _sbx_* / _SBX_*): AFTER cell_duck_natives.py
(it rebinds natives globals that _nat_run_python_tool reads at call time; with FIXES=1 the natives text is patched first and
this composes with it), BEFORE cell_duck_xgame.py / cell_recall.py (they wrap whatever _run_python_tool is installed) and
before the arm cell (the glyph lint reads grid_utils' legend at call time, so it sees the low-norm carrier).
Anchors are assert-exactly-once text edits computed BEFORE anything is installed (all or nothing). A drifted anchor raises on
a validation run; when TRUE_SUBMISSION is True (the hidden rerun) it prints and installs nothing (shipped behaviour).
"""
import os as _sbx_os

_SBX_LEVEL = (_sbx_os.environ.get("DUCK_SANDBOX", "0") or "0").strip()
if _SBX_LEVEL not in ("0", "1", "2"):
    raise ValueError(f"DUCK_SANDBOX must be 0, 1 or 2, got {_SBX_LEVEL!r}")


def _sbx_install(level, namespace):
    import ast, dataclasses, json, re, threading
    import __future__ as fut
    import inference.agent.python_tool_sandbox as pts
    import inference.agent.tool_agent as ta
    import inference.agent.prompts as pr
    import inference.utils.grid_utils as gu

    if getattr(pts, "_sbx_installed", None):
        print(f"SANDBOX HYGIENE: already installed (level {pts._sbx_installed}) -- not installing twice", flush=True)
        return None

    def edit(text, old, new, what):
        n = text.count(old)
        if n != 1:
            raise RuntimeError(f"SANDBOX HYGIENE: anchor for {what} found {n} times (want exactly 1) -- harness drifted")
        return text.replace(old, new)

    commits = []    # (label, thunk): run only after every anchor below has matched
    done = []

    # ------------------------------------------------------------------ B1: sandbox bootstrap -------------------------------
    B = pts._SANDBOX_BOOTSTRAP
    B = edit(B, '    "zip",\n', '    "zip",\n    "__build_class__",\n    "object",\n    "super",\n    "staticmethod",\n'
                                 '    "classmethod",\n    "property",\n', "SAFE_BUILTINS")
    B = edit(B, '    "string",\n', '    "string",\n    "hashlib",\n    "difflib",\n    "unicodedata",\n', "SAFE_MODULES")
    B = edit(B, '        "result": None,\n', '        "result": None,\n        "__name__": "__main__",\n', "runtime_globals __name__")
    B = edit(B, '        self.frame = frame\n',
             '        self.frame = frame\n        self.step = getattr(frame, "step", None)\n        self.level = getattr(frame, "level", None)\n',
             "HistoryEntryView .step/.level")
    B = edit(B, '        self.frame = after_frame\n',
             '        self.frame = after_frame\n        self.step = getattr(after_frame, "step", None)\n'
             '        self.level = getattr(after_frame, "level", None)\n', "TransitionView .step/.level")
    B = edit(B, '        action_results.append(action_result)\n        _refresh_state(reply.get("state") or {})\n',
             '        action_results.append(action_result)\n'
             '        _sbx_old = [runtime_globals.get(_k) for _k in ("current_frame", "latest_frame", "previous_frame", '
             '"last_action_frame", "last_transition", "history", "transitions")]\n'
             '        _refresh_state(reply.get("state") or {})\n'
             '        try:  # SANDBOX HYGIENE: defaults that captured a pre-action frame get the refreshed one\n'
             '            _sbx_map = {id(_o): runtime_globals.get(_k) for _k, _o in zip(("current_frame", "latest_frame", '
             '"previous_frame", "last_action_frame", "last_transition", "history", "transitions"), _sbx_old) if _o is not None}\n'
             '            for _f in list(runtime_globals.values()):\n'
             '                if type(_f).__name__ != "function":\n'
             '                    continue\n'
             '                _d = _f.__defaults__\n'
             '                if _d and any(id(_x) in _sbx_map for _x in _d):\n'
             '                    _f.__defaults__ = tuple(_sbx_map[id(_x)] if id(_x) in _sbx_map else _x for _x in _d)\n'
             '                _kd = _f.__kwdefaults__\n'
             '                if _kd and any(id(_x) in _sbx_map for _x in _kd.values()):\n'
             '                    _f.__kwdefaults__ = {_n: (_sbx_map[id(_x)] if id(_x) in _sbx_map else _x) for _n, _x in _kd.items()}\n'
             '        except Exception:\n'
             '            pass\n', "action() default refresh")
    compile(B, "<sandbox bootstrap>", "exec")
    commits.append(("bootstrap", lambda: setattr(pts, "_SANDBOX_BOOTSTRAP", B)))
    done.append("bootstrap: .step/.level on history+transitions, class, hashlib/difflib/unicodedata, frame defaults refreshed after action()")

    # names the sandbox binds itself (a persisted def under one of these replaces it for the rest of the game)
    sandbox_names = set(re.findall(r'runtime_globals\[\s*"(\w+)"\s*\]', B)) | {"action", "result", "__builtins__", "__name__"}

    # ------------------------------------------------------------------ natives (only when the natives cell is installed) ----
    nat_run = namespace.get("_nat_run_python_tool")
    if nat_run is None and getattr(ta.ToolAgent._run_python_tool, "__name__", "") == "_nat_run_python_tool":
        nat_run = ta.ToolAgent._run_python_tool    # exec'd in a namespace of its own: reach the natives through the method
    NG = getattr(nat_run, "__globals__", None) or {}
    natives_on = bool(NG.get("_NAT_DOC")) and NG["_NAT_DOC"] in (ta._PYTHON_TOOL_DESCRIPTION or "")
    persist = natives_on and bool(NG.get("_NAT_PERSIST"))
    native_names = set()
    if natives_on:
        # N1: natives source
        S0 = NG["_NAT_SRC"]
        native_names = {n for n in re.findall(r"^def (\w+)", S0 + "\n" + (NG.get("_NAT_SRC_V2") or ""), re.M) if not n.startswith("_")}
        S = edit(S0, "        out.append({'id': n['id'],", "        out.append(_nat_obj(b, {'id': n['id'],", "objs() append")
        S = edit(S, "'children': list(n.get('children', []))})\n", "'children': list(n.get('children', []))}))\n", "objs() append close")
        S = edit(S, "def diff(a=None, b=None, limit=400):\n", "def _nat_diff_raw(a=None, b=None, limit=400):\n", "diff() def")
        # Sandbox-side code: no KeyError / class statement there (neither is a sandbox builtin at stock); `{}[k]` raises the
        # same KeyError(k) a plain dict would. A dict subclass's repr is dict.__repr__, so printing one costs what it did; the
        # classes are NAMED dict (module builtins) so print(type(d)) also prints <class 'dict'>, as the natives doc says.
        S = S + r'''# --- sandbox hygiene (harness-provided) ---
try:
    import collections, itertools, functools, heapq, bisect, math, re, json, copy, random, statistics, string, fractions, operator
    from collections import Counter, deque, defaultdict
except Exception:
    pass
def _nat_obj_missing(self, k):
    if k == 'bbox':
        return (self['r0'], self['c0'], self['r1'], self['c1'])
    if k in ('centre', 'center'):
        return (self['cr'], self['cc'])
    if k == 'boundary':
        return getattr(self, '_nat_b', [])
    return {}[k]
def _nat_obj_get(self, k, default=None):
    try:
        return self[k]
    except Exception:
        return default
def _nat_obj_contains(self, k):
    return k in ('bbox', 'centre', 'center', 'boundary') or dict.__contains__(self, k)
_NatObj = type('dict', (dict,), {'__missing__': _nat_obj_missing, 'get': _nat_obj_get, '__contains__': _nat_obj_contains,
                                 '__module__': 'builtins'})
def _nat_obj(b, d):
    o = _NatObj(d); o._nat_b = b
    return o
def _nat_pairs_getitem(self, k):
    return dict(list(self.items())[k]) if isinstance(k, slice) else dict.__getitem__(self, k)
_NatPairs = type('dict', (dict,), {'__getitem__': _nat_pairs_getitem, '__module__': 'builtins'})
def _nat_diff_getitem(self, k):
    return dict.__getitem__(self, 'cells')[k] if isinstance(k, (int, slice)) else dict.__getitem__(self, k)
_NatDiff = type('dict', (dict,), {'__getitem__': _nat_diff_getitem, '__module__': 'builtins',
                                  '__iter__': lambda self: iter(dict.__getitem__(self, 'cells')),
                                  '__len__': lambda self: dict.__getitem__(self, 'changed')})
def diff(a=None, b=None, limit=400):
    """Changed cells between two frames (default previous_frame -> current_frame): changed, cells [(r,c,old,new)], pairs {'old>new': n}, rows, cols, bbox. len(d) = changed; `for r, c, old, new in d`, d[i], d[:k] go over cells."""
    d = _nat_diff_raw(a, b, limit)
    d['pairs'] = _NatPairs(d['pairs'])
    return _NatDiff(d)
'''
        compile(S, "<natives source>", "exec")
        commits.append(("natives source", lambda: NG.__setitem__("_NAT_SRC", S)))
        done.append("natives: modules + Counter/deque/defaultdict pre-imported, objs bbox/centre/boundary (lazy), diff len/iter/slice")

        # R1: traceback line numbers, every form the tool content carries
        def _sbx_fix_lines(text, offset):
            def sub(m):
                n = int(m.group(2))
                return m.group(1) + str(n - offset if n > offset else n)
            text = re.sub(r'(<python_tool>(?:\\?", line |, line )|\(detected at line )(\d+)', sub, text)
            return re.sub(r"(<python_tool>:)(\d+)", sub, text)
        commits.append(("line fix", lambda: NG.__setitem__("_nat_fix_lines", _sbx_fix_lines)))
        done.append("traceback line numbers relative to the model's code")

    # H1: persisted defs -- wraps whatever harvest is installed (stock, or FIXES=1's)
    tls = threading.local()
    if persist:
        prev_harvest = NG["_nat_harvest"]

        def compiles_alone(seg):
            body = "\n".join("    " + ln for ln in seg.split("\n"))
            src = f"try:\n{body}\nexcept Exception:\n    pass\n"
            try:
                compile(src, "<persisted>", "exec", dont_inherit=True)                                         # the sandbox
                compile(src, "<persisted>", "exec", flags=fut.annotations.compiler_flag, dont_inherit=True)    # tool_agent's check
                return True
            except Exception:
                return False

        def _sbx_harvest(code):
            out = prev_harvest(code)
            try:
                return _sbx_filter(code, out)
            except Exception as exc:   # review 10-03: this cell's own checks must never cost the call
                print(f"SANDBOX HYGIENE: persisted-def check skipped ({type(exc).__name__}: {exc})", flush=True)
                return out

        def _sbx_filter(code, out):
            meta = getattr(tls, "meta", None)
            try:
                tree = ast.parse(code)
            except SyntaxError:
                return out
            bad = set()
            for node in tree.body:
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    continue
                seg = ast.get_source_segment(code, node) or ""
                if node.name in sandbox_names:
                    bad.add(node.name)
                    if meta is not None:
                        meta["reserved"].append(node.name)
                elif seg and not compiles_alone(seg):
                    bad.add(node.name)
                    if meta is not None:
                        meta["dropped"].append(node.name)
                elif meta is not None and node.name in native_names and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    sig = f"{node.name}({ast.unparse(node.args)})"
                    meta["shadowed"][node.name] = sig if len(sig) <= 80 else sig[:77] + "..."   # review 10-03: capped
            return {k: v for k, v in out.items() if k not in bad}
        _sbx_harvest._sbx_wraps = prev_harvest
        commits.append(("harvest", lambda: NG.__setitem__("_nat_harvest", _sbx_harvest)))
        done.append("persisted defs: sandbox-bound names and defs that do not compile alone are not saved")

    # ------------------------------------------------------------------ level 2: text + notes --------------------------------
    if level >= 2:
        if natives_on:
            d0 = ta._PYTHON_TOOL_DESCRIPTION
            suffix = NG["_NAT_DOC"] + (NG.get("_NAT_DOC_V2", "") if NG.get("_NAT_V2") else "") + (NG.get("_NAT_DOC_PERSIST", "") if persist else "")
            if not d0.endswith(suffix):
                raise RuntimeError("SANDBOX HYGIENE: the tool description does not end with the natives doc -- not the natives cell this was written against")
            base = d0[: len(d0) - len(suffix)]   # _nat_tools appends the natives doc to this once per request
            commits.append(("tool description", lambda: setattr(ta, "_PYTHON_TOOL_DESCRIPTION", base)))
            done.append("natives doc once in the tool description")
        if persist:
            swaps = (
                ("- Every `python` tool call starts fresh. Re-import modules or re-define any custom utility logic you need.\n",
                 "- Every `python` tool call runs in a fresh process. Your top-level functions and classes from earlier calls are re-run "
                 "for you; other variables are not. The allowed modules and Counter, deque, defaultdict are pre-imported.\n"),
                ("- The only tool is `python`; call it with one persistent-for-your-defs `code` string.\n",
                 "- The only tool is `python`; call it with one `code` string.\n"),
                ("- The `python` tool code is not saved between calls, so rewrite any custom utility logic you still need.\n",
                 "- Your top-level functions and classes from earlier `python` calls are saved for this game; other variables are not.\n"),
            )
            planned = []
            for old, new in swaps:
                hits_ta = [k for k, v in vars(ta).items() if isinstance(v, str) and old in v]
                if len(hits_ta) != 1 or vars(ta)[hits_ta[0]].count(old) != 1:
                    raise RuntimeError(f"SANDBOX HYGIENE: prompt sentence found {len(hits_ta)}x in tool_agent: {old[:60]!r}")
                for mod in (ta, pr):
                    for k, v in list(vars(mod).items()):
                        if isinstance(v, str) and old in v:
                            planned.append((mod, k, old, new))

            def _apply_swaps():
                for mod, k, old, new in planned:
                    setattr(mod, k, getattr(mod, k).replace(old, new))
            commits.append(("prompt sentences", _apply_swaps))
            done.append("prompt says what persists (3 sentences)")

        def legend():
            chars = str(getattr(gu, "ARC_COLOR_CHARS", "") or "")
            names = {}
            for seg in str(getattr(gu, "ARC_COLOR_LEGEND", "") or "").split(","):
                if "=" in seg:
                    g, n = seg.split("=", 1)
                    names[g.strip()] = n.strip()
            return chars, names

        def glyph_script(ch):
            o = ord(ch)
            return 0xAC00 <= o <= 0xD7A3 or 0x4E00 <= o <= 0x9FFF or 0x0D00 <= o <= 0x0D7F or 0x1F300 <= o <= 0x1FAFF

        def nearest(ch, chars):
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

        def glyph_literals(tree):
            """String constants the code compares against or filters with (==, !=, in, color=..., dict keys). (Review 10-03:
            no longer any short positional string -- print('세') is not a filter.)"""
            out = []

            def consts(e):
                if isinstance(e, ast.Constant) and isinstance(e.value, str):
                    yield e.value
                elif isinstance(e, (ast.Set, ast.List, ast.Tuple)):
                    for x in e.elts:
                        yield from consts(x)
                elif isinstance(e, ast.Call) and isinstance(e.func, ast.Name) and e.func.id in ("set", "frozenset", "list", "tuple") and e.args:
                    yield from consts(e.args[0])
            for n in ast.walk(tree):
                if isinstance(n, ast.Compare):
                    for e in [n.left] + list(n.comparators):
                        out.extend(consts(e))
                elif isinstance(n, ast.Call):
                    for kw in n.keywords:
                        if kw.arg in ("color", "colour", "col", "c", "ch", "colors", "colours"):
                            out.extend(consts(kw.value))
                elif isinstance(n, ast.Dict):
                    for k in n.keys:
                        if k is not None:
                            out.extend(consts(k))
            return out

        def ascii_double_index(tree):
            for n in ast.walk(tree):
                if (isinstance(n, ast.Subscript) and isinstance(n.value, ast.Subscript) and isinstance(n.value.value, ast.Attribute)
                        and n.value.value.attr == "ascii" and not isinstance(n.value.slice, ast.Slice)):
                    return True
            return False

        def notes_for(agent, code, meta):
            seen = agent.__dict__.get("_sbx_seen")
            rd = agent.__dict__.get("_session_runtime_dir")
            if not isinstance(seen, dict) or seen.get("dir") != rd:
                seen = agent.__dict__["_sbx_seen"] = {"dir": rd, "shadow": set(), "glyph": set(), "ascii": False}
            notes = []
            for name in meta["reserved"]:
                notes.append(f"`{name}` is a name the sandbox binds itself: your definition ran in this call only and was not saved for later calls.")
            for name in meta["dropped"]:
                notes.append(f"`{name}` was not saved for later calls: it does not compile on its own.")
            for name, sig in meta["shadowed"].items():
                if name not in seen["shadow"]:
                    seen["shadow"].add(name)
                    notes.append(f"your `{sig}` replaces the harness's `{name}` for the rest of this game; later calls to {name}() run yours.")
            try:
                tree = ast.parse(code)
            except SyntaxError:
                return notes
            if not seen["ascii"] and ascii_double_index(tree):
                seen["ascii"] = True
                notes.append("`.ascii` is one string: `.ascii[r]` is its r-th character, not row r. Rows: `.ascii.split('\\n')[r][c]`.")
            chars, names = legend()
            if chars and any(glyph_script(c) for c in chars):
                for s in glyph_literals(tree):
                    for ch in s:
                        if glyph_script(ch) and ch not in chars and ch not in seen["glyph"]:
                            seen["glyph"].add(ch)
                            g = nearest(ch, chars)
                            notes.append(f"'{ch}' is not a board glyph (nearest: {g}={names.get(g, '?')}); a filter on it matches nothing.")
            return notes

        def with_notes(text, notes):
            """Prepend into stdout (cell_recall's pattern): the payload stays valid JSON, _render_tool_result_display shows stdout
            first, so the note reaches the model and the transcript. Re-dumped with tool_agent's own `json` (the unicode proxy
            from cell_duck_fixes when installed) exactly as _render_tool_payload dumped it (indent=2, same key order), so
            everything but stdout is byte-identical."""
            block = "\n".join("note: " + n for n in notes)
            try:
                obj = json.loads(text)
                if isinstance(obj, dict):
                    obj["stdout"] = block + "\n" + (obj.get("stdout") or "")
                    return ta.json.dumps(obj, indent=2)
            except Exception:
                pass
            return block + "\n" + text

        prev_run = ta.ToolAgent._run_python_tool

        def _sbx_run_python_tool(self, state_path, arguments):
            tls.meta = {"reserved": [], "dropped": [], "shadowed": {}}
            try:
                res = prev_run(self, state_path, arguments)
            finally:
                meta, tls.meta = tls.meta, None
            try:
                code = str((arguments or {}).get("code", ""))
                txt = res if isinstance(res, str) else getattr(res, "content", None)
                notes = notes_for(self, code, meta) if isinstance(txt, str) and code.strip() else []
                if notes:
                    new = with_notes(txt, notes)
                    res = new if isinstance(res, str) else dataclasses.replace(res, content=new)   # every other field kept
            except Exception as exc:   # a note must never cost the call
                print(f"SANDBOX HYGIENE: notes skipped ({type(exc).__name__}: {exc})", flush=True)
            return res
        _sbx_run_python_tool.__wrapped__ = prev_run
        commits.append(("notes", lambda: setattr(ta.ToolAgent, "_run_python_tool", _sbx_run_python_tool)))
        done.append("notes (unsaved defs, native replaced, off-legend glyph, .ascii[r][c])")

    for _label, thunk in commits:
        thunk()
    pts._sbx_installed = level
    print(f"SANDBOX HYGIENE INSTALLED level {level} (natives {'on' if natives_on else 'OFF: natives parts skipped'}, "
          f"persisted defs {'on' if persist else 'off'}): " + "; ".join(done), flush=True)
    return {"level": level, "natives": natives_on, "persist": persist, "parts": [c[0] for c in commits]}


if _SBX_LEVEL == "0":
    print("SANDBOX HYGIENE available but off (DUCK_SANDBOX=1 runtime fixes; =2 adds tool text + notes)", flush=True)
else:
    try:
        _sbx_report = _sbx_install(int(_SBX_LEVEL), globals())
    except Exception as _sbx_exc:
        if not bool(globals().get("TRUE_SUBMISSION", False)):
            raise
        _sbx_report = None
        print(f"SANDBOX HYGIENE NOT INSTALLED ({type(_sbx_exc).__name__}: {_sbx_exc}) -- TRUE_SUBMISSION: shipped behaviour", flush=True)
