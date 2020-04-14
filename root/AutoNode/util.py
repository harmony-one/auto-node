from pyhmy import cli
from pyhmy import (
    Typgpy,
    json_load
)

from .common import (
    default_endpoint
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


def check_min_bal_on_s0(address, amount, endpoint=default_endpoint):
    balances = json_load(cli.single_call(f"hmy --node={endpoint} balances {address}"))
    for bal in balances:
        if bal['shard'] == 0:
            return bal['amount'] >= amount