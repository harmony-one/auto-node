import sys
import time
import json
import datetime
import traceback
import subprocess
import os
import logging

from pyhmy import (
    blockchain,
    cli,
    json_load,
    staking,
    Typgpy,
)

from .common import (
    log,
    harmony_dir,
    validator_config,
    node_config,
    save_node_config,
    check_interval,
    user
)
from .validator import (
    check_and_activate
)
from .node import (
    wait_for_node_response,
    assert_no_bad_blocks,
)
from .util import (
    get_simple_rotating_log_handler
)

log_path = f"{harmony_dir}/autonode_monitor.log"
progress_check_interval = 300  # Must account for view-change
node_epoch_slack = 500  # Account for recovery time


# TODO: move this to an exceptions library
class ResetNode(Exception):
    """The only exception that triggers a hard reset."""

    def __init__(self, *args, clean=False):
        node_config['clean'] = clean
        save_node_config()
        super(ResetNode, self).__init__(*args)


def _check_for_hard_reset(shard_endpoint, error_ok=False):
    """
    Raises a ResetNodeError (with clean enabled) if blockchain does not match.
    """
    network_epoch = blockchain.get_current_epoch(endpoint=shard_endpoint)
    node_epoch = blockchain.get_current_epoch() - node_epoch_slack
    if node_epoch > network_epoch:
        log(f"{Typgpy.WARNING}Epoch of node higher than endpoint epoch, sleeping {progress_check_interval} seconds "
            f"before checking endpoint progress for hard-reset trigger.{Typgpy.ENDC}")
        time.sleep(progress_check_interval)  # check that network is not making progress
        new_network_epoch = blockchain.get_latest_header(endpoint=shard_endpoint)['epoch']
        if network_epoch < new_network_epoch < node_epoch:  # made progress so reset
            raise ResetNode(f"Blockchains don't match! Network "
                            f"epoch {new_network_epoch} < Node epoch {node_epoch + node_epoch_slack}", clean=True)
        else:
            log(f"{Typgpy.WARNING} Shard endpoint ({shard_endpoint}) is not making progress, "
                f"possible endpoint issue, or hard-reset.{Typgpy.ENDC}")
    try:
        assert_no_bad_blocks()
    except AssertionError as e:
        raise ResetNode("BAD BLOCK", clean=True) from e
    fb_ref_hash = blockchain.get_block_by_number(1, endpoint=shard_endpoint)['hash']
    fb_hash = blockchain.get_block_by_number(1)['hash']
    if not error_ok and fb_hash is not None and fb_ref_hash is not None and fb_hash != fb_ref_hash:
        raise ResetNode(f"Blockchains don't match! "
                        f"Block 1 hash of chain: {fb_ref_hash} != Block 1 hash of node {fb_hash}", clean=True)
    return True


def _wait_for_node_block_two():
    """
    Triggers a clean node restart if node is not able to boot 5 mins after rclone.
    """
    time.sleep(check_interval * 2)  # Wait 2 intervals for node process to start.
    informed_rclone = False
    while subprocess.call("pgrep rclone", shell=True, env=os.environ) == 0:
        if not informed_rclone:
            informed_rclone = True
            log(f"{Typgpy.HEADER}Waiting for rclone to finish...{Typgpy.ENDC}")
        time.sleep(check_interval)
    try:
        wait_for_node_response("http://localhost:9500/", verbose=True, sleep=1, tries=300)  # Try for 5 min
        log(f"{Typgpy.HEADER}Waiting for block 2 on node...{Typgpy.ENDC}")
    except (ConnectionError, TimeoutError) as e:
        log(f"{Typgpy.FAIL}Could not connect to node after 5 min...{Typgpy.ENDC}")
        raise ResetNode(clean=True) from e
    count = 0
    try:
        while blockchain.get_latest_header()['blockNumber'] < 2:
            assert_no_bad_blocks()
            count += 1
            sys.stdout.write(f"\rWaiting for node (http://localhost:9500/) to get past block 1, "
                             f"checked {count} times")
            sys.stdout.flush()
            time.sleep(check_interval)
    except AssertionError as e:
        raise ResetNode("BAD BLOCK", clean=True) from e
    node_config['clean'] = False  # Once node got past block 1, don't clean until absolutely needed.
    save_node_config()


def _run_monitor(shard_endpoint):
    """
    Hard reset (clean node.sh reset) triggers:
    1) See bad blocks in logs
    2) Node's epoch is greater than network's epoch
    3) Block 1 hashes dont match (on shard)
    4) Node unable to boot 5 mins after rclone (last resort clean)
    """
    start_time = time.time()
    _wait_for_node_block_two()
    curr_time = time.time()
    duration = node_config['duration'] if node_config['duration'] else float("inf")
    count = 0
    while curr_time - start_time < duration:
        if node_config["auto-reset"]:
            if subprocess.call("sudo -n true", shell=True, env=os.environ) != 0:
                log(f"{Typgpy.WARNING}User {user} does not have sudo access without passphrase. "
                    f"Cannot trigger auto-reset if there is a hard reset (on testnet).{Typgpy.ENDC}")
            _check_for_hard_reset(shard_endpoint)
        log(f"{Typgpy.HEADER}Validator address: {Typgpy.OKGREEN}{validator_config['validator-addr']}{Typgpy.ENDC}")
        meta_data = blockchain.get_node_metadata()
        log(f"{Typgpy.HEADER}Node BLS keys: {Typgpy.OKGREEN}{meta_data['blskey']}{Typgpy.ENDC}")
        log(f"{Typgpy.HEADER}Node version: {Typgpy.OKGREEN}{meta_data['version']}{Typgpy.ENDC}")
        log(f"{Typgpy.HEADER}Node network: {Typgpy.OKGREEN}{meta_data['network']}{Typgpy.ENDC}")
        log(f"{Typgpy.HEADER}Node is leader: {Typgpy.OKGREEN}{meta_data['is-leader']}{Typgpy.ENDC}")
        log(f"{Typgpy.HEADER}Node is archival: {Typgpy.OKGREEN}{meta_data['is-archival']}{Typgpy.ENDC}")
        log(f"{Typgpy.HEADER}Node shard: {Typgpy.OKGREEN}{meta_data['shard-id']}{Typgpy.ENDC}")
        log(f"{Typgpy.HEADER}Node role: {Typgpy.OKGREEN}{meta_data['role']}{Typgpy.ENDC}")
        all_val = staking.get_all_validator_addresses(endpoint=node_config['endpoint'])
        if validator_config["validator-addr"] in all_val:
            val_chain_info = staking.get_validator_information(validator_config["validator-addr"], endpoint=node_config['endpoint'])
            log(f"{Typgpy.HEADER}EPOS status: {Typgpy.OKGREEN}{val_chain_info['epos-status']}{Typgpy.ENDC}")
            log(f"{Typgpy.HEADER}Booted status: {Typgpy.OKGREEN}{val_chain_info['booted-status']}{Typgpy.ENDC}")
            log(f"{Typgpy.HEADER}Current epoch performance: {Typgpy.OKGREEN}"
                f"{json.dumps(val_chain_info['current-epoch-performance'], indent=4)}{Typgpy.ENDC}")
            if node_config["auto-active"]:
                if check_and_activate():
                    count += 1
                log(f"{Typgpy.HEADER}Auto activation count: {Typgpy.OKGREEN}{count}{Typgpy.ENDC}")
        elif not node_config["no-validator"]:
            log(f"{Typgpy.WARNING}{validator_config['validator-addr']} is not a validator.{Typgpy.ENDC}")
        log(f"{Typgpy.HEADER}This node's latest header at {datetime.datetime.utcnow()}: "
            f"{Typgpy.OKGREEN}{json.dumps(blockchain.get_latest_headers(), indent=4)}"
            f"{Typgpy.ENDC}")
        time.sleep(check_interval)
        curr_time = time.time()


def _init():
    wait_for_node_response(node_config['endpoint'], sleep=1)
    bls_keys = node_config['public-bls-keys']
    shard = json_load(cli.single_call(f"hmy utility shard-for-bls {bls_keys[0].replace('0x', '')} "
                                      f"-n {node_config['endpoint']}"))['shard-id']
    shard_endpoint = blockchain.get_sharding_structure(endpoint=node_config['endpoint'])[shard]["http"]
    wait_for_node_response(shard_endpoint, sleep=1)
    return shard_endpoint


def start():
    """
    Will throw a RestartNode exception to signal a need to restart the node.
    """
    old_logging_handlers = logging.getLogger('AutoNode').handlers.copy()
    logging.getLogger('AutoNode').addHandler(get_simple_rotating_log_handler(log_path))
    log(f"{Typgpy.HEADER}Starting monitor...{Typgpy.ENDC}")
    if node_config['auto-reset'] and subprocess.call("sudo -n true", shell=True, env=os.environ) != 0:
        log(f"{Typgpy.WARNING}User {user} does not have sudo privileges without password.\n "
            f"For auto-reset option, user must have said privilege. Continuing...{Typgpy.ENDC}")
        time.sleep(2)  # So user can read message...
    try:
        shard_endpoint = _init()
        _run_monitor(shard_endpoint)
    except Exception as err:  # Catch all to handle recover options
        log(traceback.format_exc())
        log(f"{Typgpy.FAIL}Node failed with error: {err}{Typgpy.ENDC}")
        if not node_config['auto-reset']:  # Exit early since no need for restart
            logging.getLogger('AutoNode').handlers = old_logging_handlers
            return
        if isinstance(err, ResetNode):
            log(f"{Typgpy.WARNING}Monitor is waiting for endpoint {node_config['endpoint']} to "
                f"respond before triggering node reset.{Typgpy.ENDC}")
            wait_for_node_response(node_config['endpoint'], verbose=False, sleep=2)
            log(f"{Typgpy.WARNING}Monitor is triggering reset with clean: {node_config['clean']}{Typgpy.ENDC}")
            raise err
    logging.getLogger('AutoNode').handlers = old_logging_handlers
