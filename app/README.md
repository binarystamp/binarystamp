# BinaryStamp — Technical Documentation

## Architecture Overview

BinaryStamp is a multi-chain file provenance registry. Users hash files client-side and register the hash on-chain. The system spans EVM (Base), Sui, Walrus, ENS, and The Graph.

### Components

```
app/
├── app.py                  # Flask backend — API routes, contract interaction
├── ens_resolver.py         # ENS CCIP-Read gateway (EIP-3668)
├── requirements.txt        # Python dependencies
├── Dockerfile              # Alpine-based container
├── frontend/
│   ├── index.html          # Single-page UI
│   ├── style.css           # ASTA design, light/dark mode
│   └── app.js              # Client-side hashing, wallet, API calls
├── contracts/
│   ├── sui/
│   │   └── BinaryStamp.move    # Sui Move contract
│   └── evm/
│       ├── BinaryStamp.sol         # Solidity registry (Base)
│       ├── BinaryStampResolver.sol # ENS CCIP-Read resolver
│       ├── abi.json                # Compiled ABI
│       └── subgraph/               # The Graph subgraph
│           ├── schema.graphql
│           ├── subgraph.yaml
│           └── src/mapping.ts
├── scripts/
│   ├── deploy_evm.py          # Deploy EVM contract
│   ├── deploy_resolver.py     # Deploy ENS resolver
│   ├── deploy_sui.py          # Generate Sui Move package
│   └── update_resolver_urls.py # Update resolver gateway URL
└── tests/
    └── test_api.py             # API tests (11 tests)
```

## Setup

### Prerequisites

- Python 3.12+
- Node.js 18+ (for Solidity compiler and Graph CLI)
- A funded wallet on Base Sepolia
- (Optional) Sui CLI for Move contract deployment

### Installation

```bash
cd app
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
```

### Configuration

Copy `.env.example` to `.env` and fill in:

| Variable | Description |
|----------|-------------|
| `EVM_RPC_URL` | Base Sepolia RPC endpoint |
| `CONTRACT_ADDRESS` | Deployed BinaryStamp contract |
| `PRIVATE_KEY` | Wallet private key for server-side stamping |
| `SUBGRAPH_URL` | The Graph subgraph query endpoint |
| `WALRUS_AGGREGATOR` | Walrus aggregator URL |
| `WALRUS_PUBLISHER` | Walrus publisher URL |
| `ANTHROPIC_API_KEY` | Claude API key for AI agent |
| `MAINNET_RPC_URL` | Ethereum mainnet RPC (for ENS resolver) |
| `MAINNET_PRIVATE_KEY` | Mainnet wallet (for ENS resolver deployment) |

### Running

```bash
# Development
./_start dev

# Production
./_start up

# Tests
./_start test
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Frontend UI |
| `GET` | `/api/health` | Service health check |
| `POST` | `/api/hash` | Hash uploaded file (multipart) |
| `GET` | `/api/lookup?hash=0x...` | Look up file hash (subgraph + contract) |
| `POST` | `/api/stamp` | Register hash on-chain |
| `POST` | `/api/walrus/store` | Store metadata on Walrus |
| `GET` | `/api/walrus/fetch/<blobId>` | Fetch metadata from Walrus |
| `POST` | `/api/subgraph/query` | Proxy GraphQL to The Graph |
| `POST` | `/api/ai/provenance` | AI provenance analysis |
| `GET` | `/api/ens/resolve/<name>` | Resolve ENS subdomain |
| `POST` | `/api/ens/resolve` | CCIP-Read gateway endpoint |

## Smart Contracts

### EVM — BinaryStamp.sol (Base Sepolia)

- `stamp(bytes32 fileHash, bytes32 metadataHash, string walrusBlobId, string description)` — Register a file hash
- `transferStamp(bytes32 fileHash, address newOwner)` — Transfer ownership
- `getLatestStamp(bytes32 fileHash)` — Get latest stamp data
- `isStamped(bytes32 fileHash)` — Check if hash exists
- Events: `StampCreated`, `StampTransferred` (indexed by The Graph)

### EVM — BinaryStampResolver.sol (Ethereum Mainnet)

CCIP-Read (EIP-3668) resolver for `binarystamp.eth`. Redirects all subdomain lookups to the gateway at `https://binarystamp.com/api/ens/resolve`.

Supports: `addr(bytes32)`, `text(bytes32,string)`, `contenthash(bytes32)`, `resolve(bytes,bytes)`.

### Sui — BinaryStamp.move

- `stamp(registry, file_hash, metadata_hash, walrus_blob_id, description, clock, ctx)` — Register a file hash
- `transfer_stamp(stamp, new_owner, clock, ctx)` — Transfer ownership
- Shared `Registry` and `StampRecord` objects for lookups

## The Graph Subgraph

Indexes `StampCreated` and `StampTransferred` events from the EVM contract. Entities:

- `Stamp` — Individual stamp records
- `Transfer` — Ownership transfer history
- `FileHashLookup` — Quick lookup by file hash
- `OwnerStats` — Per-owner stamp counts

## ENS Integration

`binarystamp.eth` uses a custom CCIP-Read resolver:

- `<sha256hash>.binarystamp.eth` resolves to the file's owner address
- `<number>.binarystamp.eth` resolves to the owner of stamp #N
- Resolution queries The Graph subgraph via the gateway

## Deployment

### Deploy EVM Contract

```bash
cd app
./venv/bin/python scripts/deploy_evm.py
```

### Deploy ENS Resolver

```bash
./venv/bin/python scripts/deploy_resolver.py
# Then set binarystamp.eth resolver at app.ens.domains
```

### Deploy Subgraph

```bash
cd app/contracts/evm/subgraph
npm install
npx graph codegen
npx graph build
npx graph auth --studio <DEPLOY_KEY>
npx graph deploy --studio binarystamp
```

### Deploy Sui Contract

```bash
cd sui-package
./deploy.sh
```
