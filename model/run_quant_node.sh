#!/usr/bin/env bash
# v2 quant on the Nebius node (2026-10-07): ALL 976 calibration windows (Cody: "no half-measures"), recipe_v2
# (in_proj_a/b BF16, experts observer nvfp4_expanded_mse), BF16 source verified shard-for-shard against the local copy.
# One GPU (CUDA_VISIBLE_DEVICES=0): with 1.7 TB RAM the whole model stays in host memory and llm-compressor's
# sequential pipeline onloads one layer at a time; the offload dir should stay empty (it is checked at the end).
set -uo pipefail
export CUDA_DEVICE_ORDER=PCI_BUS_ID   # 10-07: CUDA default is FASTEST_FIRST; index 1 was the 5090, not the 6000
SRC=/data/models/Qwen3.8-Flash-Next; OUT=/data/quant/out/Qwen3.8-Flash-Next-NVFP4-ours-v2; OFF=/data/quant/offload
CALIB=/data/quant/calib_v2.jsonl; RECIPE=/data/quant/recipe_v2.yaml; N=$(wc -l < "$CALIB")
LOG=/data/quant/quantize_v2.log; RSS=/data/quant/quantize_v2.rss.log
mkdir -p "$(dirname "$OUT")" "$OFF"
echo "[$(date -u +%FT%TZ)] start src=$SRC out=$OUT samples=$N (all windows) recipe=$RECIPE gpu=${CUDA_VISIBLE_DEVICES:-0}" | tee -a "$LOG"
cd /data/quant
CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-0} /data/quant/venv/bin/python -u /data/quant/quantize.py \
  --src "$SRC" --out "$OUT" --offload-dir "$OFF" --calib "$CALIB" --recipe "$RECIPE" \
  --samples "$N" --max-seq 4096 --device cuda:0 --cpu-mem 1500GiB --gpu-mem 80GiB >> "$LOG" 2>&1 &
QPID=$!; echo "quantize.py pid $QPID" | tee -a "$LOG"
( while kill -0 $QPID 2>/dev/null; do echo "$(date +%s) rss_mb=$(( $(awk '/VmRSS/{print $2}' /proc/$QPID/status 2>/dev/null || echo 0) / 1024 )) gpu_mb=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits -i ${CUDA_VISIBLE_DEVICES:-0} 2>/dev/null | head -1)"; sleep 60; done ) >> "$RSS" 2>&1 &
wait $QPID; RC=$?
echo "[$(date -u +%FT%TZ)] quantize.py exited rc=$RC; offload dir: $(du -sh "$OFF" | cut -f1); out: $(du -sh "$OUT" 2>/dev/null | cut -f1)" | tee -a "$LOG"
