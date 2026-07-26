# BinaryStamp

Prove file ownership on-chain. Drop a file, get a cryptographic stamp.

BinaryStamp lets anyone register the SHA-256 hash of any file on a blockchain, creating a timestamped, immutable record of ownership. Verify any file's provenance instantly.

## Features

- **One Screen** — Drop a file: if it is claimed you see by whom and when, if not you can claim it
- **Client-Side Hashing** — SHA-256 in the browser; the file itself is never uploaded
- **Multi-Chain** — Stamp on Base (EVM), Sui, or both at once — signed by your own wallet
- **Walrus Storage** — Metadata stored on Walrus decentralized blob storage
- **ENS Resolution** — Every stamp gets a real ENS name resolving to its owner via CCIP-Read
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

Stamping needs a browser wallet: MetaMask for Base, a Wallet-Standard Sui wallet
for Sui. Your wallet signs the transaction, so the stamp is owned by you.

## How It Works

1. **Hash** — File is SHA-256 hashed entirely in-browser (never uploaded)
2. **Check** — The hash is looked up across The Graph, Base, and Sui
3. **Store** — Optional metadata stored on Walrus
4. **Stamp** — Unclaimed hashes can be registered on-chain (Base / Sui)
5. **Transfer** — Stamps can be handed to another address
6. **Resolve** — `<base36-hash>.binarystamp.eth` and `<number>.binarystamp.eth` resolve to the owner

## Architecture

```
User drops file
    |
    v
SHA-256 (client-side)
    |
    v
Lookup ---> The Graph ---> EVM Contract (Base) ---> Sui event log
    |
    +-- stamped ------> owner, date, metadata
    |                   + transfer ownership
    |                   + AI provenance agent
    |
    +-- unstamped ----> claim it
                        |
                        +---> Walrus (metadata storage)
                        |
                        +---> EVM Contract (Base) ---> The Graph
                        |
                        +---> Sui Contract (Move)

ENS CCIP-Read Gateway <--- binarystamp.eth subdomains
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
| BinaryStamp (Sui Move) | Sui Testnet | [`0xc5487e68a3c6b4cb5a34992c976017178d52b865580d57943e660208d19abc9b`](https://suiscan.xyz/testnet/object/0xc5487e68a3c6b4cb5a34992c976017178d52b865580d57943e660208d19abc9b) |
| Sui Registry (shared object) | Sui Testnet | [`0x2ba5935995d77fcae22d4403084a8f949da03ed49fbcad053cbd4df51c9a713e`](https://suiscan.xyz/testnet/object/0x2ba5935995d77fcae22d4403084a8f949da03ed49fbcad053cbd4df51c9a713e) |
| ENS Name | Ethereum Mainnet | [`binarystamp.eth`](https://app.ens.domains/binarystamp.eth) |

## Assets

Logo (512×512) and 16:9 splash screens in [`assets/`](assets/) — dark and light,
SVG plus PNG at 1x and 2x.

## Documentation

- [Presentation](docs/presentation/index.html) — what it is and why, in a few slides
- [Quickstart](docs/QUICKSTART.md) — running locally and stamping your first file
- [API Reference](docs/API.md) — HTTP endpoints
- [Deployment](docs/DEPLOYMENT.md) — production and contract deployment
- [Technical docs](app/README.md) — architecture and internals

## Links

- Website: https://binarystamp.com
- ENS: binarystamp.eth
- Twitter: https://x.com/binarystamp

## License

MIT
