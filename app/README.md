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
│   ├── app.js              # UI wiring, client-side hashing, API calls
│   ├── chains.js           # EVM calldata encoding + Sui wallet/transactions
│   └── vendor/
│       └── sui.js          # Bundled @mysten/sui (built, committed)
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
│   ├── sui-entry.js           # Bundle entry for the browser Sui SDK
│   ├── deploy_evm.py          # Deploy EVM contract
│   ├── deploy_resolver.py     # Deploy ENS resolver
│   ├── deploy_sui.py          # Generate Sui Move package
│   └── update_resolver_urls.py # Update resolver gateway URL
└── tests/
    ├── test_api.py            # API tests
    ├── test_sui.py            # Sui RPC parsing + routes (mocked)
    ├── test_chains.py         # EVM calldata vs eth_abi reference
    └── e2e/
        ├── frontend.mjs       # DOM harness driving the real app.js
        └── test_frontend.py   # Assertions over the harness output
```

### Frontend build

`frontend/chains.js` encodes EVM calldata by hand, so the EVM path needs no
dependencies. Sui needs BCS and programmable transaction building, so
`@mysten/sui` is bundled into `frontend/vendor/sui.js` and loaded lazily the
first time a Sui stamp is made. The bundle is committed — the app loads no
external resources at runtime.

Rebuild it after changing `scripts/sui-entry.js` or bumping `@mysten/sui`:

```bash
./_start build      # or: cd app && npm install && npm run build
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
| `SUI_RPC` | Sui JSON-RPC endpoint |
| `SUI_PACKAGE_ID` | Published Sui Move package |
| `SUI_REGISTRY_ID` | Shared `Registry` object — required to call `stamp()` |
| `SUI_EVENT_PAGE_SIZE` | Events per page when scanning for a hash (default 50) |
| `SUI_EVENT_MAX_PAGES` | Page cap for that scan (default 10) |

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
| `GET` | `/api/sui/lookup?hash=0x...` | Look up a file hash in the Sui event log |
| `GET` | `/api/sui/stamp-object?address=&hash=` | Find the Stamp object an address holds |
| `GET` | `/api/sui/config` | Sui package/registry IDs for the frontend |
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
- `transfer_stamp(stamp, new_owner, clock, ctx)` — Move a stamp to a new owner (takes the object by value)
- Shared `Registry` and `StampRecord` objects for lookups
- Unit tests in `sui-package/tests/stamp_tests.move` (`sui move test`)

Calling `stamp()` needs the shared `Registry` object created by the package's
`init` — it is not derivable from the package ID, so it is recorded in
`SUI_REGISTRY_ID` and in `frontend/chains.js` (with its initial shared version,
which the transaction builder needs to reference a shared object).

Sui has no hash index on-chain, so lookups scan `StampCreated` events via
`suix_queryEvents`. That is bounded by `SUI_EVENT_MAX_PAGES`; a busy registry
would want a real indexer.

## Ownership Transfers

The Verify view offers a transfer once a stamp is found, on whichever chain it
was found on.

**Base** — `transferStamp(bytes32,address)` reassigns `owner` on the latest
stamp for that hash. Storage is the source of truth, so this is complete.

**Sui** — ownership is the Sui object itself, so `transfer_stamp` takes the
`Stamp` by value and calls `transfer::public_transfer`. The frontend must know
the object ID, which `/api/sui/stamp-object` resolves from the owner address
plus file hash.

> The published testnet package still contains the earlier `transfer_stamp`,
> which took `&mut Stamp` and only reassigned the `owner` field — the object
> never moved, so the recipient could not use it. The fix is in
> `sui-package/sources/BinaryStamp.move` and needs a redeploy (Deploy Sui Move
> Contract workflow). Sui transfers will fail against the current package.

Because a stamp can move, `query_sui_stamp` replays `StampTransferred` events
and reports the current holder rather than the creator.

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
sui move test      # run the Move unit tests
./deploy.sh
```

Or run the **Deploy Sui Move Contract** GitHub Action, which builds, runs
`sui move test`, publishes, and prints the new `SUI_PACKAGE_ID` and
`SUI_REGISTRY_ID` to the job summary.

A redeploy mints a **new** package ID *and* a new Registry object. Update
`.env`, `.env.example`, the README table, and the `SUI_PACKAGE` /
`SUI_REGISTRY` / `SUI_REGISTRY_VERSION` constants in `frontend/chains.js`.
