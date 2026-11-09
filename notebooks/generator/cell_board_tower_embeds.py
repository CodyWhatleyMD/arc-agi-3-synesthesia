# ---- BOARD-TOWER EMBEDS ARM for the vendored Duck harness (plan S2c, game level) ------------------
# The question this cell exists to answer: can the model PLAY with DISTILLED vision -- the 64x64 board
# mapped to image tokens by the 27M-param student (scripts/board_tower) -- instead of a rendered PNG
# through the real vision tower? Every prior measurement of the student was on STATIC boards.
#
# TWO INDEPENDENT SWITCHES (either one alone installs this cell; ab_local.py execs it when either is set):
#
#   BT_TOWER=1            Replace Duck's board PNG with the student's image_embeds part. Needs a server
#                         booted with --enable-mm-embeds and MULTIMODAL_CONTEXT=current_grid; REFUSES to
#                         install otherwise, because a tower arm that silently played the control is the
#                         exact failure this experiment is about.
#   BT_IMAGE_KEEP=<n>     History image window: keep the board image on the n most recent image-bearing
#                         messages, replace the rest with a text marker. Handles BOTH image_url (png arms)
#                         and image_embeds (tower arm), so it can be set identically in every image arm.
#                         Unset = stock Duck (images accumulate for as long as their message is retained).
#
# WHY THE WINDOW IS NEEDED AT ALL. Stock Duck attaches exactly ONE image per request (the current grid --
# `current_grid_image_part`, vision_context.py:74; there is no previous-frame/diff image in this harness,
# that is the franzen fork's ARC3_DIFF_IMAGE) and never strips it from history. A board PNG at
# MULTIMODAL_UPSCALE=4 costs 66 real tokens, so accumulating is cheap. The student emits ONE TOKEN PER
# CELL: 4096 + 2 = 4098 prompt tokens per board, 12.5% of a 32k window. Accumulating that overflows the
# window inside ~6 turns and the "recovery" is Duck deleting its own history. So the tower arm cannot run
# at all without a window, and the png arms are given the SAME window so the comparison stays one-variable.
#
# HOW THE 28 MB PAYLOAD IS KEPT OUT OF EVERYTHING BUT THE WIRE. A (4096, 2560) bf16 matrix is 21 MB raw,
# 28.0 MB base64. Duck deep-copies the outgoing messages (`json.loads(json.dumps(messages))`,
# tool_agent.py:1791), writes them to a prompt-log snapshot and to requests.jsonl twice per request, and
# estimates the trim budget as `len(json.dumps(payload)) // 3` -- i.e. a 28 MB blob would be copied four
# times per request and ESTIMATED AT 10.7 MILLION TOKENS, which empties the agent's history on turn one.
# So the part Duck carries holds only a REFERENCE:
#     {"type": "image_embeds", "uuid": "tower-g4096-<ckpt>-<board sha1>",
#      "image_embeds": {"__board_tower_ref__": "<uuid>", "n_pos": 4096, "hidden": 2560}}
# and `build_chat_payload` is wrapped to HYDRATE the reference into the real base64 tensors in a COPY of
# the messages, immediately before the POST. The reference resolves through a small board cache (uuid ->
# 64x64 uint8 cells, 4 KB each); a miss regenerates from the cells, so eviction can never send stale
# vectors. Consequences: history, logs and the trim estimate stay tiny; the real vectors exist only in
# the request body; and requests.jsonl keeps the per-turn uuid, which is the proof the arm was live.
#
# THE UUID. The server's multimodal cache is keyed on it (mm_hash is the uuid when one is given --
# notes/serving_sprint_1003/mm_embeds.md section 1 step 5), so a uuid that does not change with the board
# silently serves the PREVIOUS board's vectors. export_embeds.Student.uuid is
# "tower-g<n_pos>-<ckpt sha256[:10]>-<sha1 of the 4096 cell ids>": it changes with the board, the
# checkpoint and the geometry. This cell additionally ASSERTS the uuid tracks the board (it recomputes the
# sha1 at hydration time and compares) and logs every uuid, so "uuids varied per turn" is measured, not assumed.
#
# TOKEN ACCOUNTING. The estimator is wrapped the way cell_image_trim.py wraps it for PNGs: image_embeds
# parts are removed from a COPY of the messages, whatever estimator is already installed (cell_ctx_overflow's
# x1.15) runs on the rest unchanged, and each embeds part adds its REAL cost, n_pos + 2.
#
# PRE-FLIGHT. One tiny VALID image_embeds request (64 tokens, grid [1,16,16]) is sent to the configured
# server at install time. A 400 ("You must set --enable-mm-embeds to input image_embeds") or any other
# failure RAISES, so the run dies at setup instead of playing the png/text control under a tower label.
# A wrong SHAPE in this path kills the engine (EngineDeadError), so every part also passes the client-side
# shape assert in scripts/board_tower/export_embeds.assert_request_shapes_n.
#
# Every module-level name is _bt_-prefixed (ab_local.py may exec this in a shared namespace).
import base64 as _bt_b64, collections as _bt_col, functools as _bt_ft, hashlib as _bt_hash
import json as _bt_json, os as _bt_os, sys as _bt_sys, threading as _bt_thr, time as _bt_time
import urllib.error as _bt_uerr, urllib.request as _bt_ureq

import inference.agent.tool_agent as _bt_ta
import inference.agent.vision_context as _bt_vc
import inference.utils.openai_compat as _bt_oc

_bt_tower = _bt_os.environ.get("BT_TOWER", "").strip() == "1"
_bt_keep_raw = _bt_os.environ.get("BT_IMAGE_KEEP", "").strip()
_bt_keep = int(_bt_keep_raw) if _bt_keep_raw.lstrip("-").isdigit() else None
if _bt_keep is not None and _bt_keep < 0:
    raise SystemExit(f"BT_IMAGE_KEEP must be >= 0, got {_bt_keep_raw!r}")
_bt_log_path = _bt_os.environ.get("BT_LOG") or _bt_os.path.join(_bt_os.environ.get("SMOKE_JOB_DIR", "."), "board_tower.jsonl")
_bt_lock = _bt_thr.Lock()
_bt_stats = {"parts_built": 0, "requests_hydrated": 0, "parts_hydrated": 0, "bytes_hydrated": 0,
             "fallback_png": 0, "uuids": set(), "est_calls": 0, "est_parts": 0,
             "window_stripped": 0, "window_calls": 0, "hydrate_misses": 0, "regen": 0,
             "payload_hits": 0, "regen_seconds": 0.0, "png_unsized": 0}
# A board PNG we cannot size: charge it a 64x64 board at the configured upscale rather than guessing.
_bt_png_tokens_fallback = 4098
_bt_HISTORY_MARKER = "[board image omitted from history]"
_bt_REF_KEY = "__board_tower_ref__"


def _bt_emit(**kw):
    kw["t"] = round(_bt_time.time(), 3)
    try:
        with _bt_lock, open(_bt_log_path, "a", encoding="utf-8") as f:
            f.write(_bt_json.dumps(kw, default=str) + "\n")
    except OSError:
        pass


# ======================================================================== history image window
def _bt_is_image_part(p):
    return isinstance(p, dict) and p.get("type") in ("image_url", "image_embeds")


def _bt_has_image(message):
    c = message.get("content") if isinstance(message, dict) else None
    return isinstance(c, list) and any(_bt_is_image_part(p) for p in c)


def _bt_strip_images(message):
    """Image parts -> a text marker. Keeps the message well formed (a message whose only part was an
    image would otherwise be empty) and tells the model a board image WAS there."""
    c = message.get("content")
    if not isinstance(c, list):
        return message
    out = []
    for p in c:
        if _bt_is_image_part(p):
            out.append({"type": "text", "text": _bt_HISTORY_MARKER})
            _bt_stats["window_stripped"] += 1
        else:
            out.append(p)
    return {**message, "content": out}


def _bt_apply_window(messages, keep):
    """Keep images on the `keep` most recent image-bearing MESSAGES, strip the rest. Walks backwards so
    recency wins; the originals are never mutated."""
    seen, out = 0, []
    for m in reversed(messages):
        if _bt_has_image(m):
            seen += 1
            if seen > keep:
                m = _bt_strip_images(m)
        out.append(m)
    out.reverse()
    return out


# ======================================================================== the tower part
_bt_student = None
_bt_boards = _bt_col.OrderedDict()          # uuid -> 64x64 uint8 cells (4 KB each)
_bt_payloads = _bt_col.OrderedDict()        # uuid -> the built part (28 MB each) -- see _bt_PAYLOAD_CACHE
_bt_BOARD_CACHE = 256
# How many BUILT parts to keep. A turn makes several requests (tool steps) and each one re-sends the same
# board, so a cache of 1 already removes almost all of the rebuild cost; 3 covers concurrent games sharing
# the process. Each entry is ~28 MB of base64, so this is the one real memory knob in the cell.
_bt_PAYLOAD_CACHE = max(1, int(_bt_os.environ.get("BT_PAYLOAD_CACHE", "3")))
_bt_se = _bt_bt = None


def _bt_load_student():
    """Load the student once, in-process, on the GPU if one is visible. 27M params / ~110 MB."""
    global _bt_student, _bt_se, _bt_bt
    if _bt_student is not None:
        return _bt_student
    _bt_root = _bt_os.environ.get("BT_REPO_ROOT") or _bt_os.getcwd()
    if _bt_root not in _bt_sys.path:
        _bt_sys.path.insert(0, _bt_root)
    from notebooks_duck.synth_tokens import synth_embeds as _se
    from scripts.board_tower import export_embeds as _bt
    _bt_se, _bt_bt = _se, _bt
    t0 = _bt_time.time()
    _bt_student = _bt.load_student()
    print(f"BOARD TOWER: student loaded from {_bt_student.path} (step {_bt_student.step}, ckpt tag "
          f"{_bt_student.tag}) on {_bt_student.device} in {_bt_time.time()-t0:.1f}s -- n_pos "
          f"{_bt_student.n_pos}, {_bt_student.n_pos + 2} prompt tokens per board", flush=True)
    # Which COPY of the student code ran. BT_REPO_ROOT normally points at a FROZEN snapshot of
    # scripts/board_tower + notebooks_duck/synth_tokens, because the live files are being edited by another
    # agent for the 1024-token variant: a mid-run change would silently alter the arm. Hashes recorded so the
    # run can be tied to exact source.
    _bt_mods = {}
    for _m in (_se, _bt):
        try:
            _bt_mods[_m.__name__] = _bt_hash.sha256(open(_m.__file__, "rb").read()).hexdigest()[:16]
        except Exception:
            pass
    print(f"BOARD TOWER: module root {_bt_root} | sources {_bt_mods}", flush=True)
    _bt_emit(event="student_loaded", ckpt=str(_bt_student.path), tag=_bt_student.tag,
             step=_bt_student.step, device=str(_bt_student.device), n_pos=_bt_student.n_pos,
             params=sum(p.numel() for p in _bt_student.model.parameters()),
             module_root=_bt_root, module_sha=_bt_mods,
             ckpt_bytes=_bt_os.path.getsize(_bt_student.path))
    return _bt_student


def _bt_remember(uuid, cells):
    with _bt_lock:
        _bt_boards[uuid] = cells
        _bt_boards.move_to_end(uuid)
        while len(_bt_boards) > _bt_BOARD_CACHE:
            _bt_boards.popitem(last=False)


def _bt_ref_part(frame):
    """The reference part for one frame. Returns None when the frame is unusable, so the caller can
    decide (we never silently substitute a PNG without counting it)."""
    st = _bt_load_student()
    cells = _bt_se.board_cells(frame.grid)       # validates 64x64, ints 0..15; raises otherwise
    uuid = st.uuid(cells)
    _bt_remember(uuid, cells)
    _bt_stats["parts_built"] += 1
    _bt_stats["uuids"].add(uuid)
    return {"type": "image_embeds", "uuid": uuid,
            "image_embeds": {_bt_REF_KEY: uuid, "n_pos": st.n_pos, "hidden": 2560}}


def _bt_current_grid_image_part(frame):
    """Replacement for vision_context.current_grid_image_part. Same gate (MULTIMODAL_CONTEXT=current_grid),
    same position in the user message; only the SOURCE of the board's image tokens differs."""
    if frame is None or not _bt_vc.current_grid_image_enabled():
        return None
    try:
        return _bt_ref_part(frame)
    except Exception as exc:
        # A frame the student cannot model (not 64x64, or a colour outside 0..15). Fall back to Duck's
        # real PNG and COUNT it: a fallback is contamination of the arm and has to be reportable, not silent.
        _bt_stats["fallback_png"] += 1
        if _bt_stats["fallback_png"] <= 5:
            print(f"BOARD TOWER: FALLBACK TO PNG for this frame ({type(exc).__name__}: {exc}) -- "
                  f"shape {getattr(frame, 'shape', None)}; count so far {_bt_stats['fallback_png']}", flush=True)
        _bt_emit(event="fallback_png", error=f"{type(exc).__name__}: {exc}",
                 shape=list(getattr(frame, "shape", ()) or ()), n=_bt_stats["fallback_png"])
        return _bt_orig_part(frame)


# ======================================================================== hydration at the wire
def _bt_hydrate_part(part):
    """Reference part -> the real {"image_embeds": b64, "image_grid_thw": b64} part, shape-asserted."""
    emb = part.get("image_embeds")
    if not (isinstance(emb, dict) and _bt_REF_KEY in emb):
        return part, 0
    uuid = emb[_bt_REF_KEY]
    with _bt_lock:
        cells = _bt_boards.get(uuid)
        if cells is not None:
            _bt_boards.move_to_end(uuid)
    if cells is None:
        _bt_stats["hydrate_misses"] += 1
        raise RuntimeError(f"board-tower reference {uuid} evicted from the board cache -- refusing to send "
                           f"a request whose vectors cannot be regenerated (would be a silent substitution)")
    st = _bt_load_student()
    real = st.uuid(cells)
    if real != uuid:                              # the anti-silent-substitution assert
        raise RuntimeError(f"board-tower uuid mismatch: part says {uuid}, cells hash to {real}")
    with _bt_lock:
        full = _bt_payloads.get(uuid)
        if full is not None:
            _bt_payloads.move_to_end(uuid)
            _bt_stats["payload_hits"] += 1
    if full is None:
        _bt_stats["regen"] += 1
        t0 = _bt_time.time()
        full = _bt_bt.build_image_embeds(cells, st, uuid=uuid)   # runs assert_request_shapes_n
        _bt_stats["regen_seconds"] += _bt_time.time() - t0
        with _bt_lock:
            _bt_payloads[uuid] = full
            _bt_payloads.move_to_end(uuid)
            while len(_bt_payloads) > _bt_PAYLOAD_CACHE:
                _bt_payloads.popitem(last=False)
    # The uuid in the part we send is the one the board hashes to (asserted above) AND the one the built
    # payload carries: the server's mm cache can therefore never be keyed on a different board's vectors.
    assert full["uuid"] == uuid, f"built payload uuid {full['uuid']} != reference uuid {uuid}"
    n = _bt_se.part_payload_bytes(full)
    _bt_stats["parts_hydrated"] += 1
    _bt_stats["bytes_hydrated"] += n
    return full, n


def _bt_hydrate_messages(messages):
    """A COPY of `messages` with every reference part hydrated. The caller's list keeps the references,
    so history / logs / the trim estimate never carry the 28 MB blob."""
    out, n_parts, nbytes, uuids = [], 0, 0, []
    for m in messages:
        c = m.get("content") if isinstance(m, dict) else None
        if not isinstance(c, list) or not any(
                isinstance(p, dict) and p.get("type") == "image_embeds"
                and isinstance(p.get("image_embeds"), dict) and _bt_REF_KEY in p["image_embeds"] for p in c):
            out.append(m)
            continue
        parts = []
        for p in c:
            if isinstance(p, dict) and p.get("type") == "image_embeds":
                hp, nb = _bt_hydrate_part(p)
                parts.append(hp)
                if nb:
                    n_parts += 1; nbytes += nb; uuids.append(p.get("uuid"))
            else:
                parts.append(p)
        out.append({**m, "content": parts})
    return out, n_parts, nbytes, uuids


# ======================================================================== token estimate
# Duck's estimate is `len(json.dumps(payload)) // 3` (x1.15 from cell_ctx_overflow), so it counts an
# image part by its BASE64 LENGTH. For a board PNG at 4 px/cell that is ~579 estimate units against a
# real 66 tokens; at 32 px/cell it is ~19,000 against a real 4,098; and for an image_embeds reference
# part it would be ~50 against a real 4,098. All three are wrong, in both directions, and the trim then
# drops text history on bad arithmetic -- which would be a SECOND difference between the image arms.
# So every image part, of either kind, is removed from a COPY of the messages and charged its REAL
# cost, and whatever estimator is installed underneath runs on the rest exactly as before.
#
# The PNG rule is vLLM's own for this model family (transformers' qwen2_vl smart_resize with
# factor = patch x merge, then (h/patch)*(w/patch)/merge^2, + 2 for vision_start/end). Checked against
# the live server on 2026-10-05: 4 px/cell -> 66, 32 px/cell -> 4,098, both exact.
_bt_PATCH, _bt_MERGE, _bt_MIN_PX, _bt_MAX_PX = 16, 2, 65536, 16777216
_bt_png_cache = {}


def _bt_png_tokens(url):
    """Real vision tokens for a data-URL PNG, from its IHDR header. None when it cannot be sized."""
    hit = _bt_png_cache.get(url)
    if hit is not None:
        return hit
    try:
        if not url.startswith("data:image/png;base64,"):
            return None
        head = _bt_b64.b64decode(url[22:22 + 44])      # 33 bytes: sig 8 + len 4 + b"IHDR" 4 + w 4 + h 4
        if head[:8] != b"\x89PNG\r\n\x1a\n" or head[12:16] != b"IHDR":
            return None
        import struct as _st
        w, h = _st.unpack(">II", head[16:24])
        f = _bt_PATCH * _bt_MERGE
        hb, wb = round(h / f) * f, round(w / f) * f
        if hb * wb > _bt_MAX_PX:
            import math as _mt
            beta = _mt.sqrt((h * w) / _bt_MAX_PX)
            hb, wb = max(f, int(h / beta // f) * f), max(f, int(w / beta // f) * f)
        elif hb * wb < _bt_MIN_PX:
            import math as _mt
            beta = _mt.sqrt(_bt_MIN_PX / (h * w))
            hb, wb = -(-int(h * beta) // f) * f, -(-int(w * beta) // f) * f
        n = (hb // _bt_PATCH) * (wb // _bt_PATCH) // (_bt_MERGE ** 2) + 2
    except Exception:
        return None
    if len(_bt_png_cache) > 4096:
        _bt_png_cache.clear()
    _bt_png_cache[url] = n
    return n


def _bt_part_tokens(p):
    """Real prompt-token cost of one image content part, or None if it is not an image part we know."""
    if not isinstance(p, dict):
        return None
    if p.get("type") == "image_embeds":
        return int((p.get("image_embeds") or {}).get("n_pos") or 4096) + 2
    if p.get("type") == "image_url":
        iu = p.get("image_url")
        url = iu.get("url", "") if isinstance(iu, dict) else (iu if isinstance(iu, str) else "")
        n = _bt_png_tokens(url)
        if n is None:
            _bt_stats["png_unsized"] += 1
            n = _bt_png_tokens_fallback
        return n
    return None


def _bt_split_for_estimate(messages):
    """(messages without image parts or the original list, their real token cost, their count)."""
    out, extra, n, changed = [], 0, 0, False
    for m in messages:
        c = m.get("content") if isinstance(m, dict) else None
        if isinstance(c, list) and any(_bt_is_image_part(p) for p in c):
            keep = []
            for p in c:
                t = _bt_part_tokens(p)
                if t is None:
                    keep.append(p)
                else:
                    extra += t; n += 1
            out.append({**m, "content": keep}); changed = True
        else:
            out.append(m)
    return (out if changed else messages), extra, n


# ======================================================================== pre-flight probe
def _bt_preflight():
    """One tiny VALID image_embeds request. Dies loudly if the server will not accept the path."""
    import numpy as _np, torch as _torch
    st = _bt_load_student()
    base = (_bt_os.environ.get("LOCAL_ANALYZER_BASE_URL") or "http://127.0.0.1:5300/v1").rstrip("/")
    model = _bt_os.environ.get("LOCAL_ANALYZER_MODEL_ID") or "flashnext"
    side = 8                                                   # 64 tokens, grid [1,16,16]
    tok = _torch.zeros(side * side, 2560, dtype=_torch.bfloat16)
    tok[:, 0] = 1.0
    part = _bt_bt.part_from_embeds(tok.contiguous(), side, "board-tower-preflight-v1")
    body = {"model": model, "max_tokens": 8, "temperature": 0.0,
            "messages": [{"role": "user", "content": [part, {"type": "text", "text": "Reply with OK."}]}]}
    req = _bt_ureq.Request(f"{base}/chat/completions", data=_bt_json.dumps(body).encode(),
                           headers={"Content-Type": "application/json",
                                    "Authorization": f"Bearer {_bt_os.environ.get('LOCAL_ANALYZER_API_KEY', 'local')}"})
    t0 = _bt_time.time()
    try:
        with _bt_ureq.urlopen(req, timeout=300) as r:
            got = _bt_json.loads(r.read())
    except _bt_uerr.HTTPError as e:
        why = e.read().decode("utf-8", "replace")[:600]
        _bt_emit(event="preflight_failed", status=e.code, body=why)
        raise SystemExit(f"BOARD TOWER PRE-FLIGHT FAILED ({e.code}): {why}\n"
                         f"  -> the server at {base} does not accept image_embeds. Boot it with "
                         f"--enable-mm-embeds (scripts/flashnext_serve/serve_mm_embeds.sh). REFUSING to play a "
                         f"tower arm that would silently be the control.")
    except Exception as e:
        _bt_emit(event="preflight_failed", error=f"{type(e).__name__}: {e}")
        raise SystemExit(f"BOARD TOWER PRE-FLIGHT FAILED ({type(e).__name__}: {e}) against {base}")
    pt = (got.get("usage") or {}).get("prompt_tokens")
    print(f"BOARD TOWER PRE-FLIGHT OK in {_bt_time.time()-t0:.1f}s: server {base} accepted a 64-token "
          f"image_embeds part (prompt_tokens={pt}, expect ~66 + the text)", flush=True)
    _bt_emit(event="preflight_ok", prompt_tokens=pt, seconds=round(_bt_time.time() - t0, 2))


# ======================================================================== install
if getattr(_bt_ta, "_bt_installed", False):
    print("BOARD TOWER CELL: already installed", flush=True)
elif not (_bt_tower or _bt_keep is not None):
    print("BOARD TOWER CELL: off (set BT_TOWER=1 and/or BT_IMAGE_KEEP=<n>)", flush=True)
else:
    _bt_mm = _bt_os.environ.get("MULTIMODAL_CONTEXT", "").strip().lower()
    if _bt_tower and _bt_mm != "current_grid":
        raise SystemExit(f"BT_TOWER=1 needs MULTIMODAL_CONTEXT=current_grid (Duck's image gate, "
                         f"vision_context.py:38); got {_bt_mm!r}. REFUSING: the tower part is attached at "
                         f"exactly the place Duck attaches its PNG, so with the gate off the arm sends NO "
                         f"board image at all and is a text run wearing a tower label.")

    # --- server-side proof, in EVERY arm that loads this cell: what the SERVER counted per request.
    # Installed outside the BT_TOWER branch so the png arms produce the same trace and the token cost of
    # each channel is measured rather than asserted. Observation only -- the request is never touched.
    _bt_inner_cc = _bt_ta.ToolAgent._chat_completion

    @_bt_ft.wraps(_bt_inner_cc)
    def _bt_cc(self, messages, **kw):
        n_emb = n_url = 0
        for m in messages:
            c = m.get("content") if isinstance(m, dict) else None
            if isinstance(c, list):
                for q in c:
                    if isinstance(q, dict) and q.get("type") == "image_embeds":
                        n_emb += 1
                    elif isinstance(q, dict) and q.get("type") == "image_url":
                        n_url += 1
        t0 = _bt_time.time()
        res = _bt_inner_cc(self, messages, **kw)
        u = getattr(res, "usage", None) or {}
        g = (lambda k: u.get(k) if isinstance(u, dict) else getattr(u, k, None))
        _bt_emit(event="completion", n_embeds=n_emb, n_image_url=n_url,
                 seconds=round(_bt_time.time() - t0, 2),
                 prompt_tokens=g("prompt_tokens"), completion_tokens=g("completion_tokens"),
                 n_messages=len(messages))
        return res
    # functools.wraps copies __wrapped__, and cell_breaker.py treats a non-None __wrapped__ on
    # _chat_completion as "cell_15c already installed its own breaker" and declines to install
    # (cell_breaker.py:48-49). In block 3 that silently left the IMAGE arms with no retry ceiling and
    # one png32 run wedged in a 400 loop for 103 minutes until the per-game clock killed it -- biasing
    # against the pixel arm, i.e. in the tower's favour. Dropping the attribute lets cell_breaker
    # install ON TOP of this trace: breaker outermost (it retries), trace innermost (it logs every
    # attempt), which is the order both want.
    try:
        del _bt_cc.__wrapped__
    except AttributeError:
        pass
    _bt_ta.ToolAgent._chat_completion = _bt_cc

    # --- the history image window: wrap the trim, which every request path goes through -------------
    if _bt_keep is not None:
        _bt_orig_trim = _bt_ta.ToolAgent._trim_messages_for_context

        @_bt_ft.wraps(_bt_orig_trim)
        def _bt_trim(self, messages, *, tools=None, preserve_recent=1, extra_safety_tokens=0, **kw):
            _bt_stats["window_calls"] += 1
            try:
                messages = _bt_apply_window(messages, _bt_keep)
            except Exception as exc:
                print(f"BOARD TOWER: image window skipped for one call ({type(exc).__name__}: {exc})", flush=True)
            return _bt_orig_trim(self, messages, tools=tools, preserve_recent=preserve_recent,
                                 extra_safety_tokens=extra_safety_tokens, **kw)
        _bt_ta.ToolAgent._trim_messages_for_context = _bt_trim
        print(f"BOARD TOWER: history image window INSTALLED, keep={_bt_keep} image-bearing message(s); "
              f"older board images -> {_bt_HISTORY_MARKER!r} (applies to image_url AND image_embeds)", flush=True)

    # --- estimate: real token cost for EVERY image part, and never json.dumps a 28 MB payload ------
    _bt_inner_est = _bt_ta.ToolAgent._estimate_request_input_tokens

    @_bt_ft.wraps(_bt_inner_est)
    def _bt_est(self, messages, *, tools=None):
        try:
            text_only, extra, n = _bt_split_for_estimate(messages)
        except Exception:
            return _bt_inner_est(self, messages, tools=tools)
        if not n:
            return _bt_inner_est(self, messages, tools=tools)
        _bt_stats["est_calls"] += 1; _bt_stats["est_parts"] += n
        return _bt_inner_est(self, text_only, tools=tools) + extra
    _bt_ta.ToolAgent._estimate_request_input_tokens = _bt_est
    print("BOARD TOWER: trim estimate now charges every image part its REAL token cost "
          "(PNG via its IHDR + vLLM's smart_resize rule; image_embeds as n_pos+2) instead of its "
          "base64 length", flush=True)

    if _bt_tower:
        # --- the image part ------------------------------------------------------------------------
        _bt_orig_part = _bt_vc.current_grid_image_part
        _bt_vc.current_grid_image_part = _bt_current_grid_image_part
        # tool_agent imported the NAME at module load (tool_agent.py:29), so rebinding the module
        # attribute alone would leave the real PNG path in play -- the silent-control failure mode.
        _bt_ta.current_grid_image_part = _bt_current_grid_image_part
        assert _bt_ta.current_grid_image_part is _bt_current_grid_image_part

        # --- hydration at the wire -----------------------------------------------------------------
        _bt_inner_build = _bt_oc.build_chat_payload

        @_bt_ft.wraps(_bt_inner_build)
        def _bt_build(*a, **kw):
            p = _bt_inner_build(*a, **kw)
            try:
                msgs = p.get("messages") if isinstance(p, dict) else None
                if msgs:
                    hyd, n_parts, nbytes, uuids = _bt_hydrate_messages(msgs)
                    if n_parts:
                        p["messages"] = hyd
                        _bt_stats["requests_hydrated"] += 1
                        _bt_emit(event="hydrated", n_parts=n_parts, bytes=nbytes, uuids=uuids,
                                 n_messages=len(msgs))
            except Exception as exc:
                # Sending a reference the server cannot read would be a 400 storm; dying is correct.
                _bt_emit(event="hydrate_error", error=f"{type(exc).__name__}: {exc}")
                raise
            return p
        _bt_oc.build_chat_payload = _bt_build
        if hasattr(_bt_ta, "build_chat_payload"):
            _bt_ta.build_chat_payload = _bt_build
        assert _bt_ta.build_chat_payload is _bt_build

        _bt_load_student()
        _bt_preflight()
        print(f"BOARD TOWER ARM INSTALLED: every turn's board goes to the model as image_embeds from "
              f"{_bt_student.path} (tag {_bt_student.tag}, {_bt_student.n_pos} tokens = "
              f"{_bt_student.n_pos + 2} prompt tokens/board); Duck's PNG path is NOT used. log={_bt_log_path}",
              flush=True)

    def _bt_summary():
        """Printed at exit AND written to the log: the arm's own account of itself. The three numbers that
        decide whether the arm was live are parts_built (the student ran), requests_hydrated (the real
        vectors reached the wire) and len(uuids) (they changed with the board)."""
        d = dict(_bt_stats); d["uuids"] = len(_bt_stats["uuids"])
        d["regen_seconds"] = round(_bt_stats["regen_seconds"], 1)
        print(f"BOARD TOWER SUMMARY: {_bt_json.dumps(d, sort_keys=True)}", flush=True)
        _bt_emit(event="summary", **d)
    import atexit as _bt_atexit
    _bt_atexit.register(_bt_summary)
    _bt_ta._bt_installed = True
    _bt_ta._bt_stats = _bt_stats
    _bt_ta._bt_summary = _bt_summary
