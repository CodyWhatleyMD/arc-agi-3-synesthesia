#!/usr/bin/env bash
# Board-tower vision at GAME level (plan S2c): four arms, one variable each, through the vendored Duck
# harness (notebooks_duck/ab_local.py) against the GCP twin's Flash-Next server over the IAP tunnel.
#
#   text   no board image (the incumbent)
#   png4   Duck's real PNG at  4 px/cell  ->   66 image tokens/board  (what Kaggle ships)
#   png32  Duck's real PNG at 32 px/cell  -> 4098 image tokens/board  (the REAL tower, token-matched)
#   tower  the distilled 27M student as image_embeds -> 4098 image tokens/board  (the arm under test)
#
# Budget is matched in ACTIONS (MAX_ACTIONS), not wall clock, so the comparison is perception and not
# throughput; wall clock is recorded and reported separately.
# ARMS=... selects arms (default all four, tower first so the arm under test is never the one that gets cut).
# Nothing in here is edited while it runs.
set -u
cd /home/ignaz/github/arc-prize-2026
ROOT=${ROOT:-runs/board_tower_play}
FROZEN=${FROZEN:?set FROZEN to the frozen board_tower module tree}
BASE=${BASE:-http://127.0.0.1:15307/v1}
CKPT=${CKPT:-/media/ignaz/claude-extra/board_tower/ckpt/best.pt}
GAMES=${GAMES:-vc33,lp85,ar25}
PASSES=${PASSES:-2}
CONC=${CONC:-6}
MAXACT=${MAXACT:-35}
PERGAME=${PERGAME:-1500}
TIMEOUT=${TIMEOUT:-240}
# Duck kills a game after this many actions with no level cleared. Blocks 1-2 ran the stock 120,
# which was irrelevant at a 22-action cap but would PRE-EMPT a 160-action cap and censor exactly
# the slow-clearing (held-out) runs the real-budget run exists to measure. Default here is
# MAXACT+1 so the ACTION CAP is the only stopping rule, identically in every arm.
DEADACT=${DEADACT:-$((MAXACT+1))}
CTX=${CTX:-32768}
mkdir -p "$ROOT"

common=(
  ARM=lownorm CTX_RESERVE=0 COLOUR_VOCAB=qwen
  GAMES="$GAMES" PASSES="$PASSES" CONCURRENCY="$CONC" MAX_ACTIONS="$MAXACT"
  PER_GAME_S="$PERGAME" GLOBAL_S=32400 ANALYZER_TIMEOUT_S="$TIMEOUT"
  DUCK_DEAD_GAME_ACTIONS="$DEADACT" DUCK_LEVEL_CAP=200
  LOCAL_ANALYZER_BASE_URL="$BASE" LOCAL_ANALYZER_MODEL_ID=flashnext
  LOCAL_ANALYZER_CONTEXT_WINDOW="$CTX" LOCAL_ANALYZER_PROVIDER=vllm LOCAL_ANALYZER_API_KEY=local
  ENV_DIR=/home/ignaz/environment_files DUCK_SRC=/home/ignaz/duck-harness
  # the student: GPU 1 (the idle RTX PRO 6000) under PCI order, 110 MB of weights. The SERVED model is
  # on the twin -- nothing of the measurement runs on a local card.
  CUDA_DEVICE_ORDER=PCI_BUS_ID CUDA_VISIBLE_DEVICES=1 BOARD_TOWER_ANY_GPU=1 BOARD_TOWER_DEVICE=cuda:0
  BOARD_TOWER_CKPT="$CKPT" BT_REPO_ROOT="$FROZEN"
  OMP_NUM_THREADS=4 MKL_NUM_THREADS=4
)

run_arm() {   # name  extra-env...
  local name="$1"; shift
  local J="$ROOT/$name"
  rm -rf "$J"; mkdir -p "$J"
  echo "[$(date -u +%H:%M:%S)] === ARM $name === games=$GAMES passes=$PASSES conc=$CONC max_actions=$MAXACT extra: $*"
  curl -s --max-time 10 "$BASE/models" | grep -q flashnext || { echo "SERVER NOT READY at $BASE -- skipping $name"; return 1; }
  ( printf '%s\n' "arm=$name" "games=$GAMES" "passes=$PASSES" "concurrency=$CONC" "max_actions=$MAXACT" \
      "per_game_s=$PERGAME" "analyzer_timeout_s=$TIMEOUT" "ctx=$CTX" "base=$BASE" "extra=$*" \
      "started_utc=$(date -u +%FT%TZ)" ) > "$J/ARM_CONFIG"
  nice -n 5 env "${common[@]}" SMOKE_JOB_DIR="$J" BT_LOG="$J/board_tower.jsonl" "$@" \
    .mlvenv/bin/python -u notebooks_duck/ab_local.py > "$J/run.log" 2>&1
  local rc=$?
  echo "finished_utc=$(date -u +%FT%TZ) rc=$rc" >> "$J/ARM_CONFIG"
  echo "[$(date -u +%H:%M:%S)] ARM $name done rc=$rc  games_finished=$(grep -ac '\[finished\]' "$J/run.log" 2>/dev/null)"
  grep -a 'BOARD TOWER SUMMARY' "$J/run.log" | tail -1
}

for a in ${ARMS:-tower png32 text}; do case "$a" in
  tower) run_arm tower MULTIMODAL_CONTEXT=current_grid BT_TOWER=1 BT_IMAGE_KEEP=1 ;;
  png32) run_arm png32 MULTIMODAL_CONTEXT=current_grid MULTIMODAL_UPSCALE=32 BT_IMAGE_KEEP=1 ;;
  png4)  run_arm png4  MULTIMODAL_CONTEXT=current_grid MULTIMODAL_UPSCALE=4  BT_IMAGE_KEEP=1 ;;
  text)  run_arm text ;;
  *) echo "unknown arm $a" ;;
esac; done
echo "[$(date -u +%H:%M:%S)] === ALL ARMS COMPLETE ==="
