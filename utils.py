import json
import os
import subprocess
import stat
import sys
import time
from threading import Lock

import requests
from pyhmy import (
    Typgpy,
    json_load
)
from pyhmy import cli
import pexpect

default_endpoint = "https://api.s0.os.hmny.io/"
node_script_source = "https://raw.githubusercontent.com/harmony-one/harmony/master/scripts/node.sh"
default_cli_passphrase = ""  # WARNING: assumption made about hmy CLI
node_sh_log_dir = "/root/node/node_sh_logs"  # WARNING: assumption made on auto_node.sh
os.makedirs(node_sh_log_dir, exist_ok=True)
node_sh_out_path = f"{node_sh_log_dir}/out.log"
node_sh_err_path = f"{node_sh_log_dir}/err.log"

directory_lock = Lock()
env = os.environ


def setup():
    cli.environment.update(cli.download("./bin/hmy", replace=False))
    cli.set_binary("./bin/hmy")


"""
BLOCKCHAIN FUNCTIONS ARE BELOW
"""


def get_current_epoch(endpoint=default_endpoint):
    return int(get_latest_header(endpoint)["epoch"])


def get_latest_header(endpoint=default_endpoint):
    payload = json.dumps({"id": "1", "jsonrpc": "2.0",
                          "method": "hmy_latestHeader",
                          "params": []})
    headers = {
        'Content-Type': 'application/json'
    }
    response = requests.request('POST', endpoint, headers=headers, data=payload, allow_redirects=False, timeout=3)
    return json.loads(response.content)["result"]


def get_latest_headers(endpoint=default_endpoint):
    payload = json.dumps({"id": "1", "jsonrpc": "2.0",
                          "method": "hmy_getLatestChainHeaders",
                          "params": []})
    headers = {
        'Content-Type': 'application/json'
    }
    response = requests.request('POST', endpoint, headers=headers, data=payload, allow_redirects=False, timeout=3)
    return json.loads(response.content)["result"]


def get_sharding_structure(endpoint=default_endpoint):
    payload = json.dumps({"id": "1", "jsonrpc": "2.0",
                          "method": "hmy_getShardingStructure",
                          "params": []})
    headers = {
        'Content-Type': 'application/json'
    }
    response = requests.request('POST', endpoint, headers=headers, data=payload, allow_redirects=False, timeout=3)
    return json.loads(response.content)["result"]


def get_block_by_number(number, endpoint=default_endpoint):
    payload = json.dumps({"id": "1", "jsonrpc": "2.0",
                          "method": "hmyv2_getBlockByNumber",
                          "params": [number, {}]})
    headers = {
        'Content-Type': 'application/json'
    }
    response = requests.request('POST', endpoint, headers=headers, data=payload, allow_redirects=False, timeout=3)
    return json.loads(response.content)["result"]


def get_staking_epoch(endpoint=default_endpoint):
    payload = json.dumps({"id": "1", "jsonrpc": "2.0",
                          "method": "hmy_getNodeMetadata",
                          "params": []})
    headers = {
        'Content-Type': 'application/json'
    }
    response = requests.request('POST', endpoint, headers=headers, data=payload, allow_redirects=False, timeout=3)
    body = json.loads(response.content)
    return int(body["result"]["chain-config"]["staking-epoch"])


def get_validator_information(address, endpoint=default_endpoint):
    payload = json.dumps({"id": "1", "jsonrpc": "2.0",
                          "method": "hmy_getValidatorInformation",
                          "params": [address]})
    headers = {
        'Content-Type': 'application/json'
    }
    response = requests.request('POST', endpoint, headers=headers, data=payload, allow_redirects=False, timeout=3)
    body = json.loads(response.content)
    if 'error' in body:
        raise RuntimeError(str(body['error']))
    return body['result']


"""
VALIDATOR FUNCTIONS ARE BELOW
"""


def add_bls_key_to_validator(val_info, bls_pub_keys, passphrase, endpoint):
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
            proc = cli.expect_call(f"hmy --node={endpoint} staking edit-validator "
                                   f"--validator-addr {val_info['validator-addr']} "
                                   f"--add-bls-key {k} --passphrase-file /.wallet_passphrase ")
            proc.expect("Enter the bls passphrase:\r\n")
            proc.sendline(passphrase)
            proc.expect(pexpect.EOF)
            print(f"\n{Typgpy.OKBLUE}Edit-validator transaction response: "
                  f"{Typgpy.OKGREEN}{proc.before.decode()}{Typgpy.ENDC}")
    directory_lock.release()
    new_val_info = json_load(cli.single_call(f"hmy --node={endpoint} blockchain "
                                             f"validator information {val_info['validator-addr']}"))["result"]
    new_bls_keys = new_val_info["validator"]["bls-public-keys"]
    print(f"{Typgpy.OKBLUE}{val_info['validator-addr']} updated bls keys: {new_bls_keys}{Typgpy.ENDC}")
    verify_node_sync(endpoint)
    print()


def verify_node_sync(endpoint):
    print(f"{Typgpy.OKBLUE}Verifying Node Sync...{Typgpy.ENDC}")
    wait_for_node_liveliness("http://localhost:9500/")
    curr_headers = get_latest_headers("http://localhost:9500/")
    curr_epoch_shard = curr_headers['shard-chain-header']['epoch']
    curr_epoch_beacon = curr_headers['beacon-chain-header']['epoch']
    ref_epoch = get_latest_header(endpoint)['epoch']
    while curr_epoch_shard != ref_epoch or curr_epoch_beacon != ref_epoch:
        sys.stdout.write(f"\rWaiting for node to sync: shard epoch ({curr_epoch_shard}/{ref_epoch}) "
                         f"& beacon epoch ({curr_epoch_beacon}/{ref_epoch})")
        sys.stdout.flush()
        time.sleep(2)
        try:
            curr_headers = get_latest_headers("http://localhost:9500/")
            curr_epoch_shard = curr_headers['shard-chain-header']['epoch']
            curr_epoch_beacon = curr_headers['beacon-chain-header']['epoch']
            ref_epoch = get_latest_header(endpoint)['epoch']
        except (ConnectionError, requests.exceptions.ConnectionError, KeyError) as e:
            print(f"{Typgpy.FAIL}Warning failed to verify node sync {e}{Typgpy.ENDC}")
            pass  # Ignore any errors and try again
    print(f"\n{Typgpy.OKGREEN}Node synced to current epoch{Typgpy.ENDC}")


def create_new_validator(val_info, bls_pub_keys, passphrase, endpoint):
    print(f"{Typgpy.HEADER}Checking validator...{Typgpy.ENDC}")
    staking_epoch = get_staking_epoch(endpoint)
    curr_epoch = get_current_epoch(endpoint)
    print(f"{Typgpy.OKBLUE}Verifying Epoch...{Typgpy.ENDC}")
    while curr_epoch < staking_epoch:  # WARNING: using staking epoch for extra security of configs.
        sys.stdout.write(f"\rWaiting for staking epoch ({staking_epoch}) -- current epoch: {curr_epoch}")
        sys.stdout.flush()
        time.sleep(8)  # Assumption of 8 second block time...
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
    send_create_validator_tx(val_info, bls_pub_keys, passphrase, endpoint)
    print()


def send_create_validator_tx(val_info, bls_pub_keys, passphrase, endpoint):
    directory_lock.acquire()
    os.chdir("/root/bin")  # Needed for implicit BLS key...
    proc = cli.expect_call(f'hmy --node={endpoint} staking create-validator '
                           f'--validator-addr {val_info["validator-addr"]} --name "{val_info["name"]}" '
                           f'--identity "{val_info["identity"]}" --website "{val_info["website"]}" '
                           f'--security-contact "{val_info["security-contact"]}" --details "{val_info["details"]}" '
                           f'--rate {val_info["rate"]} --max-rate {val_info["max-rate"]} '
                           f'--max-change-rate {val_info["max-change-rate"]} '
                           f'--min-self-delegation {val_info["min-self-delegation"]} '
                           f'--max-total-delegation {val_info["max-total-delegation"]} '
                           f'--amount {val_info["amount"]} --bls-pubkeys {",".join(bls_pub_keys)} '
                           f'--passphrase-file /.wallet_passphrase ')
    for _ in range(len(bls_pub_keys)):
        proc.expect("Enter the bls passphrase:\r\n")  # WARNING: assumption about interaction
        proc.sendline(passphrase)
    proc.expect(pexpect.EOF)
    try:
        response = json_load(proc.before.decode())
        print(f"{Typgpy.OKBLUE}Created Validator!\n{Typgpy.OKGREEN}{json.dumps(response, indent=4)}{Typgpy.ENDC}")
    except (json.JSONDecodeError, RuntimeError, pexpect.exceptions) as e:
        print(f"{Typgpy.FAIL}Failed to create validator!\n\tError: {e}"
              f"\n\tMsg:\n{proc.before.decode()}{Typgpy.ENDC}")
    directory_lock.release()


"""
NODE FUNCTIONS ARE BELOW
"""


def start_node(bls_keys_path, network, clean=False):
    directory_lock.acquire()
    os.chdir("/root/node")
    if os.path.isfile("/root/node/node.sh"):
        os.remove("/root/node/node.sh")
    r = requests.get(node_script_source)
    with open("node.sh", 'w') as f:
        node_sh = r.content.decode()
        # WARNING: Hack until node.sh is changed for auto-node.
        node_sh = node_sh.replace("save_pass_file=false", 'save_pass_file=true')
        node_sh = node_sh.replace("sudo", '')
        f.write(node_sh)
    st = os.stat("node.sh")
    os.chmod("node.sh", st.st_mode | stat.S_IEXEC)
    node_args = ["./node.sh", "-N", network, "-z", "-f", bls_keys_path, "-M"]
    if clean:
        node_args.append("-c")
    directory_lock.release()
    with open(node_sh_out_path, 'w+') as fo:
        with open(node_sh_err_path, 'w+') as fe:
            print(f"{Typgpy.HEADER}Starting node!{Typgpy.ENDC}")
            return subprocess.Popen(node_args, env=env, stdout=fo, stderr=fe).pid


def wait_for_node_liveliness(endpoint, verbose=True):
    alive = False
    while not alive:
        try:
            get_latest_headers(endpoint)
            alive = True
        except (json.JSONDecodeError, json.decoder.JSONDecodeError, requests.exceptions.ConnectionError,
                RuntimeError, KeyError, AttributeError):
            time.sleep(.5)
    if verbose:
        print(f"{Typgpy.HEADER}[!] {endpoint} is alive!{Typgpy.ENDC}")


"""
MISC FUNCTIONS ARE BELOW
"""


def process_passphrase(proc, passphrase, double_take=False):
    """
    This will enter the `passphrase` interactively given the pexpect child program, `proc`.
    """
    proc.expect("Enter passphrase:\r\n")
    proc.sendline(passphrase)
    if double_take:
        proc.expect("Repeat the passphrase:\r\n")
        proc.sendline(passphrase)
        proc.expect("\n")


def check_min_bal_on_s0(address, amount, endpoint=default_endpoint):
    balances = json_load(cli.single_call(f"hmy --node={endpoint} balances {address}"))
    for bal in balances:
        if bal['shard'] == 0:
            return bal['amount'] >= amount