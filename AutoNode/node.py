import os
import stat
import subprocess
import json
import time
import shutil
import logging

import requests

from pyhmy import (
    Typgpy,
    cli
)

from .common import (
    log,
    node_script_source,
    node_sh_log_dir,
    node_config,
    node_dir,
    bls_key_dir,
    sync_dir_map,
    harmony_dir,
    validator_config,
    saved_wallet_pass_path
)
from .blockchain import (
    get_latest_header,
    get_latest_headers,
    get_all_validator_addresses,
    get_validator_information
)
from .util import (
    input_with_print,
    get_simple_rotating_log_handler
)

node_sh_out_path = f"{node_sh_log_dir}/out.log"
node_sh_err_path = f"{node_sh_log_dir}/err.log"
node_sh_rclone_err_path = f"{node_sh_log_dir}/rclone_err.log"
node_sh_rclone_out_path = f"{node_sh_log_dir}/rclone_out.log"

log_path = f"{harmony_dir}/autonode_node.log"


# TODO: add logic to check for repeated node restarts and/or add logic for checking for latest version of binary.


def _node_clean(verbose=True):
    log_dir = f"{node_dir}/latest"
    backup_log_dir = f"{node_dir}/backup_logs/{time.strftime('%Y/%m/%d/%H')}"
    os.makedirs(backup_log_dir, exist_ok=True)
    try:
        if os.path.isdir(log_dir):
            if verbose:
                log(f"{Typgpy.WARNING}[!] Moving {log_dir} to {backup_log_dir} {Typgpy.ENDC}")
            if os.path.isdir(backup_log_dir):
                shutil.rmtree(backup_log_dir)  # Should never happen, always keep latest.
            shutil.move(log_dir, backup_log_dir)
        for directory in filter(lambda e: os.path.isdir(e), os.listdir(node_dir)):
            if directory.startswith("harmony_db_") or directory.startswith(".dht"):
                path = os.path.join(node_dir, directory)
                if verbose:
                    log(f"{Typgpy.WARNING}[!] Removing {path} {Typgpy.ENDC}")
                shutil.rmtree(path)
    except shutil.Error as e:
        raise SystemExit(e)


def _rclone_s0(verbose=True):
    db_0_dir = f"{node_dir}/harmony_db_0"
    try:
        if verbose:
            log(f"{Typgpy.WARNING}[!] rclone harmony_db_0 in progress...{Typgpy.ENDC}")
        rclone_sync_dir = sync_dir_map[node_config['network']]
        with open(node_sh_rclone_out_path, 'w') as fo:
            with open(node_sh_rclone_err_path, 'w') as fe:
                subprocess.check_call(f"rclone sync -P hmy://pub.harmony.one/{rclone_sync_dir}/harmony_db_0 {db_0_dir}",
                                      shell=True, env=os.environ, stdout=fo, stderr=fe)
        if verbose:
            log(f"{Typgpy.OKGREEN}[!] rclone done!{Typgpy.ENDC}")
    except (subprocess.CalledProcessError, KeyError) as e:
        if verbose:
            log(f"{Typgpy.FAIL}Failed to rclone shard 0 db, error {e}{Typgpy.ENDC}")
            log(f"{Typgpy.WARNING}Removing shard 0 db if it exists{Typgpy.ENDC}")
            if os.path.isdir(db_0_dir):
                shutil.rmtree(db_0_dir)


def start(auto=False, verbose=True):
    old_logging_handlers = logging.getLogger('AutoNode').handlers.copy()
    logging.getLogger('AutoNode').addHandler(get_simple_rotating_log_handler(log_path))
    log(f"{Typgpy.HEADER}Starting node...{Typgpy.ENDC}")
    if not auto:
        log(f"{Typgpy.WARNING}You are starting a Harmony Node manually, "
            f"this is not recommended, continue? [Y]/n{Typgpy.ENDC}")
        if input_with_print("> ") not in {'Y', 'y', 'yes', 'Yes'}:
            raise SystemExit()
    os.chdir(node_dir)
    if os.path.isfile(f"{node_dir}/node.sh"):
        os.remove(f"{node_dir}/node.sh")
    try:
        r = requests.get(node_script_source, timeout=30, verify=True)
        with open("node.sh", 'w') as f:
            node_sh = r.content.decode()
            # WARNING: Hack until node.sh is changed for auto-node.
            node_sh = node_sh.replace("save_pass_file=false", 'save_pass_file=true')
            f.write(node_sh)
    except requests.exceptions.RequestException as e:
        raise SystemExit(e)
    st = os.stat("node.sh")
    os.chmod("node.sh", st.st_mode | stat.S_IEXEC)
    node_args = ["./node.sh", "-N", node_config["network"], "-z", "-f", bls_key_dir, "-M", "-S"]
    if node_config['clean'] and node_config['network'] != 'mainnet':
        if verbose:
            log(f"{Typgpy.WARNING}[!] Starting node with clean mode.{Typgpy.ENDC}")
        _node_clean(verbose=verbose)
        _rclone_s0(verbose=verbose)
    if node_config['archival']:
        if verbose:
            log(f"{Typgpy.WARNING}[!] Starting in archival mode.{Typgpy.ENDC}")
        node_args.append("-A")
    with open(node_sh_out_path, 'w') as fo:
        with open(node_sh_err_path, 'w') as fe:
            if verbose:
                log(f"{Typgpy.HEADER}Starting node!{Typgpy.ENDC}")
            logging.getLogger('AutoNode').handlers = old_logging_handlers  # Reset logger to old handlers
            return subprocess.Popen(node_args, env=os.environ, stdout=fo, stderr=fe).pid


# TODO (low prio): create stream load printer for multiple waits_for_node_response
def wait_for_node_response(endpoint, verbose=True, tries=float("inf"), sleep=0.5):
    count = 0
    while True:
        count += 1
        try:
            get_latest_header(endpoint)
            break
        except (json.decoder.JSONDecodeError, requests.exceptions.ConnectionError,
                RuntimeError, KeyError, AttributeError):
            if count > tries:
                raise TimeoutError(f"{endpoint} did not respond in {count} attempts (~{sleep * count} seconds)")
            if verbose and count % 10 == 0:
                log(f"{Typgpy.WARNING}Waiting for {endpoint} to respond, tried {count} times "
                    f"(~{sleep * count} seconds waited so far){Typgpy.ENDC}")
            time.sleep(sleep)
    if verbose:
        log(f"{Typgpy.HEADER}[!] {endpoint} is alive!{Typgpy.ENDC}")


def assert_no_bad_blocks():
    if os.path.isdir(f"{node_dir}/latest"):
        files = [x for x in os.listdir(f"{node_dir}/latest") if x.endswith(".log")]
        if files:
            log_path = f"{node_dir}/latest/{files[-1]}"
            assert not has_bad_block(log_path), f"`BAD BLOCK` present in {log_path}, restart AutoNode with clean option"


def has_bad_block(log_file_path):
    assert os.path.isfile(log_file_path)
    try:
        with open(log_file_path, 'r', encoding='utf8') as f:
            for line in f:
                line = line.rstrip()
                if "## BAD BLOCK ##" in line:
                    return True
    except (UnicodeDecodeError, IOError):
        log(f"{Typgpy.WARNING}WARNING: failed to read `{log_file_path}` to check for bad block{Typgpy.ENDC}")
    return False


def check_and_activate(epos_status_msg):
    """
    Return True when attempted to activate, otherwise return False.
    """
    if "not eligible" in epos_status_msg or "not signing" in epos_status_msg:
        log(f"{Typgpy.FAIL}Node not active, reactivating...{Typgpy.ENDC}")
        curr_headers = get_latest_headers("http://localhost:9500/")
        curr_epoch_shard = curr_headers['shard-chain-header']['epoch']
        curr_epoch_beacon = curr_headers['beacon-chain-header']['epoch']
        wait_for_node_response(node_config['endpoint'], tries=900, sleep=1, verbose=False)  # Try for 15 min
        ref_epoch = get_latest_header(node_config['endpoint'])['epoch']
        if curr_epoch_shard == ref_epoch and curr_epoch_beacon == ref_epoch:
            try:
                activate_validator()
                return True
            except (TimeoutError, ConnectionError, RuntimeError, subprocess.CalledProcessError) as e:
                log(f"{Typgpy.FAIL}Unable to activate validator {validator_config['validator-addr']}"
                    f"error {e}. Continuing...{Typgpy.ENDC}")
                return False
        else:
            log(f"{Typgpy.WARNING}Node not synced, did NOT activate node.{Typgpy.ENDC}")
            return False
    return False


def deactivate_validator():
    """
    Assumption that endpoint is alive. Will throw error if not.
    """
    all_val = get_all_validator_addresses(node_config['endpoint'])
    if validator_config["validator-addr"] in all_val:
        val_chain_info = get_validator_information(validator_config["validator-addr"], node_config['endpoint'])
        if "not eligible" not in val_chain_info['epos-status']:
            log(f"{Typgpy.OKBLUE}Deactivating validator{Typgpy.ENDC}")
            response = cli.single_call(
                f"hmy staking edit-validator --validator-addr {validator_config['validator-addr']} "
                f"--active false --node {node_config['endpoint']} "
                f"--passphrase-file {saved_wallet_pass_path} --gas-price {validator_config['gas-price']} ")
            log(f"{Typgpy.OKGREEN}Edit-validator response: {response}{Typgpy.ENDC}")
        else:
            log(f"{Typgpy.WARNING}Validator {validator_config['validator-addr']} is already deactivated!{Typgpy.ENDC}")
    else:
        log(f"{Typgpy.FAIL}Address {validator_config['validator-addr']} is not a validator!{Typgpy.ENDC}")


def activate_validator():
    """
    Assumption that endpoint is alive. Will throw error if not.
    """
    all_val = get_all_validator_addresses(node_config['endpoint'])
    if validator_config["validator-addr"] in all_val:
        val_chain_info = get_validator_information(validator_config["validator-addr"], node_config['endpoint'])
        if "not eligible" in val_chain_info['epos-status']:
            log(f"{Typgpy.OKBLUE}Activating validator{Typgpy.ENDC}")
            response = cli.single_call(
                f"hmy staking edit-validator --validator-addr {validator_config['validator-addr']} "
                f"--active true --node {node_config['endpoint']} "
                f"--passphrase-file {saved_wallet_pass_path} --gas-price {validator_config['gas-price']} ")
            log(f"{Typgpy.OKGREEN}Edit-validator response: {response}{Typgpy.ENDC}")
        else:
            log(f"{Typgpy.WARNING}Validator {validator_config['validator-addr']} is already active!{Typgpy.ENDC}")
    else:
        log(f"{Typgpy.FAIL}Address {validator_config['validator-addr']} is not a validator!{Typgpy.ENDC}")
