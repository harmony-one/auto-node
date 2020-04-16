#!/usr/bin/env python3
import argparse
import subprocess
from argparse import RawTextHelpFormatter

from pyhmy import (
    Typgpy
)

import AutoNode
from AutoNode import initialize


def parse_args():
    parser = argparse.ArgumentParser(description='== Run a Harmony node & validator automagically ==',
                                     usage="auto_node.sh run [OPTIONS]",
                                     formatter_class=RawTextHelpFormatter, add_help=False)
    parser.add_argument('-h', '--help', action='help', default=argparse.SUPPRESS,
                        help='Show this help message and exit')
    parser.add_argument("--auto-active", action="store_true",
                        help="Always try to set active when EPOS status is inactive.")
    parser.add_argument("--auto-reset", action="store_true",
                        help="Automatically reset node during hard resets.")
    parser.add_argument("--no-validator", action="store_true",
                        help="Disable validator automation.")
    parser.add_argument("--clean", action="store_true", help="Clean shared node directory before starting node.")
    parser.add_argument("--shard", default=None,
                        help="Specify shard of generated bls key.\n  "
                             "Only used if no BLS keys are not provided.", type=int)
    parser.add_argument("--network", help="Network to connect to (staking, partner, stress).\n  "
                                          "Default: 'staking'.", type=str, default='staking')
    parser.add_argument("--duration", type=int, help="Duration of how long the node is to run in seconds.\n  "
                                                     "Default is forever.", default=None)
    parser.add_argument("--beacon-endpoint", dest="endpoint", type=str, default=AutoNode.node_config['endpoint'],
                        help=f"Beacon chain (shard 0) endpoint for staking transactions.\n  "
                             f"Default is {AutoNode.node_config['endpoint']}")
    return parser.parse_args()


def run_setup():
    AutoNode.node_config.update({
        "endpoint": args.beacon_endpoint,
        "network": args.network,
        "clean": args.clean,
        "duration": args.duration,
        "shard": args.shard,
        "auto-reset": args.auto_reset,
        "auto-active": args.auto_active,
        "no-validator": args.no_validator,
    })
    AutoNode.initialize.config()


def check_daemon():
    pass


def start_daemon():
    print(f"{Typgpy.HEADER}Started AutoNode!{Typgpy.ENDC}")


if __name__ == "__main__":
    args = parse_args()
    run_setup()
    check_daemon()
    start_daemon()
