"""
Library of common utils used by most function libraries of AutoNode.

To prevent cyclic import minimize the importing of other libraries in AutoNode.
"""

import gzip
import logging
import logging.handlers
import os
import sys

import pexpect
from pyhmy import (
    Typgpy,
    json_load
)
from pyhmy import cli

from .common import (
    log,
    node_config,
    validator_config,
    msg_tag,
    bls_key_len
)
from .exceptions import (
    InvalidWalletPassphrase
)
from .passphrase import (
    decrypt_wallet_passphrase,
    is_valid_passphrase
)


class _GZipRotator:
    """A simple zip rotator for logging"""

    def __call__(self, source, dest):
        os.rename(source, dest)
        f_in = open(dest, 'rb')
        f_out = gzip.open("%s.gz" % dest, 'wb')
        f_out.writelines(f_in)
        f_out.close()
        f_in.close()
        os.remove(dest)


def get_wallet_passphrase():
    """
    Gets encrypted passphrase from node_config, unencrypt, validate, and return.

    Raises InvalidWalletPassphrase if encrypted passphrase is invalid.
    """
    passphrase = decrypt_wallet_passphrase(node_config["encrypted-wallet-passphrase"])
    if not is_valid_passphrase(passphrase, validator_config["validator-addr"]):
        raise InvalidWalletPassphrase()
    return passphrase


def pexpect_input_wallet_passphrase(proc, passphrase, prompt="Enter wallet keystore passphrase:\r\n"):
    """
    Interactively input the wallet passphrase to the given pexpect child process
    """
    assert isinstance(proc, pexpect.pty_spawn.spawn)
    proc.expect(prompt)
    proc.sendline(passphrase)


def pexpect_input_wallet_creation_passphrase(proc, passphrase):
    """
    This will enter the `passphrase` interactively given the pexpect child program, `proc`.
    """
    assert isinstance(proc, pexpect.pty_spawn.spawn)
    pexpect_input_wallet_passphrase(proc, passphrase, prompt="Enter passphrase:\r\n")
    pexpect_input_wallet_passphrase(proc, passphrase, prompt="Repeat the passphrase:\r\n")
    proc.expect("\n")


def input_with_print(prompt_str, auto_interaction=None):
    if auto_interaction is not None:
        return auto_interaction
    user_input = input(prompt_str).strip()
    sys.stdout.write(f"{Typgpy.ENDC}")
    sys.stdout.flush()
    log(f"{Typgpy.OKBLUE}You entered: `{Typgpy.OKGREEN}{user_input}{Typgpy.OKBLUE}`{Typgpy.ENDC}")
    return user_input


def check_min_bal_on_s0(address, amount, endpoint=node_config['endpoint'], timeout=30):
    balances = json_load(cli.single_call(['hmy', '--node', endpoint, 'balances', address], timeout=timeout))
    for bal in balances:
        if bal['shard'] == 0:
            return bal['amount'] >= amount


def get_simple_rotating_log_handler(log_file_path, max_size=5 * 1024 * 1024):
    """
    A simple log handler with no level support.
    Used purely for the output rotation.

    `max_size` of log file is in bytes.
    """
    log_formatter = logging.Formatter(f'{msg_tag} %(message)s')
    handler = logging.handlers.RotatingFileHandler(log_file_path, mode='a', maxBytes=max_size,
                                                   backupCount=5, encoding=None, delay=0)
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(log_formatter)
    handler.rotator = _GZipRotator()
    return handler


def shard_for_bls(public_bls_key):
    """
    Fetch the shard for the BLS key.

    NOTE: Expect to be invalid one we have resharding.
    """
    return json_load(cli.single_call(['hmy', '--node', f'{node_config["endpoint"]}', 'utility',
                                      'shard-for-bls', public_bls_key]))['shard-id']


def is_bls_file(file_name, suffix):
    if file_name.startswith('.') or not file_name.endswith(suffix):
        return False
    tok = file_name.split(".")
    if len(tok) != 2 or len(tok[0]) != bls_key_len:
        return False
    return True
