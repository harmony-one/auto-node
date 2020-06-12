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
    echo "[AutoNode] Initialized service..."
    daemon_name=$(python3 -c "from AutoNode import daemon; print(daemon.name)")
    sudo systemctl start "$daemon_name"@node.service
    python3 -u -c "from AutoNode import validator; validator.setup(hard_reset_recovery=False)" || true
    sudo systemctl start "$daemon_name"@monitor.service
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
    harmony_dir=$(python3 -c "from AutoNode import common; print(common.harmony_dir)")
    bash "$harmony_dir"/node.sh "${@:2}"
    ;;
  "monitor")
    harmony_dir=$(python3 -c "from AutoNode import common; print(common.harmony_dir)")
    bash "$harmony_dir"/monitor.sh "${@:2}"
    ;;
  "tui")
    harmony_dir=$(python3 -c "from AutoNode import common; print(common.harmony_dir)")
    bash "$harmony_dir"/tui.sh "${@:2}"
    ;;
  "create-validator")
    python3 -u -c "from AutoNode import validator; validator.setup(hard_reset_recovery=False)"
    ;;
  "activate")
    val_config=$(python3 -c "from AutoNode import common; import json; print(json.dumps(common.validator_config))")
    node_config=$(python3 -c "from AutoNode import common; import json; print(json.dumps(common.node_config))")
    addr=$(echo "$val_config" | jq -r '.["validator-addr"]')
    endpoint=$(echo "$node_config" | jq -r ".endpoint")
    pw_file=$(python3 -c "from AutoNode import common; print(common.saved_wallet_pass_path)")
    if [ -f "$HOME"/hmy ]; then
      output=$("$HOME"/hmy staking edit-validator --validator-addr "$addr" --active true --passphrase-file "$pw_file" -n "$endpoint")
      echo "$output" | jq || echo "$output"
    else
      echo "[AutoNode] Harmony CLI has been moved. Reinitialize AutoNode."
    fi
    ;;
  "deactivate")
    val_config=$(python3 -c "from AutoNode import common; import json; print(json.dumps(common.validator_config))")
    node_config=$(python3 -c "from AutoNode import common; import json; print(json.dumps(common.node_config))")
    addr=$(echo "$val_config" | jq -r '.["validator-addr"]')
    endpoint=$(echo "$node_config" | jq -r ".endpoint")
    pw_file=$(python3 -c "from AutoNode import common; print(common.saved_wallet_pass_path)")
    if [ -f "$HOME"/hmy ]; then
      output=$("$HOME"/hmy staking edit-validator --validator-addr "$addr" --active false --passphrase-file "$pw_file" -n "$endpoint")
      echo "$output" | jq || echo "$output"
    else
      echo "[AutoNode] Harmony CLI has been moved. Reinitialize AutoNode."
    fi
    ;;
  "info")
    val_config=$(python3 -c "from AutoNode import common; import json; print(json.dumps(common.validator_config))")
    node_config=$(python3 -c "from AutoNode import common; import json; print(json.dumps(common.node_config))")
    addr=$(echo "$val_config" | jq -r '.["validator-addr"]')
    endpoint=$(echo "$node_config" | jq -r ".endpoint")
    if [ -f "$HOME"/hmy ]; then
      output=$("$HOME"/hmy blockchain validator information "$addr" -n "$endpoint")
      echo "$output" | jq || echo "$output"
    else
      echo "[AutoNode] Harmony CLI has been moved. Reinitialize AutoNode."
    fi
    ;;
  "config")
    python3 -c "from AutoNode import common; import json; print(json.dumps(common.validator_config))" | jq
    ;;
  "edit-config")
    nano "$(python3 -c "from AutoNode import common; print(common.saved_validator_path)")"
    echo "[AutoNode] Would you like to update your validator information on-chain (y/n)?"
    yes_or_exit
    python3 -u -c "from AutoNode import validator; validator.update_info(hard_reset_recovery=False)"
    ;;
  "update-config")
    echo "[AutoNode] Would you like to update your validator information on-chain (y/n)?"
    yes_or_exit
    python3 -u -c "from AutoNode import validator; validator.update_info(hard_reset_recovery=False)"
    ;;
  "cleanse-bls")
    harmony_dir=$(python3 -c "from AutoNode import common; print(common.harmony_dir)")
    python3 -u "$harmony_dir"/cleanse-bls.py "${@:2}"
    ;;
  "balances")
    val_config=$(python3 -c "from AutoNode import common; import json; print(json.dumps(common.validator_config))")
    node_config=$(python3 -c "from AutoNode import common; import json; print(json.dumps(common.node_config))")
    addr=$(echo "$val_config" | jq -r '.["validator-addr"]')
    endpoint=$(echo "$node_config" | jq -r ".endpoint")
    if [ -f "$HOME"/hmy ]; then
      output=$("$HOME"/hmy balances "$addr" -n "$endpoint")
      echo "$output" | jq || echo "$output"
    else
      echo "[AutoNode] Harmony CLI has been moved. Reinitialize AutoNode."
    fi
    ;;
  "collect-rewards")
    val_config=$(python3 -c "from AutoNode import common; import json; print(json.dumps(common.validator_config))")
    addr=$(echo "$val_config" | jq -r '.["validator-addr"]')
    if [ -f "$HOME"/hmy ]; then
      output=$("$HOME"/hmy staking collect-rewards --delegator-addr "$addr" -n "$endpoint")
      echo "$output" | jq || echo "$output"
    else
      echo "[AutoNode] Harmony CLI has been moved. Reinitialize AutoNode."
    fi
    ;;
  "version")
    node_dir=$(python3 -c "from AutoNode import common; print(common.node_dir)")
    owd=$(pwd)
    cd "$node_dir" && ./node.sh -V && ./node.sh -v && cd "$owd" || echo "[AutoNode] Node files not found..."
    ;;
  "header")
    if [ -f "$HOME"/hmy ]; then
      output=$("$HOME"/hmy blockchain latest-header)
      echo "$output" | jq || echo "$output"
    else
      echo "[AutoNode] Harmony CLI has been moved. Reinitialize AutoNode."
    fi
    ;;
  "headers")
    if [ -f "$HOME"/hmy ]; then
      output=$("$HOME"/hmy blockchain latest-headers)
      echo "$output" | jq || echo "$output"
    else
      echo "[AutoNode] Harmony CLI has been moved. Reinitialize AutoNode."
    fi
    ;;
  "clear-node-bls")
    daemon_name=$(python3 -c "from AutoNode import daemon; print(daemon.name)")
    if systemctl --type=service --state=active | grep -e ^"$daemon_name"; then
      echo "[AutoNode] AutoNode is still running. Kill with 'auto_node.sh kill' before cleaning BLS keys."
      exit 4
    fi
    bls_key_dir=$(python3 -c "from AutoNode import common; print(common.bls_key_dir)")
    echo "[AutoNode] removing directory: $bls_key_dir"
    rm -rf "$bls_key_dir"
    ;;
  "hmy")
    cli_bin=$(python3 -c "from AutoNode import common; print(common.cli_bin_path)")
    node_config=$(python3 -c "from AutoNode import common; import json; print(json.dumps(common.node_config))")
    endpoint=$(echo "$node_config" | jq -r ".endpoint")
    $cli_bin -n "$endpoint" "${@:2}"
    ;;
  "hmy-update")
    cli_bin=$(python3 -c "from AutoNode import common; print(common.cli_bin_path)")
    python3 -u -c "from pyhmy import cli; cli.download(\"$cli_bin\", replace=True, verbose=True)"
    ;;
  "kill")
    daemon_name=$(python3 -c "from AutoNode import daemon; print(daemon.name)")
    sudo systemctl stop "$daemon_name"* || true
    ;;
  *)
    echo "
      == Harmony AutoNode help message ==
      Note that all sensitive files are saved with read only access for user $USER.

      To auto-reset your node during hard refreshes (for testnets), user $USER must have sudo access
      with no passphrase since services must be stopped and started by a monitor.


      Param:              Help:

      run <run params>    Main execution to run a node. If errors are given
                           for other params, this needs to be ran. Use '-h' param to view help msg
      init                Initialize AutoNode config. First fallback if any errors
      config              View the validator_config.json file used by AutoNode
      edit-config         Edit the validator_config.json file used by AutoNode and change validator info on-chain
      update-config       Update validator info on-chain with given validator_config.json
      monitor <cmd>       View/Command Harmony Node Monitor. Use '-h' param to view help msg
      node <cmd>          View/Command Harmony Node. Use '-h' params to view help msg
      tui <cmd>           Start the text-based user interface to monitor your node and validator.
                           Use '-h' param to view help msg
      create-validator    Run through the steps to setup your validator
      activate            Make validator associated with node eligible for election in next epoch
      deactivate          Make validator associated with node NOT eligible for election in next epoch.
                           Note that this may not work as intended if auto-active was enabled
      info                Fetch information for validator associated with node
      cleanse-bls <opts>  Remove BLS keys from validator that are not earning. Use '-h' param to view help msg
      balances            Fetch balances for validator associated with node
      collect-rewards     Collect rewards for the associated validator
      version             Fetch the version of the node
      header              Fetch the latest header (shard chain) for the node
      headers             Fetch the latest headers (beacon and shard chain) for the node
      clear-node-bls      Remove the BLS key directory used by the node.
      hmy <command>       Execute the Harmony CLI with the given command on the given beacon endpoint.
                           Use '-h' param to view help msg
      hmy-update          Update the Harmony CLI used for AutoNode
      kill                Safely kill AutoNode & its monitor (if alive)
    "
    exit
    ;;
esac
