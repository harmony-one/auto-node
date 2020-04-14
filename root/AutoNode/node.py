import os
import stat
import subprocess
import json
import time

import requests

from pyhmy import (
    Typgpy
)

from .common import (
    directory_lock,
    node_script_source,
    node_sh_log_dir,
    env
)
from .blockchain import (
    get_latest_header,
)

node_sh_out_path = f"{node_sh_log_dir}/out.log"
node_sh_err_path = f"{node_sh_log_dir}/err.log"


def start_node(bls_keys_path, network, clean=False):
    directory_lock.acquire()
    os.chdir("/root/node")
    if os.path.isfile("/root/node/node.sh"):
        os.remove("/root/node/node.sh")
    r = requests.get(node_script_source)
    with open("node.sh", 'w') as f:
        node_sh = r.content.decode()
        # WARNING: Hack until node.sh is changed for auto-node.
        node_sh = node_sh.replace("save_pass_file=false", 'save_pass_file=true')
        node_sh = node_sh.replace("sudo", '')
        f.write(node_sh)
    st = os.stat("node.sh")
    os.chmod("node.sh", st.st_mode | stat.S_IEXEC)
    node_args = ["./node.sh", "-N", network, "-z", "-f", bls_keys_path, "-M"]
    if clean:
        node_args.append("-c")
    directory_lock.release()
    with open(node_sh_out_path, 'w+') as fo:
        with open(node_sh_err_path, 'w+') as fe:
            print(f"{Typgpy.HEADER}Starting node!{Typgpy.ENDC}")
            return subprocess.Popen(node_args, env=env, stdout=fo, stderr=fe).pid


# TODO: Add timeout option
def wait_for_node_response(endpoint, verbose=True):
    alive = False
    while not alive:
        try:
            get_latest_header(endpoint)
            alive = True
        except (json.JSONDecodeError, json.decoder.JSONDecodeError, requests.exceptions.ConnectionError,
                RuntimeError, KeyError, AttributeError):
            time.sleep(.5)
    if verbose:
        print(f"{Typgpy.HEADER}[!] {endpoint} is alive!{Typgpy.ENDC}")


def assert_no_bad_blocks():
    files = [x for x in os.listdir('/root/node/latest') if x.endswith(".log")]
    if files:
        log_path = f"/root/node/latest/{files[0]}"
        assert not has_bad_block(log_path), f"`BAD BLOCK` present in {log_path}"


def has_bad_block(log_file_path):
    assert os.path.isfile(log_file_path)
    try:
        with open(log_file_path, 'r', encoding='utf8') as f:
            for line in f:
                line = line.rstrip()
                if "## BAD BLOCK ##" in line:
                    return True
    except UnicodeDecodeError:
        print(f"{Typgpy.WARNING}WARNING: failed to read `{log_file_path}` to check for bad block{Typgpy.ENDC}")
    return False
