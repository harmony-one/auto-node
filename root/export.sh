#!/bin/bash

echo "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"
echo "Validator address: $(cat /.val_address)"
echo "BLS public keys: $(cat /.bls_keys)"
echo "Network: $(cat /.network)"
echo "Beacon chain endpoint: $(cat /.beacon_endpoint)"
echo "Validator config: $(cat /root/validator_config.json)"
echo "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"
echo ""