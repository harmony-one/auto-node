import json

import requests

from .common import (
    node_config
)

_headers = {
    'Content-Type': 'application/json'
}


def get_current_epoch(endpoint=node_config['endpoint']):
    return int(get_latest_header(endpoint)["epoch"])


def get_latest_header(endpoint=node_config['endpoint']):
    payload = json.dumps({"id": "1", "jsonrpc": "2.0",
                          "method": "hmy_latestHeader",
                          "params": []})
    response = requests.request('POST', endpoint, headers=_headers, data=payload, allow_redirects=False, timeout=3)
    return json.loads(response.content)["result"]


def get_latest_headers(endpoint=node_config['endpoint']):
    payload = json.dumps({"id": "1", "jsonrpc": "2.0",
                          "method": "hmy_getLatestChainHeaders",
                          "params": []})
    response = requests.request('POST', endpoint, headers=_headers, data=payload, allow_redirects=False, timeout=3)
    return json.loads(response.content)["result"]


def get_sharding_structure(endpoint=node_config['endpoint']):
    payload = json.dumps({"id": "1", "jsonrpc": "2.0",
                          "method": "hmy_getShardingStructure",
                          "params": []})
    response = requests.request('POST', endpoint, headers=_headers, data=payload, allow_redirects=False, timeout=3)
    return json.loads(response.content)["result"]


def get_block_by_number(number, endpoint=node_config['endpoint']):
    payload = json.dumps({"id": "1", "jsonrpc": "2.0",
                          "method": "hmyv2_getBlockByNumber",
                          "params": [number, {}]})
    response = requests.request('POST', endpoint, headers=_headers, data=payload, allow_redirects=False, timeout=3)
    return json.loads(response.content)["result"]


def get_staking_epoch(endpoint=node_config['endpoint']):
    payload = json.dumps({"id": "1", "jsonrpc": "2.0",
                          "method": "hmy_getNodeMetadata",
                          "params": []})
    response = requests.request('POST', endpoint, headers=_headers, data=payload, allow_redirects=False, timeout=3)
    body = json.loads(response.content)
    return int(body["result"]["chain-config"]["staking-epoch"])


def get_validator_information(address, endpoint=node_config['endpoint']):
    payload = json.dumps({"id": "1", "jsonrpc": "2.0",
                          "method": "hmy_getValidatorInformation",
                          "params": [address]})
    response = requests.request('POST', endpoint, headers=_headers, data=payload, allow_redirects=False, timeout=3)
    body = json.loads(response.content)
    if 'error' in body:
        raise RuntimeError(str(body['error']))
    return body['result']


def get_metadata(endpoint=node_config['endpoint']):
    payload = json.dumps({"id": "1", "jsonrpc": "2.0",
                          "method": "hmy_getNodeMetadata",
                          "params": []})
    response = requests.request('POST', endpoint, headers=_headers, data=payload, allow_redirects=False, timeout=3)
    return json.loads(response.content)["result"]
