#!/usr/bin/env bash
# v2 quant of Qwen3.8-Flash-Next (2026-10-06): recipe_v2.yaml (in_proj_a/b BF16, experts observer nvfp4_expanded_mse)
# calibrated on calib_v2.jsonl (976 current-format chat-templated 4,096-token windows from his-harness requests).
# Runs on the RTX PRO 6000 (CUDA_VISIBLE_DEVICES=1 -> cuda:0 in-process). v1: 7h33m at 512x4096 (save phase ~65 min), peak RSS ~80 GB.
# Expect ~8-9 h at N=512, ~14-15 h at N=976. LAUNCH ONLY ON CODY'S WORD (he rejected the 10-06 launch; it ran anyway and died on disk).
#   nohup setsid bash run_quant_v2.sh > /dev/null 2>&1 &      (log + rss log land next to the output dir)
set -uo pipefail
export CUDA_DEVICE_ORDER=PCI_BUS_ID   # 10-07: CUDA default is FASTEST_FIRST; index 1 was the 5090, not the 6000
cd /home/ignaz/github/arc-prize-2026
OUT="${OUT:-/media/ignaz/claude-extra/Qwen3.8-Flash-Next-NVFP4-ours-v2}"
OFF="${OFF:-/media/ignaz/2TB HDD/claude-extra-archive/flashnext_offload_v2}"   # 10-07: the ct disk cache + offload overflowed model-storage-2 (119 GB free) in the aborted 20:32 run; the HDD has >1 TB and is read ~once per oneshot
CALIB="${CALIB:-/media/ignaz/claude-extra/flashnext_calib_v2/calib_v2.jsonl}"
LOG="${OUT}.quantize.log"; RSS="${OUT}.rss.log"
test -f "$CALIB" || { echo "no calib at $CALIB"; exit 1; }
test -f scripts/flashnext_quant/recipe_v2.yaml || { echo "no recipe_v2.yaml"; exit 1; }
free_out=$(df --output=avail -B1 "$(dirname "$OUT")" | tail -1)
[ "$free_out" -gt $((185*1024*1024*1024)) ] || { echo "need >=185 GB free under $(dirname "$OUT"), have $((free_out/1024/1024/1024)) GB"; exit 1; }
mkdir -p "$OFF"
free_off=$(df --output=avail -B1 "$OFF" | tail -1)
[ "$free_off" -gt $((250*1024*1024*1024)) ] || { echo "need >=250 GB free under $OFF, have $((free_off/1024/1024/1024)) GB"; exit 1; }
N="${N:-512}"   # 512 of the 976 windows (v1 parity; survey: no measurable gain from more at 180B); N=976 for all
[ "$N" -le "$(wc -l < "$CALIB")" ] || { echo "N=$N exceeds calib rows"; exit 1; }
echo "[$(date -u +%FT%TZ)] start out=$OUT offload=$OFF calib=$CALIB samples=$N" | tee -a "$LOG"
CUDA_VISIBLE_DEVICES=1 /home/ignaz/quant-venv/bin/python -u scripts/flashnext_quant/quantize.py \
  --src /media/ignaz/model-storage-1/Qwen3.8-Flash-Next --out "$OUT" --offload-dir "$OFF" \
  --calib "$CALIB" --recipe scripts/flashnext_quant/recipe_v2.yaml --samples "$N" --max-seq 4096 \
  --device cuda:0 >> "$LOG" 2>&1 &
QPID=$!
echo "quantize.py pid $QPID" | tee -a "$LOG"
while kill -0 "$QPID" 2>/dev/null; do
  echo "$(date +%s) rss_mb=$(( $(ps -o rss= -p "$QPID" 2>/dev/null || echo 0) / 1024 ))" >> "$RSS"
  sleep 20
done
wait "$QPID"; RC=$?
echo "[$(date -u +%FT%TZ)] quantize.py exited rc=$RC" | tee -a "$LOG"
