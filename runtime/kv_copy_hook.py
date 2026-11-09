#!/usr/bin/env python3
"""The setup-script hook that applies patch_kv_copy_chunked.py between the runtime install and the server start.

For Han Solo's runtime (lordhansolo/vllm-main-e975732-arc3), which has no KV copy chunking of its own. The
TAAF / Arm B setup script (setup_commands.json[0]) installs the image runtime and launches the server inside
one function: start_vllm_server() runs `manifest = install_image_runtime()`, builds the server environment
and starts the watchdog. HOOK goes in front of LAUNCH_ANCHOR, the first statement after the script's
definitions (the same cut harness_contract_check.py makes); it rebinds install_image_runtime so that
start_vllm_server() installs, then patches vllm/v1/worker/utils.py, then starts the server. A failed patch
raises, so the setup step fails closed. A watchdog restart re-launches the server only, never the install,
so the patched file stays in place.

The notebook writes the patch script (patch_kv_copy_chunked.py, verbatim) to a file first and passes that
path to insert_hook().

On our 0.31.0 runtime the same hook is harmless: the overlay already installed the patched utils.py and the
patch script reports "already patched".
"""
from __future__ import annotations

LAUNCH_ANCHOR = "print(f'vLLM runtime dataset path: {RUNTIME_DATASET}', flush=True)\n"

HOOK = '''# ---- ARC3 bounded KV block copies: patch the installed runtime before the server starts ----
_ARC3_KV_COPY_PATCH = Path(__PATCH_PATH__)
_arc3_install_image_runtime = install_image_runtime


def install_image_runtime() -> dict:
    manifest = _arc3_install_image_runtime()
    dist_packages = IMAGE_RUNTIME_ROOT / manifest['dist_packages']
    result = subprocess.run(
        [sys.executable, '-I', str(_ARC3_KV_COPY_PATCH), str(dist_packages)], capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(f'ARC3 KV copy patch failed:\\n{result.stdout.strip()}\\n{result.stderr.strip()}')
    print(result.stdout.strip(), flush=True)

    return manifest


'''


def insert_hook(script: str, patch_path: str) -> str:
    """Return the setup script with HOOK inserted once, in front of LAUNCH_ANCHOR."""
    if script.count(LAUNCH_ANCHOR) != 1:
        raise RuntimeError(f"setup script launch anchor found {script.count(LAUNCH_ANCHOR)} times, expected 1")
    if "_arc3_install_image_runtime" in script:
        raise RuntimeError("setup script already carries the ARC3 KV copy hook")
    hook = HOOK.replace("__PATCH_PATH__", repr(str(patch_path)))
    return script.replace(LAUNCH_ANCHOR, hook + LAUNCH_ANCHOR, 1)
