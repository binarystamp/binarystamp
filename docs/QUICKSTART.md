# Quickstart

Get BinaryStamp running locally and stamp your first file.

## 1. Requirements

- **Docker** (recommended), or **Python 3.12+**
- **Node.js 18+** — only if you intend to rebuild the Sui bundle or run the
  frontend tests. The bundle is committed, so a plain run does not need it.
- A **browser wallet**:
  - MetaMask (or any EIP-1193 wallet) to stamp on Base Sepolia
  - A Wallet-Standard Sui wallet to stamp on Sui testnet

You only need a wallet for the chain you actually use. Verifying and the AI
agent work without one.

## 2. Configure

```bash
git clone https://github.com/binarystamp/binarystamp.git
cd binarystamp
cp .env.example .env
```

`.env.example` ships with the deployed testnet contract addresses, so it works
as-is for local use. Two values are blank and worth filling in:

| Variable | Why |
|----------|-----|
| `SUBGRAPH_URL` | Without it, lookups fall back to reading the contract directly — slower, and no stamp history |
| `MAINNET_RPC_URL` | Without it, owners show as plain addresses instead of their ENS names |
| `ANTHROPIC_API_KEY` | Without it, the AI agent returns structured data instead of prose |

Leave `PRIVATE_KEY` empty. It only enables server-side stamping, which
registers stamps to the *server's* address rather than the user's — see
[Server-side stamping](#server-side-stamping) below.

## 3. Run

```bash
./_start up
```

Open <http://localhost:8082>.

`./_start up` uses Docker Compose when available and falls back to a local
virtualenv otherwise. Other commands:

```bash
./_start status     # is it running?
./_start logs -f    # follow logs
./_start test       # run the test suite
./_start build      # rebuild the Sui bundle and container
./_start down       # stop
./_start clean      # remove venv, containers, images
```

## 4. Check a file

Drop any file onto the drop zone, or paste a SHA-256 hash. The file is hashed
with SHA-256 **in your browser** — it is never uploaded. The hash is then
looked up across The Graph, the Base contract, and the Sui event log.

There is a single screen, and what it offers depends on what it finds.

### If the file is already stamped

You see who owns it, when it was stamped, which chain it lives on, and any
description or Walrus metadata attached to it. If ownership has moved since,
that is noted too.

If the owner has set a primary ENS name it is shown above their address —
`vitalik.eth` rather than `0xd8dA…6045`. The address stays visible, because a
reverse record is set by whoever controls the address and is a claim rather
than proof. This needs `MAINNET_RPC_URL`, and applies to Base owners only.

Two things appear below the result:

- **Transfer ownership** — hand the stamp to another address. Sign with the
  wallet that currently owns it. Addresses are validated per chain: 20 bytes
  for Base, 32 for Sui.
- **Ask about this file's history** — a provenance question answered from the
  indexed data. Only shown when `ANTHROPIC_API_KEY` is configured.

### If the file is not stamped

You get a **Claim this file** form:

1. Optionally add a description, and tick *Store metadata on Walrus*.
2. Choose **Base (EVM)**, **Sui**, or **Both**.
3. Click **Register Stamp**. Your wallet asks you to sign.

The result links to the transaction on a block explorer. With **Both**, each
chain is reported separately — if one fails, the other still shows.

Immediately after stamping the file reads as *awaiting confirmation*: the
transaction is on-chain but the indexer has not caught up, so the registry
would still report it unclaimed. **Check again** re-queries. The claim form
stays closed in the meantime so you cannot stamp the same file twice.

You need testnet funds to pay gas:

- Base Sepolia ETH — <https://www.alchemy.com/faucets/base-sepolia>
- Sui testnet SUI — <https://faucet.sui.io>

### ENS names

Pasting `<hash>.binarystamp.eth` resolves the name to its owner. A name is not
a hash, so no claim or transfer is offered for one.

## Server-side stamping

`POST /api/stamp` will sign with `PRIVATE_KEY` if one is set. This is meant for
scripted or API use. Be aware of what it means: the stamp is owned by the key
that signed it, so a stamp created this way belongs to the server, not to the
person who uploaded the file. For a provenance record that is usually the wrong
answer. The browser UI always signs with the user's own wallet.

## Troubleshooting

**"No Ethereum wallet found" / "No Sui wallet found"** — the extension for that
chain is missing or locked. Unlock it and reload.

**Wallet prompts to switch network** — stamping is Base Sepolia only. A
transaction sent on the wrong network is lost, so the app switches first, and
offers to add the network if your wallet does not know it.

**Sui stamp fails with an object error** — `SUI_PACKAGE_ID` and
`SUI_REGISTRY_ID` must both point at the *same* publish. A redeploy changes
both. See [DEPLOYMENT.md](DEPLOYMENT.md#redeploying-the-sui-package).

**Lookups return `"source": "none"`** — `SUBGRAPH_URL` is unset and the hash is
not in the contract. Check `/api/health`.

## Next

- [API.md](API.md) — HTTP reference
- [DEPLOYMENT.md](DEPLOYMENT.md) — production and contract deployment
- [../app/README.md](../app/README.md) — architecture and internals
