# ---- SERVER-500 / RETRY-STORM CIRCUIT BREAKER, arm-independent -------------------------------------
# WHAT THIS GUARDS (premise re-checked 2026-09-21 against the stack we actually run):
#   (a) IMAGE-KEYED 500s -- precautionary now, not load-bearing. vLLM's multimodal encoder cache used
#       to evict an image entry other requests still referenced (vllm#38551), and the engine then
#       answered 500 "internal error during generation" for EVERY retry carrying that image; Kaggle's
#       vc33 lost 75 min to it and the v12 lownorm run died at action 18. That was on 0.27.1. We now
#       run vLLM 0.29.0 (`curl :5300/version` -> {"version":"0.29.0"}; exec_harness.py pins
#       vllm==0.29.0), whose v1/core/encoder_cache_manager.py only ever evicts from `freeable`, i.e.
#       entries whose referencing-request set is empty (see its num_freeable_slots/freeable
#       bookkeeping) -- so the fix IS in. The image-strip path below is kept as cheap insurance
#       against any other image-keyed 500, but do NOT cite it as the reason a 0.29.0 run survived.
#   (b) THE UNCAPPED RETRY LOOP -- load-bearing, and the reason this cell still exists. This one was
#       never fixed upstream. solver.py has no retry ceiling at all: `grep -n "max_retr|retry_count|
#       attempts|give_up|consecutive" solver.py` returns nothing. Its only exits are
#       result is None -> RuntimeError (line ~309) and should_stop() -> the per-game wall clock.
#       Anything raising requests.RequestException out of _chat_completion lands in tool_agent.py's
#       `except requests.RequestException` handler, which returns retryable_failure=True, and solver.py
#       then sleeps ANALYZER_RETRY_BACKOFF_SECONDS = 1.0 and retries forever -- a ~1 Hz spin that burns
#       the whole per-game clock against a server that is simply down. So this wrapper now:
#         * counts EVERY escaping RequestException (connection refused, timeout, 4xx, 5xx -- error-class
#           agnostic, because a dead server does not politely return 500), resetting on success;
#         * sleeps a bounded exponential backoff before re-raising, so the solver's fixed 1.0s cadence
#           cannot spin;
#         * at _MAX_CONSEC_FAIL consecutive failures raises a plain RuntimeError instead. That is the
#           clean escape and it is already proven in-tree: RuntimeError is NOT a RequestException, so it
#           falls to tool_agent.py's generic `except Exception` handler, which returns None, and
#           solver.py turns None into `raise RuntimeError("Analyzer did not return a result.")`, which
#           the solver's outer handler records as solver_note="error: ..." / state="crashed" and then
#           finishes the game. One game ends honestly instead of all of them ending on the clock.
# The visual channel (cell_15c) carries its own copy of the 500 logic inside its wrap; this cell
# installs for the arms that have no wrap (baseline, lownorm) and is a no-op when cell_15c already did.
import functools as _ft, json as _json, os as _os, time as _time, requests as _rq
import inference.agent.tool_agent as _ta

_LOG = _os.environ.get("BREAKER_LOG", "/kaggle/working/breaker.jsonl")
# Plain module constants on purpose -- NOT env-gated. A previous shim in this repo defaulted its
# threshold to the off value and so shipped switched off through every run; a breaker that can be
# silently disabled by an unset variable is not a breaker.
_MAX_CONSEC_FAIL = 8     # consecutive escaping RequestExceptions before we give the game up cleanly
_MAX_BACKOFF_S = 30.0    # ceiling on the pre-re-raise sleep
_IMAGES_OFF_RECOVER = 5  # consecutive image-less successes before we try images again

def _emit(**kw):
    kw["t"] = _time.time()
    with open(_LOG, "a") as f: f.write(_json.dumps(kw) + "\n")

_orig = _ta.ToolAgent._chat_completion
if getattr(_orig, "__wrapped__", None) is not None:
    print("BREAKER: _chat_completion is already wrapped (cell_15c carries its own breaker) -- not installing a second one", flush=True)
elif getattr(_ta.ToolAgent, "_breaker_installed", False):
    print("BREAKER: already installed", flush=True)
else:
    @_ft.wraps(_orig)
    def _w(self, messages, **kw):
        attempts = 0; patched = messages
        if getattr(self, "_images_off", False):   # image-less mode; now RECOVERABLE, see the success branch
            patched = [({**m, "content": [pt for pt in m["content"] if pt.get("type") != "image_url"]} if isinstance(m.get("content"), list) else m) for m in messages]
        while True:
            try:
                _r = _orig(self, patched, **kw)
            except _rq.RequestException as e:
                msg = str(e)
                if ("500" in msg or "Internal server error" in msg) and attempts < 3:
                    attempts += 1; stripped = []
                    # Strip images from EVERY message, history included: the evicted hash is the PREVIOUS frame's
                    # picture, not the current turn's (findings 31). Text + segmentation graph still describe the board.
                    stripped = []; patched = list(patched)
                    for k in range(len(patched)):
                        c = patched[k].get("content")
                        if isinstance(c, list) and any(pt.get("type") == "image_url" for pt in c):
                            stripped += [pt for pt in c if pt.get("type") == "image_url"]
                            patched[k] = {**patched[k], "content": [pt for pt in c if pt.get("type") != "image_url"]}
                    _emit(event="server_500_retry", attempt=attempts, images_stripped=len(stripped), error=msg[:200])
                    print(f"BREAKER: server 500 (mm-cache bug); retry {attempts}/3 with {len(stripped)} image(s) stripped", flush=True)
                    if stripped or attempts == 1: continue
                # --- from here the failure ESCAPES this wrapper, i.e. the solver will see it ---
                if "500" in msg or "Internal server error" in msg:
                    self._consec_500 = getattr(self, "_consec_500", 0) + 1
                    if self._consec_500 >= 3 and not getattr(self, "_images_off", False):
                        self._images_off = True; self._images_off_ok = 0
                        print("BREAKER: three consecutive failed turns on server 500s -- this agent runs image-less from here on", flush=True)
                # Error-class-agnostic counter: the retry storm we are capping is driven by
                # `except requests.RequestException` in tool_agent.py, which does not care WHICH one.
                self._consec_fail = getattr(self, "_consec_fail", 0) + 1
                if self._consec_fail >= _MAX_CONSEC_FAIL:
                    _emit(event="breaker_open", consec_fail=self._consec_fail, error=msg[:200])
                    print(f"BREAKER OPEN: {self._consec_fail} consecutive request failures -- raising RuntimeError so the solver stops retrying and ends this game", flush=True)
                    raise RuntimeError(
                        f"circuit breaker: {self._consec_fail} consecutive analyzer request failures "
                        f"(last: {msg[:200]}) -- giving up on this game instead of retrying at 1 Hz "
                        f"until the wall clock expires") from e
                _bo = min(2.0 ** self._consec_fail, _MAX_BACKOFF_S)
                _emit(event="backoff", consec_fail=self._consec_fail, sleep_s=_bo, error=msg[:200])
                print(f"BREAKER: request failure {self._consec_fail}/{_MAX_CONSEC_FAIL}; sleeping {_bo:.1f}s before re-raising (solver retries at 1.0s, which would spin)", flush=True)
                _time.sleep(_bo)
                raise
            else:
                self._consec_500 = 0
                self._consec_fail = 0
                if getattr(self, "_images_off", False):
                    # RECOVERY PATH. This used to be a one-way latch: one bad patch of 500s and the
                    # agent ran text-only for the rest of a multi-hour game even after the server
                    # recovered, which silently turned a visual/image arm into a lownorm arm. Count
                    # image-less successes and put the images back.
                    self._images_off_ok = getattr(self, "_images_off_ok", 0) + 1
                    if self._images_off_ok >= _IMAGES_OFF_RECOVER:
                        self._images_off = False; self._images_off_ok = 0
                        _emit(event="images_back_on", after=_IMAGES_OFF_RECOVER)
                        print(f"BREAKER: {_IMAGES_OFF_RECOVER} consecutive image-less successes -- re-enabling images", flush=True)
                return _r
    _ta.ToolAgent._chat_completion = _w
    _ta.ToolAgent._breaker_installed = True
    assert getattr(_ta.ToolAgent._chat_completion, "__wrapped__", None) is _orig
    print(f"BREAKER INSTALLED on ToolAgent._chat_completion (log: {_LOG}; open at {_MAX_CONSEC_FAIL} consecutive failures, backoff <= {_MAX_BACKOFF_S:.0f}s)", flush=True)
