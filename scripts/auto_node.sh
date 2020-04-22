#!/bin/bash

set -e

# TODO: convert auto_node.sh into python3 click CLI since lib is in python3.
function yes_or_exit(){
  read -r reply
  if [[ ! $reply =~ ^[Yy]$ ]]
  then
    exit 1
  fi
}

if (( "$EUID" == 0 )); then
  echo "You are running as root, which is not recommended. Continue (y/n)?"
  yes_or_exit
fi
sudo -l > /dev/null  # To trigger sudo first

case "${1}" in
  "run")
    harmony_dir=$(python3 -c "from AutoNode import common; print(common.harmony_dir)")
    python3 -u "$harmony_dir"/init.py "${@:2}"
    if [ "$2" == "-h" ] || [ "$2" == "--help" ]; then
      exit
    fi
    echo "[AutoNode] Initilized service..."
    daemon_name=$(python3 -c "from AutoNode.daemon import Daemon; print(Daemon.name)")
    sudo systemctl start "$daemon_name"@node.service
    sudo systemctl start "$daemon_name"@monitor.service
    python3 -u -c "from AutoNode import validator; validator.setup(recover_interaction=False)" || true
    monitor_log_path=$(python3 -c "from AutoNode import monitor; print(monitor.log_path)")
    if [ -f "$monitor_log_path" ]; then
      tail -f "$monitor_log_path"
    else
      echo "[AutoNode] Monitor failed to start..."
      systemctl status "$daemon_name"@monitor.service || true
    fi
    ;;
  "init")
    harmony_dir=$(python3 -c "from AutoNode import common; print(common.harmony_dir)")
    python3 -u "$harmony_dir"/init.py "${@:2}"
    ;;
  "node")
    daemon_name=$(python3 -c "from AutoNode.daemon import Daemon; print(Daemon.name)")
    if systemctl --type=service --state=active | grep -e ^"$daemon_name"@node.service; then
      node_daemon="$daemon_name"@node.service
    else
      node_daemon="$daemon_name"@node_recovered.service
    fi
    case "${2}" in
      "status")
      if [ "${3}" == "init" ]; then
        systemctl status "$daemon_name"@node.service
      else
        systemctl status "$node_daemon"
      fi
      ;;
      "log")
      tail -f "$(python3 -c "from AutoNode import node; print(node.log_path)")"
      ;;
      "journal")
      if [ "${3}" == "init" ]; then
        journalctl -u "$daemon_name"@node.service "${@:4}"
      else
        journalctl -u "$node_daemon" "${@:3}"
      fi
      ;;
      "restart")
      if [ "${3}" == "init" ]; then
        systemctl restart "$daemon_name"@node.service
      else
        systemctl restart "$node_daemon"
      fi
      ;;
      "name")
      if [ "${3}" == "init" ]; then
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

      Usage: auto_node.sh node <cmd>

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
    ;;
  "monitor")
    daemon_name=$(python3 -c "from AutoNode.daemon import Daemon; print(Daemon.name)")
    monitor_daemon="$daemon_name"@monitor.service
    case "${2}" in
      "status")
      systemctl status "$monitor_daemon"
      ;;
      "log")
      tail -f "$(python3 -c "from AutoNode import monitor; print(monitor.log_path)")"
      ;;
      "journal")
      journalctl -u "$monitor_daemon" "${@:3}"
      ;;
      "restart")
      sudo systemctl restart "$monitor_daemon"
      ;;
      "name")
      echo "$monitor_daemon"
      ;;
      *)
        echo "
      == AutoNode node monitor command help ==

      Usage: auto_node.sh monitor <cmd>

      Cmd:            Help:

      log             View the log of your Harmony Monitor
      status          View the status of your Harmony Monitor daemon
      journal <opts>  View the journal of your Harmony Monitor daemon
      restart         Manually restart your Harmony Monitor daemon
      name            Get the name of your Harmony Monitor deamon
        "
        exit
    esac
    ;;
  "setup-validator")
    python3 -u -c "from AutoNode import validator; validator.setup(recover_interaction=False)"
    ;;
  "activate")
    val_config=$(python3 -c "from AutoNode import common; import json; print(json.dumps(common.validator_config))")
    node_config=$(python3 -c "from AutoNode import common; import json; print(json.dumps(common.node_config))")
    addr=$(echo "$val_config" | jq -r '.["validator-addr"]')
    endpoint=$(echo "$node_config" | jq -r ".endpoint")
    pw_file=$(python3 -c "from AutoNode import common; print(common.saved_wallet_pass_path)")
    if [ -f "$HOME"/hmy ]; then
      "$HOME"/hmy staking edit-validator --validator-addr "$addr" --active true --passphrase-file "$pw_file" -n "$endpoint" | jq
    else
      echo "[AutoNode] Harmony CLI has been moved. Reinitlize AutoNode."
    fi
    ;;
  "deactivate")
    val_config=$(python3 -c "from AutoNode import common; import json; print(json.dumps(common.validator_config))")
    node_config=$(python3 -c "from AutoNode import common; import json; print(json.dumps(common.node_config))")
    addr=$(echo "$val_config" | jq -r '.["validator-addr"]')
    endpoint=$(echo "$node_config" | jq -r ".endpoint")
    pw_file=$(python3 -c "from AutoNode import common; print(common.saved_wallet_pass_path)")
    if [ -f "$HOME"/hmy ]; then
      "$HOME"/hmy staking edit-validator --validator-addr "$addr" --active false --passphrase-file "$pw_file" -n "$endpoint" | jq
    else
      echo "[AutoNode] Harmony CLI has been moved. Reinitlize AutoNode."
    fi
    ;;
  "info")
    val_config=$(python3 -c "from AutoNode import common; import json; print(json.dumps(common.validator_config))")
    node_config=$(python3 -c "from AutoNode import common; import json; print(json.dumps(common.node_config))")
    addr=$(echo "$val_config" | jq -r '.["validator-addr"]')
    endpoint=$(echo "$node_config" | jq -r ".endpoint")
    if [ -f "$HOME"/hmy ]; then
      "$HOME"/hmy blockchain validator information "$addr" -n "$endpoint" | jq
    else
      echo "[AutoNode] Harmony CLI has been moved. Reinitlize AutoNode."
    fi
    ;;
  "config")
    python3 -c "from AutoNode import common; import json; print(json.dumps(common.validator_config))" | jq
    ;;
  "edit-config")
    nano "$(python3 -c "from AutoNode import common; print(common.saved_validator_path)")"
    ;;
  "cleanse-bls")
    echo "[AutoNode] Not implemented yet"  # TODO: implement this
    ;;
  "balances")
    val_config=$(python3 -c "from AutoNode import common; import json; print(json.dumps(common.validator_config))")
    node_config=$(python3 -c "from AutoNode import common; import json; print(json.dumps(common.node_config))")
    addr=$(echo "$val_config" | jq -r '.["validator-addr"]')
    endpoint=$(echo "$node_config" | jq -r ".endpoint")
    if [ -f "$HOME"/hmy ]; then
      "$HOME"/hmy balances "$addr" -n "$endpoint" | jq
    else
      echo "[AutoNode] Harmony CLI has been moved. Reinitlize AutoNode."
    fi
    ;;
  "collect-rewards")
    val_config=$(python3 -c "from AutoNode import common; import json; print(json.dumps(common.validator_config))")
    addr=$(echo "$val_config" | jq -r '.["validator-addr"]')
    if [ -f "$HOME"/hmy ]; then
      "$HOME"/hmy staking collect-rewards --delegator-addr "$addr" -n "$endpoint" | jq
    else
      echo "[AutoNode] Harmony CLI has been moved. Reinitlize AutoNode."
    fi
    ;;
  "version")
    node_dir=$(python3 -c "from AutoNode import common; print(common.node_dir)")
    owd=$(pwd)
    cd "$node_dir" && ./node.sh -V && ./node.sh -v && cd "$owd" || echo "[AutoNode] Node files not found..."
    ;;
  "header")
    if [ -f "$HOME"/hmy ]; then
      "$HOME"/hmy blockchain latest-header | jq
    else
      echo "[AutoNode] Harmony CLI has been moved. Reinitlize AutoNode."
    fi
    ;;
  "headers")
    if [ -f "$HOME"/hmy ]; then
      "$HOME"/hmy blockchain latest-headers | jq
    else
      echo "[AutoNode] Harmony CLI has been moved. Reinitlize AutoNode."
    fi
    ;;
  "clear-node-bls")
    daemon_name=$(python3 -c "from AutoNode.daemon import Daemon; print(Daemon.name)")
    if systemctl --type=service --state=active | grep -e ^"$daemon_name"; then
      echo "[AutoNode] AutoNode is still running. Kill with 'auto_node.sh kill' before clearning BLS keys."
      exit 4
    fi
    bls_key_dir=$(python3 -c "from AutoNode import common; print(common.bls_key_dir)")
    echo "[AutoNode] removing directory: $bls_key_dir"
    rm -rf "$bls_key_dir"
    ;;
  "kill")
    daemon_name=$(python3 -c "from AutoNode.daemon import Daemon; print(Daemon.name)")
    sudo systemctl stop "$daemon_name"* || true
    ;;
  *)
    echo "
      == Harmony AutoNode help message ==
      Note that all sensitive files are saved with read only access for user $USER.

      To auto-reset your node during hard refreshes (for testnets), user $USER must have sudo access
      with no passphrase since the monitor daemon needs to stop and start the node daemon.


      Param:              Help:

      run <run params>    Main execution to run a node. If errors are given
                           for other params, this needs to be ran. Use '-h' param for run param msg
      init                Initlize AutoNode config. First fallback if any errors
      config              View the validator_config.json file used by AutoNode
      edit-config         Edit the validator_config.json file used by AutoNode
      monitor <cmd>       View/Command Harmony Node Monitor. Use '-h' cmd for node monitor cmd help msg
      node <cmd>          View/Command Harmony Node. Use '-h' cmd for node cmd help msg
      setup-validator     Run through the steps to setup your validator
      activate            Make validator associated with node elegable for election in next epoch
      deactivate          Make validator associated with node NOT elegable for election in next epoch.
                           Note that this may not work as intended if auto-active was enabled
      info                Fetch information for validator associated with node
      cleanse-bls <opts>  Remove BLS keys from validaor that are not earning. Use '-h' opts for opts help msg
      balances            Fetch balances for validator associated with node
      collect-rewards     Collect rewards for the associated validator
      version             Fetch the version of the node
      header              Fetch the latest header (shard chain) for the node
      headers             Fetch the latest headers (beacon and shard chain) for the node
      clear-node-bls      Remove the BLS key directory used by the node.
      kill                Safely kill AutoNode & its monitor (if alive)
    "
    exit
    ;;
esac