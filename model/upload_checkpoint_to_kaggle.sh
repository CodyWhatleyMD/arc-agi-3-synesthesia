#!/usr/bin/env bash
# Our Flash-Next NVFP4 checkpoint -> private Kaggle dataset (09-30).
#   1. split the BF16 PLE table into table-only shards (repack_split_table.py; byte-exact; idempotent)
#   2. hard-link everything EXCEPT table-* into an upload folder (same filesystem: no copy)
#   3. kaggle datasets create --dir-mode zip   (later versions: kaggle datasets version)
#      CLI, not the MCP: the MCP has no folder/zip dataset-versioning tool (upload_dataset_file is per file).
# The table is served on Kaggle from the quantized sidecar dataset (arc3-flashnext-ple-sidecar); the checkpoint's
# own copy stays local. Nothing here touches the calibration run's inputs.
set -euo pipefail
CK=${1:-/media/ignaz/claude-extra/Qwen3.8-Flash-Next-NVFP4-ours}
SLUG=${SLUG:-arc3-flashnext-nvfp4-ours}
UP=${UP:-/media/ignaz/claude-extra/kaggle_ds_${SLUG}}
[ -f "$CK/model.safetensors.index.json" ] || { echo "no index in $CK -- not a finished checkpoint"; exit 1; }
[ -f "$CK/config.json" ] || { echo "no config.json in $CK"; exit 1; }
echo "[1/3] repack: split the table out"
/home/ignaz/quant-venv/bin/python /home/ignaz/github/arc-prize-2026/scripts/flashnext_quant/repack_split_table.py "$CK"
echo "[2/3] upload folder (hard links, no table shards)"
rm -rf "${UP:?}"; mkdir -p "$UP"
for f in "$CK"/*; do b=$(basename "$f"); case "$b" in table-*|table.safetensors.index.json|*.log) continue;; esac; ln "$f" "$UP/$b"; done
cat > "$UP/dataset-metadata.json" <<JSON
{"title": "arc3 flashnext nvfp4 ours", "id": "codywhatleymd/${SLUG}", "licenses": [{"name": "other"}]}
JSON
echo "  files: $(ls "$UP" | wc -l) | size: $(du -shL "$UP" | cut -f1) | table shards left behind: $(ls "$CK"/table-*.safetensors 2>/dev/null | wc -l)"
python3 - "$UP" <<'PY'
import json,os,sys
d=sys.argv[1]; idx=json.load(open(f"{d}/model.safetensors.index.json"))
missing=[f for f in set(idx["weight_map"].values()) if not os.path.exists(f"{d}/{f}")]
tab=[k for k in idx["weight_map"] if "ngram_embedding" in k]
print(f"  index check: {len(idx['weight_map'])} tensors, {len(set(idx['weight_map'].values()))} files, missing files {len(missing)}, table entries {len(tab)}")
assert not missing and not tab, "index inconsistent with the upload folder"
PY
echo "[3/3] push"
cd "$UP"
if kaggle datasets status "codywhatleymd/${SLUG}" >/dev/null 2>&1; then
  kaggle datasets version -p . --dir-mode zip -m "checkpoint $(date +%F_%H%M)"
else
  kaggle datasets create -p . --dir-mode zip
fi
echo "UPLOAD SUBMITTED $(date +%H:%M) -> https://www.kaggle.com/datasets/codywhatleymd/${SLUG}"
