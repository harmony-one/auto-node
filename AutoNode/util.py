from pyhmy import cli
from pyhmy import (
    Typgpy,
    json_load
)

from .common import (
    node_config
)

from .blockchain import (
    get_block_by_number,
)


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


def input_with_print(prompt_str):
    user_input = input(prompt_str).strip()
    print(f"{Typgpy.OKBLUE}You entered: `{Typgpy.OKGREEN}{user_input}{Typgpy.OKBLUE}`{Typgpy.ENDC}")
    return user_input


def check_min_bal_on_s0(address, amount, endpoint=node_config['endpoint']):
    balances = json_load(cli.single_call(f"hmy --node={endpoint} balances {address}"))
    for bal in balances:
        if bal['shard'] == 0:
            return bal['amount'] >= amount


def can_check_blockchain(shard_endpoint, error_ok=False):
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
    if not error_ok and fb_hash is not None and fb_ref_hash is not None and fb_hash != fb_ref_hash:
        raise RuntimeError(f"Blockchains don't match! "
                           f"Block 1 hash of chain: {fb_ref_hash} != Block 1 hash of node {fb_hash}")
    return True
