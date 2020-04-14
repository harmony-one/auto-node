import os
from threading import Lock

default_endpoint = "https://api.s0.os.hmny.io/"
node_script_source = "https://raw.githubusercontent.com/harmony-one/harmony/master/scripts/node.sh"
default_cli_passphrase = ""  # WARNING: assumption made about hmy CLI
node_sh_log_dir = "/root/node/node_sh_logs"  # WARNING: assumption made on auto_node.sh
directory_lock = Lock()
env = os.environ
