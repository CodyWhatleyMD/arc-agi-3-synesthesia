#!/usr/bin/env bash
# Dihedral-augmentation run (2026-10-08): augment (host) -> record the added boards (docker, --resume, ALL token rows)
# -> train. GPU: the RTX PRO 6000, selected by UUID everywhere (docker --gpus device=<uuid>, CUDA_VISIBLE_DEVICES=<uuid>),
# so the CUDA_DEVICE_ORDER trap (index 1 was the 5090 under FASTEST_FIRST) cannot bite. Verify the bus id with
#   nvidia-smi --query-compute-apps=pid,gpu_bus_id --format=csv      (the 6000 is 00000000:04:00.0)
# Everything is logged under $CKPT: launch.txt (command line, env, git sha), run_dih.log (this script + both steps):
#   mkdir -p $CKPT && nohup bash scripts/board_tower/run_dih.sh > $CKPT/run_dih.log 2>&1 &
# Env knobs: SRC TARGETS CKPT GPU_UUID TRAIN_MINUTES CPUS SHARD_BOARDS LOADER_THREADS SCRATCH (defaults below).
set -uo pipefail
here=$(cd "$(dirname "$0")" && pwd)
WT=$(cd "$here/../.." && pwd)
PY=${BOARD_TOWER_PY:-/home/ignaz/github/arc-prize-2026/.mlvenv/bin/python}
GPU_UUID=${GPU_UUID:-GPU-f47a00d6-9881-7ef5-997a-0f86d6345f56}     # nvidia-smi -L: the RTX PRO 6000 Blackwell Max-Q, bus 04:00.0
SRC=${SRC:-/media/ignaz/claude-extra/board_tower/targets_px16}
TARGETS=${TARGETS:-/media/ignaz/480GB Kingston/board_tower/targets_px16_dih}
CKPT=${CKPT:-/media/ignaz/claude-extra/board_tower/ckpt_px16_dih}
SCRATCH=${SCRATCH:-/media/ignaz/claude-extra/board_tower/docker_scratch}     # the record container's HOME + triton cache (warm)
TRAIN_MINUTES=${TRAIN_MINUTES:-180}; CPUS=${CPUS:-4}; LOADER_THREADS=${LOADER_THREADS:-4}
PX=${PX:-16}                           # px per cell of the target set (16 -> 1024 tokens/board, 8 -> 256); must match SRC
export CK=${CK:-/media/ignaz/claude-extra/Qwen3.8-Flash-Next-NVFP4-ours}   # teacher checkpoint for the record step (run_record_docker.sh)
SHARD_BOARDS=${SHARD_BOARDS:-256}      # same boards, same rows: 8x fewer files than 32 and 8x fewer rewrites of the growing manifest
export CUDA_DEVICE_ORDER=PCI_BUS_ID CUDA_VISIBLE_DEVICES=$GPU_UUID OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 BOARD_TOWER_THREADS=2
mkdir -p "$CKPT"
log() { echo "$(date '+%F %T') run_dih: $*"; }
{ echo "launched $(date '+%F %T') pid $$ on $(hostname) from $PWD"; echo "cmd: $0 $*"; echo "git: $(git -C "$WT" rev-parse HEAD) ($WT)"
  echo "SRC=$SRC"; echo "TARGETS=$TARGETS"; echo "CKPT=$CKPT"; echo "GPU_UUID=$GPU_UUID"; echo "SCRATCH=$SCRATCH"
  echo "TRAIN_MINUTES=$TRAIN_MINUTES CPUS=$CPUS SHARD_BOARDS=$SHARD_BOARDS LOADER_THREADS=$LOADER_THREADS PX=$PX CK=$CK"
  echo "record: run_record_docker.sh --batch 1 --shard-boards $SHARD_BOARDS --px-per-cell $PX --resume   (ALL rows per board: no --train-cells)"
  echo "train:  train.py --targets \$TARGETS --out \$CKPT --max-minutes $TRAIN_MINUTES --dim 384 --depth 8 --heads 6 --batch 8 --lr 3e-4 --eval-every 500 --eval-boards 64 --allow-any-gpu --loader-threads $LOADER_THREADS"
} > "$CKPT/launch.txt"
cd "$(mktemp -d "${TMPDIR:-/tmp}/bt_dih_cwd.XXXXXX")"
log "start: $SRC -> $TARGETS; ckpt $CKPT; GPU $GPU_UUID; $TRAIN_MINUTES min; targets disk: $(df -h "$TARGETS" | tail -1)"

# 1. augment (host): skipped when the new root already has its boards.json
if [ ! -f "$TARGETS/boards.json" ]; then
  log "augment"
  nice -n 19 "$PY" "$here/make_targets.py" augment --src "$SRC" --out "$TARGETS" || { log "augment FAILED"; exit 1; }
else
  log "augment: $TARGETS/boards.json exists, keeping it"
fi

# 2. record the added boards (docker on the 6000; resumable; every token row of every board)
log "record (docker, GPU $GPU_UUID)"
TARGETS="$TARGETS" GPU="$GPU_UUID" CPUS="$CPUS" SCRATCH="$SCRATCH" NAME=board_tower_record_dih bash "$here/run_record_docker.sh" \
  --batch 1 --shard-boards "$SHARD_BOARDS" --px-per-cell "$PX" --resume || { log "record FAILED"; exit 1; }
"$PY" - "$TARGETS" <<'PYEOF'
import json, sys
m = json.load(open(sys.argv[1] + "/manifest.json")); r = m["recorder"]; a = m["augmentation"]
kinds = {}
for b in m["boards"]:
    kinds[b["kind"]] = kinds.get(b["kind"], 0) + 1
print("recorded", len(m["boards"]), "boards", kinds, "in", len(m["shards"]), "shards;", round(sum(s["bytes"] for s in m["shards"]) / 2**30, 1), "GiB;",
      "this run:", r.get("boards_recorded_this_run"), "boards, tower", r.get("rate_boards_per_s_tower"), "boards/s, wall", r.get("rate_boards_per_s_wall"),
      "boards/s; added by augment:", a["n_added"], "; hf cross-check:", r.get("hf_crosscheck", {}).get("cases"))
PYEOF

# 3. train on the 6000 (train.py refuses a non-5090 device without --allow-any-gpu; the UUID above is the pin)
log "train ($TRAIN_MINUTES min)"
nice -n 19 "$PY" "$here/train.py" --targets "$TARGETS" --out "$CKPT" --max-minutes "$TRAIN_MINUTES" \
  --dim 384 --depth 8 --heads 6 --batch 8 --lr 3e-4 --eval-every 500 --eval-boards 64 --allow-any-gpu \
  --loader-threads "$LOADER_THREADS" || { log "train FAILED"; exit 1; }
log "done: $CKPT/best.pt last.pt summary.json metrics.jsonl"
