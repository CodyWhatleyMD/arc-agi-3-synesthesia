# ---- RECALL: tell the agent what its context window has already evicted ------------------------
# WHAT WAS WRONG: scripts/recall_scaffold.py was written on 09-09 and NOTHING ever imported it
# (repo-wide grep for importers: zero hits, only prose mentions). So the failure it was built for
# has never been mitigated in a single run, while the notes counted it as a delivered mitigation.
# The measured failure, runs/reasoner_doubter/base27: 91% of turns took no action, and 84% of those
# re-ran code the agent had ALREADY run -- one snippet 736 times. The context window evicts about
# every 8 turns, so from the inside every repetition is a fresh idea.
#
# WHY THIS FORM IS RIGHT: the existing loop-breaker answers repetition with `del msgs[2:]` -- it
# deletes the conversation, i.e. the only evidence that would let the agent notice. This annotates
# the RESULT of a repeated python call with the fact of the repetition and whether the output
# changed, and destroys nothing. It is not a prior: it states only facts about the agent's own
# history that an unbounded context would have handed it for free (cf. the ACTION7 rule in
# cell_duck_fixes.py -- state what the harness knows, never guess a meaning).
#
# HOW: monkeypatch on the vendored class, exactly like cell_breaker.py wraps _chat_completion.
# /home/ignaz/duck-harness stays byte-identical. The ledger is PER ToolAgent INSTANCE (one game =
# one agent), so concurrent games can never see each other's repeats.
# Set DUCK_RECALL_NOTES=0 to disable.
import os as _os, json as _json, functools as _ft, dataclasses as _dc
import importlib.util as _ilu
from pathlib import Path as _P
import inference.agent.tool_agent as _ta


def _load_scaffold():
    """scripts/recall_scaffold.py is not importable by name: `python notebooks_duck/ab_local.py`
    puts notebooks_duck/ on sys.path, not the repo root. Load it by path, and fail LOUDLY if it
    is missing rather than installing a no-op -- a silently-absent mitigation is the bug this
    whole file exists to undo."""
    here = _P(globals().get("__file__", "notebooks_duck/cell_recall.py")).resolve().parent
    cands = [_os.environ.get("RECALL_SCAFFOLD"),
             here.parent / "scripts" / "recall_scaffold.py",   # repo layout
             here / "recall_scaffold.py",                      # flat Kaggle bundle
             _P("scripts/recall_scaffold.py")]                 # cwd = repo root
    for c in cands:
        if c and _P(c).is_file():
            spec = _ilu.spec_from_file_location("recall_scaffold", str(c))
            mod = _ilu.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod, str(c)
    raise FileNotFoundError(f"cell_recall: recall_scaffold.py not found; looked at {cands}")


def _outcome(content):
    """The comparison key for 'did this call produce anything new'.

    NOT the raw tool content: _render_tool_payload dumps a JSON object that can carry
    run_elapsed_seconds / time_remaining_seconds, which differ on every call. Comparing the raw
    prefix would make every repeat look informative and the note would always say the opposite of
    the truth. Compare only what the code actually produced."""
    try:
        d = _json.loads(content)
        if isinstance(d, dict):
            return _json.dumps({k: d.get(k) for k in ("stdout", "error", "result")}, sort_keys=True)
    except Exception:
        pass
    return content or ""


def _annotate(content, note):
    """Put the note where BOTH the model and the transcript see it.

    `content` is json.dumps(...) from _render_tool_payload and goes verbatim into the tool message
    (tool_agent.py:1962). Prepending raw text in front of the opening brace would keep the model
    informed but break the JSON, and _render_tool_result_display (tool_agent.py:662-670) returns
    stdout ALONE when there is no error/result -- so the note would vanish from every transcript.
    Prepending into stdout keeps the payload valid JSON and visible in both places."""
    try:
        d = _json.loads(content)
        if isinstance(d, dict):
            d["stdout"] = note + "\n" + (d.get("stdout") or "")
            return _json.dumps(d, indent=2)
    except Exception:
        pass
    return note + "\n" + (content or "")


if _os.environ.get("DUCK_RECALL_NOTES", "1") == "0":
    print("RECALL: disabled by DUCK_RECALL_NOTES=0", flush=True)
elif getattr(_ta.ToolAgent, "_cc_recall_installed", False):
    print("RECALL: already installed", flush=True)
else:
    _rs, _rs_path = _load_scaffold()
    _RepetitionLedger = _rs.RepetitionLedger
    _orig_py = _ta.ToolAgent._run_python_tool

    @_ft.wraps(_orig_py)
    def _w(self, state_path, arguments):
        res = _orig_py(self, state_path, arguments)
        try:
            code = str((arguments or {}).get("code", ""))
            if not code.strip():
                return res
            led = getattr(self, "_cc_recall", None)
            if led is None:
                led = self._cc_recall = _RepetitionLedger()
                self._cc_recall_turn = 0
                self._cc_recall_notes = 0
            self._cc_recall_turn += 1
            out = _outcome(getattr(res, "content", ""))
            note = led.notice(code, out)          # BEFORE record(), or every call is its own repeat
            led.record(code, self._cc_recall_turn, out)
            if note:
                self._cc_recall_notes += 1
                return _dc.replace(res, content=_annotate(res.content, note))
        except Exception as e:                    # never let bookkeeping kill a game
            print(f"RECALL: annotation skipped ({type(e).__name__}: {e})", flush=True)
        return res

    _ta.ToolAgent._run_python_tool = _w
    _ta.ToolAgent._cc_recall_installed = True
    # the install line is the only proof the wrapper was live for THIS run -- three shims in this
    # repo were recorded as done while defining a function nobody called.
    assert getattr(_ta.ToolAgent._run_python_tool, "__wrapped__", None) is _orig_py
    print(f"RECALL INSTALLED on ToolAgent._run_python_tool (ledger from {_rs_path}; "
          f"DUCK_RECALL_NOTES=0 disables)", flush=True)
