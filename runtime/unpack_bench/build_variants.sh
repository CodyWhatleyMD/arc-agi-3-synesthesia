#!/bin/bash
# Build every variant the unpack bench needs from the raw layer tars (made by `make_variants.py raw`).
# Usage: build_variants.sh <dir holding l8.tar and l100.tar> <plan_l100_4.json> <results dir>
# Runs on 4 cores (taskset 16-19) at nice 19: zstd -$ZSTD_LEVEL (default 3) --long=27 single streams for layers 8 and
# 100 (-T4), then the 4 zstd parts and the 4 gzip parts (pigz -6) of layer 100 (4 single-threaded compressors at
# once). Each step logs JSON.
set -euo pipefail
B=$1; PLAN=$2; R=$3
HERE=$(cd "$(dirname "$0")" && pwd)
run() { taskset -c 16-19 nice -n 19 python3 -I "$HERE/make_variants.py" "$@"; }
stamp() { date '+%F %T'; }
echo "$(stamp) start"
for l in l100 l8; do
  t0=$(date +%s.%N); run single "$B/$l.tar" zstd "$B/$l.tar.zst" > "$R/single_$l.json"; t1=$(date +%s.%N)
  echo "$(stamp) single $l zstd: $(cat "$R/single_$l.json") build_s=$(echo "$t1 - $t0" | bc)"
done
mkdir -p "$B/parts_zstd" "$B/parts_gzip"
for codec in zstd gzip; do
  t0=$(date +%s.%N); run parts "$B/l100.tar" "$PLAN" $codec "$B/parts_$codec" > "$R/parts_$codec.json"; t1=$(date +%s.%N)
  echo "$(stamp) parts $codec: $(cat "$R/parts_$codec.json") build_s=$(echo "$t1 - $t0" | bc)"
done
echo "$(stamp) done"
