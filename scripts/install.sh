#!/usr/bin/env bash
set -e

stable_auto_node_version="0.4.1"


if command -v auto-node > /dev/null; then
  first_install=False
else
  first_install=True
fi

function check_min_dependencies(){
  if [ "$(uname)" != "Linux" ]; then
    echo "[AutoNode] not on a Linux machine, exiting."
    exit
  fi
  if ! command -v systemctl > /dev/null; then
    echo "[AutoNode] distro does not have systemd, exiting."
    exit
  fi
  systemctl > /dev/null  # Check if systemd is ran with PID 1
}

function setup_check_and_install(){
  unset PKG_INSTALL
  if command -v yum > /dev/null; then
    sudo yum update -y
    PKG_INSTALL='sudo yum install -y'
  fi
  if command -v apt-get > /dev/null; then
    sudo apt update -y
    PKG_INSTALL='sudo apt-get install -y'
  fi
}

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

function check_and_install_dependencies(){
  echo "[AutoNode] Checking dependencies..."
  setup_check_and_install
  for dependency in "python3" "python3-pip" "jq" "unzip" "nano" "curl" "bc"; do
    check_and_install "$dependency"
  done

  if ! command -v rclone > /dev/null; then
    echo "[AutoNode] Installing rclone dependency for fast db syncing"
    curl https://rclone.org/install.sh | sudo bash
    mkdir -p ~/.config/rclone
  fi
  if ! grep -q 'harmony' ~/.config/rclone/rclone.conf 2> /dev/null; then
    echo "[AutoNode] Adding [harmony] profile to rclone.conf"
    echo "[harmony]
type = s3
provider = AWS
env_auth = false
region = us-west-1
acl = public-read" >> "$HOME/.config/rclone/rclone.conf"
  fi

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
  python3 -m pip install --upgrade pip || sudo -H python3 -m pip install --upgrade pip || echo "[AutoNode] cannot update your pip3, attempting install anyways..."
}

function install_python_lib(){
  echo "[AutoNode] Removing existing AutoNode installation"
  python3 -m pip uninstall AutoNode -y 2>/dev/null || sudo python3 -m pip uninstall AutoNode -y 2>/dev/null || echo "[AutoNode] Was not installed..."
  echo "[AutoNode] Installing main python3 library"
  python3 -m pip install AutoNode=="$stable_auto_node_version" --no-cache-dir --user || sudo python3 -m pip install AutoNode=="$stable_auto_node_version" --no-cache-dir
  echo "[AutoNode] Initilizing python3 library"
  python3 -c "from AutoNode import common; common.save_validator_config()" > /dev/null
  python3 -c "from AutoNode import initialize; initialize.make_directories()" > /dev/null
}

function install_cli(){
  echo "[AutoNode] Installing Harmony CLI"
  curl -s -LO https://harmony.one/hmycli && mv hmycli "$HOME"/hmy && chmod +x "$HOME"/hmy
}

function install(){
  systemd_service="[Unit]
Description=Harmony AutoNode %I service
After=network.target

[Service]
Type=simple
ExecStart=$(command -v python3) -u $HOME/bin/autonode-service.py %I
StandardError=syslog

[Install]
WantedBy=multi-user.target
"
  daemon_name=$(python3 -c "from AutoNode import daemon; print(daemon.name)")
  harmony_dir=$(python3 -c "from AutoNode import common; print(common.harmony_dir)")
  user_systemd_dir="$HOME/.config/systemd/user"

  if systemctl --user --type=service --state=active | grep -e ^"$daemon_name"; then
    echo "[AutoNode] Detected running AutoNode. Must stop existing AutoNode to continue. Proceed (y/n)?"
    yes_or_exit
    if ! auto-node kill; then
       echo "[AutoNode] Could not kill existing AutoNode, exiting"
       exit 3
    fi
  fi
  if pgrep harmony; then
    echo "[AutoNode] Harmony process is running, kill it for upgrade (y/n)?"
    yes_or_exit
    killall harmony
  fi

  echo "[AutoNode] Installing AutoNode wrapper script"
  mkdir -p "$harmony_dir" "$HOME/bin"
  # TODO: change this back to master
  curl -s -o "$HOME/bin/auto-node"  https://raw.githubusercontent.com/harmony-one/auto-node/mainnet-pt2/scripts/auto-node.sh
  chmod +x "$HOME/bin/auto-node"
  for auto_node_script in "run.py" "cleanse-bls.py" "tui.sh" "monitor.sh" "node.sh"; do
    # TODO: change this back to master
    curl -s -o "$harmony_dir/$auto_node_script" "https://raw.githubusercontent.com/harmony-one/auto-node/mainnet-pt2/scripts/$auto_node_script"
  done
  export PATH=$PATH:~/bin
  if [ -f "$HOME/.zshrc" ]; then
    # shellcheck disable=SC2016
    echo 'export PATH=$PATH:~/bin' >> "$HOME/.zshrc"
  elif [ -f "$HOME/.bashrc" ]; then
    # shellcheck disable=SC2016
    echo 'export PATH=$PATH:~/bin' >> "$HOME/.bashrc"
  else
    echo "[AutoNode] Could not add \"export PATH=\$PATH:~/bin\" to rc shell file, please do so manually!"
    sleep 3
  fi
  auto-node tui update

  echo "[AutoNode] Installing AutoNode daemon: $daemon_name"
  # TODO: change this back to master
  curl -s -o "$HOME"/bin/autonode-service.py https://raw.githubusercontent.com/harmony-one/auto-node/mainnet-pt2/scripts/autonode-service.py
  mkdir -p "$user_systemd_dir"
  echo "$systemd_service" > "$user_systemd_dir/$daemon_name@.service"
  chmod 644 "$user_systemd_dir/$daemon_name@.service"
  systemctl --user daemon-reload
  systemctl --user enable "$daemon_name@.service"
}

function main(){
  check_min_dependencies

  docs_link="https://docs.harmony.one/home/validators/autonode"
  cli_doc_link="https://docs.harmony.one/home/wallets/harmony-cli"
  echo "[AutoNode] Starting installation for user $USER (with home: $HOME)"
  echo "[AutoNode] Will install the following:"
  echo "           * Python 3.6 if needed and upgrade pip3"
  echo "           * AutoNode ($stable_auto_node_version) python3 library and all dependencies"
  echo "           * autonode-service.py service script in $HOME/bin"
  echo "           * auto-node.sh in $HOME/bin"
  echo "           * validator_config.json config file in $HOME"
  echo "           * harmony node files generated in $HOME/harmony_node"
  echo "           * supporting script, saved configs, and BLS key(s) will be generated/saved in $HOME/.hmy"
  echo "           * add \"$HOME/bin\" to path in .bashrc or .zshrc (if possible)"
  echo "[AutoNode] Reference the documentation here: $docs_link"
  echo "[AutoNode] Sudo access may be required on installation, install script will prompt for passphrase when needed."
  echo "[AutoNode] Continue to install (y/n)?"
  yes_or_exit

  echo "[AutoNode] Installing for user $USER"
  if (( "$EUID" == 0 )); then
    echo "[AutoNode] WARNING: You are installing as root, which is not recommended."
    echo "[AutoNode] If you proceed, you must run AutoNode as root."
    echo "[AutoNode] Continue (y/n)?"
    yes_or_exit
  fi

  check_and_install_dependencies
  install_python_lib
  install_cli
  install

  echo "[AutoNode] Installation complete!"
  echo -e "[AutoNode] Help message for \033[0;92mauto-node\033[0m"
  auto-node -h
  echo ""
  # shellcheck disable=SC2016
  run_cmd='export PATH=$PATH:~/bin'
  if [ "$first_install" == "True" ]; then
    echo -e "[AutoNode] Before you can use the \033[0;92mauto-node\033[0m command, you must add \033[0;92mauto-node\033[0m to path."
    echo -e "[AutoNode] You can do so by reloading your shell, or execute the following command: \e[38;5;0;48;5;255m$run_cmd\e[0m"
    echo ""
  fi
  echo -e "[AutoNode] \033[1;33mNote that you have to import/generate your validator wallet using"
  echo -e "           the Harmony CLI before you can use validator features.\033[0m"
  run_cmd="auto-node hmy keys add example-validator-wallet-name"
  echo -e "           Generate a wallet with the following command: \e[38;5;0;48;5;255m$run_cmd\e[0m"
  echo -e "           Import a wallet following the documentation here: $cli_doc_link"
  echo ""
  run_cmd="auto-node run --fast-sync"
  echo -e "[AutoNode] Start your validator with: \e[38;5;0;48;5;255m$run_cmd\e[0m"
  echo "[AutoNode] Reference the documentation here: $docs_link"
  echo ""
}

if [ "$1" != "source" ]; then
  main
fi