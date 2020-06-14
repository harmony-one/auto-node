#!/bin/bash
set -e

tui_path=$(python3 -c "from AutoNode import common; print(common.tui_path)")


case "${1}" in
  "run")
    node_dir=$(python3 -c "from AutoNode import common; print(common.node_dir)")
    val_config=$(python3 -c "from AutoNode import common; import json; print(json.dumps(common.validator_config))")
    cli_bin_path=$(python3 -c "from AutoNode import common; print(common.cli_bin_path)")
    addr=$(echo "$val_config" | jq -r '.["validator-addr"]')
    "$tui_path" --address "$addr" --hmyPath "$cli_bin_path" --logPath "$node_dir"/latest
  ;;
  "custom-run")
    "$tui_path" "${@:2}"
  ;;
  "update")
    tui_source=$(python3 -c "from AutoNode import common; print(common.tui_source)")
    curl -o "$tui_path" "$tui_source"
    chmod +x "$tui_path"
  ;;
  "version")
    "$tui_path" --version
  ;;
  *)
    echo "
      == AutoNode TUI command help ==

      Usage: auto-node tui <cmd>

      Cmd:              Help:

      run [cmd]         Run the TUI with AutoNode's params (validator address, CLI, and log directory) filled out.
                         One can add additional commands if desired. Use the -h command to view all options.
      custom-run <cmd>  Run the TUI with custom params. Use the -h command to view all options.
      update            Update/download the latest TUI.
      "
      exit
    ;;
esac
