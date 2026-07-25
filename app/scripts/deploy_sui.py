"""
Deploy BinaryStamp Move package to Sui Testnet.

Since we can't run the Sui CLI in this environment (musl-based),
this script creates the Move project structure for manual deployment.

To deploy:
1. Install Sui CLI on your machine: https://docs.sui.io/guides/developer/getting-started/sui-install
2. Copy the generated project directory
3. Run: sui client publish --gas-budget 100000000
"""
import os
import sys
import shutil

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(SCRIPT_DIR)
PROJECT_DIR = os.path.dirname(APP_DIR)

# Create Move project at a known location
MOVE_DIR = os.path.join(PROJECT_DIR, 'sui-package')

if os.path.exists(MOVE_DIR):
    shutil.rmtree(MOVE_DIR)

os.makedirs(os.path.join(MOVE_DIR, 'sources'))

# Move.toml
with open(os.path.join(MOVE_DIR, 'Move.toml'), 'w') as f:
    f.write('''[package]
name = "BinaryStamp"
edition = "2024.beta"

[dependencies]
Sui = { git = "https://github.com/MystenLabs/sui.git", subdir = "crates/sui-framework/packages/sui-framework", rev = "framework/testnet" }

[addresses]
binarystamp = "0x0"
''')

# Copy Move source
shutil.copy(
    os.path.join(APP_DIR, 'contracts', 'sui', 'BinaryStamp.move'),
    os.path.join(MOVE_DIR, 'sources', 'BinaryStamp.move')
)

print(f'''
{"="*50}
Sui Move package created at: {MOVE_DIR}
{"="*50}

To deploy to Sui testnet:

1. Make sure Sui CLI is installed on your machine
2. Import your key:
   sui keytool import <your-private-key> ed25519

3. Switch to testnet:
   sui client switch --env testnet

4. Deploy:
   cd {MOVE_DIR}
   sui client publish --gas-budget 100000000

5. Note the Package ID and Registry Object ID from the output
   Add them to .env:
   SUI_PACKAGE_ID=0x...
   SUI_REGISTRY_ID=0x...

The contract creates a shared Registry object on init that
can be used for stamp lookups.
''')

# Also create a helper script
with open(os.path.join(MOVE_DIR, 'deploy.sh'), 'w') as f:
    f.write('''#!/bin/bash
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
''')
os.chmod(os.path.join(MOVE_DIR, 'deploy.sh'), 0o755)

print(f'Deploy script: {MOVE_DIR}/deploy.sh')
