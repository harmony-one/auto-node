import os
import stat
import subprocess
import json
import sys
import time

import requests

from pyhmy import (
    cli,
    Typgpy
)

from .common import (
    validator_config,
    node_script_source,
    node_sh_log_dir,
    node_config,
    saved_wallet_pass_path,
    node_dir,
    bls_key_dir
)
from .blockchain import (
    get_latest_header,
)

node_sh_out_path = f"{node_sh_log_dir}/out.log"
node_sh_err_path = f"{node_sh_log_dir}/err.log"


def start(clean=False):
    os.chdir(node_dir)
    if os.path.isfile(f"{node_dir}/node.sh"):
        os.remove(f"{node_dir}/node.sh")
    r = requests.get(node_script_source)
    with open("node.sh", 'w') as f:
        node_sh = r.content.decode()
        # WARNING: Hack until node.sh is changed for auto-node.
        node_sh = node_sh.replace("save_pass_file=false", 'save_pass_file=true')
        f.write(node_sh)
    st = os.stat("node.sh")
    os.chmod("node.sh", st.st_mode | stat.S_IEXEC)
    node_args = ["./node.sh", "-N", node_config["network"], "-z", "-f", bls_key_dir, "-M", "-S"]
    if clean:
        node_args.append("-c")
    with open(node_sh_out_path, 'a') as fo:
        with open(node_sh_err_path, 'a') as fe:
            print(f"{Typgpy.HEADER}Starting node!{Typgpy.ENDC}")
            return subprocess.Popen(node_args, env=os.environ, stdout=fo, stderr=fe).pid


def wait_for_node_response(endpoint, verbose=True, tries=float("inf"), sleep=0.5):
    alive = False
    count = 0
    while not alive:
        count += 1
        try:
            get_latest_header(endpoint)
            alive = True
        except (json.decoder.JSONDecodeError, requests.exceptions.ConnectionError,
                RuntimeError, KeyError, AttributeError):
            if count > tries:
                raise RuntimeError(f"{endpoint} did not respond in {count} attempts")
            if verbose:
                sys.stdout.write(f"\rWaiting for {endpoint} to respond, tried {count} times")
                sys.stdout.flush()
            time.sleep(sleep)
    if verbose:
        print(f"\n{Typgpy.HEADER}[!] {endpoint} is alive!{Typgpy.ENDC}")


def assert_no_bad_blocks():
    if os.path.isdir(f"{node_dir}/latest"):
        files = [x for x in os.listdir(f"{node_dir}/latest") if x.endswith(".log")]
        if files:
            log_path = f"{node_dir}/latest/{files[-1]}"
            assert not has_bad_block(log_path), f"`BAD BLOCK` present in {log_path}"


def has_bad_block(log_file_path):
    assert os.path.isfile(log_file_path)
    try:
        with open(log_file_path, 'r', encoding='utf8') as f:
            for line in f:
                line = line.rstrip()
                if "## BAD BLOCK ##" in line:
                    return True
    except (UnicodeDecodeError, IOError):
        print(f"{Typgpy.WARNING}WARNING: failed to read `{log_file_path}` to check for bad block{Typgpy.ENDC}")
    return False


def check_and_activate(epos_status_msg):
    if "not eligible" in epos_status_msg or "not signing" in epos_status_msg:
        print(f"{Typgpy.FAIL}Node not active, reactivating...{Typgpy.ENDC}")
        response = cli.single_call(f"hmy staking edit-validator --validator-addr {validator_config['validator-addr']} "
                                   f"--active true --node {node_config} --passphrase-file {saved_wallet_pass_path} ")
        print(f"{Typgpy.OKGREEN} Edit-validator response: {response}{Typgpy.ENDC}")
