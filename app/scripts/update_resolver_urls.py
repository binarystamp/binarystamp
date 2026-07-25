"""Update the BinaryStampResolver gateway URLs on mainnet."""
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

RPC_URL = os.getenv('MAINNET_RPC_URL', 'https://eth.llamarpc.com')
PRIVATE_KEY = os.getenv('MAINNET_PRIVATE_KEY', '')
RESOLVER_ADDRESS = '0x5969D7558d3409ac70ebdF24063AeC7257d0aCe3'
GATEWAY_URL = 'https://binarystamp.com/api/ens/resolve'

abi_path = os.path.join(APP_DIR, 'contracts', 'evm', 'BinaryStampResolver_sol_BinaryStampResolver.abi')
with open(abi_path) as f:
    abi = json.load(f)

w3 = Web3(Web3.HTTPProvider(RPC_URL))
account = w3.eth.account.from_key(PRIVATE_KEY)
contract = w3.eth.contract(address=Web3.to_checksum_address(RESOLVER_ADDRESS), abi=abi)

print(f'Updating resolver URLs to: {GATEWAY_URL}')
print(f'From: {account.address}')

tx = contract.functions.setUrls([GATEWAY_URL]).build_transaction({
    'from': account.address,
    'nonce': w3.eth.get_transaction_count(account.address),
    'gas': 100000,
    'gasPrice': w3.eth.gas_price,
    'chainId': w3.eth.chain_id,
})

signed = account.sign_transaction(tx)
tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
print(f'TX: {tx_hash.hex()}')
receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=300)
print(f'Confirmed in block {receipt["blockNumber"]}')
print(f'https://etherscan.io/tx/{tx_hash.hex()}')
