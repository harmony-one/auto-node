#!/bin/bash
set -e
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

# shellcheck source=../install.sh
source "$DIR/install.sh" source

check_min_dependencies
check_and_install_dependencies
python3 -m pip install "$DIR/../" --user
install > /dev/null || echo "could not do regular install, could be due to changes, continuing..."
python3 -c "from AutoNode import common; common.save_validator_config()" > /dev/null
harmony_dir=$(python3 -c "from AutoNode import common; print(common.harmony_dir)")
cp "$DIR"/../scripts/init.py "$harmony_dir"
cp "$DIR"/../scripts/cleanse-bls.py "$harmony_dir"
cp "$DIR"/../scripts/tui.sh "$harmony_dir"
cp "$DIR"/../scripts/monitor.sh "$harmony_dir"
cp "$DIR"/../scripts/node.sh "$harmony_dir"
cp "$DIR"/../scripts/auto_node.sh "$HOME"
cp "$DIR"/../scripts/autonode_service.py "$HOME"/bin/autonode_service.py
echo "== FINISHED DEV INSTALL =="