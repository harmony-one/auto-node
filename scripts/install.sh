#!/bin/bash
set -e

if [ -f ./auto_node.sh ]; then
    echo "Would you like to replace existing ./auto_node.sh (y/n)?"
    read -r answer
    if [ "$answer" != "${answer#[Yy]}" ] ;then
        rm ./auto_node.sh
    else
        exit
    fi
fi

curl -O https://raw.githubusercontent.com/harmony-one/auto-node/master/scripts/auto_node.sh
chmod +x ./auto_node.sh
./auto_node.sh setup