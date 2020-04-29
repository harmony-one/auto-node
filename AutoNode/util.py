import gzip
import os
import logging
import logging.handlers
import sys

from pyhmy import cli
from pyhmy import (
    Typgpy,
    json_load
)

from .common import (
    log,
    node_config,
    msg_tag
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


def input_with_print(prompt_str, auto_interaction=None):
    if auto_interaction is not None:
        return auto_interaction
    user_input = input(prompt_str).strip()
    sys.stdout.write(f"{Typgpy.ENDC}")
    sys.stdout.flush()
    log(f"{Typgpy.OKBLUE}You entered: `{Typgpy.OKGREEN}{user_input}{Typgpy.OKBLUE}`{Typgpy.ENDC}")
    return user_input


def check_min_bal_on_s0(address, amount, endpoint=node_config['endpoint'], timeout=30):
    balances = json_load(cli.single_call(f"hmy --node={endpoint} balances {address}", timeout=timeout))
    for bal in balances:
        if bal['shard'] == 0:
            return bal['amount'] >= amount


def get_simple_rotating_log_handler(log_file_path):
    """
    A simple log handler with no level support.
    Used purely for the output rotation.
    """
    log_formatter = logging.Formatter(f'{msg_tag} %(message)s')
    handler = logging.handlers.TimedRotatingFileHandler(log_file_path, when='h', interval=1,
                                                        backupCount=5, encoding='utf8')
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(log_formatter)
    handler.rotator = _GZipRotator()
    return handler

