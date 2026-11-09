#!/usr/bin/env bash
# All board-tower tests, from an EMPTY cwd, nice 19, GPU = nvidia-smi index 0 (the 5090). ~6 min.
#   BOARD_TOWER_TEST_DIR=<dir> (default: a temp dir)  BOARD_TOWER_PY=<python> (default: the repo .mlvenv)
set -u
here=$(cd "$(dirname "$0")" && pwd)
export BOARD_TOWER_TEST_DIR=${BOARD_TOWER_TEST_DIR:-$(mktemp -d "${TMPDIR:-/tmp}/board_tower_tests.XXXXXX")}
export BOARD_TOWER_PY=${BOARD_TOWER_PY:-/home/ignaz/github/arc-prize-2026/.mlvenv/bin/python}
export CUDA_DEVICE_ORDER=PCI_BUS_ID CUDA_VISIBLE_DEVICES=${BOARD_TOWER_GPU:-0} OMP_NUM_THREADS=2 BOARD_TOWER_THREADS=2
cd "$(mktemp -d "${TMPDIR:-/tmp}/bt_cwd.XXXXXX")"
fail=0
for t in test_export.py test_make_targets_smoke.py test_train_smoke.py; do
  echo "=== $t"
  if nice -n 19 "$BOARD_TOWER_PY" "$here/$t" > "$BOARD_TOWER_TEST_DIR/$t.log" 2>&1; then
    tail -1 "$BOARD_TOWER_TEST_DIR/$t.log"
  else
    echo "FAIL ($BOARD_TOWER_TEST_DIR/$t.log)"; tail -5 "$BOARD_TOWER_TEST_DIR/$t.log"; fail=1
  fi
done
echo "outputs: $BOARD_TOWER_TEST_DIR"
exit $fail
