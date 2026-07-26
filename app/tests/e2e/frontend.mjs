// End-to-end frontend harness.
//
// Loads the real index.html in a DOM emulator, runs the real app.js (bundled),
// drives the actual user flow, and prints KEY=VALUE lines for the pytest
// wrapper in test_frontend.py to assert on.
//
// The wallets are mocks: the point is to prove the app builds the right
// transaction and reports results honestly, without touching a live chain.

import { JSDOM } from 'jsdom';
import { webcrypto } from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';

const FRONTEND = path.resolve(import.meta.dirname, '../../frontend');
const BUNDLE = process.argv[2];

const SUI_ACCOUNT = {address: '0xceee87d715a7469462bb883a2ff7cf4952f8df2a5c0efdb55471dd9e8580fa0f'};
const EVM_ACCOUNT = '0x1111111111111111111111111111111111111111';
const HELLO_SHA256 = '0x2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824';

const out = [];
function emit(key, value) {
    out.push(key + '=' + value);
}

function makeSuiWallet(captured) {
    return {
        name: 'Mock Sui Wallet',
        accounts: [SUI_ACCOUNT],
        features: {
            'standard:connect': {connect: async () => ({accounts: [SUI_ACCOUNT]})},
            'sui:signAndExecuteTransaction': {
                signAndExecuteTransaction: async (input) => {
                    captured.sui = input;
                    return {digest: 'MockSuiDigest'};
                },
            },
        },
    };
}

function makeEvmProvider(captured) {
    return {
        request: async ({method, params}) => {
            if (method === 'eth_requestAccounts') return [EVM_ACCOUNT];
            if (method === 'eth_chainId') return '0x14a34';
            if (method === 'eth_sendTransaction') {
                captured.evm = params[0];
                return '0xMockEvmTxHash';
            }
            throw new Error('unexpected method ' + method);
        },
    };
}

async function bootPage({withSui, withEvm, lookup, ownedStamp}) {
    const html = fs.readFileSync(path.join(FRONTEND, 'index.html'), 'utf8')
        .replace(/<script type="module"[^>]*><\/script>/, '');

    const errors = [];
    const dom = new JSDOM(html, {
        runScripts: 'dangerously',
        pretendToBeVisual: true,
        url: 'http://localhost/',
    });
    dom.virtualConsole.on('jsdomError', e => errors.push(e.detail?.message || e.message));

    const w = dom.window;
    Object.defineProperty(w, 'crypto', {value: webcrypto, configurable: true});
    // Stub the backend so the harness stays offline and deterministic.
    w.fetch = async (url) => {
        const target = String(url);
        if (target.includes('/api/lookup')) {
            return {ok: true, json: async () => lookup || {found: false}};
        }
        if (target.includes('/api/sui/stamp-object')) {
            return {ok: true, json: async () => ownedStamp || {found: false}};
        }
        return {ok: true, json: async () => ({})};
    };

    const captured = {};
    if (withSui) {
        w.addEventListener('wallet-standard:app-ready', e => e.detail.register(makeSuiWallet(captured)));
    }
    if (withEvm) {
        w.ethereum = makeEvmProvider(captured);
    }

    const script = w.document.createElement('script');
    script.textContent = fs.readFileSync(BUNDLE, 'utf8');
    w.document.body.appendChild(script);
    w.document.dispatchEvent(new w.Event('DOMContentLoaded', {bubbles: true}));
    await new Promise(r => setTimeout(r, 300));

    return {dom, window: w, doc: w.document, errors, captured};
}

function click(window, element) {
    element.dispatchEvent(new window.MouseEvent('click', {bubbles: true}));
}

async function dropFile(ctx, zoneId) {
    const {window, doc} = ctx;
    const file = new window.File([new Uint8Array([104, 101, 108, 108, 111])], 'hello.txt');
    const event = new window.Event('drop', {bubbles: true});
    Object.defineProperty(event, 'dataTransfer', {value: {files: [file]}});
    doc.getElementById(zoneId).dispatchEvent(event);
    await new Promise(r => setTimeout(r, 800));
}

async function selectChain(ctx, chain) {
    click(ctx.window, ctx.doc.querySelector(`[data-chain="${chain}"]`));
    ctx.doc.getElementById('store-walrus').checked = false;
}

async function stamp(ctx) {
    click(ctx.window, ctx.doc.getElementById('btn-stamp'));
    await new Promise(r => setTimeout(r, 3000));
    return ctx.doc.getElementById('stamp-result').textContent.trim();
}

// ============ Cases ============

// Hashing happens in-browser and drives the UI.
{
    const ctx = await bootPage({});
    await dropFile(ctx, 'drop-zone');
    emit('HASH', ctx.doc.getElementById('file-hash').textContent);
    emit('HASH_MATCHES', String(ctx.doc.getElementById('file-hash').textContent === HELLO_SHA256));
    emit('CLAIM_PANEL_VISIBLE', String(!ctx.doc.getElementById('claim-panel').classList.contains('hidden')));
    emit('LOOKUP_SAYS_UNCLAIMED', String(/not stamped/i.test(ctx.doc.getElementById('lookup-result').textContent)));
    emit('CHAIN_SWITCHES', String((() => {
        click(ctx.window, ctx.doc.querySelector('[data-chain="sui"]'));
        return ctx.doc.querySelector('[data-chain="sui"]').classList.contains('active')
            && !ctx.doc.querySelector('[data-chain="evm"]').classList.contains('active');
    })()));
    emit('LOAD_ERRORS', ctx.errors.length);
}

// Sui: the transaction must target the deployed package with the right shape.
{
    const ctx = await bootPage({withSui: true});
    await dropFile(ctx, 'drop-zone');
    await selectChain(ctx, 'sui');
    const result = await stamp(ctx);
    emit('SUI_RESULT_OK', String(result.includes('Stamped') && result.includes('Sui Testnet')));

    const input = ctx.captured.sui;
    emit('SUI_CAPTURED', String(!!input));
    emit('SUI_CHAIN', input?.chain);
    const data = JSON.parse(await input.transaction.toJSON());
    const call = data.commands[0].MoveCall;
    emit('SUI_TARGET', `${call.package}::${call.module}::${call.function}`);
    emit('SUI_ARG_COUNT', call.arguments.length);
    emit('SUI_SENDER', data.sender);
    emit('SUI_ERRORS', ctx.errors.length);
}

// EVM: calldata must carry the stamp selector and go to the registry contract.
{
    const ctx = await bootPage({withEvm: true});
    await dropFile(ctx, 'drop-zone');
    await selectChain(ctx, 'evm');
    const result = await stamp(ctx);
    emit('EVM_RESULT_OK', String(result.includes('Stamped') && result.includes('Base Sepolia')));

    const tx = ctx.captured.evm;
    emit('EVM_CAPTURED', String(!!tx));
    emit('EVM_TO', tx?.to);
    emit('EVM_SELECTOR', tx?.data.slice(0, 10));
    emit('EVM_HASH_IN_CALLDATA', String(tx?.data.includes(HELLO_SHA256.slice(2))));
    emit('EVM_ERRORS', ctx.errors.length);
}

// No wallet at all: the user must be told, not silently served a fallback.
{
    const ctx = await bootPage({});
    await dropFile(ctx, 'drop-zone');
    await selectChain(ctx, 'evm');
    const result = await stamp(ctx);
    emit('NOWALLET_REPORTS_ERROR', String(result.includes('✗') && /wallet/i.test(result)));
    emit('NOWALLET_NOT_CLAIMING_SUCCESS', String(!result.includes('Stamped')));
}

// ============ Transfers ============

const FILE_HASH = '0x' + 'ab'.repeat(32);
const NEW_EVM_OWNER = '0x2222222222222222222222222222222222222222';
const NEW_SUI_OWNER = '0x' + '33'.repeat(32);

async function verify(ctx, hash) {
    ctx.doc.getElementById('hash-input').value = hash;
    click(ctx.window, ctx.doc.getElementById('btn-check'));
    await new Promise(r => setTimeout(r, 800));
}

async function transfer(ctx, newOwner) {
    ctx.doc.getElementById('transfer-to').value = newOwner;
    click(ctx.window, ctx.doc.getElementById('btn-transfer'));
    await new Promise(r => setTimeout(r, 3000));
    return ctx.doc.getElementById('transfer-result').textContent.trim();
}

// Panel must not appear for a hash that was never stamped.
{
    const ctx = await bootPage({lookup: {found: false}});
    await verify(ctx, FILE_HASH);
    emit('XFER_PANEL_HIDDEN_WHEN_NOT_FOUND',
        String(ctx.doc.getElementById('transfer-panel').classList.contains('hidden')));
}

// EVM transfer against a stamp found on Base.
{
    const ctx = await bootPage({
        withEvm: true,
        lookup: {found: true, owner: EVM_ACCOUNT, source: 'contract'},
    });
    await verify(ctx, FILE_HASH);
    emit('XFER_PANEL_SHOWN', String(!ctx.doc.getElementById('transfer-panel').classList.contains('hidden')));
    emit('XFER_CHAIN_LABEL', ctx.doc.getElementById('transfer-chain').textContent);

    const result = await transfer(ctx, NEW_EVM_OWNER);
    emit('XFER_EVM_RESULT_OK', String(result.includes('Transferred')));
    const tx = ctx.captured.evm;
    emit('XFER_EVM_SELECTOR', tx?.data.slice(0, 10));
    emit('XFER_EVM_TO_CONTRACT', tx?.to);
    emit('XFER_EVM_ENCODES_NEW_OWNER',
        String(tx?.data.toLowerCase().includes(NEW_EVM_OWNER.slice(2).toLowerCase())));
    emit('XFER_EVM_ERRORS', ctx.errors.length);
}

// Sui transfer resolves the Stamp object first, then moves it.
{
    const ctx = await bootPage({
        withSui: true,
        lookup: {found: true, owner: SUI_ACCOUNT.address, source: 'sui'},
        ownedStamp: {found: true, objectId: '0x' + '44'.repeat(32)},
    });
    await verify(ctx, FILE_HASH);
    emit('XFER_SUI_CHAIN_LABEL', ctx.doc.getElementById('transfer-chain').textContent);

    const result = await transfer(ctx, NEW_SUI_OWNER);
    emit('XFER_SUI_RESULT_OK', String(result.includes('Transferred')));

    const input = ctx.captured.sui;
    emit('XFER_SUI_CAPTURED', String(!!input));
    const data = JSON.parse(await input.transaction.toJSON());
    const call = data.commands[0].MoveCall;
    emit('XFER_SUI_TARGET', `${call.package}::${call.module}::${call.function}`);
    emit('XFER_SUI_ARG_COUNT', call.arguments.length);
    emit('XFER_SUI_ERRORS', ctx.errors.length);
}

// A Sui wallet that holds no matching stamp must be told, not silently failed.
{
    const ctx = await bootPage({
        withSui: true,
        lookup: {found: true, owner: SUI_ACCOUNT.address, source: 'sui'},
        ownedStamp: {found: false},
    });
    await verify(ctx, FILE_HASH);
    const result = await transfer(ctx, NEW_SUI_OWNER);
    emit('XFER_SUI_NO_OBJECT_REPORTS_ERROR',
        String(result.includes('✗') && /does not hold/i.test(result)));
    emit('XFER_SUI_NO_OBJECT_NO_TX', String(!ctx.captured.sui));
}

// A malformed address must be rejected before any wallet is asked to sign.
{
    const ctx = await bootPage({
        withEvm: true,
        lookup: {found: true, owner: EVM_ACCOUNT, source: 'contract'},
    });
    await verify(ctx, FILE_HASH);
    const result = await transfer(ctx, '0xnot-an-address');
    emit('XFER_REJECTS_BAD_ADDRESS', String(result.includes('✗')));
    emit('XFER_BAD_ADDRESS_NO_TX', String(!ctx.captured.evm));
}

// ============ Unified flow ============

// A stamped file shows its provenance and offers no claim form.
{
    const ctx = await bootPage({
        lookup: {
            found: true,
            owner: EVM_ACCOUNT,
            timestamp: 1700000000,
            description: 'design doc v2',
            walrusBlobId: 'blob123',
            source: 'subgraph',
        },
    });
    await dropFile(ctx, 'drop-zone');
    const text = ctx.doc.getElementById('lookup-result').textContent;

    emit('FOUND_SHOWS_STAMPED', String(/Stamped/.test(text)));
    emit('FOUND_SHOWS_OWNER', String(text.includes(EVM_ACCOUNT)));
    emit('FOUND_SHOWS_WHEN', String(/Stamped/.test(text) && text.includes('20')));
    emit('FOUND_SHOWS_METADATA', String(text.includes('design doc v2') && text.includes('blob123')));
    emit('FOUND_SHOWS_CHAIN', String(text.includes('Base Sepolia')));
    emit('FOUND_HIDES_CLAIM', String(ctx.doc.getElementById('claim-panel').classList.contains('hidden')));
    emit('FOUND_ERRORS', ctx.errors.length);
}

// After stamping, the claim form gives way to a pending state — no second claim.
{
    const ctx = await bootPage({withEvm: true});
    await dropFile(ctx, 'drop-zone');
    await selectChain(ctx, 'evm');
    ctx.doc.getElementById('stamp-desc').value = 'my notes';
    await stamp(ctx);

    const lookup = ctx.doc.getElementById('lookup-result').textContent;
    emit('AFTER_STAMP_HIDES_CLAIM', String(ctx.doc.getElementById('claim-panel').classList.contains('hidden')));
    emit('AFTER_STAMP_SHOWS_PENDING', String(/awaiting confirmation/i.test(lookup)));
    emit('AFTER_STAMP_SHOWS_OWNER', String(lookup.includes(EVM_ACCOUNT)));
    emit('AFTER_STAMP_SHOWS_NOTES', String(lookup.includes('my notes')));
    emit('AFTER_STAMP_KEEPS_TX', String(/Stamped/.test(ctx.doc.getElementById('stamp-result').textContent)));

    // Re-checking before the indexer catches up must not re-offer the claim.
    click(ctx.window, ctx.doc.getElementById('btn-recheck'));
    await new Promise(r => setTimeout(r, 800));
    emit('RECHECK_KEEPS_CLAIM_HIDDEN', String(ctx.doc.getElementById('claim-panel').classList.contains('hidden')));
    emit('RECHECK_STILL_PENDING', String(/awaiting confirmation/i.test(ctx.doc.getElementById('lookup-result').textContent)));
}

// Pasted input: malformed hashes are rejected without a lookup.
{
    const ctx = await bootPage({});
    await verify(ctx, 'plainly-not-a-hash');
    const text = ctx.doc.getElementById('lookup-result').textContent;
    emit('BAD_HASH_REJECTED', String(/not a SHA-256 hash/i.test(text)));
    emit('BAD_HASH_NO_CLAIM', String(ctx.doc.getElementById('claim-panel').classList.contains('hidden')));
}

// A valid pasted hash behaves like a dropped file.
{
    const ctx = await bootPage({lookup: {found: false}});
    await verify(ctx, FILE_HASH);
    emit('PASTED_HASH_SHOWS_HASH', ctx.doc.getElementById('file-hash').textContent);
    emit('PASTED_HASH_OFFERS_CLAIM', String(!ctx.doc.getElementById('claim-panel').classList.contains('hidden')));
}

console.log(out.join('\n'));
