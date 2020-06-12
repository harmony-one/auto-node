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
    exceptions
)

from .common import (
    log,
    harmony_dir,
    validator_config,
    node_config,
    check_interval,
    user
)
from .validator import (
    check_and_activate,
    get_validator_information
)
from .node import (
    wait_for_node_response,
    assert_no_bad_blocks,
)
from .util import (
    get_simple_rotating_log_handler
)
from .exceptions import (
    ResetNode
)

log_path = f"{harmony_dir}/autonode_monitor.log"
progress_check_interval = 300  # Must account for view-change
node_epoch_slack = 100  # Account for recovery time


def _check_for_hard_reset(shard_endpoint, error_ok=False):
    """
    Raises a ResetNodeError if blockchain does not match.

    Only used on testnets.
    """
    if node_config['network'] == "mainnet":
        return
    network_epoch = blockchain.get_current_epoch(endpoint=shard_endpoint)
    node_epoch = blockchain.get_current_epoch(endpoint='http://localhost:9500')
    if network_epoch == 0 or node_epoch == 0:
        return  # Don't hard reset on epoch 0, network could still be initing & resetting many times.
    else:
        node_epoch -= node_epoch_slack  # Slack to account for ops related hiccups on testnets.
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


def _run_monitor(shard_endpoint, duration=50):
    """
    Internal function that monitors the node for `duration` seconds.

    Hard reset (clean node.sh reset) triggers:
    1) See bad blocks in logs
    2) Node's epoch is greater than network's epoch
    3) Block 1 hashes dont match (on shard)
    4) Node unable to boot 5 mins after rclone (last resort clean)
    """
    activate_count, start_time = 0, time.time()
    while time.time() - start_time < duration:
        try:
            if node_config["auto-reset"]:
                if subprocess.call("sudo -n true", shell=True, env=os.environ) != 0:
                    log(f"{Typgpy.WARNING}User {user} does not have sudo access without passphrase. "
                        f"Cannot trigger auto-reset if there is a hard reset (on testnet).{Typgpy.ENDC}")
                _check_for_hard_reset(shard_endpoint)
            log(f"{Typgpy.HEADER}Validator address: {Typgpy.OKGREEN}{validator_config['validator-addr']}{Typgpy.ENDC}")
            meta_data = blockchain.get_node_metadata('http://localhost:9500/')
            log(f"{Typgpy.HEADER}Node BLS keys: {Typgpy.OKGREEN}{meta_data['blskey']}{Typgpy.ENDC}")
            log(f"{Typgpy.HEADER}Node version: {Typgpy.OKGREEN}{meta_data['version']}{Typgpy.ENDC}")
            log(f"{Typgpy.HEADER}Node network: {Typgpy.OKGREEN}{meta_data['network']}{Typgpy.ENDC}")
            log(f"{Typgpy.HEADER}Node is leader: {Typgpy.OKGREEN}{meta_data['is-leader']}{Typgpy.ENDC}")
            log(f"{Typgpy.HEADER}Node is archival: {Typgpy.OKGREEN}{meta_data['is-archival']}{Typgpy.ENDC}")
            log(f"{Typgpy.HEADER}Node shard: {Typgpy.OKGREEN}{meta_data['shard-id']}{Typgpy.ENDC}")
            log(f"{Typgpy.HEADER}Node role: {Typgpy.OKGREEN}{meta_data['role']}{Typgpy.ENDC}")
            all_val = staking.get_all_validator_addresses(endpoint=node_config['endpoint'])
            if validator_config["validator-addr"] in all_val:
                val_chain_info = get_validator_information()
                log(f"{Typgpy.HEADER}EPOS status: {Typgpy.OKGREEN}{val_chain_info['epos-status']}{Typgpy.ENDC}")
                log(f"{Typgpy.HEADER}Booted status: {Typgpy.OKGREEN}{val_chain_info['booted-status']}{Typgpy.ENDC}")
                log(f"{Typgpy.HEADER}Current epoch performance: {Typgpy.OKGREEN}"
                    f"{json.dumps(val_chain_info['current-epoch-performance'], indent=4)}{Typgpy.ENDC}")
                if node_config["auto-active"]:
                    if check_and_activate():
                        activate_count += 1
                    log(f"{Typgpy.HEADER}Auto activation count: {Typgpy.OKGREEN}{activate_count}{Typgpy.ENDC}")
            elif not node_config["no-validator"]:
                log(f"{Typgpy.WARNING}{validator_config['validator-addr']} is not a validator.{Typgpy.ENDC}")
            log(f"{Typgpy.HEADER}This node's latest header at {datetime.datetime.utcnow()}: "
                f"{Typgpy.OKGREEN}{json.dumps(blockchain.get_latest_headers(), indent=4)}"
                f"{Typgpy.ENDC}")
        except (exceptions.RPCError, exceptions.RequestsError, exceptions.RequestsTimeoutError) as e:
            log(f"{Typgpy.WARNING}RPC exception {e}{Typgpy.ENDC}")
            log(f"{Typgpy.WARNING}Continuing...{Typgpy.ENDC}")
        finally:
            time.sleep(check_interval)


def start(duration=float('inf')):
    """
    Start a monitor for duration seconds.

    Will throw a RestartNode exception to signal a need to restart the node.
    """
    old_logging_handlers = logging.getLogger('AutoNode').handlers.copy()
    logging.getLogger('AutoNode').addHandler(get_simple_rotating_log_handler(log_path))
    try:
        bls_keys = node_config['public-bls-keys']
        shard = json_load(cli.single_call(['hmy', 'utility', 'shard-for-bls', bls_keys[0],
                                           '--node', f'{node_config["endpoint"]}']))['shard-id']
        shard_endpoint = blockchain.get_sharding_structure(endpoint=node_config['endpoint'])[shard]['http']
        _run_monitor(shard_endpoint, duration=duration)
    except Exception as err:  # Catch all to handle recover options
        log(traceback.format_exc())
        log(f"{Typgpy.FAIL}Monitor failed with error: {err}{Typgpy.ENDC}")
        if node_config['auto-reset'] and isinstance(err, ResetNode):  # Execute Auto-Reset
            log(f"{Typgpy.WARNING}Monitor is waiting for endpoint {node_config['endpoint']} to "
                f"respond before triggering node reset.{Typgpy.ENDC}")
            wait_for_node_response(node_config['endpoint'], verbose=False, sleep=2)
            log(f"{Typgpy.WARNING}Monitor is triggering reset with clean: {node_config['clean']}{Typgpy.ENDC}")
            logging.getLogger('AutoNode').handlers = old_logging_handlers
            raise err
    logging.getLogger('AutoNode').handlers = old_logging_handlers
