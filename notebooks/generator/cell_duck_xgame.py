"""CROSS-GAME MEMORY for the Duck harness (09-30, findings 144 -- the investigator's idea: "learning from other games").

The rules allow it (read in full 09-30: nothing forbids memory across games within the 9-hour run). Duck plays the
110 hidden games x 3 passes in waves, passes-major (taaf/benchmark.py:138-155): a game in a later wave can know what
earlier waves learned, and pass 1 of a game can know what its pass 0 verified. This cell keeps, process-wide:
  (a) a LIBRARY of helper functions the model defined that were followed by a level clear in their game,
  (b) a LEDGER of mechanics the model asserted via a tiny native `remember(fact, evidence)` AND that were followed by
      a level clear within N actions (unverified facts never propagate),
  (c) a per-game DIGEST at game end (levels, per-level actions, last world model, which library helpers were called),
and for each NEW game prepends one compact block ("What earlier games in this run taught") to its first user turn: the
top-K verified facts (ranked by how many games confirmed them, then how many clears) and the library helpers'
names+signatures; the helper BODIES are seeded into the sandbox through the natives' persisted-defs store, so they are
callable like `objs()`. Only FINISHED game-passes contribute (finish_game is the gate); nothing is taken from one still
in progress; no frames, boards or coordinates are stored -- only the model's own abstractions.

Unit of memory = one game-pass (Duck's run stem `<game>_p<pass>`: framework/solver.py:1253). The passes of one game are
separate Game objects that run CONCURRENTLY under one semaphore (solver.py:896-920), so keying by game id would expose
the in-progress passes the moment one pass finished. DUCK_XGAME_SAME_GAME=0 hides a game's earlier passes from its
later ones (pure cross-game transfer; default 1 = passes learn from each other too).

Mechanism (monkeypatch only; the vendored harness stays byte-identical; shared exec namespace -> every name `_xg_*`):
  - ToolAgent.analyze (tool_agent.py:1706): learn the game-pass stem from state_path before the first prompt is built.
  - ToolAgent._build_user_prompt (:1161): prepend the block to the first prompt of each game-pass.
  - ToolAgent._tools (:1258) + _PYTHON_TOOL_DESCRIPTION: tell the model `remember()` exists (the natives' pattern; the
    block alone cannot, because the first wave of games has no block yet).
  - ToolAgent._run_python_tool (:1453; wrapping whatever is installed -- the natives go first): seed `remember` + the
    library into `self._nat_defs` before the call; after it, count helper calls, bank the facts remember() emitted, and
    on a level clear verify pending facts and promote defs. A clear is `_last_step_summary["level_transition"]` (:1063)
    from THIS call: the summary object only changes when the call executed an action, so identity is compared.
  - tool_agent.run_sandboxed_python (module global, resolved at call time): pull the `@@XG|...` marker lines that
    `remember()` prints out of the RAW stdout before _render_tool_payload truncates it; the model never sees them.
  - taaf.game.Game.finish_game (game.py:600): mark the game-pass complete, write its digest, dump the store to
    <artifacts>/xgame_store.json. play() and finish_game() run on the same worker thread, which resolves the stem.
  Per game-pass counters in the store (plan 10-03 mechanism readout): helpers_called, remember_calls, facts_verified, clears.
Enable with DUCK_XGAME=1 (default off: v5 behaviour is byte-identical). Requires DUCK_NATIVES=1 and DUCK_PERSIST_DEFS=1
(the seeding rides the persisted-defs store); the cell refuses to install otherwise.
"""
import os as _xg_os, re as _xg_re, ast as _xg_ast, json as _xg_json, hashlib as _xg_hashlib, threading as _xg_threading, time as _xg_time
from pathlib import Path as _xg_Path
import inference.agent.tool_agent as _xg_ta

_XG_ON = _xg_os.environ.get("DUCK_XGAME", "0") == "1"
_XG_N_ACTIONS = int(_xg_os.environ.get("DUCK_XGAME_VERIFY_WINDOW", "60"))    # a fact counts if a clear follows within N actions
_XG_LIB_CAP = int(_xg_os.environ.get("DUCK_XGAME_LIB_CAP", "40"))            # helpers retained (newest wins)
_XG_TOP_LIB = int(_xg_os.environ.get("DUCK_XGAME_TOP_LIB", "15"))            # helpers seeded + listed per new game
_XG_TOP_FACTS = int(_xg_os.environ.get("DUCK_XGAME_TOP_FACTS", "12"))
_XG_BLOCK_CHARS = int(_xg_os.environ.get("DUCK_XGAME_BLOCK_CHARS", "5000"))  # ~1,400 Qwen tokens (test_xgame.py measures it)
_XG_SAME_GAME = _xg_os.environ.get("DUCK_XGAME_SAME_GAME", "1") == "1"
_XG_MARK = "@@XG|"

_xg_lock = _xg_threading.RLock()
_xg_tls = _xg_threading.local()
_XG = {"library": {}, "facts": [], "pending": {}, "games": {}, "seq": 0, "artifacts_dir": None}
# library: name -> {name, src, hash, game(stem), level, seq, uses}; facts: [{fact, evidence, game(stem), level, action_num, clears, seq}]
# pending: stem -> [{fact, evidence, action_num, level, seq}]; games: stem -> {base, complete, helpers_called, facts_verified,
# clears, note, levels, number_of_levels, actions, actions_per_level, state, final_score, solver_note, started_at, finished_at}

_XG_REMEMBER_SRC = '''def remember(fact, evidence=""):
    """Record a game mechanic you have VERIFIED by acting (e.g. "ACTION3 rotates the blue piece clockwise", evidence
    "turns 12-14: three ACTION3 presses returned it to the start"). Facts recorded shortly before a level clear are
    carried to later games in this run; unverified ones are not. Keep both under 240 characters; no coordinates."""
    print("@@XG|" + repr((str(fact)[:240], str(evidence)[:240])))
'''
_XG_TOOL_DOC = (" CROSS-GAME MEMORY: `remember(fact, evidence)` -> record a game mechanic you have VERIFIED by acting (two short strings, "
                "no coordinates); facts recorded shortly before a level clear are carried to later games in this run, unverified ones are not.")

def _xg_stem(state_path):
    """Duck's run stem from its runtime-state path: .../artifacts/<game>_p<pass>_tool_runtime_state.json -> <game>_p<pass>."""
    return _xg_re.sub(r"_tool_runtime_state$", "", _xg_Path(str(state_path)).stem)

def _xg_base(stem):
    return _xg_re.sub(r"_p\d+$", "", stem)

def _xg_artifact_stem(game_id):
    """== inference.framework.solver.artifact_stem (not imported: that module drags the whole framework in)."""
    return _xg_re.sub(r"[^A-Za-z0-9_.-]+", "_", str(game_id))

def _xg_hash(src):
    return _xg_hashlib.sha1(src.encode()).hexdigest()[:12]

def _xg_sig(src):
    """'name(a, b=1)' from a def's source, for the prompt block."""
    try:
        node = _xg_ast.parse(src).body[0]
        if isinstance(node, (_xg_ast.FunctionDef, _xg_ast.AsyncFunctionDef)):
            return f"{node.name}({_xg_ast.unparse(node.args)})"
        if isinstance(node, _xg_ast.ClassDef):
            return f"class {node.name}"
    except Exception:
        pass
    return src.split("\n", 1)[0][:80]

def _xg_doc(src):
    try:
        return " ".join((_xg_ast.get_docstring(_xg_ast.parse(src).body[0]) or "").split())[:120]
    except Exception:
        return ""

def _xg_game(stem):
    """The ledger row of a game-pass (caller holds the lock)."""
    return _XG["games"].setdefault(stem, {"base": _xg_base(stem), "complete": False, "helpers_called": {}, "facts_verified": 0,
                                          "remember_calls": 0, "clears": 0, "note": "", "started_at": _xg_time.time()})

def _xg_eligible(for_stem=None):
    """Finished game-passes whose material a NEW game-pass may see (caller holds the lock)."""
    done = {s for s, g in _XG["games"].items() if g.get("complete")}
    if not _XG_SAME_GAME and for_stem:
        b = _xg_base(for_stem)
        done = {s for s in done if _XG["games"][s]["base"] != b}
    return done

def _xg_ranked_facts(done):
    """Verified facts from `done`, merged by text; ranked by (#distinct games that confirmed it, #clears, recency)."""
    merged = {}
    for f in _XG["facts"]:
        if f["game"] not in done:
            continue
        m = merged.setdefault(" ".join(f["fact"].lower().split()), {"fact": f["fact"], "evidence": f["evidence"], "games": set(), "clears": 0, "seq": 0})
        m["games"].add(_xg_base(f["game"])); m["clears"] += f["clears"]
        if f["seq"] > m["seq"]:
            m["seq"] = f["seq"]; m["evidence"] = f["evidence"]
    return sorted(merged.values(), key=lambda m: (-len(m["games"]), -m["clears"], -m["seq"]))

def _xg_library_for(done):
    lib = [v for v in _XG["library"].values() if v["game"] in done]
    lib.sort(key=lambda v: (-v["uses"], -v["seq"]))
    return lib[:_XG_TOP_LIB]

def _xg_block(for_stem=None):
    """The first-turn block: ranked verified facts + library signatures, whole lines only, under _XG_BLOCK_CHARS."""
    with _xg_lock:
        done = _xg_eligible(for_stem)
        facts = _xg_ranked_facts(done)[:_XG_TOP_FACTS]
        lib = _xg_library_for(done)
        n_done = len(done)
    if not facts and not lib:
        return ""
    head = (f"What earlier games in this run taught ({n_done} finished game-pass{'es' if n_done != 1 else ''}; the games differ -- "
            "treat these as hypotheses to test cheaply, not as rules):")
    tail = "Use remember(fact, evidence) when you have VERIFIED a mechanic by acting; it is carried to later games in this run."
    fact_lines = []
    for m in facts:
        ev = f" (evidence: {m['evidence'][:120]})" if m["evidence"] else ""
        tag = f" [{len(m['games'])} games]" if len(m["games"]) > 1 else ""
        fact_lines.append(f"- {m['fact'][:200]}{ev}{tag}")
    lib_lines = [f"- {_xg_sig(v['src'])}" + (f" -- {_xg_doc(v['src'])}" if _xg_doc(v["src"]) else "") for v in lib]
    lib_head = "Helpers from earlier games are already defined in your python tool (call them like objs()):"
    budget = _XG_BLOCK_CHARS - len(head) - len(tail) - 2
    lines, used = [head], 0
    for ln in fact_lines:                                   # facts take at most 65% when helpers want room too
        if used + len(ln) + 1 > (int(budget * 0.65) if lib_lines else budget):
            break
        lines.append(ln); used += len(ln) + 1
    for i, ln in enumerate(lib_lines):
        extra = len(lib_head) + 1 if i == 0 else 0
        if used + extra + len(ln) + 1 > budget:
            break
        if i == 0:
            lines.append(lib_head); used += extra
        lines.append(ln); used += len(ln) + 1
    lines.append(tail)
    return "\n".join(lines)

def _xg_seed(agent, stem):
    """Once per game-pass, before its first python call: `remember` + the eligible library go into the persisted store."""
    if agent.__dict__.get("_xg_seeded_for") == stem:
        return
    store = agent.__dict__.setdefault("_nat_defs", {})
    seeded = agent.__dict__.setdefault("_xg_seeded", {})
    agent.__dict__["_xg_seeded_for"] = stem
    store["remember"] = _XG_REMEMBER_SRC; seeded["remember"] = "native"
    with _xg_lock:
        lib = _xg_library_for(_xg_eligible(stem))
    for v in lib:
        if v["name"] != "remember" and v["name"] not in store:
            store[v["name"]] = v["src"]; seeded[v["name"]] = v["hash"]

def _xg_after_call(agent, stem, code, summary_before):
    """After a python call: count helper uses, bank remember()ed facts, and on a clear verify + promote."""
    seeded = agent.__dict__.get("_xg_seeded", {})
    store = agent.__dict__.get("_nat_defs", {})
    lar = agent.__dict__.get("_last_action_result") or {}
    try:
        action_num = int(lar.get("action_num") or 0)
    except (TypeError, ValueError):
        action_num = 0
    try:
        level = int(lar.get("level") or 0)
    except (TypeError, ValueError):
        level = 0
    summary = agent.__dict__.get("_last_step_summary")
    cleared = bool(summary) and summary is not summary_before and bool(summary.get("level_transition"))
    wm = agent.__dict__.get("_summarized_knowledge") or {}
    note = " | ".join(f"{k}: {str(wm.get(k))[:300]}" for k in ("world_model", "action_model") if isinstance(wm, dict) and wm.get(k))
    new_facts = list(getattr(_xg_tls, "facts", None) or []); _xg_tls.facts = []
    with _xg_lock:
        g = _xg_game(stem)
        if note:
            g["note"] = note
        for name, h in seeded.items():
            if h != "native" and _xg_re.search(r"(?<!def )\b" + _xg_re.escape(name) + r"\s*\(", code):
                g["helpers_called"][name] = g["helpers_called"].get(name, 0) + 1
                if name in _XG["library"]:
                    _XG["library"][name]["uses"] += 1
        g["remember_calls"] = g.get("remember_calls", 0) + len(new_facts)   # every remember() the model made (verified or not): a mechanism counter
        for fact, evidence in new_facts:
            _XG["seq"] += 1
            _XG["pending"].setdefault(stem, []).append({"fact": fact, "evidence": evidence, "action_num": action_num, "level": level, "seq": _XG["seq"]})
        if not cleared:
            return
        g["clears"] += 1
        for p in _XG["pending"].get(stem, []):
            if action_num - p["action_num"] <= _XG_N_ACTIONS:      # the clear came soon after the assertion: verified
                same = next((f for f in _XG["facts"] if f["game"] == stem and f["fact"] == p["fact"]), None)
                if same:
                    same["clears"] += 1
                else:
                    _XG["facts"].append({**p, "game": stem, "clears": 1}); g["facts_verified"] += 1
            # older pending facts expire here: a later clear would be even further from the assertion
        _XG["pending"][stem] = []
        for name, src in store.items():
            if name == "remember":
                continue
            h = _xg_hash(src)
            if seeded.get(name) == h:
                continue                                          # an untouched library seed: not this game's own work
            cur = _XG["library"].get(name)
            if cur is None or cur["hash"] != h:                   # new helper, or a redefinition (newest wins)
                _XG["seq"] += 1
                _XG["library"][name] = {"name": name, "src": src, "hash": h, "game": stem, "level": level, "seq": _XG["seq"], "uses": 0}
        if len(_XG["library"]) > _XG_LIB_CAP:
            for name in sorted(_XG["library"], key=lambda n: _XG["library"][n]["seq"])[: len(_XG["library"]) - _XG_LIB_CAP]:
                del _XG["library"][name]

def _xg_wrap_run_python(orig):
    def _run_python_tool(self, state_path, arguments):
        stem = _xg_stem(state_path)
        try:
            self.__dict__["_xg_stem"] = stem; _xg_tls.stem = stem
            with _xg_lock:
                _xg_game(stem)
                if _XG["artifacts_dir"] is None:
                    _XG["artifacts_dir"] = str(_xg_Path(str(state_path)).parent)
            _xg_seed(self, stem)
        except Exception as e:
            print(f"XGAME: seed hook error {type(e).__name__}: {e}", flush=True)
        _xg_tls.facts = []
        before = self.__dict__.get("_last_step_summary")
        code = str((arguments or {}).get("code", ""))
        res = orig(self, state_path, arguments)
        try:
            _xg_after_call(self, stem, code, before)
        except Exception as e:
            print(f"XGAME: after-call hook error {type(e).__name__}: {e}", flush=True)
        return res
    return _run_python_tool

def _xg_wrap_analyze(orig):
    def analyze(self, state_path, *a, **k):
        try:
            stem = _xg_stem(state_path)
            self.__dict__["_xg_stem"] = stem; _xg_tls.stem = stem
            with _xg_lock:
                _xg_game(stem)
        except Exception:
            pass
        return orig(self, state_path, *a, **k)
    return analyze

def _xg_wrap_prompt(orig):
    def _build_user_prompt(self, *a, **k):
        r = orig(self, *a, **k)
        try:
            stem = self.__dict__.get("_xg_stem") or "?"
            shown = self.__dict__.setdefault("_xg_prompted", set())
            if stem in shown or not isinstance(r, str):
                return r
            shown.add(stem)
            block = _xg_block(None if stem == "?" else stem)
            if block:
                return block + "\n\n" + r
        except Exception as e:
            print(f"XGAME: prompt hook error {type(e).__name__}: {e}", flush=True)
        return r
    return _build_user_prompt

def _xg_wrap_tools(orig):
    def _tools(self, state_path):
        tools = orig(self, state_path)
        try:
            for t in tools:
                fn = t.get("function", {}) if isinstance(t, dict) else {}
                if fn.get("name") == "python" and _XG_TOOL_DOC not in (fn.get("description") or ""):
                    fn["description"] = (fn.get("description") or "") + _XG_TOOL_DOC
        except Exception:
            pass
        return tools
    return _tools

def _xg_wrap_sandbox(orig):
    def run_sandboxed_python(*a, **k):
        out = orig(*a, **k)
        try:
            text = str(out.get("stdout", "") or "")
            if _XG_MARK in text:
                kept = []
                for ln in text.split("\n"):
                    if ln.startswith(_XG_MARK):
                        try:
                            fact, evidence = _xg_ast.literal_eval(ln[len(_XG_MARK):])
                            _xg_tls.facts = (getattr(_xg_tls, "facts", None) or []) + [(str(fact), str(evidence))]
                        except Exception:
                            pass
                    else:
                        kept.append(ln)
                out["stdout"] = "\n".join(kept)
        except Exception:
            pass
        return out
    return run_sandboxed_python

def _xg_wrap_finish(orig):
    def finish_game(self, *a, **k):
        run = getattr(self, "game_run", None)
        first = run is not None and getattr(run, "final_score", None) is None     # finish_game is idempotent: act once
        res = orig(self, *a, **k)
        if not first:
            return res
        try:
            base = _xg_artifact_stem(getattr(run, "game_id", ""))
            lines = []
            with _xg_lock:
                cands = [s for s, g in _XG["games"].items() if g["base"] == base and not g["complete"]]
                mine = getattr(_xg_tls, "stem", None)
                targets = [mine] if mine in cands else cands       # own worker thread, else cancel/teardown from another: all still-playing passes are being finished
                if not targets:                                      # never reached analyze(): still count it
                    _XG["seq"] += 1; targets = [f"{base}_p?{_XG['seq']}"]; _xg_game(targets[0])
                apl = list(getattr(run, "actions_per_level", None) or [])
                for s in targets:
                    g = _XG["games"][s]
                    g.update({"complete": True, "levels": int(getattr(run, "levels_completed", 0) or 0), "number_of_levels": int(getattr(run, "number_of_levels", 0) or 0),
                              "actions": int(sum(apl)), "actions_per_level": apl, "state": str(getattr(run, "state", "")), "final_score": getattr(run, "final_score", None),
                              "solver_note": str(getattr(run, "solver_note", "") or "")[:300], "finished_at": _xg_time.time()})
                    _XG["pending"].pop(s, None)
                n_done = sum(1 for g in _XG["games"].values() if g["complete"])
                for s in targets:
                    g = _XG["games"][s]
                    lines.append(f"XGAME: {s} finished ({g['levels']}/{g['number_of_levels']} levels, {g['actions']} actions, helpers called {g['helpers_called'] or '{}'}, "
                                 f"remember() calls {g.get('remember_calls', 0)}, facts verified {g['facts_verified']}); ledger: {len(_XG['library'])} helpers, "
                                 f"{len(_XG['facts'])} facts, {n_done} game-passes done")
                snap = _xg_json.dumps({"library": {n: {k2: v2 for k2, v2 in v.items() if k2 != "src"} | {"sig": _xg_sig(v["src"])} for n, v in _XG["library"].items()},
                                       "facts": _XG["facts"], "games": _XG["games"]}, indent=1, default=str)
                art = _XG["artifacts_dir"]
            target = _xg_os.environ.get("DUCK_XGAME_STORE") or (art + "/xgame_store.json" if art else None)
            if target:
                tmp = f"{target}.{_xg_threading.get_ident()}.tmp"
                with open(tmp, "w") as fo:
                    fo.write(snap)
                _xg_os.replace(tmp, target)
            for ln in lines:
                print(ln, flush=True)
        except Exception as e:
            print(f"XGAME: finish hook error {type(e).__name__}: {e}", flush=True)
        return res
    return finish_game

if _XG_ON:
    assert _xg_os.environ.get("DUCK_NATIVES", "0") == "1" and _xg_os.environ.get("DUCK_PERSIST_DEFS", "0") == "1", \
        "DUCK_XGAME=1 requires DUCK_NATIVES=1 and DUCK_PERSIST_DEFS=1 (the library rides the persisted-defs store); load cell_duck_natives.py first"
    _xg_ta.ToolAgent._run_python_tool = _xg_wrap_run_python(_xg_ta.ToolAgent._run_python_tool)
    _xg_ta.ToolAgent._build_user_prompt = _xg_wrap_prompt(_xg_ta.ToolAgent._build_user_prompt)
    _xg_ta.ToolAgent._tools = _xg_wrap_tools(_xg_ta.ToolAgent._tools)
    if hasattr(_xg_ta.ToolAgent, "analyze"):
        _xg_ta.ToolAgent.analyze = _xg_wrap_analyze(_xg_ta.ToolAgent.analyze)
    _xg_ta.run_sandboxed_python = _xg_wrap_sandbox(_xg_ta.run_sandboxed_python)
    if _XG_TOOL_DOC not in _xg_ta._PYTHON_TOOL_DESCRIPTION:
        _xg_ta._PYTHON_TOOL_DESCRIPTION = _xg_ta._PYTHON_TOOL_DESCRIPTION + _XG_TOOL_DOC
    try:
        import taaf.game as _xg_game_mod
        _xg_game_mod.Game.finish_game = _xg_wrap_finish(_xg_game_mod.Game.finish_game)
        _xg_finish_hooked = True
    except Exception as _xg_e:
        _xg_finish_hooked = False
        print(f"XGAME: taaf.game.Game.finish_game not hooked ({type(_xg_e).__name__}); games will never count as finished", flush=True)
    print(f"XGAME installed: library (keep {_XG_LIB_CAP}, seed/list top {_XG_TOP_LIB}) + verified-facts ledger (window {_XG_N_ACTIONS} actions, top {_XG_TOP_FACTS}) "
          f"+ first-turn block (<= {_XG_BLOCK_CHARS} chars); same-game passes: {'ON' if _XG_SAME_GAME else 'off'}; finish hook: {'ON' if _xg_finish_hooked else 'OFF'}", flush=True)
else:
    print("XGAME available but off (DUCK_XGAME=1 enables; needs DUCK_NATIVES=1 DUCK_PERSIST_DEFS=1)", flush=True)
