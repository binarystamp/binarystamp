#!/bin/bash
set -euo pipefail

echo "Deploying BinaryStamp to Sui testnet..."

# Ensure testnet
sui client switch --env testnet 2>/dev/null || sui client new-env --alias testnet --rpc https://fullnode.testnet.sui.io:443

# Build
sui move build

# Publish
sui client publish --gas-budget 100000000

echo ""
echo "Done! Note the Package ID and update .env"
