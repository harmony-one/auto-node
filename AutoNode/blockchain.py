import json

import requests

from .common import (
    node_config
)


# TODO: move this to library collection of exceptions...
class RpcError(RuntimeError):
    """Exception raised when RPC call returns an exception"""

    def __init__(self, *args, **kwargs):
        pass


def rpc_request(method, params=None, endpoint=node_config['endpoint'], timeout=60):
    """
    RPC the blockchain and return whatever the RPC returned (including errors).
    """
    params = [] if params is None else params
    if not isinstance(params, list):
        raise TypeError(f"{params} must be of type list for RPC call.")
    try:
        headers = {'Content-Type': 'application/json'}
        payload = json.dumps({"id": "1", "jsonrpc": "2.0", "method": method, "params": params})
        response = requests.request('POST', endpoint, headers=headers, data=payload,
                                    allow_redirects=True, timeout=timeout)
        return json.loads(response.content)
    except json.decoder.JSONDecodeError as e:
        raise requests.exceptions.InvalidSchema(f"JSON parse error.") from e


def get_current_epoch(endpoint=node_config['endpoint'], timeout=60):
    return int(get_latest_header(endpoint, timeout=timeout)["epoch"])


def get_latest_header(endpoint=node_config['endpoint'], timeout=60):
    body = rpc_request("hmy_latestHeader", endpoint=endpoint, timeout=timeout)
    if 'error' in body:
        raise RpcError(str(body['error']))
    return body["result"]


def get_latest_headers(endpoint=node_config['endpoint'], timeout=60):
    body = rpc_request("hmy_getLatestChainHeaders", endpoint=endpoint, timeout=timeout)
    if 'error' in body:
        raise RpcError(str(body['error']))
    return body["result"]


def get_sharding_structure(endpoint=node_config['endpoint'], timeout=60):
    body = rpc_request("hmy_getShardingStructure", endpoint=endpoint, timeout=timeout)
    if 'error' in body:
        raise RpcError(str(body['error']))
    return body["result"]


def get_block_by_number(number, endpoint=node_config['endpoint'], timeout=60):
    body = rpc_request("hmy_getBlockByNumber", params=[hex(number), False], endpoint=endpoint, timeout=timeout)
    if 'error' in body:
        raise RpcError(str(body['error']))
    return body["result"]


def get_staking_epoch(endpoint=node_config['endpoint'], timeout=60):
    body = rpc_request("hmy_getNodeMetadata", endpoint=endpoint, timeout=timeout)
    if 'error' in body:
        raise RpcError(str(body['error']))
    return int(body["result"]["chain-config"]["staking-epoch"])


def get_validator_information(address, endpoint=node_config['endpoint'], timeout=60):
    body = rpc_request("hmy_getValidatorInformation", params=[address], endpoint=endpoint, timeout=timeout)
    if 'error' in body:
        raise RpcError(str(body['error']))
    return body['result']


def get_all_validator_addresses(endpoint=node_config['endpoint'], timeout=60):
    body = rpc_request("hmy_getAllValidatorAddresses", endpoint=endpoint, timeout=timeout)
    if 'error' in body:
        raise RpcError(str(body['error']))
    return body['result']


def get_metadata(endpoint=node_config['endpoint'], timeout=60):
    body = rpc_request("hmy_getNodeMetadata", endpoint=endpoint, timeout=timeout)
    if 'error' in body:
        raise RpcError(str(body['error']))
    return body["result"]
