#!/bin/bash
set -e

if [ "$(uname)" -ne "Linux" ]; then
  echo "[AutoNode] not on a Linux machine, exiting."
  exit
fi
if ! command -v systemctl > /dev/null; then
  echo "[AutoNode] machine does not have systemd, exiting."
  exit
fi
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

systemd_service="[Unit]
Description=Run a Harmony Blockchain Node with AutoNode

[Service]
Type=simple
ExecStart=/bin/bash /usr/bin/autonode_service.sh
Restart=on-failure
RestartSec=1
User=$USER

[Install]
WantedBy=multi-user.target
"

pip3 install AutoNode --upgrade
python3 -c "import AutoNode"  # Init AutoNode
sudo curl -o /usr/bin/autonode_service.sh https://raw.githubusercontent.com/harmony-one/auto-node/master/autonode_service.sh
sudo chmod +x /usr/bin/autonode_service.sh
sudo echo "$systemd_service" | sudo tee /etc/systemd/system/autonoded.service
sudo chmod 644 /etc/systemd/system/autonoded.service
curl -O https://raw.githubusercontent.com/harmony-one/auto-node/master/scripts/auto_node.sh
chmod +x ./auto_node.sh
./auto_node.sh setup