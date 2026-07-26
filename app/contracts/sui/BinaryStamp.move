module binarystamp::stamp {
    use sui::event;
    use sui::clock::Clock;
    use std::string::String;

    // ============ Structs ============

    public struct Stamp has key, store {
        id: UID,
        file_hash: vector<u8>,
        metadata_hash: vector<u8>,
        walrus_blob_id: String,
        owner: address,
        timestamp_ms: u64,
        description: String,
    }

    public struct Registry has key {
        id: UID,
    }

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

    public entry fun stamp(
        _registry: &mut Registry,
        file_hash: vector<u8>,
        metadata_hash: vector<u8>,
        walrus_blob_id: String,
        description: String,
        clock: &Clock,
        ctx: &mut TxContext,
    ) {
        let sender = ctx.sender();
        let now = clock.timestamp_ms();
        let stamp_uid = object::new(ctx);
        let stamp_id = stamp_uid.to_inner();

        // Copy values needed for event and record
        let fh_event = file_hash;
        let mh_event = metadata_hash;
        let fh_record = file_hash;
        let mh_record = metadata_hash;

        event::emit(StampCreated {
            stamp_id,
            file_hash: fh_event,
            owner: sender,
            timestamp_ms: now,
            metadata_hash: mh_event,
        });

        let new_stamp = Stamp {
            id: stamp_uid,
            file_hash,
            metadata_hash,
            walrus_blob_id,
            owner: sender,
            timestamp_ms: now,
            description,
        };

        // Copy values for the record before they move into the stamp
        let wid_record = new_stamp.walrus_blob_id;
        let desc_record = new_stamp.description;

        transfer::transfer(new_stamp, sender);

        let record = StampRecord {
            id: object::new(ctx),
            file_hash: fh_record,
            stamp_id,
            owner: sender,
            timestamp_ms: now,
            metadata_hash: mh_record,
            walrus_blob_id: wid_record,
            description: desc_record,
        };

        transfer::share_object(record);
    }

    public entry fun transfer_stamp(
        stamp: &mut Stamp,
        new_owner: address,
        clock: &Clock,
        ctx: &mut TxContext,
    ) {
        let sender = ctx.sender();
        assert!(stamp.owner == sender, 0);

        let now = clock.timestamp_ms();

        event::emit(StampTransferred {
            stamp_id: stamp.id.to_inner(),
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
}
