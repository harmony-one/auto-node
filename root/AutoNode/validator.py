import os
import sys
import time
import json

import pexpect
import requests
from pyhmy import cli
from pyhmy import (
    Typgpy,
    json_load
)

from .common import (
    directory_lock,
    bls_key_folder
)
from .blockchain import (
    get_latest_header,
    get_latest_headers,
    get_staking_epoch,
    get_current_epoch
)
from .node import (
    wait_for_node_response,
    assert_no_bad_blocks
)
from .util import (
    check_min_bal_on_s0,
)


def add_bls_key_to_validator(val_info, bls_pub_keys, endpoint):
    print(f"{Typgpy.HEADER}{val_info['validator-addr']} already in list of validators!{Typgpy.ENDC}")
    chain_val_info = json_load(cli.single_call(f"hmy --node={endpoint} blockchain "
                                               f"validator information {val_info['validator-addr']}"))["result"]
    bls_keys = chain_val_info["validator"]["bls-public-keys"]
    directory_lock.acquire()
    for k in bls_pub_keys:
        if k not in bls_keys:  # Add imported BLS key to existing validator if needed
            print(f"{Typgpy.OKBLUE}adding bls key: {k} "
                  f"to validator: {val_info['validator-addr']}{Typgpy.ENDC}")
            os.chdir("/root/bin")
            try:
                # TODO: test this to make sure that this works.
                response = cli.single_call(f"hmy --node={endpoint} staking edit-validator "
                                           f"--validator-addr {val_info['validator-addr']} "
                                           f"--add-bls-key {k} --passphrase-file /.wallet_passphrase "
                                           f"--bls-pubkeys-dir {bls_key_folder}")
                print(f"\n{Typgpy.OKBLUE}Edit-validator transaction response: "
                      f"{Typgpy.OKGREEN}{response}{Typgpy.ENDC}")
            except (json.decoder.JSONDecodeError, RuntimeError) as e:
                print(f"{Typgpy.FAIL}Failed to edit validator!\n\tError: {e}{Typgpy.ENDC}")
    directory_lock.release()
    new_val_info = json_load(cli.single_call(f"hmy --node={endpoint} blockchain "
                                             f"validator information {val_info['validator-addr']}"))["result"]
    new_bls_keys = new_val_info["validator"]["bls-public-keys"]
    print(f"{Typgpy.OKBLUE}{val_info['validator-addr']} updated bls keys: {new_bls_keys}{Typgpy.ENDC}")
    verify_node_sync(endpoint)
    print()


def verify_node_sync(endpoint):
    print(f"{Typgpy.OKBLUE}Verifying Node Sync...{Typgpy.ENDC}")
    wait_for_node_response("http://localhost:9500/")
    curr_headers = get_latest_headers("http://localhost:9500/")
    curr_epoch_shard = curr_headers['shard-chain-header']['epoch']
    curr_epoch_beacon = curr_headers['beacon-chain-header']['epoch']
    ref_epoch = get_latest_header(endpoint)['epoch']
    while curr_epoch_shard != ref_epoch or curr_epoch_beacon != ref_epoch:
        sys.stdout.write(f"\rWaiting for node to sync: shard epoch ({curr_epoch_shard}/{ref_epoch}) "
                         f"& beacon epoch ({curr_epoch_beacon}/{ref_epoch})")
        sys.stdout.flush()
        time.sleep(2)
        assert_no_bad_blocks()
        try:
            curr_headers = get_latest_headers("http://localhost:9500/")
            curr_epoch_shard = curr_headers['shard-chain-header']['epoch']
            curr_epoch_beacon = curr_headers['beacon-chain-header']['epoch']
            ref_epoch = get_latest_header(endpoint)['epoch']
        except (ConnectionError, requests.exceptions.ConnectionError, KeyError) as e:
            print(f"{Typgpy.FAIL}Warning failed to verify node sync {e}{Typgpy.ENDC}")
            pass  # Ignore any errors and try again
    print(f"\n{Typgpy.OKGREEN}Node synced to current epoch{Typgpy.ENDC}")


def create_new_validator(val_info, bls_pub_keys, endpoint):
    print(f"{Typgpy.HEADER}Checking validator...{Typgpy.ENDC}")
    staking_epoch = get_staking_epoch(endpoint)
    curr_epoch = get_current_epoch(endpoint)
    print(f"{Typgpy.OKBLUE}Verifying Epoch...{Typgpy.ENDC}")
    while curr_epoch < staking_epoch:  # WARNING: using staking epoch for extra security of configs.
        sys.stdout.write(f"\rWaiting for staking epoch ({staking_epoch}) -- current epoch: {curr_epoch}")
        sys.stdout.flush()
        time.sleep(8)  # Assumption of 8 second block time...
        assert_no_bad_blocks()
        curr_epoch = get_current_epoch(endpoint)
    print(f"{Typgpy.OKGREEN}Network is at or past staking epoch{Typgpy.ENDC}")
    print(f"{Typgpy.OKBLUE}Verifying Balance...{Typgpy.ENDC}")
    # Check validator amount +1 for gas fees.
    if not check_min_bal_on_s0(val_info['validator-addr'], val_info['amount'] + 1, endpoint):
        print(f"{Typgpy.FAIL}Cannot create validator, {val_info['validator-addr']} "
              f"does not have sufficient funds.{Typgpy.ENDC}")
        return
    else:
        print(f"{Typgpy.OKGREEN}Address: {val_info['validator-addr']} has enough funds{Typgpy.ENDC}")
    verify_node_sync(endpoint)
    print(f"\n{Typgpy.OKBLUE}Sending create validator transaction...{Typgpy.ENDC}")
    send_create_validator_tx(val_info, bls_pub_keys, endpoint)
    print()


def send_create_validator_tx(val_info, bls_pub_keys, endpoint):
    directory_lock.acquire()
    os.chdir("/root/bin")  # Needed for implicit BLS key...
    try:
        # TODO: test this to make sure that this works.
        response = cli.single_call(f'hmy --node={endpoint} staking create-validator '
                                   f'--validator-addr {val_info["validator-addr"]} --name "{val_info["name"]}" '
                                   f'--identity "{val_info["identity"]}" --website "{val_info["website"]}" '
                                   f'--security-contact "{val_info["security-contact"]}" --details "{val_info["details"]}" '
                                   f'--rate {val_info["rate"]} --max-rate {val_info["max-rate"]} '
                                   f'--max-change-rate {val_info["max-change-rate"]} '
                                   f'--min-self-delegation {val_info["min-self-delegation"]} '
                                   f'--max-total-delegation {val_info["max-total-delegation"]} '
                                   f'--amount {val_info["amount"]} --bls-pubkeys {",".join(bls_pub_keys)} '
                                   f'--passphrase-file /.wallet_passphrase '
                                   f'--bls-pubkeys-dir {bls_key_folder}')
        print(f"{Typgpy.OKBLUE}Created Validator!\n{Typgpy.OKGREEN}{response}{Typgpy.ENDC}")
    except (json.decoder.JSONDecodeError, RuntimeError) as e:
        print(f"{Typgpy.FAIL}Failed to edit validator!\n\tError: {e}{Typgpy.ENDC}")
    directory_lock.release()
