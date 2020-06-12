from cryptography.fernet import InvalidToken

from .common import (
    node_config,
    save_node_config
)


class ResetNode(Exception):
    """
    The only exception that triggers a hard reset.
    """

    def __init__(self, *args, clean=False):
        node_config['clean'] = clean
        save_node_config()
        super(ResetNode, self).__init__(*args)


class InvalidWalletPassphrase(InvalidToken):
    """
    Exception raised if passphrase is invalid
    """