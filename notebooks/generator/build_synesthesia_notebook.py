#!/usr/bin/env python3
"""Build the ARC-AGI-3 Synesthesia Kaggle notebook from our harness tree (CL2, 2026-10-26).

Synesthesia sends the board to the model through its visual pathway: our board-tower student encodes each board
straight into image-embedding rows (vLLM image_embeds), so no PNG is rendered and the native vision tower is never
loaded. This builder writes two things:

1. the harness dataset folder (codywhatleymd/arc3-synesthesia-harness): `git archive <commit> harness/`, plus
   HARNESS_COMMIT.txt and a private dataset-metadata.json. Nothing in it is patched at run time;
2. the notebook folder (codywhatleymd/arc-agi-3-synesthesia): synesthesia.ipynb + kernel-metadata.json.

The notebook's cell logic is v8's (kernel version 8, 10-18; notebooks_duck/kaggle_staged/kaggle_armB_dih_v22_fix_0310),
minus its boot-time patching, which lives in harness/ as code since commit 8552964
(notes/harness_v8_as_code_2026-10-26.md). The harness's own run cells are taken verbatim from v8's staged notebook and
pinned by sha256, so any drift in that source stops the build. Every other difference from v8 is listed in
DIFFERENCES below and written next to the notebook.

usage: build_synesthesia_notebook.py [--out DIR] [--commit REV] [--dataset-dir DIR] [--max-runtime-s 9300]
                                    [--kernel-id ID --title TITLE] [--dataset-slug OWNER/SLUG] [--env KEY=VAL ...]
  --max-runtime-s  the commit run's whole budget from notebook start (v8: 9300). A scored rerun ignores it.
                   Local validation: about 3900 (load + 600 s buffer + ~2,700 s of play).

With no arm flags the build is the anchor notebook (codywhatleymd/arc-agi-3-synesthesia), byte for byte the last
pushed version. An ARM is the same notebook as its own kernel: --kernel-id and --title (Kaggle runs one session per
kernel, so parallel arms need separate kernels), optionally --dataset-slug (the harness dataset it attaches and reads)
and --env KEY=VAL (repeatable: harness switches, harness/SWITCHES.md). An arm states itself three ways: an
"ARM: <title> env: K=V ..." line as the first line of the log, the switches in cell 2's environment (printed as
"synesthesia: env K=V"), and an "arm" record in RUN_CONFIG.json. An arm needs its own --out and --kernel-id, so it can
never overwrite the anchor's staged folder or kernel. Each --env key must be read somewhere in the harness commit's
code, or the arm would silently run as the control (--allow-unread-env overrides, for builder tests only).
"""
import argparse
import hashlib
import importlib.util
import json
import math
import pathlib
import re
import shutil
import subprocess
import sys
import textwrap

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
from notebook_boot import boot_cell  # noqa: E402

V8_NOTEBOOK = REPO / "notebooks_duck/kaggle_staged/kaggle_armB_dih_v22_fix_0310/armB.ipynb"
V8_HARNESS_COMMIT = "8552964"          # harness/ = v8's patched bundle as code; the notebook needs at least this
KERNEL_ID = "codywhatleymd/arc-agi-3-synesthesia"
TITLE = "ARC-AGI-3 Synesthesia"
HARNESS_DATASET = "codywhatleymd/arc3-synesthesia-harness"
TOWER_DATASET = "codywhatleymd/arc3-board-tower-armb"
TOWER_CKPT = "ckpt_px16_dih/best.pt"   # the anchor's student, relative to the tower dataset
TOWER_CKPT_SHA = "5e4eb805a80cab0f21b67dde0240e55d1216d9999fbe1dcd4043a2b544db445b"
TOWER_NPOS = 1024                      # tokens per board of the anchor's student (px16)
# base64 length of torch.save of an (n_pos, 2560) bfloat16 tensor (synth_embeds.b64_tensor, torch 2.13): the
# estimator self-test prices a payload of exactly this size. 1024 reproduces the anchor's measured constant.
B64_LEN_BY_NPOS = {256: 1749732, 1024: 6992612}
RUNTIME_DATASET = "codywhatleymd/vllm-v0310-arc3-py313"
MODEL_SOURCE = "codywhatleymd/arc3-flashnext-nvfp4-ours-v22/PyTorch/v22/3"
COMPETITION = "arc-prize-2026-arc-agi-3"
DATASET_ROOT = pathlib.Path("/home/ignaz/kaggle_local/datasets")   # a harness dataset is built into <root>/<slug>
DEFAULT_OUT = REPO / "notebooks_duck/kaggle_staged/synesthesia"   # the anchor's staged folder

# v8's cells that are the harness's own notebook code (TAAF's run notebook), pinned to the bytes v8 ran.
V8_CELL_SHA = {
    3: "04874ee80d3f925026586b736090a5af9a8309f5b453b8d8e79a006d1500baee",
    4: "8f105fec2e04dc9db8a2a6de789d6a99ae3cde691db5c7ed645f4191c847ca47",
    5: "6db0f653ba871896525d6d9e636b1d350e87f49c1f598c70d9dba1c6b9ca29ce",
    6: "960498334499d8585c4d5bd160a2db4237fc28a47ee19cd7d6764c4f046b5fae",
    7: "f8240d511ad8e0233f35867e358426c7e2ba12f67d5d0ad92d1893695d4814b1",
    8: "686c7b71cc066e486aaa34752193697e34ec7d107afc3af9961be7c9ffe91e1b",
    9: "aca7f3e6c31213ff5f61baec6305feae909fa7cff9756338327a4675193fabf2",
    10: "4ae5d071648efe7c7d84a2b10b58c266033c10d527d1c3cab240548e3db66c3a",
    11: "daf189eff02ce27f66207de32e3a0fba93ceff68a0cebd4b5996b84df0b553e1",
}

DIFFERENCES = """\
Differences from v8 (kernel version 8, notebooks_duck/kaggle_staged/kaggle_armB_dih_v22_fix_0310/armB.ipynb):
- v8 cells 0-1 (markdown) -> one markdown cell in our terms.
- new first code cell: BOOT (scripts/notebook_boot.py), printed before any input is touched.
- v8 cell 2 (copy the frozen bundle, run seven patch scripts and three inline setup edits on the copy, structural and
  marker checks, token-estimate check, environment) -> copy OUR harness dataset (built from one git commit, which the
  cell checks) to /tmp/synesthesia_harness with nothing patched; same tower checkpoint sha256 check; the model is the
  Kaggle Model v22/3 mounted in place (v8 symlink-merged two datasets and set ARM_MODEL_DIR; the setup script now
  resolves v22/3 itself); same embedding-channel marker check and token-estimate check, run on the copy; the same
  environment values except TAAF_KAGGLE_BUNDLE_DIR (our copy), ARM_LABEL ('synesthesia', the output folder name) and
  no ARM_MODEL_DIR. Inputs are found at their two explicit mount paths, never by searching /kaggle/input.
- v8 cell 5: DATASET_SOURCES names our harness and runtime datasets (v8: the frozen bundle and a runtime it no longer
  used); the harness's runtime lookup then gets the runtime's real mount path from TAAF_KAGGLE_INPUT_PATHS.
- v8 cells 10-11: same logic; printed labels and comments in our terms; the serving-line comparison against a twin
  machine's command line is dropped (the three defining embedding flags are still verified and the launched command
  is written to SERVER_CMD.json); ARM_CONFIG.json -> RUN_CONFIG.json.
- metadata: our five inputs (v8: two model datasets, the frozen bundle, the Python 3.12 runtime, the tower); no image
  pin (v8 pinned the 10-06 image; our runtime is built for the current image's Python 3.13).
- v8 cells 3, 4, 6, 7, 8, 9 and the harness's code in 10-11: unchanged.
"""

ABOUT = """\
# ARC-AGI-3 Synesthesia

Synesthesia sends the board to the model through its visual pathway. Our board-tower student, an 18.2M-parameter
network distilled from the model's own 449M-parameter vision tower, encodes each 64x64 board straight into 1,024
image-embedding rows, which vLLM accepts as `image_embeds`. No image is rendered and the native vision tower is never
loaded: each cell's color reaches the model as a visual percept, the way a grapheme-color synesthete sees letters.

What runs here, all of it ours:

- **Model:** our NVFP4/FP8 quantization of Qwen3.8-Flash-Next with an NVFP4 multi-token-prediction head
  (Kaggle Model `codywhatleymd/arc3-flashnext-nvfp4-ours-v22`, v22/3).
- **Serving:** our vLLM 0.31.0 runtime, rebuilt for Python 3.13 (`codywhatleymd/vllm-v0310-arc3-py313`), with bounded
  KV block copies, shipped autotune tactics and parallel shard prefetch for a fast, stable cold start.
- **Board channel:** the board-tower student (`codywhatleymd/arc3-board-tower-armb`) and the harness changes that carry
  its embeddings and price them correctly in the context budget.
- **Harness:** our own tree (`codywhatleymd/arc3-synesthesia-harness`, built from one commit of our repository). It is
  copied and run as it is; nothing is patched at run time.

Built on the TAAF ARC-AGI-3 agent harness (Tufa ARC-AGI Framework), serving on vLLM.
"""

CELL_HARNESS = r'''# ================================ Synesthesia: harness + environment ================================
# The harness is ours: harness/ in the arc-prize-2026 repository, shipped as a dataset built from one git commit. It is
# copied to a writable directory and run as it is; nothing is patched here.
import hashlib, importlib.util, json, os, pathlib, shutil, sys

ARM_LABEL = "synesthesia"                      # output folder name (/kaggle/working/synesthesia)
EXPECT_HARNESS_COMMIT = "__HARNESS_COMMIT__"
EXPECT_CKPT_SHA = "5e4eb805a80cab0f21b67dde0240e55d1216d9999fbe1dcd4043a2b544db445b"
MODEL_PARTS = ("codywhatleymd", "arc3-flashnext-nvfp4-ours-v22", "PyTorch", "v22", "3")


def _dataset_dir(owner: str, slug: str, marker: str) -> pathlib.Path:
    """Kaggle mounts a dataset at /kaggle/input/datasets/<owner>/<slug> or /kaggle/input/<slug>; check both."""
    for cand in (pathlib.Path("/kaggle/input/datasets") / owner / slug, pathlib.Path("/kaggle/input") / slug):
        if (cand / marker).is_file():
            return cand
    raise RuntimeError(f"dataset {owner}/{slug} is not mounted (no {marker} at either mount path)")


# ---- 1. the harness: our commit, copied, nothing patched -------------------------------------------------------
HARNESS_SRC = _dataset_dir("codywhatleymd", "arc3-synesthesia-harness", "taaf-kaggle-bundle.json")
_commit = (HARNESS_SRC / "HARNESS_COMMIT.txt").read_text().split()[0]
if not _commit.startswith(EXPECT_HARNESS_COMMIT):
    raise RuntimeError(f"harness dataset is commit {_commit}, this notebook was built for {EXPECT_HARNESS_COMMIT}")
HARNESS_DIR = pathlib.Path("/tmp/synesthesia_harness")   # writable, and not a notebook output
if HARNESS_DIR.exists():
    shutil.rmtree(HARNESS_DIR)
shutil.copytree(HARNESS_SRC, HARNESS_DIR)
_n = 0
for _src in HARNESS_SRC.rglob("*"):
    if _src.is_file():
        _n += 1
        if (HARNESS_DIR / _src.relative_to(HARNESS_SRC)).read_bytes() != _src.read_bytes():
            raise RuntimeError(f"harness copy differs from the dataset at {_src.relative_to(HARNESS_SRC)}")
print(f"synesthesia: harness {HARNESS_SRC} @ {_commit[:12]} -> {HARNESS_DIR} ({_n} files, copied as is)", flush=True)

# ---- 2. the board tower: the checkpoint is byte-identical to the one v8 ran -------------------------------------
BT = _dataset_dir("codywhatleymd", "arc3-board-tower-armb", "SHA256SUMS")
CKPT = BT / "ckpt_px16_dih" / "best.pt"
h = hashlib.sha256()
with open(CKPT, "rb") as f:
    for chunk in iter(lambda: f.read(1 << 20), b""):
        h.update(chunk)
if h.hexdigest() != EXPECT_CKPT_SHA:
    raise RuntimeError(f"board-tower checkpoint sha256 {h.hexdigest()} != {EXPECT_CKPT_SHA}")
print(f"synesthesia: tower {BT}, ckpt sha256 OK ({EXPECT_CKPT_SHA[:16]}..., {CKPT.stat().st_size:,} B)", flush=True)


# ---- 3. the model: the Kaggle Model, mounted in place, found the way the setup script finds it ------------------
def _model_dir(owner: str, model: str, framework: str, instance: str, version: str) -> pathlib.Path:
    cands = []
    for fw in dict.fromkeys((framework.lower(), framework)):
        cands += [pathlib.Path("/kaggle/input/models") / owner / model / fw / instance / version,
                  pathlib.Path("/kaggle/input") / model / fw / instance / version]
    for cand in cands:
        if (cand / "model.safetensors.index.json").is_file():
            return cand
    raise RuntimeError(f"model {'/'.join((owner, model, framework, instance, version))} is not mounted "
                       f"(tried {[str(c) for c in cands]})")


MODEL_DIR = _model_dir(*MODEL_PARTS)
_wm = json.loads((MODEL_DIR / "model.safetensors.index.json").read_text())["weight_map"]
_need = sorted(set(_wm.values()))
_miss = [f for f in _need if not (MODEL_DIR / f).is_file()]
if _miss:
    raise RuntimeError(f"{MODEL_DIR}: {len(_miss)} shard files missing, e.g. {_miss[:3]}")
print(f"synesthesia: model {MODEL_DIR} ({len(_need)} shard files, "
      f"{sum((MODEL_DIR / f).stat().st_size for f in _need) / 1e9:.1f} GB, {len(_wm)} tensors)", flush=True)

# ---- 4. the embedding channel is in this harness ----------------------------------------------------------------
MARKERS = {
    "setup_commands.json": ["ARM_MAX_PIXELS", "ARM_LIMIT_MM", "ARM_ENABLE_MM_EMBEDS", "ARM_UPSCALE",
                            "vllm-v0310-arc3-py313", "'arc3_tools' / 'patch_kv_copy_chunked.py'", "_ARC3_PF_NEW"],
    "src/ARC3-Inference/inference/agent/token_estimate.py": ["_embeds_part_tokens", '"image_embeds"'],
    "src/ARC3-Inference/inference/agent/transcript_log.py": ["_elide_embeds_payloads"],
    "src/ARC3-Inference/inference/agent/vision_context.py":
        ["_student_tower_part", "ARM_B_STUDENT_TOWER", "BOARD_TOWER_THREADS", "_log_png_part", "ARM_B_EXPECT_NPOS"],
}
for rel, needles in MARKERS.items():
    text = (HARNESS_DIR / rel).read_text()
    for needle in needles:
        if needle not in text:
            raise RuntimeError(f"{rel}: {needle!r} absent -- this is not the Synesthesia harness")
if not (HARNESS_DIR / "arc3_tools" / "patch_kv_copy_chunked.py").is_file():
    raise RuntimeError("arc3_tools/patch_kv_copy_chunked.py is missing from the harness")
print("synesthesia: embedding channel present (setup flags, token pricing, log elision, board-tower branch)", flush=True)

# ---- 5. the token-estimate fix, measured before a single game is played -----------------------------------------
# An image_embeds part carries a ~7 MB base64 tensor. Priced as text it would be ~2.4M tokens against a true 1,024,
# and the 81,536-token context target would trim history to nothing every turn. The harness prices it at its row
# count; measured here, not assumed. (torch is not imported yet: the setup may replace it.)
_spec = importlib.util.spec_from_file_location(
    "te_synesthesia", HARNESS_DIR / "src/ARC3-Inference/inference/agent/token_estimate.py")
_te_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_te_mod)
_B64_LEN = 6992612          # measured: torch.save of a (1024, 2560) bfloat16 tensor, base64'd
_fake = {"type": "image_embeds", "uuid": "tower-g1024-fa0a0f5dbd-" + "0" * 40,
         "image_embeds": {"image_embeds": "A" * _B64_LEN, "image_grid_thw": "A" * 300}}
_msgs = [{"role": "user", "content": [{"type": "text", "text": "Pick the next action."}, _fake]}]
_priced_total = _te_mod.estimate_tokens(_msgs)
_rows = _te_mod._embeds_part_tokens(_fake)
print(f"synesthesia: token estimate of one board message = {_priced_total:,} tokens (board priced at {_rows}, "
      f"true 1024)", flush=True)
if _rows != 1024 or _priced_total > 2000:
    raise RuntimeError(f"token estimate prices a board at {_rows} rows / {_priced_total} tokens -- history would be "
                       f"trimmed to nothing")

# ---- 6. the run's environment -----------------------------------------------------------------------------------
# Every variable gates one harness behaviour and defaults to the base harness's value when unset.
ARM_ENV = {
    "ARM_LABEL": ARM_LABEL,
    "ARM_UPSCALE": "16",                 # 1024 tokens per board (16 px per cell)
    "ARM_MAX_PIXELS": "1048576",         # -> --mm-processor-kwargs {"max_pixels": 1048576}
    "ARM_LIMIT_MM": '{"image":0,"video":0}',   # no image may arrive as pixels: the native tower is never loaded
    "ARM_ENABLE_MM_EMBEDS": "1",         # -> --enable-mm-embeds
    "ARM_B_STUDENT_TOWER": "1",          # the board-tower branch of vision_context
    "ARM_B_EXPECT_NPOS": "1024",         # hard-fails a geometry-mismatched checkpoint
    "BOARD_TOWER_REPO": str(BT),
    "BOARD_TOWER_CKPT": str(CKPT),
    "BOARD_TOWER_DEVICE": "cpu",         # the GPU belongs to the server
    "BOARD_TOWER_ANY_GPU": "1",
    "BOARD_TOWER_THREADS": "2",          # an uncapped torch takes every core and starves the server
    "TAAF_KAGGLE_BUNDLE_DIR": str(HARNESS_DIR),
    # A commit run's whole budget from notebook start (the pickled default, 2100 s, leaves almost no play after the
    # setup and the model load). A scored rerun ignores it: its soft end is None.
    "ARM_MAX_RUNTIME_S": "__MAX_RUNTIME_S__",
}
os.environ.update(ARM_ENV)
for k in sorted(ARM_ENV):
    print(f"synesthesia: env {k}={ARM_ENV[k]}", flush=True)
print(f"synesthesia: host has {os.cpu_count()} vCPU "
      f"(board-tower peak demand {14 * int(ARM_ENV['BOARD_TOWER_THREADS'])} threads)", flush=True)
'''

# Exact rewrites of v8's cells 5, 10 and 11: (old, new, expected count). Logic is untouched; labels, comments and the
# twin comparison change.
def cell5_edits(harness_dataset: str) -> list:
    return [
        ('DATASET_SOURCES: list[str] = ["codywhatleymd/arc3-taaf-bundle-frozen", "lordhansolo/vllm-main-e975732-arc3"]',
         f'DATASET_SOURCES: list[str] = ["{harness_dataset}", "{RUNTIME_DATASET}"]', 1),
    ]

CELL10_EDITS = [
    ("# ================================ ARM B: the customization hook ================================\n"
     "# His cell 8, used for what he documents it for. Runs AFTER his setup (so torch is whatever the\n"
     "# server's install left behind) and BEFORE the first game.\n",
     "# ================================ customization hook ================================\n"
     "# The harness's customization point: runs after its setup (so torch is whatever the server's install\n"
     "# left behind) and before the first game.\n", 1),
    ("# ---- artifacts in one directory, the twin's layout, so score_arm.py / count_wire.py apply -------\n",
     "# ---- this run's artifacts in one directory ----------------------------------------------------\n", 1),
    ("# His pickled target.max_runtime_s", "# The pickled target.max_runtime_s", 1),
    ('f"ARM B: target.max_runtime_s left at his pickled "', 'f"synesthesia: target.max_runtime_s left at the pickled "', 1),
    ("# ---- the student, loaded once here so a bad mount fails BEFORE any game ------------------------\n",
     "# ---- the board-tower student, loaded once here so a bad mount fails BEFORE any game -------------\n", 1),
    ("# the MANDATORY patch, re-measured against a REAL student part rather than a synthetic one\n",
     "# the token-estimate fix, measured again against a REAL board-tower part rather than a synthetic one\n", 1),
    ("# the loaded harness module really is the patched one, in THIS process\n",
     "# the loaded harness module really has the board-tower branch, in THIS process\n", 1),
    ('"vision_context in sys.modules is NOT the patched copy"',
     '"vision_context in sys.modules lacks the board-tower branch"', 1),
    ('f"ARM B: vision_context patched, current_grid enabled, "',
     'f"synesthesia: vision_context has the board-tower branch, current_grid enabled, "', 1),
    ('f"(inert in arm B: the student branch never renders a PNG)"',
     'f"(unused: the board-tower branch never renders a PNG)"', 1),
    ("# ---- the SERVER really got the arm-B flags (RUNBOOK PASS criterion 1) --------------------------\n"
     "# Setting ARM_* is not evidence; the launched command line is. Three flags DEFINE arm B: without\n"
     "# --enable-mm-embeds an image_embeds part is rejected, and without image:0 a silent fallback to his\n"
     "# pixel path would be possible and would look exactly like success.\n",
     "# ---- the SERVER really got the embedding flags --------------------------------------------------\n"
     "# Setting ARM_* is not evidence; the launched command line is. Three flags define the channel: without\n"
     "# --enable-mm-embeds an image_embeds part is rejected, and without image:0 a silent fallback to the\n"
     "# pixel path would be possible and would look exactly like success.\n", 1),
    ("# warns, a WRONG flag aborts (a wrong flag means the arm is not arm B and the run is worthless).\n",
     "# warns, a WRONG flag aborts (a wrong flag means the board channel is not what runs).\n", 1),
    ('f"(arm B\'s result holds only at 1024 tokens/board)")', 'f"(the board tower produces 1024 tokens/board)")', 1),
]

CELL11_EDITS = [
    ("        # His 3,918 s/game x ceil(110/14) = 8 waves", "        # The pickled 3,918 s/game x ceil(110/14) = 8 waves", 1),
    ("    # ---- ARM B provenance: the EFFECTIVE config, read off the objects the run actually uses ----\n",
     "    # ---- provenance: the EFFECTIVE config, read off the objects the run actually uses ----\n", 1),
    ('_src = "his PNG pixel path (image_url) through the native tower"',
     '_src = "PNG pixel path (image_url) through the native tower"', 1),
    ('(ARM_JOB / "ARM_CONFIG.json").write_text(json.dumps({\n        "arm": ARM_LABEL,',
     '(ARM_JOB / "RUN_CONFIG.json").write_text(json.dumps({\n        "run": ARM_LABEL,', 1),
    ('os.environ.get("ARM_MAX_PIXELS", "65536 (his default)")', 'os.environ.get("ARM_MAX_PIXELS", "65536 (harness default)")', 1),
    ("""_limit_mm or '{"video": 0} (his default)'""", """_limit_mm or '{"video": 0} (harness default)'""", 1),
    ("        # ---- ARM B evidence gate (review finding 1, 2026-10-06): his Benchmark.run swallows the\n",
     "        # ---- evidence gate (review finding 1, 2026-10-06): Benchmark.run swallows the\n", 1),
    ('raise RuntimeError("ARM B evidence gate FAILED: no student image_embeds part was ever sent "',
     'raise RuntimeError("evidence gate FAILED: no board-tower image_embeds part was ever sent "', 1),
]


def apply_edits(text: str, edits: list, where: str) -> str:
    for old, new, count in edits:
        got = text.count(old)
        if got != count:
            raise SystemExit(f"{where}: expected {count} of {old[:70]!r}, found {got}")
        text = text.replace(old, new)
    return text


def rewrite_cell10(text: str) -> str:
    text = apply_edits(text, CELL10_EDITS, "cell 10")
    # drop the comparison with the twin machine's serving line; keep the record of this run's command
    start = text.index("    # a full diff against the serving line arm B actually ran;")
    end = text.index("json.dumps({\"this_run\": _cmd, \"twin_armB\": _ARMB_CMD}, indent=1))") + \
        len("json.dumps({\"this_run\": _cmd, \"twin_armB\": _ARMB_CMD}, indent=1))")
    text = text[:start] + ('    (ARM_JOB / "SERVER_CMD.json").write_text(json.dumps({"this_run": _cmd}, indent=1))\n'
                           '    print("synesthesia: serving line:", " ".join(_cmd), flush=True)') + text[end:]
    return text.replace('"ARM B: ', '"synesthesia: ')


def rewrite_cell11(text: str) -> str:
    text = apply_edits(text, CELL11_EDITS, "cell 11")
    return text.replace('"ARM B: ', '"synesthesia: ')


def git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(REPO), *args], check=True, capture_output=True, text=True).stdout.strip()


def kaggle_slug(title: str) -> str:
    """The slug Kaggle derives from a title. `kaggle kernels push` uses python-slugify and warns when a title does not
    resolve to the metadata id; for a new kernel that means 'surprising behavior', so the build refuses it instead."""
    try:
        from slugify import slugify
        return slugify(title)
    except ImportError:          # python-slugify's result for plain ASCII titles without quotes
        return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def dataset_title(slug: str) -> str:
    """The harness dataset's title: 'ARC3 Synesthesia Harness' for the anchor's slug, the same rule for an arm's."""
    return " ".join(w.upper() if w == "arc3" else w.capitalize() for w in slug.split("/")[1].split("-"))


def write_dataset(commit: str, out: pathlib.Path, harness_dataset: str) -> None:
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    archive = subprocess.run(["git", "-C", str(REPO), "archive", "--format=tar", commit, "harness/"],
                             check=True, capture_output=True).stdout
    subprocess.run(["tar", "-x", "--strip-components=1", "-C", str(out)], input=archive, check=True)
    subject = git("log", "-1", "--format=%H %cI %s", commit)
    (out / "HARNESS_COMMIT.txt").write_text(subject + "\n")
    (out / "dataset-metadata.json").write_text(json.dumps({
        "title": dataset_title(harness_dataset),
        "id": harness_dataset,
        "isPrivate": True,
        "licenses": [{"name": "unknown"}],
        "description": ("The agent harness of the ARC-AGI-3 Synesthesia notebook, built from one commit of our "
                        f"repository ({commit[:12]}, recorded in HARNESS_COMMIT.txt). It carries the board-tower "
                        "embedding channel, its token pricing and log handling, and our serving setup (vLLM 0.31.0 "
                        "for Python 3.13, bounded KV block copies, parallel shard prefetch). Built on the TAAF "
                        "ARC-AGI-3 agent harness."),
    }, indent=1) + "\n")


# ---- arms -------------------------------------------------------------------------------------------------------
# Cell 2's own environment. An arm's --env adds switches on top of it and may not redefine one of these (the run's
# budget has its own flag, --max-runtime-s).
BASE_ENV_KEYS = frozenset(re.findall(r'^    "([A-Z0-9_]+)":',
                                     CELL_HARNESS.split("ARM_ENV = {\n", 1)[1].split("\n}\n", 1)[0], re.M))
ENV_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
REF = re.compile(r"[A-Za-z0-9_-]+/[a-z0-9][a-z0-9-]*")
ARM_BLOCK = """\
# ---- the arm: its own kernel, harness dataset and switches (build_synesthesia_notebook.py arm flags) -------------
# The switches are set on top of the environment above; none of them redefines one of its values.
ARM_NAME = __TITLE__
ARM_KERNEL = __KERNEL__
ARM_HARNESS_DATASET = __DATASET__
ARM_SWITCHES = __SWITCHES__
ARM_ENV.update(ARM_SWITCHES)
"""
ARM_SWITCH_CHECK = """\
# Fail here, in seconds, not after the model load: the harness's own check (utils/env.py) rejects SYN_* keys no
# switch reads and malformed values, either of which would otherwise run the control arm.
_spec = importlib.util.spec_from_file_location("syn_env_check", HARNESS_DIR / "src/ARC3-Inference/inference/utils/env.py")
_syn_env = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_syn_env)
print("synesthesia: switches checked:", _syn_env.validate_syn_env({**os.environ, **ARM_ENV}), flush=True)
"""
RUN_CONFIG_ARM = ('        "arm": {"title": ARM_NAME, "kernel_id": ARM_KERNEL, "harness_dataset": ARM_HARNESS_DATASET,\n'
                  '                "env": {k: os.environ.get(k) for k in ARM_SWITCHES}},\n')


def parse_env(items: list) -> dict:
    env = {}
    for item in items:
        key, sep, val = item.partition("=")
        if not sep or not ENV_KEY.fullmatch(key):
            raise SystemExit(f"--env {item!r}: expected KEY=VAL, KEY an environment variable name")
        if key in env:
            raise SystemExit(f"--env {key} is given twice")
        if key in BASE_ENV_KEYS:
            raise SystemExit(f"--env {key}: cell 2's environment already sets it; an arm adds switches, it does not "
                             f"redefine the base run")
        env[key] = val
    return dict(sorted(env.items()))       # flag order does not change the notebook


def unread_env(env: dict, dataset_dir: pathlib.Path) -> list:
    """The --env keys that no code file of the harness dataset mentions (docs and the build's own records excluded)."""
    code = [f.read_bytes() for f in sorted(dataset_dir.rglob("*"))
            if f.is_file() and f.suffix not in (".md", ".txt") and f.name != "dataset-metadata.json"]
    return [k for k in env if not any(k.encode() in b for b in code)]


def check_arm_env(env: dict, dataset_dir: pathlib.Path) -> bool:
    """Run the arm's own harness check (validate_syn_env in utils/env.py at its commit) on its switches, so a bad
    switch fails the build instead of a Kaggle run after the model load. Returns whether that commit has the check
    (an older commit does not: only the unread-key check covers it then)."""
    paths = sorted(dataset_dir.rglob("inference/utils/env.py"))
    if len(paths) != 1:
        raise SystemExit(f"expected one inference/utils/env.py in {dataset_dir}, found {len(paths)}")
    if "def validate_syn_env" not in paths[0].read_text(encoding="utf-8"):
        return False
    spec = importlib.util.spec_from_file_location("arm_env_check", paths[0])
    module = importlib.util.module_from_spec(spec)
    saved, sys.dont_write_bytecode = sys.dont_write_bytecode, True    # no __pycache__ in the dataset folder
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = saved
    try:
        module.validate_syn_env(dict(env))
    except ValueError as exc:
        raise SystemExit(f"--env: {exc}") from None
    return True


def arm_banner(title: str, env: dict) -> str:
    return f"ARM: {title} env: " + (" ".join(f"{k}={v}" for k, v in env.items()) or "(none)")


def arm_cells(cells: list, title: str, kernel_id: str, harness_dataset: str, env: dict,
              switch_check: bool = False) -> list:
    """The anchor's cells made into an arm's: the About heading, the log banner, the switches, the RUN_CONFIG record."""
    switches = (", ".join(f"`{k}={v}`" for k, v in env.items()) + " (harness switches, harness/SWITCHES.md)"
                if env else "no harness switches")
    harness = "" if harness_dataset == HARNESS_DATASET else f"; harness dataset `{harness_dataset}`"
    arm_md = textwrap.fill(f"**Arm** of `{KERNEL_ID}`: {switches}{harness}. Everything else is that notebook.",
                           width=118, break_long_words=False, break_on_hyphens=False)
    about = apply_edits(cells[0][1], [
        ("# ARC-AGI-3 Synesthesia\n\n", f"# {title}\n\n{arm_md}\n\n", 1),
        (f"`{HARNESS_DATASET}`", f"`{harness_dataset}`", 1)], "about")
    boot = apply_edits(cells[1][1], [
        ("_BOOT_T0 = time.time()\n",
         f"_BOOT_T0 = time.time()\nprint({json.dumps(arm_banner(title, env))}, flush=True)\n", 1)], "boot")
    block = (ARM_BLOCK.replace("__TITLE__", json.dumps(title)).replace("__KERNEL__", json.dumps(kernel_id))
             .replace("__DATASET__", json.dumps(harness_dataset)).replace("__SWITCHES__", json.dumps(env)))
    if switch_check:
        block += ARM_SWITCH_CHECK
    harness_cell = apply_edits(cells[2][1], [
        ("os.environ.update(ARM_ENV)\n", block + "os.environ.update(ARM_ENV)\n", 1)], "cell 2")
    run_cell = apply_edits(cells[11][1], [
        ('        "run": ARM_LABEL,\n', '        "run": ARM_LABEL,\n' + RUN_CONFIG_ARM, 1)], "cell 11")
    return ([("markdown", about), ("code", boot), ("code", harness_cell)] + cells[3:11] + [("code", run_cell)])


def tower_cells(cells: list, tower_dataset: str, ckpt: str, ckpt_sha: str, npos: int) -> list:
    """The anchor's cells with another board-tower student: its dataset, checkpoint, sha256 and token count, in every
    place the anchor fixes 1024 (cell 2's estimator self-test and ARM_B_EXPECT_NPOS, cell 10's shape and pricing
    checks, cell 11's evidence gate). The anchor's PNG settings (ARM_UPSCALE, ARM_MAX_PIXELS) are inert on the student
    branch and stay as they are."""
    if npos not in B64_LEN_BY_NPOS:
        raise SystemExit(f"--tower-npos {npos}: no measured payload length (have {sorted(B64_LEN_BY_NPOS)})")
    t_owner, t_slug = tower_dataset.split("/")
    ckpt_parts = " / ".join(json.dumps(x) for x in ckpt.split("/"))
    c2 = apply_edits(cells[2][1], [
        ('BT = _dataset_dir("codywhatleymd", "arc3-board-tower-armb", "SHA256SUMS")',
         f'BT = _dataset_dir("{t_owner}", "{t_slug}", "SHA256SUMS")', 1),
        ('CKPT = BT / "ckpt_px16_dih" / "best.pt"', f'CKPT = BT / {ckpt_parts}', 1),
        (f'EXPECT_CKPT_SHA = "{TOWER_CKPT_SHA}"', f'EXPECT_CKPT_SHA = "{ckpt_sha}"', 1),
        ("_B64_LEN = 6992612          # measured: torch.save of a (1024, 2560) bfloat16 tensor, base64'd",
         f"_B64_LEN = {B64_LEN_BY_NPOS[npos]}          # measured: torch.save of a ({npos}, 2560) bfloat16 tensor, base64'd", 1),
        ('"uuid": "tower-g1024-', f'"uuid": "tower-g{npos}-', 1),
        ('f"true 1024)", flush=True)', f'f"true {npos})", flush=True)', 1),
        ('if _rows != 1024 or _priced_total > 2000:', f'if _rows != {npos} or _priced_total > 2000:', 1),
        ('"ARM_UPSCALE": "16",                 # 1024 tokens per board (16 px per cell)',
         '"ARM_UPSCALE": "16",                 # inert on the student branch (it never renders a PNG)', 1),
        ('"ARM_B_EXPECT_NPOS": "1024",', f'"ARM_B_EXPECT_NPOS": "{npos}",', 1)], "cell 2 (tower)")
    c10 = apply_edits(cells[10][1], [
        ("assert tuple(_emb.shape) == (1024, 2560)", f"assert tuple(_emb.shape) == ({npos}, 2560)", 1),
        ("tokens (true 1024)\", flush=True)", f"tokens (true {npos})\", flush=True)", 1),
        ("if _priced != 1024:", f"if _priced != {npos}:", 1),
        ("not 1024 -- ", f"not {npos} -- ", 1)], "cell 10 (tower)")
    c11 = apply_edits(cells[11][1], [
        ("        # 1024 tokens in board_parts.jsonl,", f"        # {npos} tokens in board_parts.jsonl,", 1),
        ('_r.get("n_tokens") == 1024:', f'_r.get("n_tokens") == {npos}:', 1),
        ("student image_embeds parts at 1024 tokens", f"student image_embeds parts at {npos} tokens", 1)], "cell 11 (tower)")
    return cells[:2] + [(cells[2][0], c2)] + cells[3:10] + [(cells[10][0], c10), (cells[11][0], c11)]


RESTORE_ANCHOR = 'print(f"synesthesia: job_dir={bm.job_dir} save_request_logs={bm.solver.save_request_logs}", flush=True)\n'

POOL_ANCHOR = "    try:\n        await bm.run(\n"
POOL_CODE = '''    # ---- pool clock (builder --pool-clock; harness solver.pool_clock) ----
    # No per-game time cap. A game keeps its slot while it clears levels; while other games are still waiting for a
    # slot, it hands its slot back after 1,500 actions with no level clear, or after 750 once it has used more than its
    # fair share of the run's slot-time. Shares are sized against the 9 h notebook budget on a scored rerun (the
    # platform ends the run) and against the commit run's soft end otherwise.
    bm.solver.pool_clock = True
    bm.solver.pool_clock_end_epoch = (
        NOTEBOOK_START_EPOCH + float(os.environ.get("ARC3_NOTEBOOK_LIMIT_S", "32400"))
        if (true_submission or soft_end is None) else soft_end.timestamp())
    print(f"synesthesia: POOL CLOCK on: end in {bm.solver.pool_clock_end_epoch - time.time():.0f} s, "
          f"concurrency {bm.solver.concurrency}, {len(bm.games)} games x {bm.n_passes} passes "
          f"(fixed per-game clock {bm.solver.max_runtime_s_per_game} is now only the fallback)", flush=True)

'''


WHEELHOUSE_OLD = 'wheelhouse = Path("/kaggle/input/competitions/arc-prize-2026-arc-agi-3/arc_agi_3_wheels")\n'
WHEELHOUSE_NEW = (
    "# The competition mounts at /kaggle/input/competitions/<slug> on some hosts and at /kaggle/input/<slug> on others\n"
    "# (10-31: the pool-clock run got the second, skipped the arc-agi install and died on a missing arcengine 1,597 s in).\n"
    "_WHEELHOUSE_CANDIDATES = [Path(\"/kaggle/input/competitions/arc-prize-2026-arc-agi-3/arc_agi_3_wheels\"),\n"
    "                          Path(\"/kaggle/input/arc-prize-2026-arc-agi-3/arc_agi_3_wheels\")]\n"
    "wheelhouse = next((p for p in _WHEELHOUSE_CANDIDATES if p.exists()), _WHEELHOUSE_CANDIDATES[0])\n"
    "print(f\"synesthesia: competition wheelhouse {wheelhouse} (exists={wheelhouse.exists()})\", flush=True)\n"
    "if not wheelhouse.exists() and os.environ.get(\"KAGGLE_KERNEL_RUN_TYPE\"):\n"
    "    raise RuntimeError(f\"competition wheelhouse not found at {[str(p) for p in _WHEELHOUSE_CANDIDATES]}: \"\n"
    "                       f\"arc-agi would not be installed and arcengine would be missing\")\n")


def fix_wheelhouse_cell(text: str) -> str:
    """Cell 4: find the competition wheelhouse at either mount path, and fail fast on Kaggle when it is missing."""
    return apply_edits(text, [(WHEELHOUSE_OLD, WHEELHOUSE_NEW, 1)], "cell 4 (wheelhouse)")


BOOT_CLOCK_ANCHOR = "NOTEBOOK_START_EPOCH = time.time()\n"
BOOT_CLOCK_CODE = '''NOTEBOOK_START_EPOCH = time.time()
# ---- boot clock (builder --boot-clock) ----
# On scored reruns the notebook starts ~40-50 min after the machine does, and that time counts against the 9 h limit
# (forum topic 753843, 10-29/30: a /proc/uptime check at notebook start, and an empty notebook taking ~50 min to error).
# Scored-run clocks therefore count from the machine's start when /proc/uptime gives a plausible value (0 < uptime < 2 h;
# a container on a long-running host reports the host's uptime instead, and then the notebook start is used).
try:
    MACHINE_UPTIME_S = float(open("/proc/uptime").read().split()[0])
except Exception:
    MACHINE_UPTIME_S = -1.0
CLOCK_START_EPOCH = (min(NOTEBOOK_START_EPOCH, time.time() - MACHINE_UPTIME_S)
                     if 0.0 < MACHINE_UPTIME_S < 7200.0 else NOTEBOOK_START_EPOCH)
print(f"BOOT machine_uptime_s={MACHINE_UPTIME_S:.0f} clock_start_offset_s={NOTEBOOK_START_EPOCH - CLOCK_START_EPOCH:.0f}",
      flush=True)
'''


def boot_clock_cells(cells: list) -> list:
    """Count the scored-run clocks (the per-game clock fit and, with --pool-clock, the pool's end) from the machine's
    start instead of the notebook's (cell 3 defines CLOCK_START_EPOCH; cell 11 uses it). Commit runs are unchanged:
    their pool end is the soft end and the clock fit runs only on a scored rerun."""
    c3 = apply_edits(cells[3][1], [(BOOT_CLOCK_ANCHOR, BOOT_CLOCK_CODE, 1)], "cell 3 (boot clock)")
    edits = [("_arc3_left = NOTEBOOK_START_EPOCH + _arc3_limit", "_arc3_left = CLOCK_START_EPOCH + _arc3_limit", 1)]
    if "pool_clock_end_epoch = (" in cells[11][1]:
        edits.append(('        NOTEBOOK_START_EPOCH + float(os.environ.get("ARC3_NOTEBOOK_LIMIT_S", "32400"))',
                      '        CLOCK_START_EPOCH + float(os.environ.get("ARC3_NOTEBOOK_LIMIT_S", "32400"))', 1))
    c11 = apply_edits(cells[11][1], edits, "cell 11 (boot clock)")
    return cells[:3] + [(cells[3][0], c3)] + cells[4:11] + [(cells[11][0], c11)] + cells[12:]


def pool_clock_cells(cells: list, dataset_dir: pathlib.Path, park: bool = False, stall: int | None = None,
                     soft_stall: int | None = None, stall_seconds: float | None = None,
                     min_share: float | None = None) -> list:
    """Turn on the harness's pool clock (solver.pool_clock) in cell 11, just before the run starts; optionally
    park/resume (solver.pool_park), non-default stall thresholds (smoke tests only) and the time-based stop
    (solver.pool_stall_seconds, solver.pool_min_share_s; both unset unless their flag is given)."""
    solver_src = (dataset_dir / "src/ARC3-Inference/inference/framework/solver.py").read_text()
    if "def _pool_take_budget" not in solver_src:
        raise SystemExit("--pool-clock: this harness commit has no pool clock (solver._pool_take_budget)")
    code = POOL_CODE
    if park:
        if "def _pool_next_parked" not in solver_src:
            raise SystemExit("--pool-park: this harness commit has no park/resume (solver._pool_next_parked)")
        code += ('    # Park/resume (builder --pool-park): a stalled game gives up its slot unfinished; once every game\n'
                 '    # has had a slot, parked games resume deepest level first, each with a fresh stall window.\n'
                 '    bm.solver.pool_park = True\n')
    if stall is not None:
        code += f'    bm.solver.pool_stall_actions = {int(stall)}\n'
    if soft_stall is not None:
        code += f'    bm.solver.pool_soft_stall_actions = {int(soft_stall)}\n'
    if park or stall is not None or soft_stall is not None:
        code += ('    print(f"synesthesia: pool park={getattr(bm.solver, \'pool_park\', False)} '
                 'stall={bm.solver.pool_stall_actions} soft_stall={bm.solver.pool_soft_stall_actions}", flush=True)\n\n')
    if stall_seconds is not None or min_share is not None:
        if "def pool_time_stop_reached" not in solver_src:
            raise SystemExit("--pool-stall-seconds / --pool-min-share: this harness commit has no time-based stop "
                             "(solver._HarnessGameSession.pool_time_stop_reached)")
        code += ('    # Time-based stop (builder --pool-stall-seconds / --pool-min-share): only a game that has used its fair\n'
                 '    # share hands its slot back, at its next action boundary (parked, with --pool-park): while other games\n'
                 '    # wait, once it has gone pool_stall_seconds without a level clear; while any game is unstarted, once the\n'
                 '    # slot-time left cannot give each unstarted game pool_min_share_s, progressing or not.\n')
        if stall_seconds is not None:
            code += f'    bm.solver.pool_stall_seconds = {float(stall_seconds)!r}\n'
        if min_share is not None:
            code += f'    bm.solver.pool_min_share_s = {float(min_share)!r}\n'
        code += ('    print(f"synesthesia: pool time-based stop: stall_seconds={bm.solver.pool_stall_seconds} '
                 'min_share_s={bm.solver.pool_min_share_s}", flush=True)\n\n')
    c11 = apply_edits(cells[11][1], [(POOL_ANCHOR, code + POOL_ANCHOR, 1)], "cell 11 (pool clock)")
    return cells[:11] + [(cells[11][0], c11)] + cells[12:]


def restore_cells(cells: list, per_game_none: bool, concurrency, max_actions, audit_every) -> list:
    """Restoration-series solver settings (notes/prestate_restoration_2026-10-30.md), set on the unpickled solver in
    cell 10 (Benchmark.run deep-copies it, so they carry into the run). The strategy audit, time-triggered in the
    harness (25% of the per-game clock since the last level clear or delivered audit, solver.py:238-250, 310, 476-477),
    can be re-triggered by ACTIONS with the same reset rules: due once `audit_every` actions have passed since the
    last change of _strategy_audit_started_at (a level clear or a delivered audit)."""
    code = "\n# ---- restoration series: solver settings (inert in the anchor; builder --per-game-none etc.) ----\n"
    if per_game_none:
        code += "bm.solver.max_runtime_s_per_game = None\n"
    if concurrency is not None:
        code += f"bm.solver.concurrency = {int(concurrency)}\n"
    if max_actions is not None:
        code += f"bm.solver.max_actions_per_game = {int(max_actions)}\n"
    if audit_every is not None:
        code += f'''from inference.framework import solver as _arc3_solver
_ARC3_AUDIT_EVERY = {int(audit_every)}


def _arc3_should_audit_strategy(self) -> bool:
    """Action-triggered strategy audit: due once _ARC3_AUDIT_EVERY actions have passed since the last level clear or
    delivered audit (both move _strategy_audit_started_at, solver.py:310 and :477)."""
    s = self._strategy_audit_started_at
    if getattr(self, "_arc3_audit_seen", None) != s:
        self._arc3_audit_seen = s
        self._arc3_audit_base = self.action_count if getattr(self, "_arc3_audit_base", None) is not None else 0
    due = self.action_count - self._arc3_audit_base >= _ARC3_AUDIT_EVERY
    if due and not getattr(self, "_arc3_audit_due", False):
        self._arc3_audits_due = getattr(self, "_arc3_audits_due", 0) + 1
        print(f"synesthesia: strategy audit due at action {{self.action_count}} (audit {{self._arc3_audits_due}}, "
              f"every {{_ARC3_AUDIT_EVERY}} actions)", flush=True)
    self._arc3_audit_due = due
    return due


_arc3_solver._HarnessGameSession._should_audit_strategy = _arc3_should_audit_strategy
'''
    code += ("print(f\"synesthesia: restoration settings: per_game_s={bm.solver.max_runtime_s_per_game} "
             "concurrency={bm.solver.concurrency} max_actions={bm.solver.max_actions_per_game} "
             f"audit_every_actions={audit_every}\", flush=True)\n")
    c10 = apply_edits(cells[10][1], [(RESTORE_ANCHOR, RESTORE_ANCHOR + code, 1)], "cell 10 (restore)")
    return cells[:10] + [(cells[10][0], c10)] + cells[11:]


def passes_cells(cells: list, passes: int) -> list:
    """Local scale test (builder --passes): play every game `passes` times in one run, so 25 public games stand in for
    the hidden run's 110 under the same clock. Applied on commit runs only: a scored rerun keeps the pickled single
    pass (an n_passes set outside that guard zeroed two submissions in September, findings 113)."""
    code = (f"\n# ---- local scale test (builder --passes {int(passes)}): commit runs only ----\n"
            "if run_as_submission:\n"
            "    print(\"synesthesia: --passes ignored on a scored rerun (each game is played once)\", flush=True)\n"
            "else:\n"
            f"    bm.n_passes = {int(passes)}\n"
            "    print(f\"synesthesia: scale test: {len(bm.games)} games x {bm.n_passes} passes\", flush=True)\n")
    c10 = apply_edits(cells[10][1], [(RESTORE_ANCHOR, RESTORE_ANCHOR + code, 1)], "cell 10 (passes)")
    return cells[:10] + [(cells[10][0], c10)] + cells[11:]


def arm_differences(title: str, kernel_id: str, harness_dataset: str, env: dict) -> str:
    lines = [f"\nThis folder is an ARM, not the anchor notebook ({KERNEL_ID}); it differs from the anchor only in:",
             f"- kernel id {kernel_id}, title {title!r} (kernel-metadata.json; the About heading names the arm).",
             f"- the first line of the log: {arm_banner(title, env)!r} (BOOT cell)."]
    if harness_dataset != HARNESS_DATASET:
        lines.append(f"- harness dataset {harness_dataset} (anchor: {HARNESS_DATASET}): attached, checked by BOOT, read "
                     f"by cell 2, first in cell 5's DATASET_SOURCES.")
    lines.append(f"- cell 2: ARM_NAME / ARM_KERNEL / ARM_HARNESS_DATASET / ARM_SWITCHES "
                 f"({' '.join(f'{k}={v}' for k, v in env.items()) or 'none'}) added to the environment, which "
                 f"prints each as 'synesthesia: env K=V'.")
    lines.append("- cell 11: RUN_CONFIG.json gains \"arm\": title, kernel id, harness dataset and each switch's value "
                 "as the run's environment has it.")
    return "\n".join(lines) + "\n"


NATIVE_ENV = {"ARM_B_STUDENT_TOWER": "0", "ARM_LIMIT_MM": '{"image":143,"video":0}',
              # the multimodal processor cache is OFF for every run that sends pixels: the mm-cache race
              # (vllm#38551 family; first recorded 2026-09-03 in reasoner_doubter_findings, one mm_hash failing
              # forever; required by the 10-03 images arm; MISSING from the native arm 11-04..11-07, which froze one
              # game on each of r5s/r5x1/r5x2). ARM_EXTRA_VLLM_ARGS is split with shlex onto the serve line.
              "ARM_EXTRA_VLLM_ARGS": "--mm-processor-cache-gb 0"}


def native_cells(cells: list) -> list:
    """--board-native: the edits the hand-built Board Native notebook (10-28) carried, applied by the generator.
    The arm block's comment says what is redefined; cell 10 expects the server to accept image:143 instead of
    refusing images; cell 11's evidence gate counts native image_url parts at 1024 tokens and refuses any
    image_embeds part (a run with the student's parts is not the native arm)."""
    cells = list(cells)
    cells[2] = (cells[2][0], apply_edits(cells[2][1], [(
        "# The switches are set on top of the environment above; none of them redefines one of its values.\n",
        "# The switches are set on top of the environment above; this arm REDEFINES two of its values on purpose\n"
        "# (ARM_B_STUDENT_TOWER, ARM_LIMIT_MM): the native tower replaces the student.\n", 1)], "cell 2 (native)"))
    cells[10] = (cells[10][0], apply_edits(cells[10][1], [
        ('      f"(unused: the board-tower branch never renders a PNG)", flush=True)',
         '      f"(board channel NATIVE: the PNG path renders at this upscale; the student is loaded only for its '
         'self-check)", flush=True)', 1),
        ('    if _lim.get("image") != 0:\n'
         '        raise RuntimeError(f"--limit-mm-per-prompt is {_lim}, not image:0 -- the native tower is "\n'
         '                           f"RESIDENT and a silent fallback to the pixel path would be possible")',
         '    if _lim.get("image") != 143:\n'
         '        raise RuntimeError(f"board channel NATIVE: --limit-mm-per-prompt is {_lim}, not image:143 -- the "\n'
         '                           f"native tower must be RESIDENT and accept the whole board history per prompt")', 1),
    ], "cell 10 (native)"))
    cells[11] = (cells[11][0], apply_edits(cells[11][1], [
        ("            _n = 0\n            if _bp.is_file():\n",
         "            _n = 0\n            _ne = 0\n            if _bp.is_file():\n", 1),
        ('                    if _r.get("type") == "image_embeds" and _r.get("n_tokens") == 1024:\n'
         '                        _n += 1\n',
         '                    if _r.get("type") == "image_url" and _r.get("n_tokens") == 1024:\n'
         '                        _n += 1\n'
         '                    elif _r.get("type") == "image_embeds":\n'
         '                        _ne += 1\n', 1),
        ('            print(f"synesthesia: evidence gate: {_n} student image_embeds parts at 1024 tokens", flush=True)\n'
         '            if _n == 0:\n'
         '                raise RuntimeError("evidence gate FAILED: no board-tower image_embeds part was ever sent "\n'
         '                                   "-- this commit run proves nothing and must not be submitted")',
         '            print(f"synesthesia: evidence gate (board channel NATIVE): {_n} native image_url parts at 1024 "\n'
         '                  f"tokens, {_ne} image_embeds parts (must be >=1 and 0)", flush=True)\n'
         '            if _n == 0 or _ne != 0:\n'
         '                raise RuntimeError(f"board channel NATIVE: evidence gate FAILED: {_n} native parts at 1024 tokens, "\n'
         '                                   f"{_ne} image_embeds parts -- this run is not the NATIVE arm")', 1),
    ], "cell 11 (native)"))
    return cells


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", help=f"the staged notebook folder (default, the anchor's: {DEFAULT_OUT.relative_to(REPO)}; "
                                  f"an arm must name its own)")
    ap.add_argument("--commit", default="HEAD", help="the harness is taken from the last commit touching harness/ at or before this")
    ap.add_argument("--dataset-dir", help=f"where the harness dataset folder is built (default {DATASET_ROOT}/<slug>)")
    ap.add_argument("--max-runtime-s", type=int, default=9300)
    ap.add_argument("--dataset-slug", default=HARNESS_DATASET, help="the harness dataset the notebook attaches and reads")
    ap.add_argument("--kernel-id", default=KERNEL_ID)
    ap.add_argument("--title", default=TITLE, help="must resolve to the kernel id's slug, as Kaggle derives it")
    ap.add_argument("--model-source", default=MODEL_SOURCE,
                    help="the Kaggle Model the notebook attaches and checks (owner/model/Framework/instance/version); "
                         "the harness reads it only through ARM_MODEL_DIR, which the arm must also set with --env")
    ap.add_argument("--tower-dataset", default=TOWER_DATASET, help="the board-tower dataset (student + its code)")
    ap.add_argument("--tower-ckpt", default=TOWER_CKPT, help="the student checkpoint, relative to the tower dataset")
    ap.add_argument("--tower-ckpt-sha", default=TOWER_CKPT_SHA, help="its sha256; the notebook refuses any other bytes")
    ap.add_argument("--tower-npos", type=int, default=TOWER_NPOS, help="its tokens per board (256 at px8, 1024 at px16)")
    ap.add_argument("--per-game-none", action="store_true", help="restoration: no per-game clock (max_runtime_s_per_game=None)")
    ap.add_argument("--concurrency", type=int, default=None, help="restoration: games played at once (anchor: pickled 14)")
    ap.add_argument("--passes", type=int, default=None, help="local scale test: play every game N times in one commit run (a scored rerun keeps 1); never for a notebook that gets submitted")
    ap.add_argument("--max-actions", type=int, default=None, help="restoration: per-game action cap (anchor: None)")
    ap.add_argument("--audit-every-actions", type=int, default=None, help="restoration: action-triggered strategy audit")
    ap.add_argument("--pool-clock", action="store_true",
                    help="harness pool clock: per-game time = fair share of the remaining slot-time (needs a harness "
                         "commit with solver._pool_take_budget)")
    ap.add_argument("--pool-park", action="store_true",
                    help="with --pool-clock: park stalled games and resume them once every game has had a slot")
    ap.add_argument("--pool-stall", type=int, default=None, help="with --pool-clock: hard stall cut (smoke tests)")
    ap.add_argument("--pool-soft-stall", type=int, default=None, help="with --pool-clock: soft stall cut (smoke tests)")
    ap.add_argument("--pool-stall-seconds", type=float, default=None,
                    help="with --pool-clock: time-based stall cut, seconds: while other games wait, a game over its fair "
                         "share hands its slot back after this long without a level clear (solver.pool_stall_seconds; "
                         "needs a harness commit with the time-based stop)")
    ap.add_argument("--boot-clock", action="store_true",
                    help="scored-run clocks (per-game clock fit; pool end with --pool-clock) count from the machine's "
                         "start (/proc/uptime) instead of the notebook's: on scored reruns the notebook starts ~40-50 "
                         "min late and that time counts against the 9 h limit (forum 753843)")
    ap.add_argument("--pool-min-share", type=float, default=None,
                    help="with --pool-clock: reserve, seconds per unstarted game: once the slot-time left cannot give "
                         "each unstarted game this much, every game over its fair share hands its slot back at its "
                         "next action boundary (solver.pool_min_share_s)")
    ap.add_argument("--env", action="append", default=[], metavar="KEY=VAL",
                    help="a harness switch for this arm (repeatable)")
    ap.add_argument("--extra-dataset", action="append", default=[], metavar="OWNER/SLUG",
                    help="attach another dataset (repeatable), e.g. a DFlash drafter read through --env ARM_DFLASH_MODEL")
    ap.add_argument("--board-native", action="store_true",
                    help="board channel NATIVE: the model's own vision tower encodes the 16 px/cell board PNG "
                         "(ARM_B_STUDENT_TOWER=0, ARM_LIMIT_MM image:143 so the whole board history fits one prompt); "
                         "the student is loaded only for its self-check. The na1c-na3c arm (10-28), until now a "
                         "hand-edited staged notebook; cell 10's server-flag check and cell 11's evidence gate are "
                         "rewritten to expect image_url parts and refuse image_embeds")
    ap.add_argument("--allow-unread-env", action="store_true",
                    help="build even if an --env key appears nowhere in the harness code (builder tests only)")
    a = ap.parse_args()

    for flag, seconds in (("--pool-stall-seconds", a.pool_stall_seconds), ("--pool-min-share", a.pool_min_share)):
        if seconds is not None and not (math.isfinite(seconds) and seconds > 0):
            raise SystemExit(f"{flag} {seconds}: expected a positive number of seconds")
    for flag, ref in (("--kernel-id", a.kernel_id), ("--dataset-slug", a.dataset_slug)):
        if not REF.fullmatch(ref):
            raise SystemExit(f"{flag} {ref!r}: expected owner/slug")
    if kaggle_slug(a.title) != a.kernel_id.split("/")[1]:
        raise SystemExit(f"--title {a.title!r} resolves to the slug {kaggle_slug(a.title)!r}, not the kernel id's "
                         f"{a.kernel_id.split('/')[1]!r}; `kaggle kernels push` warns of 'surprising behavior' then")
    env = parse_env(a.env)
    model_parts = tuple(a.model_source.split("/"))
    if len(model_parts) != 5 or not all(model_parts):
        raise SystemExit(f"--model-source {a.model_source!r}: expected owner/model/Framework/instance/version")
    if a.model_source != MODEL_SOURCE and "ARM_MODEL_DIR" not in env:
        raise SystemExit(f"--model-source {a.model_source!r} is not the anchor's: the harness finds the model only "
                         f"through ARM_MODEL_DIR, so the arm must also pass --env ARM_MODEL_DIR=<its mount path>")
    tower = (a.tower_dataset, a.tower_ckpt, a.tower_ckpt_sha, a.tower_npos)
    tower_swapped = tower != (TOWER_DATASET, TOWER_CKPT, TOWER_CKPT_SHA, TOWER_NPOS)
    if tower_swapped and not REF.fullmatch(a.tower_dataset):
        raise SystemExit(f"--tower-dataset {a.tower_dataset!r}: expected owner/slug")
    if a.board_native:
        # the one arm that redefines two base-environment values on purpose; parse_env refuses them by design, so
        # they are merged here, after the user's own switches were checked
        env = dict(sorted({**env, **NATIVE_ENV}.items()))
    restore = (a.per_game_none, a.concurrency, a.max_actions, a.audit_every_actions)
    restoring = restore != (False, None, None, None)
    is_arm = (bool(env) or (a.kernel_id, a.title, a.dataset_slug) != (KERNEL_ID, TITLE, HARNESS_DATASET)
              or a.model_source != MODEL_SOURCE or tower_swapped or restoring or a.pool_clock or a.board_native)
    out = pathlib.Path(a.out) if a.out else DEFAULT_OUT
    if is_arm and a.kernel_id == KERNEL_ID:
        raise SystemExit(f"an arm needs its own --kernel-id ({KERNEL_ID} is the anchor's kernel)")
    if is_arm and out.resolve() == DEFAULT_OUT.resolve():
        raise SystemExit(f"an arm needs its own --out ({DEFAULT_OUT.relative_to(REPO)} is the anchor's staged folder)")
    dataset_dir = pathlib.Path(a.dataset_dir) if a.dataset_dir else DATASET_ROOT / a.dataset_slug.split("/")[1]

    # the harness dataset is identified by the last commit that touched harness/, so unrelated commits do not
    # produce a new dataset version
    commit = git("log", "-1", "--format=%H", git("rev-parse", a.commit), "--", "harness/")
    if subprocess.run(["git", "-C", str(REPO), "merge-base", "--is-ancestor", V8_HARNESS_COMMIT, commit]).returncode:
        raise SystemExit(f"{commit[:12]} does not contain {V8_HARNESS_COMMIT} (v8's harness as code)")
    if is_arm and a.dataset_slug == HARNESS_DATASET:
        # one Kaggle dataset holds one commit at a time, and each notebook checks the commit it was built for
        staged = json.loads((DEFAULT_OUT / "synesthesia.ipynb").read_text())["cells"][2]["source"]
        anchor = re.search(r'EXPECT_HARNESS_COMMIT = "([0-9a-f]{40})"', staged)
        if anchor is None or anchor.group(1) != commit:
            raise SystemExit(f"harness {commit[:12]} is not the anchor's ({anchor.group(1)[:12] if anchor else '?'}), "
                             f"so this arm needs its own --dataset-slug")
    write_dataset(commit, dataset_dir, a.dataset_slug)
    unread = unread_env(env, dataset_dir)
    if unread:
        msg = (f"--env {', '.join(unread)}: no harness code at {commit[:12]} mentions it, so the arm would run as the "
               f"control (pick the commit that carries the switch with --commit)")
        if not a.allow_unread_env:
            raise SystemExit(msg)
        print(f"WARNING (--allow-unread-env): {msg}", file=sys.stderr)
    switch_check = check_arm_env(env, dataset_dir) if is_arm else False
    if is_arm and not switch_check:
        print(f"note: harness {commit[:12]} has no validate_syn_env; the arm notebook gets no switch check "
              f"(the unread-key check above still applied)", file=sys.stderr)

    src = [("".join(c["source"]) if isinstance(c["source"], list) else c["source"])
           for c in json.loads(V8_NOTEBOOK.read_text())["cells"]]
    for i, want in V8_CELL_SHA.items():
        got = hashlib.sha256(src[i].encode()).hexdigest()
        if want is not None and got != want:
            raise SystemExit(f"v8 cell {i} changed: {got} != {want}")

    owner, slug = a.dataset_slug.split("/")
    for ref in a.extra_dataset:
        if not REF.fullmatch(ref):
            raise SystemExit(f"--extra-dataset {ref!r}: expected owner/slug")
    datasets = [a.dataset_slug, a.tower_dataset, RUNTIME_DATASET] + list(a.extra_dataset)
    cells = [("markdown", ABOUT),
             ("code", boot_cell(datasets, [a.model_source], [COMPETITION])),
             ("code", apply_edits(CELL_HARNESS, [(
                 '_dataset_dir("codywhatleymd", "arc3-synesthesia-harness", "taaf-kaggle-bundle.json")',
                 f'_dataset_dir("{owner}", "{slug}", "taaf-kaggle-bundle.json")', 1),
                 ('MODEL_PARTS = ("codywhatleymd", "arc3-flashnext-nvfp4-ours-v22", "PyTorch", "v22", "3")',
                  "MODEL_PARTS = (" + ", ".join(json.dumps(x) for x in model_parts) + ")", 1)], "cell 2")
                      .replace("__HARNESS_COMMIT__", commit)
                      .replace("__MAX_RUNTIME_S__", str(a.max_runtime_s))),
             ("code", src[3]), ("code", fix_wheelhouse_cell(src[4])),
             ("code", apply_edits(src[5], cell5_edits(a.dataset_slug), "cell 5")),
             ("code", src[6]), ("code", src[7]), ("code", src[8]), ("code", src[9]),
             ("code", rewrite_cell10(src[10])),
             ("code", rewrite_cell11(src[11]))]
    if (dataset_dir / "arc3_tools" / "patch_ple_inc.py").is_file():     # 2e1af90+: the harness also ships the PLE/INC patch
        cells = cells[:2] + [(cells[2][0], apply_edits(cells[2][1], [('''if not (HARNESS_DIR / "arc3_tools" / "patch_kv_copy_chunked.py").is_file():
    raise RuntimeError("arc3_tools/patch_kv_copy_chunked.py is missing from the harness")
''', '''for _tool in ("patch_kv_copy_chunked.py", "patch_ple_inc.py"):
    if not (HARNESS_DIR / "arc3_tools" / _tool).is_file():
        raise RuntimeError(f"arc3_tools/{_tool} is missing from the harness")
''', 1)], "cell 2 (tools)"))] + cells[3:]
    if tower_swapped:
        cells = tower_cells(cells, *tower)
    if restoring:
        cells = restore_cells(cells, *restore)
    if a.passes is not None:
        if a.passes < 1:
            raise SystemExit("--passes must be >= 1")
        cells = passes_cells(cells, a.passes)
    if (a.pool_park or a.pool_stall is not None or a.pool_soft_stall is not None or a.pool_stall_seconds is not None
            or a.pool_min_share is not None) and not a.pool_clock:
        raise SystemExit("--pool-park / --pool-stall / --pool-soft-stall / --pool-stall-seconds / --pool-min-share "
                         "need --pool-clock")
    if a.pool_clock:
        cells = pool_clock_cells(cells, dataset_dir, a.pool_park, a.pool_stall, a.pool_soft_stall,
                                 a.pool_stall_seconds, a.pool_min_share)
    if a.boot_clock:
        cells = boot_clock_cells(cells)
    if is_arm:
        cells = arm_cells(cells, a.title, a.kernel_id, a.dataset_slug, env, switch_check)
    if a.board_native:
        cells = native_cells(cells)
    leftover = [i for i, (_, s) in enumerate(cells) if "ARM B" in s or "arm B" in s or "lordhansolo" in s]
    if leftover:
        raise SystemExit(f"cells {leftover} still mention ARM B / lordhansolo")
    nb = {"cells": [{"cell_type": t, "metadata": {}, "source": s, "id": f"cell-{i}",
                     **({"execution_count": None, "outputs": []} if t == "code" else {})}
                    for i, (t, s) in enumerate(cells)],
          "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                       "language_info": {"name": "python"}},
          "nbformat": 4, "nbformat_minor": 5}
    out.mkdir(parents=True, exist_ok=True)
    (out / "synesthesia.ipynb").write_text(json.dumps(nb, indent=1) + "\n")
    (out / "kernel-metadata.json").write_text(json.dumps({
        "id": a.kernel_id, "title": a.title, "code_file": "synesthesia.ipynb", "language": "python",
        "kernel_type": "notebook", "is_private": True, "enable_gpu": True, "enable_tpu": False,
        "enable_internet": False, "keywords": [],
        "dataset_sources": datasets, "kernel_sources": [], "competition_sources": [COMPETITION],
        "model_sources": [a.model_source], "machine_shape": "NvidiaRtxPro6000",
        # Explicit: the runtime is built for Python 3.13 (Kaggle's current image). Left unset, a push could inherit an
        # older version's pin (v34, the investigator's editor draft, pinned a CPU image).
        "docker_image_pinning_type": "latest",
    }, indent=1) + "\n")
    (out / "DIFFERENCES_FROM_V8.txt").write_text(
        DIFFERENCES + (arm_differences(a.title, a.kernel_id, a.dataset_slug, env) if is_arm else "")
        + (f"- Kaggle Model {a.model_source} (anchor: {MODEL_SOURCE}): attached instead of the anchor's, checked by "
           f"BOOT and cell 2 (MODEL_PARTS); the harness reads it through ARM_MODEL_DIR (an --env switch above).\n"
           if a.model_source != MODEL_SOURCE else "")
        + (f"- board-tower student {a.tower_dataset}:{a.tower_ckpt} (sha256 {a.tower_ckpt_sha[:16]}..., {a.tower_npos} "
           f"tokens/board; anchor: {TOWER_DATASET}:{TOWER_CKPT}, {TOWER_NPOS}): attached instead of the anchor's, checked "
           f"by BOOT and cell 2 (sha256); ARM_B_EXPECT_NPOS, the estimator self-tests (cells 2, 10) and the evidence gate "
           f"(cell 11) count {a.tower_npos} tokens.\n" if tower_swapped else ""))
    print(f"wrote {out}/synesthesia.ipynb ({len(cells)} cells), kernel-metadata.json; harness dataset "
          f"{dataset_dir} @ {commit[:12]}; max_runtime_s={a.max_runtime_s}")
    if is_arm:
        print(f"{arm_banner(a.title, env)} | kernel {a.kernel_id} | harness dataset {a.dataset_slug}")


if __name__ == "__main__":
    main()
