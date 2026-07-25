import os
import json
import hashlib
import time
import logging
from flask import Flask, request, jsonify, send_from_directory
from web3 import Web3
import requests

app = Flask(__name__, static_folder='frontend', static_url_path='')

logging.basicConfig(level=os.getenv('LOG_LEVEL', 'info').upper())

from ens_resolver import ens_bp
app.register_blueprint(ens_bp, url_prefix='/api')
log = logging.getLogger('binarystamp')

# ============ Config ============

RPC_URL = os.getenv('EVM_RPC_URL', 'https://sepolia.base.org')
CONTRACT_ADDRESS = os.getenv('CONTRACT_ADDRESS', '')
PRIVATE_KEY = os.getenv('PRIVATE_KEY', '')
SUBGRAPH_URL = os.getenv('SUBGRAPH_URL', '')
WALRUS_AGGREGATOR = os.getenv('WALRUS_AGGREGATOR', 'https://aggregator.walrus-testnet.walrus.space')
WALRUS_PUBLISHER = os.getenv('WALRUS_PUBLISHER', 'https://publisher.walrus-testnet.walrus.space')
SUI_RPC = os.getenv('SUI_RPC', 'https://fullnode.testnet.sui.io:443')
ENS_GATEWAY_URL = os.getenv('ENS_GATEWAY_URL', '')

# ABI for the EVM mirror contract - load from file, fallback to env
ABI_FILE = os.path.join(os.path.dirname(__file__), 'contracts', 'evm', 'abi.json')
if os.path.exists(ABI_FILE):
    with open(ABI_FILE) as _f:
        CONTRACT_ABI = json.load(_f)
else:
    CONTRACT_ABI = json.loads(os.getenv('CONTRACT_ABI', '[]'))

w3 = None
contract = None


def init_web3():
    global w3, contract
    if not RPC_URL or not CONTRACT_ADDRESS:
        log.warning('EVM not configured - running in demo mode')
        return
    w3 = Web3(Web3.HTTPProvider(RPC_URL))
    if CONTRACT_ABI:
        contract = w3.eth.contract(
            address=Web3.to_checksum_address(CONTRACT_ADDRESS),
            abi=CONTRACT_ABI
        )


# ============ Routes ============

@app.route('/')
def index():
    return send_from_directory('frontend', 'index.html')


@app.route('/api/hash', methods=['POST'])
def compute_hash():
    """Compute SHA-256 hash of uploaded file (server-side fallback)."""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    f = request.files['file']
    sha = hashlib.sha256()
    for chunk in iter(lambda: f.read(8192), b''):
        sha.update(chunk)
    file_hash = sha.hexdigest()
    return jsonify({'hash': file_hash, 'hash_bytes32': '0x' + file_hash})


@app.route('/api/lookup', methods=['GET'])
def lookup():
    """Look up a file hash via The Graph subgraph."""
    file_hash = request.args.get('hash', '')
    if not file_hash:
        return jsonify({'error': 'hash parameter required'}), 400

    if not file_hash.startswith('0x'):
        file_hash = '0x' + file_hash

    # Query The Graph
    if SUBGRAPH_URL:
        result = query_subgraph(file_hash)
        if result:
            return jsonify(result)

    # Fallback: query contract directly
    if contract:
        try:
            is_stamped = contract.functions.isStamped(bytes.fromhex(file_hash[2:])).call()
            if is_stamped:
                stamp_data = contract.functions.getLatestStamp(bytes.fromhex(file_hash[2:])).call()
                return jsonify({
                    'found': True,
                    'owner': stamp_data[3],
                    'timestamp': stamp_data[4],
                    'metadataHash': '0x' + stamp_data[1].hex(),
                    'walrusBlobId': stamp_data[2],
                    'description': stamp_data[5],
                    'source': 'contract'
                })
            return jsonify({'found': False})
        except Exception as e:
            log.error(f'Contract lookup failed: {e}')

    return jsonify({'found': False, 'source': 'none'})


@app.route('/api/stamp', methods=['POST'])
def create_stamp():
    """Register a file hash on-chain (EVM mirror)."""
    data = request.json
    if not data:
        return jsonify({'error': 'JSON body required'}), 400

    file_hash = data.get('fileHash', '')
    metadata_hash = data.get('metadataHash', '0x' + '0' * 64)
    walrus_blob_id = data.get('walrusBlobId', '')
    description = data.get('description', '')

    if not file_hash:
        return jsonify({'error': 'fileHash required'}), 400

    if not file_hash.startswith('0x'):
        file_hash = '0x' + file_hash
    if not metadata_hash.startswith('0x'):
        metadata_hash = '0x' + metadata_hash

    # If user wants server-side stamping (has private key configured)
    if contract and PRIVATE_KEY:
        try:
            account = w3.eth.account.from_key(PRIVATE_KEY)
            tx = contract.functions.stamp(
                bytes.fromhex(file_hash[2:]),
                bytes.fromhex(metadata_hash[2:]),
                walrus_blob_id,
                description
            ).build_transaction({
                'from': account.address,
                'nonce': w3.eth.get_transaction_count(account.address),
                'gas': 300000,
                'gasPrice': w3.eth.gas_price,
            })
            signed = account.sign_transaction(tx)
            tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
            return jsonify({
                'success': True,
                'txHash': tx_hash.hex(),
                'blockNumber': receipt['blockNumber'],
            })
        except Exception as e:
            log.error(f'Stamp transaction failed: {e}')
            return jsonify({'error': str(e)}), 500

    # Return unsigned transaction data for client-side signing
    return jsonify({
        'unsigned': True,
        'contractAddress': CONTRACT_ADDRESS,
        'fileHash': file_hash,
        'metadataHash': metadata_hash,
        'walrusBlobId': walrus_blob_id,
        'description': description,
        'message': 'Sign this transaction with your wallet'
    })


@app.route('/api/walrus/store', methods=['POST'])
def walrus_store():
    """Store metadata on Walrus and return blob ID."""
    data = request.json or {}
    metadata = data.get('metadata', {})
    if not metadata:
        return jsonify({'error': 'metadata required'}), 400

    payload = json.dumps(metadata, sort_keys=True).encode()

    try:
        resp = requests.put(
            f'{WALRUS_PUBLISHER}/v1/blobs',
            data=payload,
            headers={'Content-Type': 'application/octet-stream'},
            timeout=30
        )
        if resp.status_code in (200, 201):
            result = resp.json()
            blob_id = ''
            if 'newlyCreated' in result:
                blob_id = result['newlyCreated']['blobObject']['blobId']
            elif 'alreadyCertified' in result:
                blob_id = result['alreadyCertified']['blobId']

            metadata_hash = hashlib.sha256(payload).hexdigest()
            return jsonify({
                'blobId': blob_id,
                'metadataHash': metadata_hash,
                'size': len(payload)
            })
        return jsonify({'error': f'Walrus returned {resp.status_code}'}), 502
    except Exception as e:
        log.error(f'Walrus store failed: {e}')
        return jsonify({'error': str(e)}), 502


@app.route('/api/walrus/fetch/<blob_id>', methods=['GET'])
def walrus_fetch(blob_id):
    """Fetch metadata from Walrus by blob ID."""
    try:
        resp = requests.get(
            f'{WALRUS_AGGREGATOR}/v1/blobs/{blob_id}',
            timeout=15
        )
        if resp.status_code == 200:
            try:
                return jsonify(resp.json())
            except Exception:
                return resp.content, 200, {'Content-Type': 'application/octet-stream'}
        return jsonify({'error': f'Walrus returned {resp.status_code}'}), 502
    except Exception as e:
        return jsonify({'error': str(e)}), 502


@app.route('/api/subgraph/query', methods=['POST'])
def subgraph_proxy():
    """Proxy GraphQL queries to The Graph subgraph."""
    if not SUBGRAPH_URL:
        return jsonify({'error': 'Subgraph not configured'}), 503
    data = request.json or {}
    query = data.get('query', '')
    variables = data.get('variables', {})
    try:
        resp = requests.post(
            SUBGRAPH_URL,
            json={'query': query, 'variables': variables},
            timeout=15
        )
        return jsonify(resp.json())
    except Exception as e:
        return jsonify({'error': str(e)}), 502


@app.route('/api/ai/provenance', methods=['POST'])
def ai_provenance():
    """AI agent: analyze file provenance using The Graph data."""
    data = request.json or {}
    file_hash = data.get('fileHash', '')
    question = data.get('question', 'Who owns this file and when was it stamped?')

    if not file_hash:
        return jsonify({'error': 'fileHash required'}), 400

    if not file_hash.startswith('0x'):
        file_hash = '0x' + file_hash

    # Gather data from subgraph or contract
    graph_data = query_subgraph(file_hash) if SUBGRAPH_URL else None
    if not graph_data and contract:
        try:
            file_hash_bytes = bytes.fromhex(file_hash[2:])
            is_stamped = contract.functions.isStamped(file_hash_bytes).call()
            if is_stamped:
                stamp_data = contract.functions.getLatestStamp(file_hash_bytes).call()
                graph_data = {
                    'found': True,
                    'owner': stamp_data[3],
                    'timestamp': stamp_data[4],
                    'metadataHash': '0x' + stamp_data[1].hex(),
                    'walrusBlobId': stamp_data[2],
                    'description': stamp_data[5],
                    'source': 'contract'
                }
        except Exception as e:
            log.error(f'Contract lookup for AI failed: {e}')

    # Build AI context
    context = build_provenance_context(file_hash, graph_data)

    # Use Claude API if available, otherwise return structured data
    anthropic_key = os.getenv('ANTHROPIC_API_KEY', '')
    if anthropic_key:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=anthropic_key)
            message = client.messages.create(
                model='claude-sonnet-4-6',
                max_tokens=1024,
                system='You are BinaryStamp AI, a provenance analysis agent. You analyze file ownership and history data from The Graph subgraph. Be concise and factual. Format timestamps as human-readable dates.',
                messages=[{
                    'role': 'user',
                    'content': f'File hash: {file_hash}\n\nSubgraph data:\n{json.dumps(context, indent=2)}\n\nQuestion: {question}'
                }]
            )
            return jsonify({
                'answer': message.content[0].text,
                'data': context,
                'source': 'ai+subgraph'
            })
        except Exception as e:
            log.error(f'AI analysis failed: {e}')

    # Fallback: return structured data without AI
    return jsonify({
        'answer': format_provenance_text(context),
        'data': context,
        'source': 'subgraph'
    })


@app.route('/api/ens/resolve/<name>', methods=['GET'])
def ens_resolve(name):
    """Resolve ENS name (e.g., <hash>.binarystamp.eth)."""
    # This would use the CCIP-Read gateway
    if ENS_GATEWAY_URL:
        try:
            resp = requests.get(f'{ENS_GATEWAY_URL}/resolve/{name}', timeout=10)
            return jsonify(resp.json())
        except Exception as e:
            return jsonify({'error': str(e)}), 502

    # Fallback: try to resolve via subgraph
    parts = name.replace('.binarystamp.eth', '').split('.')
    if parts:
        label = parts[0]
        # Check if it's a hash or a number
        if label.startswith('0x') or len(label) == 64:
            file_hash = label if label.startswith('0x') else '0x' + label
            result = query_subgraph(file_hash) if SUBGRAPH_URL else None
            if result and result.get('found'):
                return jsonify({
                    'name': name,
                    'resolved': True,
                    'owner': result['owner'],
                    'timestamp': result.get('timestamp'),
                })
        elif label.isdigit():
            # Resolve by stamp number
            result = query_subgraph_by_number(int(label))
            if result:
                return jsonify({
                    'name': name,
                    'resolved': True,
                    **result
                })

    return jsonify({'name': name, 'resolved': False})


@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'ok',
        'evm': bool(contract),
        'subgraph': bool(SUBGRAPH_URL),
        'walrus': bool(WALRUS_PUBLISHER),
        'ai': bool(os.getenv('ANTHROPIC_API_KEY')),
    })


# ============ Helpers ============

def query_subgraph(file_hash):
    """Query The Graph for file hash info."""
    if not SUBGRAPH_URL:
        return None
    query = '''
    query($fileHash: ID!) {
        fileHashLookup(id: $fileHash) {
            fileHash
            latestOwner
            stampCount
            firstStampedAt
            stamps {
                id
                owner
                timestamp
                metadataHash
                walrusBlobId
                description
                stampNumber
                transfers {
                    from
                    to
                    timestamp
                }
            }
        }
    }
    '''
    try:
        resp = requests.post(
            SUBGRAPH_URL,
            json={'query': query, 'variables': {'fileHash': file_hash.lower()}},
            timeout=10
        )
        data = resp.json().get('data', {})
        lookup = data.get('fileHashLookup')
        if lookup:
            return {
                'found': True,
                'owner': lookup['latestOwner'],
                'stampCount': lookup['stampCount'],
                'firstStampedAt': lookup['firstStampedAt'],
                'stamps': lookup['stamps'],
                'source': 'subgraph'
            }
    except Exception as e:
        log.error(f'Subgraph query failed: {e}')
    return None


def query_subgraph_by_number(number):
    """Query The Graph for stamp by number."""
    if not SUBGRAPH_URL:
        return None
    query = '''
    query($number: ID!) {
        stamp(id: $number) {
            fileHash
            owner
            timestamp
            metadataHash
            walrusBlobId
            description
            stampNumber
        }
    }
    '''
    try:
        resp = requests.post(
            SUBGRAPH_URL,
            json={'query': query, 'variables': {'number': str(number)}},
            timeout=10
        )
        data = resp.json().get('data', {})
        stamp = data.get('stamp')
        if stamp:
            return {
                'found': True,
                'fileHash': stamp['fileHash'],
                'owner': stamp['owner'],
                'timestamp': stamp['timestamp'],
                'stampNumber': stamp['stampNumber'],
            }
    except Exception as e:
        log.error(f'Subgraph query failed: {e}')
    return None


def build_provenance_context(file_hash, graph_data):
    """Build context for AI provenance analysis."""
    ctx = {'fileHash': file_hash, 'found': False}
    if graph_data and graph_data.get('found'):
        ctx.update(graph_data)
    return ctx


def format_provenance_text(context):
    """Format provenance data as human-readable text."""
    if not context.get('found'):
        return 'This file hash has not been registered on BinaryStamp.'
    owner = context.get('owner', 'unknown')
    timestamp = context.get('firstStampedAt', 'unknown')
    count = context.get('stampCount', 0)
    if timestamp != 'unknown':
        try:
            from datetime import datetime
            dt = datetime.fromtimestamp(int(timestamp))
            timestamp = dt.strftime('%Y-%m-%d %H:%M:%S UTC')
        except Exception:
            pass
    return f'File owned by {owner}, first stamped at {timestamp}. Total stamps: {count}.'


# ============ Init ============

init_web3()

# ============ Main ============

if __name__ == '__main__':
    port = int(os.getenv('PORT', '8082'))
    host = os.getenv('HOST', '0.0.0.0')
    debug = os.getenv('ENVIRONMENT', 'dev') == 'dev'
    app.run(host=host, port=port, debug=debug)
