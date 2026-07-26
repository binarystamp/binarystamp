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


def test_unstamped_file_offers_a_claim(results):
    assert results['LOOKUP_SAYS_UNCLAIMED'] == 'true'
    assert results['CLAIM_PANEL_VISIBLE'] == 'true'


def test_chain_selector_switches(results):
    assert results['CHAIN_SWITCHES'] == 'true'


def test_page_loads_without_errors(results):
    assert results['LOAD_ERRORS'] == '0'


# ============ Sui ============

def test_sui_transaction_is_sent_to_wallet(results):
    assert results['SUI_CAPTURED'] == 'true'


def test_sui_targets_deployed_package(results):
    assert results['SUI_TARGET'] == (
        '0xc5487e68a3c6b4cb5a34992c976017178d52b865580d57943e660208d19abc9b::stamp::stamp'
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
        '0xc5487e68a3c6b4cb5a34992c976017178d52b865580d57943e660208d19abc9b::stamp::transfer_stamp'
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


# ============ Unified flow ============

def test_stamped_file_shows_provenance(results):
    assert results['FOUND_SHOWS_STAMPED'] == 'true'
    assert results['FOUND_SHOWS_OWNER'] == 'true'
    assert results['FOUND_SHOWS_WHEN'] == 'true'


def test_stamped_file_shows_metadata(results):
    assert results['FOUND_SHOWS_METADATA'] == 'true'


def test_stamped_file_shows_chain(results):
    assert results['FOUND_SHOWS_CHAIN'] == 'true'


def test_stamped_file_offers_no_claim(results):
    """An already-claimed file must not invite a second claim."""
    assert results['FOUND_HIDES_CLAIM'] == 'true'


def test_found_lookup_runs_without_errors(results):
    assert results['FOUND_ERRORS'] == '0'


def test_claim_form_closes_after_stamping(results):
    assert results['AFTER_STAMP_HIDES_CLAIM'] == 'true'


def test_pending_state_reports_what_was_submitted(results):
    assert results['AFTER_STAMP_SHOWS_PENDING'] == 'true'
    assert results['AFTER_STAMP_SHOWS_OWNER'] == 'true'
    assert results['AFTER_STAMP_SHOWS_NOTES'] == 'true'


def test_transaction_stays_visible_after_stamping(results):
    assert results['AFTER_STAMP_KEEPS_TX'] == 'true'


def test_recheck_before_indexing_does_not_reoffer_claim(results):
    """Re-querying before the indexer catches up must not invite a double stamp."""
    assert results['RECHECK_KEEPS_CLAIM_HIDDEN'] == 'true'
    assert results['RECHECK_STILL_PENDING'] == 'true'


def test_malformed_hash_is_rejected(results):
    assert results['BAD_HASH_REJECTED'] == 'true'
    assert results['BAD_HASH_NO_CLAIM'] == 'true'


def test_pasted_hash_behaves_like_a_dropped_file(results):
    assert results['PASTED_HASH_SHOWS_HASH'] == '0x' + 'ab' * 32
    assert results['PASTED_HASH_OFFERS_CLAIM'] == 'true'


# ============ Owner ENS name ============

def test_owner_ens_name_is_shown(results):
    assert results['ENS_NAME_SHOWN'] == 'true'


def test_owner_address_stays_visible_alongside_name(results):
    """A reverse record is a claim by its own owner, so keep the address."""
    assert results['ENS_SHOWS_SHORT_ADDRESS'] == 'true'
    assert results['ENS_KEEPS_FULL_ADDRESS'] == 'true'


def test_owner_address_stays_on_one_line(results):
    """The full 42-character address wrapped in the narrow value column."""
    assert results['ENS_ADDRESS_ONE_LINE'] == 'true'


def test_ens_lookup_causes_no_errors(results):
    assert results['ENS_ERRORS'] == '0'


def test_owner_without_ens_name_shows_address(results):
    assert results['NO_ENS_SHOWS_ADDRESS'] == 'true'
    assert results['NO_ENS_NO_STRAY_DOT_ETH'] == 'true'


def test_sui_owner_skips_ens_lookup(results):
    """ENS is Ethereum-only; a 32-byte Sui address has no reverse record."""
    assert results['SUI_OWNER_NO_ENS_CALL'] == 'true'
    assert results['SUI_OWNER_SHOWS_ADDRESS'] == 'true'


# ============ Wallet restore on page load ============

def test_authorized_evm_wallet_shows_without_clicking(results):
    assert results['RESTORE_EVM_SHOWS_ADDRESS'] == 'true'
    assert results['RESTORE_EVM_HIDES_CONNECT'] == 'true'


def test_restore_uses_the_non_prompting_call(results):
    assert results['RESTORE_EVM_USED_ETH_ACCOUNTS'] == 'true'


def test_page_load_never_prompts_for_evm(results):
    """eth_requestAccounts opens a wallet dialog; loading a page must not."""
    assert results['RESTORE_EVM_DID_NOT_PROMPT'] == 'true'
    assert results['NO_AUTH_DID_NOT_PROMPT'] == 'true'


def test_restore_causes_no_errors(results):
    assert results['RESTORE_EVM_ERRORS'] == '0'


def test_unauthorized_wallet_still_shows_connect(results):
    assert results['NO_AUTH_SHOWS_CONNECT'] == 'true'
    assert results['NO_AUTH_HIDES_ADDRESS'] == 'true'


def test_authorized_sui_wallet_is_restored(results):
    assert results['RESTORE_SUI_SHOWS_ADDRESS'] == 'true'


def test_exposed_sui_accounts_need_no_connect_call(results):
    assert results['RESTORE_SUI_NO_SILENT_CALL_NEEDED'] == 'true'


def test_page_load_never_prompts_for_sui(results):
    assert results['RESTORE_SUI_DID_NOT_PROMPT'] == 'true'
    assert results['OLD_WALLET_DID_NOT_PROMPT'] == 'true'


def test_silent_connect_skipped_on_older_wallets(results):
    """Silent connect landed in standard:connect 1.1; older wallets would prompt."""
    assert results['OLD_WALLET_NO_SILENT_ATTEMPT'] == 'true'


def test_revoking_access_clears_the_header(results):
    assert results['REVOKE_WAS_CONNECTED'] == 'true'
    assert results['REVOKE_CLEARS_ADDRESS'] == 'true'
    assert results['REVOKE_RESTORES_CONNECT'] == 'true'


def test_switching_account_updates_the_header(results):
    assert results['SWITCH_UPDATES_ADDRESS'] == 'true'


# ============ ENS names for a stamp ============

def test_hash_derived_ens_name_is_shown(results):
    """Derivable from the file alone, so it has to be visible to be usable."""
    assert results['ENS_HASH_NAME_SHOWN'] == 'true'


def test_shown_ens_label_fits_the_dns_limit(results):
    assert results['ENS_HASH_LABEL_FITS_DNS'] == 'true'


def test_stamp_number_ens_name_is_shown(results):
    assert results['ENS_NUMBER_NAME_SHOWN'] == 'true'


def test_sui_stamp_shows_no_ens_name(results):
    """ENS resolution runs through the subgraph, which only indexes Base."""
    assert results['SUI_STAMP_HAS_NO_ENS_NAME'] == 'true'


# ============ Agent answer rendering ============

def test_agent_panel_shown_for_a_stamped_file(results):
    assert results['AI_PANEL_SHOWN'] == 'true'


def test_agent_markdown_table_becomes_a_real_table(results):
    """Cells used to be emitted with no <table>, collapsing into inline text."""
    assert results['AI_RENDERS_TABLE'] == 'true'
    assert results['AI_NO_ORPHAN_CELLS'] == 'true'


def test_agent_lists_are_wrapped(results):
    """Numbered lists were not handled at all and ran together as a paragraph."""
    assert results['AI_RENDERS_ORDERED_LIST'] == 'true'
    assert results['AI_RENDERS_BULLET_LIST'] == 'true'


def test_agent_headings_and_quotes_render(results):
    assert results['AI_RENDERS_HEADING'] == 'true'
    assert results['AI_RENDERS_BLOCKQUOTE'] == 'true'


def test_agent_answer_has_no_double_breaks(results):
    """Blank lines became <br><br>, which is what spread the output out."""
    assert results['AI_NO_STRAY_BR'] == 'true'


def test_agent_answer_escapes_markup(results):
    """The answer is model output rendered as HTML; it must stay inert."""
    assert results['AI_ESCAPES_MARKUP'] == 'true'


def test_agent_renders_without_errors(results):
    assert results['AI_ERRORS'] == '0'


def test_agent_panel_hidden_when_unconfigured(results):
    assert results['AI_HIDDEN_WHEN_UNCONFIGURED'] == 'true'


# ============ Failure honesty ============

def test_missing_wallet_reports_error(results):
    assert results['NOWALLET_REPORTS_ERROR'] == 'true'


def test_missing_wallet_does_not_claim_success(results):
    """A failed stamp must never render as 'Stamped'."""
    assert results['NOWALLET_NOT_CLAIMING_SUCCESS'] == 'true'
