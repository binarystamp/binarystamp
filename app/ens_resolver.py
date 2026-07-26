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
import re
import time
from flask import Blueprint, request, jsonify
from eth_abi import encode, decode
from eth_utils import keccak

log = logging.getLogger('binarystamp.ens')

ens_bp = Blueprint('ens', __name__)

SUBGRAPH_URL = os.getenv('SUBGRAPH_URL', '')

# Reverse resolution ("what name does this address claim?") lives on Ethereum
# mainnet, not on Base, so it needs its own provider.
MAINNET_RPC_URL = os.getenv('MAINNET_RPC_URL', '')
REVERSE_CACHE_TTL = int(os.getenv('ENS_REVERSE_CACHE_TTL', '3600'))
# Misses expire far sooner than hits. web3's ens.name() returns None both when
# an address genuinely has no name and when the forward check it runs happens
# to fail, so a transient RPC blip is indistinguishable from "no record" — and
# caching that for an hour makes a real name vanish for an hour.
REVERSE_MISS_TTL = int(os.getenv('ENS_REVERSE_MISS_TTL', '300'))

EVM_ADDRESS = re.compile(r'^0x[0-9a-fA-F]{40}$')

_mainnet = None
_reverse_cache = {}  # lowercased address -> (name or None, expires_at)

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


def unwrap_resolve_calldata(calldata):
    """Pull (name, inner calldata) out of a CCIP-Read request body.

    Two shapes reach us. The usual one is selector-prefixed, as produced by
    abi.encodeWithSelector(resolve.selector, name, data). The deployed
    BinaryStampResolver instead sends a bare abi.encode(name, data) with no
    selector, so accept both rather than silently failing on our own resolver.
    """
    resolve_selector = keccak(text='resolve(bytes,bytes)')[:4]

    if calldata[:4] == resolve_selector:
        body = calldata[4:]
    else:
        body = calldata

    dns_name, inner_data = decode(['bytes', 'bytes'], body)
    return decode_dns_name(dns_name), inner_data


# The deployed resolver points clients at /api/ens, so serve the gateway there
# as well as at the canonical /api/ens/resolve.
@ens_bp.route('/ens', methods=['POST'])
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

    try:
        name, inner_data = unwrap_resolve_calldata(calldata)
        selector = inner_data[:4]
        inner_calldata = inner_data
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


def mainnet_web3():
    """Lazily connect to Ethereum mainnet for reverse resolution."""
    global _mainnet
    if _mainnet is None:
        if not MAINNET_RPC_URL:
            return None
        from web3 import Web3
        _mainnet = Web3(Web3.HTTPProvider(MAINNET_RPC_URL, request_kwargs={'timeout': 15}))
    return _mainnet


def reverse_ens(address):
    """Primary ENS name for an address, or None.

    web3's ens.name() forward-resolves the candidate name and discards it
    unless it points back at the same address. That check matters: a reverse
    record is set by its own owner, so without it anyone could claim to be
    vitalik.eth.

    Results are cached, misses included, because a lookup costs two mainnet
    calls and most addresses have no name at all — but misses expire much
    sooner, since one may only mean the network was briefly unhappy.
    """
    key = address.lower()
    cached = _reverse_cache.get(key)
    if cached and cached[1] > time.time():
        return cached[0]

    w3 = mainnet_web3()
    if w3 is None:
        raise RuntimeError('MAINNET_RPC_URL is not configured')

    from web3 import Web3
    name = w3.ens.name(Web3.to_checksum_address(address))

    ttl = REVERSE_CACHE_TTL if name else REVERSE_MISS_TTL
    _reverse_cache[key] = (name, time.time() + ttl)
    return name


@ens_bp.route('/ens/reverse/<address>', methods=['GET'])
def reverse_lookup(address):
    """Resolve an address to its primary ENS name, if it has set one."""
    if not EVM_ADDRESS.match(address):
        return jsonify({'error': 'Expected a 20-byte EVM address'}), 400

    if not MAINNET_RPC_URL:
        return jsonify({'address': address, 'name': None,
                        'error': 'Mainnet RPC not configured'}), 503

    try:
        name = reverse_ens(address)
    except Exception as e:
        log.error(f'Reverse ENS lookup failed for {address}: {e}')
        return jsonify({'address': address, 'name': None, 'error': str(e)}), 502

    return jsonify({'address': address, 'name': name})


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


# A SHA-256 hex digest is 64 characters, and DNS wire-format labels are capped
# at 63 bytes (RFC 1035), so a hex label can never be resolved by an ENS client.
# Base36 packs the same 256 bits into 50 characters, which fits.
BASE36_DIGITS = '0123456789abcdefghijklmnopqrstuvwxyz'
BASE36_LABEL_LENGTH = 50  # ceil(256 / log2(36))

HEX_64 = re.compile(r'^[0-9a-f]{64}$')
BASE36_LABEL = re.compile(r'^[0-9a-z]{%d}$' % BASE36_LABEL_LENGTH)


def hash_to_label(file_hash):
    """Encode a 32-byte hash as the 50-character base36 label for its name."""
    value = int(file_hash, 16)
    if value < 0 or value >= 1 << 256:
        raise ValueError('hash out of range')

    out = ''
    while value:
        value, remainder = divmod(value, 36)
        out = BASE36_DIGITS[remainder] + out

    # Fixed width, so a hash with leading zero bytes cannot encode short and
    # collide with a different hash.
    return out.rjust(BASE36_LABEL_LENGTH, '0')


def label_to_hash(label):
    """Decode a subdomain label back to a 0x file hash, or None.

    Accepts the base36 form used in real ENS names, and plain hex for the
    app's own lookup endpoint, which is not bound by the DNS label limit.
    """
    if not label:
        return None

    label = label.lower()
    if label.startswith('0x'):
        label = label[2:]

    if HEX_64.match(label):
        return '0x' + label

    # Checked before the digits-only stamp-number case: a base36 label can be
    # all digits, and length is what tells them apart.
    if BASE36_LABEL.match(label):
        value = int(label, 36)
        if value >= 1 << 256:
            return None
        return '0x' + format(value, '064x')

    return None


def resolve_owner(label):
    """Resolve a label to an owner address."""
    if not label:
        return None

    import requests as req

    file_hash = label_to_hash(label)
    if file_hash is None:
        if label.isdigit():
            return resolve_owner_by_number(int(label))
        return None

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
    file_hash = label_to_hash(label)
    by_number = file_hash is None and label.isdigit()

    if not file_hash and not by_number:
        return ''

    if by_number:
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

        if by_number:
            stamp = data.get('stamp', {})
        else:
            lookup = data.get('fileHashLookup', {})
            stamps = lookup.get('stamps', [])
            stamp = stamps[0] if stamps else {}

        return stamp.get(key, '')
    except Exception as e:
        log.error(f'Text resolve failed: {e}')
    return ''
