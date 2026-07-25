// ============ BinaryStamp Frontend ============

const API = '';
let currentHash = null;
let currentChain = 'evm';
let walletAddress = null;

// ============ Contract ABI (minimal for client-side) ============
const STAMP_ABI = [
    {
        "inputs": [
            {"name": "fileHash", "type": "bytes32"},
            {"name": "metadataHash", "type": "bytes32"},
            {"name": "walrusBlobId", "type": "string"},
            {"name": "description", "type": "string"}
        ],
        "name": "stamp",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [{"name": "fileHash", "type": "bytes32"}],
        "name": "isStamped",
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [{"name": "fileHash", "type": "bytes32"}],
        "name": "getLatestStamp",
        "outputs": [{
            "components": [
                {"name": "fileHash", "type": "bytes32"},
                {"name": "metadataHash", "type": "bytes32"},
                {"name": "walrusBlobId", "type": "string"},
                {"name": "owner", "type": "address"},
                {"name": "timestamp", "type": "uint256"},
                {"name": "description", "type": "string"}
            ],
            "name": "",
            "type": "tuple"
        }],
        "stateMutability": "view",
        "type": "function"
    }
];

// Contract address on Base Sepolia
const CONTRACT_ADDRESS = '0x5969D7558d3409ac70ebdF24063AeC7257d0aCe3';

// ============ Init ============

document.addEventListener('DOMContentLoaded', () => {
    setupNav();
    setupDropZones();
    setupButtons();
    checkHealth();
});

// ============ Navigation ============

function setupNav() {
    document.querySelectorAll('.nav-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
            btn.classList.add('active');
            document.getElementById('view-' + btn.dataset.view).classList.add('active');
        });
    });
}

// ============ Drop Zones ============

function setupDropZones() {
    setupDropZone('drop-zone', 'file-input', handleStampFile);
    setupDropZone('verify-drop-zone', 'verify-file-input', handleVerifyFile);
}

function setupDropZone(zoneId, inputId, handler) {
    const zone = document.getElementById(zoneId);
    const input = document.getElementById(inputId);

    zone.addEventListener('click', () => input.click());
    zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('dragover'); });
    zone.addEventListener('dragleave', () => zone.classList.remove('dragover'));
    zone.addEventListener('drop', e => {
        e.preventDefault();
        zone.classList.remove('dragover');
        if (e.dataTransfer.files.length) handler(e.dataTransfer.files[0]);
    });
    input.addEventListener('change', () => { if (input.files.length) handler(input.files[0]); });
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

async function handleStampFile(file) {
    const zone = document.getElementById('drop-zone');
    setDropZoneLoading(zone, true, 'Hashing ' + file.name + '...');

    const hash = await hashFile(file);
    currentHash = hash;

    setDropZoneLoading(zone, false);
    document.getElementById('file-hash').textContent = '0x' + hash;
    document.getElementById('file-name').textContent = file.name;
    document.getElementById('file-size').textContent = formatSize(file.size);
    document.getElementById('hash-result').classList.remove('hidden');
    document.getElementById('stamp-form').classList.remove('hidden');
    document.getElementById('stamp-result').classList.add('hidden');
}

async function handleVerifyFile(file) {
    const zone = document.getElementById('verify-drop-zone');
    const resultEl = document.getElementById('verify-result');
    resultEl.classList.add('hidden');

    setDropZoneLoading(zone, true, 'Hashing ' + file.name + '...');
    const hash = await hashFile(file);
    document.getElementById('verify-hash-input').value = '0x' + hash;

    setDropZoneLoading(zone, true, 'Looking up hash on-chain...');
    await doVerify('0x' + hash);
    setDropZoneLoading(zone, false);
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
        });
    });

    // Stamp button
    document.getElementById('btn-stamp').addEventListener('click', doStamp);

    // Verify button
    document.getElementById('btn-verify').addEventListener('click', () => {
        const input = document.getElementById('verify-hash-input').value.trim();
        if (input) doVerify(input);
    });

    // Enter key on verify input
    document.getElementById('verify-hash-input').addEventListener('keydown', e => {
        if (e.key === 'Enter') {
            const input = e.target.value.trim();
            if (input) doVerify(input);
        }
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

async function connectWallet() {
    if (!window.ethereum) {
        alert('Please install MetaMask or another Web3 wallet');
        return;
    }
    try {
        const accounts = await window.ethereum.request({ method: 'eth_requestAccounts' });
        walletAddress = accounts[0];
        document.getElementById('btn-connect').classList.add('hidden');
        const addrEl = document.getElementById('wallet-address');
        addrEl.textContent = walletAddress.slice(0, 6) + '...' + walletAddress.slice(-4);
        addrEl.classList.remove('hidden');
    } catch (e) {
        console.error('Wallet connection failed:', e);
    }
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

        // Try client-side signing with MetaMask
        if (window.ethereum && walletAddress && CONTRACT_ADDRESS) {
            try {
                const result = await stampOnChain(currentHash, metadataHash, walrusBlobId, description);
                showStampResult(resultEl, true, result);
                return;
            } catch (e) {
                console.error('On-chain stamp failed:', e);
            }
        }

        // Fallback: server-side stamp
        const resp = await fetch(API + '/api/stamp', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                fileHash: '0x' + currentHash,
                metadataHash: metadataHash,
                walrusBlobId: walrusBlobId,
                description: description
            })
        });
        const data = await resp.json();
        if (data.success) {
            showStampResult(resultEl, true, data);
        } else if (data.unsigned) {
            showStampResult(resultEl, true, {
                message: 'Connect wallet to sign transaction',
                ...data
            });
        } else {
            showStampResult(resultEl, false, data);
        }
    } catch (e) {
        showStampResult(resultEl, false, {error: e.message});
    } finally {
        btn.classList.remove('loading');
        btn.disabled = false;
    }
}

async function stampOnChain(fileHash, metadataHash, walrusBlobId, description) {
    // Use ethers.js-free approach with raw eth calls
    const iface = new ethers.Interface(STAMP_ABI);
    const data = iface.encodeFunctionData('stamp', [
        '0x' + fileHash,
        metadataHash,
        walrusBlobId,
        description
    ]);

    const txHash = await window.ethereum.request({
        method: 'eth_sendTransaction',
        params: [{
            from: walletAddress,
            to: CONTRACT_ADDRESS,
            data: data,
            gas: '0x493E0' // 300000
        }]
    });

    return {txHash: txHash, chain: 'evm'};
}

function showStampResult(el, success, data) {
    el.classList.remove('hidden');
    if (success) {
        let html = '<div class="result-success">';
        html += '<div class="result-row"><span class="result-label">Status</span><span class="result-value" style="color:var(--success)">&#10003; Stamped</span></div>';
        if (data.txHash) {
            html += '<div class="result-row"><span class="result-label">Transaction</span><span class="result-value">' + data.txHash.slice(0, 10) + '...' + data.txHash.slice(-8) + '</span></div>';
        }
        if (data.blockNumber) {
            html += '<div class="result-row"><span class="result-label">Block</span><span class="result-value">' + data.blockNumber + '</span></div>';
        }
        if (data.message) {
            html += '<div class="result-row"><span class="result-label">Note</span><span class="result-value">' + data.message + '</span></div>';
        }
        html += '</div>';
        el.innerHTML = html;
    } else {
        el.innerHTML = '<div class="result-error">&#10007; ' + (data.error || 'Stamp failed') + '</div>';
    }
}

// ============ Verify Action ============

async function doVerify(input) {
    const btn = document.getElementById('btn-verify');
    const resultEl = document.getElementById('verify-result');
    btn.classList.add('loading');
    resultEl.classList.add('hidden');

    try {
        let hash = input;

        // Check if it's an ENS name
        if (input.includes('.binarystamp.eth') || input.includes('.eth')) {
            const ensResp = await fetch(API + '/api/ens/resolve/' + encodeURIComponent(input));
            const ensData = await ensResp.json();
            if (ensData.resolved) {
                showVerifyResult(resultEl, ensData);
                return;
            }
        }

        // Clean up hash
        if (!hash.startsWith('0x')) hash = '0x' + hash;

        const resp = await fetch(API + '/api/lookup?hash=' + encodeURIComponent(hash));
        const data = await resp.json();
        showVerifyResult(resultEl, data);
    } catch (e) {
        resultEl.classList.remove('hidden');
        resultEl.innerHTML = '<div class="result-error">&#10007; ' + e.message + '</div>';
    } finally {
        btn.classList.remove('loading');
    }
}

function showVerifyResult(el, data) {
    el.classList.remove('hidden');
    if (data.found) {
        let html = '<div class="result-success">';
        html += '<div class="result-row"><span class="result-label">Status</span><span class="result-value" style="color:var(--success)">&#10003; Found</span></div>';
        html += '<div class="result-row"><span class="result-label">Owner</span><span class="result-value">' + (data.owner || 'N/A') + '</span></div>';
        if (data.timestamp || data.firstStampedAt) {
            const ts = data.timestamp || data.firstStampedAt;
            const date = new Date(parseInt(ts) * 1000).toLocaleString();
            html += '<div class="result-row"><span class="result-label">First Stamped</span><span class="result-value">' + date + '</span></div>';
        }
        if (data.stampCount) {
            html += '<div class="result-row"><span class="result-label">Total Stamps</span><span class="result-value">' + data.stampCount + '</span></div>';
        }
        if (data.walrusBlobId) {
            html += '<div class="result-row"><span class="result-label">Walrus Blob</span><span class="result-value">' + data.walrusBlobId + '</span></div>';
        }
        if (data.description) {
            html += '<div class="result-row"><span class="result-label">Description</span><span class="result-value">' + escapeHtml(data.description) + '</span></div>';
        }
        if (data.source) {
            html += '<div class="result-row"><span class="result-label">Source</span><span class="result-value">' + data.source + '</span></div>';
        }
        // Show stamps history if available
        if (data.stamps && data.stamps.length > 1) {
            html += '<div style="margin-top:12px;font-size:12px;color:var(--text-muted)">History (' + data.stamps.length + ' stamps)</div>';
            for (const s of data.stamps) {
                const d = new Date(parseInt(s.timestamp) * 1000).toLocaleString();
                html += '<div class="result-row"><span class="result-label">#' + s.stampNumber + '</span><span class="result-value">' + s.owner.slice(0,8) + '... @ ' + d + '</span></div>';
            }
        }
        html += '</div>';
        el.innerHTML = html;
    } else {
        el.innerHTML = '<div class="result-not-found"><div class="result-row"><span class="result-label">Status</span><span class="result-value">Not found — this hash has not been stamped</span></div></div>';
    }
}

// ============ AI Agent ============

async function doAiAsk() {
    const hashInput = document.getElementById('ai-hash').value.trim();
    const question = document.getElementById('ai-question').value.trim();
    if (!question) return;

    const btn = document.getElementById('btn-ai-ask');
    const messages = document.getElementById('ai-messages');
    btn.classList.add('loading');

    // Add user message
    const userMsg = document.createElement('div');
    userMsg.className = 'ai-message user';
    userMsg.textContent = question;
    messages.appendChild(userMsg);
    messages.scrollTop = messages.scrollHeight;

    document.getElementById('ai-question').value = '';

    try {
        const resp = await fetch(API + '/api/ai/provenance', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                fileHash: hashInput || currentHash || '',
                question: question
            })
        });
        const data = await resp.json();

        const aiMsg = document.createElement('div');
        aiMsg.className = 'ai-message assistant';
        aiMsg.innerHTML = simpleMarkdown(data.answer || 'No data available for this hash.');
        messages.appendChild(aiMsg);
    } catch (e) {
        const errMsg = document.createElement('div');
        errMsg.className = 'ai-message assistant';
        errMsg.textContent = 'Error: ' + e.message;
        messages.appendChild(errMsg);
    } finally {
        btn.classList.remove('loading');
        messages.scrollTop = messages.scrollHeight;
    }
}

// ============ Health Check ============

async function checkHealth() {
    try {
        const resp = await fetch(API + '/api/health');
        const data = await resp.json();
        if (data.evm) document.getElementById('badge-evm').style.borderColor = 'var(--success)';
        if (data.subgraph) document.getElementById('badge-graph').style.borderColor = 'var(--success)';
        if (data.walrus) document.getElementById('badge-walrus').style.borderColor = 'var(--success)';
        if (data.ai) document.getElementById('badge-ens').style.borderColor = 'var(--success)';
        // Show AI status in footer
        if (data.ai) {
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
