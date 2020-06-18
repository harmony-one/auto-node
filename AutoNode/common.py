import json
import logging
import os
import getpass
import pickle
import subprocess

from pyhmy import (
    Typgpy,
    validator,
    exceptions,
)

user = getpass.getuser()
harmony_dir = f"{os.environ['HOME']}/.hmy"
node_dir = f"{os.environ['HOME']}/harmony_node"
node_sh_log_dir = f"{node_dir}/node_sh_logs"
bls_key_dir = f"{harmony_dir}/blskeys"
imported_wallet_pass_file_dir = f"{os.environ['HOME']}/harmony_wallet_pass"
cli_bin_dir = f"{harmony_dir}/bin"
cli_bin_path = f"{cli_bin_dir}/hmy"
saved_validator_path = f"{os.environ['HOME']}/harmony_validator_config.json"
saved_node_config_path = f"{harmony_dir}/.node_config.p"
tui_path = f"{harmony_dir}/tui"

node_script_source = "https://harmony.one/node.sh"
tui_source = "http://pub.harmony.one.s3.amazonaws.com/release/linux-x86_64/mainnet/static/harmony-tui"

default_cli_passphrase = ""
bls_key_len = 96
b32_addr_len = 42
check_interval = 8  # Estimated block time

msg_tag = "[AutoNode]"

# TODO: Keybase integration for identity
_validator_config_default = {
    "validator-addr": None,
    "name": None,
    "website": None,
    "security-contact": None,
    "identity": None,
    "amount": None,
    "min-self-delegation": None,
    "rate": None,
    "max-rate": None,
    "max-change-rate": None,
    "max-total-delegation": None,
    "details": None,
    "gas-price": "1"
}
validator_config = _validator_config_default.copy()

# Invariant: 'public-bls-keys' does not change after node is started.
_node_config_default = {
    "endpoint": "https://api.s0.b.hmny.io/",
    "network": "testnet",
    "clean": False,
    "shard": None,
    "auto-reset": False,
    "auto-active": False,
    "no-validator": False,
    "archival": False,
    "no-download": False,
    "fast-sync": False,
    "public-bls-keys": [],
    "encrypted-wallet-passphrase": b'',
    "_is_recovering": False  # Only used for auto hard-reset
}
node_config = _node_config_default.copy()


def save_validator_config():
    """
    Do not save invalid validator.
    In worst case, new validator information will be re-prompted on re-init of AutoNode.
    """
    if node_config['no-validator']:
        return
    try:
        for key, value in _validator_config_default.items():
            if key not in validator_config.keys():
                raise KeyError(f"Missing key {key} from validator config.")
        if validator_config['validator-addr'] is not None:  # Only validate if validator addr has been saved
            validator.Validator(validator_config['validator-addr']).load(validator_config)
        config_string = json.dumps(validator_config, indent=4)
    except (exceptions.InvalidValidatorError, json.decoder.JSONDecodeError, KeyError, TypeError) as e:
        log(f"{Typgpy.FAIL}Invalid validator information to save.{Typgpy.ENDC}\n"
            f"Error: {e}.\n"
            f"Validator Config: {json.dumps(validator_config, indent=2)}")
        log(f"{Typgpy.WARNING}NOT saving validator config, continuing...{Typgpy.ENDC}")
        return
    save_protected_file(config_string, saved_validator_path, verbose=False)
    # Make validator config file easily writeable
    subprocess.check_call(["chmod", "600", saved_validator_path], env=os.environ)


def load_validator_config():
    """
    Load the saved validator config.

    Raises json.decoder.JSONDecodeError, IOError, PermissionError
    """
    with open(saved_validator_path, 'r', encoding='utf8') as f:
        imported_val_config = json.load(f)
        validator_config.update(imported_val_config)


def save_node_config():
    """
    Do not save invalid node config.
    In worst case, node config will be refreshed with valid info on re-init of AutoNode.
    """
    try:
        for key, value in _node_config_default.items():
            if key not in node_config.keys():
                raise KeyError(f"Missing key {key} from node config.")
        node_config_string = pickle.dumps(node_config)
    except (pickle.PickleError, KeyError, TypeError) as e:
        log(f"{Typgpy.FAIL}Invalid node config to save.{Typgpy.ENDC}\n"
            f"Error: {e}.")
        log(f"{Typgpy.WARNING}NOT saving node config, continuing...{Typgpy.ENDC}")
        return
    save_protected_file(node_config_string, saved_node_config_path, verbose=False)


def load_node_config():
    """
    Load the saved node config.

    Raises pickle.PickleError, IOError, PermissionError
    """
    with open(saved_node_config_path, 'rb') as f:
        imported_node_config = pickle.load(f)
        node_config.update(imported_node_config)


def save_protected_file(content, file_path, verbose=True):
    if os.path.isfile(file_path):
        if os.access(file_path, os.R_OK):  # check for min needed perms.
            os.remove(file_path)
        else:
            raise PermissionError(f"Cannot save protected file to {file_path} for user {user}")
    if isinstance(content, bytes):
        with open(file_path, 'wb') as f:
            f.write(content)
            protect_file(file_path, verbose=verbose)
    else:
        with open(file_path, 'w', encoding='utf8') as f:
            f.write(content)
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
        log(f"{Typgpy.WARNING}Protecting file `{file_path}` for user {user}{Typgpy.ENDC}")
    subprocess.check_call(["chmod", "400", file_path], env=os.environ)
