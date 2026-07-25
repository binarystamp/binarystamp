"""
ENS CCIP-Read (EIP-3668) Offchain Resolver Gateway for BinaryStamp.

Resolves:
  <hash>.binarystamp.eth  -> owner address + metadata
  <number>.binarystamp.eth -> owner by stamp filing number

This implements the offchain lookup protocol that ENS uses to resolve
names via an external gateway instead of on-chain storage.
"""

import os
import json
import hashlib
import logging
from flask import Blueprint, request, jsonify
from eth_abi import encode, decode
from eth_utils import keccak

log = logging.getLogger('binarystamp.ens')

ens_bp = Blueprint('ens', __name__)

SUBGRAPH_URL = os.getenv('SUBGRAPH_URL', '')

# EIP-3668 CCIP-Read interface
# The resolver contract calls this gateway with encoded calldata

# Supported resolve functions (matching ENS resolver interface)
# addr(bytes32 node) -> address
ADDR_SELECTOR = keccak(text='addr(bytes32)')[:4]
# text(bytes32 node, string key) -> string
TEXT_SELECTOR = keccak(text='text(bytes32,string)')[:4]


def namehash(name):
    """Compute ENS namehash for a domain name."""
    if not name:
        return b'\x00' * 32
    labels = name.split('.')
    node = b'\x00' * 32
    for label in reversed(labels):
        label_hash = keccak(text=label)
        node = keccak(node + label_hash)
    return node


def parse_subdomain(name):
    """Extract subdomain label from <label>.binarystamp.eth"""
    if name.endswith('.binarystamp.eth'):
        return name.replace('.binarystamp.eth', '')
    return None


@ens_bp.route('/ens/resolve', methods=['POST'])
def ccip_resolve():
    """
    CCIP-Read gateway endpoint.
    Called by ENS resolver contract with encoded calldata.
    Returns ABI-encoded response.
    """
    data = request.json or {}
    sender = data.get('sender', '')
    calldata = bytes.fromhex(data.get('data', '')[2:]) if data.get('data') else b''

    if len(calldata) < 4:
        return jsonify({'error': 'Invalid calldata'}), 400

    selector = calldata[:4]

    # Decode the resolve(bytes name, bytes data) call
    # The outer call is resolve(bytes,bytes) which wraps the inner call
    try:
        # Try to decode as resolve(bytes,bytes)
        resolve_selector = keccak(text='resolve(bytes,bytes)')[:4]
        if calldata[:4] == resolve_selector:
            dns_name, inner_data = decode(['bytes', 'bytes'], calldata[4:])
            name = decode_dns_name(dns_name)
            selector = inner_data[:4]
            inner_calldata = inner_data
        else:
            name = ''
            inner_calldata = calldata
    except Exception:
        name = ''
        inner_calldata = calldata

    label = parse_subdomain(name) if name else None

    if selector == ADDR_SELECTOR:
        # addr(bytes32) -> resolve to owner address
        owner = resolve_owner(label)
        if owner:
            result = encode(['address'], [owner])
            return jsonify({'data': '0x' + result.hex()})
        return jsonify({'data': '0x' + encode(['address'], ['0x' + '0' * 40]).hex()})

    if selector == TEXT_SELECTOR:
        # text(bytes32, string) -> resolve text records
        try:
            _, key = decode(['bytes32', 'string'], inner_calldata[4:])
        except Exception:
            key = 'description'
        value = resolve_text(label, key)
        result = encode(['string'], [value])
        return jsonify({'data': '0x' + result.hex()})

    return jsonify({'error': 'Unsupported function'}), 400


@ens_bp.route('/ens/resolve/<name>', methods=['GET'])
def resolve_name(name):
    """Simple HTTP resolve endpoint for the frontend."""
    label = parse_subdomain(name) if '.binarystamp.eth' in name else name

    if not label:
        return jsonify({'resolved': False, 'error': 'Invalid name'})

    owner = resolve_owner(label)
    if owner:
        return jsonify({
            'resolved': True,
            'name': name,
            'owner': owner,
            'description': resolve_text(label, 'description'),
            'walrusBlobId': resolve_text(label, 'walrusBlobId'),
        })

    return jsonify({'resolved': False, 'name': name})


def decode_dns_name(data):
    """Decode DNS wire format name to string."""
    labels = []
    i = 0
    while i < len(data):
        length = data[i]
        if length == 0:
            break
        i += 1
        labels.append(data[i:i + length].decode('utf-8'))
        i += length
    return '.'.join(labels)


def resolve_owner(label):
    """Resolve a label to an owner address."""
    if not label:
        return None

    import requests as req

    # Check if label is a file hash
    file_hash = label
    if not file_hash.startswith('0x'):
        # Could be a stamp number
        if label.isdigit():
            return resolve_owner_by_number(int(label))
        file_hash = '0x' + file_hash

    if not SUBGRAPH_URL:
        return None

    query = '''
    query($id: ID!) {
        fileHashLookup(id: $id) {
            latestOwner
        }
    }
    '''
    try:
        resp = req.post(
            SUBGRAPH_URL,
            json={'query': query, 'variables': {'id': file_hash.lower()}},
            timeout=10
        )
        data = resp.json().get('data', {})
        lookup = data.get('fileHashLookup')
        if lookup:
            return lookup['latestOwner']
    except Exception as e:
        log.error(f'Subgraph query failed: {e}')
    return None


def resolve_owner_by_number(number):
    """Resolve a stamp number to an owner address."""
    if not SUBGRAPH_URL:
        return None

    import requests as req
    query = '''
    query($id: ID!) {
        stamp(id: $id) {
            owner
        }
    }
    '''
    try:
        resp = req.post(
            SUBGRAPH_URL,
            json={'query': query, 'variables': {'id': str(number)}},
            timeout=10
        )
        data = resp.json().get('data', {})
        stamp = data.get('stamp')
        if stamp:
            return stamp['owner']
    except Exception as e:
        log.error(f'Subgraph query failed: {e}')
    return None


def resolve_text(label, key):
    """Resolve a text record for a label."""
    if not label or not SUBGRAPH_URL:
        return ''

    import requests as req
    file_hash = label if label.startswith('0x') else '0x' + label

    if label.isdigit():
        query = '''
        query($id: ID!) {
            stamp(id: $id) {
                description
                walrusBlobId
                metadataHash
                owner
                timestamp
            }
        }
        '''
        var_id = label
    else:
        query = '''
        query($id: ID!) {
            fileHashLookup(id: $id) {
                stamps(first: 1, orderBy: timestamp, orderDirection: desc) {
                    description
                    walrusBlobId
                    metadataHash
                    owner
                    timestamp
                }
            }
        }
        '''
        var_id = file_hash.lower()

    try:
        resp = req.post(
            SUBGRAPH_URL,
            json={'query': query, 'variables': {'id': var_id}},
            timeout=10
        )
        data = resp.json().get('data', {})

        if label.isdigit():
            stamp = data.get('stamp', {})
        else:
            lookup = data.get('fileHashLookup', {})
            stamps = lookup.get('stamps', [])
            stamp = stamps[0] if stamps else {}

        return stamp.get(key, '')
    except Exception as e:
        log.error(f'Text resolve failed: {e}')
    return ''
