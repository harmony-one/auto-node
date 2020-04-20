#!/usr/bin/env python3
import argparse
import os

from AutoNode import (
    daemon,
    common
)


def parse_args():
    parser = argparse.ArgumentParser(description="== Harmony AutoNode daemon ==")
    parser.add_argument("service", help=f"Specify the desired service. Currently supports: {daemon.Daemon.services}")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    common.log(f"Running daemon as user: {os.environ['USER']}")
    daemon = daemon.Daemon(args.service)
    daemon.validate_config()
    daemon.start()
    daemon.block()
    common.log(f"Daemon terminated...")
