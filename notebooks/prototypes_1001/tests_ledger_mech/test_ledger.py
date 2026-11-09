"""Tests for the cell_duck_ledger.py prototype against the REAL vendored ToolAgent (bundle 029 src), a fake model and a
fake step_env. No GPU, no network. Run: PYTHONDONTWRITEBYTECODE=1 .mlvenv/bin/python test_ledger.py"""
import os, sys, json, io, contextlib, subprocess, tempfile, pathlib, time, types
HERE = pathlib.Path(__file__).resolve().parent
SRC = ["/home/ignaz/kaggle_bundle_029_visual/src/ARC3-Inference", "/home/ignaz/kaggle_bundle_029_visual/src/tufa-arc-agi-framework/src"]
CELL = (HERE / "cell_duck_ledger.py").read_text()
PASS = []

# ---------- 1. default off: a separate interpreter, nothing patched ----------
probe = f"""
import sys; sys.path[:0] = {SRC!r}
import inference.agent.tool_agent as ta
before = {{n: getattr(ta.ToolAgent, n) for n in ("analyze", "_build_user_prompt", "_persistent_history_messages", "_chat_completion")}}
exec(compile(open({str(HERE / 'cell_duck_ledger.py')!r}).read(), "cell_duck_ledger.py", "exec"), {{"__name__": "cells"}})
after = {{n: getattr(ta.ToolAgent, n) for n in before}}
assert before == after, "patched while off"
print("OFF-OK")
"""
env = {k: v for k, v in os.environ.items() if not k.startswith("DUCK_")}
env["PYTHONDONTWRITEBYTECODE"] = "1"
out = subprocess.run([sys.executable, "-c", probe], env=env, capture_output=True, text=True)
assert "OFF-OK" in out.stdout and "available but off" in out.stdout, out.stdout + out.stderr
PASS.append("DUCK_LEDGER unset: no ToolAgent method replaced (identity), one 'available but off' line")

# ---------- 2. on ----------
sys.path[:0] = SRC
os.environ["DUCK_LEDGER"] = "1"
TMP = pathlib.Path(tempfile.mkdtemp(prefix="ledger_test_", dir=str(HERE))); os.environ["DUCK_LEDGER_LOG"] = str(TMP / "ledger.jsonl")
import inference.agent.tool_agent as ta
from inference.agent.runtime_state import Frame, HistoryEntry, write_runtime_state
SCRIPT = []          # fake model: list of responses (tool-call code strings)
def fake_chat(self, messages, *, tools=None, request_timeout_seconds=None):
    self.__dict__.setdefault("_seen_requests", []).append(json.loads(json.dumps(messages)))
    code = SCRIPT.pop(0) if SCRIPT else "print('noop')"
    return ta._ChatCompletionResult(message={"role": "assistant", "content": "World model: test.",
                                             "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "python", "arguments": json.dumps({"code": code})}}]},
                                    finish_reason="tool_calls", usage={"completion_tokens": 5})
ta.ToolAgent._chat_completion = fake_chat
ns = {"__name__": "cells"}
with contextlib.redirect_stdout(io.StringIO()) as so:
    exec(compile(CELL, "cell_duck_ledger.py", "exec"), ns)
assert "LEDGER installed" in so.getvalue(), so.getvalue()
assert getattr(ta.ToolAgent._build_user_prompt, "__name__", "") == "_build_user_prompt" and ta.ToolAgent._ldg_installed
try:
    exec(compile(CELL, "cell_duck_ledger.py", "exec"), {"__name__": "cells"}); raise SystemExit("double install not refused")
except AssertionError:
    pass
PASS.append("DUCK_LEDGER=1: four hooks installed, a second exec is refused")

# ---------- 3. real data through the real _build_user_prompt ----------
sys.path.insert(0, str(HERE))
from lm_load import gpath, transitions
def hist_from(run, g, upto):
    tr, ev = transitions(gpath(run, g))
    init = next(e for e in ev if e.get("type") == "initial")
    H = [HistoryEntry(action="", frame=Frame(grid=tuple(tuple(r) for r in init["board"]), step=0, level=init.get("level", 1)))]
    for t in tr[:upto]:
        H.append(HistoryEntry(action=t["action"], frame=Frame(grid=tuple(tuple(r) for r in t["after"]), step=t["i"], level=t["level"])))
    deaths = {k + 1 for k, t in enumerate(tr[:upto]) if t["state"] == "GAME_OVER"}
    return H, deaths
agent = ta.ToolAgent(model="flashnext", base_url="http://127.0.0.1:1", provider="vllm")
agent.__dict__["_ldg_stem"] = "tn36_p0"
H, deaths = hist_from("q25", "tn36", 78)
agent.__dict__["_ldg_deaths"] = set(deaths)
p = agent._build_user_prompt(78, valid_actions=["ACTION6", "RESET"], current_frame=H[-1].frame, history_entries=H, previous_step_summary=None)
i = p.index("end of world model. "); j = p.index("Coverage ledger ("); k = p.index("End of coverage ledger.")
assert i < j < k and p.count("Coverage ledger (") == 1, p
block = p[j:k + len("End of coverage ledger.")]
assert len(block) <= 1200 and "HUD rows 1 ignored" in block and "Deaths on this level (1)" in block and "A no-effect result holds only for the state you tested." in block, block
PASS.append(f"tn36 @78 through the real _build_user_prompt: ledger after the world-model anchor, {len(block)} chars, HUD row 1 masked, the death listed")
print("---- tn36 @78 ledger as the model would see it ----\n" + block + "\n")

# ---------- 4. the real analyze loop: deaths recorded via step_env, history stubbed, one full ledger per request ----------
state = TMP / "artifacts"; state.mkdir()
sp = state / "tu93-0768757b_p0_tool_runtime_state.json"
H, _ = hist_from("q25", "tu93", 22)          # just before the first death (action 23 is fatal in q25)
write_runtime_state(sp, current_frame=H[-1].frame, history=H)
tr, ev = transitions(gpath("q25", "tu93"))
def step_env(arguments):
    # replay the recorded action 23 (the fatal one) whatever the model asked for
    t = tr[22]
    H.append(HistoryEntry(action=t["action"], frame=Frame(grid=tuple(tuple(r) for r in t["after"]), step=23, level=t["level"])))
    write_runtime_state(sp, current_frame=H[-1].frame, history=H)
    return {"executed": True, "executed_count": 1, "action_num": 23, "level": t["level"], "score": 1, "state": "GAME_OVER",
            "valid_actions": ["ACTION1", "ACTION2", "ACTION3", "ACTION4"], "board_changed": True, "game_over": True,
            "done": False, "level_completed": False, "run_complete": False, "action_display": t["action"], "executed_actions": [t["action"]]}
SCRIPT[:] = ["action(['UP'])"]
r1 = agent2 = ta.ToolAgent(model="flashnext", base_url="http://127.0.0.1:1", provider="vllm")
res = agent2.analyze(sp, 22, valid_actions=["ACTION1", "ACTION2", "ACTION3", "ACTION4"], step_env=step_env)
assert res is not None and res.step_executed, res
assert agent2._ldg_deaths == {23}, agent2.__dict__.get("_ldg_deaths")
hist_users = [m for m in agent2._history_messages if m.get("role") == "user"]
assert hist_users and all("End of coverage ledger." not in (m["content"] if isinstance(m["content"], str) else "") for m in hist_users), hist_users
assert all("Coverage ledger (" not in m["content"] for m in hist_users) and any("end of world model. " in m["content"] for m in hist_users)
# auto-reset (solver.py:281 runs RESET outside step_env), then the next turn
t = tr[23]; assert t["action"] == "RESET", t["action"]
H.append(HistoryEntry(action="RESET", frame=Frame(grid=tuple(tuple(r) for r in t["after"]), step=24, level=t["level"])))
write_runtime_state(sp, current_frame=H[-1].frame, history=H)
SCRIPT[:] = ["print('look')", "print('look again')"]
agent2.analyze(sp, 24, valid_actions=["ACTION1", "ACTION2", "ACTION3", "ACTION4"], step_env=lambda a: {"executed": False})
reqs = agent2._seen_requests[1:]
for m in reqs:
    full = sum(1 for x in m if x.get("role") == "user" and isinstance(x.get("content"), str) and "End of coverage ledger." in x["content"])
    assert full == 1, [x.get("content", "")[:80] for x in m if x.get("role") == "user"]
last_user = [x for x in reqs[0] if x.get("role") == "user"][-1]["content"]
assert "Deaths on this level (1)" in last_user and "#1 (" in last_user, last_user
PASS.append("real analyze(): the fatal action's number recorded from step_env, the death shows in the next prompt, history keeps a stub, every request carries exactly one full ledger")
print("---- tu93 after the auto-RESET ----\n" + last_user[last_user.index("Coverage ledger ("):last_user.index("End of coverage ledger.") + 23] + "\n")

# ---------- 5. failure isolation ----------
orig_render = ns["_LdgLedger"].render
ns["_LdgLedger"].render = lambda *a, **k: 1 / 0
agent3 = ta.ToolAgent(model="flashnext", base_url="http://127.0.0.1:1", provider="vllm")
with contextlib.redirect_stdout(io.StringIO()) as so:
    p3 = agent3._build_user_prompt(78, valid_actions=["ACTION6"], current_frame=H[-1].frame, history_entries=H, previous_step_summary=None)
    p3b = agent3._build_user_prompt(78, valid_actions=["ACTION6"], current_frame=H[-1].frame, history_entries=H, previous_step_summary=None)
ns["_LdgLedger"].render = orig_render
base = ta.ToolAgent.__dict__["_build_user_prompt"]
assert "Coverage ledger" not in p3 and so.getvalue().count("LEDGER: prompt error ZeroDivisionError") == 1, so.getvalue()
PASS.append("a render exception returns the unmodified prompt and logs once per agent")

# ---------- 6. cost on the longest recorded histories ----------
for run, g in (("opus", "ls20"), ("vercel", "re86"), ("vercel", "ka59")):
    try:
        Hl, dl = hist_from(run, g, 10_000)
    except Exception as e:
        print("skip", run, g, e); continue
    led = ns["_LdgLedger"]()
    E = [(h.action, h.frame.grid, h.frame.level) for h in Hl]
    t0 = time.time(); steps = 0
    for n in range(5, len(E), 5):              # a prompt every ~5 actions, incremental like the shim
        led.render(E[:n + 1], {d for d in dl if d <= n}, ["UP", "DOWN", "LEFT", "RIGHT", "SPACE", "MOUSE"]); steps += 1
    t1 = time.time(); text, st = led.render(E, dl, ["UP", "DOWN", "LEFT", "RIGHT"]); t2 = time.time()
    print(f"cost {run} {g}: {len(E) - 1} actions, {steps} prompts, mean {1000 * (t1 - t0) / max(1, steps):.1f} ms/prompt, last {1000 * (t2 - t1):.1f} ms, {st['chars']} chars")
PASS.append("render cost measured on the longest recorded games (printed above)")

lines = [json.loads(l) for l in open(os.environ["DUCK_LEDGER_LOG"])]
assert lines and all("gaps" in l and "ms" in l for l in lines)
PASS.append(f"per-turn jsonl log written ({len(lines)} lines) with gaps for the uptake analysis")
print("\n".join("PASS " + s for s in PASS))
