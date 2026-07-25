import io
import json
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app import app


@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def test_health(client):
    resp = client.get('/api/health')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['status'] == 'ok'


def test_index(client):
    resp = client.get('/')
    assert resp.status_code == 200
    assert b'BinaryStamp' in resp.data


def test_hash_file(client):
    data = {'file': (io.BytesIO(b'hello world'), 'test.txt')}
    resp = client.post('/api/hash', content_type='multipart/form-data', data=data)
    assert resp.status_code == 200
    result = resp.get_json()
    assert 'hash' in result
    assert len(result['hash']) == 64
    # SHA-256 of "hello world"
    assert result['hash'] == 'b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9'


def test_hash_no_file(client):
    resp = client.post('/api/hash')
    assert resp.status_code == 400


def test_lookup_no_hash(client):
    resp = client.get('/api/lookup')
    assert resp.status_code == 400


def test_lookup_not_found(client):
    resp = client.get('/api/lookup?hash=0x' + 'a' * 64)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['found'] is False


def test_stamp_no_body(client):
    resp = client.post('/api/stamp', content_type='application/json')
    assert resp.status_code == 400


def test_stamp_no_hash(client):
    resp = client.post('/api/stamp', json={})
    assert resp.status_code == 400


def test_stamp_returns_unsigned(client):
    resp = client.post('/api/stamp', json={
        'fileHash': '0x' + 'ab' * 32,
        'description': 'test file'
    })
    assert resp.status_code == 200
    data = resp.get_json()
    assert data.get('unsigned') is True


def test_ens_resolve_not_found(client):
    resp = client.get('/api/ens/resolve/unknown.binarystamp.eth')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['resolved'] is False


def test_subgraph_proxy_not_configured(client):
    resp = client.post('/api/subgraph/query', json={'query': '{ stamps { id } }'})
    assert resp.status_code == 503
