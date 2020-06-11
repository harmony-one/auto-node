#!/usr/bin/env python3
import argparse
import time
import json
from argparse import RawTextHelpFormatter

from pyhmy import (
    blockchain,
    cli,
    json_load,
    staking,
    Typgpy
)
from AutoNode import (
    common,
    util,
    node
)

validator_addr = common.validator_config['validator-addr']
endpoint = common.node_config['endpoint']
bls_keys = common.node_config['public-bls-keys']
removed_keys = []


def parse_args():
    parser = argparse.ArgumentParser(description="Cleanse BLS keys associated with this node's validator",
                                     usage="auto_node.sh cleanse-bls [OPTIONS]",
                                     formatter_class=RawTextHelpFormatter, add_help=False)
    parser.add_argument('-h', '--help', action='help', default=argparse.SUPPRESS,
                        help='Show this help message and exit')
    parser.add_argument("--hard", action="store_true",
                        help="Remove ALL BLS keys that are not this node's BLS key")
    parser.add_argument("--keep-shard", action="store_true",
                        help="Remove ALL BLS keys that are not this node's SHARD")
    parser.add_argument("--yes", action="store_true",
                        help="Answer yes to all interaction")
    return parser.parse_args()


def hard_cleanse():
    """ Only keep BLS keys for current running node.
    """
    # WARNING: Assumption that chain BLS keys are not 0x strings
    keys_on_chain = staking.get_validator_information(validator_addr, endpoint=endpoint)['validator']['bls-public-keys']
    for key in keys_on_chain:
        if key not in bls_keys:
            common.log(f"{Typgpy.WARNING}Removing {key}, key not in node's list of BLS keys: {bls_keys}{Typgpy.ENDC}")
            response = cli.single_call(['hmy', '--node', endpoint, 'staking', 'edit-validator',
                                        '--validator-addr', validator_addr,
                                        '--remove-bls-key', key, '--passphrase-file', common.saved_wallet_pass_path])
            common.log(f"{Typgpy.OKGREEN}Edit-validator transaction response: {response}{Typgpy.ENDC}")
            removed_keys.append(key)


def shard_cleanse():
    """ Only keep BLS keys on same shard as current running node.
    """
    # WARNING: Assumption that chain BLS keys are not 0x strings
    keys_on_chain = staking.get_validator_information(validator_addr, endpoint=endpoint)['validator']['bls-public-keys']
    shard = json_load(cli.single_call(['hmy', 'utility', 'shard-for-bls', list(bls_keys)[0],
                                       '--node', endpoint]))['shard-id']
    for key in keys_on_chain:
        key_shard = json_load(cli.single_call(['hmy', 'utility', 'shard-for-bls', key,
                                               '--node', endpoint]))['shard-id']
        if key_shard != shard and key not in bls_keys:
            common.log(
                f"{Typgpy.WARNING}Removing {key}, key for shard {key_shard}, node for shard {shard}{Typgpy.ENDC}")
            response = cli.single_call(['hmy', '--node', endpoint, 'staking', 'edit-validator',
                                        '--validator-addr', validator_addr,
                                        '--remove-bls-key', key, '--passphrase-file', common.saved_wallet_pass_path])
            common.log(f"{Typgpy.OKGREEN}Edit-validator transaction response: {response}{Typgpy.ENDC}")
            removed_keys.append(key)


def reward_cleanse():
    """ Only keep BLS keys that have earned something in the current epoch
    """
    # WARNING: Assumption that chain BLS keys are not 0x strings
    val_metrics = staking.get_validator_information(validator_addr, endpoint=endpoint)['metrics']
    if val_metrics is None:
        common.log(f"{Typgpy.WARNING}Can not get current BLS key performance, "
                   f"validator ({validator_addr}) is not elected.{Typgpy.ENDC}")
        if args.yes or util.input_with_print(f"Wait for election? [Y]/n\n> ").lower() in {'y', 'yes'}:
            while val_metrics is None:
                time.sleep(8)
                val_metrics = staking.get_validator_information(validator_addr, endpoint=endpoint)['metrics']
        else:
            exit()
    block_per_epoch = blockchain.get_node_metadata(endpoint=endpoint)['blocks-per-epoch']
    # WARNING: Assumption that epochs are greater than 6 blocks
    while 0 <= blockchain.get_latest_header()['blockNumber'] % block_per_epoch <= 5:
        pass
    bls_metrics = staking.get_validator_information(validator_addr, endpoint=endpoint)['metrics']['by-bls-key']
    common.log(f"{Typgpy.OKBLUE}BLS key metrics: {Typgpy.OKGREEN}{json.dumps(bls_metrics, indent=2)}{Typgpy.ENDC}")
    keys_on_chain = staking.get_validator_information(validator_addr, endpoint=endpoint)['validator']['bls-public-keys']
    for metric in bls_metrics:
        if metric['earned-reward'] == 0:
            key = metric['key']['bls-public-key']
            if key not in bls_keys and key in keys_on_chain:
                common.log(f"{Typgpy.WARNING}Removing {key}, key earned 0 rewards.{Typgpy.ENDC}")
                response = cli.single_call(['hmy', '--node', endpoint, 'staking', 'edit-validator',
                                            '--validator-addr', validator_addr,
                                            '--remove-bls-key', key, '--passphrase-file', common.saved_wallet_pass_path])
                common.log(f"{Typgpy.OKGREEN}Edit-validator transaction response: {response}{Typgpy.ENDC}")
                removed_keys.append(key)


if __name__ == "__main__":
    args = parse_args()
    all_val = json_load(cli.single_call(['hmy', 'blockchain', 'validator', 'all', '--node', endpoint]))['result']
    old_logging_handlers = common.logging.getLogger('AutoNode').handlers.copy()
    common.logging.getLogger('AutoNode').addHandler(util.get_simple_rotating_log_handler(node.log_path))
    if validator_addr not in all_val:
        common.log(f"{Typgpy.FAIL}{validator_addr} is not a validator on {endpoint}.{Typgpy.ENDC}")
        exit(-1)
    keys_on_chain = staking.get_validator_information(validator_addr, endpoint=endpoint)['validator']['bls-public-keys']
    common.log(f"{Typgpy.OKBLUE}Keys on validator {validator_addr} (before cleanse): {Typgpy.OKGREEN}{keys_on_chain}{Typgpy.ENDC}")
    if args.hard:
        hard_cleanse()
    elif args.keep_shard:
        shard_cleanse()
    else:
        reward_cleanse()
    keys_on_chain = staking.get_validator_information(validator_addr, endpoint=endpoint)['validator']['bls-public-keys']
    common.log(f"{Typgpy.OKBLUE}Cleansed following BLS keys: {Typgpy.OKGREEN}{removed_keys}{Typgpy.ENDC}")
    common.log(f"{Typgpy.OKBLUE}Keys on validator {validator_addr} (after cleanse): {Typgpy.OKGREEN}{keys_on_chain}{Typgpy.ENDC}")
