#!/usr/bin/env bash
# Detached waiter for run_full.sh: starts ONLY when the measurement chain is over --
#   the lock file has been ABSENT for 5 consecutive minutes AND no run_measure*.sh / run_chain.sh process exists.
# Launch:  setsid nohup scripts/board_tower/wait_then_run_full.sh > /media/ignaz/claude-extra/board_tower/run_full.log 2>&1 &
set -u
here=$(cd "$(dirname "$0")" && pwd)
LOCK=${LOCK:-/tmp/claude-1000/-home-ignaz/a69572fd-b71a-4c65-b62e-a45043ddb561/scratchpad/gpu_arm.lock}
NEED=${NEED_ABSENT_SECONDS:-300}
log() { echo "$(date '+%F %T') $*"; }
chain_running() {  # any run_measure*.sh or run_chain.sh process (not this script, not the grep)
  ps -eo pid,args | awk -v me=$$ '$1 != me && ($0 ~ /[r]un_measure[^ ]*\.sh/ || $0 ~ /[r]un_chain\.sh/) {found=1} END {exit !found}'
}
log "waiter start (pid $$): lock $LOCK must be absent for ${NEED}s and no chain process"
absent_since=""
last_note=0
while :; do
  now=$(date +%s)
  if [ -e "$LOCK" ] || chain_running; then
    absent_since=""
    if [ $((now - last_note)) -ge 1800 ]; then
      log "still waiting: lock $([ -e "$LOCK" ] && echo present || echo absent), chain $(chain_running && echo running || echo gone), load $(cut -d' ' -f1 /proc/loadavg)"
      last_note=$now
    fi
  else
    [ -z "$absent_since" ] && { absent_since=$now; log "lock absent and no chain process: starting the ${NEED}s countdown"; }
    if [ $((now - absent_since)) -ge "$NEED" ]; then
      log "clear for ${NEED}s: launching run_full.sh"
      break
    fi
  fi
  sleep 20
done
exec bash "$here/run_full.sh"
