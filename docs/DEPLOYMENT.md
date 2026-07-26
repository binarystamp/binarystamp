# Deployment

Covers running the service in production and deploying the contracts it
depends on.

## Contents

- [Deploying the service](#deploying-the-service)
- [Environment](#environment)
- [Deploying the EVM contract](#deploying-the-evm-contract)
- [Deploying the ENS resolver](#deploying-the-ens-resolver)
- [Deploying the subgraph](#deploying-the-subgraph)
- [Deploying the Sui package](#deploying-the-sui-package)
- [Redeploying the Sui package](#redeploying-the-sui-package)

---

## Deploying the service

```bash
cp .env.example .env     # then fill in the production values
./_start build
./_start up
```

Compose publishes port 8082, mounts `./data` at `/data`, restarts unless
stopped, and health-checks `/api/health`. Put a TLS-terminating reverse proxy
in front of it.

Two things worth knowing before shipping:

**`.env` is gitignored.** It is never part of a deploy. Production values must
be set wherever the service actually runs — a redeploy will not carry them over
on your behalf. `SUI_PACKAGE_ID` and `SUI_REGISTRY_ID` in particular have to be
updated by hand after a Sui redeploy.

**The Sui bundle is committed.** `app/frontend/vendor/sui.js` is checked in, so
a deploy needs no Node toolchain. Rebuild it only when `@mysten/sui` or
`scripts/sui-entry.js` changes:

```bash
./_start build          # or: cd app && npm install && npm run build
```

Verify a deploy:

```bash
curl -s https://<host>/api/health
```

Every flag should be `true` for a fully configured deployment. A `false` means
that feature is unconfigured, not that it is broken.

---

## Environment

| Variable | Required | Notes |
|----------|----------|-------|
| `PORT`, `HOST` | no | Defaults to 8082 / 0.0.0.0 |
| `EVM_RPC_URL` | yes | Base Sepolia RPC |
| `CONTRACT_ADDRESS` | yes | Deployed BinaryStamp registry |
| `PRIVATE_KEY` | no | Enables server-side stamping — see the warning below |
| `SUBGRAPH_URL` | recommended | Without it, lookups read the contract directly |
| `WALRUS_AGGREGATOR`, `WALRUS_PUBLISHER` | no | Default to the public testnet endpoints |
| `SUI_RPC` | no | Defaults to the public testnet fullnode |
| `SUI_PACKAGE_ID` | for Sui | Published Move package |
| `SUI_REGISTRY_ID` | for Sui | Shared `Registry` object from the same publish |
| `SUI_EVENT_PAGE_SIZE`, `SUI_EVENT_MAX_PAGES` | no | Bound the Sui event scan (50 / 10) |
| `MAINNET_RPC_URL` | recommended | Reverse-resolves owner addresses to ENS names; without it owners show as plain addresses |
| `ENS_REVERSE_CACHE_TTL` | no | Seconds to cache a reverse lookup, hits and misses (3600) |
| `ENS_GATEWAY_URL` | no | Read by `deploy_resolver.py` only, not by the app |
| `ANTHROPIC_API_KEY` | no | Without it the AI agent returns data without prose |
| `LOG_LEVEL` | no | `debug`, `info`, `warning`, `error` |

> **`PRIVATE_KEY` in production.** It makes `POST /api/stamp` sign with the
> server's key, so stamps created through it are owned by the server rather
> than by the user who submitted the file. For a provenance registry that is
> usually wrong. Leave it unset unless you specifically want server-signed
> stamps.

`SUI_PACKAGE_ID` and `SUI_REGISTRY_ID` must come from the **same** publish.
`stamp()` takes `&mut Registry`, and the registry's object ID is not derivable
from the package ID, so a mismatched pair fails at transaction build time.

---

## Deploying the EVM contract

```bash
cd app
./venv/bin/python scripts/deploy_evm.py
```

Set the resulting address as `CONTRACT_ADDRESS`, and update `EVM_CONTRACT` in
`app/frontend/chains.js`.

If the contract's function signatures change, the hardcoded selectors in
`chains.js` must change too. `app/tests/test_chains.py` recomputes them from
`contracts/evm/abi.json` and fails on a mismatch, so a stale selector cannot
ship silently.

---

## Deploying the ENS resolver

```bash
cd app
./venv/bin/python scripts/deploy_resolver.py
```

Then set the resolver for `binarystamp.eth` at
[app.ens.domains](https://app.ens.domains). The resolver stores the gateway URL
it redirects lookups to; `scripts/update_resolver_urls.py` changes it later.

The gateway is `POST /api/ens/resolve` on this service, so the URL must point
at a publicly reachable deployment.

---

## Deploying the subgraph

```bash
cd app/contracts/evm/subgraph
npm install
npx graph codegen
npx graph build
npx graph auth --studio <DEPLOY_KEY>
npx graph deploy --studio binarystamp
```

Point `SUBGRAPH_URL` at the resulting query endpoint. After redeploying the EVM
contract, update the address and `startBlock` in `subgraph.yaml` first.

---

## Deploying the Sui package

Use the **Deploy Sui Move Contract** GitHub Action (manual trigger). It needs
the `SUI_PRIVATE_KEY_TESTNET` secret, and the corresponding address needs
testnet SUI — each publish budgets 0.2 SUI.

The job builds the package, runs `sui move test`, publishes, and writes the new
identifiers to the run summary. It fails if the publish does not yield both a
package ID and a Registry object ID.

Locally, if you have the Sui CLI for your platform:

```bash
cd sui-package
sui move test
./deploy.sh
```

> The prebuilt Sui CLI releases are x86_64 glibc binaries. They will not run on
> arm64 or on musl-based images such as Alpine, which is why deployment goes
> through CI.

---

## Redeploying the Sui package

The workflow runs `sui client publish`, not `sui client upgrade`. **Every run
creates a brand new package ID and a brand new Registry object.** It does not
update the existing package in place, and stamps registered against the old
package stay there.

After a redeploy, update every one of these — a partial update leaves the app
pointing at a package that no longer matches:

| Location | What to change |
|----------|----------------|
| `.env` (and the production environment) | `SUI_PACKAGE_ID`, `SUI_REGISTRY_ID` |
| `.env.example` | same two values |
| `README.md` | the Sui rows in the Deployed Contracts table |
| `app/frontend/chains.js` | `SUI_PACKAGE`, `SUI_REGISTRY`, `SUI_REGISTRY_VERSION` |
| `app/tests/e2e/test_frontend.py` | the two asserted Move call targets |

`SUI_REGISTRY_VERSION` is the Registry's **initial shared version**, which the
transaction builder needs in order to reference a shared object. The workflow
summary prints it. To recover it from an existing deployment:

```bash
curl -s -X POST "$SUI_RPC" -H 'Content-Type: application/json' -d '{
  "jsonrpc":"2.0","id":1,"method":"sui_getObject",
  "params":["<SUI_REGISTRY_ID>",{"showOwner":true}]
}' | python3 -c 'import json,sys; print(json.load(sys.stdin)["result"]["data"]["owner"])'
```

Confirm the deployed code is what you expect — a workflow run against an
unpushed fix will happily republish the old source:

```bash
curl -s -X POST "$SUI_RPC" -H 'Content-Type: application/json' -d '{
  "jsonrpc":"2.0","id":1,"method":"sui_getNormalizedMoveModule",
  "params":["<SUI_PACKAGE_ID>","stamp"]
}' | python3 -c 'import json,sys; print(json.load(sys.stdin)["result"]["exposedFunctions"]["transfer_stamp"]["parameters"][0])'
```

A bare `Struct` is correct — the stamp is taken by value and genuinely moves. A
`MutableReference` means the old, broken `transfer_stamp` is deployed.

Finally, run the tests: the e2e suite asserts the Move call targets, so a
missed identifier shows up there.

```bash
./_start test
```

### Upgrading instead of republishing

The publish creates an `UpgradeCap` owned by the publishing address. Once there
are stamps worth preserving, switch the workflow to `sui client upgrade` with
that cap so the package keeps its identity across versions instead of stranding
prior stamps.
