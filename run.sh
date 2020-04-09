#!/bin/bash
cmd="python3 -u /root/run.py ${*}"
tmux new-session -d -s "node" "${cmd}"
echo ""
echo "[AutoNode] Process initlized"
tail -f /dev/null