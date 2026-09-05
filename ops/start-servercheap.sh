#!/bin/sh
set -eu
mkdir -p "$HOME/.local/state/antenna-observatory"
nohup python3 "$HOME/antenna-observatory/current/ops/servercheap-supervisor.py" relay </dev/null >/dev/null 2>&1 &
nohup python3 "$HOME/antenna-observatory/current/ops/servercheap-supervisor.py" tunnel </dev/null >/dev/null 2>&1 &
