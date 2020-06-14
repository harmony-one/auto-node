#!/usr/bin/env python3
import argparse
from inspect import signature

from AutoNode import (
    daemon,
    common
)


def node():
    if common.node_config["_is_recovering"]:
        if common.node_config["auto-reset"]:
            print("== RUNNING NODE IN HARD-RESET RECOVERY MODE ==")
            daemon.run_node(hard_reset_recovery=True, duration=float('inf'))
        else:
            raise SystemExit("Node config specifies NO auto-reset, but node was attempting to auto-reset.")
    else:
        daemon.run_node(hard_reset_recovery=False, duration=float('inf'))


autonode_service_functions = {
    "monitor": lambda: daemon.run_monitor(duration=float('inf')),
    "node": node,
}
assert set(daemon.services) == set(autonode_service_functions.keys()), "Failed autonoded API sanity check"
assert all(len(signature(fn).parameters) == 0 for fn in
           autonode_service_functions.values()), "Failed autonoded API sanity check"


def parse_args():
    parser = argparse.ArgumentParser(description="== Harmony AutoNode daemon ==")
    parser.add_argument("service", help=f"Specify the desired service. Currently supports: {daemon.services}")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if args.service not in autonode_service_functions.keys():
        raise SystemExit(f"Service '{args.service}' is not supported.")
    autonode_service_functions[args.service]()
