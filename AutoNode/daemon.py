"""
Library of tools to be used by the AutoNode Daemon.
"""
import os
import subprocess
import time

from .common import (
    saved_node_config_path,
    save_node_config,
    saved_validator_path,
    bls_key_dir,
    node_config,
)
from .node import (
    start as node_start
)
from .validator import (
    setup as validator_setup,
    assert_node_started
)
from .monitor import (
    start as start_monitor,
    ResetNode
)
from .initialize import (
    save_wallet_passphrase
)
from .util import (
    get_wallet_passphrase,
)
from .exceptions import (
    InvalidWalletPassphrase
)

name = f"autonoded"
services = [
    "monitor",
    "node",
]


def _validate_config(for_node=False):
    """
    Validates the given config.
    Should be used prior to running a major AutoNode operation.
    """
    required_files = [
        saved_node_config_path,
    ]
    if not for_node:
        required_files.append(saved_validator_path)
    if any(not os.path.isfile(p) for p in required_files):
        raise SystemExit(f"AutoNode was not initialized properly. "
                         f"One or more files are missing: {required_files}")
    if for_node:
        # Assumes that .pass files are always present -- artifact of node.sh, should be amended in the future
        files_in_bls_dir = set(os.listdir(bls_key_dir))
        for bls_key in node_config['public-bls-keys']:
            key_file, pass_file = f"{bls_key}.key", f"{bls_key}.pass"
            if key_file not in files_in_bls_dir:
                raise SystemExit(f"{bls_key} in node config, but {key_file} not found in "
                                 f"BLS key directory at {bls_key_dir}")
            if pass_file not in files_in_bls_dir:
                raise SystemExit(f"{bls_key} in node config, but {pass_file} not found in "
                                 f"BLS key directory at {bls_key_dir}")


def run_node(hard_reset_recovery=False, duration=float('inf')):
    """
    Main function to run a harmony node.
    Will block for the `duration`.
    """
    print(f"Running node for {duration} seconds. Hard reset: {hard_reset_recovery}")
    start_time = time.time()
    _validate_config(for_node=True)
    pid = None
    try:
        pid = node_start(auto=True, verbose=True)
        if hard_reset_recovery:
            validator_setup(hard_reset_recovery=True)
        while time.time() - start_time < duration:
            time.sleep(1)
            pass
    finally:
        if pid is not None:
            print(f"Killing harmony process, pid: {pid}")
            subprocess.check_call(f"kill -2 {pid}", shell=True, env=os.environ)


def _reset_node(recover_service_name, error):
    """
    Internal function to reset a node during hard reset.
    """
    assert isinstance(error, ResetNode)
    assert recover_service_name in services, f"{recover_service_name} is not a valid service."

    print(f"Resetting Node: {error}")
    if node_config['network'] == 'mainnet':
        print("WARNING: cannot reset mainnet node, ignoring...")
        return

    passphrase = get_wallet_passphrase()

    # Set flags to indicate that node is in hard-reset recovery mode.
    node_config['_is_recovering'] = True
    save_node_config()

    for service in filter(lambda e: e.startswith("node"), services):
        daemon_name = f"{name}@{service}.service"
        command = f"systemctl --user stop {daemon_name}"
        print(f"Stopping daemon {daemon_name}")
        try:
            subprocess.check_call(command, shell=True, env=os.environ)
        except subprocess.CalledProcessError as e:
            print(f"Unable to stop service '{daemon_name}'")
            raise e

    subprocess.call(f"killall harmony", shell=True, env=os.environ)  # OK if this fails, so use subprocess.call
    time.sleep(5)  # wait for node shutdown

    daemon_name = f"{name}@{recover_service_name}.service"
    command = f"systemctl --user start {daemon_name}"
    print(f"Starting daemon {daemon_name}")
    try:
        subprocess.check_call(command, shell=True, env=os.environ)
    except subprocess.CalledProcessError as e:
        print(f"Unable to start service '{daemon_name}'")
        raise e

    try:
        assert_node_started()
        save_wallet_passphrase(passphrase)
    except (AssertionError, InvalidWalletPassphrase) as e:
        print(f"Could not re-auth wallet, error {e}")
        print(f"Continuing...")
    finally:
        # Set flags to indicate that node finished with hard-reset recovery.
        node_config['_is_recovering'] = False
        save_node_config()


def run_monitor(duration=float('inf')):
    """
    Main function to run the monitor.
    """
    print(f"Running monitor for {duration} seconds.")
    _validate_config(for_node=False)
    while True:
        try:
            # Monitor will raise a ResetNode exception to trigger a node reset, otherwise it will gracefully exit.
            start_monitor(duration=duration)
            break
        except ResetNode as error:
            if node_config['auto-reset']:
                _reset_node("node", error)
    print("Terminating monitor.")
