// ============ On-chain interaction: EVM (Base) and Sui ============
//
// EVM calldata is encoded by hand so the frontend stays dependency-free.
// Sui needs BCS + programmable transaction building, so it lazily loads the
// locally bundled SDK (vendor/sui.js) the first time a Sui stamp is made.

// ============ Config ============

const EVM_CONTRACT = '0x5969D7558d3409ac70ebdF24063AeC7257d0aCe3';
const EVM_CHAIN_ID = '0x14a34'; // Base Sepolia (84532)

const SUI_PACKAGE = '0xc5487e68a3c6b4cb5a34992c976017178d52b865580d57943e660208d19abc9b';
const SUI_REGISTRY = '0x2ba5935995d77fcae22d4403084a8f949da03ed49fbcad053cbd4df51c9a713e';
const SUI_REGISTRY_VERSION = 698589285; // initial shared version, from the publish tx
const SUI_CLOCK = '0x0000000000000000000000000000000000000000000000000000000000000006';
const SUI_CLOCK_VERSION = 1;
const SUI_CHAIN = 'sui:testnet';

// Function selectors — first 4 bytes of keccak256(signature).
// stamp(bytes32,bytes32,string,string) / transferStamp(bytes32,address)
const SELECTOR_STAMP = '3fa348a4';
const SELECTOR_TRANSFER = '19ee075c';

// ============ EVM ABI encoding ============

function strip0x(hex) {
    return hex.startsWith('0x') ? hex.slice(2) : hex;
}

function word(n) {
    return n.toString(16).padStart(64, '0');
}

function utf8Hex(text) {
    const bytes = new TextEncoder().encode(text);
    let hex = '';
    for (const b of bytes) hex += b.toString(16).padStart(2, '0');
    return hex;
}

// A dynamic `string` argument: length word, then the bytes right-padded to 32.
function encodeString(text) {
    const hex = utf8Hex(text);
    const byteLength = hex.length / 2;
    const padded = hex.padEnd(Math.ceil(byteLength / 32) * 64, '0');
    return word(byteLength) + padded;
}

function encodeStampCall(fileHash, metadataHash, walrusBlobId, description) {
    const blob = encodeString(walrusBlobId);
    const desc = encodeString(description);
    // Head is 4 words: 2 static bytes32 plus 2 offsets into the tail.
    const offsetBlob = 4 * 32;
    const offsetDesc = offsetBlob + blob.length / 2;

    return '0x' + SELECTOR_STAMP
        + strip0x(fileHash).padStart(64, '0')
        + strip0x(metadataHash).padStart(64, '0')
        + word(offsetBlob)
        + word(offsetDesc)
        + blob
        + desc;
}

function encodeTransferCall(fileHash, newOwner) {
    return '0x' + SELECTOR_TRANSFER
        + strip0x(fileHash).padStart(64, '0')
        + strip0x(newOwner).toLowerCase().padStart(64, '0');
}

// ============ EVM wallet ============

async function connectEvmWallet() {
    if (!window.ethereum) {
        throw new Error('No Ethereum wallet found. Install MetaMask to stamp on Base.');
    }
    const accounts = await window.ethereum.request({method: 'eth_requestAccounts'});
    if (!accounts.length) throw new Error('No account authorized');
    return accounts[0];
}

// Base Sepolia only — a stamp sent to the wrong network is silently lost.
async function ensureBaseNetwork() {
    const current = await window.ethereum.request({method: 'eth_chainId'});
    if (current === EVM_CHAIN_ID) return;

    try {
        await window.ethereum.request({
            method: 'wallet_switchEthereumChain',
            params: [{chainId: EVM_CHAIN_ID}],
        });
    } catch (e) {
        // 4902 = chain unknown to the wallet, so offer to add it.
        if (e.code === 4902) {
            await window.ethereum.request({
                method: 'wallet_addEthereumChain',
                params: [{
                    chainId: EVM_CHAIN_ID,
                    chainName: 'Base Sepolia',
                    nativeCurrency: {name: 'Ether', symbol: 'ETH', decimals: 18},
                    rpcUrls: ['https://sepolia.base.org'],
                    blockExplorerUrls: ['https://sepolia.basescan.org'],
                }],
            });
        } else {
            throw e;
        }
    }
}

async function stampOnEvm(address, fileHash, metadataHash, walrusBlobId, description) {
    await ensureBaseNetwork();
    const txHash = await window.ethereum.request({
        method: 'eth_sendTransaction',
        params: [{
            from: address,
            to: EVM_CONTRACT,
            data: encodeStampCall(fileHash, metadataHash, walrusBlobId, description),
        }],
    });
    return {chain: 'evm', txHash: txHash, explorer: 'https://sepolia.basescan.org/tx/' + txHash};
}

async function transferOnEvm(address, fileHash, newOwner) {
    await ensureBaseNetwork();
    const txHash = await window.ethereum.request({
        method: 'eth_sendTransaction',
        params: [{
            from: address,
            to: EVM_CONTRACT,
            data: encodeTransferCall(fileHash, newOwner),
        }],
    });
    return {chain: 'evm', txHash: txHash, explorer: 'https://sepolia.basescan.org/tx/' + txHash};
}

// ============ Sui wallet (Wallet Standard) ============

// Wallets that loaded before us are queued on navigator.wallets; wallets that
// load later answer the app-ready event. Ask both ways.
function discoverSuiWallets() {
    const found = [];
    const api = {
        register(...wallets) {
            found.push(...wallets);
            return () => {};
        },
    };

    const queued = window.navigator && window.navigator.wallets;
    if (queued && typeof queued.push === 'function') {
        try {
            queued.push(api.register);
        } catch (e) {
            console.warn('navigator.wallets registration failed:', e);
        }
    }

    window.dispatchEvent(new CustomEvent('wallet-standard:app-ready', {detail: api}));

    return found.filter(w => w.features && (
        w.features['sui:signAndExecuteTransaction'] ||
        w.features['sui:signAndExecuteTransactionBlock']
    ));
}

async function connectSuiWallet() {
    const wallets = discoverSuiWallets();
    if (!wallets.length) {
        throw new Error('No Sui wallet found. Install the Sui Wallet extension to stamp on Sui.');
    }

    const wallet = wallets[0];
    const result = await wallet.features['standard:connect'].connect();
    const accounts = (result && result.accounts) || wallet.accounts || [];
    if (!accounts.length) throw new Error('No Sui account authorized');

    return {wallet: wallet, account: accounts[0], address: accounts[0].address};
}

let suiSdk = null;

async function loadSuiSdk() {
    if (!suiSdk) suiSdk = await import('./vendor/sui.js');
    return suiSdk;
}

function hexToBytes(hex) {
    const clean = strip0x(hex);
    const out = [];
    for (let i = 0; i < clean.length; i += 2) out.push(parseInt(clean.slice(i, i + 2), 16));
    return out;
}

async function buildSuiStampTx(fileHash, metadataHash, walrusBlobId, description) {
    const {Transaction} = await loadSuiSdk();
    const tx = new Transaction();

    // Shared objects are passed by explicit ref so the transaction builds
    // without a round-trip to a fullnode.
    tx.moveCall({
        target: SUI_PACKAGE + '::stamp::stamp',
        arguments: [
            tx.sharedObjectRef({
                objectId: SUI_REGISTRY,
                initialSharedVersion: SUI_REGISTRY_VERSION,
                mutable: true,
            }),
            tx.pure.vector('u8', hexToBytes(fileHash)),
            tx.pure.vector('u8', hexToBytes(metadataHash)),
            tx.pure.string(walrusBlobId),
            tx.pure.string(description),
            tx.sharedObjectRef({
                objectId: SUI_CLOCK,
                initialSharedVersion: SUI_CLOCK_VERSION,
                mutable: false,
            }),
        ],
    });

    return tx;
}

async function stampOnSui(connection, fileHash, metadataHash, walrusBlobId, description) {
    const tx = await buildSuiStampTx(fileHash, metadataHash, walrusBlobId, description);
    tx.setSender(connection.address);

    const wallet = connection.wallet;
    const features = wallet.features;
    let result;

    if (features['sui:signAndExecuteTransaction']) {
        result = await features['sui:signAndExecuteTransaction'].signAndExecuteTransaction({
            transaction: tx,
            account: connection.account,
            chain: SUI_CHAIN,
        });
    } else {
        result = await features['sui:signAndExecuteTransactionBlock'].signAndExecuteTransactionBlock({
            transactionBlock: tx,
            account: connection.account,
            chain: SUI_CHAIN,
        });
    }

    const digest = result.digest;
    return {chain: 'sui', txHash: digest, explorer: 'https://suiscan.xyz/testnet/tx/' + digest};
}

// Sui transfers act on the Stamp object itself, so the caller has to know its
// object ID. The backend resolves that from the owner address plus file hash.
async function transferOnSui(connection, stampObjectId, newOwner) {
    const {Transaction} = await loadSuiSdk();
    const tx = new Transaction();

    tx.moveCall({
        target: SUI_PACKAGE + '::stamp::transfer_stamp',
        arguments: [
            tx.object(stampObjectId),
            tx.pure.address(newOwner),
            tx.sharedObjectRef({
                objectId: SUI_CLOCK,
                initialSharedVersion: SUI_CLOCK_VERSION,
                mutable: false,
            }),
        ],
    });
    tx.setSender(connection.address);

    const features = connection.wallet.features;
    let result;

    if (features['sui:signAndExecuteTransaction']) {
        result = await features['sui:signAndExecuteTransaction'].signAndExecuteTransaction({
            transaction: tx,
            account: connection.account,
            chain: SUI_CHAIN,
        });
    } else {
        result = await features['sui:signAndExecuteTransactionBlock'].signAndExecuteTransactionBlock({
            transactionBlock: tx,
            account: connection.account,
            chain: SUI_CHAIN,
        });
    }

    const digest = result.digest;
    return {chain: 'sui', txHash: digest, explorer: 'https://suiscan.xyz/testnet/tx/' + digest};
}

export {
    EVM_CONTRACT,
    SUI_PACKAGE,
    SUI_REGISTRY,
    encodeStampCall,
    encodeTransferCall,
    connectEvmWallet,
    stampOnEvm,
    transferOnEvm,
    discoverSuiWallets,
    connectSuiWallet,
    stampOnSui,
    transferOnSui,
};
