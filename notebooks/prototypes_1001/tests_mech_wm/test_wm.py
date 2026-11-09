"""Offline test of the cell_duck_wm.py prototype against the REAL vendored tool_agent (bundle src), q25 boards."""
import os, sys, json, types
OVF = "/tmp/claude-1000/-home-ignaz/3e3841a1-74c3-47fd-96a6-233b057f0237/scratchpad/ovf/mech_wm"
sys.path.insert(0, "/home/ignaz/kaggle_bundle_029_visual/src/ARC3-Inference")
MODE = sys.argv[1]
os.environ["DUCK_WM_LOG"] = f"{OVF}/wm_test_{MODE}.jsonl"
if MODE != "unset": os.environ["DUCK_WM_MODE"] = MODE
import inference.agent.tool_agent as ta
from inference.agent.runtime_state import Frame, HistoryEntry, write_runtime_state
T = ta.ToolAgent
# the label fix from cell_duck_fixes (FIX 1) only -- the solver-side fixes need the full framework
src = open("/home/ignaz/github/arc-prize-2026/notebooks_duck/cell_duck_fixes.py").read()
ns = {}; exec(compile(src.split("def _install_dead_game_kill")[0] + "\n_install_label_fix()\n", "fixes_fix1", "exec"), ns)
# fakes for the two network/sandbox-bound originals, installed BEFORE the shim so it wraps them
REASONING = ("Hmm, the gray moved again.\nWorld model: draft one, wrong.\n\nMore checking...\n"
             "**World model**: the gray ghost replays the blob's move history from attempt 1; walls are black.\n"
             "Action model: arrows move the blob 6 cells; SPACE starts a new attempt.\n\nLet me press RIGHT twice and diff.")
def fake_chat(self, messages, **kw):
    return types.SimpleNamespace(message={"content": "", "reasoning": REASONING}, finish_reason="tool_calls", usage={})
def fake_dispatch(self, state_path, name, arguments):
    self._last_step_summary = arguments["summary"]; self._last_action_result = {"action_num": arguments["summary"]["end_action_num"]}
    self._update_summarized_knowledge_from_step_summary()
    return "ok"
def fake_analyze(self, state_path, *a, **k):
    return [dict(m) for m in self._history_messages]
T._chat_completion = fake_chat; T._dispatch_tool = fake_dispatch; T.analyze = fake_analyze
orig_methods = {k: T.__dict__[k] for k in ("_summarized_knowledge_lines", "_update_summarized_knowledge_from_assistant",
                                           "_update_summarized_knowledge_from_step_summary", "_build_user_prompt", "analyze")}
exec(compile(open(f"{OVF}/cell_duck_wm.py").read(), "cell_duck_wm.py", "exec"), {"__name__": "wm"})
if MODE in ("unset", "stock"):
    assert all(T.__dict__[k] is v for k, v in orig_methods.items()) and T._chat_completion is fake_chat and T._dispatch_tool is fake_dispatch
    print("STOCK: every method identical -> no behaviour change"); sys.exit(0)
a = T(model="flashnext", base_url="http://127.0.0.1:9/v1", provider="vllm")
a._last_action_result = {"action_num": 59}
if MODE == "off":
    a._update_summarized_knowledge_from_assistant("World model: x")
    p = a._build_user_prompt(60, valid_actions=["ACTION1"])
    assert "Working world model" not in p and "end of world model" not in p
    print("OFF prompt tail:\n", p[-900:]); sys.exit(0)
# (i) harvest from reasoning when content is empty
a._chat_completion([{"role": "user", "content": "x"}])
print("HARVESTED:", json.dumps({k: v for k, v in a._summarized_knowledge.items() if v}, ensure_ascii=False))
assert "replays" in a._summarized_knowledge["world_model"] and "draft one" not in a._summarized_knowledge["world_model"]
# content with a label wins over reasoning
a._update_summarized_knowledge_from_assistant("Plan: push the blob right")
# (ii)+(iv) a real clear from q25 g50t: action 70 RIGHT, level 1 -> 2
Q = "/tmp/claude-1000/-home-ignaz/4076a7d2-9632-46d3-9bfe-aab0fd65656e/scratchpad/out_q25/artifacts/g50t-5849a774_p0_events.jsonl"
ev = [json.loads(l) for l in open(Q)]; acts = {r["action_num"]: r for r in ev if r.get("type") in ("initial", "action")}
hist = [HistoryEntry(action=("" if n == 0 else acts[n]["action_display"]), frame=Frame(grid=tuple(map(tuple, acts[n]["board"])), step=n, level=acts[n]["level"])) for n in range(0, 71)]
sp = f"{OVF}/g50t-5849a774_p0_tool_runtime_state.json"
write_runtime_state(__import__("pathlib").Path(sp), current_frame=hist[-1].frame, history=hist)
summ = {"start_action_num": 69, "end_action_num": 70, "executed_count": 2, "executed_actions": ["RIGHT", "RIGHT"], "level": 2,
        "level_transition": True, "run_complete": False, "game_over": False, "board_changed": True, "stop_reason": "level_completed"}
a._dispatch_tool(__import__("pathlib").Path(sp), "python", {"summary": summ})
a._update_summarized_knowledge_from_assistant("World model: **Level 1 SOLVED** (reward 1/7). Mechanics confirmed: blob moves 6 cells/press; black = walkable floor; red gate retracts via the red T button.")
a._update_summarized_knowledge_from_assistant("World model: Level 2 - blob at (26,50); socket goal at (20,26).")
a._last_action_result = {"action_num": 75}
p = a._build_user_prompt(75, valid_actions=["UP", "DOWN", "LEFT", "RIGHT", "SPACE"], previous_step_summary=summ)
i = p.find("Working world model carried"); j = p.find("end of world model")
blk = p[i:j]; print("\nCARRY BLOCK (%d chars):\n%s" % (len(blk), blk))
assert "- Carried from L1" in blk and "Level-clear record L1" in blk and "history[69].frame" in blk and "Mechanics confirmed" in blk and "- World model [unchanged for 5 actions]: Level 2" in blk
# a game over on L2 after a new labelled WM
a._update_summarized_knowledge_from_assistant("World model: L2 socket is the goal; red gates open when the ghost stands on a node.")
a._last_action_result = {"action_num": 90}
a._dispatch_tool(__import__("pathlib").Path(sp), "python", {"summary": {**summ, "end_action_num": 96, "level_transition": False, "game_over": True}})
a._last_action_result = {"action_num": 97}
p2 = a._build_user_prompt(97, valid_actions=["UP"], previous_step_summary=None)
print("\nAFTER GAME OVER:\n" + p2[p2.find("Working world model carried"):p2.find("end of world model")])
# (v) strip old copies
a._history_messages = [{"role": "user", "content": p}, {"role": "assistant", "content": None, "reasoning": "r"}]
seen = a.analyze(__import__("pathlib").Path(sp), 0)
old = seen[0]["content"]
assert "- Carried from L" not in old and "Level-clear record" not in old and "Working world model carried" in old
print("\nSTRIP: old prompt keeps the stock lines, loses carry-only lines:", old.count("\n"), "lines vs", p.count("\n"))
print("\nLOG:"); print(open(os.environ["DUCK_WM_LOG"]).read())
