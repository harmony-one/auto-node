#!/usr/bin/env python3
import argparse
import os
import time
import glob
from argparse import RawTextHelpFormatter
import subprocess

from pyhmy import Typgpy
import AutoNode
from AutoNode import (
    initialize,
    daemon,
    validator,
    common,
    monitor,
    node,
    util
)


def assert_dead_daemons():
    """
    Exits script if AutoNode services are active.
    """
    check_monitor_cmd = f"systemctl --user --type=service --all --state=active | grep {daemon.name}@monitor"
    check_node_cmd = f"systemctl --user --type=service --all --state=active | grep {daemon.name}@node"
    if subprocess.call(f"{check_monitor_cmd} > /dev/null", shell=True, env=os.environ) == 0:
        raise SystemExit("AutoNode monitor daemon is still active, stop with `auto-node kill`")
    if subprocess.call(f"{check_node_cmd} > /dev/null", shell=True, env=os.environ) == 0:
        raise SystemExit("AutoNode node daemon is still active, stop with `auto-node kill`")


def start_node():
    """
    Raises a subprocess.CalledProcessError if unable to start node service
    """
    service = "node"
    assert service in daemon.services, f"sanity check: unknown {service} service"
    cmd = ["systemctl", "--user", "start", f"{daemon.name}@{service}.service"]
    subprocess.check_call(cmd, env=os.environ)
    AutoNode.common.log(f"{Typgpy.HEADER}Started node!{Typgpy.ENDC}")


def start_monitor():
    """
    Raises a subprocess.CalledProcessError if unable to start node service
    """
    service = "monitor"
    assert service in daemon.services, f"sanity check: unknown {service} service"
    cmd = ["systemctl", "--user", "start", f"{daemon.name}@{service}.service"]
    subprocess.check_call(cmd, env=os.environ)
    AutoNode.common.log(f"{Typgpy.HEADER}Started monitor!{Typgpy.ENDC}")


def clean_up_bls_pass(is_auto_reset):
    prompt = f"Remove BLS passphrase file? [Y]/n"
    if is_auto_reset:
        prompt += f"\n{Typgpy.WARNING}Note: 'auto-recover' option will not work if files are removed{Typgpy.ENDC}"
    prompt += "\n> "
    if util.input_with_print(prompt).lower not in {'y', 'yes'}:
        return
    for file_path in glob.glob(f"{common.bls_key_dir}/*.pass"):
        os.remove(file_path)


def tail_monitor_log():
    if os.path.exists(monitor.log_path):
        subprocess.call(["tail", "-f", monitor.log_path], env=os.environ)
    else:
        raise SystemExit("Monitor failed to start")


def reset():
    """
    Assumes that monitor and node daemons are stopped.
    """
    try:
        common.reset_node_config()
        if os.path.isfile(common.saved_node_config_path):
            os.remove(common.saved_node_config_path)
        if os.path.isfile(node.log_path):
            os.remove(node.log_path)
        if os.path.isfile(monitor.log_path):
            os.remove(monitor.log_path)
    except Exception as e:
        raise SystemExit(e)


def _parse_args():
    parser = argparse.ArgumentParser(description='== Run a Harmony node & validator automagically ==',
                                     usage="auto-node run [OPTIONS]",
                                     formatter_class=RawTextHelpFormatter, add_help=False)
    parser.add_argument('-h', '--help', action='help', default=argparse.SUPPRESS,
                        help='Show this help message and exit')
    parser.add_argument("--auto-active", action="store_true",
                        help="Always try to set active when EPOS status is inactive.")
    parser.add_argument("--auto-reset", action="store_true", help="Automatically reset node during hard resets.\n"
                                                                  "Only available with test networks.")
    parser.add_argument("--no-validator", action="store_true", help="Disable validator automation.")
    parser.add_argument("--archival", action="store_true", help="Run node with archival mode.")
    parser.add_argument("--no-download", action="store_true", help="Run node with existing binary.")
    parser.add_argument("--clean", action="store_true", help="Clean shared node directory before starting node.")
    parser.add_argument("--fast-sync", action="store_true", help="Rclone existing db snapshot(s)")
    parser.add_argument("--shard", default=None,
                        help="Specify shard of generated bls key.\n  "
                             "Only used if no BLS keys are not provided.", type=int)
    parser.add_argument("--network", help="Network to connect to (mainnet, testnet).\n  "
                                          "Default: 'testnet'.", type=str, default='testnet',
                        choices=['mainnet', 'testnet', 'partner', 'stress', 'staking'])
    parser.add_argument("--beacon-endpoint", dest="endpoint", type=str, default="https://api.s0.b.hmny.io/",
                        help=f"Beacon chain (shard 0) endpoint for staking transactions.\n  "
                             f"Default is https://api.s0.b.hmny.io/")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    assert_dead_daemons()
    common.log(f"{Typgpy.HEADER}=== STARTED NEW AUTONODE ==={Typgpy.ENDC}")
    reset()
    if args.network == 'mainnet':
        if args.auto_reset:
            raise SystemExit(f"Cannot use --auto-reset with 'mainnet' network")
        if args.clean:
            raise SystemExit(f"Cannot use --clean with 'mainnet' network")
    common.node_config.update({
        "endpoint": args.endpoint,
        "network": args.network,
        "clean": args.clean,
        "shard": args.shard,
        "auto-reset": args.auto_reset,
        "auto-active": args.auto_active,
        "no-validator": args.no_validator,
        "no-download": args.no_download,
        "fast-sync": args.fast_sync,
        "archival": args.archival,
        "_is_recovering": False  # Never recovering from a hard reset on a run
    })
    common.save_node_config()
    initialize.setup_node_config()
    node.assert_valid_bls_key_directory()
    start_node()
    try:
        if not args.no_validator:
            validator.setup(hard_reset_recovery=False)
    finally:
        clean_up_bls_pass(is_auto_reset=args.auto_reset)
        start_monitor()
        start_time = time.time()
        while time.time() - start_time < 5:
            if os.path.exists(monitor.log_path):
                break
        try:
            tail_monitor_log()
        except KeyboardInterrupt:
            exit(0)
