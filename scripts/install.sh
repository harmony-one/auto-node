#!/bin/bash
set -e

if ! command -v python3 > /dev/null; then
  echo "[AutoNode] python3 is not installed, please install that first."
  exit
fi

if ! command -v pip3 > /dev/null; then
  echo "[AutoNode] pip3 is not installed, please install that first."
  exit
fi

if [ -f ./auto_node.sh ]; then
    echo "[AutoNode] Would you like to replace existing ./auto_node.sh (y/n)?"
    read -r answer
    if [ "$answer" != "${answer#[Yy]}" ] ;then
        rm ./auto_node.sh
    else
        exit
    fi
fi

pip3 install AutoNode --upgrade
python3 -c "import AutoNode"  # Init AutoNode
curl -O https://raw.githubusercontent.com/harmony-one/auto-node/master/scripts/auto_node.sh
chmod +x ./auto_node.sh
./auto_node.sh setup