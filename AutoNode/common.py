import json
import subprocess
import os

daemon_name = "autonoded"
harmony_dir = f"{os.environ['HOME']}/.hmy"
node_dir = f"{os.environ['HOME']}/harmony_node"
node_sh_log_dir = f"{node_dir}/node_sh_logs"
bls_key_dir = f"{harmony_dir}/blskeys"
imported_bls_pass_file_dir = f"{os.environ['HOME']}/bls_pass"
imported_wallet_pass_file_dir = f"{os.environ['HOME']}/wallet_pass"
cli_bin_dir = f"{harmony_dir}/bin"
cli_bin_path = f"{cli_bin_dir}/hmy"
saved_validator_path = f"{os.environ['HOME']}/validator_config.json"
saved_node_path = f"{harmony_dir}/.saved_config"
saved_wallet_pass_path = f"{harmony_dir}/.wallet_pass"
node_pid_path = f"{harmony_dir}/.autonode_node_pid"

node_script_source = "https://raw.githubusercontent.com/harmony-one/harmony/master/scripts/node.sh"

default_cli_passphrase = ""
bls_key_len = 96

validator_config = {
    "validator-addr": None,
    "name": "harmony autonode",
    "website": "harmony.one",
    "security-contact": "Daniel-VDM",
    "identity": "auto-node",
    "amount": 10100,
    "min-self-delegation": 10000,
    "rate": 0.1,
    "max-rate": 0.75,
    "max-change-rate": 0.05,
    "max-total-delegation": 100000000.0,
    "details": "None"
}
node_config = {
    "endpoint": "https://api.s0.os.hmny.io/",
    "network": "staking",
    "clean": True,
    "duration": None,
    "shard": None,
    "auto-reset": True,
    "auto-active": True,
    "no-validator": False,
    "public-bls-keys": []
}


def save_validator_config():
    with open(saved_validator_path, 'w', encoding='utf8') as f:
        json.dump(validator_config, f, indent=4)
        subprocess.call(f"chmod go-rwx {saved_validator_path}", shell=True, env=os.environ)


def save_node_config():
    with open(saved_node_path, 'w', encoding='utf8') as f:
        json.dump(node_config, f, indent=4)
        subprocess.call(f"chmod go-rwx {saved_node_path}", shell=True, env=os.environ)
