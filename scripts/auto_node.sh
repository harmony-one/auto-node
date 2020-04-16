#!/bin/bash

# Assumes that AutoNode lib is installed
harmony_dir=$(python3 -c "from AutoNode import common; print(common.harmony_dir)")
run_script="$harmony_dir"/run.py

case "${1}" in
  "run")
    monitor_log_path=$(python3 -c "from AutoNode import monitor; print(monitor.log_path)")
    val_tmux_session=$(python3 -c "from AutoNode import validator; print(validator.tmux_session_name)")
    python3 -u "$run_script" "${@:2}"
    until tmux list-session | grep "${val_tmux_session}"
    do
      sleep 1
    done
    unset TMUX  # For nested tmux sessions
    tmux a -t "$val_tmux_session"
    tail -f "$monitor_log_path"
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
   # TODO
    ;;
  "header")
    # TODO
    ;;
  "headers")
    # TODO
    ;;
  "attach")
    # TODO
    ;;
  "kill")
    # TODO
    ;;
  *)
    # TODO
    echo "
      == Harmony auto-node deployment help message ==

      Param:              Help:

      run <run params>    Main execution to run a node. If errors are given
                           for other params, this needs to be ran. Use '-h' for run help msg
      create-validator    Send a create validator transaction with the given config
      activate            Make validator associated with node elegable for election in next epoch
      deactivate          Make validator associated with node NOT elegable for election in next epoch
      info                Fetch information for validator associated with node
      cleanse-bls <opts>  Remove BLS keys from validaor that are not earning. Use '-h' for help msg
      balances            Fetch balances for validator associated with node
      version             Fetch the of the Docker image.
      header              Fetch the latest header (shard chain) for the node
      headers             Fetch the latest headers (beacon and shard chain) for the node
      attach              Attach to the running node
      kill                Safely kill the node
    "
    exit
    ;;
esac