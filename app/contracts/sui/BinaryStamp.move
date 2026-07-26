module binarystamp::stamp {
    use sui::event;
    use sui::clock::Clock;
    use std::string::String;

    // ============ Errors ============

    /// Caller is not the current owner of the stamp.
    const ENotOwner: u64 = 0;

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

    /// Shared snapshot of a stamp at creation time, so anyone can look one up
    /// without owning it. `owner` here is the ORIGINAL owner — transfers move
    /// the Stamp object and emit StampTransferred, but do not touch this
    /// record. Resolve current ownership from the event log.
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
        transfer::share_object(Registry {
            id: object::new(ctx),
        });
    }

    #[test_only]
    /// `init` does not run in tests, so expose it for the test scenario.
    public fun init_for_testing(ctx: &mut TxContext) {
        init(ctx)
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

        event::emit(StampCreated {
            stamp_id,
            file_hash,
            owner: sender,
            timestamp_ms: now,
            metadata_hash,
        });

        // Create record first (before values move into Stamp)
        let record = StampRecord {
            id: object::new(ctx),
            file_hash,
            stamp_id,
            owner: sender,
            timestamp_ms: now,
            metadata_hash,
            walrus_blob_id,
            description,
        };

        let new_stamp = Stamp {
            id: stamp_uid,
            file_hash,
            metadata_hash,
            walrus_blob_id,
            owner: sender,
            timestamp_ms: now,
            description,
        };

        transfer::transfer(new_stamp, sender);
        transfer::share_object(record);
    }

    /// Hand a stamp to a new owner.
    ///
    /// Takes the Stamp by value: updating only the `owner` field would leave
    /// the Sui object itself owned by the sender, so the recipient could never
    /// use it. The object has to actually move.
    public entry fun transfer_stamp(
        mut stamp: Stamp,
        new_owner: address,
        clock: &Clock,
        ctx: &mut TxContext,
    ) {
        assert!(stamp.owner == ctx.sender(), ENotOwner);

        event::emit(StampTransferred {
            stamp_id: stamp.id.to_inner(),
            file_hash: stamp.file_hash,
            from: ctx.sender(),
            to: new_owner,
            timestamp_ms: clock.timestamp_ms(),
        });

        stamp.owner = new_owner;
        transfer::public_transfer(stamp, new_owner);
    }

    // ============ View Functions ============

    public fun get_owner(stamp: &Stamp): address { stamp.owner }
    public fun get_file_hash(stamp: &Stamp): vector<u8> { stamp.file_hash }
    public fun get_metadata_hash(stamp: &Stamp): vector<u8> { stamp.metadata_hash }
    public fun get_timestamp(stamp: &Stamp): u64 { stamp.timestamp_ms }
}
