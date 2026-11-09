#!/bin/bash
# Run a schedule of unpack-bench repeats in the Kaggle image, one extracted tree at a time.
# Usage: run_bench.sh "<arm:rep> <arm:rep> ..." <results dir>
#   e.g. run_bench.sh "A3:1 A0:1 A3:2 A0:2" /path/results
# Per repeat: free-space gate (>= 22 GB on the output drive to start), warm the original blobs into page cache,
# syncfs + wait for Dirty+Writeback < 512 MB, extract (bench_unpack.py) under a guard that stops the container if
# the drive falls below 3 GB, manifest the tree (tree_manifest.py), delete it, syncfs + drain again.
# The container: Kaggle image by digest, root, --network none, 4 E-cores (16-19), --cpu-shares 2, every step nice 19.
set -uo pipefail
SCHED=$1; R=$2
HERE=$(cd "$(dirname "$0")" && pwd)
OUT=${RTU_OUT:-/media/ignaz/claude-extra/rtu_1101}
SRC=${RTU_SRC:-/mnt/data/arc3_runtime313/dataset}
BLOBS=${RTU_BLOBS:-/dev/shm/rtu_1101}
IMG=gcr.io/kaggle-gpu-images/python@sha256:9a6bcfda6d03b2cd9aa347ee8c1bae62043328ed0f4afe9bda014e4f8bbf9435
NAME=rtu-bench
stamp() { date '+%F %T'; }
avail_gb() { df --output=avail -B1G "$OUT" | tail -1 | tr -d ' '; }
dirty_mb() { awk '/^(Dirty|Writeback):/ {s+=$2} END {print int(s/1024)}' /proc/meminfo; }
drain() {
  sync -f "$OUT"
  for _ in $(seq 1 300); do [ "$(dirty_mb)" -lt 512 ] && return 0; sleep 2; done
  echo "$(stamp) WARN dirty did not drain below 512 MB: $(dirty_mb) MB"
}
running() { [ "$(docker inspect -f '{{.State.Running}}' $NAME 2>/dev/null)" = "true" ]; }
swap_pages() { awk '/^pswpin / {i=$2} /^pswpout / {o=$2} END {print i, o}' /proc/vmstat; }
inputs() {  # the variant files an arm reads from $BLOBS (the originals are warmed for every arm)
  case $1 in
    A2) echo "$BLOBS/l8.tar.zst $BLOBS/l100.tar.zst";;
    A3) echo "$BLOBS/l100.tar";;
    A4) echo "$BLOBS"/parts_gzip/*;;
    A5) echo "$BLOBS/l8.tar.zst" "$BLOBS"/parts_zstd/*;;
  esac
}

if docker inspect $NAME >/dev/null 2>&1; then echo "$(stamp) container $NAME already exists; refusing"; exit 1; fi
docker run -d --name $NAME --pull never --network none --cpuset-cpus 16-19 --cpu-shares 2 \
  -v "$SRC":/src:ro -v "$BLOBS":/blobs:ro -v "$OUT":/out -v "$HERE":/bench:ro -v "$R":/results \
  --entrypoint sleep $IMG infinity > /dev/null || exit 1
echo "$(stamp) container $NAME up ($IMG)"
for item in $SCHED; do
  arm=${item%%:*}; rep=${item##*:}; tag="${arm}_r${rep}"
  running || { echo "$(stamp) ABORT container not running"; break; }
  docker exec $NAME test -e /out/root && { echo "$(stamp) ABORT /out/root exists"; break; }
  free_gb=$(avail_gb)
  [ "$free_gb" -ge 22 ] || { echo "$(stamp) ABORT $tag: $free_gb GB free on $OUT (< 22)"; break; }
  # Warm the inputs: page cache for the originals, and swap-in for tmpfs variants (11-01: an outside shared-memory
  # spike pushed the /dev/shm variants to swap mid-schedule; pswpin during the extraction is recorded below).
  taskset -c 16-19 nice -n 19 cat "$SRC"/layer-*.blob $(inputs "$arm") > /dev/null
  drain
  pre="free_gb=$free_gb dirty_mb=$(dirty_mb) memfree_gb=$(free -g | awk '/^Mem:/ {print $4}') load=$(cut -d' ' -f1-3 /proc/loadavg)"
  ( while sleep 1; do a=$(avail_gb); if [ "$a" -lt 3 ]; then echo "$(stamp) GUARD $a GB free: stopping $NAME"; docker stop -t 1 $NAME > /dev/null; exit 0; fi; done ) &
  guard=$!
  read -r sin0 sout0 <<< "$(swap_pages)"
  docker exec $NAME nice -n 19 python3 -I /bench/bench_unpack.py "$arm" /out/root "/results/run_$tag.json" > "$R/run_$tag.out" 2>&1
  rc=$?
  read -r sin1 sout1 <<< "$(swap_pages)"
  pre="$pre pswpin=$((sin1 - sin0)) pswpout=$((sout1 - sout0))"
  kill $guard 2>/dev/null; wait $guard 2>/dev/null
  low_gb=$(avail_gb)
  if running; then
    docker exec $NAME nice -n 19 python3 -I /bench/tree_manifest.py manifest /out/root "/results/m_$tag.tsv" > "$R/man_$tag.json" 2>&1
    docker exec $NAME rm -rf /out/root
  fi
  drain
  echo "$(stamp) $tag rc=$rc $(tail -1 "$R/run_$tag.out") | $pre free_after_extract_gb=$low_gb | manifest $(python3 -I -c 'import json,sys; d=json.load(open(sys.argv[1])); print(d["entries"], d["core_sha256"][:16], d["dirmtime_sha256"][:16])' "$R/man_$tag.json" 2>/dev/null || echo FAILED)"
done
docker stop -t 1 $NAME > /dev/null 2>&1; docker rm $NAME > /dev/null 2>&1
echo "$(stamp) schedule done; container removed"
