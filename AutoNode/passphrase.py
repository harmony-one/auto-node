import subprocess
import os
import base64

import pexpect
from cryptography.fernet import Fernet
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, hmac
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from pyhmy import (
    Typgpy,
    cli
)

from .common import (
    log,
    validator_config,
    node_config
)


def _get_harmony_pid():
    try:
        return subprocess.check_output(["pgrep", "harmony"], env=os.environ, timeout=2)
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as e:
        log(f"{Typgpy.FAIL}WARNING: unable to get Harmony PID for wallet encryption. Error {e}{Typgpy.ENDC}")
        return b'0'


def _get_process_info(pid):
    assert isinstance(pid, bytes)
    try:
        return subprocess.check_output(["ls", "-ld", f"/proc/{pid.decode()}"], env=os.environ, timeout=2)
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as e:
        log(f"{Typgpy.FAIL}WARNING: unable to list process info for PID {pid.decode()}. Error {e}{Typgpy.ENDC}")
        return b'0'


def _get_node_based_salt():
    key = ''.join([str(x) for x in node_config["public-bls-keys"]]
                  + [str(validator_config["validator-addr"]), str(validator_config["identity"])]).encode()
    return hmac.HMAC(key, hashes.SHA256(), backend=default_backend()).finalize()


def _derive_wallet_encryption_key():
    """
    Create the wallet encryption key based on:
        PBKDF2HMAC(PID(harmony) + ProcessInfo(harmony), salt=HMAC(node_bls_public_keys, Validator_Addr, Validator_ID))
    Where node_config* are all node_configs as a dict, except for encrypted values.

    This means that the encryption key is only valid for when AutoNode has a harmony node process running.
    """
    pid = _get_harmony_pid()
    proc_info = _get_process_info(pid)
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_get_node_based_salt(),
        iterations=10000,
        backend=default_backend()
    )
    return base64.urlsafe_b64encode(kdf.derive(pid + proc_info))


def encrypt_wallet_passphrase(passphrase):
    """
    Encrypt the given passphrase.

    Returned string can be stored on disk, will be invalidated once harmony process is stopped.
    """
    assert isinstance(passphrase, str)
    return Fernet(_derive_wallet_encryption_key()).encrypt(passphrase.encode())


def decrypt_wallet_passphrase(encrypted_wallet_passphrase):
    """
    Decrypt the given encrypted passphrase.
    """
    assert isinstance(encrypted_wallet_passphrase, bytes)
    return Fernet(_derive_wallet_encryption_key()).decrypt(encrypted_wallet_passphrase).decode()


def is_valid_passphrase(passphrase, validator_address):
    """
    Validate the given passphrase, can be an expensive call.
    """
    cmd = ["hmy", "keys", "export-ks", validator_address, "/dev/null", "--passphrase"]
    try:
        proc = cli.expect_call(cmd, timeout=10)
        proc.sendline(passphrase)
        proc.expect(pexpect.EOF)
        if "Exported" in proc.before.decode():
            return True
        return False
    except (RuntimeError, pexpect.ExceptionPexpect):
        return False
