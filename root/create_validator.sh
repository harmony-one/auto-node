#!/bin/bash
python3 -u /root/create_validator.py "$(cat /.bls_keys)" "$(cat /.bls_passphrase)" "$(cat /.beacon_endpoint)"