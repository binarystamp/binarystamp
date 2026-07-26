"""Subdomain label encoding.

A hex label cannot be used: 64 characters against a 63-byte DNS limit. Base36
carries the same 256 bits in 50 characters, which fits, so that is the form
real ENS names use. Stamp numbers still work as short labels.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import ens_resolver
from ens_resolver import BASE36_LABEL_LENGTH, hash_to_label, label_to_hash

HASH = '0xd3ab18b78082d3b4f768779c3dbd163155cfbfbbbd7eaeb8da6497745f401274'
LABEL = '59x6n7u66bsd6bzlsnpk2izswbpf7vljhtguldnk8adldrpkdw'


# ============ Encoding ============

def test_known_hash_encodes_to_known_label():
    assert hash_to_label(HASH) == LABEL


def test_label_fits_the_dns_limit():
    assert len(LABEL) == BASE36_LABEL_LENGTH
    assert BASE36_LABEL_LENGTH <= 63


@pytest.mark.parametrize('hex_hash', [
    '0x' + '00' * 32,                    # zero
    '0x' + '00' * 31 + '01',             # leading zero bytes
    '0x' + 'ff' * 32,                    # maximum
    HASH,
    '0x' + '0f' * 32,
])
def test_round_trip(hex_hash):
    assert label_to_hash(hash_to_label(hex_hash)) == hex_hash


@pytest.mark.parametrize('hex_hash', ['0x' + '00' * 32, '0x' + '00' * 31 + '01', HASH])
def test_labels_are_fixed_width(hex_hash):
    """Variable width would let a leading-zero hash collide with another."""
    assert len(hash_to_label(hex_hash)) == BASE36_LABEL_LENGTH


def test_distinct_hashes_give_distinct_labels():
    a = hash_to_label('0x' + '00' * 31 + '01')
    b = hash_to_label('0x' + '00' * 30 + '0100')
    assert a != b


# ============ Decoding ============

def test_hex_label_still_decodes():
    """The app's own lookup endpoint is not bound by the DNS limit."""
    assert label_to_hash(HASH) == HASH
    assert label_to_hash(HASH[2:]) == HASH


def test_uppercase_label_decodes():
    assert label_to_hash(LABEL.upper()) == HASH


def test_all_digit_label_is_a_hash_not_a_stamp_number():
    """A base36 label can be all digits; length is what separates the cases."""
    label = hash_to_label('0x' + '00' * 31 + '01')
    assert label.isdigit()
    assert label_to_hash(label) == '0x' + '00' * 31 + '01'


def test_short_number_is_not_a_hash():
    assert label_to_hash('3') is None


def test_out_of_range_label_is_rejected():
    """36**50 exceeds 2**256, so some 50-character labels are not hashes."""
    assert label_to_hash('z' * BASE36_LABEL_LENGTH) is None


@pytest.mark.parametrize('label', ['', 'not-a-label', 'zz', 'x' * 49, 'x' * 51,
                                   '!' * BASE36_LABEL_LENGTH])
def test_invalid_labels_are_rejected(label):
    assert label_to_hash(label) is None


# ============ Routing ============

def test_base36_label_resolves_by_hash(monkeypatch):
    seen = {}
    monkeypatch.setattr(ens_resolver, 'SUBGRAPH_URL', 'http://subgraph')
    monkeypatch.setattr(ens_resolver, 'resolve_owner_by_number',
                        lambda n: pytest.fail('should not route by number'))

    class FakeResp:
        @staticmethod
        def json():
            return {'data': {'fileHashLookup': {'latestOwner': '0xowner'}}}

    def fake_post(url, json=None, timeout=None):
        seen['id'] = json['variables']['id']
        return FakeResp()

    monkeypatch.setitem(sys.modules, 'requests',
                        type('m', (), {'post': staticmethod(fake_post)}))

    assert ens_resolver.resolve_owner(LABEL) == '0xowner'
    assert seen['id'] == HASH


def test_stamp_number_label_resolves_by_number(monkeypatch):
    monkeypatch.setattr(ens_resolver, 'resolve_owner_by_number',
                        lambda n: f'owner-of-{n}')
    assert ens_resolver.resolve_owner('3') == 'owner-of-3'


def test_unrecognised_label_resolves_to_nothing(monkeypatch):
    monkeypatch.setattr(ens_resolver, 'SUBGRAPH_URL', 'http://subgraph')
    assert ens_resolver.resolve_owner('hello') is None
