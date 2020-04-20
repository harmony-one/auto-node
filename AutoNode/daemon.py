import os
import subprocess
import time

from pyhmy import (
    Typgpy,
)

from .common import (
    saved_node_path,
    saved_validator_path,
    saved_wallet_pass_path,
    bls_key_dir,
    node_config,
    log
)
from .node import (
    start as node_start
)
from .validator import (
    setup as validator_setup
)
from .monitor import (
    start as start_monitor,
    ResetNode
)


class Daemon:
    """Main AutoNode daemon logic"""

    name = f"{os.environ['USER']}-autonoded"
    services = {
        "node",
        "node_recovered",
        "monitor"
    }

    @staticmethod
    def _assert_perms_for_auto_reset():
        if subprocess.call("sudo -n true", shell=True, env=os.environ) != 0:
            raise SystemExit(
                f"{Typgpy.FAIL}User {os.environ['USER']} does not have sudo privileges without password.\n "
                f"For auto-reset option, user must have said privilege.\n "
                f"Node still running and/or syncing. To have status monitoring, rerun/reinitialize "
                f"AutoNode without auto-reset. {Typgpy.ENDC}")

    @staticmethod
    def validate_config():
        required_files = [
            saved_node_path,
            saved_validator_path,
            saved_wallet_pass_path
        ]
        if any(not os.path.isfile(p) for p in required_files):
            raise SystemExit(f"AutoNode was not initialized properly. "
                             f"One or more files are missing: {required_files}")

        files_in_bls_dir = set(os.listdir(bls_key_dir))
        for bls_key in node_config['public-bls-keys']:
            key_file, pass_file = f"{bls_key}.key", f"{bls_key}.pass"
            if key_file not in files_in_bls_dir:
                raise SystemExit(f"{bls_key} in node config, but {key_file} not found in "
                                 f"BLS key directory at {bls_key_dir}")
            if pass_file not in files_in_bls_dir:
                raise SystemExit(f"{bls_key} in node config, but {pass_file} not found in "
                                 f"BLS key directory at {bls_key_dir}")

    def __init__(self, service):
        if service not in self.services:
            raise ValueError(f"{service} is not a valid service. Valid services: {self.services}")
        self.node_sh_pid = None
        self.service = service
        if node_config['auto-reset']:
            self._assert_perms_for_auto_reset()

    def __del__(self):
        if self.node_sh_pid is not None:
            subprocess.call(f"kill -2 {self.node_sh_pid}", shell=True, env=os.environ)

    def start_node(self):
        if not self.service.startswith("node"):
            raise SystemExit(f"Attempted to start node service as {self.service} service.")
        self.node_sh_pid = node_start(auto=True, verbose=True)
        if self.service == "node_recovered":  # only automatically create validator if in recovered service
            validator_setup(recover_interaction=True)

    def start_monitor(self):
        if self.service != "monitor":
            raise SystemExit(f"Attempted to start monitor service as {self.service} service.")
        count = 0
        while True:
            count += 1
            try:
                log(f"{Typgpy.HEADER}[!] Starting monitor, restart number {count}{Typgpy.ENDC}")
                # Invariant: Monitor will raise a ResetNode exception to trigger a node reset,
                # otherwise it will gracefully exit to restart monitor
                start_monitor()
                if not node_config['auto-reset']:
                    break
            except ResetNode:  # All other errors should blow up
                log(f"{Typgpy.FAIL}Resetting Node{Typgpy.ENDC}")
                self.stop_all_daemons(ignore_self=True)
                time.sleep(5)  # wait for node shutdown
                daemon_name = f"{self.name}@node_recovered.service"
                log(f"{Typgpy.WARNING}Starting daemon {daemon_name}{Typgpy.ENDC}")
                subprocess.check_call(f"sudo systemctl start {daemon_name}", shell=True, env=os.environ)
        self.stop_all_daemons(ignore_self=True)
        log(f"{Typgpy.WARNING}Terminating monitor...{Typgpy.ENDC}")

    def start(self):
        if self.service == 'monitor':
            self.start_monitor()
        else:
            self.start_node()

    def stop_all_daemons(self, ignore_self=True):
        for service in self.services:
            if ignore_self and service == self.service:
                continue
            daemon_name = f"{self.name}@{service}.service"
            log(f"{Typgpy.WARNING}Stopping daemon {daemon_name}{Typgpy.ENDC}")
            command = f"sudo systemctl stop {daemon_name}"
            subprocess.check_call(command, shell=True, env=os.environ)  # let it blow up if error.

    def block(self):
        log("Blocking process...")
        if self.service == 'monitor' and not node_config['auto-reset']:
            return
        subprocess.call("tail -f /dev/null", shell=True, env=os.environ)
