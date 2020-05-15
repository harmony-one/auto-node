#!/usr/bin/env python3
import argparse
import os
from argparse import RawTextHelpFormatter
import subprocess

from pyhmy import Typgpy
import AutoNode
from AutoNode import initialize
from AutoNode.daemon import Daemon
from AutoNode.common import log


def parse_args():
    parser = argparse.ArgumentParser(description='== Run a Harmony node & validator automagically ==',
                                     usage="auto_node.sh run [OPTIONS]",
                                     formatter_class=RawTextHelpFormatter, add_help=False)
    parser.add_argument('-h', '--help', action='help', default=argparse.SUPPRESS,
                        help='Show this help message and exit')
    parser.add_argument("--auto-active", action="store_true",
                        help="Always try to set active when EPOS status is inactive.")
    parser.add_argument("--auto-reset", action="store_true", help="Automatically reset node during hard resets.")
    parser.add_argument("--no-validator", action="store_true", help="Disable validator automation.")
    parser.add_argument("--archival", action="store_true", help="Run node with archival mode.")
    parser.add_argument("--no-download", action="store_true", help="Run node with existing binary.")
    parser.add_argument("--update-cli", action="store_true", help="Toggle upgrading the Harmony CLI used by AutoNode")
    parser.add_argument("--clean", action="store_true", help="Clean shared node directory before starting node.\n "
                                                             "Only available with test networks.")
    parser.add_argument("--fast-sync", action="store_true", help="Rclone existing db snapshot(s)")
    parser.add_argument("--shard", default=None,
                        help="Specify shard of generated bls key.\n  "
                             "Only used if no BLS keys are not provided.", type=int)
    parser.add_argument("--network", help="Network to connect to (staking, partner, stress).\n  "
                                          "Default: 'staking'.", type=str, default='staking')
    parser.add_argument("--duration", type=int, help="Duration of how long the node is to run in seconds.\n  "
                                                     "Default is forever.", default=None)
    parser.add_argument("--beacon-endpoint", dest="endpoint", type=str, default="https://api.s0.os.hmny.io/",
                        help=f"Beacon chain (shard 0) endpoint for staking transactions.\n  "
                             f"Default is https://api.s0.os.hmny.io/")
    return parser.parse_args()


def assert_dead_daemons():
    check_monitor_cmd = f"systemctl --type=service --state=active | grep -e ^{Daemon.name}@monitor"
    check_node_cmd = f"systemctl --type=service --state=active | grep -e ^{Daemon.name}@node"
    if subprocess.call(f"{check_monitor_cmd} > /dev/null", shell=True, env=os.environ) == 0:
        raise SystemExit("AutoNode monitor daemon is still active, stop with `auto_node.sh kill`")
    if subprocess.call(f"{check_node_cmd} > /dev/null", shell=True, env=os.environ) == 0:
        raise SystemExit("AutoNode node daemon is still active, stop with `auto_node.sh kill`")


if __name__ == "__main__":
    args = parse_args()
    assert_dead_daemons()
    if args.auto_reset and subprocess.call("sudo -n true", shell=True, env=os.environ) != 0:
        raise SystemExit(
            f"{Typgpy.FAIL}User {AutoNode.common.user} does not have sudo privileges without password.\n "
            f"For `--auto-reset` option, user must have said privilege.{Typgpy.ENDC}")
    AutoNode.initialize.reset()
    if args.network == 'mainnet':
        if args.auto_reset:
            log(f'{Typgpy.WARNING}[!] Cannot use --auto-reset with Mainnet{Typgpy.ENDC}')
            args.auto_reset = False
        if args.clean:
            log(f'{Typgpy.WARNING}[!] Cannot use --clean with Mainnet{Typgpy.ENDC}')
            args.clean = False
    AutoNode.node_config.update({
        "endpoint": args.endpoint,
        "network": args.network,
        "clean": args.clean,
        "duration": args.duration,
        "shard": args.shard,
        "auto-reset": args.auto_reset,
        "auto-active": args.auto_active,
        "no-validator": args.no_validator,
        "no-download": args.no_download,
        "fast-sync": args.fast_sync,
        "archival": args.archival
    })
    AutoNode.initialize.config(update_cli=args.update_cli)
    AutoNode.common.log(f"{Typgpy.HEADER}AutoNode has been initialized!{Typgpy.ENDC}")
