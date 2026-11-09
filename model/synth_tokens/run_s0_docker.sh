#!/usr/bin/env bash
# S0 recorder inside the serving image, one GPU (default 0 = the 5090; GPU 1 belongs to the measurement).
# Mounts: checkpoint ro at /model; the main checkout ro at /repo (engine palette source + runs/ events,
# both git-ignored so a worktree lacks them); the worktree rw at /work (code + outputs); scratch for the
# 3 x 126 MB real-board token dumps. Runs as the invoking user so outputs are not root-owned.
set -euo pipefail
CK=${CK:-/media/ignaz/claude-extra/Qwen3.8-Flash-Next-NVFP4-ours}
REPO=${ARC_ENGINE_ROOT:-/home/ignaz/github/arc-prize-2026}
WT=${WT:-$(cd "$(dirname "$0")/../.." && pwd)}
GPU=${GPU:-0}
SCRATCH=${SCRATCH:-$WT/../s0_scratch}
IMG=${IMG:-vllm/vllm-openai:qwen38-flash-next}
IMAGE_ID=$(docker images --no-trunc -q "$IMG")
GIT_SHA=$(git -C "$WT" rev-parse HEAD)
mkdir -p "$SCRATCH/home" "$SCRATCH/triton"
BOARDS=${BOARDS:-"runs/opus55_docker/artifacts/vc33-5430563c_p0_events.jsonl:40 runs/opus55_docker/artifacts/ls20-9607627b_p0_events.jsonl:40 runs/opus55_docker/artifacts/ft09-0d8bbf25_p0_events.jsonl:4"}
BARGS=(); for b in $BOARDS; do BARGS+=(--board "$b"); done
exec docker run --rm --gpus "\"device=$GPU\"" --ipc=host --name s0_synth_tokens \
  --user "$(id -u):$(id -g)" -e HOME=/scratch/home -e TRITON_CACHE_DIR=/scratch/triton \
  -v "$CK":/model:ro -v "$REPO":/repo:ro -v "$WT":/work -v "$SCRATCH":/scratch \
  -e ARC_ENGINE_ROOT=/repo -e S0_IMAGE_ID="$IMAGE_ID" -e S0_GIT_SHA="$GIT_SHA" -e PYTHONPATH=/work \
  -e VLLM_LOGGING_LEVEL=WARNING \
  --entrypoint python3 "$IMG" /work/notebooks_duck/synth_tokens/s0_record_table.py \
  --ckpt /model --out-dir /work/notebooks_duck/synth_tokens --scratch /scratch "${BARGS[@]}" "$@"
