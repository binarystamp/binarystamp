"""CCIP-Read gateway.

Two things here were broken in a way that only showed up through a real ENS
client, because both our own API and our own tests bypassed the gateway:

  - the deployed resolver points clients at /api/ens, not /api/ens/resolve
  - it sends a bare abi.encode(name, data) with no function selector, while
    the gateway only understood the selector-prefixed form

Together they meant <name>.binarystamp.eth never resolved through ENS at all.
"""

import os
import sys

import pytest
from eth_abi import decode, encode
from eth_utils import keccak

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import ens_resolver
from app import app

OWNER = '0x29810A9c1F4ba5854bB8D6732580D7D7c6eDcbC0'
ADDR_SELECTOR = keccak(text='addr(bytes32)')[:4]
TEXT_SELECTOR = keccak(text='text(bytes32,string)')[:4]
RESOLVE_SELECTOR = keccak(text='resolve(bytes,bytes)')[:4]

GATEWAY_PATHS = ['/api/ens/resolve', '/api/ens']


@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def dns_encode(name):
    out = b''
    for label in name.split('.'):
        out += bytes([len(label)]) + label.encode()
    return out + b'\x00'


def inner_addr_call(node=b'\x00' * 32):
    return ADDR_SELECTOR + node


def bare_calldata(name, inner):
    """What the deployed resolver sends: abi.encode(name, data), no selector."""
    return encode(['bytes', 'bytes'], [dns_encode(name), inner])


def prefixed_calldata(name, inner):
    """The conventional form: selector + abi.encode(name, data)."""
    return RESOLVE_SELECTOR + bare_calldata(name, inner)


def post(client, path, calldata):
    return client.post(path, json={'sender': OWNER, 'data': '0x' + calldata.hex()})


# ============ Calldata shapes ============

def test_unwraps_bare_encoding():
    name, inner = ens_resolver.unwrap_resolve_calldata(
        bare_calldata('3.binarystamp.eth', inner_addr_call()))
    assert name == '3.binarystamp.eth'
    assert inner[:4] == ADDR_SELECTOR


def test_unwraps_selector_prefixed_encoding():
    name, inner = ens_resolver.unwrap_resolve_calldata(
        prefixed_calldata('3.binarystamp.eth', inner_addr_call()))
    assert name == '3.binarystamp.eth'
    assert inner[:4] == ADDR_SELECTOR


# ============ Both gateway paths ============

@pytest.mark.parametrize('path', GATEWAY_PATHS)
@pytest.mark.parametrize('encoder', [bare_calldata, prefixed_calldata],
                         ids=['bare', 'selector-prefixed'])
def test_addr_resolves_owner(client, monkeypatch, path, encoder):
    monkeypatch.setattr(ens_resolver, 'resolve_owner', lambda label: OWNER)

    resp = post(client, path, encoder('3.binarystamp.eth', inner_addr_call()))
    assert resp.status_code == 200

    returned = decode(['address'], bytes.fromhex(resp.get_json()['data'][2:]))[0]
    assert returned.lower() == OWNER.lower()


@pytest.mark.parametrize('path', GATEWAY_PATHS)
def test_unknown_name_resolves_to_zero_address(client, monkeypatch, path):
    monkeypatch.setattr(ens_resolver, 'resolve_owner', lambda label: None)

    resp = post(client, path, bare_calldata('9999.binarystamp.eth', inner_addr_call()))
    assert resp.status_code == 200

    returned = decode(['address'], bytes.fromhex(resp.get_json()['data'][2:]))[0]
    assert int(returned, 16) == 0


@pytest.mark.parametrize('path', GATEWAY_PATHS)
def test_label_is_extracted_from_the_dns_name(client, monkeypatch, path):
    """The label drives the lookup, so it has to survive DNS decoding."""
    seen = []
    monkeypatch.setattr(ens_resolver, 'resolve_owner',
                        lambda label: seen.append(label) or OWNER)

    post(client, path, bare_calldata('3.binarystamp.eth', inner_addr_call()))
    assert seen == ['3']


@pytest.mark.parametrize('path', GATEWAY_PATHS)
def test_text_record_is_returned(client, monkeypatch, path):
    monkeypatch.setattr(ens_resolver, 'resolve_text', lambda label, key: 'a design doc')

    inner = TEXT_SELECTOR + encode(['bytes32', 'string'], [b'\x00' * 32, 'description'])
    resp = post(client, path, bare_calldata('3.binarystamp.eth', inner))
    assert resp.status_code == 200

    value = decode(['string'], bytes.fromhex(resp.get_json()['data'][2:]))[0]
    assert value == 'a design doc'


@pytest.mark.parametrize('path', GATEWAY_PATHS)
def test_short_calldata_is_rejected(client, path):
    assert client.post(path, json={'sender': OWNER, 'data': '0x00'}).status_code == 400


@pytest.mark.parametrize('path', GATEWAY_PATHS)
def test_gateway_is_post_only(client, path):
    assert client.get(path).status_code in (404, 405)


# ============ Label length ============

def test_sha256_label_exceeds_the_dns_limit():
    """A 64-char hex label cannot be DNS-encoded, so <hash>.binarystamp.eth
    is unreachable through any standard ENS client. Recorded so the
    limitation is not rediscovered as a gateway bug."""
    file_hash = 'd3ab18b78082d3b4f768779c3dbd163155cfbfbbbd7eaeb8da6497745f401274'
    assert len(file_hash) == 64
    assert len(file_hash) > 63          # RFC 1035 label limit
    assert len('0x' + file_hash) == 66  # worse with the 0x prefix
