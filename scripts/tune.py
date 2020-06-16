#!/usr/bin/env python3
import os
import argparse
import subprocess
import pickle
import time
import datetime
from argparse import RawTextHelpFormatter

from AutoNode import common
from pyhmy import (
    Typgpy
)

kernel_tunes = {
    "fs.file-max": 2097152,
    "vm.swappiness": 10,
    "vm.dirty_ratiol": 60,
    "vm.dirty_background_ratio": 2,
    "kernel.sched_migration_cost_ns": 5000000
}

network_security = {
    "net.ipv4.tcp_synack_retries": 2,
    "net.ipv4.ip_local_port_range": "'2000 65535'",
    "net.ipv4.tcp_rfc1337": 1,
    "net.ipv4.tcp_syncookies": 1,
    "net.ipv4.tcp_fin_timeout": 15,
    "net.ipv4.tcp_keepalive_time": 300,
    "net.ipv4.tcp_keepalive_probes": 5,
    "net.ipv4.tcp_keepalive_intvl": 15,
}

network_tuning = {
    "net.core.rmem_default": 31457280,
    "net.core.rmem_max": 33554432,
    "net.core.wmem_default": 31457280,
    "net.core.wmem_max": 33554432,
    "net.core.somaxconn": 8096,
    "net.core.netdev_max_backlog": 65536,
    "net.core.optmem_max": 25165824,
    "net.ipv4.tcp_max_syn_backlog": 8192,
    "net.ipv4.tcp_mem": "'786432 1048576 26777216'",
    "net.ipv4.udp_mem": "'65536 131072 262144'",
    "net.ipv4.tcp_rmem": "'8192 87380 33554432'",
    "net.ipv4.udp_rmem_min": 16384,
    "net.ipv4.tcp_wmem": "'8192 65536 33554432'",
    "net.ipv4.udp_wmem_min": 16384,
    "net.ipv4.tcp_max_tw_buckets": 1440000,
    "net.ipv4.tcp_tw_reuse": 1,
    "net.ipv4.tcp_fastopen": 3,
    "net.ipv4.tcp_window_scaling": 1
}

params = {"kernel", "network", "restore"}
sysctl_path = "/etc/sysctl.conf"
saved_config_path = f"{common.harmony_dir}/.tune_saved_configs.p"
saved_config = {}  # Keys = time.time(): Value = saved config as a string


def _load_existing_config():
    saved_config.clear()
    if os.path.exists(saved_config_path):
        with open(saved_config_path, 'rb') as f:
            saved_config.update(pickle.load(f))


def _save_existing_config():
    if os.path.isfile(saved_config_path):
        subprocess.check_call(["sudo", "chattr", "-i", saved_config_path], env=os.environ)
    try:
        with open(saved_config_path, 'wb') as f:
            pickle.dump(saved_config, f)
    finally:
        subprocess.check_call(["sudo", "chattr", "+i", saved_config_path], env=os.environ)


def save_existing_config():
    """
    Saves files contents at `sysctl_path` to pickle file in
    AutoNode directory and makes saves pickle file immutable.

    Returns time of stored config.
    """
    old_config_string = ''
    if os.path.isfile(sysctl_path):
        with open(sysctl_path, 'r', encoding='utf8') as f:
            old_config_string = f.read()
    _load_existing_config()
    saved_time = time.time()
    saved_config[saved_time] = old_config_string
    _save_existing_config()
    return saved_time


def restore_existing_config():
    """
    Restore existing config file in last known.

    Returns time of restored config.
    """
    _load_existing_config()
    if not saved_config:
        raise SystemExit("No sysctl config to restore from...")
    latest_saved_config_key = sorted(saved_config.keys(), reverse=True)[0]
    latest_saved_config = saved_config[latest_saved_config_key]
    with open(sysctl_path, 'w', encoding='utf8') as f:
        f.write(latest_saved_config)
    subprocess.check_call(["sudo", "sysctl", "-p"], env=os.environ)
    del saved_config[latest_saved_config_key]
    _save_existing_config()
    return latest_saved_config_key


def process_temp_config(configs, verbose=True):
    """
    Temporarily set the sysctl configs.
    Given configs must follow format:
        Key=variable; Value=variable_value when evaluated as a string
    """
    assert isinstance(configs, dict)
    assert isinstance(verbose, bool)

    # TODO: interactive confirm before proceeding...
    # TODO: sysctl -w each config


def process_persistent_config(configs, verbose=True):
    """
    Set sysctl configs that persist throughout system reboots.
    Given configs must follow format:
        Key=variable; Value=variable_value when evaluated as a string
    """
    assert isinstance(configs, dict)
    assert isinstance(verbose, bool)

    # TODO: interactive confirm before proceeding...
    # TODO: see if sysctl -w write to `sysctl_path` otherwise:
    # TODO: write each config to config file if is not present, first filter out all comments (ez to do)....


def _parse_args():
    parser = argparse.ArgumentParser(description='== Optimize OS for running a node ==',
                                     usage="auto-node [OPTIONS]",
                                     formatter_class=RawTextHelpFormatter, add_help=False)
    parser.add_argument('-h', '--help', action='help', default=argparse.SUPPRESS,
                        help='Show this help message and exit')
    parser.add_argument("target", help=f"Desired thing to optimize. Options:\n"
                                       f"* kernel\t Tune kernel for running a node.\n"
                                       f"* network\t Tune network settings for running a node.\n"
                                       f"* restore\t Restore sysctl config to previous config (if available).")
    parser.add_argument("--save", action="store_true", help="Save tuning between system restarts.")
    parser.add_argument("--quiet", action="store_true", help="Do not print anything.")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    assert args.target in params, f"given target {args.target} not in {params}"
    assert os.geteuid() == 0, f"must be ran as root! Try running command with 'sudo' in front of it."

    if args.target == "restore":
        latest_saved_time = restore_existing_config()
        if not args.quiet:
            restored_readable_time = datetime.datetime.fromtimestamp(latest_saved_time).strftime('%c')
            common.log(f"Restored sysctl config from {restored_readable_time}")
            common.log(f"{Typgpy.OKGREEN}Successfully restored sysctl config!{Typgpy.ENDC}")
        exit(0)

    if args.save:
        save_existing_config()
        if not args.quiet:
            common.log(f"{Typgpy.OKGREEN}Successfully saved existing sysctl config!{Typgpy.ENDC}")

    if args.target == "kernel":
        if not args.quiet:
            common.log(f"{Typgpy.HEADER}== Tuning kernel =={Typgpy.ENDC}")
        if args.save:
            process_persistent_config(kernel_tunes, verbose=not args.quiet)
        else:
            process_temp_config(kernel_tunes, verbose=not args.quiet)
    if args.target == "network":
        if not args.quiet:
            common.log(f"{Typgpy.HEADER}== Tuning network =={Typgpy.ENDC}")
            if args.save:
                process_persistent_config(network_tuning, verbose=not args.quiet)
                process_persistent_config(network_security, verbose=not args.quiet)
            else:
                process_temp_config(network_tuning, verbose=not args.quiet)
                process_temp_config(network_security, verbose=not args.quiet)
    if not args.quiet:
        common.log(f"{Typgpy.OKGREEN}Finished tuning!{Typgpy.ENDC}")
