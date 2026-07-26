"""Route registration tests.

/api/ens/resolve/<name> was defined twice — once by the ens blueprint and once
directly on the app. Werkzeug served the blueprint's, so the app-level copy was
dead code that still looked live. It also proxied to ENS_GATEWAY_URL, which in
production points back at this same service, so had it ever won it would have
called itself.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app import app


def rules_for(path):
    return [r for r in app.url_map.iter_rules() if r.rule == path]


def test_ens_resolve_registered_once():
    assert len(rules_for('/api/ens/resolve/<name>')) == 1


def test_ens_resolve_served_by_blueprint():
    adapter = app.url_map.bind('localhost')
    endpoint, _ = adapter.match('/api/ens/resolve/test.binarystamp.eth', method='GET')
    assert endpoint == 'ens.resolve_name'
    assert app.view_functions[endpoint].__module__ == 'ens_resolver'


def test_ccip_gateway_is_post_only():
    """The CCIP-Read gateway and the browser lookup must not collide."""
    rules = rules_for('/api/ens/resolve')
    assert len(rules) == 1
    assert rules[0].methods - {'HEAD', 'OPTIONS'} == {'POST'}


def test_no_duplicate_rules_anywhere():
    """Any duplicated rule means one handler is silently unreachable."""
    seen = {}
    for rule in app.url_map.iter_rules():
        methods = rule.methods - {'HEAD', 'OPTIONS'}
        for method in methods:
            key = (rule.rule, method)
            seen.setdefault(key, []).append(rule.endpoint)

    duplicates = {k: v for k, v in seen.items() if len(v) > 1}
    assert not duplicates, f'shadowed routes: {duplicates}'


@pytest.mark.parametrize('path,method', [
    ('/api/health', 'GET'),
    ('/api/hash', 'POST'),
    ('/api/lookup', 'GET'),
    ('/api/stamp', 'POST'),
    ('/api/sui/lookup', 'GET'),
    ('/api/sui/stamp-object', 'GET'),
    ('/api/sui/config', 'GET'),
    ('/api/ens/resolve', 'POST'),
    ('/api/ens/resolve/<name>', 'GET'),
    ('/api/ens/reverse/<address>', 'GET'),
    ('/api/subgraph/query', 'POST'),
    ('/api/ai/provenance', 'POST'),
    ('/api/walrus/store', 'POST'),
])
def test_documented_route_exists(path, method):
    """Every route in app/README.md's API table is actually registered."""
    matches = [r for r in rules_for(path) if method in r.methods]
    assert matches, f'{method} {path} is documented but not registered'
