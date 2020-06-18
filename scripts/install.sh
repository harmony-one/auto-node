#!/usr/bin/env bash
set -e

stable_auto_node_version="0.6.1"

if command -v auto-node >/dev/null; then
  first_install=False
else
  first_install=True
fi

function yes_or_exit() {
  read -r reply
  if [[ ! $reply =~ ^[Yy]$ ]]; then
    exit 1
  fi
}

function _fix_user_systemd() {
  if systemctl | grep user@ >/dev/null; then
    echo "[AutoNode] try starting systemd for user? (y/n)"
    yes_or_exit
    sudo systemctl start user@$UID.service
    sudo systemctl enable user@$UID.service
  fi
  if ! systemctl --user >/dev/null; then
    echo "[AutoNode] install user service for systemd? (y/n)"
    yes_or_exit
    user_service="[Unit]
Description=User Manager for UID %i
After=systemd-user-sessions.service

[Service]1
User=%i
PAMName=systemd-user
Type=notify
ExecStart=-/lib/systemd/systemd --user
Slice=user-%i.slice
KillMode=mixed
Delegate=yes
TasksMax=infinity"
    sudo echo "$user_service" | sudo tee /etc/systemd/system/user@.service >/dev/null
    sudo systemctl daemon-reload
    sudo systemctl enable user@$UID.service
    sudo systemctl start user@$UID.service
  fi
}

function check_min_dependencies() {
  if [ "$(uname)" != "Linux" ]; then
    echo "[AutoNode] Not on a Linux machine, exiting."
    exit
  fi
  if ! command -v systemctl >/dev/null; then
    echo "[AutoNode] Distro does not have systemd, exiting."
    exit
  fi
  systemctl >/dev/null # Check if systemd is ran with PID 1
  if ! systemctl --user >/dev/null; then
    echo "[AutoNode] Cannot access systemd in user mode"
    _fix_user_systemd
    if ! systemctl --user >/dev/null; then
      echo "[AutoNode] Unable to fix access to systemd in user mode, exiting."
      exit
    else
      echo "[AutoNode] Successfully fixed access to systemd in user mode."
    fi
  fi
}

function setup_check_and_install() {
  unset PKG_INSTALL
  if command -v yum >/dev/null; then
    sudo yum update -y
    PKG_INSTALL='sudo yum install -y'
  fi
  if command -v apt-get >/dev/null; then
    sudo apt update -y
    PKG_INSTALL='sudo apt-get install -y'
  fi
}

function check_and_install() {
  pkg=$1
  if ! command -v "$pkg" >/dev/null; then
    if [ -z "$PKG_INSTALL" ]; then
      echo "[AutoNode] Unknown package manager, please install $pkg and run install again."
      exit 2
    else
      echo "[AutoNode] Installing $pkg"
      $PKG_INSTALL "$pkg"
    fi
  fi
}

function check_and_install_dependencies() {
  echo "[AutoNode] Checking dependencies..."
  setup_check_and_install
  for dependency in "python3" "python3-pip" "unzip" "nano" "curl" "bc" "jq"; do
    check_and_install "$dependency"
  done

  if ! command -v rclone >/dev/null; then
    echo "[AutoNode] Installing rclone dependency for fast db syncing"
    curl https://rclone.org/install.sh | sudo bash
  fi
  rclone_config_path=$(rclone config file)
  rclone_config_path=${rclone_config_path/$'\n'/}
  rclone_config_path="$(echo "$rclone_config_path" | rev | cut -d: -f1 | rev)"
  mkdir -p "$(dirname "$rclone_config_path")"
  if ! grep -q harmony "$rclone_config_path" 2>/dev/null; then
    echo "[AutoNode] Adding [harmony] profile to rclone.conf"
    echo "[harmony]
type = s3
provider = AWS
env_auth = false
region = us-west-1
acl = public-read" >>"$rclone_config_path"
  fi

  python_version=$(python3 -V | cut -d ' ' -f2 | cut -d '.' -f1-2)
  if (($(echo "3.6 > $python_version" | bc -l))); then
    if command -v apt-get >/dev/null; then
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

function install_python_lib() {
  echo "[AutoNode] Removing existing AutoNode installation"
  python3 -m pip uninstall AutoNode -y 2>/dev/null || sudo python3 -m pip uninstall AutoNode -y 2>/dev/null || echo "[AutoNode] Was not installed..."
  echo "[AutoNode] Installing main python3 library"
  python3 -m pip install AutoNode=="$stable_auto_node_version" --no-cache-dir --user || sudo python3 -m pip install AutoNode=="$stable_auto_node_version" --no-cache-dir
  echo "[AutoNode] Initilizing python3 library"
  python3 -c "from AutoNode import common; common.save_validator_config()"
  python3 -c "from AutoNode import initialize; initialize.make_directories()"
}

# TODO: set-up versioned install...
function install() {
  systemd_service="[Unit]
Description=Harmony AutoNode %I service
After=network.target
After=user@.service

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

  if systemctl --user --type=service --all --state=active | grep "$daemon_name"; then
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

  mkdir -p "$harmony_dir" "$HOME/bin" "$user_systemd_dir"

  echo "[AutoNode] Installing AutoNode daemon: $daemon_name"
  # TODO: change this back to master
  curl -s -o "$HOME"/bin/autonode-service.py https://raw.githubusercontent.com/harmony-one/auto-node/mainnet-pt2/scripts/autonode-service.py
  echo "$systemd_service" >"$user_systemd_dir/$daemon_name@.service"
  chmod 644 "$user_systemd_dir/$daemon_name@.service"
  systemctl --user daemon-reload
  services=$(python3 -c "from AutoNode import daemon; print(' '.join(daemon.services))")
  for service in $services; do
    systemctl --user enable "$daemon_name@$service.service" || true
  done

  echo "[AutoNode] Installing AutoNode wrapper script"
  # TODO: change this back to master
  curl -s -o "$HOME/bin/auto-node" https://raw.githubusercontent.com/harmony-one/auto-node/mainnet-pt2/scripts/auto-node.sh
  chmod +x "$HOME/bin/auto-node"
  for auto_node_script in "run.py" "cleanse-bls.py" "tui.sh" "monitor.sh" "node.sh" "tune.py"; do
    # TODO: change this back to master
    curl -s -o "$harmony_dir/$auto_node_script" "https://raw.githubusercontent.com/harmony-one/auto-node/mainnet-pt2/scripts/$auto_node_script"
  done
  export PATH=$PATH:~/bin
  # shellcheck disable=SC2016
  if [ -f "$HOME/.zshrc" ]; then
    if ! grep 'PATH=$PATH:~/bin' "$HOME/.zshrc" >/dev/null; then
      echo 'export PATH=$PATH:~/bin' >>"$HOME/.zshrc"
    fi
  elif [ -f "$HOME/.bashrc" ]; then
    if ! grep 'PATH=$PATH:~/bin' "$HOME/.bashrc" >/dev/null; then
      echo 'export PATH=$PATH:~/bin' >>"$HOME/.bashrc"
    fi
  else
    echo "[AutoNode] Could not add \"export PATH=\$PATH:~/bin\" to rc shell file, please do so manually!"
    sleep 3
  fi
  auto-node tui update || echo "[AutoNode] Failed to install TUI, continuing..."
}

function main() {
  check_min_dependencies

  docs_link="https://docs.harmony.one/home/validators/autonode"
  cli_doc_link="https://docs.harmony.one/home/wallets/harmony-cli"
  echo "[AutoNode] Starting installation for user $USER (with home: $HOME)"
  echo "[AutoNode] Will install the following:"
  echo "           * Python 3.6 if needed and upgrade pip3"
  echo "           * AutoNode ($stable_auto_node_version) python3 library and all dependencies"
  echo "           * autonode-service.py service script in $HOME/bin"
  echo "           * auto-node.sh in $HOME/bin"
  echo "           * harmony_validator_config.json config file in $HOME"
  echo "           * harmony node files generated in $HOME/harmony_node"
  echo "           * supporting script, saved configs, and BLS key(s) will be generated/saved in $HOME/.hmy"
  echo "           * add \"$HOME/bin\" to path in .bashrc or .zshrc (if possible)"
  echo "[AutoNode] Reference the documentation here: $docs_link"
  echo "[AutoNode] Sudo access may be required on installation, install script will prompt for passphrase when needed."
  echo "[AutoNode] Continue to install (y/n)?"
  yes_or_exit

  echo "[AutoNode] Installing for user $USER"
  if (("$EUID" == 0)); then
    echo "[AutoNode] WARNING: You are installing as root, which is not recommended."
    echo "[AutoNode] If you proceed, you must run AutoNode as root."
    echo "[AutoNode] Continue (y/n)?"
    yes_or_exit
  fi

  check_and_install_dependencies
  install_python_lib
  install

  # TODO: add optimization check (like first install) & only execute if needed...
  echo ""
  echo "[AutoNode] Optimize OS for running a harmony node (y/n)?"
  read -r reply
  if [[ $reply =~ ^[Yy]$ ]]; then
    auto-node tune kernel --save || true
    auto-node tune network --save || true
    run_cmd="auto-node tune restore"
    echo -e "[AutoNode] Note that all optimizations can be undone with \e[38;5;0;48;5;255m$run_cmd\e[0m"
    echo ""
  fi

  echo "[AutoNode] Installation complete!"
  echo -e "[AutoNode] Help message for \033[0;92mauto-node\033[0m"
  auto-node -h
  echo ""
  # shellcheck disable=SC2016
  run_cmd="export PATH=\$PATH:$HOME/bin"
  if [ "$first_install" == "True" ]; then
    echo -e "[AutoNode] Before you can use the \033[0;92mauto-node\033[0m command, you must add \033[0;92mauto-node\033[0m to path."
    echo -e "[AutoNode] You can do so by reloading your shell, or execute the following command: \e[38;5;0;48;5;255m$run_cmd\e[0m"
    echo ""
  fi

  # TODO: add wallet count check & only print if needed...
  echo -e "[AutoNode] \033[1;33mNote that you have to import/generate your validator wallet using"
  echo -e "           the Harmony CLI before you can use validator features.\033[0m"
  run_cmd="auto-node hmy keys add example-validator-wallet-name"
  echo -e "           Generate a wallet with the following command: \e[38;5;0;48;5;255m$run_cmd\e[0m"
  echo -e "           Import a wallet following the documentation here: $cli_doc_link"
  echo ""

  run_cmd="auto-node run --fast-sync"
  echo -e "[AutoNode] Start your node with: \e[38;5;0;48;5;255m$run_cmd\e[0m"
  echo "[AutoNode] Reference the documentation here: $docs_link"
}

if [ "$1" != "source" ]; then
  main
fi
