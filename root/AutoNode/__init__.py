import os

from pyhmy import cli

from .common import (
    default_endpoint,
    node_script_source,
    default_cli_passphrase,
    node_sh_log_dir,
    directory_lock,
    env
)

from .blockchain import (
    get_metadata,
    get_validator_information,
    get_sharding_structure,
    get_latest_header,
    get_current_epoch,
    get_block_by_number,
    get_latest_headers,
    get_staking_epoch
)

from .node import (
    start_node,
    wait_for_node_response,
    assert_no_bad_blocks
)

from .validator import (
    add_bls_key_to_validator,
    create_new_validator
)

from .util import (
    process_passphrase,
    input_with_print
)

os.makedirs(node_sh_log_dir, exist_ok=True)
cli.environment.update(cli.download("/root/bin/hmy", replace=False))
cli.set_binary("/root/bin/hmy")
