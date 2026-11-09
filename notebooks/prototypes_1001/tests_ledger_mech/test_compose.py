"""Composition: natives (v1+persist+v2) + xgame + ledger exec'd in one namespace in the notebook's order, real ToolAgent,
fake model, one analyze() turn through the REAL sandbox (natives preamble + action())."""
import os, sys, json, io, contextlib, tempfile, pathlib
HERE = pathlib.Path(__file__).resolve().parent
sys.path[:0] = ["/home/ignaz/kaggle_bundle_029_visual/src/ARC3-Inference", "/home/ignaz/kaggle_bundle_029_visual/src/tufa-arc-agi-framework/src", str(HERE)]
os.environ.update({"DUCK_NATIVES": "1", "DUCK_PERSIST_DEFS": "1", "DUCK_NATIVES_V2": "1", "DUCK_XGAME": "1", "DUCK_LEDGER": "1",
                   "DUCK_NATIVES_V2_SRC": "/home/ignaz/github/arc-prize-2026/notebooks_duck/natives_v2_src.py"})
TMP = pathlib.Path(tempfile.mkdtemp(prefix="ledger_compose_", dir=str(HERE))); os.environ["DUCK_LEDGER_LOG"] = str(TMP / "l.jsonl"); os.environ["DUCK_XGAME_STORE"] = str(TMP / "x.json")
import inference.agent.tool_agent as ta
from inference.agent.runtime_state import Frame, HistoryEntry, write_runtime_state
def fake_chat(self, messages, *, tools=None, request_timeout_seconds=None):
    self.__dict__.setdefault("_req", []).append(messages)
    code = "print(len(objs()), report()['changed'] if previous_frame else 0)\naction(['UP'])"
    return ta._ChatCompletionResult(message={"role": "assistant", "content": "World model: x.", "tool_calls": [{"id": "c", "type": "function", "function": {"name": "python", "arguments": json.dumps({"code": code})}}]}, finish_reason="tool_calls", usage={})
ta.ToolAgent._chat_completion = fake_chat
ns = {"__name__": "cells"}
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    for f in ("/home/ignaz/github/arc-prize-2026/notebooks_duck/cell_duck_natives.py", "/home/ignaz/github/arc-prize-2026/notebooks_duck/cell_duck_xgame.py", str(HERE / "cell_duck_ledger.py")):
        exec(compile(open(f).read(), f, "exec"), ns)
print("\n".join(l for l in buf.getvalue().splitlines() if "installed" in l or "ERROR" in l.upper()))
from lm_load import gpath, transitions
tr, ev = transitions(gpath("q25", "ls20"))
init = next(e for e in ev if e.get("type") == "initial")
H = [HistoryEntry(action="", frame=Frame(grid=tuple(tuple(r) for r in init["board"]), step=0, level=1))]
for t in tr[:30]:
    H.append(HistoryEntry(action=t["action"], frame=Frame(grid=tuple(tuple(r) for r in t["after"]), step=t["i"], level=t["level"])))
art = TMP / "artifacts"; art.mkdir(); sp = art / "ls20-9607627b_p0_tool_runtime_state.json"
write_runtime_state(sp, current_frame=H[-1].frame, history=H)
def step_env(arguments):
    t = tr[30]; H.append(HistoryEntry(action=t["action"], frame=Frame(grid=tuple(tuple(r) for r in t["after"]), step=31, level=t["level"])))
    write_runtime_state(sp, current_frame=H[-1].frame, history=H)
    return {"executed": True, "executed_count": 1, "action_num": 31, "level": t["level"], "score": 0, "state": "NOT_FINISHED", "valid_actions": ["ACTION1", "ACTION2", "ACTION3", "ACTION4"],
            "board_changed": True, "game_over": False, "done": False, "level_completed": False, "run_complete": False, "action_display": t["action"], "executed_actions": [t["action"]]}
a = ta.ToolAgent(model="flashnext", base_url="http://127.0.0.1:1", provider="vllm")
res = a.analyze(sp, 30, valid_actions=["ACTION1", "ACTION2", "ACTION3", "ACTION4"], step_env=step_env)
u = [m for m in a._req[0] if m.get("role") == "user"][-1]["content"]
assert res.step_executed and "Coverage ledger (" in u and "End of coverage ledger." in u, u[-800:]
tool_msgs = [m for m in a._history_messages if m.get("role") == "tool"]
assert tool_msgs and "error" not in json.loads(tool_msgs[-1]["content"]), tool_msgs[-1]["content"][:400]
print("tool result:", json.loads(tool_msgs[-1]["content"]).get("stdout", "")[:80].strip())
print("COMPOSE PASS: natives+xgame+ledger installed in notebook order; one real-sandbox turn executed an action; the prompt carried one ledger")
print(u[u.index("Coverage ledger ("):u.index("End of coverage ledger.") + 23])
