# What the scoring ARC-AGI-3 notebooks actually do with the model

Research pass, 2026-08-24. Read-only Kaggle CLI (`kernels list/pull`, `datasets files/download`,
`competitions leaderboard`, `forums topics list/show`). **Nothing was pushed, submitted, or published.**

**Headline: this is not a secret. The top approach is fully open source and has an official
technical write-up.** It is called the **Duck harness** (a.k.a. TAAF — Tufa ARC-AGI Framework),
by Tufa Labs, and it won ARC-AGI-3 Milestone 1. Essentially every notebook on the leaderboard
that uses `foysalemonshanto/qwen3-8-27b-fp8-repacked-v1` is a fork of it.

The single most important structural fact:

> **The notebooks contain almost no agent code.** They are ~200-line launchers. The agent is a
> full Python source tree shipped as an attached **Kaggle Dataset** (~460 KB), mounted and put on
> `sys.path`. If you only read notebook sources you will conclude nobody has an architecture.

---

## 0. Leaderboard and score scale (verified)

`kaggle competitions leaderboard arc-prize-2026-arc-agi-3 -s`, 2026-08-24:

| rank | team | score |
|---|---|---|
| 1 | cstl | 5.99 |
| 2 | Tufa Labs | 4.58 |
| 3 | Lord Han Solo | 3.36 |
| 4 | Tony G | 3.17 |
| 5 | Daniel Franzen | 2.88 |
| … | a long tail at 2.4–2.8 | |

Scores are **percent of 100**, not a 0–1 fraction. Confirmed by Jeroen Cottaar (Tufa Labs) in
forum topic 705022:

> "It's a percentage. The maximum possible score is 100. (Not 115 - you can score 1.15x human
> baseline on a single level, but it gets capped to 100 per game.)"

The scaffold's 0.14 (submission 55692780, **no model in the loop** — not this agent) is
therefore 0.14%, against a 2.4–2.8% mass of duck forks and 5.99% at the top.
**[2026-09-21, Kaggle submissions API]** With the model in the loop we are at **1.56**
(56377237, syn v2), after 0.34 (v12) and 0.24 (v14), and 0.76 on 09-21 (56420448).

**Per-level scoring, verbatim from `thtennant/taaf-kaggle-source-share-fork` → `taaf_grafts/agent_ext.py`:**

> "the per-level score is `min(115, (baseline/actions)^2 * 100)` — quadratic in efficiency"

and from `taaf_grafts/clockwatch.py`, the part that changes strategy:

> "the benchmark score is `min(raw, cap)` with `cap = 100 * sum(i completed) / sum(i all levels)`,
> and on every game this project has ever scored, the **CAP** bound, not the efficiency term —
> tn36 cleared level 1 in 24 actions against a baseline of 32, which saturates the efficiency term
> at 115 and still scored 3.57, the cap exactly."

**Implication: levels cleared dominates. Action efficiency is a secondary multiplier that
saturates.** Depth of progress is the score.

---

## 1. THE DUCK HARNESS — the architecture that scores

### Canonical sources (all pulled and read)

| kernel ref | author | notes |
|---|---|---|
| `jeroencottaar/tufa-labs-duck-harness-june-30-milestone-winner` | Jeroen Cottaar (Tufa Labs) | Milestone 1 winner, LB 1.21. 282 votes |
| `jeroencottaar/taaf-duck-harness-kaggle` | Jeroen Cottaar | the 1.30 run (retracted) |
| `foysalemonshanto/lb-9-arc3-duck-v12-with-qwen-3-8-27b` | FOYSAL | 207 votes. Duck + **our exact Qwen3.8 checkpoint** |
| `keithtyser/duck-qwen3-8-27b-fp8` | ktyser | 85 votes. Duck + Qwen3.8, own serving overlay |
| `thtennant/arc3-duck-v22` | Teddy Tennant | most recent (2026-08-24). Duck + 20 "graft" modules |
| `yw8837/lb-1-17-arc-agi-3-qwen3-6-duck-full-code` | yw8837 | LB 1.17, with an 11-submission ledger |
| `boristown/agi-duck-harness-fast-eval` | 暗黑AGI | 263 votes |

Agent source datasets (this is where the code is):
`jeroencottaar/taaf-kaggle-source-share` (449 KB), `jakobbrggen/taaf-kaggle-source` (470 KB,
updated 2026-08-22), `jakobbrggen/taaf-kaggle-source-anim-20260807-anim`,
`thtennant/taaf-kaggle-source-share-fork`, `keithtyser/taaf-duck-qwen38-serving-v1`.

Tree: `src/ARC3-Inference/inference/{agent,framework,tools,utils}` +
`src/tufa-arc-agi-framework/src/taaf/`. Key files: `agent/prompts.py` (15 KB),
`agent/tool_agent.py` (109 KB, 2428 lines), `agent/python_tool_sandbox.py` (619 lines),
`framework/solver.py` (1555 lines).

### Official write-up (forum topic 717133, 62 votes)

"Tufa Labs' Winning Solution for ARC-AGI-3 Milestone 1", by Harold Bessis, Jeroen Cottaar,
Isaiah Pressman, Dries Smit, Michal Tešnar, Stefano Viel. Verbatim excerpts:

> "The Duck harness exposes the game to the agent as Python variables and allows the agent to
> interact with these variables in whichever way it prefers, letting it lean on its pre-trained
> patterns:
> - All game observations are encoded as Python variables;
> - The agent can interact with these variables using the Python tool, call pre-built helper
>   functions, and take actions in the environment;
> - The actions are executed in the ARC-AGI-3 environment, which then updates the Python sandbox
>   with new variables;
> - The LLM freely iterates between reasoning, tool use, and taking actions, until the game is
>   solved or times out;
> - Whenever we reach the maximum context length, we evict the oldest non-system-prompt context to
>   enable the model to play indefinitely;
> - We also leverage Qwen 3's multimodal image input to allow the model to directly observe the
>   latest frame."

> "Our solution takes inspiration from previously published works. Symbolica's solution, called
> ARCgentica, achieved a score of 36% the day after the release of the public official games. …
> This solution shows that the models are naturally good at problem solving using code, similar to
> the CodeAct method. … the RGB Agent … uses OpenCode. Their solution was the first to show
> near-human action efficiency on the 3 preview games. … This allows the agent to first analyze
> observations, generate hypotheses, and then queue up a limited number of actions; a pattern that
> limits wasteful moves."

> "The UNDO action is not provided to the model as the model fails to use it efficiently: it undoes
> big batches of actions that wastes energy."

> "We cap the agent's maximum context to 64k tokens … The harness attempts to maintain an input
> context of 32k tokens by evicting the oldest user message and subsequent assistant turns,
> whenever it surpass this limit. … We currently do not optimally use prefix caching on the vLLM
> engine."

> "a 4× upscaled image of the board is injected into its context at the beginning of every turn.
> Qwen's encoder processes images in 16×16 pixel patches and we found that this upscaling gives the
> model the best visual understanding of the scene. … We also tried injecting more frames or video
> animations, but we noticed that small models struggle with extracting details and acting on them."

> "A common failure mode of the agent is that it tries to print the whole grid directly, which
> pollutes its context. To help it analyze the structure of the grid, we provide it with a
> segmentation tool that helps the model locate the 4-connected components in pixel space."

> "The mean score we achieve is 1.6002 (+/- 0.4475)" (25 public games × 20 tries, Qwen3.6-27B-FP8).

⚠️ Also verbatim: *"The REPL is not fully isolated. Running this harness can lead to arbitrary code
execution. Run the code at your own risk."*

---

### 1.1 THE AGENT LOOP

**Two nested loops.**

**Outer (per game)** — `inference/framework/solver.py`, `_HarnessGameSession.play()`:

```python
while not self.should_stop():
    if _is_engine_game_over(self.game) and self.last_engine_action != "RESET":
        self._execute_auto_reset()
        continue
    self.analysis_step += 1
    ...
    result = self.analyzer.analyze(
        self.state_path, self.action_count,
        valid_actions=_engine_action_names(self.game),
        step_env=self.step_env, transcript_path=self.transcript_path,
        analysis_step=analysis_step,
        request_timeout_seconds=self.request_timeout_seconds(),
        should_stop=self.should_stop,
    )
```

**Inner (per analyze() turn)** — `tool_agent.py::analyze`, an unbounded tool-call loop:

```python
turn_count = 0
while self._tool_steps is None or turn_count < self._tool_steps:
    yielded_control_reason = control_yield_reason()
    if yielded_control_reason is not None:
        break
    turn_count += 1
    tools = self._tools(state_path)
    messages = self._trim_messages_for_context(messages, tools=tools)
    result = self._chat_completion(messages, **request_kwargs)
```

`LOCAL_ANALYZER_TOOL_STEPS = '0'` and
`self._tool_steps = None if _LOCAL_ANALYZER_TOOL_STEPS <= 0 else max(1, ...)` → **`_tool_steps` is
`None`, i.e. unlimited tool calls per turn.** The only inner-loop exit is
`LOCAL_ANALYZER_YIELD_SECONDS = '60'` (a wall-clock yield) or `should_stop()`.

**So: the model is NOT called once per action.** It is called repeatedly in a tool-use loop; it
inspects, writes code, runs code, and the code itself takes 0..N game actions. One `analyze()`
turn can execute a whole batched plan.

**Prompt contents.** System prompt is assembled once per agent
(`_build_system_prompt`, `prompts.py`): game overview + runtime-variable reference +
(multimodal note) + visual-game heuristics + Python guidance + tool-session rules. It contains
**no board data at all**.

Each user turn carries: previous-step summary, `step`/`level` state line, valid actions, tool
reminders, the carried-over world model, and — if `MULTIMODAL_CONTEXT=current_grid` — a
**4× (or 8×) upscaled PNG of the current 64×64 board as a base64 data URL**:

```python
return {
    "role": "user",
    "content": [
        {"type": "text", "text": f"{user_prompt}\n\nCurrent grid image:"},
        image_part,
    ],
}
```

**The raw grid is deliberately withheld from the prompt.** Verbatim from `prompts.py`:

> "- The raw numeric grid is intentionally not exposed. Use `current_frame.segmentation` as your
> primary view of the board -- objects, colors, shapes, containment, adjacency, and cross-frame
> object hashes. Use `current_frame.ascii` only to read a small, specific region; do not scan the
> whole board with it."

The board is reachable *only through code the model writes*.

---

### 1.2 THE OUTPUT CONTRACT — the model writes and runs code

There is exactly **one tool**, `python`, and it takes one free-form `code` string
(`tool_agent.py::_tools`):

```python
return [{
    "type": "function",
    "function": {
        "name": "python",
        "description": _python_tool_description(animation_retrieval=self._animation_retrieval_enabled),
        "parameters": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": (
                        "Python code to run. The snippet is ephemeral and is not saved across tool calls."
                    ),
                },
            },
            "required": ["code"],
        },
    },
}]
```

Tool description (`_python_tool_description`):

> "Run one ephemeral Python snippet against preloaded ASCII game state. Available globals:
> `current_frame`, `previous_frame`, `history`, `transitions`, `last_transition`, `valid_actions`,
> `last_action_result`, `action(actions)` for executing one or more real environment actions. …
> For MOUSE, pass `row` and `col` integer fields; legacy x/y fields are rejected. The raw numeric
> grid is not available. Use `.segmentation` as the primary view; use `.ascii` only to read a
> small, specific region. Use `print(...)` for compact output or assign final data to `result`."

**Actions are a function call inside the model's own code**, not a parsed JSON field. From
`python_tool_sandbox.py`, the sandboxed child process:

```python
def action(actions):
    normalized_actions = _normalize_actions(actions)
    _send({"type": "action", "actions": normalized_actions})
    reply = _recv()
    if reply.get("type") == "action_error":
        raise RuntimeError(str(reply.get("error", "action failed")))
    if reply.get("type") != "action_result":
        raise RuntimeError("Invalid action response from sandbox host.")
    action_result = reply.get("action_result") or {}
    action_results.append(action_result)
    _refresh_state(reply.get("state") or {})
    return action_result
```

Normalisation accepts `'LEFT'`, `{'action':'MOUSE','row':4,'col':7}`, or a list of either.

**Crucially, state refreshes mid-snippet.** After each `action(...)` call, `_refresh_state`
rebinds `current_frame`, `previous_frame`, `history`, `transitions`, `valid_actions`,
`last_action_result` **inside the still-running snippet**. So the model can write a genuine
closed-loop controller:

```
# what the prompt explicitly invites:
"- You can also call `action(...)` multiple times in one Python snippet, including inside loops.
   Each call updates the preloaded variables before execution continues."
```

Sandbox: subprocess, `SAFE_BUILTINS` whitelist, `_safe_import` restricted to
`{bisect, collections, copy, fractions, functools, heapq, itertools, json, math, operator,
random, re, statistics, string}`, `resource` rlimits, 30 s hard timeout, output capped to
`LOCAL_ANALYZER_TOOL_OUTPUT_TOKENS = 1024` (≈4096 chars). No numpy, no filesystem.

**This is the Duck/CodeAct pattern the brief asked about, and yes — they let the model write and
run code, including search algorithms.** Verbatim instruction from `PYTHON_ADDENDUM`:

> "- IMPORTANT: Especially when the game is about making an agent navigate to a target, it is
> usually safer to write an explicit search algorithm such as BFS. More generally, when the
> objective is understood but the best action order is unclear, pathfinding, flood fill, BFS, DFS,
> beam search, shortest-path search, limited action-sequence search, or custom heuristics are all
> valid."
> "- Optimize for the shortest reliable sequence that advances the current goal as described by
> your world model. If confidence is low, program a discriminating probe and revise the world model
> from the result."
> "- Once the important state variables and action effects are sufficiently understood, stop
> probing and search in the inferred state space."
> "- A strong default loop is: summarize the board, infer the desired environment change, write a
> small scorer or search over candidate sequences, execute the best probe or plan with
> `action(...)`, then inspect again until you understand exactly what changed."

---

### 1.3 MEMORY

Three layers.

**(a) Message history with eviction.** `_history_messages` persists across `analyze()` calls.
`_PERSISTENT_HISTORY_ASSISTANT_TURNS = 30`. `_trim_messages_for_context` drops the oldest
non-system blocks until the estimate fits `_context_budget_tokens`
(= `LOCAL_ANALYZER_CONTEXT_WINDOW` 32768 − reply reserve − 512 safety). There is also a
context-overflow retry that trims and re-sends on a server-side 400.

**(b) A carried "world model" note — the load-bearing part.** The model is told to emit labelled
blocks in its assistant text; the harness parses them and re-injects them next turn.
`_extract_scientist_note` looks for: `World model`, `Goal model`, `Action model`,
`Recent findings`, `Open questions`, `Plan`, `Cross-level notes` (plus aliases
`Hypothesis`/`History check`/`Next test`). Re-injection (`_summarized_knowledge_lines`):

```python
return [
    "Working world model carried from earlier turns:",
    *lines,
    "- Revise any item above immediately if `current_frame` or `history` contradicts it.",
]
```

Prompt pressure, verbatim from `_build_user_prompt`:

> "Below you are provided with the current world model from the previous turn. The default behavior
> is to copy it and add or remove things based on the evidence that you gathered. BEFORE EXECUTING
> NEW ACTIONS YOU MUST ALWAYS GIVE THE REVISED VERSION OF THE WORLD MODEL."

Note `_update_summarized_knowledge_from_step_summary` **wipes** world/goal/action/findings/
questions/plan on a level transition, win, or game-over — but deliberately **keeps
`cross_level_notes`**. That is the only channel that survives a level change.

⚠️ Known defect, forum topic 734843 (Jason Feng): the parser only reads *visible* assistant
content, so world-model updates emitted inside `<think>` reasoning are silently lost. He measured
it and published a patched fork.

**(c) Hard no-op guard.** `agent/noop_guard.py` records `(level, board_before_sig, action_sig)`
triples proven to change nothing and *blocks re-execution* — not a prompt hint, a mechanical block.
Bounded (512 states/level, 16 actions/state). Animated actions are never recorded as no-ops:

> "in a type-1 animation (ft09, sb26) the first and last frame match by design and the entire
> signal -- a rejected click, a consumed attempt -- lives in the frames in between. Recording those
> as no-ops made the guard hard-block actions that had clearly worked."

No notes file, no cross-game persistence in stock Duck. (Cross-game memory is thtennant's graft —
§3.)

---

### 1.4 ACTION BUDGET AND RESET

**There is no action cap.** `HarnessSolver.max_actions_per_game: int | None = None`, and the
pickled solver in every bundle confirms it:

```
HarnessSolver(label='duck-harness', ..., analyzer_timeout=900.0,
              max_actions_per_game=None, max_runtime_s_per_game=7920.0,
              concurrency=28, ...)
```

`should_stop()` fires on: run not `playing`, stop event, run complete, **runtime limit**, or the
(unset) action cap. So the binding constraint is **7920 s (2 h 12 m) of wall clock per game, 28
games in flight concurrently**, inside Kaggle's 9 h budget for 110 runs.

Measured, from `taaf_grafts/clockwatch.py` (12 game-runs, 665 `analyze()` calls):

> "* Every archived game ends on the 7920 s per-game wall-clock. None ends on the action cap.
> * The model generates at a flat ~30.7 tok/s, so that wall-clock IS a fixed generated-token
>   budget. …
> * 97.6-98.3% of every generated token is reasoning.
> * **12 of 12 games ended inside an analysis step that never produced an action**: 67k-171k
>   reasoning characters per arm stranded mid-thought when the clock stopped the game where it
>   stood.
> * The agent is never told any of this. `time_remaining_seconds` appears 7-9 times per arm in
>   ~70,000 lines of transcript … In a 132-minute game the agent typically sees the clock once,
>   at action 1."

**Reset:** `os.environ["ONLY_RESET_LEVELS"] = "true"` is set in every notebook — RESET restarts the
*level*, not the game. On engine game-over the solver auto-resets without consulting the model
(`_execute_auto_reset`). RESET is exposed to the model as a normal action name.

---

### 1.5 SAMPLING, CONTEXT, PARSERS — the exact vLLM invocation

From `setup_commands.json` (`jakobbrggen/taaf-kaggle-source`), verbatim:

```python
cmd = [
    sys.executable, '-m', 'vllm.entrypoints.openai.api_server',
    '--model', str(MODEL_PATH),
    '--served-model-name', SERVED_MODEL_NAME,
    '--host', VLLM_HOST,
    '--port', str(VLLM_PORT),
    '--tensor-parallel-size', str(VLLM_TENSOR_PARALLEL_SIZE),
    '--enable-auto-tool-choice',
    '--tool-call-parser', 'qwen3_coder',
    '--generation-config', 'vllm',
    '--enable-prefix-caching',
    '--default-chat-template-kwargs', '{"preserve_thinking": true}',
    '--reasoning-parser', 'qwen3',
    '--max-model-len', str(VLLM_MAX_MODEL_LEN),   # 65536
]
```

**`--reasoning-parser qwen3` is present.** That is exactly the flag missing from our local
`:5300` server and the cause of the `</think>` leakage into `message.content`. They also pass
`--enable-auto-tool-choice --tool-call-parser qwen3_coder` (mandatory — the whole contract is
tool calls) and `--enable-prefix-caching`.

Analyzer env exported by setup:

```python
'LOCAL_ANALYZER_CONTEXT_WINDOW': str(ANALYZER_CONTEXT_WINDOW),   # 32768
'LOCAL_ANALYZER_MAX_OUTPUT': '0',        # no max_tokens cap on generation
'LOCAL_ANALYZER_TOOL_STEPS': '0',        # unlimited tool calls per turn
'LOCAL_ANALYZER_TOOL_TIMEOUT': '30',
'LOCAL_ANALYZER_TOOL_OUTPUT_TOKENS': '1024',
'LOCAL_ANALYZER_YIELD_SECONDS': '60',
'LOCAL_ANALYZER_TEMPERATURE': '0.6',
'LOCAL_ANALYZER_TOP_P': '0.95',
'LOCAL_ANALYZER_TOP_K': '20',
'LOCAL_ANALYZER_ENABLE_THINKING': 'true',
'MULTIMODAL_CONTEXT': 'current_grid',
'MULTIMODAL_UPSCALE': '8',               # '4' in keithtyser's; write-up says 4
'MULTIMODAL_GRID_LINES': 'true',
```

Two notes:
- `max_model_len 65536` vs analyzer budget `32768` — the 2× headroom is for reasoning + tool output.
- **Their own bug:** `vision_context.multimodal_grid_lines_enabled()` tests
  `os.environ.get("MULTIMODAL_GRID_LINES", "").strip() == "1"`, but setup sets it to `'true'`.
  Grid lines are therefore **off** in that bundle despite being configured on.

`keithtyser/duck-qwen3-8-27b-fp8` differs where Qwen3.8 needs it:
- `VLLM_MAX_MODEL_LEN = 262144`, plus `'--kv-cache-dtype', 'fp8'`
- a **serving overlay** installed over the wheelhouse:
  `transformers-5.8.0-py3-none-any.whl` + `huggingface_hub-1.5.0-py3-none-any.whl`
  (vLLM 0.19.0's pinned transformers cannot parse the Qwen3.8 config), shipped inside his dataset
  as `serving_wheels/`, plus `serving_reference/official-file-hashes.json`.
- pins `MODEL_HF_REVISION = '017b9c7af6b5689d5dd426a76e0bc077eb5ca20a'`.

### 1.6 Board encoding

`inference/utils/grid_utils.py`, verbatim:

```python
ARC_COLOR_CHARS = "WwgGcBMPRbSYOrNp"
ARC_COLOR_LEGEND = (
    "W=white, w=light gray, g=gray, G=dark gray, c=charcoal, B=black, "
    "M=magenta, P=pink, R=red, b=blue, S=sky blue, Y=yellow, O=orange, "
    "r=dark red, N=light green, p=purple"
)
```

Letters, not digits — one char per cell, and each letter carries a colour name in the legend.

Segmentation (`utils/segmentation.py`, inlined into the sandbox bootstrap via
`inspect.getsource`) returns, per `prompts.py`:

> "`current_frame.segmentation` parses the board into objects. It returns
> `{'nodes': [...], 'adjacency_list': [...]}`. … Each node … `id` (index, ordered
> top-most-left-most), `color` (ARC color character), `hash` (a signature of the object's color and
> shape that ignores its position -- equal hashes mean the same object regardless of where it is,
> so use it to track an object across frames or to spot multiple identical objects in one frame),
> `pixels` (cell count), `boundary` (clockwise outer-perimeter corner points as `[row, col]`), and
> `children` (ids of objects fully enclosed by this one). … `segmentation['adjacency_list']` is a
> list of `[i, j]` node-id pairs whose objects share an edge."

### 1.7 The full system-prompt heuristics worth stealing verbatim

From `VISUAL_GAME_ADDENDUM`:

> "- Some games are logic or layout puzzles with no explicit player avatar or controllable sprite
> on the board. Do not assume a player exists; the relevant state may be an object, region, cursor,
> selector, or whole-board configuration."
> "- In many games, a long horizontal or vertical line near an edge is a timer or remaining-steps
> bar. … If you identify such a bar, do not get distracted by it …
> A common failure mode is to mistake a segmented edge bar for clickable puzzle pieces. If a
> repeated strip of small blocks sits flush against the top, bottom, left, or right border and
> actions only change that strip while the interior board stays the same, classify it as HUD/timer
> state, not as an object to click through segment by segment. DON'T DO THIS!"
> "- Use coordinates only to target actions or describe local evidence. Do not frame the objective
> as reaching a specific absolute row or column."
> "- `WIN` means the whole game is solved. Mid-run level completion is more likely to appear as a
> score increase while play continues."

From `GAME_OVERVIEW_ADDENDUM`:

> "- Your job is to solve the entire game by clearing every level, not just the current screen."
> "- Optimize for as few in-game actions as possible while still being reliable."

From `COMPACT_TOOL_SESSION_ADDENDUM`:

> "- Do not ration tool calls when the state is unclear. Spend extra tool calls to confirm what
> changed between frames and whether the last action affected gameplay state or only HUD elements
> such as countdown bars."

(`clockwatch.py` argues this last line is actively harmful, since thinking *is* the scarce
resource — see §3.)

---

## 2. THE OTHER ARCHITECTURE — vision + JSON action menu (weaker)

### `ruichardliu/milestone1-2nd-solution` — Milestone 1, 2nd place, Gemma-4-31B-IT

Self-contained notebook (no dataset). Budgets: `MAX_ACTIONS = 200`, `ACTION_CONTEXT_FRAMES = 4`,
`MAX_PLAN_ACTIONS = 4`, `MAX_NEW_TOKENS = 1024`, `REFLECTION_INTERVAL = 10`,
`MAX_REFLECTION_CHARS = 1800`, `REFLECTION_MAX_NEW_TOKENS = 10000`.

Loop: every action, send the last 4 frames **as PNG images** with red STEP labels + a text prompt;
model returns one JSON object with 1–4 actions; guided/JSON mode with a repair prompt on parse
failure. Every 10 transitions a separate **reflection agent** call rewrites a Markdown memory doc.

Action prompt, verbatim:

```
You are the action agent for an interactive ARC-AGI-3 visual game.
The images are chronological; the last is current. Red STEP labels are added
chronology, not game UI. Ignore the outer {self._border_ignore_pixels()} pixels
when judging progress. Trust numeric transitions over visual guesses.

Infer the controllable object, causal action effects, and current objective.
Prefer purposeful new states. A repeated state is not progress. Do not invent
counters, bars, or goals without evidence.

Legal actions for this exact state: {available_actions}
Action format rules for this state only:
{legal_action_instructions}
Do not output any action name outside Legal actions for this exact state.
Ineffective in this exact state: {ineffective_actions}

Reflection memory (authoritative but revisable):
{self.reflection_memory}

Recent transitions:
{recent_history}

Return exactly one JSON object, no tools or markdown. Include 1 to
{self.MAX_PLAN_ACTIONS} actions; use one exploratory action if uncertain.
Example: {output_example}
{thinking_directive}
```

Reflection prompt, verbatim:

```
You are the reflection agent for an ARC-AGI-3 game. Review the previous
memory, the last {self.REFLECTION_INTERVAL} completed transitions, and the
chronological images. The final image is current; red STEP labels are added
chronology. Pixel changes may be movement, transformation, collection,
animation, or UI, so do not assume translation.

Keep only evidence-supported, useful conclusions. Correct stale beliefs.
Distinguish confirmed rules from hypotheses and state a concrete next goal.
Return only a compact Markdown document under {self.MAX_REFLECTION_CHARS}
characters with exactly these headings:

# Agent Memory
## Rules
## Goal
## Progress
## Avoid

Previous memory:
{self.reflection_memory}

Current level: {int(latest_frame.levels_completed) + 1}
Completed transitions:
{transitions}
/no_think
```

Sampling: `temperature 0.6` thinking / `0.2` non-thinking, `top_p 0.95`, `top_k 20`,
`repetition_penalty 1.08`, `chat_template_kwargs={"enable_thinking": …}`.

**No code execution.** It picks from a menu. It placed 2nd at milestone; the code-executing Duck
placed 1st, and the whole leaderboard has since converged on Duck.

### `gregkamradt/arc-agi-3-gpt-oss-120b` — the official ARC Prize reference

The baseline everyone forks *away* from. `MAX_ACTIONS = 50`, `MESSAGE_LIMIT = 2`,
`ACTION_MAX_TOKENS = 8192`, `GAME_TIME_LIMIT_S = 60*20`, guided-JSON single action per call.
State prompt is the raw grid pretty-printed:

```
# RESULT OF PREVIOUS ACTION
State: {state}
Score: {score}

# FRAME
{latest_frame}
```

Action prompt:

```
# CONTEXT
You are playing an ARC-AGI-3 dynamic game. Your objective is to WIN
and avoid GAME_OVER while minimizing the number of actions.
...
# RESPONSE FORMAT
Return only one JSON object. Do not include prose, markdown, code
fences, or commentary.

Valid examples:
{"action":"ACTION1"}
{"action":"ACTION6","x":0,"y":0}
```

This shape — raw grid in prompt, one LLM call per action, JSON menu — is architecturally what our
`arm_c2_harness.py` is, and it is the shape the leaderboard abandoned.

### `ko0kip/arc-agi-3-gemma-4-31b-reflection-agent`, `mbmmurad/…-lb-0-86-…`

Same family (Gemma-4-31B, vLLM 0.23 offline dataset, `machine_shape: NvidiaRtxPro6000`),
reflection-style, no code execution. Both pre-date the Duck consensus.

---

## 3. THE FRONTIER — `thtennant/arc3-duck-v22` grafts (most valuable single find)

`thtennant/taaf-kaggle-source-share-fork` is stock Duck **plus** `src/taaf-grafts/taaf_grafts/`,
20 modules, each with a long docstring stating a measured defect and its fix. These read like a
lab notebook and they name the numbers. Highlights:

**`agent_ext.py` — the efficiency diagnosis:**
> "Forensics of the last real run showed the model reasons correctly but overspends action
> baselines 13-26x through (1) net-zero action bursts (30xLEFT then 30xRIGHT round-trips),
> (2) raster-scan / exhaustive enumeration, and (3) death-driven auto-RESETs. The model is
> self-aware it is wasting moves but realises it TOO LATE."

Also, critical for submission planning:
> "The real competition rerun strips baselines (the REST API omits `baseline_actions` and env ids
> are anonymised clones), so on the hidden set `_resolve_baselines` returns `None` for every game."

**`banking_solver.py` — a scoring exploit, verified against engine source:**
> "- A scorecard card's score is the MAX over its plays (`arc_agi.scorecard.EnvironmentScoreList.score`).
> - RESET issued while the engine is in the WIN state performs a *full* reset even under
>   `ONLY_RESET_LEVELS=true` … and a full reset opens a NEW play on the SAME card …
> Strategy: once a session's WIN is fully recorded, prune the winning trace per level (drop actions
> that changed neither the frame nor `levels_completed`; a RESET voids everything since the level
> started) and replay it on a fresh play of the same card."

→ **Win slowly, then replay the pruned trace cheaply. The card keeps the max.** Aborting is free.

**`transfer_solver.py` + `family_store.py` — cross-clone transfer:**
> "This graft turns the 110 competition runs (25 public games cloned round-robin) into a
> cooperative pool: the first clone of a family to clear a level *publishes* its pruned per-level
> action sequence to the process-global `family_store`, and later clones of the SAME family
> *replay* that sequence mechanically … A sibling that would otherwise cold-start can skip straight
> to the deepest already-solved level for free."
> "All 110 competition runs share ONE process and ONE ThreadPoolExecutor (`HarnessSolver` fans
> games out under a single `Semaphore(28)`), so a module-level singleton guarded by a lock is the
> whole coordination mechanism."

Clone detection is an initial-frame fingerprint; a miss degrades to stock.

**`schema_helpers.py` / `schema_notes.py` / `schema_void.py`** reverse-engineer a rival named
"Schema" described as "the top LB agents' pattern":
> "Schema … grounds its reasoning in `run_python` experiments over the observed grids — diffing
> frames, finding objects, summarizing action effects — instead of eyeballing ASCII."
> "Schema's harness lift came partly from a hard outer/inner loop — probe an unknown control
> cheaply, certify a hypothesis, plan one short sequence, commit, and void the plan the moment
> reality diverges."
> "Schema's execute-stage discipline — 'reality outranks the model; one surprise voids the rest of
> the plan' …"

**`hudmask.py`, `clickmap.py`, `goalkeep.py`, `lawbook.py`, `searchmap.py`, `recovery.py`,
`retry_guard.py`, `shortcircuit_solver.py`** — HUD-band segmentation out of `board_changed`;
per-click-target (not per-pixel) effect ledger; stop erasing the world model; check induced laws
against the board; infer the goal from action-space structure rather than reward; un-stick
GAME_OVER loops; cap the infinite 1 s retry loop that can otherwise burn a whole game's 7920 s on
a dead vLLM; trim homogeneous repeated-action batches once they stop having effect.

**A repeated cautionary result, verbatim from `clockwatch.py`:**
> "'waste' was twice measured and twice found not to be waste: the inert clicks a suppressor would
> have removed were the sweep that cleared the level, and the arm with zero inert actions died
> twice and scored zero. … the games that SCORED have the HIGHEST concentration of clock in a
> single long analysis step (a median 35% for the arm that cleared three levels against 21% for the
> arm that cleared none). Long thinking is not the disease. Long thinking with no idea what it
> costs, ending in a plan the clock never let the agent play, is."

---

## 4. VARIANCE — read this before reading anything into one submission

- Jeroen Cottaar, topic 716696: *"No, it's very unstable, ranging from 0.7 to 1.3."*
- Official write-up: *"our best submission got scores as low as 0.77% on Kaggle and on the public
  games we observe standard deviations of up to 0.4."*
- yw8837, topic 731522, 11 official submissions from one lineage:
  **1.29, 1.05, 0.71, 0.73, 0.68, 0.75, 0.55, 1.11, 1.17, 0.90, 0.94** —
  *"more local actions, tokens, or public-game levels did not reliably improve the hidden score."*
- Public→private gap, topic 736578 (Nick Pellegrin): Duck+Qwen3.8 scored ~2.1% locally on the 25
  public games and ~1.4% on the LB; **his own harness scored 5.0–5.4% locally and still ~1.4% on
  the LB.** Local public-set score is a weak predictor.

With one submission per day, a single A/B is not measurable. Plan accordingly.

---

## 5. KAGGLE MECHANICS — confirmed by measurement, not folklore

`machine_shape` is real. From four independently-authored, GPU-running kernels' own
`kernel-metadata.json` (pulled via `kaggle kernels pull -m`):

| kernel | machine_shape | enable_gpu | enable_internet |
|---|---|---|---|
| `foysalemonshanto/lb-9-arc3-duck-v12-with-qwen-3-8-27b` | `NvidiaRtxPro6000` | true | false |
| `keithtyser/duck-qwen3-8-27b-fp8` | `NvidiaRtxPro6000` | true | false |
| `jeroencottaar/tufa-labs-duck-harness-june-30-milestone-winner` | `NvidiaRtxPro6000` | true | false |
| `thtennant/arc3-duck-v22` | `NvidiaRtxPro6000` | true | false |
| `ko0kip/arc-agi-3-gemma-4-31b-reflection-agent` | `NvidiaRtxPro6000` | true | false |

Model attachment string, verbatim in every one of them:
`"model_sources": ["foysalemonshanto/qwen3-8-27b-fp8-repacked-v1/PyTorch/hf-fp8/1"]`
(PascalCase `PyTorch` in metadata; mounts lowercase at
`/kaggle/input/models/foysalemonshanto/qwen3-8-27b-fp8-repacked-v1/pytorch/hf-fp8/1`).

Two docker images appear: `gcr.io/kaggle-private-byod/python@sha256:57e612b4…` on the RTX PRO 6000
kernels, `gcr.io/kaggle-images/python@sha256:e5452ce6…` on the CPU one.

Wheelhouse: `driessmit1/arc3-vllm-h100-wheelhouse-v3`, installed with
`pip install --no-index --find-links {WHEELHOUSE} --requirement {WHEELHOUSE}/requirements.lock
--target /kaggle/working/vllm-site-packages --upgrade --ignore-installed --only-binary :all:
--no-compile`, then `PYTHONPATH={SITE_PACKAGES}`. Stamp file
`vllm==0.19.0 torch==2.10.0 flashinfer==0.6.6` caches the install across restarts. **I did not
download it** — the file listing (`kaggle datasets files`) was sufficient.

Competition wheelhouse `/kaggle/input/competitions/arc-prize-2026-arc-agi-3/arc_agi_3_wheels`
supplies only `arc-agi` itself.

Gateway handshake for the graded rerun, verbatim:
```python
os.environ.setdefault("ARC_API_KEY", "test-key-123")
os.environ.setdefault("ARC_BASE_URL", "http://gateway:8001/")
os.environ.setdefault("OPERATION_MODE", "competition")
# poll http://gateway:8001/api/games until status < 500, 600 s deadline
```
and `KAGGLE_IS_COMPETITION_RERUN` is the flag that distinguishes a graded run.

### Correction to the brief

The brief said `scripts/build_notebook.py` "writes the notebook-metadata string `nvidiaRtx6000`
and never writes `machine_shape` at all." **That is no longer true of the file on disk** — but read
the provenance note below before acting on this.

It now carries a documented `rtxpro6000` profile:

```python
"rtxpro6000": {
    "name": "nvidiaRtxPro6000",
    "gpu": True,
    "machine_shape": "NvidiaRtxPro6000",
    "model_sources": [QWEN38_MODEL_SOURCE],
    "dataset_sources": [VLLM_WHEELHOUSE_DATASET],
},
```
with `_ACCELERATOR_ALIASES = {"rtx6000": "rtxpro6000"}` and a comment recording the measurement
that settled it ("we pushed `metadata.kaggle.accelerator == "nvidiaTeslaT4"` with no
`machine_shape`, and the server stored `machine_shape == "Gpu"` — the notebook string was
ignored"). The remaining gap is only that **`ACCELERATOR = "t4"` is still the module default**, so
the checked-in `notebooks/kernel-metadata.json` is stale t4 output with empty
`model_sources`/`dataset_sources`. Flipping that constant to `"rtxpro6000"` and re-running the
builder is the whole fix. My finding here **confirms** the `NvidiaRtxPro6000` value against five
live kernels, which was previously unverified.

**Provenance — this file is being edited live by a concurrent session.** `scripts/build_notebook.py`
has an mtime of 2026-08-24 22:03, i.e. *inside* the window of this research pass, and
`git diff --stat` shows +197/−32 consisting almost entirely of the `machine_shape`/`rtxpro6000`
work. I only ever read this file (`sed -n`, `grep`); I wrote nothing outside
`notes/kaggle_working_recipe.md`. So the brief was probably accurate when it was written, and a
sibling agent fixed it while I was reading. Treat my quoted snippet as a snapshot of an in-flight
edit, not as a settled state, and re-read the file before relying on it. The independent part of my
finding — the five live kernels all carrying `"machine_shape": "NvidiaRtxPro6000"` — stands on its
own regardless of what that script currently says.

---

## 6. SYNTHESIS — what the scoring approaches have in common that ours lacks

Ours: `agent/my_agent.py`, deterministic, `MAX_ACTIONS = 400`, no LLM. `scripts/arm_c2_harness.py`,
per its own docstring, gates the model behind the scaffold — *"the model NEVER sees pixels"*, it is
consulted only when the scaffold stalls, and it returns a symbolic subgoal the scaffold validates.
It scored 0.30 vs the scaffold's 0.50.

*(The 0.14 hidden is the NO-MODEL scaffold 55692780, not an agent run — corrected 2026-09-21;
our model stack's hidden scores are 0.34 / 0.24 / 1.56 / 0.76. The 0.5043 public aggregate and
arm_c2 0.30 are taken from the brief I was given. I did not re-run them. Everything attributed to a Kaggle kernel, dataset, forum topic,
or leaderboard below is read directly from that source.)*

Seven differences, roughly in order of expected impact.

**1. The model is the player, not an advisor.** Every scoring harness puts the LLM in the driver's
seat with the environment reachable from its own code. Ours puts a deterministic scaffold in the
seat and lets the model suggest. Tufa states this as a design principle: *"This keeps the model in
the driver seat."* Our arm_c2 result (0.30 < 0.50) is the predictable outcome of consulting a model
that cannot see the board and cannot act — it is not evidence that LLM-in-the-loop fails here.

**2. Code execution with a live `action()` — the single biggest structural gap.** They do not parse
an action out of model text. They hand the model a REPL where `action(['LEFT','LEFT'])` is a
function call whose return value refreshes `current_frame` *inside the running snippet*. The model
writes BFS and drives it. Our arm_c2 has a REPL but the model proposes subgoals that our scaffold
then validates and executes — the model never closes the loop itself.

**3. No action cap; a wall-clock cap.** `max_actions_per_game=None`, `max_runtime_s_per_game=7920`,
`concurrency=28`. Our `MAX_ACTIONS=400` is a hard ceiling on how deep we can ever get, and depth is
what the score cap rewards (`cap = 100 * sum(i completed) / sum(i all levels)`). We are capping the
resource that pays and ignoring the one that binds.

**4. Structured perception handed over, raw grid withheld.** 4-connected-component segmentation with
position-invariant object hashes, containment (`children`), adjacency — *plus* a 4–8× upscaled PNG
in every user turn — and an explicit refusal to expose the numeric grid so the model cannot burn
context describing pixels. We solve perception well (25/25 by intervention) but keep the result
inside the scaffold instead of handing it to a reasoner as a manipulable object graph.

**5. An explicit, parsed, re-injected world model.** Labelled blocks
(`World model:` / `Goal model:` / `Action model:` / `Plan:` / `Cross-level notes:`) extracted from
assistant text and re-injected, wiped on level transition except cross-level notes, with
"BEFORE EXECUTING NEW ACTIONS YOU MUST ALWAYS GIVE THE REVISED VERSION OF THE WORLD MODEL." This is
the composition mechanism we are missing — the thing that carries a mechanic learned on level 1
into level 3.

**6. Mechanical guards under the model, not prompt hints.** `NoopGuard` *blocks* a
`(level, board_sig, action)` proven inert; auto-RESET on game-over without a model call;
context-overflow trim-and-retry; per-game wall-clock enforcement. Cheap, deterministic, and they
compose with a fallible model instead of trusting it.

**7. Serving flags we are currently missing.** `--reasoning-parser qwen3` (our `:5300` lacks it —
that is exactly the `</think>`-in-content leak), `--enable-auto-tool-choice --tool-call-parser
qwen3_coder` (the entire output contract is tool calls, so without this there is no agent),
`--enable-prefix-caching`, `--generation-config vllm`,
`--default-chat-template-kwargs '{"preserve_thinking": true}'`. Sampling `temp 0.6 / top_p 0.95 /
top_k 20`, thinking on, **no `max_tokens` cap**. For Qwen3.8 specifically, keithtyser's overlay
(transformers 5.8.0 + huggingface_hub 1.5.0 over the 0.19.0 wheelhouse, `--kv-cache-dtype fp8`) is
the working recipe.

### Measured gap against our own live server

Our running vLLM on `:5300` (PID 125196, left untouched), verbatim from `pgrep -af`:

```
vllm serve /home/ignaz/.cache/kagglehub/models/foysalemonshanto/qwen3-8-27b-fp8-repacked-v1/pyTorch/hf-fp8/1 \
  --served-model-name qwen38 --host 127.0.0.1 --port 5300 \
  --max-model-len 32768 --max-num-seqs 256 --gpu-memory-utilization 0.90 --trust-remote-code
```

Missing versus the working recipe: `--enable-auto-tool-choice`, `--tool-call-parser qwen3_coder`,
`--reasoning-parser qwen3`, `--enable-prefix-caching`, `--generation-config vllm`,
`--default-chat-template-kwargs '{"preserve_thinking": true}'`; and `--max-model-len` is 32768
against their 65536.

**The first two are blocking, not cosmetic.** Without `--enable-auto-tool-choice
--tool-call-parser qwen3_coder` the server never populates `message.tool_calls`, and the entire
Duck contract is a `python` tool call. Any local test of this architecture against `:5300` as
currently launched will fail in a way that looks like "the model won't use the tool" but is
actually a serving flag. `--reasoning-parser qwen3` is the separate, already-known `</think>`
leak. Note `/home/ignaz/vllm-venv/work/serve.sh` also mounts the checkpoint from a `pyTorch`
(mixed-case) kagglehub path, which differs from Kaggle's lowercase `pytorch` mount — worth keeping
straight when porting paths.

### Above the harness — two ideas nobody's baseline has

- **Banking (`banking_solver.py`).** Card score is the max over plays; RESET-from-WIN opens a new
  play on the same card. Win however slowly, prune the trace, replay it cheaply, keep the max.
- **Cross-clone transfer (`transfer_solver.py`).** The 110 hidden runs are ~25 families of clones
  in one process. Publish a solved level's pruned action sequence to a process-global store; later
  siblings replay it and skip straight to the deepest solved level. Both degrade safely to stock.

### The honest strategic read

Cloning the Duck harness gets us to the 2.4–2.8 crowd, not past it. But we are at 0.14 with a
scaffold that has no model in the loop at all, and the gap between us and the pack is entirely
architectural, not a matter of tuning.
> **[2026-09-21]** This paragraph is from 2026-08-24 and its premise has moved: we DID clone the
> Duck harness, and the model-in-the-loop stack now scores 1.56 hidden (56377237), not 0.14. The
> 0.14 remains the scaffold's. Keep the architectural argument, drop the number.

The fastest credible path is: take the public Duck source, swap in Qwen3.8 with the keithtyser serving
overlay, and — this is where our own asset actually pays — feed our intervention-based
controlled-object identification in as a *preloaded sandbox helper or a seeded `Action model:`
note*, since identifying the controlled object in 25/25 games is precisely the probe phase the
27B model currently spends its scarce token budget rediscovering.

Two caveats before anyone plans around a number: one submission per day, and the same code has
been measured from 0.55 to 1.29 on this leaderboard.

**Licence — RESOLVED 2026-09-21. Upstream declares MIT; our own bundles said CC0, which was
wrong and is now corrected.** What settled it (primary source, read today, not recalled):

- The Kaggle dataset licence field on `jeroencottaar/taaf-kaggle-source-share` — the exact field
  the escalation below says "someone should read" — is **`licenses: [{"name": "MIT"}]`** (Kaggle
  API `get_dataset_metadata`, dataset_id 10710965, collaborator group `tufa-labs`, role WRITER).
  That is the owner's own declaration on the artifact we redistribute, not a third party's claim
  about it, so yw8837's assertion in topic 731522 checks out.
- The GitHub repo `Tufalabs/duck-harness` still ships **no LICENSE file**, and
  `tufa-arc-agi-framework/pyproject.toml` still declares no licence field.
  `ARC3-Inference/pyproject.toml:25`'s classifier `"License :: OSI Approved :: MIT License"`
  remains the only in-source statement. Our bundles already carry `src/ARC3-Inference/LICENSE`
  (MIT text plus an explicit note that the redistributor added it and it confers nothing beyond
  Tufa's grant) and `src/tufa-arc-agi-framework/NOTICE`. Those stay — they are the precise
  statement; the Kaggle licence dropdown is only the closest single label.

**WHAT WAS WRONG, and why the new value is right.** The `dataset-metadata.json` for the 029 and
029-visual bundles declared **`CC0-1.0`**. CC0 is a public-domain dedication: it asserts we waive
all rights in the whole bundle — including Tufa Labs' code, which is not ours to dedicate — and it
strips the attribution requirement that the bundled MIT LICENSE and NOTICE exist to preserve. Both
now read `{"name": "MIT"}`, matching the upstream grant, keeping the attribution chain intact, and
satisfying the competition's OSI-licence requirement.

**STILL OPEN — do not mark these done:**
1. The qwen38 bundle's `job/kaggle/source-dataset/dataset-metadata.json` still says `CC0-1.0`.
   Same one-line change; it was outside this pass's file scope.
2. The already-published Kaggle datasets keep the old CC0 field until a **metadata-only** push
   (`kaggle datasets metadata -p <dir>`, then update — do NOT re-upload the files, the bundles are
   large and the push would be a full re-version). Nothing was pushed here; publishing under
   the investigator's account is the investigator's call.
3. This repo has **no LICENSE file at all**. An OSI licence is required before submission; MIT is
   the compatible choice given the MIT dependency. That is a whole-project licensing decision, so
   it is flagged here, not silently made.
4. Residual caveat, stated rather than papered over: `tufa-arc-agi-framework` declares no licence
   anywhere. The dataset-level "MIT" label is the closest available enum value, not a claim that
   every file in the bundle was granted under MIT. The NOTICE file carries that distinction.

<details><summary>Original escalation, kept verbatim for the record (Aug 24)</summary>

**Licence — do not treat this as settled.** I checked and could not confirm a clean answer:
- The source bundles contain **no LICENSE file**. `src/ARC3-Inference/pyproject.toml` carries only
  the classifier `"License :: OSI Approved :: MIT License"` — a metadata classifier, not a licence
  grant, and I found no corresponding licence text anywhere in the bundle.
- yw8837 asserts in topic 731522: *"The notebook is public under Kaggle's Apache 2.0 notebook
  license. The attached TAAF source bundle is marked MIT."* That is a third-party claim about
  someone else's dataset; I did not verify the Kaggle dataset page's declared licence field.
- The write-up says *"We make the code freely available on GitHub"* and *"We release this harness
  with the hope of lowering the barrier to entry"*, which is intent, not a licence.

Given the competition's OSI-licence requirement, someone should read the actual GitHub repo's
LICENSE and the Kaggle dataset licence field before any of this is reused in a submission. That is
The investigator's call, not mine.

</details>

---

## 7. Search log — what was actually queried

Read-only Kaggle CLI only. No pushes, no submissions, no comments, no votes.

- `kernels list --competition arc-prize-2026-arc-agi-3 --page-size 100 --sort-by scoreDescending` (100 rows)
- `kernels list --search "arc-agi-3" --page-size 100` (100 rows)
- `kernels pull -m` on: `foysalemonshanto/lb-9-arc3-duck-v12-with-qwen-3-8-27b`,
  `keithtyser/duck-qwen3-8-27b-fp8`, `jeroencottaar/tufa-labs-duck-harness-june-30-milestone-winner`,
  `jeroencottaar/taaf-duck-harness-kaggle`, `gregkamradt/arc-agi-3-gpt-oss-120b`,
  `ko0kip/arc-agi-3-gemma-4-31b-reflection-agent`, `nihilisticneuralnet/arc-agi-3-qwen3-8-27b-bf16`,
  `thtennant/arc3-duck-v22`, `mbmmurad/arc-agi-3-lb-0-86-3rd-place-candidate-milestone`,
  `ruichardliu/milestone1-2nd-solution`
- `datasets files` on: `jakobbrggen/taaf-kaggle-source-anim-20260807-anim`,
  `jeroencottaar/taaf-kaggle-source-share`, `keithtyser/taaf-duck-qwen38-serving-v1`,
  `driessmit1/arc3-vllm-h100-wheelhouse-v3`
- `datasets download --unzip` (source bundles only, ~460 KB each; **wheelhouse NOT downloaded**):
  `jakobbrggen/taaf-kaggle-source-anim-20260807-anim`, `jakobbrggen/taaf-kaggle-source`,
  `jeroencottaar/taaf-kaggle-source-share`, `thtennant/taaf-kaggle-source-share-fork`,
  `keithtyser/taaf-duck-qwen38-serving-v1`
- `competitions leaderboard arc-prize-2026-arc-agi-3 -s --page-size 30`
- `forums topics list -s "duck harness" / "arc-agi-3 approach"`;
  `forums topics show` on 717133, 716696, 736578, 734843, 731522, 729743, 732419, 705022
- `forums topics list arc-prize-2026-arc-agi-3` → **403 Forbidden** (per-competition forum listing
  is not permitted for this account; the global `-s` search worked and reached the same threads)

Working copies: `/tmp/claude-1000/-home-ignaz/035bfc82-234a-4c8f-9525-c9a174c42147/scratchpad/kk/`
(session scratch — copy anything you want to keep before it is reaped).
