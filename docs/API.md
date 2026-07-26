# API Reference

Base URL: `http://localhost:8082` locally, `https://binarystamp.com` in
production.

All request and response bodies are JSON unless noted. Errors return
`{"error": "<message>"}` with a non-2xx status.

| Status | Meaning |
|--------|---------|
| `400` | Missing or malformed parameter |
| `502` | An upstream service failed (RPC, Walrus, The Graph) |
| `503` | A feature is not configured on this deployment |

---

## Service

### `GET /api/health`

Reports which subsystems are configured. Each flag reflects configuration, not
live reachability.

```json
{
  "status": "ok",
  "evm": true,
  "subgraph": true,
  "walrus": true,
  "ai": true,
  "sui": true
}
```

`sui` is true only when **both** `SUI_PACKAGE_ID` and `SUI_REGISTRY_ID` are set
— `stamp()` takes the registry as an argument, so a package ID alone is not
enough to transact.

---

## Hashing

### `POST /api/hash`

Server-side SHA-256, as a fallback for clients that cannot hash locally. The
browser UI does **not** use this — it hashes with the Web Crypto API so the
file never leaves the machine.

Send `multipart/form-data` with a `file` field.

```json
{
  "hash": "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9",
  "hash_bytes32": "0xb94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"
}
```

---

## Lookups

### `GET /api/lookup?hash=0x...`

Resolves a file hash across every source, in order: The Graph, then the Base
contract, then the Sui event log. The `source` field says which answered.

```json
{
  "found": true,
  "owner": "0x1111111111111111111111111111111111111111",
  "timestamp": 1700000000,
  "metadataHash": "0x...",
  "walrusBlobId": "abc123",
  "description": "design doc",
  "source": "subgraph"
}
```

`source` is one of `subgraph`, `contract`, `sui`, or `none`. When nothing is
found: `{"found": false, "source": "none"}`.

### `GET /api/sui/lookup?hash=0x...`

Sui only. Scans `StampCreated` events for the hash, then replays
`StampTransferred` events so the reported `owner` is the **current** holder
rather than the creator. `transferred: true` is present when ownership moved.

```json
{
  "found": true,
  "source": "sui",
  "fileHash": "0xab...",
  "owner": "0xceee...",
  "timestamp": 1700000000,
  "metadataHash": "0x00...",
  "stampId": "0x...",
  "txDigest": "6ZPvuG...",
  "transferred": true
}
```

Sui has no on-chain index by file hash, so this is a bounded scan of the event
log — `SUI_EVENT_PAGE_SIZE` events per page, `SUI_EVENT_MAX_PAGES` pages. A
busy registry should use a real indexer instead.

Returns `503` if Sui is not configured, `502` if the RPC call fails.

### `GET /api/sui/stamp-object?address=0x...&hash=0x...`

Finds the `Stamp` object an address holds for a file hash.

Sui ownership is the object itself, so `transfer_stamp` takes the object rather
than the hash. The frontend calls this before building a transfer.

```json
{"found": true, "objectId": "0x..."}
```

### `GET /api/sui/config`

Identifiers the frontend needs to build a transaction.

```json
{
  "rpc": "https://fullnode.testnet.sui.io:443",
  "packageId": "0xc5487e68...",
  "registryId": "0x2ba59359...",
  "configured": true
}
```

---

## Stamping

### `POST /api/stamp`

```json
{
  "fileHash": "0xab...",
  "metadataHash": "0x00...",
  "walrusBlobId": "abc123",
  "description": "design doc"
}
```

Only `fileHash` is required.

Behaviour depends on whether the server holds a key:

- **`PRIVATE_KEY` set** — the server signs and broadcasts, then returns
  `{"success": true, "txHash": "0x...", "blockNumber": 123}`. The stamp is
  owned by the server's address.
- **`PRIVATE_KEY` unset** — returns `{"unsigned": true, ...}` echoing the
  fields plus `contractAddress`, for the caller to sign themselves.

> The browser never uses this endpoint to stamp. It builds and signs the
> transaction with the user's own wallet, so the stamp belongs to the user.
> Server-side signing is for scripted use where that distinction is acceptable.

---

## Walrus

### `POST /api/walrus/store`

```json
{"metadata": {"fileHash": "0xab...", "description": "design doc"}}
```

The metadata is serialised with sorted keys, so the hash is stable for
identical content.

```json
{"blobId": "abc123", "metadataHash": "<sha256 hex>", "size": 128}
```

### `GET /api/walrus/fetch/<blobId>`

Returns the stored JSON, or the raw bytes as `application/octet-stream` if the
blob is not JSON.

---

## The Graph

### `POST /api/subgraph/query`

Proxies GraphQL to the configured subgraph, keeping the endpoint out of the
client.

```json
{"query": "{ stamps(first: 5) { id owner } }", "variables": {}}
```

The subgraph's response is returned unchanged. Returns `503` when
`SUBGRAPH_URL` is unset.

---

## AI Agent

### `POST /api/ai/provenance`

```json
{"fileHash": "0xab...", "question": "Who owns this and when was it stamped?"}
```

`question` is optional. Provenance data is gathered from The Graph (falling
back to the contract) and passed to Claude for analysis.

```json
{
  "answer": "## File Not Found\n\nThe file with hash **0xab** has ...",
  "data": {"fileHash": "0xab", "found": false},
  "source": "ai+subgraph"
}
```

`answer` is Markdown. Without `ANTHROPIC_API_KEY` the endpoint still responds,
returning the structured provenance data without prose.

---

## ENS

`binarystamp.eth` resolves subdomains through a CCIP-Read (EIP-3668) gateway
served by this application.

- `<sha256hash>.binarystamp.eth` → the file's owner
- `<number>.binarystamp.eth` → the owner of stamp #N

### `GET /api/ens/resolve/<name>`

Direct lookup, used by the browser UI.

```json
{
  "resolved": true,
  "name": "0xab....binarystamp.eth",
  "owner": "0x1111...",
  "description": "design doc",
  "walrusBlobId": "abc123"
}
```

Unresolved: `{"resolved": false, "name": "<name>"}`.

### `GET /api/ens/reverse/<address>`

The reverse direction: an address's **primary ENS name**, if it has set one.
Used to show `vitalik.eth` next to an owner address.

```json
{"address": "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045", "name": "vitalik.eth"}
```

`name` is `null` when the address has no primary name — which is the common
case, since reverse records are opt-in.

A reverse record is set by whoever controls the address, so on its own it is a
claim rather than proof. The name is only returned if resolving it forward
lands back on the same address; the UI shows the address alongside the name for
the same reason.

Reverse records live on Ethereum mainnet, so this needs `MAINNET_RPC_URL`
(`503` without it) and does not apply to Sui addresses (`400` — they are 32
bytes). Results are cached for `ENS_REVERSE_CACHE_TTL` seconds, misses
included, since each lookup costs two mainnet calls.

### `POST /api/ens/resolve`

The CCIP-Read gateway itself. Called by the resolver contract on Ethereum
mainnet, not by browsers — the deployed
[`BinaryStampResolver`](https://etherscan.io/address/0x61DF09Bf03f5693f8928F3aF9364EbC3a4D61D50)
redirects lookups here.

```json
{"sender": "0x61DF...", "data": "0x9061b923..."}
```

Returns ABI-encoded results: `{"data": "0x..."}`.

Supports `addr(bytes32)` and `text(bytes32,string)`, including when wrapped in
`resolve(bytes,bytes)`. An unknown selector returns `400`.

> This path and `GET /api/ens/resolve/<name>` share a prefix but differ by
> method: the gateway is POST-only, the browser lookup is GET.
