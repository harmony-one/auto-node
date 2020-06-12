import gzip
import os
import logging
import logging.handlers
import sys

import pexpect
from pyhmy import cli
from pyhmy import (
    Typgpy,
    json_load
)

from .common import (
    log,
    node_config,
    validator_config,
    msg_tag
)
from .passphrase import (
    decrypt_wallet_passphrase,
    is_valid_passphrase
)
from .exceptions import (
    InvalidWalletPassphrase
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


def interact_wallet_passphrase(proc, passphrase, prompt="Enter wallet keystore passphrase:\r\n"):
    """
    Interactively input the wallet passphrase to the given pexpect child process
    """
    assert isinstance(proc, pexpect.pty_spawn.spawn)
    proc.expect(prompt)
    proc.sendline(passphrase)


def process_wallet_creation_passphrase(proc, passphrase):
    """
    This will enter the `passphrase` interactively given the pexpect child program, `proc`.
    """
    assert isinstance(proc, pexpect.pty_spawn.spawn)
    interact_wallet_passphrase(proc, passphrase, prompt="Enter passphrase:\r\n")
    interact_wallet_passphrase(proc, passphrase, prompt="Repeat the passphrase:\r\n")
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


def get_simple_rotating_log_handler(log_file_path, max_size=5*1024*1024):
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
