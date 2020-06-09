"""
This package takes care of all validator related commands.

Note that if `_recover_interaction` is set (True) then a function MUST exit
gracefully (including RPC timeouts etc...), otherwise, it is free to throw errors.
"""

import sys
import time
import json
import logging
import subprocess
import traceback
import requests

from decimal import Decimal

from pyhmy import (
    blockchain,
    cli,
    staking,
    Typgpy
)

from .common import (
    log,
    bls_key_dir,
    node_config,
    validator_config,
    saved_wallet_pass_path,
    check_interval
)
from .node import (
    log_path,
    wait_for_node_response,
    assert_no_bad_blocks,
)
from .util import (
    check_min_bal_on_s0,
    input_with_print,
    get_simple_rotating_log_handler
)

_balance_buffer = Decimal(1)
_recover_interaction = False


def _interaction_preprocessor(recover_interaction):
    """
    All user calls (i.e: validator setup) must be processed by this
    """
    global _recover_interaction
    _recover_interaction = recover_interaction
    old_logging_handlers = logging.getLogger('AutoNode').handlers.copy()
    logging.getLogger('AutoNode').addHandler(get_simple_rotating_log_handler(log_path))
    if node_config['no-validator']:
        print(f"{Typgpy.WARNING}Config specifies no validator automation, exiting...{Typgpy.ENDC}")
        exit(0)
    return old_logging_handlers


def _add_bls_key_to_validator():
    """
    Assumes past staking epoch by definition of adding keys to existing validator
    """
    _verify_account_balance(0.1 * len(node_config["public-bls-keys"]))  # Heuristic amount for balance
    chain_val_info = staking.get_validator_information(validator_config['validator-addr'], node_config['endpoint'])
    bls_keys = set(x.replace('0x', '') for x in chain_val_info["validator"]["bls-public-keys"])
    for k in (x.replace('0x', '') for x in node_config["public-bls-keys"]):
        if k not in bls_keys:  # Add imported BLS key to existing validator if needed
            _send_edit_validator_tx(k)
        else:
            log(f"{Typgpy.WARNING}Bls key: {Typgpy.OKGREEN}{k}{Typgpy.WARNING} "
                f"is already present, ignoring...{Typgpy.ENDC}")


def _send_edit_validator_tx(bls_key_to_add):
    log(f"{Typgpy.OKBLUE}Adding bls key: {Typgpy.OKGREEN}{bls_key_to_add}{Typgpy.OKBLUE} "
        f"to validator: {Typgpy.OKGREEN}{validator_config['validator-addr']}{Typgpy.ENDC}")
    count = 0
    while True:
        count += 1
        try:
            response = cli.single_call(['hmy', '--node', f'{node_config["endpoint"]}', 'staking', 'edit-validator',
                                        '--validator-addr', f'{validator_config["validator-addr"]}',
                                        '--add-bls-key', bls_key_to_add, '--passphrase-file', saved_wallet_pass_path,
                                        '--bls-pubkeys-dir', bls_key_dir, '--gas-price', f'{validator_config["gas-price"]}'])
            log(f"{Typgpy.OKBLUE}Edit-validator transaction response: "
                f"{Typgpy.OKGREEN}{response}{Typgpy.ENDC}")
            return
        except (RuntimeError, TimeoutError, ConnectionError, subprocess.CalledProcessError) as e:
            log(f"{Typgpy.FAIL}Edit-validator transaction failure (attempt {count}). Error: {e}{Typgpy.ENDC}")
            if not _recover_interaction:
                raise e
            log(f"{Typgpy.WARNING}Trying again in {check_interval} seconds.{Typgpy.ENDC}")
            time.sleep(check_interval)


def _create_new_validator():
    _verify_prestaking_epoch()
    _verify_account_balance(Decimal(validator_config['amount']) + _balance_buffer)
    _send_create_validator_tx()


def _verify_staking_epoch():
    """
    Invariant: All staking transactions are done AFTER staking epoch.
    """
    log(f"{Typgpy.OKBLUE}Verifying Staking Epoch...{Typgpy.ENDC}")
    staking_epoch = blockchain.get_staking_epoch(endpoint=node_config['endpoint'])
    curr_epoch = blockchain.get_current_epoch(endpoint=node_config['endpoint'])
    while curr_epoch < staking_epoch:  # WARNING: using staking epoch for extra security of configs.
        sys.stdout.write(f"\rWaiting for staking epoch ({staking_epoch}) -- current epoch: {curr_epoch}")
        sys.stdout.flush()
        time.sleep(check_interval)
        curr_epoch = blockchain.get_current_epoch(endpoint=node_config['endpoint'])
    log(f"{Typgpy.OKGREEN}Network is at or past staking epoch{Typgpy.ENDC}")


def _verify_prestaking_epoch():
    """
    Invariant: All staking transactions are done AFTER staking epoch.
    """
    log(f"{Typgpy.OKBLUE}Verifying Pre Staking Epoch...{Typgpy.ENDC}")
    prestaking_epoch = blockchain.get_prestaking_epoch(endpoint=node_config['endpoint'])
    curr_epoch = blockchain.get_current_epoch(endpoint=node_config['endpoint'])
    while curr_epoch < prestaking_epoch:
        sys.stdout.write(f"\rWaiting for pre staking epoch ({prestaking_epoch}) -- current epoch: {curr_epoch}")
        sys.stdout.flush()
        time.sleep(check_interval)
        curr_epoch = blockchain.get_current_epoch(endpoint=node_config['endpoint'])
    log(f"{Typgpy.OKGREEN}Network is at or past pre staking epoch{Typgpy.ENDC}")


def _verify_account_balance(amount):
    count = 0
    log(f"{Typgpy.OKBLUE}Verifying Balance...{Typgpy.ENDC}")
    while True:
        count += 1
        if not check_min_bal_on_s0(validator_config['validator-addr'], amount, node_config['endpoint']):
            log(f"{Typgpy.FAIL}Cannot create validator, {validator_config['validator-addr']} "
                f"does not have sufficient funds (need {amount} ONE). Checked {count} time(s).{Typgpy.ENDC}")
            if not _recover_interaction:
                raise SystemExit("Create Validator Error")
            log(f"{Typgpy.WARNING}Checking again in {check_interval} seconds.{Typgpy.ENDC}")
            time.sleep(check_interval)
        else:
            log(f"{Typgpy.OKGREEN}Address: {validator_config['validator-addr']} has enough funds{Typgpy.ENDC}")
            return


def is_active_validator():
    """
    Default to false if exception to be defensive.
    """
    try:
        val_chain_info = staking.get_validator_information(validator_config["validator-addr"], endpoint=node_config['endpoint'])
        return "active" not in val_chain_info['active-status']
    except (ConnectionError, requests.exceptions.RequestException, TimeoutError) as e:
        log(f"{Typgpy.WARNING}Could not fetch validator active status, error: {e}{Typgpy.ENDC}")
        return False


# TODO: separate this function into its own or proper lib
def verify_node_sync():
    log(f"{Typgpy.OKBLUE}Verifying Node Sync...{Typgpy.ENDC}")
    wait_for_node_response("http://localhost:9500/", sleep=1, verbose=True)
    wait_for_node_response(node_config['endpoint'], sleep=1, verbose=True)
    curr_headers = blockchain.get_latest_headers()
    curr_epoch_shard = curr_headers['shard-chain-header']['epoch']
    curr_epoch_beacon = curr_headers['beacon-chain-header']['epoch']
    ref_epoch = blockchain.get_current_epoch(endpoint=node_config['endpoint'])
    has_looped = False
    if curr_epoch_shard < ref_epoch or curr_epoch_beacon < ref_epoch:
        log(f"{Typgpy.OKBLUE}Deactivating validator until node is synced.{Typgpy.ENDC}")
        try:
            if is_active_validator():
                deactivate_validator()
        except (TimeoutError, ConnectionError, RuntimeError, subprocess.CalledProcessError) as e:
            log(f"{Typgpy.FAIL}Unable to deactivate validator {validator_config['validator-addr']}"
                f"error {e}. Continuing...{Typgpy.ENDC}")
    while curr_epoch_shard < ref_epoch or curr_epoch_beacon < ref_epoch:
        sys.stdout.write(f"\rWaiting for node to sync: shard epoch ({curr_epoch_shard}/{ref_epoch}) "
                         f"& beacon epoch ({curr_epoch_beacon}/{ref_epoch})")
        sys.stdout.flush()
        has_looped = True
        time.sleep(check_interval)
        assert_no_bad_blocks()
        curr_headers = blockchain.get_latest_headers()
        curr_epoch_shard = curr_headers['shard-chain-header']['epoch']
        curr_epoch_beacon = curr_headers['beacon-chain-header']['epoch']
        ref_epoch = blockchain.get_current_epoch(endpoint=node_config['endpoint'])
    if curr_epoch_shard > ref_epoch + 1 or curr_epoch_beacon > ref_epoch + 1:  # +1 for some slack on epoch change.
        log(f"{Typgpy.FAIL}Node epoch (shard: {curr_epoch_shard} beacon: {curr_epoch_beacon}) is greater than network "
            f"epoch ({ref_epoch}) which is not possible, is config correct?{Typgpy.ENDC}")
        if not _recover_interaction:
            raise SystemExit("Invalid node sync")
    if has_looped:
        log("")
    log(f"{Typgpy.OKGREEN}Node synced to current epoch...{Typgpy.ENDC}")
    try:
        if not has_looped and not is_active_validator():
            log(f"{Typgpy.OKGREEN}Waiting {check_interval} seconds before sending activate transaction{Typgpy.ENDC}")
            time.sleep(check_interval)  # Wait for nonce to finalize before sending activate
        if not is_active_validator():
            activate_validator()
    except (TimeoutError, ConnectionError, RuntimeError, subprocess.CalledProcessError) as e:
        log(f"{Typgpy.FAIL}Unable to activate validator {validator_config['validator-addr']}"
            f"error {e}. Continuing...{Typgpy.ENDC}")


def _send_create_validator_tx():
    log(f"{Typgpy.OKBLUE}Sending create validator transaction...{Typgpy.ENDC}")
    count = 0
    while True:
        count += 1
        try:
            response = cli.single_call(['hmy', '--node', f'{node_config["endpoint"]}', 'staking', 'create-validator',
                                        '--validator-addr', f'{validator_config["validator-addr"]}',
                                        '--name', f'{validator_config["name"]}',
                                        '--identity', f'{validator_config["identity"]}',
                                        '--website', f'{validator_config["website"]}',
                                        '--security-contact', f'{validator_config["security-contact"]}',
                                        '--details', f'{validator_config["details"]}',
                                        '--rate', f'{validator_config["rate"]}',
                                        '--max-rate', f'{validator_config["max-rate"]}',
                                        '--max-change-rate', f'{validator_config["max-change-rate"]}',
                                        '--min-self-delegation', f'{validator_config["min-self-delegation"]}',
                                        '--max-total-delegation', f'{validator_config["max-total-delegation"]}',
                                        '--amount', f'{validator_config["amount"]}',
                                        '--bls-pubkeys', f'{",".join(node_config["public-bls-keys"])}',
                                        '--passphrase-file', saved_wallet_pass_path,
                                        '--bls-pubkeys-dir', bls_key_dir,
                                        '--gas-price', f'{validator_config["gas-price"]}'])
            log(f"{Typgpy.OKBLUE}Create-validator transaction response: "
                f"{Typgpy.OKGREEN}{response}{Typgpy.ENDC}")
            return
        except (RuntimeError, TimeoutError, ConnectionError, subprocess.CalledProcessError) as e:
            log(f"{Typgpy.FAIL}Create-validator transaction failure (attempt {count}). Error: {e}{Typgpy.ENDC}")
            if not _recover_interaction:
                raise e
            log(f"{Typgpy.WARNING}Trying again in {check_interval} seconds.{Typgpy.ENDC}")
            time.sleep(check_interval)


def check_and_activate():
    """
    Return True when attempted to activate, otherwise return False.
    """
    try:
        if not is_active_validator():
            log(f"{Typgpy.FAIL}Node not active, reactivating...{Typgpy.ENDC}")
            curr_headers = blockchain.get_latest_headers()
            curr_epoch_shard = curr_headers['shard-chain-header']['epoch']
            curr_epoch_beacon = curr_headers['beacon-chain-header']['epoch']
            wait_for_node_response(node_config['endpoint'], tries=900, sleep=1, verbose=False)  # Try for 15 min
            ref_epoch = blockchain.get_current_epoch(endpoint=node_config['endpoint'])
            if curr_epoch_shard == ref_epoch and curr_epoch_beacon == ref_epoch:
                activate_validator()
                return True
            else:
                log(f"{Typgpy.WARNING}Node not synced, did NOT activate node.{Typgpy.ENDC}")
                return False
    except (TimeoutError, ConnectionError, RuntimeError, subprocess.CalledProcessError) as e:
        log(traceback.format_exc())
        log(f"{Typgpy.FAIL}Unable to activate validator {validator_config['validator-addr']}"
            f"error {e}. Continuing...{Typgpy.ENDC}")
        if not _recover_interaction:
            raise e
    return False


def deactivate_validator():
    try:
        all_val = staking.get_all_validator_addresses(endpoint=node_config['endpoint'])
        if validator_config["validator-addr"] in all_val:
            log(f"{Typgpy.OKBLUE}Deactivating validator{Typgpy.ENDC}")
            response = cli.single_call(
                ['hmy', 'staking', 'edit-validator', '--validator-addr', f'{validator_config["validator-addr"]}',
                 '--active', 'false', '--node', f'{node_config["endpoint"]}',
                 '--passphrase-file', saved_wallet_pass_path, '--gas-price', f'{validator_config["gas-price"]}'])
            log(f"{Typgpy.OKGREEN}Edit-validator response: {response}{Typgpy.ENDC}")
        else:
            log(f"{Typgpy.FAIL}Address {validator_config['validator-addr']} is not a validator!{Typgpy.ENDC}")
    except (TimeoutError, ConnectionError, RuntimeError, subprocess.CalledProcessError) as e:
        log(traceback.format_exc())
        log(f"{Typgpy.FAIL}{Typgpy.BOLD}Edit-validator error: {e}{Typgpy.ENDC}")
        if not _recover_interaction:
            raise e
        log(f"{Typgpy.WARNING}{Typgpy.BOLD}Continuing...{Typgpy.ENDC}")


def activate_validator():
    try:
        all_val = staking.get_all_validator_addresses(endpoint=node_config['endpoint'])
        if validator_config["validator-addr"] in all_val:
            log(f"{Typgpy.OKBLUE}Activating validator{Typgpy.ENDC}")
            response = cli.single_call(
                ['hmy', 'staking', 'edit-validator', '--validator-addr', f'{validator_config["validator-addr"]}',
                 '--active', 'true', '--node', f'{node_config["endpoint"]}',
                 '--passphrase-file', saved_wallet_pass_path, '--gas-price', f'{validator_config["gas-price"]}'])
            log(f"{Typgpy.OKGREEN}Edit-validator response: {response}{Typgpy.ENDC}")
        else:
            log(f"{Typgpy.FAIL}Address {validator_config['validator-addr']} is not a validator!{Typgpy.ENDC}")
    except (TimeoutError, ConnectionError, RuntimeError, subprocess.CalledProcessError) as e:
        log(traceback.format_exc())
        log(f"{Typgpy.FAIL}{Typgpy.BOLD}Edit-validator error: {e}{Typgpy.ENDC}")
        if not _recover_interaction:
            raise e
        log(f"{Typgpy.WARNING}{Typgpy.BOLD}Continuing...{Typgpy.ENDC}")


def setup(recover_interaction=False):
    log(f"{Typgpy.HEADER}Starting validator setup...{Typgpy.ENDC}")
    old_logging_handlers = _interaction_preprocessor(recover_interaction)
    log(f"{Typgpy.OKBLUE}Create validator config: {Typgpy.OKGREEN}"
        f"{json.dumps(validator_config, indent=4)}{Typgpy.ENDC}")
    log(f"{Typgpy.OKBLUE}Using BLS key(s): {Typgpy.OKGREEN}{node_config['public-bls-keys']}{Typgpy.ENDC}")
    try:
        wait_for_node_response(node_config['endpoint'], verbose=True, tries=120, sleep=1)  # Try for 2 min
        all_val_address = staking.get_all_validator_addresses(endpoint=node_config['endpoint'])
        if validator_config['validator-addr'] in all_val_address:
            log(f"{Typgpy.WARNING}{validator_config['validator-addr']} already in list of validators!{Typgpy.ENDC}")
            validator_info = staking.get_validator_information(validator_config['validator-addr'],
                                                               endpoint=node_config['endpoint'])
            keys_one_chain = set(validator_info['validator']['bls-public-keys'])
            if all(k.replace('0x', '') in keys_on_chain for k in node_config["public-bls-keys"]):
                log(f"{Typgpy.OKBLUE}{Typgpy.BOLD}No BLS key(s) to add to validator!{Typgpy.ENDC}")
            else:
                prompt = "Add BLS key(s) to existing validator? [Y]/n \n> "
                if input_with_print(prompt, 'Y' if recover_interaction else None) in {'Y', 'y', 'yes', 'Yes'}:
                    log(f"{Typgpy.HEADER}{Typgpy.BOLD}Editing validator...{Typgpy.ENDC}")
                    _add_bls_key_to_validator()
        elif validator_config['validator-addr'] not in all_val_address:
            prompt = "Create validator? [Y]/n \n> "
            if input_with_print(prompt, 'Y' if recover_interaction else None) in {'Y', 'y', 'yes', 'Yes'}:
                log(f"{Typgpy.HEADER}{Typgpy.BOLD}Creating new validator...{Typgpy.ENDC}")
                _create_new_validator()
        else:
            node_config['no-validator'] = True
        log(f"{Typgpy.HEADER}{Typgpy.BOLD}Finished setting up validator!{Typgpy.ENDC}")
        verify_node_sync()
        logging.getLogger('AutoNode').handlers = old_logging_handlers
    except Exception as e:
        log(traceback.format_exc())
        logging.getLogger('AutoNode').handlers = old_logging_handlers
        if not _recover_interaction:
            raise SystemExit(e)
        else:
            log(f"{Typgpy.FAIL}{Typgpy.BOLD}Validator creation error: {e}{Typgpy.ENDC}")
            log(f"{Typgpy.WARNING}{Typgpy.BOLD}Continuing...{Typgpy.ENDC}")


def _get_edit_validator_options():
    changeable_fields = {
        "details", "identity", "name", "security-contact", "website",
        "max-total-delegation", "min-self-delegation", "rate"
    }
    edit_validator_fields = {}
    for key, value in validator_config.items():
        if key in changeable_fields:
            edit_validator_fields[key] = validator_config[key]
    return edit_validator_fields


def update_info(recover_interaction=False):
    old_logging_handlers = _interaction_preprocessor(recover_interaction)
    address = validator_config['validator-addr']
    try:
        all_val_address = staking.get_all_validator_addresses(endpoint=node_config['endpoint'])
        if address not in all_val_address:
            log(f"{Typgpy.WARNING}Cannot edit validator information, validator "
                f"{Typgpy.OKGREEN}{address}{Typgpy.WARNING} is not a validator!{Typgpy.ENDC}")
            if recover_interaction:
                return  # clean exit for recover interaction.
            raise SystemExit("Validator does not exist")
        fields = _get_edit_validator_options()
        if fields:
            log(f"{Typgpy.OKBLUE}Updating validator information for {address}: "
                f"{Typgpy.OKGREEN}{json.dumps(fields, indent=2)}{Typgpy.ENDC}")
            cmd = ['hmy', '--node', f'{node_config["endpoint"]}', 'staking', 'edit-validator',
                   '--validator-addr', f'{address}', '--passphrase-file', f'{saved_wallet_pass_path}']
            for key, value in fields.items():
                cmd.extend([f'--{key}', f'{value}'])
            response = cli.single_call(cmd)
            log(f"{Typgpy.OKBLUE}Edit-validator transaction response: {Typgpy.OKGREEN}{response}{Typgpy.ENDC}")
        logging.getLogger('AutoNode').handlers = old_logging_handlers
    except Exception as e:
        log(traceback.format_exc())
        logging.getLogger('AutoNode').handlers = old_logging_handlers
        if not _recover_interaction:
            raise SystemExit(e)
        else:
            log(f"{Typgpy.FAIL}{Typgpy.BOLD}Edit-validator error: {e}{Typgpy.ENDC}")
            log(f"{Typgpy.WARNING}{Typgpy.BOLD}Continuing...{Typgpy.ENDC}")
