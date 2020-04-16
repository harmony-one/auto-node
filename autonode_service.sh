#!/bin/bash
set -e
trap 'killall harmony' EXIT

if ! pip3 list --format=legacy | grep AutoNode; then
  echo "[AutoNode] Missing AutoNode python3 library, installing using pip3."
  pip3 install AutoNode
fi

reset_mode=false

node_dir=$(python3 -c "from AutoNode import common; print(common.node_dir)")
bls_key_dir=$(python3 -c "from AutoNode import common; print(common.bls_key_dir)")
validator_log_path=$(python3 -c "from AutoNode import validator; print(validator.log_path)")
monitor_log_path=$(python3 -c "from AutoNode import monitor; print(monitor.log_path)")
autonode_node_pid_path=$(python3 -c "from AutoNode import common; print(common.node_pid_path)")

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
  if ps -p "$pid" | grep harmony || ps -p "$pid" | grep node.sh; then
    echo "[AutoNode] Killing existing Harmony Node"
    kill -2 "$pid"
  fi
fi

if pgrep harmony; then
  echo "[AutoNode] Killing existing Harmony proces"
  killall harmony > /dev/null
  sleep 5  # wait for node to shutdown
fi

log_dir="$node_dir"/latest
if [ -d "$log_dir" ]; then
  log_backup_dir="$node_dir"/autonode_backup_logs/$(date +"%T")
  echo "[AutoNode] Backing up logs to \`${log_backup_dir}\` and cleaning Harmony Node logs..."
  mkdir -p "$log_backup_dir"
  cp -R "$log_dir"/. "$log_backup_dir"/
  rm -rf "$log_dir"
fi

echo "[AutoNode] Starting new Harmony Node"
pid=$(python3 -c "from AutoNode import node; print(node.start(verbose=False))")

if [ "$reset_mode" = "true" ]; then
  python3 -u -c "from AutoNode import validator; validator.setup(recover_interaction=True)" > "$validator_log_path"
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
