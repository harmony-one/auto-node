#!/bin/bash
set -e

function yes_or_exit() {
  read -r reply
  if [[ ! $reply =~ ^[Yy]$ ]]; then
    exit 1
  fi
}

daemon_name=$(python3 -c "from AutoNode import daemon; print(daemon.name)")
node_daemon="$daemon_name"@node.service
case "${1}" in
"status")
  systemctl --user status "$node_daemon"
  ;;
"log")
  tail -f "$(python3 -c "from AutoNode import node; print(node.log_path)")"
  ;;
"journal")
  journalctl _SYSTEMD_USER_UNIT="$node_daemon" "${@:2}"
  ;;
"restart")
  can_safe_stop=$(python3 -c "from AutoNode import validator; print(validator.can_safe_stop_node())")
  if [ "$can_safe_stop" == "False" ]; then
    echo "[AutoNode] Validator is still elected and node is still signing."
    echo "[AutoNode] Continue to restart node? (y/n)"
    yes_or_exit
  fi
  systemctl --user restart "$node_daemon"
  ;;
"name")
  echo "$node_daemon"
  ;;
"info")
  python3 -u -c "from pyhmy import blockchain; import json; print(json.dumps(blockchain.get_node_metadata('http://localhost:9500'), indent=2))"
  ;;
*)
  echo "
  == AutoNode node command help ==

  Usage: auto-node node <cmd>

  Cmd:           Help:

  log            View the current log of your Harmony Node
  status         View the status of your current Harmony Node daemon
  journal <opts> View the journal of your current Harmony Node daemon
  restart        Manually restart your current Harmony Node daemon
  name           Get the name of your current Harmony Node deamon
  info                  Get the node's current metadata

  'init' is a special option for the inital node daemon, may be needed for debugging.
  Otherwise not needed.
    "
  exit
  ;;
esac
