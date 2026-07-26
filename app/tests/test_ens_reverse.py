"""Reverse ENS resolution.

An address's reverse record is set by whoever controls the address, so it is a
claim, not proof. web3's ens.name() only returns a name whose forward
resolution points back at the same address; these tests pin the behaviour we
depend on, and the caching that keeps a two-call mainnet lookup off the hot
path.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import ens_resolver
from app import app

VITALIK = '0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045'
NO_NAME = '0x5969D7558d3409ac70ebdF24063AeC7257d0aCe3'


@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


@pytest.fixture(autouse=True)
def clear_cache():
    """The cache is module-level, so it would leak between tests."""
    ens_resolver._reverse_cache.clear()
    yield
    ens_resolver._reverse_cache.clear()


class FakeEns:
    def __init__(self, names, calls):
        self.names = names
        self.calls = calls

    def name(self, address):
        self.calls.append(address)
        return self.names.get(address.lower())


class FakeWeb3:
    def __init__(self, names, calls):
        self.ens = FakeEns(names, calls)


def install_fake(monkeypatch, names=None, calls=None):
    calls = calls if calls is not None else []
    monkeypatch.setattr(ens_resolver, 'MAINNET_RPC_URL', 'http://fake')
    monkeypatch.setattr(ens_resolver, 'mainnet_web3',
                        lambda: FakeWeb3(names or {}, calls))
    return calls


# ============ Resolution ============

def test_returns_primary_name(monkeypatch):
    install_fake(monkeypatch, {VITALIK.lower(): 'vitalik.eth'})
    assert ens_resolver.reverse_ens(VITALIK) == 'vitalik.eth'


def test_returns_none_without_a_name(monkeypatch):
    install_fake(monkeypatch, {})
    assert ens_resolver.reverse_ens(NO_NAME) is None


def test_lookup_is_case_insensitive(monkeypatch):
    install_fake(monkeypatch, {VITALIK.lower(): 'vitalik.eth'})
    assert ens_resolver.reverse_ens(VITALIK.lower()) == 'vitalik.eth'


def test_unconfigured_mainnet_raises(monkeypatch):
    monkeypatch.setattr(ens_resolver, 'MAINNET_RPC_URL', '')
    monkeypatch.setattr(ens_resolver, 'mainnet_web3', lambda: None)
    with pytest.raises(RuntimeError):
        ens_resolver.reverse_ens(VITALIK)


# ============ Caching ============

def test_second_lookup_is_cached(monkeypatch):
    calls = install_fake(monkeypatch, {VITALIK.lower(): 'vitalik.eth'})
    ens_resolver.reverse_ens(VITALIK)
    ens_resolver.reverse_ens(VITALIK)
    assert len(calls) == 1


def test_misses_are_cached_too(monkeypatch):
    """Most addresses have no name; re-querying them is the common case."""
    calls = install_fake(monkeypatch, {})
    ens_resolver.reverse_ens(NO_NAME)
    ens_resolver.reverse_ens(NO_NAME)
    assert len(calls) == 1


def test_expired_entries_are_refetched(monkeypatch):
    calls = install_fake(monkeypatch, {VITALIK.lower(): 'vitalik.eth'})
    ens_resolver.reverse_ens(VITALIK)
    # Force expiry.
    ens_resolver._reverse_cache[VITALIK.lower()] = ('vitalik.eth', 0)
    ens_resolver.reverse_ens(VITALIK)
    assert len(calls) == 2


# ============ Route ============

def test_route_returns_name(client, monkeypatch):
    install_fake(monkeypatch, {VITALIK.lower(): 'vitalik.eth'})
    data = client.get('/api/ens/reverse/' + VITALIK).get_json()
    assert data['name'] == 'vitalik.eth'
    assert data['address'] == VITALIK


def test_route_returns_null_without_a_name(client, monkeypatch):
    install_fake(monkeypatch, {})
    resp = client.get('/api/ens/reverse/' + NO_NAME)
    assert resp.status_code == 200
    assert resp.get_json()['name'] is None


def test_route_rejects_malformed_address(client):
    assert client.get('/api/ens/reverse/notanaddress').status_code == 400


def test_route_rejects_sui_address(client):
    """Sui addresses are 32 bytes and have no ENS reverse record."""
    assert client.get('/api/ens/reverse/0x' + 'ab' * 32).status_code == 400


def test_route_503_when_mainnet_unconfigured(client, monkeypatch):
    monkeypatch.setattr(ens_resolver, 'MAINNET_RPC_URL', '')
    resp = client.get('/api/ens/reverse/' + VITALIK)
    assert resp.status_code == 503
    assert resp.get_json()['name'] is None


def test_route_502_on_rpc_failure(client, monkeypatch):
    monkeypatch.setattr(ens_resolver, 'MAINNET_RPC_URL', 'http://fake')

    def boom():
        raise RuntimeError('mainnet unreachable')

    monkeypatch.setattr(ens_resolver, 'mainnet_web3', boom)
    resp = client.get('/api/ens/reverse/' + VITALIK)
    assert resp.status_code == 502
    assert resp.get_json()['name'] is None
