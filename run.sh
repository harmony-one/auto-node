#!/bin/bash
cmd="python3 -u /root/run.py ${*}"
tmux new-session -d -s "node" "${cmd}"
echo ""
echo "[AutoNode] Process initlized. Attach to see progress with \`./auto_node.sh attach\`"
tail -f /dev/null