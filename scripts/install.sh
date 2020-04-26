#!/usr/bin/env bash
set -e

if [ "$(uname)" != "Linux" ]; then
  echo "[AutoNode] not on a Linux machine, exiting."
  exit
fi
if ! command -v systemctl > /dev/null; then
  echo "[AutoNode] distro does not have systemd, exiting."
  exit
fi


stable_auto_node_version="0.2.8"

function check_and_install(){
  pkg=$1
  if ! command -v "$pkg" > /dev/null; then
    if [ -z "$PKG_INSTALL" ]; then
      echo "[AutoNode] Unknown package manager, please install $pkg and run install again."
      exit 2
    else
      echo "[AutoNode] Installing $pkg"
      $PKG_INSTALL "$pkg"
    fi
  fi
}

function yes_or_exit(){
  read -r reply
  if [[ ! $reply =~ ^[Yy]$ ]]
  then
    exit 1
  fi
}

echo "[AutoNode] Starting installation for user $USER (with home: $HOME)"
echo "[AutoNode] Will install the following:"
echo "           * Python 3.6 if needed and upgrade pip3"
echo "           * AutoNode ($stable_auto_node_version) python3 library and all dependencies"
echo "           * autonode_service.py service script in $HOME/bin"
echo "           * auto_node.sh main shell script in $HOME"
echo "           * validator_config.json config file in $HOME"
echo "           * harmony node files generated in $HOME/harmony_node"
echo "           * supporting script, saved configs, and BLS key(s) will be generated/saved in $HOME/.hmy"
echo "[AutoNode] Continue to install (y/n)?"
yes_or_exit

if (( "$EUID" == 0 )); then
  echo "You are installing as root, which is not recommended. Continue (y/n)?"
  yes_or_exit
fi

echo "[AutoNode] Installing for user $USER"
echo "[AutoNode] Checking dependencies..."
unset PKG_INSTALL
if command -v yum > /dev/null; then
  sudo yum update
  PKG_INSTALL='sudo yum install -y'
fi
if command -v apt-get > /dev/null; then
  sudo apt update
  PKG_INSTALL='sudo apt-get install -y'
fi
for dependency in "python3" "python3-pip" "jq" "unzip" "nano" "curl" "bc"; do
  check_and_install "$dependency"
done


python_version=$(python3 -V | cut -d ' ' -f2 | cut -d '.' -f1-2)
if (( $(echo "3.6 > $python_version" | bc -l) )); then
  if command -v apt-get > /dev/null; then
    echo "[AutoNode] Must have python 3.6 or higher. Automatically upgrade (y/n)?"
    yes_or_exit
    sudo add-apt-repository ppa:deadsnakes/ppa -y
    sudo apt update -y
    sudo apt install python3.6 -y
    sudo update-alternatives --install "$(command -v python3)" python3 "$(command -v python3.6)" 1
  else
    echo "[AutoNode] Must have python 3.6 or higher. Please install that first before installing AutoNode. Exiting..."
    exit 5
  fi
fi

echo "[AutoNode] Upgrading pip3"
pip3 install --upgrade pip || sudo -H pip3 install --upgrade pip || echo "[AutoNode] cannot update your pip3, attempting install anyways..."
echo "[AutoNode] Removing existing AutoNode installation"
pip3 uninstall AutoNode -y 2>/dev/null || sudo pip3 uninstall AutoNode -y 2>/dev/null || echo "[AutoNode] Was not installed..."
echo "[AutoNode] Installing main python3 library"
pip3 install AutoNode=="$stable_auto_node_version" --no-cache-dir --user || sudo pip3 install AutoNode=="$stable_auto_node_version" --no-cache-dir
echo "[AutoNode] Initilizing python3 library"
python3 -c "from AutoNode import common; common.save_validator_config()" > /dev/null

daemon_name=$(python3 -c "from AutoNode.daemon import Daemon; print(Daemon.name)")
if systemctl --type=service --state=active | grep -e ^"$daemon_name"; then
  echo "[AutoNode] Detected running AutoNode. Must stop existing AutoNode to continue. Proceed (y/n)?"
  yes_or_exit
  if ! "$HOME"/auto_node.sh kill; then
     echo "[AutoNode] Could not kill existing AutoNode, exiting"
     exit 3
  fi
fi
if pgrep harmony; then
  echo "[AutoNode] Harmony process is running, kill it for upgrade (y/n)?"
  yes_or_exit
  killall harmony
fi

systemd_service="[Unit]
Description=Harmony AutoNode %I service

[Service]
Type=simple
ExecStart=$(command -v python3) -u $HOME/bin/autonode_service.py %I
User=$USER

[Install]
WantedBy=multi-user.target
"

echo "[AutoNode] Installing Harmony CLI"
curl -s -LO https://harmony.one/hmycli && mv hmycli "$HOME"/hmy && chmod +x "$HOME"/hmy
harmony_dir=$(python3 -c "from AutoNode import common; print(common.harmony_dir)")
mkdir -p "$harmony_dir"
echo "[AutoNode] Installing AutoNode wrapper script"
curl -s -o "$HOME"/auto_node.sh  https://raw.githubusercontent.com/harmony-one/auto-node/master/scripts/auto_node.sh
chmod +x "$HOME"/auto_node.sh
curl -s -o "$harmony_dir"/init.py https://raw.githubusercontent.com/harmony-one/auto-node/master/scripts/init.py
daemon_name=$(python3 -c "from AutoNode.daemon import Daemon; print(Daemon.name)")
echo "[AutoNode] Installing AutoNode daemon: $daemon_name"
mkdir -p "$HOME"/bin
curl -s -o "$HOME"/bin/autonode_service.py https://raw.githubusercontent.com/harmony-one/auto-node/master/scripts/autonode_service.py
sudo echo "$systemd_service" | sudo tee /etc/systemd/system/"$daemon_name"@.service > /dev/null
sudo chmod 644 /etc/systemd/system/"$daemon_name"@.service
sudo systemctl daemon-reload

if ! command -v rclone > /dev/null; then
  echo "[AutoNode] Installing rclone dependency for fast db syncing"
  curl https://rclone.org/install.sh | sudo bash
  mkdir -p ~/.config/rclone
fi
if ! grep -q 'hmy' ~/.config/rclone/rclone.conf 2> /dev/null; then
  echo "[AutoNode] Adding [hmy] profile to rclone.conf"
  cat<<-EOT>>~/.config/rclone/rclone.conf
[hmy]
type = s3
provider = AWS
env_auth = false
region = us-west-1
acl = public-read
EOT
fi

echo "[AutoNode] Installation complete!"
echo "[AutoNode] Help message for auto_node.sh:"
"$HOME"/auto_node.sh -h
echo ""
echo "[AutoNode] Note that you have to import your wallet using the Harmony CLI before"
echo "           you can use validator features of AutoNode."
run_cmd="$HOME/auto_node.sh run --auto-active --clean"
echo -e "[AutoNode] Start your AutoNode with: \e[38;5;0;48;5;255m$run_cmd\e[0m"
echo ""
