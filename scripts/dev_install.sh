#!/bin/bash
set -e

python3 -m pip install . --user
harmony_dir=$(python3 -c "from AutoNode import common; print(common.harmony_dir)")
cp ./scripts/init.py "$harmony_dir"
cp ./scripts/cleanse-bls.py "$harmony_dir"
cp ./scripts/auto_node.sh "$HOME"
cp ./scripts/autonode_service.py "$HOME"/bin/autonode_service.py
echo "== FINISHED DEV INSTALL =="