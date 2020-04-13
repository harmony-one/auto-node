#!/usr/bin/env python3
import argparse
import shutil
import datetime
import random
import getpass
import traceback
from argparse import RawTextHelpFormatter

from utils import *

with open("./node/validator_config.json") as f:  # WARNING: assumption of copied file on docker run.
    validator_info = json.load(f)
imported_bls_key_folder = "/root/harmony_bls_keys"  # WARNING: assumption made on auto_node.sh
bls_key_folder = "/root/node/bls_keys"
auto_node_errors = "/root/node/auto_node_errors.log"
with open(auto_node_errors, 'a') as f:
    f.write("== AutoNode Run Errors ==\n")
shutil.rmtree(bls_key_folder, ignore_errors=True)
os.makedirs(bls_key_folder, exist_ok=True)

node_pid = -1


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
    parser.add_argument("--auto-interaction", action="store_true",
                        help="Say yes to all interaction (except wallet pw).")
    parser.add_argument("--clean", action="store_true", help="Clean shared node directory before starting node.")
    parser.add_argument("--wallet-passphrase", action="store_true",
                        help="Toggle specifying a passphrase interactively for the wallet.\n  "
                             "If not toggled, default CLI passphrase will be used.", )
    parser.add_argument("--wallet-passphrase-string", help="Specify passphrase string for validator's wallet.\n  "
                                                           "The passphrase may be exposed on the host machine.\n  ",
                        type=str, default=None)
    parser.add_argument("--bls-passphrase", action="store_true",
                        help="Toggle specifying a passphrase interactively for the BLS key.\n  "
                             "If not toggled, default CLI passphrase will be used.", )
    parser.add_argument("--bls-passphrase-string", help="Specify passphrase string for validator's BLS key.\n  "
                                                        "The passphrase may be exposed on the host machine.\n  ",
                        type=str, default=None)
    parser.add_argument("--shard", default=None,
                        help="Specify shard of generated bls key.\n  "
                             "Only used if no BLS keys are not provided.", type=int)
    parser.add_argument("--network", help="Network to connect to (staking, partner, stress).\n  "
                                          "Default: 'staking'.", type=str, default='staking')
    parser.add_argument("--duration", type=int, help="Duration of how long the node is to run in seconds.\n  "
                                                     "Default is forever.", default=float('inf'))
    parser.add_argument("--beacon-endpoint", dest="endpoint", type=str, default=default_endpoint,
                        help=f"Beacon chain (shard 0) endpoint for staking transactions.\n  "
                             f"Default is {default_endpoint}")
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
    if args.bls_passphrase:
        return getpass.getpass(f"Enter passphrase for all given BLS keys\n> ")
    elif args.bls_passphrase_string:
        return args.bls_passphrase_string
    else:
        return default_cli_passphrase


def import_wallet_passphrase():
    if args.wallet_passphrase:
        return getpass.getpass(f"Enter wallet passphrase for {validator_info['validator-addr']}\n> ")
    elif args.wallet_passphrase_string:
        return args.wallet_passphrase_string
    else:
        return default_cli_passphrase


def import_bls(passphrase):
    with open("/tmp/bls_pass", 'w') as fw:
        fw.write(passphrase)
    imported_keys = [k for k in os.listdir(imported_bls_key_folder) if k.endswith(".key")]
    if len(imported_keys) > 0:
        if args.shard is not None:
            print(f"{Typgpy.FAIL}[!] Shard option ignored since BLS keys provided in `./harmony_bls_keys`{Typgpy.ENDC}")
        keys_list = []
        for k in imported_keys:
            try:
                key = json_load(cli.single_call(f"hmy keys recover-bls-key {imported_bls_key_folder}/{k} "
                                                f"--passphrase-file /tmp/bls_pass"))
                keys_list.append(key)
                shutil.copy(f"{imported_bls_key_folder}/{k}", bls_key_folder)
                shutil.copy(f"{imported_bls_key_folder}/{k}", "./bin")  # For CLI
                with open(f"{bls_key_folder}/{key['public-key'].replace('0x', '')}.pass", 'w') as fw:
                    fw.write(passphrase)
            except (RuntimeError, json.JSONDecodeError, shutil.ExecError) as e:
                print(f"{Typgpy.FAIL}Failed to load BLS key {k}, error: {e}{Typgpy.ENDC}")
        if len(keys_list) == 0:
            print(f"{Typgpy.FAIL}Could not import any BLS key, exiting...{Typgpy.ENDC}")
            exit(-1)
        return [k['public-key'] for k in keys_list]
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
        shutil.copy(bls_file_path, bls_key_folder)
        shutil.copy(bls_file_path, "./bin")  # For CLI
        with open(f"{bls_key_folder}/{key['public-key'].replace('0x', '')}.pass", 'w') as fw:
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
        shutil.copy(bls_file_path, bls_key_folder)
        shutil.copy(bls_file_path, "./bin")  # For CLI
        with open(f"{bls_key_folder}/{key['public-key'].replace('0x', '')}.pass", 'w') as fw:
            fw.write(passphrase)
        return [public_bls_key]


def import_node_info():
    print(f"{Typgpy.HEADER}Importing node info...{Typgpy.ENDC}")

    address = import_validator_address()
    wallet_passphrase = import_wallet_passphrase()
    bls_passphrase = import_bls_passphrase()
    public_bls_keys = import_bls(bls_passphrase)

    print("")
    # Save information for other scripts
    print("~" * 110)
    with open(os.path.abspath("/.val_address"),
              'w') as f:  # WARNING: assumption made of where to store address in other scripts.
        print(f"{Typgpy.OKGREEN}Validator address:{Typgpy.ENDC} {address}")
        f.write(address)
    with open(os.path.abspath("/.wallet_passphrase"),
              'w') as f:  # WARNING: assumption made of where to store address in other scripts.
        print(f"{Typgpy.OKGREEN}Validator wallet passphrase:{Typgpy.ENDC} {wallet_passphrase}")
        f.write(wallet_passphrase)
    with open(os.path.abspath("/.bls_keys"),
              'w') as f:  # WARNING: assumption made of where to store address in other scripts.
        print(f"{Typgpy.OKGREEN}BLS keys:{Typgpy.ENDC} {public_bls_keys}")
        f.write(str(public_bls_keys))
    with open(os.path.abspath("/.bls_passphrase"),
              'w') as f:  # WARNING: assumption made of where to store address in other scripts.
        print(f"{Typgpy.OKGREEN}BLS passphrase (for all keys):{Typgpy.ENDC} {bls_passphrase}")
        f.write(wallet_passphrase)
    with open(os.path.abspath("/.network"),
              'w') as f:  # WARNING: assumption made of where to store address in other scripts.
        print(f"{Typgpy.OKGREEN}Network:{Typgpy.ENDC} {args.network}")
        f.write(args.network)
    with open(os.path.abspath("/.beacon_endpoint"),
              'w') as f:  # WARNING: assumption made of where to store address in other scripts.
        print(f"{Typgpy.OKGREEN}Beacon chain endpoint:{Typgpy.ENDC} {args.endpoint}")
        f.write(args.endpoint)
    with open(os.path.abspath("/.duration"),
              'w') as f:  # WARNING: assumption made of where to store address in other scripts.
        print(f"{Typgpy.OKGREEN}Node duration:{Typgpy.ENDC} {args.duration}")
        f.write(str(args.duration))
    print("~" * 110)
    print("")
    print(f"{Typgpy.HEADER}[!] Copied BLS key file to shared node directory "
          f"with the given passphrase (or default CLI passphrase if none){Typgpy.ENDC}")
    return public_bls_keys


def setup_validator(val_info, bls_pub_keys):
    print(f"{Typgpy.OKBLUE}Create validator config\n{Typgpy.OKGREEN}{json.dumps(val_info, indent=4)}{Typgpy.ENDC}")
    with open("/.bls_passphrase", 'r') as fr:
        bls_passphrase = fr.read()

    # Check BLS key with validator if it exists
    all_val = json_load(cli.single_call(f"hmy --node={args.endpoint} blockchain validator all"))["result"]
    if val_info['validator-addr'] in all_val:
        if args.auto_interaction \
                or input_with_print("Add BLS key to existing validator? [Y]/n \n> ") in {'Y', 'y', 'yes', 'Yes'}:
            print(f"{Typgpy.HEADER}{Typgpy.BOLD}Editing validator...{Typgpy.ENDC}")
            add_bls_key_to_validator(val_info, bls_pub_keys, bls_passphrase, args.endpoint)
    elif val_info['validator-addr'] not in all_val:
        if args.auto_interaction \
                or input_with_print("Create validator? [Y]/n \n> ") in {'Y', 'y', 'yes', 'Yes'}:
            print(f"{Typgpy.HEADER}{Typgpy.BOLD}Creating new validator...{Typgpy.ENDC}")
            create_new_validator(val_info, bls_pub_keys, bls_passphrase, args.endpoint)


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
    ref_block1 = get_block_by_number(1, shard_endpoint)
    if ref_block1:
        fb_ref_hash = ref_block1.get('hash', None)
    else:
        return False
    block1 = get_block_by_number(1, 'http://localhost:9500/')
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
    node_pid = start_node(bls_key_folder, args.network, clean=args.clean)
    setup_validator(validator_info, bls_keys)
    wait_for_node_response("http://localhost:9500/")
    while get_latest_header('http://localhost:9500/')['blockNumber'] == 0:
        pass
    curr_time = time.time()
    while curr_time - start_time < args.duration:
        if args.auto_reset:
            if not can_check_blockchain(shard_endpoint):
                time.sleep(8)
                continue
        all_val = json_load(cli.single_call(f"hmy --node={args.endpoint} blockchain validator all"))["result"]
        if validator_info["validator-addr"] in all_val:
            val_chain_info = get_validator_information(validator_info["validator-addr"], args.endpoint)
            print(f"{Typgpy.HEADER}EPOS status: {Typgpy.OKGREEN}{val_chain_info['epos-status']}{Typgpy.ENDC}")
            print(f"{Typgpy.HEADER}Current epoch performance: {Typgpy.OKGREEN}"
                  f"{json.dumps(val_chain_info['current-epoch-performance'], indent=4)}{Typgpy.ENDC}")
            if args.auto_active:
                check_and_activate(validator_info["validator-addr"], val_chain_info['epos-status'])
        print(f"{Typgpy.HEADER}This node's latest header at {datetime.datetime.utcnow()}: "
              f"{Typgpy.OKGREEN}{json.dumps(get_latest_headers('http://localhost:9500/'), indent=4)}"
              f"{Typgpy.ENDC}")
        time.sleep(8)
        assert_no_bad_blocks()
        curr_time = time.time()


def run_auto_node_with_restart(bls_keys, shard_endpoint):
    """
    Assumption is that network is alive at this point.
    """
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
            wait_for_node_response(args.endpoint, verbose=False)
            wait_for_node_response(shard_endpoint, verbose=False)
            if args.network != "mainnet":
                args.clean = True
                args.auto_interaction = True
                print(f"{Typgpy.HEADER}Restarting auto_node with auto interaction & clean DB.{Typgpy.ENDC}")
            else:
                print(f"{Typgpy.HEADER}Restarting auto_node.{Typgpy.ENDC}")


if __name__ == "__main__":
    args = parse_args()
    setup()
    try:
        bls_keys = import_node_info()
        wait_for_node_response(args.endpoint, verbose=True)
        shard = json_load(cli.single_call(f"hmy utility shard-for-bls {bls_keys[0].replace('0x', '')} "
                                          f"-n {args.endpoint}"))['shard-id']
        shard_endpoint = get_sharding_structure(args.endpoint)[shard]["http"]
        if args.auto_reset:
            run_auto_node_with_restart(bls_keys, shard_endpoint)
        else:
            run_auto_node(bls_keys, shard_endpoint)
    except Exception as e:
        if isinstance(e, KeyboardInterrupt):
            print(f"{Typgpy.OKGREEN}Killing all harmony processes...{Typgpy.ENDC}")
            subprocess.call(["killall", "harmony"])
            exit()
        traceback.print_exc(file=sys.stdout)
        print(f"{Typgpy.FAIL}Auto node failed with error: {e}{Typgpy.ENDC}")
        with open(auto_node_errors, 'a') as f:
            f.write(f"{e}\n")
        print(f"Docker image still running; `auto_node.sh` commands will still work.")
        subprocess.call(['tail', '-f', '/dev/null'], env=env, timeout=None)
