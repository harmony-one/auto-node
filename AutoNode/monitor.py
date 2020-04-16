import sys
import time
import json
import datetime
import traceback

from pyhmy import (
    cli,
    json_load,
    Typgpy
)

from .common import (
    harmony_dir,
    validator_config,
    node_config,
    save_node_config
)
from .node import (
    wait_for_node_response,
    assert_no_bad_blocks,
    check_and_activate
)
from .blockchain import (
    get_latest_header,
    get_latest_headers,
    get_all_validator_addresses,
    get_validator_information,
    get_sharding_structure,
)
from .util import (
    can_check_blockchain,
)

log_path = f"{harmony_dir}/autonode_monitor.log"

_check_interval = 8  # Estimated block time


def _run_monitor(shard_endpoint):
    start_time = time.time()
    wait_for_node_response(node_config['endpoint'], tries=900, sleep=1)  # Try for 15 min
    wait_for_node_response(shard_endpoint, tries=900, sleep=1)  # Try for 15 min
    wait_for_node_response("http://localhost:9500/", verbose=True)
    count = 0
    while get_latest_header('http://localhost:9500/')['blockNumber'] == 0:
        assert_no_bad_blocks()
        count += 1
        sys.stdout.write(f"\rWaiting for node to get past genesis block, checked {count} times")
        sys.stdout.flush()
        time.sleep(1)
    duration = node_config['duration'] if node_config['duration'] else float("inf")
    curr_time = time.time()
    while curr_time - start_time < duration:
        assert_no_bad_blocks()
        if node_config["auto-reset"]:
            if not can_check_blockchain(shard_endpoint):
                time.sleep(_check_interval)
                continue
        all_val = get_all_validator_addresses(node_config['endpoint'])
        if validator_config["validator-addr"] in all_val:
            val_chain_info = get_validator_information(validator_config["validator-addr"], node_config['endpoint'])
            print(f"{Typgpy.HEADER}EPOS status: {Typgpy.OKGREEN}{val_chain_info['epos-status']}{Typgpy.ENDC}")
            print(f"{Typgpy.HEADER}Booted status: {Typgpy.OKGREEN}{val_chain_info['booted-status']}{Typgpy.ENDC}")
            print(f"{Typgpy.HEADER}Current epoch performance: {Typgpy.OKGREEN}"
                  f"{json.dumps(val_chain_info['current-epoch-performance'], indent=4)}{Typgpy.ENDC}")
            if node_config["auto-active"]:
                check_and_activate(val_chain_info['epos-status'])
        else:
            print(f"{Typgpy.WARNING}{validator_config['validator-addr']} is not a validator.{Typgpy.ENDC}")
        print(f"{Typgpy.HEADER}This node's latest header at {datetime.datetime.utcnow()}: "
              f"{Typgpy.OKGREEN}{json.dumps(get_latest_headers('http://localhost:9500/'), indent=4)}"
              f"{Typgpy.ENDC}")
        time.sleep(_check_interval)
        curr_time = time.time()


def start():
    wait_for_node_response(node_config['endpoint'], tries=900, sleep=1)  # Try for 15 min
    bls_keys = node_config['public-bls-keys']
    shard = json_load(cli.single_call(f"hmy utility shard-for-bls {bls_keys[0].replace('0x', '')} "
                                      f"-n {node_config['endpoint']}"))['shard-id']
    shard_endpoint = get_sharding_structure(node_config['endpoint'])[shard]["http"]
    try:
        _run_monitor(shard_endpoint)
    except Exception as e:  # Catch all to handle recover options
        traceback.print_exc(file=sys.stdout)
        print(f"{Typgpy.FAIL}Auto node failed with error: {e}{Typgpy.ENDC}")
        if not node_config['auto-reset']:
            exit(0)  # Clean exit to not trigger daemon restart.
        print("")
        print(f"{Typgpy.WARNING}Waiting for network response before raising exception for daemon restart.{Typgpy.ENDC}")
        wait_for_node_response(node_config['endpoint'], verbose=False)
        wait_for_node_response(shard_endpoint, verbose=False)
        if node_config['network'] != "mainnet":
            node_config['clean'] = True
            save_node_config()
        raise e
