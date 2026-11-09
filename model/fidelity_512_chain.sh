#!/usr/bin/env bash
# All 512 held-out prompts through each served checkpoint, sequentially on the 6000 (09-30).
# Detached (setsid) because it runs ~4.5 h; the per-checkpoint fidelity_vllm.py is resume-safe (skips done ids).
# Waits for the RadixArk-64 chain to release the card first (its watcher output prints THREE-WAY when done).
set -u
cd /home/ignaz/github/arc-prize-2026
GATE=${GATE:-/tmp/claude-1000/-home-ignaz/bb6e48a1-763f-4887-b30e-034d8921d8e8/tasks/bn7c4rmcn.output}
until grep -qE "THREE-WAY|CONTAINER DIED" "$GATE" 2>/dev/null; do sleep 120; done; sleep 30
log(){ echo "[$(date +%H:%M:%S)] $*"; }
serve_and_run() { # $1 name $2 checkpoint dir
  docker rm -f flashnext >/dev/null 2>&1; sleep 3; M=$2 scripts/flashnext_serve/serve_ours_sidecar.sh >/dev/null
  for i in $(seq 1 120); do curl -s --max-time 3 http://127.0.0.1:5300/v1/models >/dev/null 2>&1 && break; docker ps --filter name=flashnext --format '{{.Status}}' | grep -q Up || { log "$1: CONTAINER DIED"; return 1; }; sleep 10; done
  log "$1 up: $(docker logs flashnext 2>&1 | grep -aoE 'GPU KV cache size: [0-9,]+ tokens' | head -1)"
  /home/ignaz/quant-venv/bin/python -u scripts/flashnext_quant/fidelity_vllm.py --workers 6 --tokenizer "$2" --out runs/flashnext/fidelity_vllm_$1.jsonl > runs/flashnext/fidelity_vllm_$1_512.log 2>&1
  log "$1: $(grep -E '^FIDELITY' runs/flashnext/fidelity_vllm_$1_512.log | sed -E 's/FIDELITY flashnext: //' | cut -c1-170)"
}
log "512 chain start"
serve_and_run ours /media/ignaz/claude-extra/Qwen3.8-Flash-Next-NVFP4-ours
serve_and_run nvidia /media/ignaz/model-storage-2/nvidia-flashnext-nvfp4
serve_and_run radixark /media/ignaz/model-storage-2/radixark-flashnext-nvfp4
log "512 DONE"
