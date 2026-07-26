import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import app as app_module
from app import app


@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def make_event(file_hash_bytes, owner, timestamp_ms, digest='DIGEST1'):
    return {
        'id': {'txDigest': digest},
        'parsedJson': {
            'file_hash': list(file_hash_bytes),
            'metadata_hash': [0] * 32,
            'owner': owner,
            'stamp_id': '0xstamp',
            'timestamp_ms': str(timestamp_ms),
        },
    }


# ============ Field normalization ============

def test_bytes_field_from_list():
    assert app_module.bytes_field_to_hex([171, 205]) == '0xabcd'


def test_bytes_field_from_prefixed_string():
    assert app_module.bytes_field_to_hex('0xabcd') == '0xabcd'


def test_bytes_field_from_bare_string():
    assert app_module.bytes_field_to_hex('abcd') == '0xabcd'


def test_bytes_field_from_missing():
    assert app_module.bytes_field_to_hex(None) == ''


# ============ Event scanning ============

def test_sui_stamp_found(monkeypatch):
    target = bytes.fromhex('ab' * 32)
    monkeypatch.setattr(app_module, 'SUI_PACKAGE_ID', '0xpkg')
    monkeypatch.setattr(app_module, 'sui_rpc', lambda m, p: {
        'data': [make_event(target, '0xowner', 1700000000000)],
        'hasNextPage': False,
    })

    result = app_module.query_sui_stamp('0x' + 'ab' * 32)
    assert result['found'] is True
    assert result['source'] == 'sui'
    assert result['owner'] == '0xowner'
    assert result['timestamp'] == 1700000000  # ms converted to seconds
    assert result['txDigest'] == 'DIGEST1'


def test_sui_stamp_accepts_hash_without_prefix(monkeypatch):
    target = bytes.fromhex('ab' * 32)
    monkeypatch.setattr(app_module, 'SUI_PACKAGE_ID', '0xpkg')
    monkeypatch.setattr(app_module, 'sui_rpc', lambda m, p: {
        'data': [make_event(target, '0xowner', 1700000000000)],
        'hasNextPage': False,
    })

    assert app_module.query_sui_stamp('ab' * 32)['found'] is True


def test_sui_stamp_ignores_other_hashes(monkeypatch):
    other = bytes.fromhex('cd' * 32)
    monkeypatch.setattr(app_module, 'SUI_PACKAGE_ID', '0xpkg')
    monkeypatch.setattr(app_module, 'sui_rpc', lambda m, p: {
        'data': [make_event(other, '0xowner', 1700000000000)],
        'hasNextPage': False,
    })

    assert app_module.query_sui_stamp('0x' + 'ab' * 32) is None


def test_sui_stamp_returns_earliest_across_pages(monkeypatch):
    """Events arrive newest-first, so the oldest match wins."""
    target = bytes.fromhex('ab' * 32)
    pages = [
        {'data': [make_event(target, '0xnewer', 2000, 'NEW')],
         'hasNextPage': True, 'nextCursor': 'c1'},
        {'data': [make_event(target, '0xolder', 1000, 'OLD')],
         'hasNextPage': False},
    ]
    calls = []

    def fake_rpc(method, params):
        if 'StampTransferred' in params[0]['MoveEventType']:
            return {'data': [], 'hasNextPage': False}
        calls.append(params[1])
        return pages[len(calls) - 1]

    monkeypatch.setattr(app_module, 'SUI_PACKAGE_ID', '0xpkg')
    monkeypatch.setattr(app_module, 'sui_rpc', fake_rpc)

    result = app_module.query_sui_stamp('0x' + 'ab' * 32)
    assert result['owner'] == '0xolder'
    assert result['txDigest'] == 'OLD'
    assert calls == [None, 'c1']  # cursor threaded through


def test_sui_stamp_respects_page_cap(monkeypatch):
    """An endless event log must not loop forever."""
    other = bytes.fromhex('cd' * 32)
    calls = []

    def fake_rpc(method, params):
        calls.append(1)
        return {'data': [make_event(other, '0xowner', 1000)],
                'hasNextPage': True, 'nextCursor': 'c'}

    monkeypatch.setattr(app_module, 'SUI_PACKAGE_ID', '0xpkg')
    monkeypatch.setattr(app_module, 'SUI_EVENT_MAX_PAGES', 3)
    monkeypatch.setattr(app_module, 'sui_rpc', fake_rpc)

    assert app_module.query_sui_stamp('0x' + 'ab' * 32) is None
    assert len(calls) == 3


# ============ Routes ============

def test_sui_lookup_requires_hash(client):
    assert client.get('/api/sui/lookup').status_code == 400


def test_sui_lookup_unconfigured(client, monkeypatch):
    monkeypatch.setattr(app_module, 'SUI_PACKAGE_ID', '')
    resp = client.get('/api/sui/lookup?hash=0x' + 'ab' * 32)
    assert resp.status_code == 503


def test_sui_lookup_found(client, monkeypatch):
    target = bytes.fromhex('ab' * 32)
    monkeypatch.setattr(app_module, 'SUI_PACKAGE_ID', '0xpkg')
    monkeypatch.setattr(app_module, 'sui_rpc', lambda m, p: {
        'data': [make_event(target, '0xowner', 1700000000000)],
        'hasNextPage': False,
    })

    resp = client.get('/api/sui/lookup?hash=0x' + 'ab' * 32)
    assert resp.status_code == 200
    assert resp.get_json()['owner'] == '0xowner'


def test_sui_lookup_not_found(client, monkeypatch):
    monkeypatch.setattr(app_module, 'SUI_PACKAGE_ID', '0xpkg')
    monkeypatch.setattr(app_module, 'sui_rpc', lambda m, p: {'data': [], 'hasNextPage': False})

    resp = client.get('/api/sui/lookup?hash=0x' + 'ab' * 32)
    assert resp.status_code == 200
    assert resp.get_json()['found'] is False


def test_sui_lookup_rpc_failure_is_502(client, monkeypatch):
    def boom(method, params):
        raise RuntimeError('node unreachable')

    monkeypatch.setattr(app_module, 'SUI_PACKAGE_ID', '0xpkg')
    monkeypatch.setattr(app_module, 'sui_rpc', boom)

    resp = client.get('/api/sui/lookup?hash=0x' + 'ab' * 32)
    assert resp.status_code == 502
    assert resp.get_json()['found'] is False


# ============ Transfers ============

def transfer_event(file_hash_bytes, to_address):
    return {
        'id': {'txDigest': 'T'},
        'parsedJson': {
            'file_hash': list(file_hash_bytes),
            'from': '0xold',
            'to': to_address,
            'stamp_id': '0xstamp',
            'timestamp_ms': '1700000001000',
        },
    }


def route_by_event_type(created_pages, transferred_pages):
    """Dispatch a fake sui_rpc by which event type is being queried."""
    def fake_rpc(method, params):
        if method == 'suix_queryEvents':
            event_type = params[0]['MoveEventType']
            pages = transferred_pages if 'StampTransferred' in event_type else created_pages
            return pages.pop(0) if pages else {'data': [], 'hasNextPage': False}
        raise AssertionError('unexpected method ' + method)
    return fake_rpc


def test_lookup_reports_current_owner_after_transfer(monkeypatch):
    """A transferred stamp must not report the original owner."""
    target = bytes.fromhex('ab' * 32)
    monkeypatch.setattr(app_module, 'SUI_PACKAGE_ID', '0xpkg')
    monkeypatch.setattr(app_module, 'sui_rpc', route_by_event_type(
        [{'data': [make_event(target, '0xcreator', 1700000000000)], 'hasNextPage': False}],
        [{'data': [transfer_event(target, '0xnewowner')], 'hasNextPage': False}],
    ))

    result = app_module.query_sui_stamp('0x' + 'ab' * 32)
    assert result['owner'] == '0xnewowner'
    assert result['transferred'] is True


def test_lookup_applies_last_transfer_in_a_chain(monkeypatch):
    target = bytes.fromhex('ab' * 32)
    monkeypatch.setattr(app_module, 'SUI_PACKAGE_ID', '0xpkg')
    monkeypatch.setattr(app_module, 'sui_rpc', route_by_event_type(
        [{'data': [make_event(target, '0xcreator', 1700000000000)], 'hasNextPage': False}],
        [{'data': [transfer_event(target, '0xsecond'),
                   transfer_event(target, '0xthird')], 'hasNextPage': False}],
    ))

    assert app_module.query_sui_stamp('0x' + 'ab' * 32)['owner'] == '0xthird'


def test_lookup_ignores_transfers_of_other_files(monkeypatch):
    target = bytes.fromhex('ab' * 32)
    other = bytes.fromhex('cd' * 32)
    monkeypatch.setattr(app_module, 'SUI_PACKAGE_ID', '0xpkg')
    monkeypatch.setattr(app_module, 'sui_rpc', route_by_event_type(
        [{'data': [make_event(target, '0xcreator', 1700000000000)], 'hasNextPage': False}],
        [{'data': [transfer_event(other, '0xunrelated')], 'hasNextPage': False}],
    ))

    result = app_module.query_sui_stamp('0x' + 'ab' * 32)
    assert result['owner'] == '0xcreator'
    assert 'transferred' not in result


def test_find_stamp_object_matches_file_hash(monkeypatch):
    target = bytes.fromhex('ab' * 32)
    monkeypatch.setattr(app_module, 'SUI_PACKAGE_ID', '0xpkg')
    monkeypatch.setattr(app_module, 'sui_rpc', lambda m, p: {
        'data': [
            {'data': {'objectId': '0xwrong',
                      'content': {'fields': {'file_hash': list(bytes.fromhex('cd' * 32))}}}},
            {'data': {'objectId': '0xright',
                      'content': {'fields': {'file_hash': list(target)}}}},
        ],
        'hasNextPage': False,
    })

    assert app_module.find_sui_stamp_object('0xowner', '0x' + 'ab' * 32) == '0xright'


def test_find_stamp_object_returns_none_when_absent(monkeypatch):
    monkeypatch.setattr(app_module, 'SUI_PACKAGE_ID', '0xpkg')
    monkeypatch.setattr(app_module, 'sui_rpc', lambda m, p: {'data': [], 'hasNextPage': False})

    assert app_module.find_sui_stamp_object('0xowner', '0x' + 'ab' * 32) is None


def test_stamp_object_route_requires_both_params(client):
    assert client.get('/api/sui/stamp-object').status_code == 400
    assert client.get('/api/sui/stamp-object?address=0xa').status_code == 400


def test_stamp_object_route_found(client, monkeypatch):
    target = bytes.fromhex('ab' * 32)
    monkeypatch.setattr(app_module, 'SUI_PACKAGE_ID', '0xpkg')
    monkeypatch.setattr(app_module, 'sui_rpc', lambda m, p: {
        'data': [{'data': {'objectId': '0xobj',
                           'content': {'fields': {'file_hash': list(target)}}}}],
        'hasNextPage': False,
    })

    data = client.get('/api/sui/stamp-object?address=0xowner&hash=0x' + 'ab' * 32).get_json()
    assert data['found'] is True
    assert data['objectId'] == '0xobj'


def test_stamp_object_route_not_found(client, monkeypatch):
    monkeypatch.setattr(app_module, 'SUI_PACKAGE_ID', '0xpkg')
    monkeypatch.setattr(app_module, 'sui_rpc', lambda m, p: {'data': [], 'hasNextPage': False})

    resp = client.get('/api/sui/stamp-object?address=0xowner&hash=0x' + 'ab' * 32)
    assert resp.status_code == 200
    assert resp.get_json()['found'] is False


def test_sui_config_route(client):
    data = client.get('/api/sui/config').get_json()
    assert 'packageId' in data
    assert 'registryId' in data
    assert 'configured' in data


def test_health_reports_sui(client):
    assert 'sui' in client.get('/api/health').get_json()
