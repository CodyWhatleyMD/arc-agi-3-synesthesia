# ---- IMAGE-AWARE TRIM ESTIMATE (images arm, 10-03 night). Embedded in cell 14 only when the notebook is built with IMAGES=1 and
# IMAGES_TRIM=real (the default with IMAGES=1); IMAGES_TRIM=duck leaves Duck's estimator alone.
#
# WHY. Duck's trim estimate is (len(json.dumps(payload)) + 2) // 3 (tool_agent.py:462), x1.15 by cell_ctx_overflow, so with
# MULTIMODAL_CONTEXT=current_grid every board PNG in the window is counted by its base64 length: median 579 estimate units for an
# image that costs 66 real tokens at upscale 4 (64 + vision start/end). The trim then drops text history to make room for base64
# the model never sees -- 5-17% fewer assistant turns in the window on four recorded corpora (scripts/images_arm/retrim_whatif.py).
#
# WHAT. ToolAgent._estimate_request_input_tokens is wrapped: the image_url parts are removed from a COPY of the messages, the
# estimator installed underneath (cell_ctx_overflow's x1.15) runs on the rest exactly as before, and each image part adds its REAL
# token count. That count is vLLM's own rule for this model family (vllm/model_executor/models/qwen3_vl.py, the image branch of
# _get_vision_info): smart_resize(height, width, factor = patch x merge, min_pixels = size.shortest_edge, max_pixels =
# size.longest_edge) -> (h / patch) x (w / patch) / merge^2 tokens, + 2 for <|vision_start|><|vision_end|> -- computed from the
# image's own size (the PNG header), not a constant: 256x256 px -> 66, 512x512 -> 258. Processor values: the checkpoint's
# config.json vision_config (patch, merge) and preprocessor_config.json size (min / max pixels) from DUCK_IMAGE_TRIM_PROC_DIR;
# unreadable -> the Flash-Next values (16, 2, 65,536, 16,777,216) and the install line says so.
# A message without image parts is passed through untouched: in the images-off arm the wrapper returns the installed estimator's
# value on the original list. Any exception returns the installed estimator's value on the original messages (Duck's behaviour).
# Also observes every real request (build_chat_payload, the seam cell_think_budget uses; the payload is returned unchanged) and logs
# one line per request to DUCK_IMAGE_TRIM_LOG: images in the request and their real tokens -- the arm's image load, measured.
# Every module-level name is _it_-prefixed (cell 14 may exec it in the shared namespace).
import base64 as _it_b64, json as _it_json, math as _it_math, os as _it_os, struct as _it_struct, threading as _it_threading, time as _it_time
import inference.agent.tool_agent as _it_ta
import inference.utils.openai_compat as _it_oc

_it_mode = _it_os.environ.get("DUCK_IMAGE_TRIM", "").strip().lower()
if _it_mode != "real":
    print(f"IMAGE TRIM SHIM: off (DUCK_IMAGE_TRIM={_it_mode!r})", flush=True)
elif getattr(_it_ta.ToolAgent, "_image_trim_installed", False):
    print("IMAGE TRIM SHIM: already installed", flush=True)
else:
    _it_cfg = {"patch": 16, "merge": 2, "min_px": 65536, "max_px": 16777216, "source": "Flash-Next defaults (no DUCK_IMAGE_TRIM_PROC_DIR)"}
    _it_pd = _it_os.environ.get("DUCK_IMAGE_TRIM_PROC_DIR", "").strip()
    if _it_pd:
        try:
            _it_pc = _it_json.load(open(_it_os.path.join(_it_pd, "preprocessor_config.json"), encoding="utf-8"))
            _it_vc = {}
            try:
                _it_vc = (_it_json.load(open(_it_os.path.join(_it_pd, "config.json"), encoding="utf-8")).get("vision_config") or {})
            except Exception:
                pass
            _it_sz = _it_pc.get("size") or {}
            _it_cfg.update(patch=int(_it_vc.get("patch_size") or _it_pc.get("patch_size") or 16),
                           merge=int(_it_vc.get("spatial_merge_size") or _it_pc.get("merge_size") or 2),
                           min_px=int(_it_sz.get("shortest_edge") or _it_pc.get("min_pixels") or 65536),
                           max_px=int(_it_sz.get("longest_edge") or _it_pc.get("max_pixels") or 16777216),
                           source=_it_os.path.join(_it_pd, "preprocessor_config.json"))
        except Exception as _it_exc:
            _it_cfg["source"] = f"Flash-Next defaults ({_it_pd}: preprocessor_config.json unreadable, {type(_it_exc).__name__})"

    def _it_resize(height, width):
        """transformers' qwen2_vl smart_resize, the function vLLM calls for this model (factor = patch x merge)."""
        f = _it_cfg["patch"] * _it_cfg["merge"]
        h_bar, w_bar = round(height / f) * f, round(width / f) * f
        if h_bar * w_bar > _it_cfg["max_px"]:
            beta = _it_math.sqrt((height * width) / _it_cfg["max_px"])
            h_bar, w_bar = max(f, _it_math.floor(height / beta / f) * f), max(f, _it_math.floor(width / beta / f) * f)
        elif h_bar * w_bar < _it_cfg["min_px"]:
            beta = _it_math.sqrt(_it_cfg["min_px"] / (height * width))
            h_bar, w_bar = _it_math.ceil(height * beta / f) * f, _it_math.ceil(width * beta / f) * f
        return h_bar, w_bar

    def _it_tokens_for(width, height):
        h_bar, w_bar = _it_resize(height, width)
        return (h_bar // _it_cfg["patch"]) * (w_bar // _it_cfg["patch"]) // (_it_cfg["merge"] ** 2) + 2

    try:
        _it_up = max(1, int(_it_os.environ.get("MULTIMODAL_UPSCALE", "") or 16))   # vision_context.py's default when unset
    except ValueError:
        _it_up = 16
    _it_fallback = _it_tokens_for(64 * _it_up, 64 * _it_up)   # a 64x64 board at the configured upscale (an image we cannot size)
    _it_cache, _it_lock = {}, _it_threading.Lock()
    _it_stats = {"sized": 0, "fallback": 0, "errors": 0, "requests": 0}
    _it_log = _it_os.environ.get("DUCK_IMAGE_TRIM_LOG", "").strip()

    def _it_size(url):
        """(width, height) of a data-URL image: the PNG header (IHDR) directly, else PIL; None when it cannot be read."""
        if url.startswith("data:image/png;base64,"):
            head = _it_b64.b64decode(url[22:22 + 44])   # 33 bytes: signature 8, IHDR length 4, b"IHDR" 4, width 4, height 4
            if head[:8] == b"\x89PNG\r\n\x1a\n" and head[12:16] == b"IHDR":
                return _it_struct.unpack(">II", head[16:24])
        if url.startswith("data:image/") and ";base64," in url:
            import io as _it_io
            from PIL import Image as _it_Image
            return _it_Image.open(_it_io.BytesIO(_it_b64.b64decode(url.split(",", 1)[1]))).size
        return None

    def _it_tokens(part):
        iu = part.get("image_url")
        url = iu.get("url", "") if isinstance(iu, dict) else (iu if isinstance(iu, str) else "")
        hit = _it_cache.get(url)
        if hit is not None:
            return hit
        try:
            wh = _it_size(url)
        except Exception:
            wh = None
        if wh and wh[0] > 0 and wh[1] > 0:
            n = _it_tokens_for(int(wh[0]), int(wh[1])); _it_stats["sized"] += 1
        else:
            n = _it_fallback; _it_stats["fallback"] += 1
            if _it_stats["fallback"] <= 3:
                print(f"IMAGE TRIM SHIM: could not size an image part ({url[:40]!r}...) -- counted as a 64x64 board at upscale {_it_up} = {n} tokens", flush=True)
        with _it_lock:
            if len(_it_cache) > 8192:
                _it_cache.clear()
            _it_cache[url] = n
        return n

    def _it_split(messages):
        """(messages without image parts or the original list, image parts' real tokens, image count)."""
        out, extra, n_img, changed = [], 0, 0, False
        for m in messages:
            c = m.get("content") if isinstance(m, dict) else None
            if isinstance(c, list) and any(isinstance(p, dict) and p.get("type") == "image_url" for p in c):
                keep = []
                for p in c:
                    if isinstance(p, dict) and p.get("type") == "image_url":
                        extra += _it_tokens(p); n_img += 1
                    else:
                        keep.append(p)
                out.append({**m, "content": keep}); changed = True
            else:
                out.append(m)
        return (out if changed else messages), extra, n_img

    _it_inner_est = _it_ta.ToolAgent._estimate_request_input_tokens

    def _it_est(self, messages, *, tools=None):
        try:
            text_only, extra, n_img = _it_split(messages)
        except Exception as exc:
            _it_stats["errors"] += 1
            if _it_stats["errors"] <= 3:
                print(f"IMAGE TRIM SHIM: estimate fell back to the installed estimator ({type(exc).__name__}: {exc})", flush=True)
            return _it_inner_est(self, messages, tools=tools)
        if not n_img:
            return _it_inner_est(self, messages, tools=tools)
        return _it_inner_est(self, text_only, tools=tools) + extra

    _it_ta.ToolAgent._estimate_request_input_tokens = _it_est

    _it_inner_build = _it_oc.build_chat_payload

    def _it_build(*a, **kw):
        p = _it_inner_build(*a, **kw)
        if _it_log:
            try:
                msgs = kw.get("messages") if "messages" in kw else (p.get("messages") if isinstance(p, dict) else None)
                _, extra, n_img = _it_split(msgs or [])
                _it_stats["requests"] += 1
                with _it_lock, open(_it_log, "a", encoding="utf-8") as fh:
                    fh.write(_it_json.dumps({"t": round(_it_time.time(), 3), "n_images": n_img, "image_tokens": extra,
                                             "n_messages": len(msgs or [])}) + "\n")
            except Exception:
                pass   # observation only: the request is never touched
        return p

    if getattr(_it_inner_build, "__think_budget_patched__", False):
        _it_build.__think_budget_patched__ = True   # keep cell_think_budget's own install guard truthful
    _it_oc.build_chat_payload = _it_build
    if hasattr(_it_ta, "build_chat_payload"):   # tool_agent imported the name at module load (tool_agent.py:34); rebind there too
        _it_ta.build_chat_payload = _it_build
    _it_ta.ToolAgent._image_trim_installed = True
    _it_ta._image_trim_cfg = _it_cfg
    _it_ta._image_trim_stats = _it_stats
    _it_ta._image_trim_tokens_for = _it_tokens_for
    print(f"IMAGE TRIM SHIM INSTALLED: the trim estimate counts each image part at its real token cost (a 64x64 board at upscale "
          f"{_it_up} = {64 * _it_up}x{64 * _it_up} px -> {_it_fallback} tokens incl. vision start/end) instead of its base64 length; text "
          f"estimate unchanged | processor: patch {_it_cfg['patch']} merge {_it_cfg['merge']} min {_it_cfg['min_px']} max {_it_cfg['max_px']} "
          f"px ({_it_cfg['source']}) | per-request log: {_it_log or 'off'}", flush=True)
