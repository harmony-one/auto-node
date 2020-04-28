import json
import subprocess
import logging
import os

from pyhmy import Typgpy

harmony_dir = f"{os.environ['HOME']}/.hmy"
node_dir = f"{os.environ['HOME']}/harmony_node"
node_sh_log_dir = f"{node_dir}/node_sh_logs"
bls_key_dir = f"{harmony_dir}/blskeys"
imported_wallet_pass_file_dir = f"{os.environ['HOME']}/wallet_pass"
cli_bin_dir = f"{harmony_dir}/bin"
cli_bin_path = f"{cli_bin_dir}/hmy"
saved_validator_path = f"{os.environ['HOME']}/validator_config.json"
saved_node_path = f"{harmony_dir}/.saved_config"
saved_wallet_pass_path = f"{harmony_dir}/.wallet_pass"

node_script_source = "https://harmony.one/master/node.sh"

default_cli_passphrase = ""
bls_key_len = 96
b32_addr_len = 42

msg_tag = "[AutoNode]"

_validator_config_default = {
    "validator-addr": None,
    "name": "Harmony AutoNode Default Name",
    "website": "harmony.one",
    "security-contact": "Daniel-VDM",
    "identity": f"AutoNode-{hash(os.urandom(42))}",
    "amount": 10100,
    "min-self-delegation": 10000,
    "rate": 0.1,
    "max-rate": 0.75,
    "max-change-rate": 0.05,
    "max-total-delegation": 100000000.0,
    "details": "Harmony AutoNode default details",
    "gas-price": 1
}
validator_config = _validator_config_default.copy()

_node_config_default = {
    "endpoint": "https://api.s0.os.hmny.io/",
    "network": "staking",
    "clean": False,
    "duration": None,
    "shard": None,
    "auto-reset": False,
    "auto-active": False,
    "no-validator": False,
    "public-bls-keys": []
}
node_config = _node_config_default.copy()

sync_dir_map = {
    "staking": "ostn",
    "partner": "pstn",
    "stress": "stn",
    "devnet": "devnet",
    "mainnet": "mainnet.min"
}


def save_validator_config():
    for key in _validator_config_default.keys():
        if key not in validator_config.keys():
            raise KeyError(f"{key} not present in validator config to save: {validator_config}. "
                           f"Remove `{saved_validator_path}` or edit validator config and follow template: "
                           f"{json.dumps(_validator_config_default, indent=4)}")
    try:
        config_string = json.dumps(validator_config, indent=4)
    except json.decoder.JSONDecodeError as e:
        raise ValueError(f"Validator config cannot be parsed into JSON.\n"
                         f"Error: {e}.\n"
                         f"Config: {validator_config}")
    save_protected_file(config_string, saved_validator_path, verbose=False)
    # Make validator config file easily writeable
    subprocess.check_call(f"chmod 600 {saved_validator_path}", shell=True, env=os.environ)


def save_node_config():
    for key in _node_config_default.keys():
        if key not in node_config.keys():
            raise KeyError(f"{key} not present in node config to save: {node_config}")
    try:
        config_string = json.dumps(node_config, indent=4)
    except json.decoder.JSONDecodeError as e:
        raise ValueError(f"Node config cannot be parsed into JSON.\n"
                         f"Error: {e}.\n"
                         f"Config: {node_config}")
    save_protected_file(config_string, saved_node_path, verbose=False)


def save_protected_file(string_content, file_path, verbose=True):
    if os.path.isfile(file_path):
        if os.access(file_path, os.R_OK):  # check for min needed perms.
            os.remove(file_path)
        else:
            raise PermissionError(f"Cannot save protected file to {file_path} for user {os.environ['USER']}")
    with open(file_path, 'w', encoding='utf8') as f:
        f.write(string_content)
        protect_file(file_path, verbose=verbose)


def reset_validator_config():
    validator_config.clear()
    validator_config.update(_validator_config_default)


def reset_node_config():
    node_config.clear()
    node_config.update(_node_config_default)


def log(*args):
    """
    Tagged print and log for AutoNode library.
    # TODO: implement and correct msgs for log levels
    """
    logging.getLogger('AutoNode').debug(*args)


def protect_file(file_path, verbose=True):
    """
    Protect a file with chmod 400.
    """
    if verbose:
        log(f"{Typgpy.WARNING}Protecting file `{file_path}` for user {os.environ['USER']}{Typgpy.ENDC}")
    return subprocess.check_call(f"chmod 400 {file_path}", shell=True, env=os.environ)
