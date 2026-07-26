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
SUI_PACKAGE_ID = os.getenv('SUI_PACKAGE_ID', '')
SUI_REGISTRY_ID = os.getenv('SUI_REGISTRY_ID', '')
SUI_EVENT_PAGE_SIZE = int(os.getenv('SUI_EVENT_PAGE_SIZE', '50'))
SUI_EVENT_MAX_PAGES = int(os.getenv('SUI_EVENT_MAX_PAGES', '10'))
# ENS_GATEWAY_URL is read by scripts/deploy_resolver.py, not by the app: this
# service *is* the gateway, so ens_resolver.py serves the lookups directly.

# The answer renders in a narrow side panel, not a document, so the format
# instructions matter as much as the persona.
AI_SYSTEM_PROMPT = (
    'You are BinaryStamp AI, a provenance analysis agent. You answer questions '
    'about a file\'s on-chain ownership using the registry data supplied with '
    'the question.\n'
    '\n'
    'Your answer is rendered as Markdown in a narrow panel. Follow these:\n'
    '- Open with the answer itself, in one or two sentences. No title heading.\n'
    '- Put facts in a compact two-column Markdown table (| Field | Value |).\n'
    '- Keep the whole answer under about 150 words unless more is asked for.\n'
    '- Use no emoji and no decorative symbols. Plain Markdown only.\n'
    '- Abbreviate hashes and addresses as 0x1234...abcd. The full file hash is '
    'already displayed above your answer, so do not repeat it in full.\n'
    '- Write timestamps as human-readable dates, and say how long ago they '
    'were relative to today.\n'
    '- State only what the data supports. If a field is absent, say so briefly '
    'rather than speculating about why.'
)

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
        except Exception as e:
            log.error(f'Contract lookup failed: {e}')

    # Not on Base — the file may have been stamped on Sui instead.
    if SUI_PACKAGE_ID:
        try:
            stamp = query_sui_stamp(file_hash)
            if stamp:
                return jsonify(stamp)
        except Exception as e:
            log.error(f'Sui lookup failed: {e}')

    return jsonify({'found': False, 'source': 'none'})


@app.route('/api/sui/lookup', methods=['GET'])
def sui_lookup():
    """Look up a file hash in the Sui StampCreated event log."""
    file_hash = request.args.get('hash', '')
    if not file_hash:
        return jsonify({'error': 'hash parameter required'}), 400

    if not SUI_PACKAGE_ID:
        return jsonify({'found': False, 'error': 'Sui not configured'}), 503

    try:
        stamp = query_sui_stamp(file_hash)
    except Exception as e:
        log.error(f'Sui lookup failed: {e}')
        return jsonify({'found': False, 'error': str(e)}), 502

    if not stamp:
        return jsonify({'found': False, 'source': 'sui'})
    return jsonify(stamp)


@app.route('/api/sui/stamp-object', methods=['GET'])
def sui_stamp_object():
    """Find the Stamp object an address holds for a file hash.

    transfer_stamp() acts on the object, not the hash, so the frontend needs
    this before it can build a transfer.
    """
    address = request.args.get('address', '')
    file_hash = request.args.get('hash', '')
    if not address or not file_hash:
        return jsonify({'error': 'address and hash parameters required'}), 400

    if not SUI_PACKAGE_ID:
        return jsonify({'found': False, 'error': 'Sui not configured'}), 503

    try:
        object_id = find_sui_stamp_object(address, file_hash)
    except Exception as e:
        log.error(f'Sui owned-object lookup failed: {e}')
        return jsonify({'found': False, 'error': str(e)}), 502

    if not object_id:
        return jsonify({'found': False})
    return jsonify({'found': True, 'objectId': object_id})


@app.route('/api/sui/config', methods=['GET'])
def sui_config():
    """Identifiers the frontend needs to build a Sui transaction."""
    return jsonify({
        'rpc': SUI_RPC,
        'packageId': SUI_PACKAGE_ID,
        'registryId': SUI_REGISTRY_ID,
        'configured': bool(SUI_PACKAGE_ID and SUI_REGISTRY_ID),
    })


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
                system=AI_SYSTEM_PROMPT,
                messages=[{
                    'role': 'user',
                    'content': (
                        f'Today is {time.strftime("%Y-%m-%d")}.\n\n'
                        f'File hash: {file_hash}\n\n'
                        f'Registry data:\n{json.dumps(context, indent=2)}\n\n'
                        f'Question: {question}'
                    )
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


@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'ok',
        'evm': bool(contract),
        'subgraph': bool(SUBGRAPH_URL),
        'walrus': bool(WALRUS_PUBLISHER),
        'ai': bool(os.getenv('ANTHROPIC_API_KEY')),
        'sui': bool(SUI_PACKAGE_ID and SUI_REGISTRY_ID),
    })


# ============ Sui Helpers ============

def sui_rpc(method, params):
    """Call the Sui JSON-RPC endpoint."""
    resp = requests.post(
        SUI_RPC,
        json={'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params},
        timeout=15,
    )
    resp.raise_for_status()
    body = resp.json()
    if 'error' in body:
        raise RuntimeError(body['error'].get('message', 'Sui RPC error'))
    return body.get('result')


def bytes_field_to_hex(value):
    """Move vector<u8> arrives as a list of ints; normalize to 0x-hex."""
    if isinstance(value, list):
        return '0x' + bytes(value).hex()
    if isinstance(value, str):
        return value if value.startswith('0x') else '0x' + value
    return ''


def query_sui_stamp(file_hash):
    """Find the earliest StampCreated event matching a file hash.

    Sui RPC cannot filter events by field value, so this scans the package's
    event log newest-first. Bounded to keep the request predictable; a busy
    registry would want a proper indexer instead.
    """
    if not file_hash.startswith('0x'):
        file_hash = '0x' + file_hash
    target = file_hash.lower()

    event_type = f'{SUI_PACKAGE_ID}::stamp::StampCreated'
    cursor = None
    match = None

    for _ in range(SUI_EVENT_MAX_PAGES):
        result = sui_rpc('suix_queryEvents', [
            {'MoveEventType': event_type}, cursor, SUI_EVENT_PAGE_SIZE, True,
        ])
        if not result:
            break

        for event in result.get('data', []):
            parsed = event.get('parsedJson', {})
            if bytes_field_to_hex(parsed.get('file_hash')).lower() != target:
                continue
            # Descending scan, so keep overwriting to end up with the earliest.
            match = {
                'found': True,
                'source': 'sui',
                'fileHash': target,
                'owner': parsed.get('owner'),
                'timestamp': int(parsed.get('timestamp_ms', 0)) // 1000,
                'metadataHash': bytes_field_to_hex(parsed.get('metadata_hash')),
                'stampId': parsed.get('stamp_id'),
                'txDigest': event.get('id', {}).get('txDigest'),
            }

        if not result.get('hasNextPage'):
            break
        cursor = result.get('nextCursor')

    if match:
        current_owner = latest_sui_owner(target)
        if current_owner:
            match['owner'] = current_owner
            match['transferred'] = True

    return match


def latest_sui_owner(file_hash):
    """Replay StampTransferred events to find who holds a stamp now.

    The shared StampRecord keeps the original owner, so a transferred stamp
    would otherwise report stale ownership.
    """
    event_type = f'{SUI_PACKAGE_ID}::stamp::StampTransferred'
    cursor = None
    owner = None

    for _ in range(SUI_EVENT_MAX_PAGES):
        result = sui_rpc('suix_queryEvents', [
            {'MoveEventType': event_type}, cursor, SUI_EVENT_PAGE_SIZE, False,
        ])
        if not result:
            break

        for event in result.get('data', []):
            parsed = event.get('parsedJson', {})
            if bytes_field_to_hex(parsed.get('file_hash')).lower() != file_hash.lower():
                continue
            # Ascending scan, so the last match is the most recent transfer.
            owner = parsed.get('to')

        if not result.get('hasNextPage'):
            break
        cursor = result.get('nextCursor')

    return owner


def find_sui_stamp_object(address, file_hash):
    """Return the object ID of the Stamp `address` holds for `file_hash`."""
    if not file_hash.startswith('0x'):
        file_hash = '0x' + file_hash
    target = file_hash.lower()

    struct_type = f'{SUI_PACKAGE_ID}::stamp::Stamp'
    cursor = None

    for _ in range(SUI_EVENT_MAX_PAGES):
        result = sui_rpc('suix_getOwnedObjects', [
            address,
            {'filter': {'StructType': struct_type}, 'options': {'showContent': True}},
            cursor,
            SUI_EVENT_PAGE_SIZE,
        ])
        if not result:
            break

        for entry in result.get('data', []):
            content = (entry.get('data') or {}).get('content') or {}
            fields = content.get('fields') or {}
            if bytes_field_to_hex(fields.get('file_hash')).lower() == target:
                return entry['data']['objectId']

        if not result.get('hasNextPage'):
            break
        cursor = result.get('nextCursor')

    return None


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
