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

## Links

- Website: https://binarystamp.com
- ENS: binarystamp.eth
- Twitter: https://x.com/binarystamp

## License

MIT
