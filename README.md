# BinaryStamp

Prove file ownership on-chain. Drop a file, get a cryptographic stamp.

BinaryStamp lets anyone register the SHA-256 hash of any file on a blockchain, creating a timestamped, immutable record of ownership. Verify any file's provenance instantly.

## Features

- **Drag & Drop Stamping** — Hash any file client-side, register it on-chain in one click
- **Multi-Chain** — Stamps on Base (EVM) with Sui support
- **Walrus Storage** — Metadata stored on Walrus decentralized blob storage
- **ENS Resolution** — Resolve `<hash>.binarystamp.eth` to its owner via CCIP-Read
- **The Graph Indexing** — All stamps indexed for instant lookups and history
- **AI Provenance Agent** — Ask questions about any file's ownership chain
- **Ownership Transfers** — Transfer stamp ownership to another address

## Quick Start

```bash
git clone https://github.com/binarystamp/binarystamp.git
cd binarystamp
cp .env.example .env    # Configure your keys
./_start up             # Start the service
```

Open http://localhost:8082

## How It Works

1. **Hash** — File is SHA-256 hashed entirely in-browser (never uploaded)
2. **Store** — Optional metadata stored on Walrus
3. **Stamp** — Hash + metadata registered on-chain (Base / Sui)
4. **Verify** — Anyone can check a file's hash against the on-chain registry
5. **Resolve** — `<hash>.binarystamp.eth` resolves to the owner address

## Architecture

```
User drops file
    |
    v
SHA-256 (client-side)
    |
    +---> Walrus (metadata storage)
    |
    +---> EVM Contract (Base) ---> The Graph (indexing)
    |
    +---> Sui Contract (Move)
    |
    v
ENS CCIP-Read Gateway <--- binarystamp.eth subdomains
    |
    v
AI Agent (provenance analysis via The Graph)
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Vanilla JS, CSS (light/dark mode) |
| Backend | Python, Flask, Gunicorn |
| EVM Contract | Solidity (Base Sepolia) |
| Sui Contract | Move |
| Storage | Walrus (decentralized blobs) |
| Indexing | The Graph (subgraph) |
| ENS | CCIP-Read (EIP-3668) offchain resolver |
| AI | Claude API |

## Deployed Contracts

| Contract | Chain | Address |
|----------|-------|---------|
| BinaryStamp Registry | Base Sepolia | [`0x5969D7558d3409ac70ebdF24063AeC7257d0aCe3`](https://sepolia.basescan.org/address/0x5969D7558d3409ac70ebdF24063AeC7257d0aCe3) |
| ENS CCIP-Read Resolver | Ethereum Mainnet | [`0x61DF09Bf03f5693f8928F3aF9364EbC3a4D61D50`](https://etherscan.io/address/0x61DF09Bf03f5693f8928F3aF9364EbC3a4D61D50) |
| Subgraph | The Graph (Base Sepolia) | [`binarystamp/binarystamp`](https://api.studio.thegraph.com/query/1757003/binarystamp/v0.0.1) |
| BinaryStamp (Sui Move) | Sui Testnet | [`0xbc097815add0220a26bc2dff1b5b1184924828d9f14cfd835f2ccc25b8faabf7`](https://suiscan.xyz/testnet/object/0xbc097815add0220a26bc2dff1b5b1184924828d9f14cfd835f2ccc25b8faabf7) |
| ENS Name | Ethereum Mainnet | [`binarystamp.eth`](https://app.ens.domains/binarystamp.eth) |

## Links

- Website: https://binarystamp.com
- ENS: binarystamp.eth
- Twitter: https://x.com/binarystamp

## License

MIT
