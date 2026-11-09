# ============================================================================
# LOW-NORM GLYPHS for the Duck harness. One variable, reversible, fail-closed.
#
# Paste as ONE cell AFTER the customization hook (cell 14) and BEFORE the
# benchmark run (cell 26). It changes exactly one thing: the sixteen characters
# Duck uses to render a board as text. Everything else -- image, segmentation
# graph, prompts, budgets, concurrency -- is byte-identical to the 6.295 run.
#
# WHAT CHANGES.  ARC_COLOR_CHARS "WwgGcBMPRbSYOrNp"  ->  "겪쏟눠됩멤굉촬훨꽤ങ탓뀌볍穌썼繽"
#
# WHY THESE. Measured on the served tokenizer (Qwen3.8 family, vocab 248320):
#   - every glyph is ONE token and NEVER merges with its neighbour, so cell (r,c)
#     is token r*W+c exactly. Duck's letters merge in runs ("WWWWWWWW" = 4 tokens),
#     so its ASCII is not per-cell addressable across background.
#   - their embedding norms sit at the 1st percentile of the vocabulary (0.31-0.45
#     vs a mean of 0.90), i.e. they carry the least prior meaning of any single-
#     token glyphs -- a board of them cannot be mistaken for prose, code, or
#     markdown. Duck's letters are ordinary English capitals; a wall of them has
#     no reading except gibberish, and B/G/R also occur inside the model's own
#     prose with no boundary between "cell value" and "letter in a word".
#   - NONE is markdown syntax. The two commonest colours in our own harness were
#     rendered as ' ' and '`' and the board read as EMPTY / "the image failed"
#     (r=+0.69 with blank-glyph fraction). Nothing here has that property.
#
# COST, stated up front: a 64x64 board is exactly 4,096 tokens this way; Duck's
# merging letters make it ~2-3k. Duck's history trim is already binding, so this
# arm carries fewer prior frames in context. That is a property of the variable
# under test, not something to correct for -- it is logged, not compensated.
#
# THE TRAP this cell exists to handle: three modules bind the glyph map or the
# legend by NAME at import time, so patching grid_utils alone leaves the sandbox
# and the system prompt on the old map. All three are patched, and the cell
# refuses to continue unless every one of them verifies.
# ============================================================================
import os as _os
import re as _re
import sys as _sys

LOWNORM_GLYPHS_ENABLED = True      # kill switch: False = the exact 6.295 configuration

# GLYPHS env overrides the carrier set (findings 89: 7 of these 16 cannot be echoed by the
# stock model in isolation; an echo-safe set is a separate ARM, not an edit). Must be 16 chars.
LOWNORM_GLYPHS = _os.environ.get("GLYPHS") or "겪쏟눠됩멤굉촬훨꽤ങ탓뀌볍穌썼繽"   # empty env = default
assert len(LOWNORM_GLYPHS) == 16 and len(set(LOWNORM_GLYPHS)) == 16, f"GLYPHS must be 16 distinct chars, got {LOWNORM_GLYPHS!r}"
assert len(LOWNORM_GLYPHS) == 16 and len(set(LOWNORM_GLYPHS)) == 16

if LOWNORM_GLYPHS_ENABLED:
    import inference.utils.grid_utils as _gu
    import inference.agent.prompts as _pr
    import inference.agent.python_tool_sandbox as _sb
    import inference.agent.tool_agent as _ta
    from inference.agent.runtime_state import Frame as _Frame

    OLD_CHARS = _gu.ARC_COLOR_CHARS
    OLD_LEGEND = _gu.ARC_COLOR_LEGEND
    assert OLD_CHARS == "WwgGcBMPRbSYOrNp", f"unexpected Duck map {OLD_CHARS!r} -- source drifted, refusing"

    # COLOUR NAMES. Default: Duck's own words, so the legend changes in glyph only
    # (one variable). With COLOUR_VOCAB=qwen, the names come from what the model
    # itself calls each engine colour (findings 74: shown the real RGB as an
    # image, 6 reps each) -- six of sixteen differ from Duck's, e.g. it never
    # says "charcoal", "sky blue" is "light blue", "dark red" is "maroon". The
    # legend has been asking the model to translate 6/16 names on every read.
    _names = [seg.split("=", 1)[1].strip() for seg in OLD_LEGEND.split(",")]
    assert len(_names) == 16, _names
    if _os.environ.get("COLOUR_VOCAB", "duck").lower() == "qwen":
        import json as _json
        # 09-25: resolve env -> next to this cell (flat Kaggle bundle) -> repo. Synesthesia v5/v6 died on
        # Kaggle with FileNotFoundError on the repo path; a local test cannot catch a path that exists locally.
        _cands = [_os.environ.get("COLOUR_VOCAB_PATH"),
                  _os.path.join(_os.path.dirname(_os.environ["CC_GLYPH_CELL"]), "qwen_colour_vocabulary_all16.json") if _os.environ.get("CC_GLYPH_CELL") else None,
                  "/home/ignaz/github/arc-prize-2026/notes/qwen_colour_vocabulary_all16.json"]   # kaggle-ok: last fallback
        _vp = next(c for c in _cands if c and _os.path.exists(c))
        print(f"lownorm: colour vocabulary from {_vp}", flush=True)
        _v = _json.load(open(_vp))["colours"]
        _q = [_v[str(i)]["qwen"] for i in range(16)]
        # collisions: the model gave two indices the same word (2 and 3 both
        # "gray"). A legend cannot label two cells identically. Overrides come
        # from a comparative probe (ask_qwen_grey_pair.py), never from a tiebreak
        # of mine -- that would be the Duck error again.
        for _i, _n in (_json.load(open(_vp)).get("overrides") or {}).items():
            _q[int(_i)] = _n
        assert len(set(_q)) == 16, f"vocabulary still has a collision: {_q}"
        _names = _q
        print(f"lownorm: legend in QWEN's words: {', '.join(_names)}", flush=True)
    NEW_LEGEND = ", ".join(f"{g}={n}" for g, n in zip(LOWNORM_GLYPHS, _names))
    # COLOUR_VOCAB=none (the investigator, 2026-09-23: "you could run visual without the key"):
    # strip the colour legend ENTIRELY. The text arm then has no colour information
    # at all; the visual arm has it only through the 16 baked embedding rows. Any
    # difference between them is the channel and nothing else (findings 83 Q3).
    _NOKEY = _os.environ.get("COLOUR_VOCAB", "duck").lower() == "none"
    _LEGEND_BULLET = f"- Color legend: {OLD_LEGEND}.\n"

    # 1. the renderer -- Frame.ascii is a @property that calls format_grid_ascii,
    #    which reads this global at call time, so every frame re-renders correctly.
    _gu.ARC_COLOR_CHARS = LOWNORM_GLYPHS
    _gu.ARC_COLOR_LEGEND = "" if _NOKEY else NEW_LEGEND
    # 2. the sandbox -- imported by name; sent to the subprocess as color_chars on
    #    every python() call, so the model's own code sees the same map.
    _sb.ARC_COLOR_CHARS = LOWNORM_GLYPHS
    # 3. the prompt -- the legend was interpolated into GAME_OVERVIEW_ADDENDUM at
    #    import, and tool_agent imported THAT string by name. Rewrite every
    #    module-level string in both namespaces that carries the old legend or
    #    calls the encoding "letter-coded".
    _patched = []
    for _mod in (_pr, _ta):
        for _k, _v in list(vars(_mod).items()):
            if isinstance(_v, str) and (OLD_LEGEND in _v or "letter-coded" in _v):
                if _NOKEY:   # drop the whole bullet, then any bare copy of the legend
                    _nv = _v.replace(_LEGEND_BULLET, "").replace(OLD_LEGEND, "").replace("letter-coded", "symbol-coded")
                else:
                    _nv = _v.replace(OLD_LEGEND, NEW_LEGEND).replace("letter-coded", "symbol-coded")
                setattr(_mod, _k, _nv); _patched.append(f"{_mod.__name__}.{_k}")
    assert any(k.endswith("tool_agent.GAME_OVERVIEW_ADDENDUM") for k in _patched), \
        f"tool_agent's legend binding was not patched; got {_patched}"

    # 4. the per-turn USER prompt -- built at runtime inside a method
    #    (_build_user_prompt, tool_agent.py:1224), so no module-level sweep can
    #    reach its "Only letter-coded board views ..." literal. Wrap the method;
    #    the owning class is located by inspection so nothing is hardcoded.
    _owner = next(c for c in vars(_ta).values()
                  if isinstance(c, type) and "_build_user_prompt" in vars(c))
    _orig_bup = _owner._build_user_prompt
    def _bup(self, *a, **k):
        r = _orig_bup(self, *a, **k)
        if isinstance(r, str): return r.replace("letter-coded", "symbol-coded")
        if isinstance(r, list): return [x.replace("letter-coded", "symbol-coded") if isinstance(x, str) else x for x in r]
        return r
    _owner._build_user_prompt = _bup
    _patched.append(f"{_owner.__name__}._build_user_prompt (wrapped)")

    # ---- verify, or refuse to run --------------------------------------------
    _probe = _Frame(grid=((5, 5, 0), (5, 9, 0), (14, 14, 14)), step=0, level=0)
    _asc = _probe.ascii
    assert _asc == "겪겪".replace("겪겪", LOWNORM_GLYPHS[5] * 2 + LOWNORM_GLYPHS[0]) + "\n" \
        + LOWNORM_GLYPHS[5] + LOWNORM_GLYPHS[9] + LOWNORM_GLYPHS[0] + "\n" \
        + LOWNORM_GLYPHS[14] * 3, f"renderer did not switch: {_asc!r}"
    if _NOKEY:
        # the investigator 2026-09-23: "if there is color anywhere else in the code and it doesn't
        # match the new vocab..." -- prompts.py:27 says "Background colors are often
        # white or gray/black-ish large regions". No glyph mapping, but colour words
        # in a no-key prompt. Neutralise that sentence, then REFUSE to run if any
        # colour word from either vocabulary survives in any prompt string.
        _CW = ["light gray","medium gray","dark gray","sky blue","light green","dark red",
               "white","gray","grey","charcoal","black","magenta","pink","red","blue",
               "yellow","orange","maroon","green","purple"]   # names only: "color" as a concept is not the key
        _BG_OLD = "Background colors are often white or gray/black-ish large regions, but not always."
        _BG_NEW = "Backgrounds are often large uniform regions, but not always."
        for _mod in (_pr, _ta):
            for _k, _v in list(vars(_mod).items()):
                if isinstance(_v, str) and _BG_OLD in _v:
                    setattr(_mod, _k, _v.replace(_BG_OLD, _BG_NEW)); _patched.append(f"{_mod.__name__}.{_k} (bg sentence)")
        _leaks = []
        for _mod in (_pr, _ta):
            for _k, _v in vars(_mod).items():
                if isinstance(_v, str) and _k.isupper():
                    for _w in _CW:
                        if _re.search(r"\b" + _re.escape(_w) + r"\b", _v, _re.I): _leaks.append(f"{_mod.__name__}.{_k}: '{_w}'")
        assert not _leaks, "COLOUR WORDS SURVIVE IN A NO-KEY PROMPT: " + "; ".join(sorted(set(_leaks))[:12])
        assert OLD_LEGEND not in _ta.GAME_OVERVIEW_ADDENDUM and "Color legend" not in _ta.GAME_OVERVIEW_ADDENDUM, "legend not stripped"
        print("lownorm: NO COLOUR KEY -- legend bullet removed from every prompt string", flush=True)
    else:
        assert OLD_LEGEND not in _ta.GAME_OVERVIEW_ADDENDUM and NEW_LEGEND in _ta.GAME_OVERVIEW_ADDENDUM
    assert _sb.ARC_COLOR_CHARS == LOWNORM_GLYPHS
    for _ch in OLD_CHARS:
        assert _ch not in _asc, "old letter leaked into a render"

    # ---- tokenizer check against the SERVED model -----------------------------
    # WAS WRONG, two ways, and both fired on every local run:
    #  1. it looked for tokenizer.json under /kaggle/input ONLY. Off Kaggle that
    #     path does not exist, so the check silently "skipped" -- runs/alpha_games/
    #     a2.0/run.log line 2, on the real sweep: "lownorm: no tokenizer.json under
    #     /kaggle/input -- tokenizer check skipped". The glyph map is this arm's one
    #     variable and nothing verified it locally, ever.
    #  2. `except Exception: print(...) -- continuing` also swallowed
    #     ImportError("tokenizers"), so a missing library disarmed the gate with a
    #     one-line note, while the cell header promises it "refuses to continue
    #     unless every one of them verifies".
    # RIGHT NOW: ordered candidate roots, first hit wins, and FAIL CLOSED.
    #   CC_CHECKPOINT -> the root :5300 itself reports -> /kaggle/input -> ~/models
    # The server's own /v1/models "root" is the authoritative answer to "which
    # tokenizer is actually serving", which is the question being asked.
    LOWNORM_TOKENIZER_VERIFIED = False
    from pathlib import Path as _P

    def _served_root():
        """the checkpoint dir :5300 says it is serving, or None"""
        try:
            import json as _j, urllib.request as _u, os as _o
            _base = _o.environ.get("LOCAL_ANALYZER_BASE_URL", "").rstrip("/")
            if not _base:
                return None
            with _u.urlopen(_base + "/models", timeout=5) as _r:
                for _m in (_j.loads(_r.read()).get("data") or []):
                    if _m.get("root"):
                        return _m["root"]
        except Exception:
            return None
        return None

    import os as _os_ln
    _roots = [_os_ln.environ.get("CC_CHECKPOINT"),
              _served_root(), "/kaggle/input", "/home/ignaz/models"]   # kaggle-ok: Kaggle path first
    _tj = None
    for _r in _roots:
        if not _r:
            continue
        _rp = _P(_r)
        # a checkpoint dir carries tokenizer.json directly; only rglob a mount point
        if (_rp / "tokenizer.json").is_file():
            _tj = _rp / "tokenizer.json"; break
        if _rp.exists():
            _tj = next(_rp.rglob("tokenizer.json"), None)
            if _tj:
                break
    if _tj is None:
        raise RuntimeError(
            "lownorm: no tokenizer.json found under any of "
            f"{[str(r) for r in _roots if r]} -- REFUSING to run. The glyph map is "
            "this arm's one variable; an unverified map can merge or split under "
            "the served tokenizer and the arm would then measure nothing. Set "
            "CC_CHECKPOINT to the served checkpoint directory.")
    try:
        from tokenizers import Tokenizer as _Tok
    except Exception as _e:
        # NOT silently swallowed any more: the gate is disarmed and says so, and
        # the flag lets a later analysis tell a verified run from an unverified one.
        print(f"lownorm: *** WARNING *** tokenizer check DISARMED -- cannot import "
              f"`tokenizers` ({type(_e).__name__}: {_e}). This run is UNVERIFIED: "
              f"lownorm_tokenizer_verified=False", flush=True)
    else:
        _t = _Tok.from_file(str(_tj)); _bad = []
        for _g in LOWNORM_GLYPHS:
            if len(_t.encode(_g, add_special_tokens=False).ids) != 1 or \
               len(_t.encode(_g * 8, add_special_tokens=False).ids) != 8:
                _bad.append(_g)
        # 1:1 tokenization was the VISUAL channel's requirement (prompt_embeds spliced one row
        # per cell). The text path is character-based end to end -- Duck's own letters merge
        # 155/256 adjacent pairs and score 6.30. LOWNORM_REQUIRE_1TOKEN=0 turns the refusal
        # into a report, for glyph sets like hybrid v2 (findings 91b) whose colour emojis are
        # 2-3 tokens each. Default stays strict.
        if _os.environ.get("LOWNORM_REQUIRE_1TOKEN", "1") == "1":
            assert not _bad, f"glyphs not 1:1 on the served tokenizer {_tj}: {_bad}"
        else:
            print(f"lownorm: 1:1 tokenization NOT required (LOWNORM_REQUIRE_1TOKEN=0); multi-token glyphs: {len(_bad) if isinstance(_bad, (list, set, tuple)) else _bad}", flush=True)
        LOWNORM_TOKENIZER_VERIFIED = True
        print(f"lownorm: tokenizer check PASSED on {_tj} -- 16/16 single-token, non-merging "
              f"(lownorm_tokenizer_verified=True)", flush=True)

    print("ARM=lownorm_glyphs", flush=True)
    print(f"lownorm: map     {OLD_CHARS} -> {LOWNORM_GLYPHS}", flush=True)
    print(f"lownorm: legend  {NEW_LEGEND}", flush=True)
    print(f"lownorm: patched {_patched}", flush=True)
    print("lownorm: probe frame:\n" + _asc, flush=True)
else:
    print("ARM=duck_baseline (LOWNORM_GLYPHS_ENABLED=False -- exact 6.295 configuration)", flush=True)
