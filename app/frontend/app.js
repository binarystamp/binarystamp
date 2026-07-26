// ============ BinaryStamp Frontend ============

import {
    connectEvmWallet,
    stampOnEvm,
    transferOnEvm,
    connectSuiWallet,
    stampOnSui,
    transferOnSui,
} from './chains.js';

const API = '';
let currentHash = null;
let currentChain = 'evm';
let walletAddress = null;   // EVM address
let suiConnection = null;   // {wallet, account, address}
let verifiedStamp = null;   // last successful lookup, drives the transfer panel
let aiAvailable = false;    // from /api/health; hides the AI panel when unconfigured
let pendingStamp = null;    // a stamp we submitted that the registry has not indexed yet

// ============ Init ============

document.addEventListener('DOMContentLoaded', () => {
    setupDropZone();
    setupButtons();
    checkHealth();
});

// ============ Drop Zone ============

function setupDropZone() {
    const zone = document.getElementById('drop-zone');
    const input = document.getElementById('file-input');

    zone.addEventListener('click', () => input.click());
    zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('dragover'); });
    zone.addEventListener('dragleave', () => zone.classList.remove('dragover'));
    zone.addEventListener('drop', e => {
        e.preventDefault();
        zone.classList.remove('dragover');
        if (e.dataTransfer.files.length) handleFile(e.dataTransfer.files[0]);
    });
    input.addEventListener('change', () => { if (input.files.length) handleFile(input.files[0]); });
}

// ============ File Handling ============

async function hashFile(file) {
    const buffer = await file.arrayBuffer();
    const hashBuffer = await crypto.subtle.digest('SHA-256', buffer);
    const hashArray = Array.from(new Uint8Array(hashBuffer));
    return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
}

function formatSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / 1048576).toFixed(1) + ' MB';
}

// Hash locally, then go straight to the lookup — the file never leaves here.
async function handleFile(file) {
    const zone = document.getElementById('drop-zone');
    resetPanels();

    setDropZoneLoading(zone, true, 'Hashing ' + file.name + '...');
    const hash = await hashFile(file);
    setDropZoneLoading(zone, false);

    showHash('0x' + hash, file.name, formatSize(file.size));
    document.getElementById('hash-input').value = '';

    await checkHash('0x' + hash);
}

function showHash(hash, name, size) {
    document.getElementById('file-hash').textContent = hash;
    document.getElementById('file-name').textContent = name || '';
    document.getElementById('file-size').textContent = size || '';
    document.getElementById('hash-result').classList.remove('hidden');
}

function resetPanels() {
    currentHash = null;
    verifiedStamp = null;
    pendingStamp = null;
    for (const id of ['lookup-result', 'claim-panel', 'transfer-panel', 'ai-panel',
                      'stamp-result', 'transfer-result', 'ai-answer']) {
        document.getElementById(id).classList.add('hidden');
    }
}

// ============ Buttons ============

function setupButtons() {
    // Copy hash
    document.getElementById('btn-copy').addEventListener('click', () => {
        navigator.clipboard.writeText('0x' + currentHash);
        document.getElementById('btn-copy').style.color = 'var(--success)';
        setTimeout(() => document.getElementById('btn-copy').style.color = '', 1000);
    });

    // Chain select
    document.querySelectorAll('.chain-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.chain-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            currentChain = btn.dataset.chain;
            renderWallet();
        });
    });

    // Stamp button
    document.getElementById('btn-stamp').addEventListener('click', doStamp);

    // Check button
    document.getElementById('btn-check').addEventListener('click', doCheck);
    document.getElementById('hash-input').addEventListener('keydown', e => {
        if (e.key === 'Enter') doCheck();
    });

    // Transfer button
    document.getElementById('btn-transfer').addEventListener('click', doTransfer);
    document.getElementById('transfer-to').addEventListener('keydown', e => {
        if (e.key === 'Enter') doTransfer();
    });

    // AI ask button
    document.getElementById('btn-ai-ask').addEventListener('click', doAiAsk);
    document.getElementById('ai-question').addEventListener('keydown', e => {
        if (e.key === 'Enter') doAiAsk();
    });

    // Connect wallet
    document.getElementById('btn-connect').addEventListener('click', connectWallet);
}

// ============ Wallet ============

function shortAddress(address) {
    return address.slice(0, 6) + '...' + address.slice(-4);
}

// Reflects whichever wallets are currently connected for the selected chain.
function renderWallet() {
    const btn = document.getElementById('btn-connect');
    const addrEl = document.getElementById('wallet-address');

    const parts = [];
    if (walletAddress && currentChain !== 'sui') parts.push(shortAddress(walletAddress));
    if (suiConnection && currentChain !== 'evm') parts.push('Sui ' + shortAddress(suiConnection.address));

    if (!parts.length) {
        btn.classList.remove('hidden');
        addrEl.classList.add('hidden');
        return;
    }

    btn.classList.toggle('hidden', !needsWallet());
    addrEl.textContent = parts.join('  ·  ');
    addrEl.classList.remove('hidden');
}

// True when the selected chain still has an unconnected wallet.
function needsWallet() {
    if (currentChain === 'evm') return !walletAddress;
    if (currentChain === 'sui') return !suiConnection;
    return !walletAddress || !suiConnection;
}

async function connectWallet() {
    const wantEvm = currentChain === 'evm' || currentChain === 'both';
    const wantSui = currentChain === 'sui' || currentChain === 'both';
    const failures = [];

    if (wantEvm && !walletAddress) {
        try {
            walletAddress = await connectEvmWallet();
        } catch (e) {
            console.error('EVM wallet connection failed:', e);
            failures.push(e.message);
        }
    }

    if (wantSui && !suiConnection) {
        try {
            suiConnection = await connectSuiWallet();
        } catch (e) {
            console.error('Sui wallet connection failed:', e);
            failures.push(e.message);
        }
    }

    renderWallet();

    if (failures.length) showToast(failures.join('  '));
}

// ============ Stamp Action ============

async function doStamp() {
    if (!currentHash) return;
    const btn = document.getElementById('btn-stamp');
    const resultEl = document.getElementById('stamp-result');
    btn.classList.add('loading');
    btn.disabled = true;
    resultEl.classList.add('hidden');

    try {
        const description = document.getElementById('stamp-desc').value.trim();
        const storeOnWalrus = document.getElementById('store-walrus').checked;
        let walrusBlobId = '';
        let metadataHash = '0x' + '0'.repeat(64);

        // Store metadata on Walrus if checked
        if (storeOnWalrus) {
            try {
                const walrusResp = await fetch(API + '/api/walrus/store', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        metadata: {
                            fileHash: '0x' + currentHash,
                            description: description,
                            timestamp: Date.now(),
                            chain: currentChain
                        }
                    })
                });
                const walrusData = await walrusResp.json();
                if (walrusData.blobId) {
                    walrusBlobId = walrusData.blobId;
                    metadataHash = '0x' + walrusData.metadataHash;
                }
            } catch (e) {
                console.error('Walrus storage failed (continuing without):', e);
            }
        }

        // Sign with the user's own wallet so the stamp is owned by them.
        const targets = currentChain === 'both' ? ['evm', 'sui'] : [currentChain];
        const results = [];
        const errors = [];

        for (const chain of targets) {
            try {
                if (chain === 'evm') {
                    if (!walletAddress) walletAddress = await connectEvmWallet();
                    results.push(await stampOnEvm(
                        walletAddress, currentHash, metadataHash, walrusBlobId, description));
                } else {
                    if (!suiConnection) suiConnection = await connectSuiWallet();
                    results.push(await stampOnSui(
                        suiConnection, currentHash, metadataHash, walrusBlobId, description));
                }
            } catch (e) {
                console.error('Stamp on ' + chain + ' failed:', e);
                errors.push(chain.toUpperCase() + ': ' + e.message);
            }
        }

        renderWallet();

        if (!results.length) {
            showStampResult(resultEl, false, {error: errors.join('  ') || 'Stamp failed'});
            return;
        }

        showStampResult(resultEl, true, {results: results, errors: errors});

        // The transaction is submitted but not yet indexed, so the registry
        // would still report the file as unclaimed. Show what just landed
        // instead of re-querying and contradicting it.
        showClaimedPending(results[0], description, walrusBlobId);
    } catch (e) {
        showStampResult(resultEl, false, {error: e.message});
    } finally {
        btn.classList.remove('loading');
        btn.disabled = false;
    }
}

const CHAIN_LABELS = {evm: 'Base Sepolia', sui: 'Sui Testnet'};

function showStampResult(el, success, data) {
    el.classList.remove('hidden');

    if (!success) {
        el.innerHTML = '<div class="result-error">&#10007; ' + escapeHtml(data.error || 'Stamp failed') + '</div>';
        return;
    }

    let html = '<div class="result-success">';
    html += '<div class="result-row"><span class="result-label">Status</span>'
        + '<span class="result-value" style="color:var(--success)">&#10003; Stamped</span></div>';

    for (const result of data.results || []) {
        const short = result.txHash.slice(0, 10) + '...' + result.txHash.slice(-8);
        html += '<div class="result-row"><span class="result-label">'
            + escapeHtml(CHAIN_LABELS[result.chain] || result.chain) + '</span>'
            + '<span class="result-value"><a href="' + escapeHtml(result.explorer)
            + '" target="_blank" rel="noopener">' + escapeHtml(short) + '</a></span></div>';
    }

    html += '</div>';

    // A partial success ("Both" where one chain failed) still shows what landed.
    for (const error of data.errors || []) {
        html += '<div class="result-error">&#10007; ' + escapeHtml(error) + '</div>';
    }

    el.innerHTML = html;
}

// ============ Transfer Action ============

// Only offer a transfer for a stamp we actually located on a chain we can sign
// for. An ENS-resolved result carries no chain, so it does not qualify.
function showTransferPanel(data, hash) {
    const panel = document.getElementById('transfer-panel');
    const chainEl = document.getElementById('transfer-chain');
    const resultEl = document.getElementById('transfer-result');

    resultEl.classList.add('hidden');
    document.getElementById('transfer-to').value = '';

    if (!data.found || !hash) {
        verifiedStamp = null;
        panel.classList.add('hidden');
        return;
    }

    const chain = data.source === 'sui' ? 'sui' : 'evm';
    verifiedStamp = {hash: hash, chain: chain, owner: data.owner};

    chainEl.textContent = CHAIN_LABELS[chain];
    panel.classList.remove('hidden');
}

function isAddressForChain(address, chain) {
    if (chain === 'evm') return /^0x[0-9a-fA-F]{40}$/.test(address);
    return /^0x[0-9a-fA-F]{64}$/.test(address);
}

async function doTransfer() {
    if (!verifiedStamp) return;

    const btn = document.getElementById('btn-transfer');
    const resultEl = document.getElementById('transfer-result');
    const newOwner = document.getElementById('transfer-to').value.trim();

    resultEl.classList.add('hidden');

    if (!isAddressForChain(newOwner, verifiedStamp.chain)) {
        showTransferResult(resultEl, false, {
            error: verifiedStamp.chain === 'evm'
                ? 'Enter a 20-byte EVM address (0x + 40 hex characters)'
                : 'Enter a 32-byte Sui address (0x + 64 hex characters)',
        });
        return;
    }

    btn.classList.add('loading');
    btn.disabled = true;

    try {
        let result;

        if (verifiedStamp.chain === 'evm') {
            if (!walletAddress) walletAddress = await connectEvmWallet();
            result = await transferOnEvm(walletAddress, verifiedStamp.hash, newOwner);
        } else {
            if (!suiConnection) suiConnection = await connectSuiWallet();

            const resp = await fetch(API + '/api/sui/stamp-object?address='
                + encodeURIComponent(suiConnection.address)
                + '&hash=' + encodeURIComponent(verifiedStamp.hash));
            const owned = await resp.json();
            if (!owned.found) {
                throw new Error('The connected Sui wallet does not hold a stamp for this file');
            }

            result = await transferOnSui(suiConnection, owned.objectId, newOwner);
        }

        renderWallet();
        showTransferResult(resultEl, true, {...result, newOwner: newOwner});
    } catch (e) {
        console.error('Transfer failed:', e);
        showTransferResult(resultEl, false, {error: e.message});
    } finally {
        btn.classList.remove('loading');
        btn.disabled = false;
    }
}

function showTransferResult(el, success, data) {
    el.classList.remove('hidden');

    if (!success) {
        el.innerHTML = '<div class="result-error">&#10007; ' + escapeHtml(data.error || 'Transfer failed') + '</div>';
        return;
    }

    const short = data.txHash.slice(0, 10) + '...' + data.txHash.slice(-8);
    el.innerHTML = '<div class="result-success">'
        + '<div class="result-row"><span class="result-label">Status</span>'
        + '<span class="result-value" style="color:var(--success)">&#10003; Transferred</span></div>'
        + '<div class="result-row"><span class="result-label">New owner</span>'
        + '<span class="result-value">' + escapeHtml(data.newOwner) + '</span></div>'
        + '<div class="result-row"><span class="result-label">Transaction</span>'
        + '<span class="result-value"><a href="' + escapeHtml(data.explorer)
        + '" target="_blank" rel="noopener">' + escapeHtml(short) + '</a></span></div>'
        + '</div>';
}

// ============ Lookup ============

// Entry point for the pasted-hash / ENS input.
async function doCheck() {
    const raw = document.getElementById('hash-input').value.trim();
    if (!raw) return;

    const btn = document.getElementById('btn-check');
    btn.classList.add('loading');
    btn.disabled = true;
    resetPanels();
    document.getElementById('hash-result').classList.add('hidden');

    try {
        // An ENS name resolves to an owner but not to a hash we could stamp.
        if (raw.endsWith('.eth')) {
            const resp = await fetch(API + '/api/ens/resolve/' + encodeURIComponent(raw));
            const data = await resp.json();
            showEnsResult(data, raw);
            return;
        }

        const hash = raw.startsWith('0x') ? raw : '0x' + raw;
        if (!/^0x[0-9a-fA-F]{64}$/.test(hash)) {
            showLookupError('That is not a SHA-256 hash. Expected 0x followed by 64 hex characters.');
            return;
        }

        showHash(hash.toLowerCase(), '', '');
        await checkHash(hash.toLowerCase());
    } catch (e) {
        showLookupError(e.message);
    } finally {
        btn.classList.remove('loading');
        btn.disabled = false;
    }
}

// Look a hash up and switch the page into "stamped" or "claimable" mode.
async function checkHash(hash) {
    currentHash = hash.slice(2);
    const resultEl = document.getElementById('lookup-result');

    setPanelBusy(resultEl, 'Checking the registry...');

    try {
        const resp = await fetch(API + '/api/lookup?hash=' + encodeURIComponent(hash));
        const data = await resp.json();
        showLookupResult(data, hash);
    } catch (e) {
        showLookupError(e.message);
    }
}

function setPanelBusy(el, message) {
    el.classList.remove('hidden');
    el.innerHTML = '<div class="result-pending">' + escapeHtml(message) + '</div>';
}

function showLookupError(message) {
    const el = document.getElementById('lookup-result');
    el.classList.remove('hidden');
    el.innerHTML = '<div class="result-error">&#10007; ' + escapeHtml(message) + '</div>';
}

function row(label, value, style) {
    return '<div class="result-row"><span class="result-label">' + escapeHtml(label)
        + '</span><span class="result-value"' + (style ? ' style="' + style + '"' : '')
        + '>' + value + '</span></div>';
}

const SOURCE_LABELS = {
    subgraph: 'Base Sepolia',
    contract: 'Base Sepolia',
    sui: 'Sui Testnet',
};

function showLookupResult(data, hash) {
    const el = document.getElementById('lookup-result');
    el.classList.remove('hidden');

    if (!data.found) {
        if (pendingStamp) {
            showClaimedPending(pendingStamp.result, pendingStamp.description,
                               pendingStamp.walrusBlobId);
            return;
        }
        el.innerHTML = '<div class="result-not-found">'
            + row('Status', 'Not stamped &mdash; this file is unclaimed')
            + '</div>';
        showClaimPanel(true);
        showTransferPanel({found: false}, null);
        showAiPanel(false);
        return;
    }

    pendingStamp = null;

    let html = '<div class="result-success">';
    html += row('Status', '&#10003; Stamped', 'color:var(--success)');
    html += row('Owner', escapeHtml(data.owner || 'unknown'));

    const ts = data.timestamp || data.firstStampedAt;
    if (ts) html += row('Stamped', escapeHtml(new Date(parseInt(ts) * 1000).toLocaleString()));

    if (SOURCE_LABELS[data.source]) html += row('Chain', escapeHtml(SOURCE_LABELS[data.source]));
    if (data.transferred) html += row('Ownership', 'Transferred since it was stamped');
    if (data.description) html += row('Notes', escapeHtml(data.description));
    if (data.stampCount) html += row('Total stamps', escapeHtml(String(data.stampCount)));

    if (data.walrusBlobId) {
        html += row('Metadata', '<a href="' + API + '/api/walrus/fetch/'
            + encodeURIComponent(data.walrusBlobId) + '" target="_blank" rel="noopener">'
            + escapeHtml(data.walrusBlobId) + '</a>');
    }

    if (data.stamps && data.stamps.length > 1) {
        html += '<div class="result-history">History (' + data.stamps.length + ' stamps)</div>';
        for (const s of data.stamps) {
            const d = new Date(parseInt(s.timestamp) * 1000).toLocaleString();
            html += row('#' + s.stampNumber, escapeHtml(s.owner.slice(0, 10) + '... @ ' + d));
        }
    }

    html += '</div>';
    el.innerHTML = html;

    showClaimPanel(false);
    showTransferPanel(data, hash);
    showAiPanel(true);
}

// An ENS name tells us the owner, but not a hash we could stamp or transfer.
function showEnsResult(data, name) {
    const el = document.getElementById('lookup-result');
    el.classList.remove('hidden');

    if (!data.resolved) {
        el.innerHTML = '<div class="result-not-found">'
            + row('Status', escapeHtml(name) + ' does not resolve to a stamp')
            + '</div>';
        showClaimPanel(false);
        showAiPanel(false);
        return;
    }

    let html = '<div class="result-success">';
    html += row('Status', '&#10003; Resolved', 'color:var(--success)');
    html += row('Name', escapeHtml(data.name || name));
    html += row('Owner', escapeHtml(data.owner || 'unknown'));
    if (data.description) html += row('Notes', escapeHtml(data.description));
    if (data.walrusBlobId) html += row('Metadata', escapeHtml(data.walrusBlobId));
    html += '</div>';
    el.innerHTML = html;

    showClaimPanel(false);
    showAiPanel(false);
}

// A freshly submitted stamp is on-chain but not yet indexed, so a re-query
// would report it unclaimed. Show the pending state and let the user re-check.
function showClaimedPending(result, description, walrusBlobId) {
    pendingStamp = {result: result, description: description, walrusBlobId: walrusBlobId};

    const owner = result.chain === 'sui'
        ? (suiConnection && suiConnection.address)
        : walletAddress;

    let html = '<div class="result-success">';
    html += row('Status', '&#10003; Stamped &mdash; awaiting confirmation', 'color:var(--success)');
    if (owner) html += row('Owner', escapeHtml(owner));
    html += row('Chain', escapeHtml(CHAIN_LABELS[result.chain] || result.chain));
    if (description) html += row('Notes', escapeHtml(description));
    if (walrusBlobId) html += row('Metadata', escapeHtml(walrusBlobId));
    html += '</div>';
    html += '<button id="btn-recheck" class="btn btn-outline btn-full">Check again</button>';

    const el = document.getElementById('lookup-result');
    el.classList.remove('hidden');
    el.innerHTML = html;

    document.getElementById('btn-recheck').addEventListener('click', () => {
        if (currentHash) checkHash('0x' + currentHash);
    });

    showClaimPanel(false);
    showAiPanel(false);
}

function showClaimPanel(show) {
    const panel = document.getElementById('claim-panel');
    panel.classList.toggle('hidden', !show);
    if (show) document.getElementById('stamp-result').classList.add('hidden');
}

function showAiPanel(show) {
    document.getElementById('ai-panel').classList.toggle('hidden', !show || !aiAvailable);
    document.getElementById('ai-answer').classList.add('hidden');
}

// ============ AI Agent ============

// Only offered on a stamp we just looked up, so the hash is implicit.
async function doAiAsk() {
    const question = document.getElementById('ai-question').value.trim();
    if (!question || !currentHash) return;

    const btn = document.getElementById('btn-ai-ask');
    const answerEl = document.getElementById('ai-answer');

    btn.classList.add('loading');
    btn.disabled = true;
    answerEl.classList.remove('hidden');
    answerEl.innerHTML = '<div class="result-pending">Analysing provenance...</div>';

    try {
        const resp = await fetch(API + '/api/ai/provenance', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({fileHash: '0x' + currentHash, question: question}),
        });
        const data = await resp.json();
        if (data.answer) {
            answerEl.innerHTML = simpleMarkdown(data.answer);
        } else {
            answerEl.innerHTML = '<div class="result-error">&#10007; '
                + escapeHtml(data.error || 'No provenance data for this hash.') + '</div>';
        }
    } catch (e) {
        answerEl.innerHTML = '<div class="result-error">&#10007; ' + escapeHtml(e.message) + '</div>';
    } finally {
        btn.classList.remove('loading');
        btn.disabled = false;
    }
}

// ============ Health Check ============

async function checkHealth() {
    try {
        const resp = await fetch(API + '/api/health');
        const data = await resp.json();

        const badges = {
            'badge-evm': data.evm,
            'badge-sui': data.sui,
            'badge-graph': data.subgraph,
            'badge-walrus': data.walrus,
        };
        for (const [id, configured] of Object.entries(badges)) {
            if (configured) document.getElementById(id).style.borderColor = 'var(--success)';
        }

        aiAvailable = Boolean(data.ai);
        if (aiAvailable) {
            const aiBadge = document.createElement('span');
            aiBadge.className = 'chain-badge';
            aiBadge.textContent = 'AI Agent';
            aiBadge.style.borderColor = 'var(--success)';
            document.querySelector('.footer-links').appendChild(aiBadge);
        }
    } catch (e) {
        // Health check failed, services may not be configured yet
    }
}

// ============ Utils ============

function setDropZoneLoading(zone, loading, statusText) {
    const defaultIcon = zone.querySelector('.drop-icon-default');
    const loadingIcon = zone.querySelector('.drop-icon-loading');
    const text = zone.querySelector('.drop-text');
    const status = zone.querySelector('.drop-status');

    if (loading) {
        zone.classList.add('loading');
        defaultIcon.classList.add('hidden');
        loadingIcon.classList.remove('hidden');
        text.classList.add('hidden');
        status.classList.remove('hidden');
        status.textContent = statusText || 'Processing...';
    } else {
        zone.classList.remove('loading');
        defaultIcon.classList.remove('hidden');
        loadingIcon.classList.add('hidden');
        text.classList.remove('hidden');
        status.classList.add('hidden');
    }
}

let toastTimer = null;

function showToast(message) {
    let toast = document.getElementById('toast');
    if (!toast) {
        toast = document.createElement('div');
        toast.id = 'toast';
        toast.className = 'toast';
        document.body.appendChild(toast);
    }
    toast.textContent = message;
    toast.classList.add('visible');

    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.remove('visible'), 6000);
}

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function simpleMarkdown(text) {
    let html = escapeHtml(text);
    // Headers
    html = html.replace(/^### (.+)$/gm, '<h4>$1</h4>');
    html = html.replace(/^## (.+)$/gm, '<h3>$1</h3>');
    // Bold
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    // Inline code
    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
    // Lists
    html = html.replace(/^- (.+)$/gm, '<li>$1</li>');
    // Tables (simple)
    html = html.replace(/\|(.+)\|/g, (match) => {
        if (match.match(/^\|[\s-|]+\|$/)) return '';
        const cells = match.split('|').filter(c => c.trim());
        return '<tr>' + cells.map(c => '<td>' + c.trim() + '</td>').join('') + '</tr>';
    });
    // Line breaks
    html = html.replace(/\n\n/g, '<br><br>');
    html = html.replace(/---/g, '<hr>');
    return html;
}
