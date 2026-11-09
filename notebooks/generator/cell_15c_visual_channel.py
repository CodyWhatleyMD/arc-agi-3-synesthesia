# ============================================================================
# VISUAL CHANNEL for the Duck harness: low-norm glyphs + borrowed VISION-TOWER
# vectors. The experiment arm. One variable over the glyph-only arm.
#
# LAYER 1 (carrier): Duck's sixteen board glyphs become the low-norm set, with
#   the legend, sandbox map and per-turn prompt all patched -- exactly the
#   glyph-only arm (cell_lownorm_glyphs.py), which runs first as its control.
# LAYER 2 (channel): every request gets one prompt_embeds part appended to its
#   last user message: the current 64x64 board, one embedding per cell, where
#   cell (r,c) is   embed(glyph[colour])  +  ALPHA * K * visual[colour]/|visual[colour]|
#   -- the low-norm carrier nudged toward the colour's own vector from the
#   model's VISION TOWER (a solid patch of that colour through the encoder,
#   pooler_output, mean). Not the word "red": the tower's red.
#
# Why these choices, each from a measurement:
#   * LOW-NORM carriers (not mnemonic letters): ~2x the nearest-neighbour margin
#     under the same rotation (gap 0.447 vs 0.222 at alpha 1.1), so the glyph
#     survives an alpha that destroys a letter. The mnemonic sweep found NO alpha
#     where glyph and colour both read; that sweep was never run on these.
#   * VISUAL basis, RAW not centred: centring strips the 98.8% shared component,
#     and that component is what makes the model treat the span as visual input.
#   * FIXED-MAGNITUDE injection: carrier norms span 0.31-0.45; scaling to each
#     carrier's norm made "alpha=1" sixteen different settings. K = mean carrier
#     norm, so alpha means one thing across colours.
#   * ALPHA from theory, not a mini-test (the investigator, 2026-09-16): the mnemonic "colour
#     reads" band was 2.0; low-norm margin is ~2x; 1.5 sits inside the window
#     where the glyph should survive and the colour should register. Overridable.
#
# FAIL LOUD, never silent: the install is CALLED and verified (both methods
# wrapped, basis shape matches the served hidden size, a probe wires 9 cells);
# a server that rejects prompt_embeds FAILS THE RUN -- an arm that silently
# fell back to text would report as "visual made no difference". (cell_15b
# defined its install and never called it; this cell exists because of that.)
# ============================================================================
import os as _os, io as _io, base64 as _b64, json as _json, time as _time
import functools as _ft, threading as _th, sys as _sys
from pathlib import Path as _P

VISUAL_CHANNEL_ENABLED = True
ALPHA          = float(_os.environ.get("CC_ALPHA", "1.5"))
RESERVE_TOKENS = 64 * 68 + 96          # 64 rows x (newline + 2-digit row number + space + 64 cells) + framing; both arms reserve it
MAX_EMBED_FAILURES = 3                 # then the run FAILS, it does not degrade
BASIS_PATH     = _os.environ.get("CC_BASIS_PATH", "")   # bases.pt with visual_raw (16, hidden)
CHECKPOINT     = _os.environ.get("CC_CHECKPOINT", "")   # for the carrier rows via safe_open

# ---- layer 1: the glyph-only arm, verbatim -----------------------------------
exec(open(_os.environ.get("CC_GLYPH_CELL", "notebooks_duck/cell_lownorm_glyphs.py")).read())
assert LOWNORM_GLYPHS_ENABLED, "visual channel requires the low-norm carrier layer"

if VISUAL_CHANNEL_ENABLED:
    import torch as _torch, numpy as _np, requests as _rq
    import inference.agent.tool_agent as _ta

    # ---- carrier rows: embed(glyph) for the 16 low-norm glyphs, lazily --------
    def _find_ckpt():
        if CHECKPOINT: return _P(CHECKPOINT)
        for root in ("/kaggle/input", "/home/ignaz/models"):   # kaggle-ok: Kaggle path first
            for idx in _P(root).rglob("model.safetensors.index.json"):
                return idx.parent
        raise RuntimeError("no checkpoint found; set CC_CHECKPOINT")
    def _embed_rows(ckpt, glyphs):
        from safetensors import safe_open
        from transformers import AutoTokenizer
        tok = AutoTokenizer.from_pretrained(str(ckpt))
        ids = []
        for g in glyphs:
            t = tok.encode(g, add_special_tokens=False)
            assert len(t) == 1, f"glyph {g!r} is {len(t)} tokens on this tokenizer"
            ids.append(t[0])
        idx = _json.load(open(ckpt / "model.safetensors.index.json"))["weight_map"]
        key = next(k for k in idx if k.endswith("embed_tokens.weight"))
        with safe_open(str(ckpt / idx[key]), "pt") as f:
            W = f.get_slice(key)
            rows = _torch.stack([W[i:i+1][0].float() for i in ids])
        return rows, key

    _ckpt = _find_ckpt()
    _carrier, _emb_key = _embed_rows(_ckpt, LOWNORM_GLYPHS)          # (16, hidden)
    _hidden = _carrier.shape[1]
    assert BASIS_PATH, "set CC_BASIS_PATH to a bases.pt holding visual_raw"
    _bases = _torch.load(BASIS_PATH)
    _visual = _bases["visual_raw"].float()                              # (16, hidden)
    assert _visual.shape == (16, _hidden), f"basis {tuple(_visual.shape)} != (16, {_hidden}) for this checkpoint"
    _K = _carrier.norm(dim=1).mean()
    FUSED = _carrier + ALPHA * _K * _visual / _visual.norm(dim=1, keepdim=True)   # (16, hidden)
    # sanity: each fused row is still nearest its OWN carrier among the 16
    _cos = _torch.nn.functional.normalize(FUSED, dim=1) @ _torch.nn.functional.normalize(_carrier, dim=1).T
    _own = int((_cos.argmax(dim=1) == _torch.arange(16)).sum())
    # Row structure (the investigator, 09-18): a 4096-token flat span made the model count tokens to find a row.
    # Each row now starts with newline + two-digit row number + space -- plain embeddings of those
    # tokens (structure, not colour); the one-colour-carrying-token-per-cell thesis is untouched.
    _SEPS = ["\n", " "] + [str(d) for d in range(10)]
    _sep, _ = _embed_rows(_ckpt, _SEPS)                                 # (12, hidden)
    TABLE = _torch.cat([FUSED, _sep], dim=0)                             # rows 0-15 cells, 16 '\n', 17 ' ', 18-27 digits
    def _row_index(g):
        rows, cols = g.shape; out = []
        for r in range(rows):
            out += [16, 18 + r // 10, 18 + r % 10, 17]
            out += [int(v) for v in g[r]]
        return _torch.tensor(out, dtype=_torch.int64)

    class _VisualChannel:
        def __init__(self):
            self.lock = _th.Lock(); self.calls = 0; self.injected = 0; self.failures = 0
            self.originals = []; self.cache = {}
            self.log_path = _P(_os.environ.get("CC_LOG", "visual_channel.jsonl"))
        def emit(self, **row):
            row["t"] = _time.time()
            with self.lock, open(self.log_path, "a") as f: f.write(_json.dumps(row) + "\n")
        def wire(self, grid):
            g = _np.asarray(grid, dtype=_np.int16); key = (g.shape, g.tobytes())
            if key in self.cache: return self.cache[key], int(g.size)
            idx = _row_index(_np.clip(g, 0, 15))
            out = TABLE.index_select(0, idx).to(_torch.bfloat16).contiguous()
            buf = _io.BytesIO(); _torch.save(out, buf)
            payload = _b64.b64encode(buf.getvalue()).decode("ascii")
            with self.lock:
                if len(self.cache) > 64: self.cache.clear()
                self.cache[key] = payload
            return payload, int(g.size)
        @staticmethod
        def inject(messages, payload, rows, cols):
            i = next((k for k in range(len(messages) - 1, -1, -1) if messages[k].get("role") == "user"), None)
            if i is None: return None
            c = messages[i].get("content")
            parts = list(c) if isinstance(c, list) else ([{"type": "text", "text": c}] if isinstance(c, str) else None)
            if parts is None: return None
            parts.append({"type": "text", "text": f"\n\nBoard ({rows} rows x {cols} cols, one symbol per cell, rows top to bottom; each line starts with its row number):"})
            parts.append({"type": "prompt_embeds", "data": payload})
            # Text anchor AFTER the span: with Duck's PNG removed the span was the last thing before the
            # assistant turn and the first response degenerated in 3/3 games (token loops, mangled tool XML).
            parts.append({"type": "text", "text": "\n(end of board)\n"})
            out = list(messages); out[i] = {**messages[i], "content": parts}; return out


    # ---- INSTRUCTIONS FOR THIS ARM, not Duck's (the investigator, 2026-09-18: "not copies of duck's instructions --
    # they won't apply with embeds only"). Duck's prompt names the segmentation graph as the primary view,
    # forbids scanning the board with .ascii, and says to reason from Python "instead of by eye" -- four
    # separate instructions to ignore the channel this arm adds. Applied at the request choke point so it
    # covers the system prompt, every per-turn user prompt, the no-tool-call nudge (an f-string inside
    # analyze()), and the python tool's description.
    BOARD_BLOCK = (
        "\n\nBoard in the message:\n"
        "- The current board is included directly in every user turn as a 64 x 64 grid of colour symbols: one symbol per cell, 64 per row, rows top to bottom, one line per row, each line starting with its two-digit row number and a space.\n"
        "- Each symbol carries its colour; the legend above maps symbols to colour names.\n"
        "- Read the board from this grid first: shapes, regions, objects, and what changed since the last turn. It is the same board `current_frame.ascii` returns in Python; use Python for exact coordinates, diffs and search, not to discover what the board looks like.\n"
    )
    _SUBS = [
        ("Use `current_frame.segmentation` as your primary view of the board -- objects, colors, shapes, containment, adjacency, and cross-frame object hashes. Use `current_frame.ascii` only to read a small, specific region; do not scan the whole board with it.",
         "The board grid in the message is your primary view of the board. Use `current_frame.segmentation` for object lists, colors, shapes, containment, adjacency, and cross-frame object hashes, and `current_frame.ascii` in code for exact coordinates and diffs."),
        ("- Use `current_frame.segmentation` as your primary view of the board -- objects, colors, containment, adjacency, and cross-frame object hashes.\n",
         "- The board grid in the message is your primary view of the board. Use `current_frame.segmentation` for object lists, containment, adjacency, and cross-frame object hashes.\n"),
        ("- Use `current_frame.ascii` only to read a small, specific region of the board when `segmentation` is not enough; never use it to scan or summarize the whole board.\n",
         "- Use `current_frame.ascii` in code when you need exact coordinates, a diff, or a search over the board.\n"),
        ("- Always inspect `current_frame`, `history`, and `valid_actions` from Python instead of reasoning from the raw board by eye.\n",
         "- Read the board from the grid first; then use Python on `current_frame`, `history`, and `valid_actions` to confirm coordinates and test hypotheses.\n"),
        ("- Inspect current and history frames from Python instead of describing frames freehand.\n", ""),
        ("- Never print or echo full board frames. Return only compact derived summaries",
         "- Never print or echo full board frames in tool output -- the board is already in the message. Return only compact derived summaries"),
        # --- the three "no raw grid" sentences. WAS WRONG: all three are FALSE, and the first
        # replacement below repeated the falsehood verbatim while rewriting the rest of the line.
        # Duck's sandbox FrameView stores the grid as `self._grid` (python_tool_sandbox.py:133) and
        # the host serialises it into every frame payload ("grid": [list(row) for row in frame.grid],
        # tool_agent.py:438), so `current_frame._grid` is a list of rows of ints in the live sandbox.
        # VERIFIED BY RUNNING THE REAL SANDBOX, not by reading: run_sandboxed_python printing
        # current_frame._grid returned [[5, 9], [14, 0]] with int cells, and the same attribute on
        # previous_frame / history[i].frame / last_transition.before_frame|after_frame.
        # WHY IT MATTERS: notes/plan_hypothesis_elimination.md item 3 declares S5 blocked because
        # "the raw numeric grid is not available" -- a plan stage parked on a prompt string that is
        # not true. Telling the model the truth unblocks `predict(grid, action) -> grid` with no
        # change to the vendored harness.
        # WHY THIS IS SAFE FOR THE ARM'S ONE VARIABLE: the model could already read the exact board
        # via `.ascii` and via the in-message grid; `._grid` is the same information in ints rather
        # than letters, not a new perceptual channel.
        # CAVEAT for whoever compares runs: this changes the visual arm's prompt text, so runs
        # before and after this edit differ by more than alpha.
        ("The raw numeric grid is not available. Use `.segmentation` as the primary view; use `.ascii` only to read a small, specific region. ",
         "The raw numeric grid IS available: every frame carries `._grid`, a list of rows of ints (ARC colour ids 0-15) -- `current_frame._grid`, `previous_frame._grid`, `history[i].frame._grid`, `last_transition.before_frame._grid` and `.after_frame._grid`. The board is also in this message. Use `.segmentation` for object lists and `.ascii` for a small specific region. "),
        ("- The raw numeric grid is intentionally not exposed. ",
         "- The raw numeric grid IS exposed: `current_frame._grid` is a list of rows of ints (ARC colour ids 0-15), and the same `._grid` exists on `previous_frame`, every `history[i].frame`, and `last_transition.before_frame`/`.after_frame`. "),
        ("Only letter-coded board views and lightweight metadata are exposed; raw numeric color IDs are not available.",
         "Letter-coded board views, lightweight metadata, and the raw numeric grid (`frame._grid`, rows of ints) are all exposed."),
        ("Keep tool output compact: use `current_frame.segmentation` as the primary view, and `current_frame.ascii` only for a small specific region; never print full boards.",
         "Read the board from the grid at the end of this message first. Keep tool output compact: use `current_frame.segmentation` for object lists and `current_frame.ascii` in code for exact coordinates and diffs; never print full boards (the board is already in this message)."),
        ("use `current_frame.segmentation` as the primary view, and `.ascii` only for a small specific region",
         "read the board from the grid in the message, use `current_frame.segmentation` for object lists and `.ascii` in code for exact coordinates"),
    ]
    _FORBIDDEN = ("as your primary view", "as the primary view", "by eye", "freehand", "never use it to scan", "do not scan the whole board")
    def _clean_text(t):
        if not isinstance(t, str): return t
        for a, b in _SUBS: t = t.replace(a, b)
        if "\n\nVisual-game guidance:" in t and "Board in the message:" not in t:
            t = t.replace("\n\nVisual-game guidance:", BOARD_BLOCK + "\nVisual-game guidance:", 1)
        return t
    def _clean_messages(messages):
        out = []
        for m in messages:
            if m.get("role") in ("system", "user"):
                c = m.get("content")
                if isinstance(c, str): m = {**m, "content": _clean_text(c)}
                elif isinstance(c, list): m = {**m, "content": [({**pt, "text": _clean_text(pt.get("text"))} if pt.get("type") == "text" else pt) for pt in c]}
            out.append(m)
        return out
    def _clean_tools(tools):
        if not isinstance(tools, list): return tools
        out = []
        for t in tools:
            t = _json.loads(_json.dumps(t))
            f = t.get("function") if isinstance(t, dict) else None
            if isinstance(f, dict) and isinstance(f.get("description"), str): f["description"] = _clean_text(f["description"])
            out.append(t)
        return out

    _chan = _VisualChannel()

    def _wrap_build_user_message(orig):
        @_ft.wraps(orig)
        def w(self, user_prompt, current_frame):
            self._cc_frame = current_frame
            return orig(self, user_prompt, current_frame)
        return w
    def _wrap_chat_completion(orig):
        @_ft.wraps(orig)
        def w(self, messages, **kw):
            _chan.calls += 1
            messages = _clean_messages(messages)
            if "tools" in kw: kw["tools"] = _clean_tools(kw["tools"])
            grid = getattr(getattr(self, "_cc_frame", None), "grid", None)
            if not grid: return orig(self, messages, **kw)
            payload, n = _chan.wire(grid)
            patched = _VisualChannel.inject(messages, payload, len(grid), max(len(r) for r in grid))
            if patched is None: return orig(self, messages, **kw)
            # CIRCUIT BREAKER (findings 25/27). vLLM's multimodal encoder cache can evict
            # an image entry while MTP still references it (vllm#38551; fix #39544 is
            # not in 0.27.1). The engine then answers 500 "internal error during
            # generation" for EVERY retry of a request carrying that image, and Duck
            # retries at 1s with no ceiling -- Kaggle's vc33 lost 75 min to it; the
            # local alpha sweep lost all 18 games. The bug is keyed on the image, so:
            # on such a 500, retry up to 3x with image parts stripped from the CURRENT
            # user turn (text, graph and the embeds span still describe the board),
            # log it, and only then re-raise. A game degrades for one turn instead of
            # dying for the rest of its clock.
            # NOTE (2026-09-21): this line used to read `attempts = 0; patched = messages`,
            # which OVERWROTE the injected message list built at the inject() call above --
            # so the channel computed the embeds, guarded them, then sent the ORIGINAL
            # messages and counted the call as `injected`. Every visual run from b47bf8e
            # (the breaker) onward was a lownorm run wearing a visual label. Keep `patched`.
            attempts = 0
            if getattr(self, "_images_off", False):   # flipped after three failed strips: image-less for the rest of this run
                patched = [({**m, "content": [pt for pt in m["content"] if pt.get("type") != "image_url"]} if isinstance(m.get("content"), list) else m) for m in patched]
            while True:
                try:
                    pass
                    r = orig(self, patched, **kw)
                    self._consec_500 = 0
                    _chan.injected += 1
                    # WIRE WITNESS. Duck's own *_requests.jsonl is written BEFORE
                    # _chat_completion is called (tool_agent.py:1812 vs 1823), so it
                    # records what Duck BUILT, never what this wrap SENDS -- it can
                    # never show prompt_embeds even when the channel works. And the
                    # install banner only proves the basis loaded. So record the part
                    # types of the list actually handed to the origin: that is the one
                    # place a dead channel cannot hide, and it is what caught this
                    # channel shipping 2,930 empty "injections".
                    _wire = [pt.get("type") for _m in patched
                             if isinstance(_m.get("content"), list)
                             for pt in _m["content"]]
                    _chan.emit(event="injected", cells=n, finish=getattr(r, "finish_reason", None),
                               image_stripped=attempts > 0,
                               wire_parts=_wire,
                               embeds_on_wire=("prompt_embeds" in _wire))
                    return r
                except _rq.RequestException as e:
                    msg = str(e)
                    if ("500" in msg or "Internal server error" in msg) and attempts < 3:
                        attempts += 1
                        # Strip images from EVERY message, history included: the evicted hash is the PREVIOUS frame's
                        # picture, not the current turn's (findings 31). Text + segmentation graph still describe the board.
                        stripped = []; patched = list(patched)
                        for k in range(len(patched)):
                            c = patched[k].get("content")
                            if isinstance(c, list) and any(pt.get("type") == "image_url" for pt in c):
                                stripped += [pt for pt in c if pt.get("type") == "image_url"]
                                patched[k] = {**patched[k], "content": [pt for pt in c if pt.get("type") != "image_url"]}
                        _chan.emit(event="server_500_retry", attempt=attempts, images_stripped=len(stripped), error=msg[:200])
                        print(f"VISUAL CHANNEL: server 500 (mm-cache bug); retry {attempts}/3 with {len(stripped)} image(s) stripped", flush=True)
                        if stripped or attempts == 1:
                            continue
                    if "prompt_embeds" in msg or "prompt embeds" in msg:
                        _chan.failures += 1
                        _chan.emit(event="embeds_rejected", error=msg[:300], failures=_chan.failures)
                        print(f"VISUAL CHANNEL: server rejected prompt_embeds ({_chan.failures}/{MAX_EMBED_FAILURES}): {msg[:120]}", flush=True)
                        if _chan.failures >= MAX_EMBED_FAILURES:
                            raise RuntimeError("visual channel: server does not accept prompt_embeds -- FAILING the run rather than degrading to text") from e
                    if "500" in msg or "Internal server error" in msg:
                        self._consec_500 = getattr(self, "_consec_500", 0) + 1
                        if self._consec_500 >= 3 and not getattr(self, "_images_off", False):
                            self._images_off = True
                            print("BREAKER: three consecutive failed turns on server 500s -- this agent runs image-less from here on", flush=True)
                    raise
        return w

    # ---- INSTALL (called, verified, loud) -----------------------------------
    _ctx_env = int(_os.environ.get("LOCAL_ANALYZER_CONTEXT_WINDOW", "65536"))
    _ta._LOCAL_ANALYZER_CONTEXT_WINDOW = _ctx_env - RESERVE_TOKENS     # from env, NOT hardcoded
    for owner, name, factory in ((_ta.ToolAgent, "_build_user_message", _wrap_build_user_message),
                                 (_ta.ToolAgent, "_chat_completion", _wrap_chat_completion)):
        orig = getattr(owner, name); _chan.originals.append((owner, name, orig))
        setattr(owner, name, factory(orig))
    for name in ("_build_user_message", "_chat_completion"):
        assert getattr(getattr(_ta.ToolAgent, name), "__wrapped__", None) is not None, f"{name} NOT wrapped"
    _p, _n = _chan.wire(((5, 5, 0), (5, 9, 0), (14, 14, 14)))
    assert _n == 9 and len(_p) > 100, "probe wire failed"
    # ---- END-TO-END INJECTION PROBE ---------------------------------------
    # The existing asserts above cover the INSTRUCTION substitution and that both
    # methods are wrapped. Neither covers the thing that actually broke: for a
    # month `attempts = 0; patched = messages` overwrote the injected list one
    # line after inject() built it, so the wrapper computed the embeds, logged
    # 2,930 `injected` events, and put the ORIGINAL messages on the wire. Every
    # visual run from b47bf8e onward was a lownorm run wearing a visual label,
    # and nothing in the install output could tell you.
    # So: drive the REAL wrapper with a recording stub in place of `orig` and
    # assert that what reaches `orig` carries the prompt_embeds part. No network,
    # no GPU, costs one dict copy, and it fails loudly the next time someone
    # rebinds `patched` between inject() and the call.
    class _ProbeAgent:
        pass
    _probe_agent = _ProbeAgent()
    _probe_agent._cc_frame = type("F", (), {"grid": ((5, 5, 0), (5, 9, 0), (14, 14, 14))})()
    _probe_seen = {}

    def _probe_orig(self, messages, **kw):
        _probe_seen["messages"] = messages
        return type("R", (), {"finish_reason": "stop", "message": {"content": ""},
                              "usage": None})()
    _probe_msgs = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]
    _wrap_chat_completion(_probe_orig)(_probe_agent, _probe_msgs)
    _got = _probe_seen.get("messages")
    assert _got is not None, "INJECTION PROBE: wrapper never called through to orig"
    _last_user = [m for m in _got if m.get("role") == "user"][-1]
    _parts = _last_user.get("content")
    # inject() always turns the last user turn into a PARTS LIST; a bare string here
    # means the un-injected message list is what reached orig.
    assert isinstance(_parts, list), (
        f"INJECTION PROBE FAILED: last user content reaching orig is {type(_parts).__name__}, "
        "not a parts list -- the injected list was discarded and the ORIGINAL messages "
        "went on the wire. This is the b47bf8e defect: the arm runs as lownorm while "
        "logging itself as visual.")
    _types = [p.get("type") for p in _parts]
    assert "prompt_embeds" in _types, (
        f"INJECTION PROBE FAILED: last user message reaching orig has parts {_types}, "
        "no prompt_embeds span -- the visual channel is not on the wire.")
    _chan.calls -= 1; _chan.injected -= 1     # do not let the probe pollute the counters
    print(f"VISUAL CHANNEL INJECTION PROBE PASSED: prompt_embeds reaches the call "
          f"(last user parts: {_types})", flush=True)
    _sys_prompt = _clean_text(_ta._build_system_prompt(tool_output_tokens=1024))
    assert "Board in the message:" in _sys_prompt, "board block not inserted"
    for _f in _FORBIDDEN: assert _f not in _sys_prompt, f"Duck instruction survived in system prompt: {_f!r}"
    for _a, _ in _SUBS: assert _a not in _sys_prompt, f"unreplaced: {_a[:60]!r}"
    _u = _clean_text("Keep tool output compact: use `current_frame.segmentation` as the primary view, and `current_frame.ascii` only for a small specific region; never print full boards.")
    assert _u.startswith("Read the board from the grid"), "user-prompt substitution failed"
    assert "as the primary view" not in _clean_text("x use `current_frame.segmentation` as the primary view, and `.ascii` only for a small specific region y"), "nudge substitution failed"
    _pp = _chan.log_path.with_name("prompt_visual_arm.txt"); _pp.write_text(_sys_prompt)
    print(f"VISUAL ARM INSTRUCTIONS: board block inserted, {len(_SUBS)} Duck lines replaced; system prompt saved to {_pp}", flush=True)
    _chan.emit(event="installed", alpha=ALPHA, K=float(_K), hidden=_hidden, own_nearest=_own,
               reserve=RESERVE_TOKENS, context_window=_ta._LOCAL_ANALYZER_CONTEXT_WINDOW, ckpt=str(_ckpt), basis=BASIS_PATH)
    print("ARM=lownorm_visual", flush=True)
    print(f"VISUAL CHANNEL INSTALLED  alpha={ALPHA}  K={float(_K):.3f}  hidden={_hidden}  fused-rows-nearest-own-carrier={_own}/16  "
          f"window={_ta._LOCAL_ANALYZER_CONTEXT_WINDOW}  ckpt={_ckpt.name}  log={_chan.log_path}", flush=True)
else:
    print("ARM=lownorm_glyphs (VISUAL_CHANNEL_ENABLED=False)", flush=True)
