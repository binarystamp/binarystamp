#[test_only]
module binarystamp::stamp_tests {
    use binarystamp::stamp::{Self, Stamp, Registry};
    use std::string;
    use sui::clock;
    use sui::test_scenario as ts;

    const ALICE: address = @0xA;
    const BOB: address = @0xB;

    fun file_hash(): vector<u8> {
        x"aabbccddeeff00112233445566778899aabbccddeeff00112233445566778899"
    }

    fun metadata_hash(): vector<u8> {
        x"1111111111111111111111111111111111111111111111111111111111111111"
    }

    /// Run `init` so the shared Registry exists, then start a fresh tx.
    fun begin(): ts::Scenario {
        let mut scenario = ts::begin(ALICE);
        stamp::init_for_testing(ts::ctx(&mut scenario));
        ts::next_tx(&mut scenario, ALICE);
        scenario
    }

    fun create_stamp(scenario: &mut ts::Scenario) {
        let mut registry = ts::take_shared<Registry>(scenario);
        let clock = clock::create_for_testing(ts::ctx(scenario));
        stamp::stamp(
            &mut registry,
            file_hash(),
            metadata_hash(),
            string::utf8(b"blob"),
            string::utf8(b"a file"),
            &clock,
            ts::ctx(scenario),
        );
        clock::destroy_for_testing(clock);
        ts::return_shared(registry);
    }

    #[test]
    fun stamp_is_owned_by_its_creator() {
        let mut scenario = begin();
        create_stamp(&mut scenario);

        ts::next_tx(&mut scenario, ALICE);
        let created = ts::take_from_sender<Stamp>(&scenario);
        assert!(stamp::get_owner(&created) == ALICE, 0);
        assert!(stamp::get_file_hash(&created) == file_hash(), 1);
        ts::return_to_sender(&scenario, created);

        ts::end(scenario);
    }

    #[test]
    fun transfer_moves_the_object_to_the_new_owner() {
        let mut scenario = begin();
        create_stamp(&mut scenario);

        // Alice hands the stamp to Bob.
        ts::next_tx(&mut scenario, ALICE);
        let owned = ts::take_from_sender<Stamp>(&scenario);
        let clock = clock::create_for_testing(ts::ctx(&mut scenario));
        stamp::transfer_stamp(owned, BOB, &clock, ts::ctx(&mut scenario));
        clock::destroy_for_testing(clock);

        // Alice must no longer hold it...
        ts::next_tx(&mut scenario, ALICE);
        assert!(!ts::has_most_recent_for_sender<Stamp>(&scenario), 0);

        // ...and Bob must, with ownership recorded.
        ts::next_tx(&mut scenario, BOB);
        let received = ts::take_from_sender<Stamp>(&scenario);
        assert!(stamp::get_owner(&received) == BOB, 1);
        ts::return_to_sender(&scenario, received);

        ts::end(scenario);
    }

    #[test]
    #[expected_failure(abort_code = stamp::ENotOwner)]
    fun non_owner_cannot_transfer() {
        let mut scenario = begin();
        create_stamp(&mut scenario);

        // Take Alice's stamp, then try to transfer it as Bob.
        ts::next_tx(&mut scenario, ALICE);
        let owned = ts::take_from_sender<Stamp>(&scenario);

        ts::next_tx(&mut scenario, BOB);
        let clock = clock::create_for_testing(ts::ctx(&mut scenario));
        stamp::transfer_stamp(owned, ALICE, &clock, ts::ctx(&mut scenario));

        clock::destroy_for_testing(clock);
        ts::end(scenario);
    }
}
