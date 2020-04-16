import sys
import time
import json

from pyhmy import cli
from pyhmy import (
    Typgpy,
)

from .common import (
    bls_key_dir,
    node_config,
    validator_config,
    saved_wallet_pass_path,
    harmony_dir,
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
    wait_for_node_response,
    assert_no_bad_blocks
)
from .util import (
    check_min_bal_on_s0,
    input_with_print
)

log_path = f"{harmony_dir}/autonode_validator.log"


def _add_bls_key_to_validator():
    wait_for_node_response(node_config['endpoint'], verbose=True)
    chain_val_info = get_validator_information(validator_config['validator-addr'], node_config['endpoint'])
    bls_keys = set(x.replace('0x', '') for x in chain_val_info["validator"]["bls-public-keys"])
    for k in (x.replace('0x', '') for x in node_config["public-bls-keys"]):
        if k not in bls_keys:  # Add imported BLS key to existing validator if needed
            print(f"{Typgpy.OKBLUE}Adding bls key: {Typgpy.OKGREEN}{k}{Typgpy.OKBLUE} "
                  f"to validator: {Typgpy.OKGREEN}{validator_config['validator-addr']}{Typgpy.ENDC}")
            try:
                wait_for_node_response(node_config['endpoint'], verbose=True)
                response = cli.single_call(f"hmy --node={node_config['endpoint']} staking edit-validator "
                                           f"--validator-addr {validator_config['validator-addr']} "
                                           f"--add-bls-key {k} --passphrase-file {saved_wallet_pass_path} "
                                           f"--bls-pubkeys-dir {bls_key_dir}")
                print(f"\n{Typgpy.OKBLUE}Edit-validator transaction response: "
                      f"{Typgpy.OKGREEN}{response}{Typgpy.ENDC}")
            except (json.decoder.JSONDecodeError, RuntimeError) as e:
                print(f"{Typgpy.FAIL}Failed to edit validator!\n\tError: {e}{Typgpy.ENDC}")
        else:
            print(f"{Typgpy.WARNING}Bls key: {Typgpy.OKGREEN}{k}{Typgpy.WARNING} "
                  f"is already present, ignoring...{Typgpy.ENDC}")
    _verify_node_sync()


def _verify_node_sync():
    print(f"{Typgpy.OKBLUE}Verifying Node Sync...{Typgpy.ENDC}")
    wait_for_node_response(node_config['endpoint'], verbose=True)
    wait_for_node_response("http://localhost:9500/", verbose=True)
    curr_headers = get_latest_headers("http://localhost:9500/")
    curr_epoch_shard = curr_headers['shard-chain-header']['epoch']
    curr_epoch_beacon = curr_headers['beacon-chain-header']['epoch']
    ref_epoch = get_latest_header(node_config['endpoint'])['epoch']
    has_looped = False
    while curr_epoch_shard != ref_epoch or curr_epoch_beacon != ref_epoch:
        sys.stdout.write(f"\rWaiting for node to sync: shard epoch ({curr_epoch_shard}/{ref_epoch}) "
                         f"& beacon epoch ({curr_epoch_beacon}/{ref_epoch})")
        sys.stdout.flush()
        has_looped = True
        time.sleep(2)
        assert_no_bad_blocks()
        curr_headers = get_latest_headers("http://localhost:9500/")
        curr_epoch_shard = curr_headers['shard-chain-header']['epoch']
        curr_epoch_beacon = curr_headers['beacon-chain-header']['epoch']
        wait_for_node_response(node_config['endpoint'], verbose=False)
        ref_epoch = get_latest_header(node_config['endpoint'])['epoch']
    if has_looped:
        print("")
    print(f"{Typgpy.OKGREEN}Node synced to current epoch{Typgpy.ENDC}")


def _create_new_validator():
    wait_for_node_response(node_config['endpoint'], verbose=True)
    print(f"{Typgpy.HEADER}Checking validator...{Typgpy.ENDC}")
    staking_epoch = get_staking_epoch(node_config['endpoint'])
    curr_epoch = get_current_epoch(node_config['endpoint'])
    print(f"{Typgpy.OKBLUE}Verifying Epoch...{Typgpy.ENDC}")
    while curr_epoch < staking_epoch:  # WARNING: using staking epoch for extra security of configs.
        sys.stdout.write(f"\rWaiting for staking epoch ({staking_epoch}) -- current epoch: {curr_epoch}")
        sys.stdout.flush()
        time.sleep(8)  # Assumption of 8 second block time...
        assert_no_bad_blocks()
        wait_for_node_response(node_config['endpoint'], verbose=True)
        curr_epoch = get_current_epoch(node_config['endpoint'])
    print(f"{Typgpy.OKGREEN}Network is at or past staking epoch{Typgpy.ENDC}")
    print(f"{Typgpy.OKBLUE}Verifying Balance...{Typgpy.ENDC}")
    # Check validator amount +1 for gas fees.
    if not check_min_bal_on_s0(validator_config['validator-addr'], validator_config['amount'] + 1, node_config['endpoint']):
        print(f"{Typgpy.FAIL}Cannot create validator, {validator_config['validator-addr']} "
              f"does not have sufficient funds.{Typgpy.ENDC}")
        raise RuntimeError("Create Validator Error")
    else:
        print(f"{Typgpy.OKGREEN}Address: {validator_config['validator-addr']} has enough funds{Typgpy.ENDC}")
    _verify_node_sync()
    print(f"{Typgpy.OKBLUE}Sending create validator transaction...{Typgpy.ENDC}")
    _send_create_validator_tx()


def _send_create_validator_tx():
    wait_for_node_response(node_config['endpoint'], verbose=True)
    try:
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
        print(f"{Typgpy.OKBLUE}Created Validator!\n{Typgpy.OKGREEN}{response}{Typgpy.ENDC}")
    except (json.decoder.JSONDecodeError, RuntimeError) as e:
        print(f"{Typgpy.FAIL}Failed to edit validator!\n\tError: {e}{Typgpy.ENDC}")


def _setup(recover_interaction):
    wait_for_node_response(node_config['endpoint'], verbose=True)
    all_val_address = get_all_validator_addresses(node_config['endpoint'])  # Check BLS key with validator if it exists
    if validator_config['validator-addr'] in all_val_address:
        print(f"{Typgpy.WARNING}{validator_config['validator-addr']} already in list of validators!{Typgpy.ENDC}")
        if recover_interaction \
                or input_with_print("Add BLS key(s) to existing validator? [Y]/n \n> ") in {'Y', 'y', 'yes', 'Yes'}:
            print(f"{Typgpy.HEADER}{Typgpy.BOLD}Editing validator...{Typgpy.ENDC}")
            _add_bls_key_to_validator()
    elif validator_config['validator-addr'] not in all_val_address:
        if recover_interaction \
                or input_with_print("Create validator? [Y]/n \n> ") in {'Y', 'y', 'yes', 'Yes'}:
            print(f"{Typgpy.HEADER}{Typgpy.BOLD}Creating new validator...{Typgpy.ENDC}")
            _create_new_validator()
    else:
        node_config['no-validator'] = True


def setup(recover_interaction=False, end_sleep=10):
    if node_config['no-validator']:
        print(f"{Typgpy.WARNING}Node config specifies not validator automation, exiting...{Typgpy.ENDC}")
        return

    print(f"{Typgpy.OKBLUE}Create validator config: {Typgpy.OKGREEN}"
          f"{json.dumps(validator_config, indent=4)}{Typgpy.ENDC}")
    print(f"{Typgpy.OKBLUE}Using BLS key(s): {Typgpy.OKGREEN}{node_config['public-bls-keys']}{Typgpy.ENDC}")
    try:
        _setup(recover_interaction)
        time.sleep(end_sleep)
    except Exception as e:
        time.sleep(end_sleep)
        raise e

