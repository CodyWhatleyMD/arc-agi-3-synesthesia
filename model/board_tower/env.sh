#!/usr/bin/env bash
# Source this before any board-tower step on the host.
#  * GPU: the 5090 ONLY. torch's default CUDA enumeration on this host puts the RTX PRO 6000 first (nvidia-smi
#    index 1!), so pin by PCI bus order + index 0 (= nvidia-smi index 0 = the 5090, bus 02:00.0). train.py and
#    export_embeds.py also refuse to run unless the visible device name contains "5090".
#  * CPU: 2 torch threads, nice 19 (callers prefix commands with `nice -n 19`).
#  * wait_load: block while the 1-min load average is above ${BOARD_TOWER_MAX_LOAD:-8} (the 6000's Flash-Next
#    server is host-bound; CPU load above ~9 contaminates its measurement arms).
export CUDA_DEVICE_ORDER=PCI_BUS_ID
export CUDA_VISIBLE_DEVICES=${BOARD_TOWER_GPU:-0}
export OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 BOARD_TOWER_THREADS=2
export BOARD_TOWER_PY=${BOARD_TOWER_PY:-/home/ignaz/github/arc-prize-2026/.mlvenv/bin/python}
wait_load() {
  local max=${BOARD_TOWER_MAX_LOAD:-8} l
  while :; do
    l=$(cut -d' ' -f1 /proc/loadavg)
    if awk -v l="$l" -v m="$max" 'BEGIN{exit !(l<=m)}'; then return 0; fi
    echo "$(date +%H:%M:%S) load $l > $max: waiting" >&2
    sleep 30
  done
}
