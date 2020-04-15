#!/bin/bash

if ! pip3 list | grep AutoNode; then
  echo "[AutoNode] Missing AutoNode python3 library, installing using pip3."
  pip3 install AutoNode
fi

node_dir=$(python3 -c "from AutoNode import common; print(common.node_dir)")
bls_key_dir=$(python3 -c "from AutoNode import common; print(common.bls_key_dir)")
harmony_dir=$(python3 -c "from AutoNode import common; print(common.harmony_dir)")
autonode_node_pid_file="${harmony_dir}/.autonode_node_pid_file"
autonode_log_dir="${harmony_dir}/autonode_service_log"
validator_log_dir="${autonode_log_dir}/validator_create.log"
monitor_log_dir="${autonode_log_dir}/node_monitor.log"
recovery_mode=false

bls_key_count=$(ls "${bls_key_dir}" | grep -c ".key")
bls_pass_count=$(ls "${bls_key_dir}" | grep -c ".pass")
if [ "$bls_key_count" -eq 0 ] || [ "$bls_pass_count" -eq 0 ] || [ "$bls_pass_count" -ne "$bls_pass_count" ]; then
  echo "[AutoNode] BLS key(s) error, AutoNode was not setup. Closing service."]
  exit
fi

if [ -f "$autonode_node_pid_file" ]; then
  recovery_mode=true
  echo "[AutoNode] Recovering Harmony Node"
  pid=$(cat "$autonode_node_pid_file")
  if ps -p "$pid" | grep harmony || ps -p "$pid" | grep node; then
    echo "[AutoNode] Killing existing Harmony Node"
    kill -2 "$pid"
    sleep 10  # wait for node to shutdown
  fi
fi

echo "[AutoNode] Backing up and cleaning Harmony Node logs..."
mkdir -p "$node_dir"/backup
cp -R "$node_dir"/latest/. "$node_dir"/backup/
rm -rf "$node_dir"/latest

echo "[AutoNode] Starting new Harmony Node"
pid=$(python3 -c "from AutoNode import node; print(node.start())")

if [ "$recovery_mode" = "true" ]; then
  python3 -u -c "from AutoNode import validator; validator.setup(recover_interaction=True)" > "$validator_log_dir"
else
  cmd="python3 -u -c \"from AutoNode import validator; validator.setup(recover_interaction=False)\" 2>&1 | tee -a $validator_log_dir"
  tmux_session=$(python3 -c "from AutoNode import validator; print(validator.tmux_session_name)")
  tmux new-session -d -s "${tmux_session}" "${cmd}"
  echo "[AutoNode] Validator setup requires interaction. Attach with \`tmux a -t node ${tmux_session}\`"
fi

# TODO: monitor library and script...
