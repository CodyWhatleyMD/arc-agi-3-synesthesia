"""Make Duck's client speak to a Mistral-tokenizer vLLM server.

Duck's build_chat_payload (inference/utils/openai_compat.py) unconditionally sets
    payload["chat_template_kwargs"] = {"enable_thinking": bool(thinking)}
on the vllm path. A server started with --tokenizer-mode mistral rejects ANY
chat_template_kwargs with HTTP 400 ("chat_template is not supported for Mistral
tokenizers"), so every request fails and the model looks incapable.

Mistral's thinking is a first-class parameter instead: reasoning_effort, which
the server validates and accepts ONLY as 'none' or 'high' (minimal/medium/xhigh/
max are rejected by name). measured: none -> 0 chars of reasoning, high -> 1368.

Wrapper-only. Install before the benchmark runs.
"""
import os
import inference.utils.openai_compat as _oc
import inference.agent.tool_agent as _ta

_MISTRAL = "mistral" in (os.environ.get("LOCAL_ANALYZER_MODEL_ID") or "").lower()
_EFFORT = os.environ.get("MISTRAL_REASONING_EFFORT", "high")

if not getattr(_oc.build_chat_payload, "__mistral_patched__", False):
    _orig = _oc.build_chat_payload

    def build_chat_payload(*a, **kw):
        p = _orig(*a, **kw)
        if _MISTRAL:
            p.pop("chat_template_kwargs", None)      # hard 400 on mistral tokenizers
            p.pop("top_k", None)                     # not accepted either
            if _EFFORT and _EFFORT != "off":
                p["reasoning_effort"] = _EFFORT      # only 'none' or 'high'
        return p

    build_chat_payload.__mistral_patched__ = True
    _oc.build_chat_payload = build_chat_payload
    # tool_agent imported it by name at module load, so rebind there too
    if hasattr(_ta, "build_chat_payload"):
        _ta.build_chat_payload = build_chat_payload
    print(f"MISTRAL COMPAT installed: mistral={_MISTRAL} reasoning_effort={_EFFORT!r}", flush=True)
else:
    print("MISTRAL COMPAT already installed", flush=True)

# ---- sandbox timeout clamp (LOCAL RUNS ONLY -- see the scope note) ---------
# SCOPE (2026-09-21): this file is exec'd from exactly one place,
# notebooks_duck/ab_local.py:55. It is NOT in any Kaggle bundle, so fixing the
# clamp here has never affected a Kaggle run, including the submission path.
# The Kaggle copy of this shim lives in the ARM cell of
# /home/ignaz/github/arc-prize-2026/notebooks_duck/kaggle_staged/kaggle_notebook_visual/arc-agi-synesthesia.ipynb (cell 14); the
# two must be changed together. Do not read "fixed in cell_mistral_compat.py"
# as "fixed on Kaggle" -- that inference is what left the clamp in place there.
# tool_agent.py:933 does  self._python_timeout = min(30, max(1, _LOCAL_ANALYZER_TOOL_TIMEOUT))
# so the env var cannot raise it above 30s. The tool description tells the model
# to "drive a whole navigation sequence with act()", and a long sweep costs one
# engine round-trip per action -- measured: a 960-action batch was killed after
# 635. The model then reasons about an experiment it believes it ran, from a
# board reflecting two thirds of it. Corrupted evidence, not just lost actions.
# DEFAULT 120 (2026-09-21): a default of 0 meant this shim shipped switched OFF, so
# the clamp kept truncating sweeps in every run that did not explicitly opt in --
# the fix existed but was never in effect. 120s covers the ~960-action batches the
# tool description invites while still bounding a runaway. Set SANDBOX_TIMEOUT_S=30
# to pin the old behaviour (the running alpha sweep does exactly that, so a default
# changed mid-flight cannot alter conditions between its alphas).
_TIMEOUT = int(os.environ.get("SANDBOX_TIMEOUT_S", "120"))
if _TIMEOUT > 30:
    _orig_init = _ta.ToolAgent.__init__
    def __init__(self, *a, **kw):
        _orig_init(self, *a, **kw)
        self._python_timeout = _TIMEOUT
    _ta.ToolAgent.__init__ = __init__
    print(f"SANDBOX TIMEOUT raised to {_TIMEOUT}s (source clamps at 30)", flush=True)
