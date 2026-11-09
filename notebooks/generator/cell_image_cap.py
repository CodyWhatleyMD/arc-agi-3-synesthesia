# ---- PROVIDER IMAGE CAP (nvapi images arm, 10-06). Inert unless DUCK_MAX_IMAGES is set to a positive integer.
#
# WHY. NVIDIA's integrate.api.nvidia.com rejects any chat request carrying more than 8 image parts:
#   400 {"message":"At most 8 image(s) may be provided in one prompt. (parameter=image)"}
# With MULTIMODAL_CONTEXT=current_grid every observation in the history window is an image_url part, so the 9th
# action of every game 400s, the breaker trips, and the game is recorded `crashed` (runs/api_k3_images_unlimited:
# 34 x 400, 4/4 finished games crashed at action ~15). The number 8 is the provider's, read off its 400, not ours.
#
# WHAT. build_chat_payload (the seam cell_think_budget / cell_image_trim use) is wrapped: when a request holds more
# than DUCK_MAX_IMAGES image parts, the OLDEST ones are removed from a COPY of the messages -- the newest boards are
# the ones the next action depends on. Text parts are never touched; a message whose content becomes empty gets a
# one-line text placeholder so the provider still sees a well-formed turn. The agent's own history is not mutated:
# the trim estimator, transcript logs and the next turn all see the original messages. Everything else -- when
# the limit is not exceeded, or in an arm without images -- passes through byte-identical.
# Every module-level name is _ic_-prefixed (may be exec'd in the shared notebook namespace).
import os as _ic_os, threading as _ic_threading
import inference.utils.openai_compat as _ic_oc
import inference.agent.tool_agent as _ic_ta

_ic_cap = int((_ic_os.environ.get("DUCK_MAX_IMAGES", "") or "0").strip() or 0)
if _ic_cap <= 0:
    print("IMAGE CAP: DUCK_MAX_IMAGES unset -- requests pass through unchanged", flush=True)
elif getattr(_ic_oc.build_chat_payload, "__image_cap_installed__", False):
    print("IMAGE CAP: already installed -- not wrapping twice", flush=True)
else:
    _ic_stats = {"requests": 0, "capped": 0, "dropped": 0}
    _ic_lock = _ic_threading.Lock()
    _ic_PLACEHOLDER = "[board image omitted: provider allows at most %d images per request]" % _ic_cap

    def _ic_is_img(p):
        return isinstance(p, dict) and p.get("type") == "image_url"

    def _ic_cap_messages(messages):
        """(messages with the oldest image parts beyond the cap removed, n_dropped); the input list is never mutated."""
        n_img = sum(1 for m in messages if isinstance(m, dict) and isinstance(m.get("content"), list)
                    for p in m["content"] if _ic_is_img(p))
        if n_img <= _ic_cap:
            return messages, 0
        to_drop = n_img - _ic_cap
        out = []
        for m in messages:
            c = m.get("content") if isinstance(m, dict) else None
            if to_drop > 0 and isinstance(c, list) and any(_ic_is_img(p) for p in c):
                keep = []
                for p in c:
                    if _ic_is_img(p) and to_drop > 0:
                        to_drop -= 1          # oldest first: messages are in order, parts within a message are in order
                    else:
                        keep.append(p)
                if not keep:
                    keep = [{"type": "text", "text": _ic_PLACEHOLDER}]
                out.append({**m, "content": keep})
            else:
                out.append(m)
        return out, n_img - _ic_cap

    _ic_inner_build = _ic_oc.build_chat_payload

    def _ic_build(*a, **kw):
        msgs = kw.get("messages")
        if isinstance(msgs, list):
            try:
                capped, dropped = _ic_cap_messages(msgs)
            except Exception as exc:
                dropped, capped = 0, msgs
                print(f"IMAGE CAP: pass-through after {type(exc).__name__}: {exc}", flush=True)
            if dropped:
                kw = {**kw, "messages": capped}
            with _ic_lock:
                _ic_stats["requests"] += 1
                if dropped:
                    _ic_stats["capped"] += 1; _ic_stats["dropped"] += dropped
                    n = _ic_stats["capped"]
            if dropped and (n <= 3 or n % 100 == 0):
                print(f"IMAGE CAP: request #{_ic_stats['requests']} carried {_ic_cap + dropped} images; dropped the oldest "
                      f"{dropped} (capped requests so far: {n})", flush=True)
        return _ic_inner_build(*a, **kw)

    _ic_build.__image_cap_installed__ = True
    if getattr(_ic_inner_build, "__think_budget_patched__", False):
        _ic_build.__think_budget_patched__ = True   # keep cell_think_budget's install guard truthful
    _ic_oc.build_chat_payload = _ic_build
    if hasattr(_ic_ta, "build_chat_payload"):       # tool_agent imported the name at module load (tool_agent.py:34)
        _ic_ta.build_chat_payload = _ic_build
    _ic_ta._image_cap_stats = _ic_stats
    _ic_ta._image_cap_messages = _ic_cap_messages
    print(f"IMAGE CAP INSTALLED: at most {_ic_cap} image parts per request (oldest dropped from a copy; history untouched)",
          flush=True)
