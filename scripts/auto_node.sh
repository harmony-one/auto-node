#!/bin/bash

# Assumes that AutoNode lib is installed
harmony_dir=$(python3 -c "from AutoNode import common; print(common.harmony_dir)")
daemon_name=$(python3 -c "from AutoNode import common; print(common.daemon_name)")
init_script="$harmony_dir"/init.py

case "${1}" in
  "run")
    monitor_log_path=$(python3 -c "from AutoNode import monitor; print(monitor.log_path)")
    validator_log_path=$(python3 -c "from AutoNode import validator; print(validator.log_path)")
    python3 -u "$init_script" "${@:2}"
    sudo systemctl start "$daemon_name".service
    echo "[AutoNode] Initilized service..."
    sleep 5  # Let service init
    python3 -u -c "from AutoNode import validator; validator.setup(recover_interaction=False)" 2>&1 | tee "$validator_log_path"
    tail -f "$monitor_log_path"
    ;;
  "status")
    tail -f "$(python3 -c "from AutoNode import monitor; print(monitor.log_path)")"
    ;;
  "daemon-status")
    sudo systemctl status "$daemon_name".service
    ;;
  "create-validator")
    # TODO
    ;;
  "activate")
    # TODO
    ;;
  "deactivate")
    # TODO
    ;;
  "info")
    # TODO
    ;;
  "cleanse-bls")
    # TODO
    ;;
  "balances")
    # TODO
    ;;
  "version")
    node_dir=$(python3 -c "from AutoNode import common; print(common.node_dir)")
    owd=$(pwd)
    cd "$node_dir" && ./node.sh -V && ./node.sh -v && cd "$owd" || exit
    ;;
  "header")
    if [ -f "$HOME"/hmy ]; then
      "$HOME"/hmy blockchain latest-header
    else
      echo "[AutoNode] Harmony CLI has been moved. Reinstall AutoNode."
    fi
    ;;
  "headers")
    if [ -f "$HOME"/hmy ]; then
      "$HOME"/hmy blockchain latest-headers
    else
      echo "[AutoNode] Harmony CLI has been moved. Reinstall AutoNode."
    fi
    ;;
  "kill")
    sudo systemctl stop "$daemon_name".service
    ;;
  *)
    # TODO
    echo "
      == Harmony auto-node deployment help message ==

      Param:              Help:

      run <run params>    Main execution to run a node. If errors are given
                           for other params, this needs to be ran. Use '-h' for run help msg
      status              View the current status of your Harmony Node
      daemon-status       View the status of the underlying daemon
      create-validator    Send a create validator transaction with the given config
      activate            Make validator associated with node elegable for election in next epoch
      deactivate          Make validator associated with node NOT elegable for election in next epoch
      info                Fetch information for validator associated with node
      cleanse-bls <opts>  Remove BLS keys from validaor that are not earning. Use '-h' for help msg
      balances            Fetch balances for validator associated with node
      version             Fetch the of the node
      header              Fetch the latest header (shard chain) for the node
      headers             Fetch the latest headers (beacon and shard chain) for the node
      kill                Safely kill the node
    "
    exit
    ;;
esac