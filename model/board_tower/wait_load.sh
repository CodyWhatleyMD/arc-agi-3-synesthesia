#!/usr/bin/env bash
# Block until the 1-min load average is <= ${BOARD_TOWER_MAX_LOAD:-8}. Used before every step tonight.
source "$(dirname "$0")/env.sh"; wait_load
