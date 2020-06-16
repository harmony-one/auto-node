#!/bin/bash
set -e
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

# shellcheck source=../install.sh
source "$DIR/install.sh" source

check_min_dependencies
check_and_install_dependencies
python3 -m pip install "$DIR/../" --user
install || echo "could not do regular install, could be due to changes, continuing..."
python3 -c "from AutoNode import common; common.save_validator_config()" > /dev/null
harmony_dir=$(python3 -c "from AutoNode import common; print(common.harmony_dir)")
echo "== COPYING OVER/REPLACING DEV AUTONODE SCRIPTS =="
cp -v "$DIR"/../scripts/run.py "$harmony_dir"
cp -v "$DIR"/../scripts/cleanse-bls.py "$harmony_dir"
cp -v "$DIR"/../scripts/tui.sh "$harmony_dir"
cp -v "$DIR"/../scripts/monitor.sh "$harmony_dir"
cp -v "$DIR"/../scripts/node.sh "$harmony_dir"
cp -v "$DIR"/../scripts/tune.py "$harmony_dir"
cp -v "$DIR"/../scripts/auto-node.sh "$HOME/bin" && mv "$HOME/bin/auto-node.sh" "$HOME/bin/auto-node"
cp -v "$DIR"/../scripts/autonode-service.py "$HOME"/bin/autonode-service.py
echo "== FINISHED DEV INSTALL =="