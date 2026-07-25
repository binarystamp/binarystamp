module binarystamp::stamp {
    use sui::event;
    use sui::clock::Clock;
    use std::string::String;

    // ============ Structs ============

    /// A registered stamp proving file existence/ownership
    public struct Stamp has key, store {
        id: UID,
        file_hash: vector<u8>,       // SHA-256 hash of the file
        metadata_hash: vector<u8>,   // Hash of metadata (or AI function spec)
        walrus_blob_id: String,      // Walrus blob ID for metadata storage
        owner: address,
        timestamp_ms: u64,
        description: String,
    }

    /// Registry mapping file hashes to stamp IDs (shared object)
    public struct Registry has key {
        id: UID,
    }

    /// A record in the registry linking hash -> stamp info
    public struct StampRecord has key, store {
        id: UID,
        file_hash: vector<u8>,
        stamp_id: ID,
        owner: address,
        timestamp_ms: u64,
        metadata_hash: vector<u8>,
        walrus_blob_id: String,
        description: String,
    }

    // ============ Events ============

    public struct StampCreated has copy, drop {
        stamp_id: ID,
        file_hash: vector<u8>,
        owner: address,
        timestamp_ms: u64,
        metadata_hash: vector<u8>,
        walrus_blob_id: String,
    }

    public struct StampTransferred has copy, drop {
        stamp_id: ID,
        file_hash: vector<u8>,
        from: address,
        to: address,
        timestamp_ms: u64,
    }

    // ============ Init ============

    fun init(ctx: &mut TxContext) {
        let registry = Registry {
            id: object::new(ctx),
        };
        transfer::share_object(registry);
    }

    // ============ Public Functions ============

    /// Register a new file hash stamp
    public entry fun stamp(
        _registry: &mut Registry,
        file_hash: vector<u8>,
        metadata_hash: vector<u8>,
        walrus_blob_id: String,
        description: String,
        clock: &Clock,
        ctx: &mut TxContext,
    ) {
        let sender = tx_context::sender(ctx);
        let now = clock.timestamp_ms();
        let stamp_uid = object::new(ctx);
        let stamp_id = object::uid_to_inner(&stamp_uid);

        let new_stamp = Stamp {
            id: stamp_uid,
            file_hash: file_hash,
            metadata_hash: metadata_hash,
            walrus_blob_id: walrus_blob_id,
            owner: sender,
            timestamp_ms: now,
            description: description,
        };

        // Create a shared record for lookups
        let record = StampRecord {
            id: object::new(ctx),
            file_hash: file_hash,
            stamp_id: stamp_id,
            owner: sender,
            timestamp_ms: now,
            metadata_hash: metadata_hash,
            walrus_blob_id: walrus_blob_id,
            description: description,
        };

        event::emit(StampCreated {
            stamp_id: stamp_id,
            file_hash: file_hash,
            owner: sender,
            timestamp_ms: now,
            metadata_hash: metadata_hash,
            walrus_blob_id: walrus_blob_id,
        });

        transfer::transfer(new_stamp, sender);
        transfer::share_object(record);
    }

    /// Transfer stamp ownership
    public entry fun transfer_stamp(
        stamp: &mut Stamp,
        new_owner: address,
        clock: &Clock,
        ctx: &mut TxContext,
    ) {
        let sender = tx_context::sender(ctx);
        assert!(stamp.owner == sender, 0);

        let now = clock.timestamp_ms();

        event::emit(StampTransferred {
            stamp_id: object::uid_to_inner(&stamp.id),
            file_hash: stamp.file_hash,
            from: sender,
            to: new_owner,
            timestamp_ms: now,
        });

        stamp.owner = new_owner;
    }

    // ============ View Functions ============

    public fun get_owner(stamp: &Stamp): address { stamp.owner }
    public fun get_file_hash(stamp: &Stamp): vector<u8> { stamp.file_hash }
    public fun get_metadata_hash(stamp: &Stamp): vector<u8> { stamp.metadata_hash }
    public fun get_timestamp(stamp: &Stamp): u64 { stamp.timestamp_ms }
    public fun get_walrus_blob_id(stamp: &Stamp): String { stamp.walrus_blob_id }
}
