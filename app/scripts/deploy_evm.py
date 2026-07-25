"""Deploy BinaryStamp EVM contract to Base Sepolia using pre-compiled artifacts."""
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

RPC_URL = os.getenv('EVM_RPC_URL', 'https://sepolia.base.org')
PRIVATE_KEY = os.getenv('PRIVATE_KEY', '')

if not PRIVATE_KEY:
    print('ERROR: PRIVATE_KEY not set in .env')
    sys.exit(1)

# Load pre-compiled artifacts
abi_path = os.path.join(APP_DIR, 'contracts', 'evm', 'BinaryStamp_sol_BinaryStamp.abi')
bin_path = os.path.join(APP_DIR, 'contracts', 'evm', 'BinaryStamp_sol_BinaryStamp.bin')

with open(abi_path) as f:
    abi = json.load(f)
with open(bin_path) as f:
    bytecode = '0x' + f.read().strip()

print(f'ABI: {len(abi)} entries, Bytecode: {len(bytecode)} chars')

# Save ABI for subgraph
subgraph_abi_dir = os.path.join(APP_DIR, 'contracts', 'evm', 'subgraph', 'abis')
os.makedirs(subgraph_abi_dir, exist_ok=True)
with open(os.path.join(subgraph_abi_dir, 'BinaryStamp.json'), 'w') as f:
    json.dump(abi, f, indent=2)

# Connect
print(f'Connecting to {RPC_URL}...')
w3 = Web3(Web3.HTTPProvider(RPC_URL))
if not w3.is_connected():
    print('ERROR: Cannot connect to RPC')
    sys.exit(1)

chain_id = w3.eth.chain_id
print(f'Chain ID: {chain_id}')

account = w3.eth.account.from_key(PRIVATE_KEY)
print(f'Deploying from: {account.address}')

balance = w3.eth.get_balance(account.address)
print(f'Balance: {w3.from_wei(balance, "ether")} ETH')

if balance == 0:
    print('ERROR: No ETH balance. Fund this address on Base Sepolia.')
    sys.exit(1)

# Deploy
print('Deploying BinaryStamp contract...')
contract = w3.eth.contract(abi=abi, bytecode=bytecode)

nonce = w3.eth.get_transaction_count(account.address)
gas_price = w3.eth.gas_price

tx = contract.constructor().build_transaction({
    'from': account.address,
    'nonce': nonce,
    'gas': 2000000,
    'gasPrice': gas_price,
    'chainId': chain_id,
})

signed = account.sign_transaction(tx)
tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
print(f'Transaction: {tx_hash.hex()}')
print('Waiting for confirmation...')

receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
contract_address = receipt['contractAddress']

print(f'\n{"="*50}')
print(f'Contract deployed!')
print(f'Address: {contract_address}')
print(f'Block: {receipt["blockNumber"]}')
print(f'Gas used: {receipt["gasUsed"]}')
print(f'TX: https://sepolia.basescan.org/tx/{tx_hash.hex()}')
print(f'Contract: https://sepolia.basescan.org/address/{contract_address}')
print(f'{"="*50}')

# Update .env
env_path = os.path.join(PROJECT_DIR, '.env')
with open(env_path) as f:
    lines = f.readlines()

abi_json = json.dumps(abi)
new_lines = []
for line in lines:
    if line.startswith('CONTRACT_ADDRESS='):
        new_lines.append(f'CONTRACT_ADDRESS={contract_address}\n')
    elif line.startswith('CONTRACT_ABI='):
        new_lines.append(f'CONTRACT_ABI={abi_json}\n')
    else:
        new_lines.append(line)

with open(env_path, 'w') as f:
    f.writelines(new_lines)

print(f'\n.env updated with CONTRACT_ADDRESS and CONTRACT_ABI')
print('Restart the app to use the deployed contract.')
