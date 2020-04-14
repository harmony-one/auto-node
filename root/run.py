#!/usr/bin/env python3
import argparse
import shutil
import datetime
import random
import getpass
import traceback
import json
import os
import time
import subprocess
import sys
from argparse import RawTextHelpFormatter

from pyhmy import cli
from pyhmy import (
    json_load,
    Typgpy
)

import AutoNode

# TODO: fix reading file format
# TODO: implement new .pass assumptions, BLS flow with export, and document in README.

with open("./node/validator_config.json", 'r',
          encoding='utf8') as f:  # WARNING: assumption of copied file on docker run.
    validator_info = json.load(f)
imported_bls_key_folder = "/root/imported_bls_keys"  # WARNING: assumption made on auto_node.sh
imported_bls_pass_folder = "/root/imported_bls_pass"  # WARNING: assumption made on auto_node.sh
imported_wallet_pass_folder = "/root/imported_wallet_pass"  # WARNING: assumption made on auto_node.sh
auto_node_errors = "/root/node/auto_node_errors.log"
with open(auto_node_errors, 'a', encoding='utf8') as f:  # TODO: convert this into proper log file...
    f.write("== AutoNode Run Errors ==\n")

node_pid = -1
recover_interaction = False  # Only enabled if recovering a node...


def parse_args():
    parser = argparse.ArgumentParser(description='== Run a Harmony node & validator automagically ==',
                                     usage="auto_node.sh [--container=CONTAINER_NAME] run [OPTIONS]",
                                     formatter_class=RawTextHelpFormatter, add_help=False)
    parser.add_argument('-h', '--help', action='help', default=argparse.SUPPRESS,
                        help='Show this help message and exit')
    parser.add_argument("--auto-active", action="store_true",
                        help="Always try to set active when EPOS status is inactive.")
    parser.add_argument("--auto-reset", action="store_true",
                        help="Automatically reset node during hard resets.")
    parser.add_argument("--clean", action="store_true", help="Clean shared node directory before starting node.")
    parser.add_argument("--shard", default=None,
                        help="Specify shard of generated bls key.\n  "
                             "Only used if no BLS keys are not provided.", type=int)
    parser.add_argument("--network", help="Network to connect to (staking, partner, stress).\n  "
                                          "Default: 'staking'.", type=str, default='staking')
    parser.add_argument("--duration", type=int, help="Duration of how long the node is to run in seconds.\n  "
                                                     "Default is forever.", default=float('inf'))
    parser.add_argument("--beacon-endpoint", dest="endpoint", type=str, default=AutoNode.default_endpoint,
                        help=f"Beacon chain (shard 0) endpoint for staking transactions.\n  "
                             f"Default is {AutoNode.default_endpoint}")
    return parser.parse_args()


def import_validator_address():
    if validator_info["validator-addr"] is None:
        print(f"{Typgpy.OKBLUE}Selecting random address in shared CLI keystore to be validator.{Typgpy.ENDC}")
        keys_list = list(cli.get_accounts_keystore().values())
        if not keys_list:
            print(f"{Typgpy.FAIL}Shared CLI keystore has no wallets{Typgpy.ENDC}")
            exit(-1)
        validator_info["validator-addr"] = random.choice(keys_list)
    elif validator_info['validator-addr'] not in cli.get_accounts_keystore().values():
        print(f"{Typgpy.FAIL}Cannot create validator, {validator_info['validator-addr']} "
              f"not in shared CLI keystore.{Typgpy.ENDC}")
        exit(-1)
    return validator_info["validator-addr"]


def import_bls_passphrase():
    """
    Import BLS passphrase (from user or file).
    Returns None if using imported passphrase files.
    """
    bls_keys = [x for x in os.listdir(imported_bls_key_folder) if not x.startswith('.')]
    bls_pass = [x for x in os.listdir(imported_bls_pass_folder) if not x.startswith('.')]
    imported_bls_keys, imported_bls_pass = set(), set()
    for k in bls_keys:
        tok = k.split(".")
        if len(tok) != 2 or len(tok[0]) != AutoNode.bls_key_len or tok[1] != 'key':
            print(f"{Typgpy.FAIL}Imported BLS key file {k} has an invalid file format. "
                  f"Must be `<BLS-pub-key>.key`{Typgpy.ENDC}")
            raise RuntimeError("Bad BLS import")
        imported_bls_keys.add(k[0])
    for p in bls_pass:
        tok = p.split(".")
        if len(tok) != 2 or len(tok[0]) != AutoNode.bls_key_len or tok[1] != 'pass':
            print(f"{Typgpy.FAIL}Imported BLS passphrase file {p} has an invalid file format. "
                  f"Must be `<BLS-pub-key>.pass`{Typgpy.ENDC}")
            raise RuntimeError("Bad BLS import")
        imported_bls_pass.add(p[0])
    if bls_pass and not bls_keys:
        print(f"{Typgpy.WARNING}BLS passphrase file(s) were imported but no BLS key files were imported. "
              f"Passphrase files are ignored.{Typgpy.ENDC}")
        return getpass.getpass(f"Enter passphrase for all BLS keys\n> ")
    if bls_keys and bls_pass:
        for k in imported_bls_keys:
            if k not in imported_bls_pass:
                print(
                    f"{Typgpy.FAIL}Imported BLS key file for {k} does not have an imported passphrase file{Typgpy.ENDC}")
                raise RuntimeError("Bad BLS import")
        return None
    return getpass.getpass(f"Enter passphrase for all BLS keys\n> ")


def import_wallet_passphrase(address):
    wallet_pass = [x for x in os.listdir(imported_wallet_pass_folder) if not x.startswith('.')]
    for p in wallet_pass:
        tok = p.split('.')
        if len(tok) != 2 or not tok[0].startswith('one1') or tok[1] != 'pass':
            print(f"{Typgpy.FAIL}Imported wallet passphrase file {p} has an invalid file format. "
                  f"Must be `<ONE-address>.pass`{Typgpy.ENDC}")
            raise RuntimeError("Bad wallet passphrase import")
        if address == tok[0]:
            with open(f"{imported_wallet_pass_folder}/{p}", 'r', encoding='utf8') as f:
                return f.read()
    return getpass.getpass(f"Enter wallet passphrase for {validator_info['validator-addr']}\n> ")


def import_bls(passphrase):
    """
    Import BLS keys using imported passphrase files if passphrase is None.
    Otherwise, use passphrase for imported BLS key files or generated BLS keys.

    Assumes that imported BLS key files and passphrase have been validated.
    """
    bls_keys = [x for x in os.listdir(imported_bls_key_folder) if not x.startswith('.')]
    bls_pass = [x for x in os.listdir(imported_bls_pass_folder) if not x.startswith('.')]
    if passphrase is None:
        for k in bls_keys:
            shutil.copy(f"{imported_bls_key_folder}/{k}", AutoNode.bls_key_folder)
            shutil.copy(f"{imported_bls_key_folder}/{k}", "/root/bin")  # For CLI
        for k in bls_pass:
            shutil.copy(f"{imported_bls_pass_folder}/{k}", AutoNode.bls_key_folder)
        # Verify Passphrase
        for k in bls_keys:
            try:
                cli.single_call(f"hmy keys recover-bls-key {imported_bls_key_folder}/{k} "
                                f"--passphrase-file {imported_bls_pass_folder}/{k.replace('.key', '.pass')}")
            except RuntimeError as e:
                print(f"{Typgpy.FAIL}Passphrase file for {k} is not correct. Error: {e}{Typgpy.ENDC}")
                raise RuntimeError("Bad BLS import") from e
        return [k.replace('.key', '').replace('0x', '') for k in bls_keys]

    with open("/tmp/bls_pass", 'w', encoding='utf8') as fw:
        fw.write(passphrase)
    if len(bls_keys) > 0:
        if args.shard is not None:
            print(f"{Typgpy.WARNING}[!] Shard option ignored since BLS keys were imported.{Typgpy.ENDC}")
            time.sleep(3)  # Sleep so user can read message
        for k in bls_keys:
            try:
                cli.single_call(f"hmy keys recover-bls-key {imported_bls_key_folder}/{k} "
                                f"--passphrase-file /tmp/bls_pass")
            except RuntimeError as e:
                print(f"{Typgpy.FAIL}Passphrase for {k} is not correct. Error: {e}{Typgpy.ENDC}")
                raise RuntimeError("Bad BLS import") from e
            shutil.copy(f"{imported_bls_key_folder}/{k}", AutoNode.bls_key_folder)
            shutil.copy(f"{imported_bls_key_folder}/{k}", "/root/bin")  # For CLI
            pass_file = f"{AutoNode.bls_key_folder}/{k.replace('.key', '.pass')}"
            with open(pass_file, 'w', encoding='utf8') as fw:
                fw.write(passphrase)
        return [k.replace('.key', '').replace('0x', '') for k in bls_keys]
    elif args.shard is not None:
        while True:
            key = json_load(cli.single_call("hmy keys generate-bls-key --passphrase-file /tmp/bls_pass"))
            public_bls_key = key['public-key']
            bls_file_path = key['encrypted-private-key-path']
            shard_id = json_load(cli.single_call(f"hmy --node={args.endpoint} utility "
                                                 f"shard-for-bls {public_bls_key}"))["shard-id"]
            if int(shard_id) != args.shard:
                os.remove(bls_file_path)
            else:
                args.bls_private_key = key['private-key']
                print(f"{Typgpy.OKGREEN}Generated BLS key for shard {shard_id}: "
                      f"{Typgpy.OKBLUE}{public_bls_key}{Typgpy.ENDC}")
                break
        shutil.copy(bls_file_path, AutoNode.bls_key_folder)
        shutil.copy(bls_file_path, imported_bls_key_folder)  # For recovery
        pass_file = f"{AutoNode.bls_key_folder}/{key['public-key'].replace('0x', '')}.pass"
        with open(pass_file, 'w', encoding='utf8') as fw:
            fw.write(passphrase)
        return [public_bls_key]
    else:
        key = json_load(cli.single_call("hmy keys generate-bls-key --passphrase-file /tmp/bls_pass"))
        public_bls_key = key['public-key']
        bls_file_path = key['encrypted-private-key-path']
        args.bls_private_key = key['private-key']
        shard_id = json_load(cli.single_call(f"hmy --node={args.endpoint} utility "
                                             f"shard-for-bls {public_bls_key}"))["shard-id"]
        print(f"{Typgpy.OKGREEN}Generated BLS key for shard {shard_id}: {Typgpy.OKBLUE}{public_bls_key}{Typgpy.ENDC}")
        shutil.copy(bls_file_path, AutoNode.bls_key_folder)
        shutil.copy(bls_file_path, imported_bls_key_folder)  # For recovery
        pass_file = f"{AutoNode.bls_key_folder}/{key['public-key'].replace('0x', '')}.pass"
        with open(pass_file, 'w', encoding='utf8') as fw:
            fw.write(passphrase)
        return [public_bls_key]


def import_node_info():
    print(f"{Typgpy.HEADER}Importing node info...{Typgpy.ENDC}")

    address = import_validator_address()
    wallet_passphrase = import_wallet_passphrase(address)
    bls_passphrase = import_bls_passphrase()
    public_bls_keys = import_bls(bls_passphrase)

    print("")
    # Save information for other scripts
    print("~" * 110)
    with open(os.path.abspath("/.val_address"),
              'w', encoding='utf8') as f:  # WARNING: assumption made of where to store address in other scripts.
        print(f"{Typgpy.OKGREEN}Validator address:{Typgpy.ENDC} {address}")
        f.write(address)
    with open(os.path.abspath("/.wallet_passphrase"),
              'w', encoding='utf8') as f:  # WARNING: assumption made of where to store address in other scripts.
        print(f"{Typgpy.OKGREEN}Validator wallet passphrase:{Typgpy.ENDC} {wallet_passphrase}")
        f.write(wallet_passphrase)
    with open(os.path.abspath("/.bls_keys"),
              'w', encoding='utf8') as f:  # WARNING: assumption made of where to store address in other scripts.
        print(f"{Typgpy.OKGREEN}BLS keys:{Typgpy.ENDC} {public_bls_keys}")
        f.write(str(public_bls_keys))
    with open(os.path.abspath("/.network"),
              'w', encoding='utf8') as f:  # WARNING: assumption made of where to store address in other scripts.
        print(f"{Typgpy.OKGREEN}Network:{Typgpy.ENDC} {args.network}")
        f.write(args.network)
    with open(os.path.abspath("/.beacon_endpoint"),
              'w', encoding='utf8') as f:  # WARNING: assumption made of where to store address in other scripts.
        print(f"{Typgpy.OKGREEN}Beacon chain endpoint:{Typgpy.ENDC} {args.endpoint}")
        f.write(args.endpoint)
    with open(os.path.abspath("/.duration"),
              'w', encoding='utf8') as f:  # WARNING: assumption made of where to store address in other scripts.
        print(f"{Typgpy.OKGREEN}Node duration:{Typgpy.ENDC} {args.duration}")
        f.write(str(args.duration))
    print("~" * 110)
    print("")
    return public_bls_keys


def setup_validator(val_info, bls_pub_keys):
    print(f"{Typgpy.OKBLUE}Create validator config\n{Typgpy.OKGREEN}{json.dumps(val_info, indent=4)}{Typgpy.ENDC}")

    # Check BLS key with validator if it exists
    all_val = json_load(cli.single_call(f"hmy --node={args.endpoint} blockchain validator all"))["result"]
    if val_info['validator-addr'] in all_val:
        if recover_interaction \
                or AutoNode.input_with_print("Add BLS key to existing validator? [Y]/n \n> ") in {'Y', 'y', 'yes', 'Yes'}:
            print(f"{Typgpy.HEADER}{Typgpy.BOLD}Editing validator...{Typgpy.ENDC}")
            AutoNode.add_bls_key_to_validator(val_info, bls_pub_keys, args.endpoint)
    elif val_info['validator-addr'] not in all_val:
        if recover_interaction \
                or AutoNode.input_with_print("Create validator? [Y]/n \n> ") in {'Y', 'y', 'yes', 'Yes'}:
            print(f"{Typgpy.HEADER}{Typgpy.BOLD}Creating new validator...{Typgpy.ENDC}")
            AutoNode.create_new_validator(val_info, bls_pub_keys, args.endpoint)


def check_and_activate(address, epos_status_msg):
    if "not eligible" in epos_status_msg or "not signing" in epos_status_msg:
        print(f"{Typgpy.FAIL}Node not active, reactivating...{Typgpy.ENDC}")
        cli.single_call(f"hmy staking edit-validator --validator-addr {address} "
                        f"--active true --node {args.endpoint} --passphrase-file /.wallet_passphrase ")


def can_check_blockchain(shard_endpoint):
    """
    Checks the node's blockchain against the given shard_endpoint.
    Returns True if success, False if unable to check.
    Raises a RuntimeError if blockchain does not match.
    """
    ref_block1 = AutoNode.get_block_by_number(1, shard_endpoint)
    if ref_block1:
        fb_ref_hash = ref_block1.get('hash', None)
    else:
        return False
    block1 = AutoNode.get_block_by_number(1, 'http://localhost:9500/')
    fb_hash = block1.get('hash', None) if block1 else None
    if args.auto_reset and fb_hash is not None and fb_ref_hash is not None and fb_hash != fb_ref_hash:
        raise RuntimeError(f"Blockchains don't match! "
                           f"Block 1 hash of chain: {fb_ref_hash} != Block 1 hash of node {fb_hash}")
    return True


def run_auto_node(bls_keys, shard_endpoint):
    """
    Assumption is that network is alive at this point.
    """
    global node_pid
    start_time = time.time()
    subprocess.call(["kill", "-2", f"{node_pid}"])
    subprocess.call(["killall", "harmony"])
    time.sleep(5)  # Sleep to ensure node is terminated b4 restart
    node_pid = AutoNode.start_node(AutoNode.bls_key_folder, args.network, clean=args.clean)
    setup_validator(validator_info, bls_keys)
    AutoNode.wait_for_node_response("http://localhost:9500/")
    while AutoNode.get_latest_header('http://localhost:9500/')['blockNumber'] == 0:
        pass
    curr_time = time.time()
    while curr_time - start_time < args.duration:
        AutoNode.assert_no_bad_blocks()
        if args.auto_reset:
            if not can_check_blockchain(shard_endpoint):
                time.sleep(8)
                continue
        all_val = json_load(cli.single_call(f"hmy --node={args.endpoint} blockchain validator all"))["result"]
        if validator_info["validator-addr"] in all_val:
            val_chain_info = AutoNode.get_validator_information(validator_info["validator-addr"], args.endpoint)
            print(f"{Typgpy.HEADER}EPOS status: {Typgpy.OKGREEN}{val_chain_info['epos-status']}{Typgpy.ENDC}")
            print(f"{Typgpy.HEADER}Current epoch performance: {Typgpy.OKGREEN}"
                  f"{json.dumps(val_chain_info['current-epoch-performance'], indent=4)}{Typgpy.ENDC}")
            if args.auto_active:
                check_and_activate(validator_info["validator-addr"], val_chain_info['epos-status'])
        else:
            print(f"{Typgpy.WARNING}{validator_info['validator-addr']} is not a validator, "
                  f"create validator with `./auto_node.sh create-validator`{Typgpy.ENDC}")
        print(f"{Typgpy.HEADER}This node's latest header at {datetime.datetime.utcnow()}: "
              f"{Typgpy.OKGREEN}{json.dumps(AutoNode.get_latest_headers('http://localhost:9500/'), indent=4)}"
              f"{Typgpy.ENDC}")
        time.sleep(8)
        curr_time = time.time()


def run_auto_node_with_restart(bls_keys, shard_endpoint):
    """
    Assumption is that network is alive at this point.
    """
    global recover_interaction
    while True:
        try:
            run_auto_node(bls_keys, shard_endpoint)
        except Exception as e:  # Catch all errors to not kill node.
            if isinstance(e, KeyboardInterrupt):
                print(f"{Typgpy.OKGREEN}Killing all harmony processes...{Typgpy.ENDC}")
                subprocess.call(["killall", "harmony"])
                exit()
            traceback.print_exc(file=sys.stdout)
            print(f"{Typgpy.FAIL}Auto node failed with error: {e}{Typgpy.ENDC}")
            with open(auto_node_errors, 'a') as f:
                f.write(f"{e}\n")
            print(f"{Typgpy.HEADER}Waiting for network liveliness before restarting...{Typgpy.ENDC}")
            AutoNode.wait_for_node_response(args.endpoint, verbose=False)
            AutoNode.wait_for_node_response(shard_endpoint, verbose=False)
            if args.network != "mainnet":
                args.clean = True
                recover_interaction = True
                print(f"{Typgpy.HEADER}Restarting auto_node with auto interaction & clean DB.{Typgpy.ENDC}")
            else:
                print(f"{Typgpy.HEADER}Restarting auto_node.{Typgpy.ENDC}")


if __name__ == "__main__":
    args = parse_args()
    try:
        bls_keys = import_node_info()
        AutoNode.wait_for_node_response(args.endpoint, verbose=True)
        shard = json_load(cli.single_call(f"hmy utility shard-for-bls {bls_keys[0].replace('0x', '')} "
                                          f"-n {args.endpoint}"))['shard-id']
        shard_endpoint = AutoNode.get_sharding_structure(args.endpoint)[shard]["http"]
        if args.auto_reset:
            run_auto_node_with_restart(bls_keys, shard_endpoint)
        else:
            run_auto_node(bls_keys, shard_endpoint)
    except Exception as e:
        traceback.print_exc(file=sys.stdout)
        print(f"{Typgpy.FAIL}Auto node failed with error: {e}{Typgpy.ENDC}")
        with open(auto_node_errors, 'a') as f:
            f.write(f"{e}\n")
        print(f"Docker image still running; `auto_node.sh` commands will still work.")
        subprocess.call(['tail', '-f', '/dev/null'], env=AutoNode.env, timeout=None)
