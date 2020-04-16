#!/bin/bash
set -e

if [ "$(uname)" != "Linux" ]; then
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
python3 -c "from AutoNode import common; common.save_validator_config()" > /dev/null  # Init AutoNode
curl -LO https://harmony.one/hmycli && mv hmycli "$HOME"/hmy && chmod +x "$HOME"/hmy

harmony_dir=$(python3 -c "from AutoNode import common; print(common.harmony_dir)")
curl -o "$HOME"/auto_node.sh  https://raw.githubusercontent.com/harmony-one/auto-node/migrate_off_docker/scripts/auto_node.sh  # TODO: change back url
chmod +x "$HOME"/auto_node.sh
curl -o "$harmony_dir"/run.py https://raw.githubusercontent.com/harmony-one/auto-node/migrate_off_docker/run.py  # TODO: change back url

daemon_name=$(python3 -c "from AutoNode import common; print(common.daemon_name)")
sudo curl -o /usr/bin/autonode_service.sh https://raw.githubusercontent.com/harmony-one/auto-node/migrate_off_docker/autonode_service.sh  # TODO: change back url
sudo chmod +x /usr/bin/autonode_service.sh
sudo echo "$systemd_service" | sudo tee /etc/systemd/system/"$daemon_name".service
sudo chmod 644 /etc/systemd/system/"$daemon_name".service