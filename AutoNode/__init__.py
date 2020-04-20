import os
import sys
import json
import warnings
import requests
import logging

from pyhmy import (
    cli,
    Typgpy
)

from .common import (
    log,
    msg_tag,
    harmony_dir,
    node_dir,
    node_sh_log_dir,
    bls_key_dir,
    saved_validator_path,
    imported_wallet_pass_file_dir,
    cli_bin_path,
    saved_node_path,
    validator_config,
    node_config,
)

if sys.version_info.major < 3:
    warnings.simplefilter("always", DeprecationWarning)
    warnings.warn(
        DeprecationWarning(
            "`AutoNode` does not support Python 2. Please use Python 3."
        )
    )
    warnings.resetwarnings()
    exit(-1)

if sys.platform.startswith('win32') or sys.platform.startswith('cygwin'):
    warnings.simplefilter("always", ImportWarning)
    warnings.warn(
        ImportWarning(
            "`AutoNode` does not work on Windows or Cygwin. Try using WSL."
        )
    )
    warnings.resetwarnings()
    exit(-1)

if sys.platform.startswith('darwin'):
    warnings.simplefilter("always", ImportWarning)
    warnings.warn(
        ImportWarning(
            "`AutoNode.node` does not work on MacOS."
        )
    )
    warnings.resetwarnings()


def _init():
    os.makedirs(harmony_dir, exist_ok=True)
    os.makedirs(node_dir, exist_ok=True)
    os.makedirs(node_sh_log_dir, exist_ok=True)
    os.makedirs(bls_key_dir, exist_ok=True)
    os.makedirs(imported_wallet_pass_file_dir, exist_ok=True)

    log_handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(f'{msg_tag} %(message)s')
    log_handler.setFormatter(formatter)
    logging.getLogger('AutoNode').handlers = []
    logging.getLogger('AutoNode').addHandler(log_handler)
    logging.getLogger('AutoNode').setLevel(logging.DEBUG)

    try:
        # TODO: implement logic to check for latest version of CLI and download if out of date.
        cli.environment.update(cli.download(cli_bin_path, replace=False))
        cli.set_binary(cli_bin_path)
    except requests.exceptions.RequestException as e:
        log(f"{Typgpy.FAIL}Request error: {e}. Exiting.{Typgpy.ENDC}")
        raise SystemExit(e)

    try:  # Config file that should exist on setup
        with open(saved_validator_path, 'r', encoding='utf8') as f:
            imported_val_config = json.load(f)
            validator_config.update(imported_val_config)
    except (json.decoder.JSONDecodeError, IOError, PermissionError) as e:
        log(f"{Typgpy.WARNING}Could not import validator config from {saved_validator_path}. Error: {e}\n"
            f"Using default config: {json.dumps(validator_config, indent=4)}{Typgpy.ENDC}")

    if os.path.isfile(saved_node_path):  # Internal file that could not exist.
        try:
            with open(saved_node_path, 'r', encoding='utf8') as f:
                imported_node_config = json.load(f)
                node_config.update(imported_node_config)
        except (json.decoder.JSONDecodeError, IOError, PermissionError) as e:
            raise SystemExit(f"Could not import saved node config from {saved_node_path}") from e


_init()
