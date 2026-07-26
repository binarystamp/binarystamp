"""End-to-end frontend tests.

Runs the real page and the real app.js in a DOM emulator (frontend.mjs) with
mocked wallets, then asserts on what it reports. Skipped when the Node
toolchain is unavailable, so the Python-only test run still works.
"""

import os
import shutil
import subprocess

import pytest

APP_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HARNESS = os.path.join(APP_DIR, 'tests', 'e2e', 'frontend.mjs')
NODE_MODULES = os.path.join(APP_DIR, 'node_modules')

pytestmark = pytest.mark.skipif(
    shutil.which('node') is None
    or not os.path.isdir(os.path.join(NODE_MODULES, 'jsdom'))
    or not os.path.isdir(os.path.join(NODE_MODULES, 'esbuild')),
    reason='needs node with jsdom and esbuild (run: cd app && npm install)',
)


@pytest.fixture(scope='module')
def results(tmp_path_factory):
    """Bundle app.js, run the harness, and parse its KEY=VALUE output."""
    bundle = str(tmp_path_factory.mktemp('bundle') / 'app.js')

    build = subprocess.run(
        ['npx', 'esbuild', 'frontend/app.js', '--bundle', '--format=iife',
         '--outfile=' + bundle],
        cwd=APP_DIR, capture_output=True, text=True, timeout=180,
    )
    assert build.returncode == 0, f'esbuild failed:\n{build.stderr}'

    run = subprocess.run(
        ['node', HARNESS, bundle],
        cwd=APP_DIR, capture_output=True, text=True, timeout=180,
    )
    assert run.returncode == 0, f'harness failed:\n{run.stdout}\n{run.stderr}'

    parsed = {}
    for line in run.stdout.strip().splitlines():
        if '=' in line:
            key, _, value = line.partition('=')
            parsed[key] = value
    return parsed


# ============ Client-side hashing ============

def test_file_is_hashed_in_browser(results):
    assert results['HASH_MATCHES'] == 'true', results.get('HASH')


def test_stamp_form_appears_after_drop(results):
    assert results['FORM_VISIBLE'] == 'true'


def test_chain_selector_switches(results):
    assert results['CHAIN_SWITCHES'] == 'true'


def test_page_loads_without_errors(results):
    assert results['LOAD_ERRORS'] == '0'


# ============ Sui ============

def test_sui_transaction_is_sent_to_wallet(results):
    assert results['SUI_CAPTURED'] == 'true'


def test_sui_targets_deployed_package(results):
    assert results['SUI_TARGET'] == (
        '0xbc097815add0220a26bc2dff1b5b1184924828d9f14cfd835f2ccc25b8faabf7::stamp::stamp'
    )


def test_sui_passes_all_move_arguments(results):
    # registry, file_hash, metadata_hash, walrus_blob_id, description, clock
    assert results['SUI_ARG_COUNT'] == '6'


def test_sui_uses_testnet_chain_id(results):
    assert results['SUI_CHAIN'] == 'sui:testnet'


def test_sui_sets_connected_account_as_sender(results):
    assert results['SUI_SENDER'].startswith('0xceee87d7')


def test_sui_result_is_reported(results):
    assert results['SUI_RESULT_OK'] == 'true'


def test_sui_runs_without_errors(results):
    assert results['SUI_ERRORS'] == '0'


# ============ EVM ============

def test_evm_transaction_is_sent_to_wallet(results):
    assert results['EVM_CAPTURED'] == 'true'


def test_evm_targets_registry_contract(results):
    assert results['EVM_TO'] == '0x5969D7558d3409ac70ebdF24063AeC7257d0aCe3'


def test_evm_uses_stamp_selector(results):
    assert results['EVM_SELECTOR'] == '0x3fa348a4'


def test_evm_calldata_contains_file_hash(results):
    assert results['EVM_HASH_IN_CALLDATA'] == 'true'


def test_evm_result_is_reported(results):
    assert results['EVM_RESULT_OK'] == 'true'


def test_evm_runs_without_errors(results):
    assert results['EVM_ERRORS'] == '0'


# ============ Transfers ============

def test_transfer_panel_hidden_for_unstamped_file(results):
    assert results['XFER_PANEL_HIDDEN_WHEN_NOT_FOUND'] == 'true'


def test_transfer_panel_shown_for_found_stamp(results):
    assert results['XFER_PANEL_SHOWN'] == 'true'


def test_transfer_panel_labels_the_chain(results):
    assert results['XFER_CHAIN_LABEL'] == 'Base Sepolia'
    assert results['XFER_SUI_CHAIN_LABEL'] == 'Sui Testnet'


def test_evm_transfer_uses_transfer_selector(results):
    assert results['XFER_EVM_SELECTOR'] == '0x19ee075c'


def test_evm_transfer_goes_to_registry_contract(results):
    assert results['XFER_EVM_TO_CONTRACT'] == '0x5969D7558d3409ac70ebdF24063AeC7257d0aCe3'


def test_evm_transfer_encodes_new_owner(results):
    assert results['XFER_EVM_ENCODES_NEW_OWNER'] == 'true'


def test_evm_transfer_reports_success(results):
    assert results['XFER_EVM_RESULT_OK'] == 'true'
    assert results['XFER_EVM_ERRORS'] == '0'


def test_sui_transfer_calls_transfer_stamp(results):
    assert results['XFER_SUI_TARGET'] == (
        '0xbc097815add0220a26bc2dff1b5b1184924828d9f14cfd835f2ccc25b8faabf7::stamp::transfer_stamp'
    )


def test_sui_transfer_passes_stamp_owner_and_clock(results):
    assert results['XFER_SUI_ARG_COUNT'] == '3'


def test_sui_transfer_reports_success(results):
    assert results['XFER_SUI_RESULT_OK'] == 'true'
    assert results['XFER_SUI_ERRORS'] == '0'


def test_sui_transfer_without_owned_stamp_reports_error(results):
    assert results['XFER_SUI_NO_OBJECT_REPORTS_ERROR'] == 'true'


def test_sui_transfer_without_owned_stamp_sends_no_transaction(results):
    assert results['XFER_SUI_NO_OBJECT_NO_TX'] == 'true'


def test_transfer_rejects_malformed_address(results):
    assert results['XFER_REJECTS_BAD_ADDRESS'] == 'true'


def test_transfer_rejects_malformed_address_before_signing(results):
    """Validation must happen before a wallet is asked to sign."""
    assert results['XFER_BAD_ADDRESS_NO_TX'] == 'true'


# ============ Failure honesty ============

def test_missing_wallet_reports_error(results):
    assert results['NOWALLET_REPORTS_ERROR'] == 'true'


def test_missing_wallet_does_not_claim_success(results):
    """A failed stamp must never render as 'Stamped'."""
    assert results['NOWALLET_NOT_CLAIMING_SUCCESS'] == 'true'
