#!/usr/bin/env bash
# Phase 2 of make_targets.py (record) inside the serving image on ONE GPU (default 0 = the 5090; GPU 1 is the
# measurement's). Same mounts as notebooks_duck/synth_tokens/run_s0_docker.sh plus the target root at /targets.
# Runs as the invoking user, under `nice -n 19` INSIDE the container (the docker client's nice does not reach
# the container), with a CPU cap (--cpus) and 2 torch threads, so it cannot disturb a host-bound server.
#   TARGETS=<dir> GPU=0 CPUS=4 scripts/board_tower/run_record_docker.sh [record args: --max 20 --batch 2 ...]
set -euo pipefail
CK=${CK:-/media/ignaz/claude-extra/Qwen3.8-Flash-Next-NVFP4-ours}
REPO=${ARC_ENGINE_ROOT:-/home/ignaz/github/arc-prize-2026}
WT=${WT:-$(cd "$(dirname "$0")/../.." && pwd)}
TARGETS=${TARGETS:-${BOARD_TOWER_TARGETS:-/media/ignaz/claude-extra/board_tower/targets}}
GPU=${GPU:-0}
CPUS=${CPUS:-4}
SCRATCH=${SCRATCH:-$TARGETS/../docker_scratch}
IMG=${IMG:-vllm/vllm-openai:qwen38-flash-next}
NAME=${NAME:-board_tower_record}
IMAGE_ID=$(docker images --no-trunc -q "$IMG")
GIT_SHA=$(git -C "$WT" rev-parse HEAD)
mkdir -p "$SCRATCH/home" "$SCRATCH/triton" "$TARGETS"
exec docker run --rm --gpus "\"device=$GPU\"" --ipc=host --cpus "$CPUS" --name "$NAME" \
  --user "$(id -u):$(id -g)" -e HOME=/scratch/home -e TRITON_CACHE_DIR=/scratch/triton \
  -v "$CK":/model:ro -v "$REPO":/repo:ro -v "$WT":/work -v "$TARGETS":/targets -v "$SCRATCH":/scratch \
  -e ARC_ENGINE_ROOT=/repo -e S0_IMAGE_ID="$IMAGE_ID" -e S0_GIT_SHA="$GIT_SHA" -e PYTHONPATH=/work \
  -e VLLM_LOGGING_LEVEL=WARNING -e OMP_NUM_THREADS=2 -e BOARD_TOWER_THREADS=2 \
  --entrypoint nice "$IMG" -n 19 python3 /work/scripts/board_tower/make_targets.py record \
  --out /targets --ckpt /model "$@"
