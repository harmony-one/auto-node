import sys
import time
import json
import logging
import subprocess

from pyhmy import cli
from pyhmy import (
    Typgpy,
)

from .common import (
    log,
    bls_key_dir,
    node_config,
    validator_config,
    saved_wallet_pass_path,
)
from .blockchain import (
    get_latest_header,
    get_latest_headers,
    get_staking_epoch,
    get_current_epoch,
    get_all_validator_addresses,
    get_validator_information
)
from .node import (
    log_path,
    wait_for_node_response,
    assert_no_bad_blocks,
    deactivate_validator,
    activate_validator
)
from .util import (
    check_min_bal_on_s0,
    input_with_print,
    get_simple_rotating_log_handler
)
from .monitor import (
    check_interval
)


def _add_bls_key_to_validator():
    """
    Assumes past staking epoch by definition of adding keys to existing validator
    """
    _verify_account_balance(0.1 * len(node_config["public-bls-keys"]))  # Heuristic amount for balance
    chain_val_info = get_validator_information(validator_config['validator-addr'], node_config['endpoint'])
    bls_keys = set(x.replace('0x', '') for x in chain_val_info["validator"]["bls-public-keys"])
    for k in (x.replace('0x', '') for x in node_config["public-bls-keys"]):
        if k not in bls_keys:  # Add imported BLS key to existing validator if needed
            _send_edit_validator_tx(k)
        else:
            log(f"{Typgpy.WARNING}Bls key: {Typgpy.OKGREEN}{k}{Typgpy.WARNING} "
                f"is already present, ignoring...{Typgpy.ENDC}")
    _verify_node_sync()


def _send_edit_validator_tx(bls_key_to_add):
    log(f"{Typgpy.OKBLUE}Adding bls key: {Typgpy.OKGREEN}{bls_key_to_add}{Typgpy.OKBLUE} "
        f"to validator: {Typgpy.OKGREEN}{validator_config['validator-addr']}{Typgpy.ENDC}")
    response = cli.single_call(f"hmy --node={node_config['endpoint']} staking edit-validator "
                               f"--validator-addr {validator_config['validator-addr']} "
                               f"--add-bls-key {bls_key_to_add} --passphrase-file {saved_wallet_pass_path} "
                               f"--bls-pubkeys-dir {bls_key_dir}")
    log(f"{Typgpy.OKBLUE}Edit-validator transaction response: "
        f"{Typgpy.OKGREEN}{response}{Typgpy.ENDC}")


def _create_new_validator():
    _verify_staking_epoch()
    _verify_account_balance(validator_config['amount'] + 50)
    _send_create_validator_tx()
    _verify_node_sync()


def _verify_staking_epoch():
    """
    Invariant: All staking transactions are done AFTER staking epoch.
    """
    log(f"{Typgpy.OKBLUE}Verifying Staking Epoch...{Typgpy.ENDC}")
    staking_epoch = get_staking_epoch(node_config['endpoint'])
    curr_epoch = get_current_epoch(node_config['endpoint'])
    while curr_epoch < staking_epoch:  # WARNING: using staking epoch for extra security of configs.
        sys.stdout.write(f"\rWaiting for staking epoch ({staking_epoch}) -- current epoch: {curr_epoch}")
        sys.stdout.flush()
        time.sleep(8)  # Assumption of 8 second block time...
        curr_epoch = get_current_epoch(node_config['endpoint'])
    log(f"{Typgpy.OKGREEN}Network is at or past staking epoch{Typgpy.ENDC}")


def _verify_account_balance(amount):
    """
    Invariant: Account has sufficient balance before sending transactions
    """
    log(f"{Typgpy.OKBLUE}Verifying Balance...{Typgpy.ENDC}")
    if not check_min_bal_on_s0(validator_config['validator-addr'], amount, node_config['endpoint']):
        log(f"{Typgpy.FAIL}Cannot create validator, {validator_config['validator-addr']} "
            f"does not have sufficient funds ({amount} ONE).{Typgpy.ENDC}")
        raise SystemExit("Create Validator Error")
    else:
        log(f"{Typgpy.OKGREEN}Address: {validator_config['validator-addr']} has enough funds{Typgpy.ENDC}")


def _verify_node_sync():
    """
    Invariant: Node sync is always checked before sending any validator transactions.
    """
    log(f"{Typgpy.OKBLUE}Verifying Node Sync...{Typgpy.ENDC}")
    wait_for_node_response("http://localhost:9500/", sleep=1, verbose=True)
    wait_for_node_response(node_config['endpoint'], sleep=1, verbose=True)
    curr_headers = get_latest_headers("http://localhost:9500/")
    curr_epoch_shard = curr_headers['shard-chain-header']['epoch']
    curr_epoch_beacon = curr_headers['beacon-chain-header']['epoch']
    ref_epoch = get_latest_header(node_config['endpoint'])['epoch']
    has_looped = False
    if curr_epoch_shard < ref_epoch or curr_epoch_beacon < ref_epoch:
        log(f"{Typgpy.OKBLUE}Deactivating validator until node is synced.{Typgpy.ENDC}")
        try:
            deactivate_validator()
        except (TimeoutError, RuntimeError, subprocess.CalledProcessError) as e:
            log(f"{Typgpy.FAIL}Unable to deactivate validator {validator_config['validator-addr']}"
                f"error {e}. Continuing...{Typgpy.ENDC}")
    while curr_epoch_shard < ref_epoch or curr_epoch_beacon < ref_epoch:
        sys.stdout.write(f"\rWaiting for node to sync: shard epoch ({curr_epoch_shard}/{ref_epoch}) "
                         f"& beacon epoch ({curr_epoch_beacon}/{ref_epoch})")
        sys.stdout.flush()
        has_looped = True
        time.sleep(check_interval)
        assert_no_bad_blocks()
        curr_headers = get_latest_headers("http://localhost:9500/")
        curr_epoch_shard = curr_headers['shard-chain-header']['epoch']
        curr_epoch_beacon = curr_headers['beacon-chain-header']['epoch']
        ref_epoch = get_latest_header(node_config['endpoint'])['epoch']
    if curr_epoch_shard > ref_epoch or curr_epoch_beacon > ref_epoch:
        log(f"{Typgpy.FAIL}Node epoch is greater than network epoch which is not possible, "
            f"is config correct?{Typgpy.ENDC}")
        raise SystemExit("Invalid node sync")
    if has_looped:
        log("")
    log(f"{Typgpy.OKGREEN}Node synced to current epoch...{Typgpy.ENDC}")
    if not has_looped:
        log(f"{Typgpy.OKGREEN}Waiting {check_interval} seconds before sending activate transaction{Typgpy.ENDC}")
        time.sleep(check_interval)  # Wait for nonce to finalize before sending activate
    try:
        activate_validator()
    except (TimeoutError, RuntimeError, subprocess.CalledProcessError) as e:
        log(f"{Typgpy.FAIL}Unable to activate validator {validator_config['validator-addr']}"
            f"error {e}. Continuing...{Typgpy.ENDC}")


def _send_create_validator_tx():
    log(f"{Typgpy.OKBLUE}Sending create validator transaction...{Typgpy.ENDC}")
    response = cli.single_call(f'hmy --node={node_config["endpoint"]} staking create-validator '
                               f'--validator-addr {validator_config["validator-addr"]} '
                               f'--name "{validator_config["name"]}" '
                               f'--identity "{validator_config["identity"]}" '
                               f'--website "{validator_config["website"]}" '
                               f'--security-contact "{validator_config["security-contact"]}" '
                               f'--details "{validator_config["details"]}" '
                               f'--rate {validator_config["rate"]} '
                               f'--max-rate {validator_config["max-rate"]} '
                               f'--max-change-rate {validator_config["max-change-rate"]} '
                               f'--min-self-delegation {validator_config["min-self-delegation"]} '
                               f'--max-total-delegation {validator_config["max-total-delegation"]} '
                               f'--amount {validator_config["amount"]} '
                               f'--bls-pubkeys {",".join(node_config["public-bls-keys"])} '
                               f'--passphrase-file "{saved_wallet_pass_path}" '
                               f'--bls-pubkeys-dir "{bls_key_dir}" ')
    log(f"{Typgpy.OKBLUE}Created Validator!{Typgpy.OKGREEN}{response}{Typgpy.ENDC}")


def setup(recover_interaction=False):
    old_logging_handlers = logging.getLogger('AutoNode').handlers.copy()
    logging.getLogger('AutoNode').addHandler(get_simple_rotating_log_handler(log_path))
    log(f"{Typgpy.HEADER}Starting validator setup...{Typgpy.ENDC}")
    if node_config['no-validator']:
        raise SystemExit(f"{Typgpy.WARNING}Node config specifies not validator automation, exiting...{Typgpy.ENDC}")
    auto_interaction = 'Y' if recover_interaction else None

    log(f"{Typgpy.OKBLUE}Create validator config: {Typgpy.OKGREEN}"
        f"{json.dumps(validator_config, indent=4)}{Typgpy.ENDC}")
    log(f"{Typgpy.OKBLUE}Using BLS key(s): {Typgpy.OKGREEN}{node_config['public-bls-keys']}{Typgpy.ENDC}")
    try:
        wait_for_node_response(node_config['endpoint'], verbose=True, tries=120, sleep=1)  # Try for 2 min
        all_val_address = get_all_validator_addresses(
            node_config['endpoint'])  # Check BLS key with validator if it exists
        if validator_config['validator-addr'] in all_val_address:
            log(f"{Typgpy.WARNING}{validator_config['validator-addr']} already in list of validators!{Typgpy.ENDC}")
            prompt = "Add BLS key(s) to existing validator? [Y]/n \n> "
            if input_with_print(prompt, auto_interaction) in {'Y', 'y', 'yes', 'Yes'}:
                log(f"{Typgpy.HEADER}{Typgpy.BOLD}Editing validator...{Typgpy.ENDC}")
                _add_bls_key_to_validator()
        elif validator_config['validator-addr'] not in all_val_address:
            prompt = "Create validator? [Y]/n \n> "
            if input_with_print(prompt, auto_interaction) in {'Y', 'y', 'yes', 'Yes'}:
                log(f"{Typgpy.HEADER}{Typgpy.BOLD}Creating new validator...{Typgpy.ENDC}")
                _create_new_validator()
        else:
            node_config['no-validator'] = True
        log(f"{Typgpy.HEADER}{Typgpy.BOLD}Finished setting up validator!{Typgpy.ENDC}")
        logging.getLogger('AutoNode').handlers = old_logging_handlers  # Reset logger to old handlers
    except Exception as e:
        raise SystemExit(e)
