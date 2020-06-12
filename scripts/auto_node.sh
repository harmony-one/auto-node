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
    python3 -u "$harmony_dir"/run.py "${@:2}"
    ;;
  "auth-wallet")
    if [ ! "$(pgrep harmony)" ]; then echo "[AutoNode] Node must be running..." && exit 1; fi
    python3 -u -c "from AutoNode import initialize; initialize.setup_wallet_passphrase()"
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
    python3 -u -c "from AutoNode import validator; validator.activate_validator()"
    ;;
  "deactivate")
    python3 -u -c "from AutoNode import validator; validator.deactivate_validator()"
    ;;
  "info")
    output=$(python3 -u -c "from AutoNode import validator; import json; print(json.dumps(validator.get_validator_information()))")
    echo "$output" | jq || echo "$output"
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
    output=$(python3 -c "from AutoNode import validator; import json; print(json.dumps(validator.get_balances()))")
    echo "$output" | jq || echo "$output"
    ;;
  "collect-rewards")
    python3 -u -c "from AutoNode import validator; validator.collect_reward()"
    ;;
  "version")
    node_dir=$(python3 -c "from AutoNode import common; print(common.node_dir)")
    owd=$(pwd)
    cd "$node_dir" && ./node.sh -V && ./node.sh -v && cd "$owd" || echo "[AutoNode] Node files not found..."
    ;;
  "header")
     output=$(python3 -c "from pyhmy import blockchain; import json; print(json.dumps(blockchain.get_latest_header()))")
     echo "$output" | jq || echo "$output"
    ;;
  "headers")
    output=$(python3 -c "from pyhmy import blockchain; import json; print(json.dumps(blockchain.get_latest_headers()))")
    echo "$output" | jq || echo "$output"
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
    $cli_bin "${@:2}"
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
      auth-wallet         Re-auth wallet passphrase if AutoNode expires/invalidates stored passphrase.
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
      hmy <command>       Execute the Harmony CLI with the given command.
                           Use '-h' param to view help msg
      hmy-update          Update the Harmony CLI used for AutoNode
      kill                Safely kill AutoNode & its monitor (if alive)
    "
    exit
    ;;
esac
