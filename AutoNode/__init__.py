import os
import sys
import json
import warnings

from pyhmy import (
    cli,
    Typgpy
)

from .common import (
    harmony_dir,
    node_dir,
    node_sh_log_dir,
    bls_key_dir,
    saved_validator_path,
    imported_bls_pass_file_dir,
    imported_wallet_pass_file_dir,
    cli_bin_path,
    saved_node_path,
    validator_config,
    node_config
)


if sys.version_info.major < 3:
    warnings.simplefilter("always", DeprecationWarning)
    warnings.warn(
        DeprecationWarning(
            "`AutoNode` does not support Python 2. Please use Python 3."
        )
    )
    warnings.resetwarnings()

if sys.platform.startswith('win32') or sys.platform.startswith('cygwin'):
    warnings.simplefilter("always", ImportWarning)
    warnings.warn(
        ImportWarning(
            "`AutoNode` does not work on Windows or Cygwin."
        )
    )
    warnings.resetwarnings()

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
    os.makedirs(imported_bls_pass_file_dir, exist_ok=True)
    os.makedirs(imported_wallet_pass_file_dir, exist_ok=True)

    cli.environment.update(cli.download(cli_bin_path, replace=False))
    cli.set_binary(cli_bin_path)

    if os.path.isfile(saved_validator_path):
        try:
            with open(saved_validator_path, 'r', encoding='utf8') as f:
                imported_val_config = json.load(f)
        except (json.decoder.JSONDecodeError, IOError) as e:
            raise RuntimeError(f"Could not import validator config from {saved_validator_path}") from e
        validator_config.update(imported_val_config)
    else:
        print(f"{Typgpy.WARNING}No validator config was found at {saved_validator_path}. "
              f"Using default config.{Typgpy.ENDC}")

    if os.path.isfile(saved_node_path):
        try:
            with open(saved_node_path, 'r', encoding='utf8') as f:
                imported_node_config = json.load(f)
        except (json.decoder.JSONDecodeError, IOError, PermissionError) as e:
            raise RuntimeError(f"Could not import save node info from {saved_node_path}") from e
        node_config.update(imported_node_config)


_init()

