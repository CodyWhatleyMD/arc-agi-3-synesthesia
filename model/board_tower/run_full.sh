#!/usr/bin/env bash
# The full S2c run: enumerate -> record every target on the 5090 inside the serving image -> train the student
# -> export a sanity part. Everything nice 19, 2 threads, docker CPU cap, load-gated before each step.
#
# Sizes (census 2026-10-03: 33,828 unique boards in runs/, 27 games; a full (4096,2560) bf16 target is 21 MB, so
# ALL of them would be 710 GB on a 410 GB-free USB HDD): per-game caps, stratified by level, and K=1024 random rows
# per TRAIN board (the loss is an unbiased estimate of the full-board loss; eval boards are always full):
#   train: 22 games (20 public + gr01/so12 custom-in-runs) x PER_GAME=400  -> <= 8,800 boards x 5.2 MB = 46 GB
#   eval : 5 held-out public games x EVAL_PER_GAME=100 (full boards)        ->      500 boards x 21 MB  = 10.5 GB
#   + the initial frame of every level of the 29 custom games (train, ~120 boards)
# Tower rate from the smoke decides the wall time (see run_full.log); the student trains for TRAIN_MINUTES.
# Knobs: PER_GAME EVAL_PER_GAME TRAIN_CELLS SHARD_BOARDS TRAIN_MINUTES DIM DEPTH HEADS BATCH LR (env).
set -uo pipefail
here=$(cd "$(dirname "$0")" && pwd)
source "$here/env.sh"
WT=$(cd "$here/../.." && pwd)
TARGETS=${TARGETS:-${BOARD_TOWER_TARGETS:-/media/ignaz/claude-extra/board_tower/targets}}
CKPT=${CKPT:-${BOARD_TOWER_CKPT_DIR:-/media/ignaz/claude-extra/board_tower/ckpt}}
PER_GAME=${PER_GAME:-400}; EVAL_PER_GAME=${EVAL_PER_GAME:-100}; TRAIN_CELLS=${TRAIN_CELLS:-1024}; SHARD_BOARDS=${SHARD_BOARDS:-32}
TRAIN_MINUTES=${TRAIN_MINUTES:-180}; DIM=${DIM:-384}; DEPTH=${DEPTH:-8}; HEADS=${HEADS:-6}; BATCH=${BATCH:-8}; LR=${LR:-3e-4}
PY=$BOARD_TOWER_PY
log() { echo "$(date '+%F %T') $*"; }
cd "$(mktemp -d "${TMPDIR:-/tmp}/bt_full_cwd.XXXXXX")"
log "run_full start: worktree $WT ($(git -C "$WT" rev-parse --short HEAD)), targets $TARGETS, ckpt $CKPT, "\
"PER_GAME=$PER_GAME EVAL_PER_GAME=$EVAL_PER_GAME TRAIN_CELLS=$TRAIN_CELLS TRAIN_MINUTES=$TRAIN_MINUTES dim/depth/heads $DIM/$DEPTH/$HEADS"
log "free space: $(df -h "$(dirname "$TARGETS")" | tail -1)"

# 1. enumerate (host, .mlvenv: events + custom games)
wait_load
if [ ! -f "$TARGETS/boards.json" ]; then
  log "enumerate"
  nice -n 19 "$PY" "$here/make_targets.py" enumerate --out "$TARGETS" --per-game "$PER_GAME" --eval-per-game "$EVAL_PER_GAME" || { log "enumerate FAILED"; exit 1; }
else
  log "enumerate: boards.json exists, keeping it"
fi
"$PY" -c "import json; m=json.load(open('$TARGETS/boards.json')); print('boards', m['n_boards'], 'train', m['n_train'], 'eval', m['n_eval'], 'holdout', m['holdout_games'], 'custom skipped', m['custom_games_skipped'])"

# 2. record (docker, GPU 0 = the 5090; resumable)
wait_load
log "record (docker, GPU 0)"
TARGETS="$TARGETS" GPU=0 CPUS=${CPUS:-4} NAME=board_tower_record_full bash "$here/run_record_docker.sh" \
  --batch 1 --shard-boards "$SHARD_BOARDS" --train-cells "$TRAIN_CELLS" --resume || { log "record FAILED"; exit 1; }
"$PY" -c "import json; m=json.load(open('$TARGETS/manifest.json')); r=m['recorder']; print('recorded', len(m['boards']), 'boards in', len(m['shards']), 'shards;', round(sum(s['bytes'] for s in m['shards'])/2**30,1), 'GiB; tower rate', r.get('rate_boards_per_s_tower'), 'boards/s; hf', r.get('hf_crosscheck',{}).get('cases'))"

# 3. train (host, the 5090)
wait_load
log "train ($TRAIN_MINUTES min)"
nice -n 19 "$PY" "$here/train.py" --targets "$TARGETS" --out "$CKPT" --max-minutes "$TRAIN_MINUTES" \
  --dim "$DIM" --depth "$DEPTH" --heads "$HEADS" --batch "$BATCH" --lr "$LR" --eval-every 500 --eval-boards 64 || { log "train FAILED"; exit 1; }

# 4. export sanity
wait_load
log "export sanity"
BOARD_TOWER_CKPT="$CKPT/best.pt" nice -n 19 "$PY" "$here/export_embeds.py" --ckpt "$CKPT/best.pt" --solid 8
log "run_full done. Next: scripts/synth_tokens_perception.py --arms png,synth,text,tower with BOARD_TOWER_CKPT=$CKPT/best.pt (needs the mm-embeds server)"
