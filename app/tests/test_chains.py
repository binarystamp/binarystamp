"""The frontend encodes EVM calldata by hand (frontend/chains.js).

These tests run that JavaScript and compare it against eth_abi, so a mistake in
the hand-rolled encoder cannot silently ship a malformed transaction.
"""

import json
import os
import shutil
import subprocess

import pytest
from eth_abi import encode
from eth_utils import keccak

FRONTEND = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'frontend')
CHAINS_JS = os.path.join(FRONTEND, 'chains.js')

pytestmark = pytest.mark.skipif(
    shutil.which('node') is None, reason='node is required to exercise chains.js'
)


def run_js(script):
    result = subprocess.run(
        ['node', '--input-type=module', '-e', script],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        pytest.fail(f'node failed: {result.stderr[-2000:]}')
    return result.stdout.strip()


def js_encode_stamp(cases):
    script = f"""
    import {{encodeStampCall}} from '{CHAINS_JS}';
    const cases = {json.dumps(cases)};
    console.log(JSON.stringify(cases.map(c => encodeStampCall(...c))));
    """
    return json.loads(run_js(script))


def py_encode_stamp(file_hash, metadata_hash, blob, description):
    selector = keccak(text='stamp(bytes32,bytes32,string,string)')[:4]
    body = encode(
        ['bytes32', 'bytes32', 'string', 'string'],
        [bytes.fromhex(file_hash[2:]), bytes.fromhex(metadata_hash[2:]), blob, description],
    )
    return '0x' + (selector + body).hex()


STAMP_CASES = [
    ['0x' + 'ab' * 32, '0x' + 'cd' * 32, 'blobABC', 'hello world'],
    ['0x' + '11' * 32, '0x' + '00' * 32, '', ''],                       # empty strings
    ['0x' + 'ff' * 32, '0x' + '22' * 32, 'x' * 32, 'héllo → 世界'],      # multi-byte utf-8
    ['0x' + '01' * 32, '0x' + '02' * 32, 'a' * 31, 'b' * 33],           # word boundaries
    ['0x' + '0a' * 32, '0x' + '0b' * 32, 'a' * 64, 'c' * 1],
]


def test_stamp_calldata_matches_eth_abi():
    actual = js_encode_stamp(STAMP_CASES)
    expected = [py_encode_stamp(*c) for c in STAMP_CASES]
    assert actual == expected


def test_transfer_calldata_matches_eth_abi():
    file_hash = '0x' + 'ab' * 32
    owner = '0x5969D7558d3409ac70ebdF24063AeC7257d0aCe3'
    script = f"""
    import {{encodeTransferCall}} from '{CHAINS_JS}';
    console.log(encodeTransferCall('{file_hash}', '{owner}'));
    """
    selector = keccak(text='transferStamp(bytes32,address)')[:4]
    expected = '0x' + (selector + encode(
        ['bytes32', 'address'], [bytes.fromhex('ab' * 32), owner]
    )).hex()
    assert run_js(script) == expected


def test_selectors_match_deployed_abi():
    """chains.js hardcodes selectors; they must match the deployed contract."""
    abi_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), 'contracts', 'evm', 'abi.json'
    )
    with open(abi_path) as f:
        abi = json.load(f)
    if isinstance(abi, dict):
        abi = abi.get('abi', abi)

    signatures = {
        entry['name']: entry['name'] + '(' + ','.join(i['type'] for i in entry['inputs']) + ')'
        for entry in abi if entry.get('type') == 'function'
    }

    with open(CHAINS_JS) as f:
        source = f.read()

    for name, expected_const in [('stamp', 'SELECTOR_STAMP'),
                                 ('transferStamp', 'SELECTOR_TRANSFER')]:
        selector = keccak(text=signatures[name])[:4].hex()
        assert f"{expected_const} = '{selector}'" in source, (
            f'{expected_const} does not match {signatures[name]} -> {selector}'
        )
