#!/bin/bash
set -e

daemon_name=$(python3 -c "from AutoNode import daemon; print(daemon.name)")
monitor_daemon="$daemon_name"@monitor.service
case "${1}" in
"status")
  systemctl --user status "$monitor_daemon"
  ;;
"log")
  tail -f "$(python3 -c "from AutoNode import monitor; print(monitor.log_path)")"
  ;;
"journal")
  journalctl _SYSTEMD_USER_UNIT="$monitor_daemon" "${@:2}"
  ;;
"restart")
  systemctl --user restart "$monitor_daemon"
  ;;
"name")
  echo "$monitor_daemon"
  ;;
*)
  echo "
  == AutoNode node monitor command help ==

  Usage: auto-node monitor <cmd>

  Cmd:            Help:

  log             View the log of your Harmony Monitor
  status          View the status of your Harmony Monitor daemon
  journal <opts>  View the journal of your Harmony Monitor daemon
  restart         Manually restart your Harmony Monitor daemon
  name            Get the name of your Harmony Monitor deamon
    "
  exit
  ;;
esac
