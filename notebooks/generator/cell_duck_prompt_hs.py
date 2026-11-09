# ---- HAN SOLO PROMPT ADDITIONS (2026-10-05, findings 179) ----------------------------------------------------------------
# House rule: the vendored Duck source stays byte-identical, so this is a monkeypatch exec'd in cell 14 -- embedded in the
# notebook text by build_notebook.py (PROMPT_HS=1), so the frozen bundle dataset is not re-uploaded. Also exec-able by
# notebooks_duck/ab_local.py for a local arm.
#
# WHAT THIS IS. Lord Han Solo scores 23.84 on the ARC-AGI-3 hidden set against our 2.55 on the same engine family, model
# family and hardware class, with a PUBLIC harness bundle. His prompts.py is 171 lines against our 114. Finding 179 names
# four things his prompt tells the model that ours never does. This shim ports them.
#
#   piece      findings 179 item           where it goes in the system prompt            his source
#   role       (the preamble)              very front                                    prompts.py:9  ROLE_PREAMBLE
#   overview   1 "every game is solvable"  appended to GAME_OVERVIEW_ADDENDUM            prompts.py:51,56,57,58
#              2 the scoring function
#              3 what the border meter is
#   strategy   (the frame for all of it)   appended at the VERY END, after multimodal     prompts.py:143-171
#   audit      4 the stuck-triggered       into the per-turn USER message, right after    prompts.py:11-46
#                strategy audit            "Valid actions right now:"                     + solver.py:231-249,307-310,476-477
#
# ===========================================================================================================================
# CORRECTION TO THE BRIEF, read this first
# ===========================================================================================================================
# (1) `role` IS ALREADY SHIPPED. His ROLE_PREAMBLE is byte-identical to a line we have always had:
#       his  prompts.py:9      ROLE_PREAMBLE = "You are a coding agent solving a grid-based puzzle game."
#       our  tool_agent.py:351 prompt = "You are a coding agent solving a grid-based puzzle game."
#     Same string, already first in the system prompt. He factored it into a named constant; we inline it. Porting it adds
#     ZERO tokens and changes nothing. This shim therefore ASSERTS it is present and first rather than duplicating it, and
#     counts it as 0 added tokens. One of the "four things we never do" is a thing we already do.
#
# (2) findings 179 items 1, 2 and 3 are NOT in GENERAL_GAME_STRATEGY_ADDENDUM. They are in his GAME_OVERVIEW_ADDENDUM
#     (prompts.py:51, 56-58), which the brief did not list as a port target. Porting only the brief's four named pieces
#     would ship a knob containing NONE of findings 179 items 1-3 and only item 4 -- i.e. the arm would not test the
#     hypothesis it exists to test. The `overview` piece below closes that gap. It is the cheapest text in the shim
#     (4 sentences, no identifiers) and carries three of the four claims the finding is about.
#
# ===========================================================================================================================
# ADAPTATION / DROP TABLE -- his text vs OUR harness
# ===========================================================================================================================
# The rule (the brief's hardest constraint): text that names a runtime variable, result key, tool, helper or state field our
# harness does not expose is WORSE than no text, because it instructs the model to use something that does not exist. Every
# row below was verified against primary source, not against his prompt's own description of his harness.
#
#  #  his clause (abridged)                               our harness                                  action taken here
# --  --------------------------------------------------  -------------------------------------------  ---------------------
#  1  `current_frame.crop(row_min, col_min, ...)`         NO crop(). FrameView exposes only .ascii     ADAPTED -> `current_frame.ascii`
#     (strategy 148)                                      .step .level .shape .segmentation
#                                                         (python_tool_sandbox.py:127-146)
#  2  "Previously assigned frames or rows remain          NO .rows attribute                           DROPPED "or rows"
#     snapshots" (strategy 165)
#  3  "Read `changed_pixels` first as a cheap magnitude   NO changed_pixels ANYWHERE (0 grep hits in    ADAPTED -> `board_changed`
#     check. 0 means... a handful of cells is most        bundle + notebooks_duck). We have the BOOL    (bool, always) + `diff()['changed']`
#     often a timer tick..." (strategy 164)               `board_changed` (tool_agent.py:1425).        (int, natives; CONDITIONAL on
#                                                         Nearest int: natives `diff()['changed']`     DUCK_NATIVES=1 -- which cell 14
#                                                         (cell_duck_natives.py:34-46)                 setdefaults to 1 in every build).
#                                                                                                      The magnitude LADDER is harness-
#                                                                                                      independent and survives intact.
#  4  "how many of the `total_pixels` cells"              NO total_pixels                              DROPPED
#  5  "check its `animation` before concluding it did     NO animation surface. cell_duck_anim.py adds  DROPPED (re-added automatically
#     nothing" (strategy 167)                             animation(n) ONLY under DUCK_ANIM=1, which   iff DUCK_ANIM=1 at install)
#                                                         is OFF in every shipped build
#  6  "print a compact observation of the relevant        same as #5                                   DROPPED "and animation"
#     objects, status indicators and animation"
#     (audit 36-38)
#  7  "reuse saved functions when applicable. Save        NO save_module/load_module/read_module/       ADAPTED -> the persisted-defs
#     small extractors, rules or planners" (strategy      saved_modules ANYWHERE (0 grep hits).        mechanism we DO have
#     157)                                                BUT DUCK_PERSIST_DEFS=1 in every build:      (CONDITIONAL on
#                                                         the model's top-level defs persist across    DUCK_PERSIST_DEFS=1)
#                                                         its later python calls within a game
#                                                         (cell_duck_natives.py:112-130)
#  8  "merely to satisfy `save_module`, including         no save apparatus, no check()                 DROPPED (3 sentences).
#     `check(True, True)`. Every new test must call at                                                  KEPT: "test its predictions
#     least one module function..." (strategy 158)                                                      against observed transitions",
#                                                                                                       "Passing tests confirms only
#                                                                                                       those examples", "A complete
#                                                                                                       simulator is optional"
#  9  "Saved tests retain the observations available      no saved tests                                DROPPED sentence 1; kept
#     when first added" (strategy 159)                                                                  sentence 2, reworded
# 10  "put the hypothesis and predicted outcomes in       NO `plan` parameter. Our python tool          ADAPTED -> the `Plan:` assistant-
#     the python call's plan" (audit 34-35)               declares exactly one property, `code`         text prefix our user prompt
#     "Include the finding ... in that action's plan"     (tool_agent.py:1266-1276)                     already advertises
#     (audit 42-43)                                                                                     (tool_agent.py:1250)
# 11  "...so they remain available in history after       Our `World model:` / `Recent findings:` /     ADAPTED, and made accurate:
#     compaction" (audit 43)                              `Plan:` prefixed assistant text IS            "...so they survive into the next
#                                                         extracted and carried into the next user      turn's prompt; these carry within
#                                                         prompt, and is cleared ONLY on a level        a level and are cleared when the
#                                                         transition / game over / run complete        level changes"
#                                                         (tool_agent.py:1105-1126) -- NOT every turn
# 12  "Saved notes and passing tests of your own code"    no saved notes                                ADAPTED -> "Notes you have
#     (audit 27)                                                                                        written and passing tests..."
# 13  "If revising a saved rule, add the observed         no saved rules/tests                          DROPPED
#     counterexample to its tests" (audit 43-44)
# 14  "The turn is over as soon as a `python` call        FALSE for us. We allow several action()        DROPPED (his overview line 53;
#     executes an action, so anything you want to do      calls per snippet and our user prompt says    not ported)
#     after acting must live inside that same snippet"    so (tool_agent.py:1234, 1246, 1494-1519)
#     (his overview 53)
#
# PORTED AS-IS, verified to resolve in our harness: current_frame.segmentation (python_tool_sandbox.py:136-140),
# current_frame.ascii (:129), .step/.level/.shape (:130-132), node `hash` and `pixels` (utils/segmentation.py:196-197),
# transitions / last_transition (:205-222, 344-345), previous_frame (:346-348), valid_actions, action(...) taking an ordered
# list (:269-307), the refusal of further action() calls after a terminal result (tool_agent.py:1494-1519), and
# score/reward/state/level_completed/game_over/run_complete/done (tool_agent.py:1416-1430).
#
# NOT PORTED, and why: his MULTIMODAL_CONTEXT_ADDENDUM (prompts.py:127-131) asserts "Each user turn attaches an image of the
# current board". Our shipped arm is TEXT-ONLY (cell 14 forces MULTIMODAL_CONTEXT=""), so that text would be a false claim.
# It is not a port target and nothing in the two blocks we DO port asserts an image exists -- checked clause by clause.
# His STRUCTURED_RUNTIME_STATE_ADDENDUM is also not ported: it documents a frame/history/game_overs/save_module API we do
# not have, and replacing our runtime-state section with a description of HIS runtime would be the single most dangerous
# text in the bundle. The arm tests his STRATEGY and DISPOSITION text against our runtime description, not his runtime.
#
# DUPLICATION, declared rather than silently resolved: roughly half his strategy bullets restate things our
# VISUAL_GAME_ADDENDUM / PYTHON_ADDENDUM / COMPACT_TOOL_SESSION_ADDENDUM already say (his 146 ~ our prompts.py:24;
# his 152 ~ our :86; his 168 ~ our :90; his 147 ~ our :28-29). They are KEPT. Pruning them on my judgement of redundancy
# would add a second, unmeasured variable to an arm whose whole point is "his text, externally validated at 9x our score,
# against ours" -- and his prompt being LONGER and more repetitive than ours is part of the artifact under test. No clause
# of his CONTRADICTS ours (checked pairwise); the cost of the duplication is tokens, and the exact token cost is measured
# by tests/cmp_fixes/prompt_hs/measure_cost.py rather than estimated.
#
# THE AUDIT TRIGGER (his framework/solver.py:231-249, 307-310, 476-477), ported exactly:
#   interval  = initial per-game runtime limit * 0.25, or None when there is no limit  (his :239-241)
#   due when    time.monotonic() - started_at >= interval                              (his :248-249)
#   started_at  RESETS on a level clear                                                (his :307-310)
#   started_at  is pushed forward when an audit is CONSUMED by a completed analysis     (his :476-477)
#   His docstring: "Use the fixed initial budget, independent of actions, lives and model claims." That refusal to trust
#   the model's self-report is the point and is preserved: there is no model-reported stuck signal anywhere in this shim.
#   OUR "fixed initial budget" is `solver.max_runtime_s_per_game` (solver.py:213-217), snapshotted ONCE per game at
#   session start. That matters: CLOCK=dyn (cell_dyn_clock.py) replaces runtime_limit_reached/timing_payload with a
#   DYNAMIC per-game deadline but leaves max_runtime_s_per_game as the shipped fixed clock -- so reading it at session
#   start is exactly his "fixed initial budget" and is immune to the dynamic clock. Reading timing_payload() instead
#   would have silently made the interval model- and schedule-dependent.
#   A level clear is detected as `reward > 0` on an executed action, which in our solver is exactly
#   `levels_completed > previous levels_completed` (solver.py:697-700) -- i.e. his `level_cleared` (his solver.py:986).
#   A retryable analysis failure does NOT consume the audit (his :460-477 continues before the reset), so the retry still
#   carries it. Preserved here.
#
# CONCURRENCY. Games run concurrently (ThreadPoolExecutor + asyncio.Semaphore, solver.py:884-898) and there is ONE
# analyzer per game (`analyzer = self._make_analyzer(...)`, solver.py:1223). All audit state therefore lives on the
# per-game session object and is reached through `analyzer._hs_session`; nothing is module-global and no thread-local is
# needed. A module-global "audit due" flag would have cross-talked between the 14-28 games in flight.
#
# WHICH ARM TO RUN (decision 10-05, findings 183b) -- and do NOT read the primary arm as "+1112"
#   DUCK_PROMPT_HS=overview,audit   PRIMARY. Carries ALL FOUR of findings 179's claims for a MEASURED +139 prompt
#                                   tokens per request, +488 in the user message only on the turns the audit fires.
#   DUCK_PROMPT_HS=1                SECONDARY: the above plus his strategy addendum, +1112 tok/request (+39.9%). The
#                                   extra 973 tokens are his FRAMING, not one of the four claims, and about half of it
#                                   restates our own prompt. At CTX=32768 the trim binds, so +1112 displaces history --
#                                   as the primary arm it would confound prompt content with context pressure.
#   Measured with the real served Flash-Next tokenizer, each arm probed on its own (additivity verified, not assumed):
#   tests/cmp_fixes/prompt_hs/measure_cost.py -> cost_prompt_hs.json.
#     role +0 (already ours)   overview +139   strategy +973   audit +488 (user, when due)
#
# SWITCHES
#   DUCK_PROMPT_HS   runtime: unset/0 = inert. "1" = all four pieces. Or a comma list of
#                    role,overview,strategy,audit to enable pieces individually.
#   build-time       PROMPT_HS in notebooks_duck/kaggle_flashnext/build_notebook.py (same values).
#   DUCK_PROMPT_HS_LOG  optional jsonl: one row per audit fired / consumed / reset.
#
# SAFETY. Every anchor is asserted at install. A mismatch raises on a validation/quota run (TRUE_SUBMISSION False) and, on
# the hidden rerun, is printed while the shipped prompt stays. Any exception inside the per-turn wrappers leaves the prompt
# unmodified and is printed once.
# ---------------------------------------------------------------------------------------------------------------------------
import json as _hs_json
import os as _hs_os
import threading as _hs_threading
import time as _hs_time

_HS_RAW = (_hs_os.environ.get("DUCK_PROMPT_HS", "") or "").strip().lower()
_HS_ALL = ("role", "overview", "strategy", "audit")
if _HS_RAW in ("", "0", "off"):
    _HS_PIECES = frozenset()
elif _HS_RAW in ("1", "all"):
    _HS_PIECES = frozenset(_HS_ALL)
else:
    _HS_PIECES = frozenset(p.strip() for p in _HS_RAW.split(",") if p.strip())
_HS_ON = bool(_HS_PIECES)

# Which conditional clauses resolve depends on shims that are themselves knob-gated. Read them at install, never assume.
_HS_NATIVES = (_hs_os.environ.get("DUCK_NATIVES", "") or "").strip() == "1"
_HS_PERSIST = (_hs_os.environ.get("DUCK_PERSIST_DEFS", "") or "").strip() == "1"
_HS_ANIM = (_hs_os.environ.get("DUCK_ANIM", "") or "").strip() == "1"

_HS_ROLE_PREAMBLE = "You are a coding agent solving a grid-based puzzle game."

# --- piece `overview`: findings 179 items 1, 2, 3. His prompts.py:51, 56, 57, 58. No identifiers; nothing to adapt. -------
_HS_OVERVIEW_ADDENDUM = (
    "- Every game is solvable.\n"
    "- A level you do not clear scores zero, and among cleared levels fewer actions score higher up to a limit.\n"
    "- Later levels weigh more than earlier ones, and the game score cannot exceed the share of that weight you have cleared.\n"
    "- Many games run a per-level action budget, drawn on the board as a long line near an edge or a strip of small blocks "
    "flush against a border, which changes each step while the interior stays the same. It is a readout of that budget "
    "rather than a puzzle element, every executed action counts against it whether or not the board changed, and "
    "exhausting it ends the level in a game over.\n"
)


def _hs_strategy_addendum():
    """His GENERAL_GAME_STRATEGY_ADDENDUM (prompts.py:143-171), with rows 1,2,3,5,7,8,9 of the table applied.

    Built as a function because three clauses are CONDITIONAL on shims that may be off (natives, persisted defs,
    animation): a clause that names a helper the run does not have is the one failure mode this shim exists to avoid.
    """
    # -- magnitude check (table row 3). board_changed is always there; diff() only with the natives.
    if _HS_NATIVES:
        magnitude = (
            "- Read `last_action_result['board_changed']` first as a cheap yes/no check, then call `diff()` when you need "
            "the magnitude: `diff()['changed']` counts the cells that differ between `previous_frame` and `current_frame`. "
            "0 means the board ended identical to the one before the call, a handful of cells is most often a timer or "
            "step-bar tick, a moderate count fits one object moving or recoloring, and a very large count usually means a "
            "scene reset, a new level, or the view scrolling over a level larger than the grid.\n"
        )
    else:
        magnitude = (
            "- Read `last_action_result['board_changed']` first as a cheap yes/no check. When you need the magnitude, count "
            "the differing cells between `previous_frame.ascii` and `current_frame.ascii` yourself. None means the board "
            "ended identical to the one before the call, a handful of cells is most often a timer or step-bar tick, a "
            "moderate count fits one object moving or recoloring, and a very large count usually means a scene reset, a "
            "new level, or the view scrolling over a level larger than the grid.\n"
        )
    # -- reuse of the model's own code (table row 7). We have persisted defs, not save_module.
    if _HS_PERSIST:
        reuse = (
            "- Write purpose-built Python for the current question. Top-level functions and classes you define persist "
            "across your later `python` calls in this game, so reuse them instead of rewriting them, and define small "
            "extractors, rules or planners when they will be reused.\n"
        )
    else:
        reuse = (
            "- Write purpose-built Python for the current question. Every `python` call starts fresh, so rewrite the small "
            "extractors, rules or planners you still need rather than assuming they survived.\n"
        )
    # -- the no-op check (table row 5). The animation clause only exists when cell_duck_anim.py is installed.
    noop = (
        "- If an action reports `board_changed` false, "
        + ("check its animation with `animation()` before concluding it did nothing. " if _HS_ANIM else "")
        + "Do not repeat it under the same observed conditions without a distinct prediction to test. Change the action, "
        "its target, or your hypothesis instead.\n"
    )
    return (
        "\n\n## General game strategy\n"
        "\n### Reading the board\n"
        "- Treat each board as a scene with objects, blockers, targets, adjacency, containment, motion, and symmetry.\n"
        "- A long line near an edge or a strip of small blocks flush against a border is a readout, not a puzzle element. "
        "Never click through it segment by segment as if it were puzzle pieces.\n"
        # table row 1: his `current_frame.crop(...)` -> our `.ascii`
        "- Read the board through `current_frame.segmentation` first. Use `current_frame.ascii` only for a small, specific "
        "region that segmentation does not answer, and never to scan or summarize the whole board.\n"
        "- Track objects across frames by `hash`, color, overlap, bounding-box proximity, area change and edge contact "
        "rather than by exact coordinates alone.\n"
        "\n### Deciding what to do\n"
        "- Maintain a compact working world model: what actions seem to do, what the goal likely is, what remains "
        "uncertain, which hypotheses the observations have ruled out, and what plan best fits the evidence so far.\n"
        "- When the game is about navigating something to a target, it is usually safer to write an explicit search "
        "algorithm such as BFS than to steer by hand. More generally, when the objective is understood but the best "
        "action order is unclear, pathfinding, flood fill, BFS, DFS, beam search, shortest-path search, limited "
        "action-sequence search and custom heuristics are all valid.\n"
        "- Optimize for the shortest reliable sequence that advances the current goal as described by your world model. "
        "If confidence is low, program a discriminating probe and revise the world model from the result.\n"
        "- Once the important state variables and action effects are sufficiently understood, stop probing and search in "
        "the inferred state space.\n"
        "- A strong default loop is: summarize the board, infer the desired environment change, write a small scorer or "
        "search over candidate sequences, then execute the best probe or plan with `action(...)`.\n"
        "- You can call the `python` tool as many times as you want per turn. Investigate until your code has a probe or "
        "plan that the evidence favors. Full certainty is not required to take an action.\n"
        + reuse
        # table row 8: the save_module/check() sentences dropped, the testing discipline kept
        + "- When creating or repairing a rule, test its predictions against observed transitions. Test the planner itself "
        "and its goal conditions on known examples before treating an empty search result as evidence about the game. "
        "Passing tests confirms only those examples. A complete simulator is optional.\n"
        # table row 9
        "- Use settled frames and specific observed transitions as the examples you check a rule against.\n"
        "- Never give up. When stuck, revise your hypotheses and try a different approach.\n"
        "\n### Acting and checking\n"
        "- `action(...)` takes an ordered list of one or more actions. Once your code has selected a reliable sequence, it "
        "is often useful to batch it.\n"
        "- Batch freely once you know what each action in the sequence will do. When you are unsure, send only the first "
        "few actions of it, then check the resulting board next turn before sending the rest.\n"
        + magnitude
        # table row 2: "or rows" dropped
        + "- Inside action loops, read `current_frame` again after every action. Previously assigned frames remain "
        "snapshots.\n"
        "- After every action, distinguish countdown or remaining-step changes from changes to gameplay objects and "
        "task-status indicators. A countdown tick alone is not evidence of progress. A changed task-status indicator can "
        "be evidence once you verify what it tracks.\n"
        + noop
        + "- Never print or echo full board frames. Return only compact derived summaries such as object lists, diffs, "
        "coordinates, counts, or tiny local crops, and keep the output short and interpretable however long the code is.\n"
        "- Re-ground on the newest frame after any score increase or abrupt scene change; the returned board may already "
        "be the next level.\n"
        "- Strategies may transfer loosely across levels, but layouts and mechanics can change. Re-check the new board "
        "before repeating a plan.\n"
    )


def _hs_audit_prompt():
    """His STRATEGY_AUDIT_PROMPT (prompts.py:11-46), with rows 6, 10, 11, 12, 13 of the table applied."""
    observe = (
        "In the same snippet inspect each action's result before issuing another and print a compact observation of the "
        "relevant objects"
        + (", status indicators and animation.\n" if _HS_ANIM else " and status indicators.\n")  # table row 6
    )
    return (
        "\nStrategy audit for this turn\n"
        "You may be stuck on this level. Briefly check whether your current approach is making progress.\n"
        "- First check whether recent observations match your predictions and advance a concrete plan. If so, briefly "
        "state the supporting observation and next expected result, then continue the plan without an extra experiment or "
        "the remaining audit steps.\n"
        "- You may also continue a search with a defined scope and stopping condition if its transition rules have been "
        "checked against actual game observations and no unresolved contradiction undermines it. Briefly state that "
        "evidence and the remaining search work. Confidence, passing tests of your own model or a growing search count "
        "alone are not evidence of progress.\n"
        "- If neither continuation is supported, or observations contradict the approach, use the audit below. Do not "
        "reset the game or abandon a plan solely because of this audit.\n"
        "When an assumption audit is needed\n"
        # table row 12: "Saved notes" -> "Notes you have written"
        "- Separate observed facts from assumptions about success, state variables, controls and how a candidate solution "
        "is evaluated. For each assumption, briefly state what observation supports it. If none does, treat it as "
        "untested. Notes you have written and passing tests of your own code do not establish that the assumed rules are "
        "complete.\n"
        "- Choose one uncertain assumption that could explain the contradiction or lack of confirmed progress and an "
        "alternative interpretation. First check existing `transitions` for evidence that distinguishes them. If they "
        "already settle the question, apply that finding and continue. Otherwise design one short discriminating "
        "experiment that preserves current progress where possible. A complete test may need both configuration and "
        "execution actions.\n"
        # table row 10: his python-call `plan` parameter -> our `Plan:` assistant-text prefix
        "- For a new experiment, state the hypothesis and predicted outcomes under a `Plan:` prefix in your assistant "
        "text before the tool call, then execute it with `action(...)`. "
        + observe
        + "Stop the sequence if an intermediate result contradicts the prediction. You will read this output on the next "
        "turn.\n"
        # table rows 10, 11, 13
        "- After an experiment, on the next turn compare prediction with observation before further actions and revise any "
        "contradicted rule, state representation or goal. Mark indistinguishable outcomes inconclusive. Put the finding "
        "and its supporting observation under your `Recent findings:` prefix so they survive into the next turn's prompt; "
        "those carry within a level and are cleared when the level changes. Add step numbers when useful. Use prior audit "
        "findings to avoid repeating an inconclusive experiment unchanged.\n"
    )


# ---------------------------------------------------------------------------------------------------------------------------
# The audit clock. Pure, no harness imports, so the trigger can be unit-tested without a game, a GPU or a server:
# `_HSAuditClock` IS the shipped object the wrappers drive -- tests exercise this, not a copy of it.
# ---------------------------------------------------------------------------------------------------------------------------
class _HSAuditClock:
    """His solver.py:231-249 / 307-310 / 476-477.

    `budget` is the FIXED initial per-game runtime limit. Not the remaining time, not a dynamic deadline, not anything
    the model reports -- his docstring is explicit that the point is independence from all three.
    """

    FRACTION = 0.25

    def __init__(self, budget, started_at):
        self.interval = budget * self.FRACTION if (budget is not None and budget > 0) else None
        self.started_at = started_at
        self.fired = 0
        self.resets = 0

    def due(self, now):
        """his _should_audit_strategy: 'Use the fixed initial budget, independent of actions, lives and model claims.'"""
        return self.interval is not None and (now - self.started_at) >= self.interval

    def consume(self, analysis_started_at):
        """his solver.py:476-477 -- push the clock forward only once an analysis actually completed."""
        self.started_at = max(self.started_at, analysis_started_at)
        self.fired += 1

    def level_cleared(self, now):
        """his solver.py:307-310 -- clearing a level restarts the audit clock."""
        self.started_at = now
        self.resets += 1


def _hs_inject_audit(text, audit_text):
    """Insert the audit block immediately after the "Valid actions right now:" line of a user prompt.

    His tool_agent.py:711 appends it after that same line. A module-level function so a test can drive the SHIPPED
    insertion against a real user prompt without constructing a ToolAgent. Returns None when the anchor is absent, so
    the caller can leave the prompt untouched and say so rather than silently appending the block somewhere else.
    """
    lines = text.split("\n")
    at = next((i for i, line in enumerate(lines) if line.startswith("Valid actions right now:")), None)
    if at is None:
        return None
    lines.insert(at + 1, audit_text)
    return "\n".join(lines)


_hs_log_lock = _hs_threading.Lock()


def _hs_log(event, **fields):
    path = _hs_os.environ.get("DUCK_PROMPT_HS_LOG")
    if not path:
        return
    try:
        row = {"t": round(_hs_time.time(), 3), "event": event, **fields}
        with _hs_log_lock, open(path, "a", encoding="utf-8") as fh:
            fh.write(_hs_json.dumps(row, ensure_ascii=True) + "\n")
    except Exception:
        pass


_hs_warned = set()


def _hs_warn(where, exc):
    if where in _hs_warned:
        return
    _hs_warned.add(where)
    print(f"PROMPT_HS: {where} error {type(exc).__name__}: {exc} (prompt left unmodified; printed once)", flush=True)


def _hs_install():
    import inspect as _hs_inspect

    import inference.agent.tool_agent as ta
    import inference.framework.solver as sv
    from inference.utils.grid_utils import ARC_COLOR_LEGEND as _HS_LEGEND

    T = ta.ToolAgent
    S = sv._HarnessGameSession
    if getattr(T, "_hs_installed", False):
        print("PROMPT_HS: already installed (second exec ignored)", flush=True)
        return

    # ---- anchors. Every one must hold, or we are patching a harness we have not read. -------------------------------------
    assert callable(getattr(ta, "_build_system_prompt", None)), "tool_agent._build_system_prompt missing"
    probe = ta._build_system_prompt(tool_output_tokens=4096)
    assert probe.startswith(_HS_ROLE_PREAMBLE), (
        "ROLE_PREAMBLE anchor: our system prompt no longer starts with the preamble Han Solo's ROLE_PREAMBLE duplicates "
        f"(got {probe[:80]!r})"
    )
    # The audit injection anchor is a line of the USER prompt, so it is asserted against that method's source rather
    # than the system prompt. (An `x in y or True` assert here would be a check that cannot fail -- findings 181.)
    assert hasattr(T, "_build_user_prompt") and hasattr(T, "analyze"), "ToolAgent anchors changed"
    _hs_user_src = _hs_inspect.getsource(T._build_user_prompt)
    assert _hs_user_src.count("Valid actions right now:") == 1, (
        "audit anchor: 'Valid actions right now:' occurs "
        f"{_hs_user_src.count('Valid actions right now:')} times in _build_user_prompt, expected exactly 1"
    )
    assert hasattr(S, "play") and hasattr(S, "_execute_action"), "_HarnessGameSession anchors changed"
    assert "max_runtime_s_per_game" in getattr(
        sv.HarnessSolver, "__annotations__", {}
    ), "solver.HarnessSolver.max_runtime_s_per_game (the fixed initial budget) is gone"
    # The overview anchor is the last line of our GAME_OVERVIEW_ADDENDUM. ARC_COLOR_LEGEND is NOT in tool_agent's
    # namespace (checked), so it is imported from where prompts.py gets it.
    _hs_legend_anchor = f"- Color legend: {_HS_LEGEND}.\n"
    assert probe.count(_hs_legend_anchor) == 1, (
        f"overview anchor: the colour-legend line occurs {probe.count(_hs_legend_anchor)} times in the system prompt, "
        "expected exactly 1"
    )

    strategy_text = _hs_strategy_addendum()
    audit_text = _hs_audit_prompt()

    # ---- piece `role` + `overview` + `strategy`: the system prompt -------------------------------------------------------
    _hs_orig_build_system = ta._build_system_prompt

    def _hs_build_system_prompt(*, tool_output_tokens):
        prompt = _hs_orig_build_system(tool_output_tokens=tool_output_tokens)
        # `role`: assert, never duplicate. His ROLE_PREAMBLE is already our first line, byte for byte.
        if "role" in _HS_PIECES and not prompt.startswith(_HS_ROLE_PREAMBLE):
            prompt = _HS_ROLE_PREAMBLE + prompt
        if "overview" in _HS_PIECES:
            # findings 179 items 1-3, appended to the overview section -- anchored on the last line of our
            # GAME_OVERVIEW_ADDENDUM (the colour legend) so it lands inside the overview, not after the runtime reference.
            if prompt.count(_hs_legend_anchor) == 1:
                prompt = prompt.replace(_hs_legend_anchor, _hs_legend_anchor + _HS_OVERVIEW_ADDENDUM, 1)
            else:  # legend moved: put the four sentences at the top of the prompt rather than losing them
                prompt = prompt.replace(
                    _HS_ROLE_PREAMBLE, _HS_ROLE_PREAMBLE + "\n\n" + _HS_OVERVIEW_ADDENDUM, 1
                )
        if "strategy" in _HS_PIECES:
            prompt += strategy_text  # his assembly: the strategy block is LAST, after the multimodal section
        return prompt

    ta._build_system_prompt = _hs_build_system_prompt

    # ---- piece `audit`: the per-turn user message + the trigger -----------------------------------------------------------
    _hs_orig_user = T._build_user_prompt
    _hs_orig_analyze = T.analyze
    _hs_orig_play = S.play
    _hs_orig_exec = S._execute_action

    def _hs_build_user_prompt(self, *a, **kw):
        text = _hs_orig_user(self, *a, **kw)
        if "audit" not in _HS_PIECES or not getattr(self, "_hs_audit_due", False):
            return text
        try:
            # his tool_agent.py:711 -- injected right after the "Valid actions right now:" line
            out = _hs_inject_audit(text, audit_text)
            if out is None:
                _hs_warn("_build_user_prompt", RuntimeError("'Valid actions right now:' line not found"))
                return text
            return out
        except Exception as e:
            _hs_warn("_build_user_prompt", e)
            return text

    def _hs_analyze(self, *a, **kw):
        clock = None
        due = False
        started = _hs_time.monotonic()
        if "audit" in _HS_PIECES:
            try:
                sess = getattr(self, "_hs_session", None)
                clock = getattr(sess, "_hs_clock", None) if sess is not None else None
                due = clock is not None and clock.due(started)
            except Exception as e:
                _hs_warn("analyze/due", e)
                clock, due = None, False
        self._hs_audit_due = due
        try:
            result = _hs_orig_analyze(self, *a, **kw)
        finally:
            self._hs_audit_due = False
        try:
            # his solver.py:460-477: a RETRYABLE failure does not consume the audit, so the retry still carries it.
            if due and clock is not None and result is not None and not getattr(result, "retryable_failure", False):
                clock.consume(started)
                _hs_log("audit_consumed", fired=clock.fired, interval=clock.interval)
        except Exception as e:
            _hs_warn("analyze/consume", e)
        return result

    def _hs_play(self, *a, **kw):
        try:
            # his __post_init__ (solver.py:236-242): the FIXED initial budget, snapshotted once, before any level runs.
            self._hs_clock = _HSAuditClock(self.solver.max_runtime_s_per_game, self.started_at)
            self.analyzer._hs_session = self
            _hs_log("clock_init", budget=self.solver.max_runtime_s_per_game, interval=self._hs_clock.interval)
        except Exception as e:
            _hs_warn("play/init", e)
        return _hs_orig_play(self, *a, **kw)

    def _hs_execute_action(self, *a, **kw):
        payload = _hs_orig_exec(self, *a, **kw)
        try:
            # his _track_life (solver.py:307-310). `reward > 0` here is exactly his `level_cleared`
            # (levels_completed > previous levels_completed; our solver.py:697-700).
            clock = getattr(self, "_hs_clock", None)
            if clock is not None and isinstance(payload, dict) and float(payload.get("reward", 0.0) or 0.0) > 0.0:
                clock.level_cleared(_hs_time.monotonic())
                _hs_log("audit_clock_reset", level=payload.get("level"), score=payload.get("score"))
        except Exception as e:
            _hs_warn("_execute_action", e)
        return payload

    if "audit" in _HS_PIECES:
        T._build_user_prompt = _hs_build_user_prompt
        T.analyze = _hs_analyze
        S.play = _hs_play
        S._execute_action = _hs_execute_action
    T._hs_installed = True
    T._hs_pieces = tuple(sorted(_HS_PIECES))
    # The exact strings this knob adds, published so a test can gate every identifier they name against an allowlist
    # (tests/cmp_fixes/prompt_hs/test_prompt_hs.py). Scanning these is the only way to gate the ADDED text precisely:
    # the audit block is inserted mid-prompt, so any "everything after the heading" slice would also catch stock text.
    T._hs_strategy_text = strategy_text if "strategy" in _HS_PIECES else ""
    T._hs_audit_text = audit_text if "audit" in _HS_PIECES else ""
    T._hs_overview_text = _HS_OVERVIEW_ADDENDUM if "overview" in _HS_PIECES else ""

    extra = ta._build_system_prompt(tool_output_tokens=4096)
    assert extra.startswith(_HS_ROLE_PREAMBLE), "post-install: system prompt no longer starts with the role preamble"
    if "strategy" in _HS_PIECES:
        assert extra.endswith(strategy_text), "post-install: the strategy addendum is not last in the system prompt"
    print(
        "PROMPT_HS INSTALLED: pieces=" + ",".join(sorted(_HS_PIECES))
        + f" | system prompt {len(probe)} -> {len(extra)} chars"
        + (f" | audit every 0.25 x per-game clock, injected after 'Valid actions right now:'" if "audit" in _HS_PIECES else "")
        + f" | conditionals: natives={int(_HS_NATIVES)} persist_defs={int(_HS_PERSIST)} anim={int(_HS_ANIM)}",
        flush=True,
    )


if _HS_ON:
    unknown = _HS_PIECES - set(_HS_ALL)
    if unknown:
        raise ValueError(f"DUCK_PROMPT_HS: unknown piece(s) {sorted(unknown)}; valid: {list(_HS_ALL)} (or 1 for all)")
    try:
        _hs_install()
    except Exception as _hs_e:
        if not bool(globals().get("TRUE_SUBMISSION", False)):  # a validation / quota run fails loudly
            raise
        print(
            f"PROMPT_HS: NOT INSTALLED ({type(_hs_e).__name__}: {_hs_e}) -- TRUE_SUBMISSION: the shipped prompt runs unchanged",
            flush=True,
        )
else:
    print("PROMPT_HS: off (DUCK_PROMPT_HS unset / 0)", flush=True)
