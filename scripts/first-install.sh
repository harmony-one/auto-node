#!/bin/bash
set -e

docs_link="https://docs.harmony.one/home/validators/autonode"
cli_doc_link="https://docs.harmony.one/home/wallets/harmony-cli"

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
  for dependency in "jq" "wget"; do
    check_and_install "$dependency"
  done
}

function optimize() {
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
}

function import_wallet_message() {
  echo -e "[AutoNode] \033[1;33mNote that you have to import/generate your validator wallet using"
  echo -e "           the Harmony CLI before you can use validator features.\033[0m"
  run_cmd="auto-node hmy keys add example-validator-wallet-name"
  echo -e "           Generate a wallet with the following command: \e[38;5;0;48;5;255m$run_cmd\e[0m"
  echo -e "           Import a wallet following the documentation here: $cli_doc_link"
  echo ""
}

function start_message() {
  echo -e "[AutoNode] Help message for \033[0;92mauto-node\033[0m"
  auto-node -h
  echo ""

  run_cmd="auto-node run --fast-sync"
  echo -e "[AutoNode] Start your node with: \e[38;5;0;48;5;255m$run_cmd\e[0m"
  echo "[AutoNode] Reference the documentation here: $docs_link"
  echo ""
}

function src_message() {
  run_cmd="export PATH=\$PATH:$HOME/bin"
  echo -e "[AutoNode] Before you can use the \033[0;92mauto-node\033[0m command, you must add \033[0;92mauto-node\033[0m to path."
  echo -e "[AutoNode] You can do so by reloading your shell, or execute the following command: \e[38;5;0;48;5;255m$run_cmd\e[0m"
  echo ""
}

function install() {
  release_info=$(curl --silent "https://api.github.com/repos/harmony-one/auto-node/releases/latest")
  temp_install_script_path="/tmp/auto-node-install.sh"
  install_script=$(echo "$release_info" | jq ".assets" | jq '[.[]|select(.name="install.sh")][0].browser_download_url' -r)
  wget "$install_script" -O "$temp_install_script_path"
  bash "$temp_install_script_path"
  export PATH=$PATH:~/bin
  sudo loginctl enable-linger "$USER"
}

## MAIN IS BELOW ##

check_and_install_dependencies
install
optimize
echo -e "\n[AutoNode] Installation complete!\n"
start_message
import_wallet_message
src_message
