#!/usr/bin/env python3
import os
import argparse
import subprocess
import pickle
import time
import datetime
from argparse import RawTextHelpFormatter

kernel_tuning = {
    # Increase size of file handles and node cache
    "fs.file-max": 2097152,
    # Do less swapping
    "vm.swappiness": 10,
    "vm.dirty_ratio": 60,
    "vm.dirty_background_ratio": 2,
    # Sets the time before the kernel considers migrating a proccess to another core
    "kernel.sched_migration_cost_ns": 5000000
}

network_security = {
    # Number of times SYNACKs for passive TCP connection.
    "net.ipv4.tcp_synack_retries": 2,
    # Allowed local port range
    "net.ipv4.ip_local_port_range": "2000 65535",
    # Protect Against TCP Time-Wait
    "net.ipv4.tcp_rfc1337": 1,
    # Control Syncookies
    "net.ipv4.tcp_syncookies": 1,
    # Decrease the time default value for tcp_fin_timeout connection
    "net.ipv4.tcp_fin_timeout": 15,
    # Decrease the time default value for connections to keep alive
    "net.ipv4.tcp_keepalive_time": 300,
    "net.ipv4.tcp_keepalive_probes": 5,
    "net.ipv4.tcp_keepalive_intvl": 15,
}

network_tuning = {
    # Default Socket Receive Buffer
    "net.core.rmem_default": 31457280,
    # Maximum Socket Receive Buffer
    "net.core.rmem_max": 33554432,
    # Default Socket Send Buffer
    "net.core.wmem_default": 31457280,
    # Maximum Socket Send Buffer
    "net.core.wmem_max": 33554432,
    # Increase number of incoming connections
    "net.core.somaxconn": 8096,
    # Increase number of incoming connections backlog
    "net.core.netdev_max_backlog": 65536,
    # Increase the maximum amount of option memory buffers
    "net.core.optmem_max": 25165824,
    "net.ipv4.tcp_max_syn_backlog": 8192,
    # Increase the maximum total buffer-space allocatable
    # This is measured in units of pages (4096 bytes)
    "net.ipv4.tcp_mem": "786432 1048576 26777216",
    "net.ipv4.udp_mem": "65536 131072 262144",
    # Increase the read-buffer space allocatable
    "net.ipv4.tcp_rmem": "8192 87380 33554432",
    "net.ipv4.udp_rmem_min": 16384,
    # Increase the write-buffer-space allocatable
    "net.ipv4.tcp_wmem": "8192 65536 33554432",
    "net.ipv4.udp_wmem_min": 16384,
    # Increase the tcp-time-wait buckets pool size to prevent simple DOS attacks
    "net.ipv4.tcp_max_tw_buckets": 1440000,
    "net.ipv4.tcp_tw_reuse": 1,
    "net.ipv4.tcp_fastopen": 3,
    "net.ipv4.tcp_window_scaling": 1
}

sysctl_path = "/etc/sysctl.conf"
saved_config = {}  # Keys = time.time(): Value = saved config as a string


def _load_existing_config(saved_config_path):
    saved_config.clear()
    if os.path.exists(saved_config_path):
        with open(saved_config_path, 'rb') as f:
            saved_config.update(pickle.load(f))


def _save_existing_config(saved_config_path):
    if os.path.isfile(saved_config_path):
        subprocess.check_call(["sudo", "chattr", "-i", saved_config_path], env=os.environ)
    try:
        with open(saved_config_path, 'wb') as f:
            pickle.dump(saved_config, f)
    finally:
        subprocess.check_call(["sudo", "chattr", "+i", saved_config_path], env=os.environ)


def save_existing_config(saved_config_path):
    """
    Saves files contents at `sysctl_path` to pickle file in
    AutoNode directory and makes saves pickle file immutable.

    Returns time of stored config.
    """
    old_config_string = ''
    if os.path.isfile(sysctl_path):
        with open(sysctl_path, 'r', encoding='utf8') as f:
            old_config_string = f.read()
    _load_existing_config(saved_config_path)
    saved_time = time.time()
    saved_config[saved_time] = old_config_string
    _save_existing_config(saved_config_path)
    return saved_time


def restore_existing_config(saved_config_path):
    """
    Restore existing config file in last known.

    Returns time of restored config.
    """
    _load_existing_config(saved_config_path)
    if not saved_config:
        print("No sysctl config to restore from...")
        exit(-1)
    latest_saved_config_key = sorted(saved_config.keys(), reverse=True)[0]
    latest_saved_config = saved_config[latest_saved_config_key]
    restored_readable_time = datetime.datetime.fromtimestamp(latest_saved_config_key).strftime('%c')

    print(f"'{sysctl_path}' to be restored from: {restored_readable_time}")
    print('='*100)
    print(latest_saved_config)
    print('='*100)
    prompt = "Revert to this sysctl.conf? [Y/n]\n>"
    if input(prompt).lower() not in {'yes', 'y'}:
        raise SystemExit("Abandoned config restore..")

    with open(sysctl_path, 'w', encoding='utf8') as f:
        f.write(latest_saved_config)
    subprocess.check_call(["sudo", "sysctl", "-p"], env=os.environ)
    del saved_config[latest_saved_config_key]
    _save_existing_config(saved_config_path)
    return latest_saved_config_key


def process_temp_config(configs, verbose=True):
    """
    Temporarily set the sysctl configs.
    Given configs must follow format:
        Key=variable; Value=variable_value when evaluated as a string
    """
    assert isinstance(configs, dict)
    assert isinstance(verbose, bool)

    print(f"\nVariables to set:\n")
    max_char_count = len(max(configs.keys(), key=lambda e: len(e)))
    formatted_row = f"{{:<{max_char_count}}}\t{{:<30}}"
    print(formatted_row.format("Variable", "Value"))
    print(formatted_row.format("--------", "-----"))
    for key, value in configs.items():
        print(formatted_row.format(key, value))
    print("")
    prompt = "Temporarily set the sysctl variables (until system reboot)? [Y/n]\n>"
    if input(prompt).lower() not in {'yes', 'y'}:
        return

    for key, value in configs.items():
        subprocess.check_call(["sysctl", "-w", f"{key}={str(value)}"])

    if verbose:
        print(f"Successfully set sysctl variables!")


def process_persistent_config(configs, verbose=True):
    """
    Set sysctl configs that persist throughout system reboots.
    Given configs must follow format:
        Key=variable; Value=variable_value when evaluated as a string
    """
    assert isinstance(configs, dict)
    assert isinstance(verbose, bool)

    print(f"\nVariables to set:\n")
    max_char_count = len(max(configs.keys(), key=lambda e: len(e)))
    formatted_row = f"{{:<{max_char_count}}}\t{{:<30}}"
    print(formatted_row.format("Variable", "Value"))
    print(formatted_row.format("--------", "-----"))
    for key, value in configs.items():
        print(formatted_row.format(key, value))
    print("")
    prompt = "Set persisting (remain after system reboot) sysctl variables? [Y/n]\nNote that this can be reverted.\n>"
    if input(prompt).lower() not in {'yes', 'y'}:
        return

    lines_in_sysctl_path = []
    if os.path.exists(sysctl_path):
        with open(sysctl_path, 'r') as f:
            lines_in_sysctl_path = f.readlines()
    lines_currently_in_sysctl_path = set(lines_in_sysctl_path)

    for key, value in configs.items():
        line = f"{key}={value}\n"
        if line not in lines_currently_in_sysctl_path:
            lines_in_sysctl_path.append(line)

    with open(sysctl_path, 'w') as f:
        f.write(''.join(lines_in_sysctl_path))

    subprocess.check_call(["sudo", "sysctl", "-p"], env=os.environ)

    if verbose:
        print(f"Successfully set sysctl variables!")


def _parse_args():
    parser = argparse.ArgumentParser(description='== Optimize OS for running a node ==',
                                     usage="auto-node [OPTIONS]",
                                     formatter_class=RawTextHelpFormatter, add_help=False)
    parser.add_argument('-h', '--help', action='help', default=argparse.SUPPRESS,
                        help='Show this help message and exit')
    parser.add_argument("target", help=f"Desired thing to optimize. Options:\n"
                                       f"* kernel\t Tune kernel for running a node.\n"
                                       f"* network\t Tune network settings for running a node.\n"
                                       f"* restore\t Restore sysctl config to previous config (if available).",
                        choices=['kernel', 'network', 'restore'])
    parser.add_argument("--save", action="store_true", help="Save tuning between system restarts.")
    parser.add_argument("--quiet", action="store_true", help="Do not print anything.")
    parser.add_argument("--saved-sysctl-path", default="/var/saved-sysctl.conf.p",
                        help="Path to saved sysctl config(s) path as a python pickle file.\n"
                             "Handled by AutoNode by default.")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    assert os.geteuid() == 0, f"must be ran as root! Try running command with 'sudo' in front of it."

    if args.target == "restore":
        latest_saved_time = restore_existing_config(args.saved_sysctl_path)
        if not args.quiet:
            restored_readable_time = datetime.datetime.fromtimestamp(latest_saved_time).strftime('%c')
            print(f"Restored sysctl config from {restored_readable_time}")
            print(f"Successfully restored sysctl config!")
        exit(0)

    if args.save:
        save_existing_config(args.saved_sysctl_path)
        if not args.quiet:
            print(f"Successfully saved existing sysctl config!")

    if args.target == "kernel":
        if not args.quiet:
            print(f"== Tuning kernel ==")
        if args.save:
            process_persistent_config(kernel_tuning, verbose=not args.quiet)
        else:
            process_temp_config(kernel_tuning, verbose=not args.quiet)
    if args.target == "network":
        if not args.quiet:
            print(f"== Tuning network ==")
            if args.save:
                process_persistent_config(network_tuning, verbose=not args.quiet)
                process_persistent_config(network_security, verbose=not args.quiet)
            else:
                process_temp_config(network_tuning, verbose=not args.quiet)
                process_temp_config(network_security, verbose=not args.quiet)
    if not args.quiet:
        print(f"Finished tuning!")
