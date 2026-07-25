"""
Deploy BinaryStamp ENS CCIP-Read Resolver.

For the hackathon:
- Deploy to Ethereum mainnet (where binarystamp.eth lives)
- Set the resolver for binarystamp.eth to this contract
- The contract redirects lookups to our gateway at https://binarystamp.com/api/ens/resolve

Requires:
- MAINNET_RPC_URL and MAINNET_PRIVATE_KEY in .env (with mainnet ETH)
- Or run with --sepolia flag for ENS testnet
"""
import os
import sys
import json

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(SCRIPT_DIR)
PROJECT_DIR = os.path.dirname(APP_DIR)

sys.path.insert(0, APP_DIR)

from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_DIR, '.env'))

from web3 import Web3

use_sepolia = '--sepolia' in sys.argv

if use_sepolia:
    RPC_URL = os.getenv('ETH_SEPOLIA_RPC_URL', 'https://rpc.sepolia.org')
    PRIVATE_KEY = os.getenv('ETH_SEPOLIA_PRIVATE_KEY', os.getenv('PRIVATE_KEY', ''))
    EXPLORER = 'https://sepolia.etherscan.io'
else:
    RPC_URL = os.getenv('MAINNET_RPC_URL', 'https://eth.llamarpc.com')
    PRIVATE_KEY = os.getenv('MAINNET_PRIVATE_KEY', '')
    EXPLORER = 'https://etherscan.io'

GATEWAY_URL = os.getenv('ENS_GATEWAY_URL', 'https://binarystamp.com/api/ens/resolve')

if not PRIVATE_KEY:
    print(f'ERROR: {"ETH_SEPOLIA_PRIVATE_KEY" if use_sepolia else "MAINNET_PRIVATE_KEY"} not set in .env')
    sys.exit(1)

# Load compiled artifacts
abi_path = os.path.join(APP_DIR, 'contracts', 'evm', 'BinaryStampResolver_sol_BinaryStampResolver.abi')
bin_path = os.path.join(APP_DIR, 'contracts', 'evm', 'BinaryStampResolver_sol_BinaryStampResolver.bin')

with open(abi_path) as f:
    abi = json.load(f)
with open(bin_path) as f:
    bytecode = '0x' + f.read().strip()

# Connect
network = 'Sepolia' if use_sepolia else 'Mainnet'
print(f'Connecting to Ethereum {network}...')
w3 = Web3(Web3.HTTPProvider(RPC_URL))
if not w3.is_connected():
    print('ERROR: Cannot connect to RPC')
    sys.exit(1)

account = w3.eth.account.from_key(PRIVATE_KEY)
balance = w3.eth.get_balance(account.address)
print(f'Deploying from: {account.address}')
print(f'Balance: {w3.from_wei(balance, "ether")} ETH')
print(f'Gateway URL: {GATEWAY_URL}')

if balance == 0:
    print('ERROR: No ETH balance.')
    sys.exit(1)

# Deploy with gateway URL
print('Deploying BinaryStampResolver...')
contract = w3.eth.contract(abi=abi, bytecode=bytecode)

tx = contract.constructor([GATEWAY_URL]).build_transaction({
    'from': account.address,
    'nonce': w3.eth.get_transaction_count(account.address),
    'gas': 1500000,
    'gasPrice': w3.eth.gas_price,
    'chainId': w3.eth.chain_id,
})

signed = account.sign_transaction(tx)
tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
print(f'Transaction: {tx_hash.hex()}')
print('Waiting for confirmation...')

receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=300)
resolver_address = receipt['contractAddress']

print(f'\n{"="*50}')
print(f'Resolver deployed!')
print(f'Address: {resolver_address}')
print(f'TX: {EXPLORER}/tx/{tx_hash.hex()}')
print(f'{"="*50}')
print(f'\nNext step: Set binarystamp.eth resolver to {resolver_address}')
print('Go to https://app.ens.domains/binarystamp.eth and set the resolver.')
