#!/usr/bin/env bash
# After fidelity_512_chain.sh prints "512 DONE": fill the 4 prompts (508-511) that ours and nvidia never reached
# (their runs crashed on the over-length prompt 507 before the per-prompt error handling existed). Resume-safe.
set -u; cd /home/ignaz/github/arc-prize-2026
until grep -q "512 DONE" runs/flashnext/fidelity_512_chain.log 2>/dev/null; do sleep 120; done; sleep 20
log(){ echo "[$(date +%H:%M:%S)] $*"; }
fill() { docker rm -f flashnext >/dev/null 2>&1; sleep 3; M=$2 scripts/flashnext_serve/serve_ours_sidecar.sh >/dev/null
  for i in $(seq 1 120); do curl -s --max-time 3 http://127.0.0.1:5300/v1/models >/dev/null 2>&1 && break; docker ps --filter name=flashnext --format '{{.Status}}' | grep -q Up || { log "$1: CONTAINER DIED"; return 1; }; sleep 10; done
  /home/ignaz/quant-venv/bin/python -u scripts/flashnext_quant/fidelity_vllm.py --workers 4 --tokenizer "$2" --out runs/flashnext/fidelity_vllm_$1.jsonl > runs/flashnext/fidelity_vllm_$1_fill.log 2>&1
  log "$1: $(grep -E '^FIDELITY' runs/flashnext/fidelity_vllm_$1_fill.log | sed -E 's/FIDELITY flashnext: //' | cut -c1-150)"; }
log "fill-in start"
fill ours /media/ignaz/claude-extra/Qwen3.8-Flash-Next-NVFP4-ours
fill nvidia /media/ignaz/model-storage-2/nvidia-flashnext-nvfp4
log "FILL DONE"; docker rm -f flashnext >/dev/null 2>&1; log "server stopped -- the 6000 is free"
