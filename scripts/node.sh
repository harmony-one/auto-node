#!/bin/bash
set -e

daemon_name=$(python3 -c "from AutoNode import daemon; print(daemon.name)")
if systemctl --type=service --state=active | grep -e ^"$daemon_name"@node_recovered.service; then
  node_daemon="$daemon_name"@node_recovered.service
else
  node_daemon="$daemon_name"@node.service
fi
case "${1}" in
  "status")
  if [ "${2}" == "init" ]; then
    systemctl status "$daemon_name"@node.service
  else
    systemctl status "$node_daemon"
  fi
  ;;
  "log")
  tail -f "$(python3 -c "from AutoNode import node; print(node.log_path)")"
  ;;
  "journal")
  if [ "${2}" == "init" ]; then
    journalctl -u "$daemon_name"@node.service "${@:3}"
  else
    journalctl -u "$node_daemon" "${@:2}"
  fi
  ;;
  "restart")
  if [ "${2}" == "init" ]; then
    systemctl restart "$daemon_name"@node.service
  else
    systemctl restart "$node_daemon"
  fi
  ;;
  "name")
  if [ "${2}" == "init" ]; then
    echo "$daemon_name"@node.service
  else
    echo "$node_daemon"
  fi
  ;;
  "info")
  curl --location --request POST 'http://localhost:9500/' \
  --header 'Content-Type: application/json' \
  --data-raw '{
      "jsonrpc": "2.0",
      "method": "hmy_getNodeMetadata",
      "params": [],
      "id": 1
  }' | jq
  ;;
  *)
    echo "
  == AutoNode node command help ==

  Usage: auto-node node <cmd>

  Cmd:                  Help:

  log                   View the current log of your Harmony Node
  status [init]         View the status of your current Harmony Node daemon
  journal [init] <opts> View the journal of your current Harmony Node daemon
  restart [init]        Manually restart your current Harmony Node daemon
  name [init]           Get the name of your current Harmony Node deamon
  info                  Get the node's current metadata

  'init' is a special option for the inital node daemon, may be needed for debugging.
  Otherwise not needed.
    "
    exit
esac