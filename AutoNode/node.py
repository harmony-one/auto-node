"""
Library for all things related to running a Harmony node with AutoNode.
"""

import glob
import json
import logging
import os
import shutil
import stat
import subprocess
import time

import pyhmy.rpc.exceptions as rpc_exception
import requests
from pyhmy import (
    blockchain,
    cli,
    Typgpy
)

from .common import (
    log,
    node_script_source,
    node_sh_log_dir,
    node_config,
    node_dir,
    bls_key_dir,
    harmony_dir
)
from .util import (
    input_with_print,
    get_simple_rotating_log_handler,
    is_bls_file,
)

node_sh_out_path = f"{node_sh_log_dir}/out.log"
node_sh_err_path = f"{node_sh_log_dir}/err.log"

log_path = f"{harmony_dir}/autonode_node.log"

rclone_space_buffer = 5 * 2 ** 30  # 5GB in bytes
rclone_config = "harmony"


def _node_clean(verbose=True):
    log_dir = f"{node_dir}/latest"
    backup_log_dir = f"{node_dir}/backup_logs/{time.strftime('%Y/%m/%d/%H')}"
    os.makedirs(backup_log_dir, exist_ok=True)
    try:
        if os.path.isdir(log_dir):
            if verbose:
                log(f"{Typgpy.WARNING}[!] Moving {log_dir} to {backup_log_dir} {Typgpy.ENDC}")
            if os.path.isdir(backup_log_dir):
                shutil.rmtree(backup_log_dir)  # Should never happen, always keep latest.
            shutil.move(log_dir, backup_log_dir)
        for directory in filter(lambda e: os.path.isdir(e), os.listdir(node_dir)):
            if directory.startswith("harmony_db_") or directory.startswith(".dht"):
                path = os.path.join(node_dir, directory)
                if verbose:
                    log(f"{Typgpy.WARNING}[!] Removing {path} {Typgpy.ENDC}")
                shutil.rmtree(path)
    except shutil.Error as e:
        raise SystemExit(e)


def _rclone(rclone_sync_dir, shard, verbose=True):
    db_dir = f"{node_dir}/harmony_db_{shard}"
    node_sh_rclone_err_path = f"{node_sh_log_dir}/rclone_err_{shard}.log"
    node_sh_rclone_out_path = f"{node_sh_log_dir}/rclone_out_{shard}.log"

    try:
        # Assumption made on installed rclone config.
        rclone_path = f'harmony://pub.harmony.one/{rclone_sync_dir}/harmony_db_{shard}'
        if verbose:
            log(f"{Typgpy.WARNING}rclone harmony_db_{shard} from {rclone_path} in progress...{Typgpy.ENDC}")
        with open(node_sh_rclone_out_path, 'w') as fo:
            with open(node_sh_rclone_err_path, 'w') as fe:
                return subprocess.Popen(['rclone', 'sync', '-P', rclone_path, db_dir],
                                        env=os.environ, stdout=fo, stderr=fe)
    except OSError as e:
        if verbose:
            log(f"{Typgpy.FAIL}Failed to rclone shard {shard} db, error {e}{Typgpy.ENDC}")
            log(f"{Typgpy.WARNING}Removing shard {shard} db if it exists{Typgpy.ENDC}")
            if os.path.isdir(db_dir):
                shutil.rmtree(db_dir)


def _rclone_space_required(rclone_sync_dir, shard):
    rclone_path = f'{rclone_config}://pub.harmony.one/{rclone_sync_dir}/harmony_db_{shard}'
    try:
        space_output = subprocess.check_output(['rclone', 'size', rclone_path, '--json'], env=os.environ)
        return int(json.loads(space_output.decode('utf8'))['bytes'])
    except (subprocess.CalledProcessError, json.decoder.JSONDecodeError, KeyError) as e:
        log(f"{Typgpy.WARNING}Failed to get rclone db size requirement, error {e}{Typgpy.ENDC}")
        return 0


def _rclone_db(shard, verbose=True):
    # WARNING: rclone sync directory naming convention may change in the future
    if node_config['archival']:
        rclone_sync_dir = node_config['network'] + '.archival'
    else:
        rclone_sync_dir = node_config['network'] + '.min'

    _, _, free_space = shutil.disk_usage(os.environ['HOME'])
    free_space = free_space + rclone_space_buffer

    rclone_processes = []
    if shard == 0:
        required_space = _rclone_space_required(rclone_sync_dir, shard)
        if required_space == 0:
            log(f"{Typgpy.WARNING}Fast-sync db not available.\n"
                f"Skipping rclone shard {shard}...{Typgpy.ENDC}")
            return
        if required_space > free_space:
            log(f"{Typgpy.WARNING}[!] Insufficient disk space. Required: {required_space}, Free: {free_space} \n"
                f"Skipping fast sync...{Typgpy.ENDC}")
            log(f"{Typgpy.WARNING}[!] Suggest increasing disk space before running node!{Typgpy.ENDC}")
            return
        rclone_processes.append(_rclone(rclone_sync_dir, shard, verbose=verbose))
    else:
        required_beacon_space = _rclone_space_required(rclone_sync_dir, 0)
        required_shard_space = _rclone_space_required(rclone_sync_dir, shard)
        total_required_space = required_beacon_space + required_shard_space
        if total_required_space > free_space:
            log(f"{Typgpy.WARNING}[!] Insufficient disk space. Required: {total_required_space}, Free: {free_space} \n"
                f"Skipping fast sync...{Typgpy.ENDC}")
            log(f"{Typgpy.WARNING}[!] Suggest increasing disk space before running node!{Typgpy.ENDC}")
            return
        if required_beacon_space == 0:
            log(f"{Typgpy.WARNING}Fast-sync db not available.\n"
                f"Skipping rclone shard 0...{Typgpy.ENDC}")
        else:
            rclone_processes.append(_rclone(rclone_sync_dir, 0, verbose=verbose))
        if required_shard_space == 0:
            log(f"{Typgpy.WARNING}Fast-sync db not available.\n"
                f"Skipping rclone shard {shard}...{Typgpy.ENDC}")
        else:
            rclone_processes.append(_rclone(rclone_sync_dir, shard, verbose=verbose))

    for p in rclone_processes:
        p.wait()

    if all(p.returncode == 0 for p in rclone_processes):
        if verbose:
            log(f"{Typgpy.OKGREEN}rclone done!{Typgpy.ENDC}")
    else:
        failed_db_list = glob.glob(os.path.join(node_dir, 'harmony_db_*'))
        for db in failed_db_list:
            db_shard = os.path.basename(db).split('_')[-1]
            log(f'{Typgpy.FAIL}[!] Failed to rclone shard {db_shard} db.{Typgpy.ENDC}')
            log(f'{Typgpy.WARNING}Check {os.path.join(node_sh_log_dir, f"rclone_err_{db_shard}.log")}\n'
                f'Removing {db}.{Typgpy.ENDC}')
            shutil.rmtree(db)
        raise SystemExit('Fast sync failed.')


def _get_node_shard():
    """
    Returns node shard based on config.
    Returns None if 0 or > 1 shards are derived from the node's BLS keys.
    """
    key_shards = []
    if not node_config['public-bls-keys']:
        log(f"{Typgpy.WARNING}No saved BLS keys for node!{Typgpy.ENDC}")
    for bls_key in node_config['public-bls-keys']:
        try:
            key_shards.append(json.loads(cli.single_call(['hmy', 'utility', 'shard-for-bls', bls_key,
                                                          '--node', f'{node_config["endpoint"]}']))['shard-id'])
        except json.decoder.JSONDecodeError:
            log(f'{Typgpy.WARNING}[!] Failed to get shard for bls key {bls_key}!{Typgpy.ENDC}')
    if not key_shards:
        return None
    assert len(
        set(key_shards)) == 1, f"Node BLS keys can only be for 1 shard. BLS keys: {node_config['public-bls-keys']}"
    return key_shards[0]


def start(auto=False, verbose=True):
    """
    Start the harmony process and return the PID.

    Note that process is running after function return.
    """
    if subprocess.call(["pgrep", "harmony"], env=os.environ) == 0:
        raise RuntimeError("Harmony process is already running, can only start 1 node on machine with AutoNode.")
    old_logging_handlers = logging.getLogger('AutoNode').handlers.copy()
    logging.getLogger('AutoNode').addHandler(get_simple_rotating_log_handler(log_path))
    log(f"{Typgpy.HEADER}Starting node...{Typgpy.ENDC}")
    if not auto:
        log(f"{Typgpy.WARNING}You are starting a Harmony Node manually, "
            f"this is not recommended, continue? [Y]/n{Typgpy.ENDC}")
        if input_with_print("> ") not in {'Y', 'y', 'yes', 'Yes'}:
            raise SystemExit()
    assert_valid_bls_key_directory()
    os.chdir(node_dir)
    if os.path.isfile(f"{node_dir}/node.sh"):
        os.remove(f"{node_dir}/node.sh")
    try:
        r = requests.get(node_script_source, timeout=30, verify=True)
        with open("node.sh", 'w') as f:
            node_sh = r.content.decode()
            # WARNING: Hack until node.sh is changed for auto-node.
            node_sh = node_sh.replace("save_pass_file=false", 'save_pass_file=true')
            f.write(node_sh)
    except requests.exceptions.RequestException as e:
        raise SystemExit(e)
    st = os.stat("node.sh")
    os.chmod("node.sh", st.st_mode | stat.S_IEXEC)
    node_args = ["./node.sh", "-N", node_config["network"], "-z", "-f", bls_key_dir, "-M", "-S"]
    if node_config['clean']:
        if verbose:
            log(f"{Typgpy.WARNING}[!] Cleaning up old files before starting node.{Typgpy.ENDC}")
        _node_clean(verbose=verbose)
    if node_config['fast-sync']:
        if verbose:
            log(f'{Typgpy.WARNING}[!] Fast syncing before starting node.{Typgpy.ENDC}')
        shard = _get_node_shard()
        if shard is not None:
            _rclone_db(shard, verbose=verbose)
        else:
            log(f'{Typgpy.WARNING}[!] Unable to determine node shard.\n'
                f'Skipping fast sync...{Typgpy.ENDC}')
    if node_config['archival']:
        if verbose:
            log(f"{Typgpy.WARNING}[!] Starting node in archival mode.{Typgpy.ENDC}")
        node_args.append("-A")
    if node_config['no-download']:
        harmony_binary = os.path.realpath(os.path.join(node_dir, 'harmony'))
        if os.path.exists(harmony_binary):
            if 'static' in subprocess.check_output(['file', harmony_binary], env=os.environ).decode('utf8'):
                if verbose:
                    log(f"{Typgpy.WARNING}[!] Starting node with existing harmony binary.{Typgpy.ENDC}")
                node_args.append("-D")
            else:
                log(f"{Typgpy.WARNING}[!] Provided harmony binary is not statically linked. "
                    f"Path: {harmony_binary}{Typgpy.ENDC}")
                raise SystemExit(f"Harmony binary not statically linked. Path: {harmony_binary}")
        else:
            if verbose:
                log(f"{Typgpy.WARNING}[!] Starting node with released harmony binary.{Typgpy.ENDC}")
    with open(node_sh_out_path, 'w') as fo:
        with open(node_sh_err_path, 'w') as fe:
            if verbose:
                log(f"{Typgpy.HEADER}Starting node!{Typgpy.ENDC}")
            logging.getLogger('AutoNode').handlers = old_logging_handlers  # Reset logger to old handlers
            return subprocess.Popen(node_args, env=os.environ, stdout=fo, stderr=fe).pid


# TODO (low prio): create stream load printer for multiple waits_for_node_response
def wait_for_node_response(endpoint, verbose=True, tries=float("inf"), sleep=0.5):
    count = 0
    while True:
        count += 1
        try:
            blockchain.get_latest_header(endpoint=endpoint)
            break
        except (rpc_exception.RequestsError, rpc_exception.RequestsTimeoutError,
                rpc_exception.RPCError):
            if count > tries:
                raise TimeoutError(f"{endpoint} did not respond in {count} attempts (~{sleep * count} seconds)")
            if verbose and count % 10 == 0:
                log(f"{Typgpy.WARNING}Waiting for {endpoint} to respond, tried {count} times "
                    f"(~{sleep * count} seconds waited so far){Typgpy.ENDC}")
            time.sleep(sleep)
    if verbose:
        log(f"{Typgpy.HEADER}[!] {endpoint} is alive!{Typgpy.ENDC}")


def assert_no_invalid_blocks():
    if os.path.isdir(f"{node_dir}/latest"):
        files = glob.glob(f"{node_dir}/latest/zero*.log")
        if files:
            log_path = files[-1]
            assert not has_invalid_block(
                log_path), f"`invalid merkle root` present in {log_path}, restart AutoNode with clean option"


def is_signing(count=1500):
    """
    Read the last `count` lines and check for signing logs.
    """
    if os.path.isdir(f"{node_dir}/latest"):
        files = glob.glob(f"{node_dir}/latest/zero*.log")
        if files:
            log_path = files[-1]
            content = subprocess.check_output(["tail", "-n", str(count), str(log_path)], env=os.environ).decode().split(
                "\n")
            for line in content:
                line = line.rstrip()
                if "BINGO" in line or "HOORAY" in line:
                    return True
    return False


def has_invalid_block(log_file_path):
    assert os.path.isfile(log_file_path), f"{log_file_path} is not a file"
    try:
        with open(log_file_path, 'r', encoding='utf8') as f:
            for line in f:
                line = line.rstrip()
                if "invalid merkle root" in line:
                    return True
    except (UnicodeDecodeError, IOError):
        log(f"{Typgpy.WARNING}WARNING: failed to read `{log_file_path}` to check for invalid block{Typgpy.ENDC}")
    return False


def assert_valid_bls_key_directory():
    """
    Asserts that the BLS keys directory contains the BLS keys for the
    given node config.

    Note that this must match EXACTLY.

    Will raise assertion error if one BLS key is missing OR
    if there is 1 BLS key more than what is in the node config.
    """
    bls_keys = list(filter(lambda e: is_bls_file(e, '.key'), os.listdir(bls_key_dir)))
    bls_pass = list(filter(lambda e: is_bls_file(e, '.pass'), os.listdir(bls_key_dir)))

    assert len(bls_keys) == len(bls_pass), f"number of BLS keys and BLS pass files must be equal in {bls_key_dir}."
    bls_pub_keys = set(x.replace('.key', '') for x in bls_keys)
    assert len(bls_pub_keys) == len(bls_keys), f"sanity check: cannot contain duplicate BLS keys in {bls_key_dir}"
    found_keys_count = len(bls_pub_keys)

    for key in bls_pass:
        bls_key = key.replace('.pass', '')
        assert bls_key in bls_pub_keys, f"got BLS pass for {bls_key}, but BLS key not found in {bls_key_dir}"

    conf_keys_count = len(node_config['public-bls-keys'])
    if conf_keys_count != found_keys_count:
        raise AssertionError(f"number of configured BLS keys ({conf_keys_count}) not equal to number of BLS keys "
                             f"keys ({found_keys_count}) in {bls_key_dir}")
    for key in node_config['public-bls-keys']:
        assert key in bls_pub_keys, f"configured BLS key {key} not found in {bls_key_dir}"


def assert_started(timeout=60, do_log=False):
    """
    Assert the node has started within the given timeout.
    Node that rclone does NOT count towards timeout.
    """
    has_informed_rclone = False
    start_time = time.time()
    while time.time() - start_time < timeout:
        if subprocess.call(["pgrep", "rclone"], env=os.environ, stdout=subprocess.DEVNULL) == 0:
            timeout += 1
            if not has_informed_rclone and do_log:
                log(f"{Typgpy.WARNING}Fast-sync (rclone) is in progress...{Typgpy.ENDC}")
                has_informed_rclone = True
        elif subprocess.call(["pgrep", "harmony"], env=os.environ, stdout=subprocess.DEVNULL) == 0:
            if do_log:
                log(f"{Typgpy.OKGREEN}Harmony node is running...{Typgpy.ENDC}")
            return
        time.sleep(1)
    if do_log:
        log(f"{Typgpy.FAIL}Harmony node is NOT running!{Typgpy.ENDC}")
    raise AssertionError("Node failed to start")
