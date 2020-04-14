import argparse
import os
import json

import pexpect
from pyhmy import cli
from pyhmy import (
    Typgpy,
    json_load,
)

with open("./node/validator_config.json") as f:  # WARNING: assumption of copied file on docker run.
    validator_info = json.load(f)


def setup():
    cli.environment.update(cli.download("./bin/hmy", replace=False))
    cli.set_binary("./bin/hmy")


def send_create_validator_tx(val_info, bls_pub_keys, passphrase, endpoint):
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
    except (json.JSONDecodeError, RuntimeError, pexpect.exceptions):
        print(f"{Typgpy.FAIL}Failed to create validator!\n\tError: {e}"
              f"\n\tMsg:\n{proc.before.decode()}{Typgpy.ENDC}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('bls_pub_keys', type=str)
    parser.add_argument('passphrase', type=str)
    parser.add_argument('endpoint', type=str)
    args = parser.parse_args()
    send_create_validator_tx(validator_info, eval(args.bls_pub_keys), args.passphrase, args.endpoint)
