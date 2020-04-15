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



def run_auto_node(bls_keys, shard_endpoint):
    """
    Assumption is that network is alive at this point.
    """
    global node_pid
    start_time = time.time()
    subprocess.call(["kill", "-2", f"{node_pid}"])
    subprocess.call(["killall", "harmony"])
    time.sleep(5)  # Sleep to ensure node is terminated b4 restart
    node_pid = AutoNode.start_node(AutoNode.bls_key_dir, args.network, clean=args.clean)
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
            # TODO: remeber to delete logs after a restart because this will cause errors.


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
