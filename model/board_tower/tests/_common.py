"""Shared bits for the board-tower tests. Every test runs from an EMPTY cwd (run_all.sh does `cd $(mktemp -d)`) and
finds the worktree through this file's location. Outputs go under $BOARD_TOWER_TEST_DIR (default: a fresh temp dir)."""
import os
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
WT = HERE.parents[2]                                   # the worktree / checkout that holds scripts/board_tower
PY = os.environ.get("BOARD_TOWER_PY", "/home/ignaz/github/arc-prize-2026/.mlvenv/bin/python")
TEST_DIR = pathlib.Path(os.environ.get("BOARD_TOWER_TEST_DIR") or tempfile.mkdtemp(prefix="board_tower_test_"))
def env_now() -> dict:
    """Built at CALL time so a test's later os.environ[...] = ... (e.g. TARGETS for the docker wrapper) is seen."""
    return dict(os.environ, CUDA_DEVICE_ORDER="PCI_BUS_ID", CUDA_VISIBLE_DEVICES=os.environ.get("BOARD_TOWER_GPU", "0"),
                OMP_NUM_THREADS="2", BOARD_TOWER_THREADS="2", PYTHONPATH=str(WT))


def run(cmd, log_name, timeout=3600, cwd=None):
    """nice -n 19, from an empty cwd, log to TEST_DIR/<log_name>."""
    TEST_DIR.mkdir(parents=True, exist_ok=True)
    cwd = cwd or tempfile.mkdtemp(prefix="cwd_", dir=TEST_DIR)
    log = TEST_DIR / log_name
    with open(log, "w") as fh:
        p = subprocess.run(["nice", "-n", "19"] + [str(c) for c in cmd], cwd=cwd, env=env_now(), stdout=fh, stderr=subprocess.STDOUT, timeout=timeout)
    text = log.read_text()
    return p.returncode, text, log


def load_ok() -> float:
    return float(open("/proc/loadavg").read().split()[0])


def wait_load(max_load=float(os.environ.get("BOARD_TOWER_MAX_LOAD", "8"))):
    import time
    while load_ok() > max_load:
        print(f"load {load_ok():.2f} > {max_load}: waiting", file=sys.stderr, flush=True); time.sleep(30)
