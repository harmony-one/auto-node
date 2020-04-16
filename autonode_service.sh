#!/bin/bash
set -e
trap 'kill $(jobs -p)' EXIT

if ! pip3 list --format=legacy | grep AutoNode; then
  echo "[AutoNode] Missing AutoNode python3 library, installing using pip3."
  pip3 install AutoNode
fi

if ! command -v tmux; then
  echo "[AutoNode] Tmux is not installed. Closing service."
  exit
fi

reset_mode=false

node_dir=$(python3 -c "from AutoNode import common; print(common.node_dir)")
bls_key_dir=$(python3 -c "from AutoNode import common; print(common.bls_key_dir)")
harmony_dir=$(python3 -c "from AutoNode import common; print(common.harmony_dir)")
validator_log_path=$(python3 -c "from AutoNode import validator; print(validator.log_path)")
monitor_log_path=$(python3 -c "from AutoNode import monitor; print(monitor.log_path)")
autonode_node_pid_path="${harmony_dir}/.autonode_node_pid"

# AutoNode will setup the .pass files for each BLS key on init setup.
bls_key_count=$(ls "${bls_key_dir}" | grep -c ".key")
bls_pass_count=$(ls "${bls_key_dir}" | grep -c ".pass")
if [ "$bls_key_count" -eq 0 ] || [ "$bls_pass_count" -eq 0 ] || [ "$bls_pass_count" -ne "$bls_pass_count" ]; then
  echo "[AutoNode] BLS key(s) error, AutoNode was not setup. Closing service."]
  exit
fi

if [ -f "$autonode_node_pid_path" ]; then
  reset_mode=true
  echo "[AutoNode] Resetting Harmony Node"
  pid=$(cat "$autonode_node_pid_path")
  if ps -p "$pid" | grep harmony || ps -p "$pid" | grep node; then
    echo "[AutoNode] Killing existing Harmony Node"
    kill -2 "$pid"
  fi
fi

killall harmony
sleep 5  # wait for node to shutdown

log_backup_dir="$node_dir"/autonode_backup_logs/$(date +"%T")
echo "[AutoNode] Backing up logs to \`${log_backup_dir}\` and cleaning Harmony Node logs..."
mkdir -p "$log_backup_dir"
cp -R "$node_dir"/latest/. "$log_backup_dir"/
rm -rf "$node_dir"/latest

echo "[AutoNode] Starting new Harmony Node"
pid=$(python3 -c "from AutoNode import node; print(node.start())")

if [ "$reset_mode" = "true" ]; then
  python3 -u -c "from AutoNode import validator; validator.setup(recover_interaction=True)" > "$validator_log_path"
else
  cmd="python3 -u -c \"from AutoNode import validator; validator.setup(recover_interaction=False)\" 2>&1 | tee -a $validator_log_path"
  tmux_session=$(python3 -c "from AutoNode import validator; print(validator.tmux_session_name)")
  tmux new-session -d -s "${tmux_session}" "${cmd}"
  echo "[AutoNode] Validator setup requires interaction. Attach with \`tmux a -t ${tmux_session}\`."
fi

echo "$pid" > "$autonode_node_pid_path"
chmod go-rwx "$autonode_node_pid_path"

echo "[AutoNode] Starting Harmony Node monitor. Logging file to \`${monitor_log_path}\`."
python3 -u -c "from AutoNode import monitor; monitor.start()" > "$monitor_log_path"

echo "[AutoNode] Node finished running due to timeout, killing Harmony Node and exiting."
kill -2 "$pid"
killall harmony
rm -rf "$autonode_node_pid_path"
exit
