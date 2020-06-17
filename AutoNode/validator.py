"""
This library takes care of all validator related commands.
"""

import sys
import time
import json
import logging
import subprocess
import traceback
import pexpect

from decimal import Decimal

from pyhmy import (
    blockchain,
    cli,
    staking,
    account,
    numbers,
    Typgpy,
    exceptions
)

from .common import (
    log,
    bls_key_dir,
    node_config,
    validator_config,
    check_interval,
)
from .node import (
    log_path,
    wait_for_node_response,
    assert_no_bad_blocks,
    assert_started as assert_node_started,
    is_signing
)
from .initialize import (
    setup_validator_config,
    setup_wallet_passphrase,
)
from .util import (
    check_min_bal_on_s0,
    input_with_print,
    get_simple_rotating_log_handler,
    get_wallet_passphrase,
    interact_wallet_passphrase
)

_balance_buffer = Decimal(1)
_hard_reset_recovery = False


def _interaction_preprocessor(hard_reset_recovery):
    """
    All user calls (i.e: validator setup) must be processed by this
    """
    global _hard_reset_recovery
    _hard_reset_recovery = hard_reset_recovery
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
    chain_val_info = get_validator_information()
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
    passphrase = get_wallet_passphrase()
    count = 0
    while True:
        count += 1
        try:
            cmd = ['hmy', '--node', f'{node_config["endpoint"]}', 'staking', 'edit-validator',
                   '--validator-addr', f'{validator_config["validator-addr"]}',
                   '--add-bls-key', bls_key_to_add, '--bls-pubkeys-dir', bls_key_dir, '--passphrase']
            if validator_config["gas-price"]:
                cmd.extend(['--gas-price', f'{validator_config["gas-price"]}'])
            proc = cli.expect_call(cmd)
            interact_wallet_passphrase(proc, passphrase)
            proc.expect(pexpect.EOF)
            response = proc.before.decode()
            log(f"{Typgpy.OKBLUE}Edit-validator transaction response: "
                f"{Typgpy.OKGREEN}{response}{Typgpy.ENDC}")
            return
        except (RuntimeError, TimeoutError, ConnectionError, subprocess.CalledProcessError) as e:
            log(f"{Typgpy.FAIL}Edit-validator transaction failure (attempt {count}). Error: {e}{Typgpy.ENDC}")
            if not _hard_reset_recovery:
                raise e
            log(f"{Typgpy.WARNING}Trying again in {check_interval} seconds.{Typgpy.ENDC}")
            time.sleep(check_interval)


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
            if not _hard_reset_recovery:
                raise SystemExit("Create Validator Error")
            log(f"{Typgpy.WARNING}Checking again in {check_interval} seconds.{Typgpy.ENDC}")
            time.sleep(check_interval)
        else:
            log(f"{Typgpy.OKGREEN}Address: {validator_config['validator-addr']} has enough funds{Typgpy.ENDC}")
            return


def _send_create_validator_tx():
    log(f"{Typgpy.OKBLUE}Sending create validator transaction...{Typgpy.ENDC}")
    passphrase = get_wallet_passphrase()
    count = 0
    while True:
        count += 1
        try:
            cmd = ['hmy', '--node', f'{node_config["endpoint"]}', 'staking', 'create-validator',
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
                   '--bls-pubkeys-dir', bls_key_dir, "--passphrase"]
            if validator_config["gas-price"]:
                cmd.extend(['--gas-price', f'{validator_config["gas-price"]}'])
            proc = cli.expect_call(cmd)
            interact_wallet_passphrase(proc, passphrase)
            proc.expect(pexpect.EOF)
            response = proc.before.decode()
            log(f"{Typgpy.OKBLUE}Create-validator transaction response: "
                f"{Typgpy.OKGREEN}{response}{Typgpy.ENDC}")
            return
        except (RuntimeError, TimeoutError, ConnectionError, subprocess.CalledProcessError) as e:
            log(f"{Typgpy.FAIL}Create-validator transaction failure (attempt {count}). Error: {e}{Typgpy.ENDC}")
            if not _hard_reset_recovery:
                raise e
            log(f"{Typgpy.WARNING}Trying again in {check_interval} seconds.{Typgpy.ENDC}")
            time.sleep(check_interval)


def _create_new_validator():
    _verify_prestaking_epoch()
    _verify_account_balance(Decimal(validator_config['amount']) + _balance_buffer)
    _send_create_validator_tx()


def _verify_node_sync():
    log(f"{Typgpy.OKBLUE}Verifying Node Sync...{Typgpy.ENDC}")
    wait_for_node_response("http://localhost:9500/", sleep=1, verbose=True)
    wait_for_node_response(node_config['endpoint'], sleep=1, verbose=True)
    curr_headers = blockchain.get_latest_headers()
    curr_epoch_shard = curr_headers['shard-chain-header']['epoch']
    curr_epoch_beacon = curr_headers['beacon-chain-header']['epoch']
    ref_epoch = blockchain.get_current_epoch(endpoint=node_config['endpoint'])
    has_looped = False
    if curr_epoch_shard < ref_epoch or curr_epoch_beacon < ref_epoch:
        prompt = "Waiting for node to sync. Deactivate validator? [Y]/n \n> "
        auto_interaction = 'Y' if _hard_reset_recovery else None
        if is_active_validator() and can_safe_stop_node() \
                and input_with_print(prompt, auto_interaction).lower() in {'y', 'yes'}:
            try:
                log(f"{Typgpy.OKBLUE}Deactivating validator until node is synced.{Typgpy.ENDC}")
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
        if not _hard_reset_recovery:
            raise SystemExit("Invalid node sync")
    if has_looped:
        log("")
    log(f"{Typgpy.OKGREEN}Node synced to current epoch...{Typgpy.ENDC}")
    try:
        prompt = "Node is synced and ready to validate. Activate validator? [Y]/n \n> "
        auto_interaction = 'Y' if _hard_reset_recovery else None
        if not is_active_validator() and input_with_print(prompt, auto_interaction).lower() in {'y', 'yes'}:
            activate_validator()
    except (TimeoutError, ConnectionError, RuntimeError, subprocess.CalledProcessError) as e:
        log(f"{Typgpy.FAIL}Unable to activate validator {validator_config['validator-addr']}"
            f"error {e}. Continuing...{Typgpy.ENDC}")


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


def _first_setup():
    """
    Initial setup done on first run of validator setup.
    """
    while True:
        try:
            setup_validator_config()
            assert_node_started(do_log=True)
            setup_wallet_passphrase()
            return
        except AssertionError as e:
            log(f"{Typgpy.WARNING}Assertion error: {e}{Typgpy.ENDC}")
            if input_with_print("Try again? [Y/n]\n> ").lower() not in {'y', 'yes'}:
                raise e


def get_validator_information():
    """
    Get the current validator information from the configured endpoint.
    """
    return staking.get_validator_information(validator_config['validator-addr'], endpoint=node_config['endpoint'])


def get_balances():
    """
    Get the balances of the configured validator (if possible)
    """
    balances = account.get_balance_on_all_shards(validator_config['validator-addr'], endpoint=node_config['endpoint'])
    for bal in balances:
        bal['balance'] = float(numbers.convert_atto_to_one(bal['balance']))
    return balances


def is_active_validator():
    """
    Default to false if exception to be defensive.
    """
    try:
        val_chain_info = get_validator_information()
        return val_chain_info['active-status'] == 'active'
    except (exceptions.RPCError, exceptions.RequestsError, exceptions.RequestsTimeoutError) as e:
        log(f"{Typgpy.WARNING}Could not fetch validator active status, error: {e}{Typgpy.ENDC}")
        return False


def deactivate_validator():
    try:
        all_val = staking.get_all_validator_addresses(endpoint=node_config['endpoint'])
        if validator_config["validator-addr"] in all_val:
            log(f"{Typgpy.OKBLUE}Deactivating validator{Typgpy.ENDC}")
            passphrase = get_wallet_passphrase()
            cmd = ['hmy', 'staking', 'edit-validator',
                   '--validator-addr', f'{validator_config["validator-addr"]}',
                   '--active', 'false', '--node', f'{node_config["endpoint"]}',
                   '--passphrase']
            if validator_config["gas-price"]:
                cmd.extend(['--gas-price', f'{validator_config["gas-price"]}'])
            proc = cli.expect_call(cmd)
            interact_wallet_passphrase(proc, passphrase)
            proc.expect(pexpect.EOF)
            response = proc.before.decode()
            log(f"{Typgpy.OKGREEN}Edit-validator response: {response}{Typgpy.ENDC}")
        else:
            log(f"{Typgpy.FAIL}Address {validator_config['validator-addr']} is not a validator!{Typgpy.ENDC}")
    except (TimeoutError, ConnectionError, RuntimeError, subprocess.CalledProcessError) as e:
        log(traceback.format_exc())
        log(f"{Typgpy.FAIL}{Typgpy.BOLD}Edit-validator error: {e}{Typgpy.ENDC}")
        if not _hard_reset_recovery:
            raise e
        log(f"{Typgpy.WARNING}{Typgpy.BOLD}Continuing...{Typgpy.ENDC}")


def activate_validator():
    try:
        all_val = staking.get_all_validator_addresses(endpoint=node_config['endpoint'])
        if validator_config["validator-addr"] in all_val:
            log(f"{Typgpy.OKBLUE}Activating validator{Typgpy.ENDC}")
            passphrase = get_wallet_passphrase()
            cmd = ['hmy', 'staking', 'edit-validator', '--validator-addr', f'{validator_config["validator-addr"]}',
                   '--active', 'true', '--node', f'{node_config["endpoint"]}',
                   '--passphrase']
            if validator_config["gas-price"]:
                cmd.extend(['--gas-price', f'{validator_config["gas-price"]}'])
            proc = cli.expect_call(cmd)
            interact_wallet_passphrase(proc, passphrase)
            proc.expect(pexpect.EOF)
            response = proc.before.decode()
            log(f"{Typgpy.OKGREEN}Edit-validator response: {response}{Typgpy.ENDC}")
        else:
            log(f"{Typgpy.FAIL}Address {validator_config['validator-addr']} is not a validator!{Typgpy.ENDC}")
    except (TimeoutError, ConnectionError, RuntimeError, subprocess.CalledProcessError) as e:
        log(traceback.format_exc())
        log(f"{Typgpy.FAIL}{Typgpy.BOLD}Edit-validator error: {e}{Typgpy.ENDC}")
        if not _hard_reset_recovery:
            raise e
        log(f"{Typgpy.WARNING}{Typgpy.BOLD}Continuing...{Typgpy.ENDC}")


def collect_reward():
    try:
        all_val = staking.get_all_validator_addresses(endpoint=node_config['endpoint'])
        if validator_config["validator-addr"] in all_val:
            log(f"{Typgpy.OKBLUE}Collecting rewards{Typgpy.ENDC}")
            passphrase = get_wallet_passphrase()
            cmd = ['hmy', 'staking', 'collect-rewards', '--delegator-addr', validator_config['validator-addr'],
                   '--node', f'{node_config["endpoint"]}', '--passphrase']
            if validator_config["gas-price"]:
                cmd.extend(['--gas-price', f'{validator_config["gas-price"]}'])
            proc = cli.expect_call(cmd)
            interact_wallet_passphrase(proc, passphrase)
            proc.expect(pexpect.EOF)
            response = proc.before.decode()
            log(f"{Typgpy.OKGREEN}Collect rewards response: {response}{Typgpy.ENDC}")
        else:
            log(f"{Typgpy.FAIL}Address {validator_config['validator-addr']} is not a validator!{Typgpy.ENDC}")
    except (TimeoutError, ConnectionError, RuntimeError, subprocess.CalledProcessError) as e:
        log(traceback.format_exc())
        log(f"{Typgpy.FAIL}{Typgpy.BOLD}Edit-validator error: {e}{Typgpy.ENDC}")
        if not _hard_reset_recovery:
            raise e
        log(f"{Typgpy.WARNING}{Typgpy.BOLD}Continuing...{Typgpy.ENDC}")


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
        if not _hard_reset_recovery:  # Do not throw error on hard resets.
            raise e
    return False


def setup(hard_reset_recovery=False):
    log(f"{Typgpy.HEADER}Starting validator setup...{Typgpy.ENDC}")
    old_logging_handlers = _interaction_preprocessor(hard_reset_recovery)
    log(f"{Typgpy.OKBLUE}Using BLS key(s): {Typgpy.OKGREEN}{node_config['public-bls-keys']}{Typgpy.ENDC}")
    try:
        if not hard_reset_recovery:
            _first_setup()
        wait_for_node_response(node_config['endpoint'], verbose=True, tries=120, sleep=1)  # Try for 2 min
        all_val_address = staking.get_all_validator_addresses(endpoint=node_config['endpoint'])
        if validator_config['validator-addr'] in all_val_address:
            log(f"{Typgpy.WARNING}{validator_config['validator-addr']} already in list of validators!{Typgpy.ENDC}")
            validator_info = get_validator_information()
            keys_on_chain = set(validator_info['validator']['bls-public-keys'])
            if all(k in keys_on_chain for k in node_config["public-bls-keys"]):
                log(f"{Typgpy.OKBLUE}{Typgpy.BOLD}No BLS key(s) to add to validator!{Typgpy.ENDC}")
            else:
                prompt = "Add BLS key(s) to existing validator? [Y]/n \n> "
                if input_with_print(prompt, 'Y' if hard_reset_recovery else None).lower() in {'y', 'yes'}:
                    log(f"{Typgpy.HEADER}{Typgpy.BOLD}Editing validator...{Typgpy.ENDC}")
                    _add_bls_key_to_validator()
        elif validator_config['validator-addr'] not in all_val_address:
            prompt = "Create validator? [Y]/n \n> "
            if input_with_print(prompt, 'Y' if hard_reset_recovery else None).lower() in {'y', 'yes'}:
                log(f"{Typgpy.HEADER}{Typgpy.BOLD}Creating new validator...{Typgpy.ENDC}")
                _create_new_validator()
        else:
            node_config['no-validator'] = True
        log(f"{Typgpy.HEADER}{Typgpy.BOLD}Finished setting up validator!{Typgpy.ENDC}")
        _verify_node_sync()
        logging.getLogger('AutoNode').handlers = old_logging_handlers
    except Exception as e:
        log(traceback.format_exc())
        logging.getLogger('AutoNode').handlers = old_logging_handlers
        if not _hard_reset_recovery:
            raise SystemExit(e)
        else:
            log(f"{Typgpy.FAIL}{Typgpy.BOLD}Validator creation error: {e}{Typgpy.ENDC}")
            log(f"{Typgpy.WARNING}{Typgpy.BOLD}Continuing...{Typgpy.ENDC}")


def update_info(hard_reset_recovery=False):
    old_logging_handlers = _interaction_preprocessor(hard_reset_recovery)
    address = validator_config['validator-addr']
    try:
        all_val_address = staking.get_all_validator_addresses(endpoint=node_config['endpoint'])
        if address not in all_val_address:
            log(f"{Typgpy.WARNING}Cannot edit validator information, validator "
                f"{Typgpy.OKGREEN}{address}{Typgpy.WARNING} is not a validator!{Typgpy.ENDC}")
            if hard_reset_recovery:
                return  # clean exit for hard resets
            raise SystemExit("Validator does not exist")
        fields = _get_edit_validator_options()
        if fields:
            log(f"{Typgpy.OKBLUE}Updating validator information for {address}: "
                f"{Typgpy.OKGREEN}{json.dumps(fields, indent=2)}{Typgpy.ENDC}")
            passphrase = get_wallet_passphrase()
            cmd = ['hmy', '--node', f'{node_config["endpoint"]}', 'staking', 'edit-validator',
                   '--validator-addr', f'{address}', '--passphrase']
            for key, value in fields.items():
                cmd.extend([f'--{key}', f'{value}'])
            proc = cli.expect_call(cmd)
            interact_wallet_passphrase(proc, passphrase)
            proc.expect(pexpect.EOF)
            response = proc.before.decode()
            log(f"{Typgpy.OKBLUE}Edit-validator transaction response: {Typgpy.OKGREEN}{response}{Typgpy.ENDC}")
        logging.getLogger('AutoNode').handlers = old_logging_handlers
    except Exception as e:
        log(traceback.format_exc())
        logging.getLogger('AutoNode').handlers = old_logging_handlers
        if not _hard_reset_recovery:
            raise SystemExit(e)
        else:
            log(f"{Typgpy.FAIL}{Typgpy.BOLD}Edit-validator error: {e}{Typgpy.ENDC}")
            log(f"{Typgpy.WARNING}{Typgpy.BOLD}Continuing...{Typgpy.ENDC}")


def can_safe_stop_node():
    """
    Determine if a node can be stopped. Conditions:
    If elected, BLS keys must not be earning (if present), otherwise can shutdown.
    """
    if node_config['no-validator']:
        return True
    if not get_validator_information()['currently-in-committee']:
        return True
    return not is_signing()
