// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title BinaryStamp - File hash registry (EVM mirror)
/// @notice Mirrors stamps from Sui for EVM indexing via The Graph
contract BinaryStamp {
    struct Stamp {
        bytes32 fileHash;
        bytes32 metadataHash;
        string walrusBlobId;
        address owner;
        uint256 timestamp;
        string description;
    }

    mapping(bytes32 => Stamp[]) public stamps;
    mapping(uint256 => bytes32) public stampByNumber;
    uint256 public stampCount;

    event StampCreated(
        bytes32 indexed fileHash,
        bytes32 metadataHash,
        string walrusBlobId,
        address indexed owner,
        uint256 timestamp,
        uint256 indexed stampNumber,
        string description
    );

    event StampTransferred(
        bytes32 indexed fileHash,
        address indexed from,
        address indexed to,
        uint256 timestamp
    );

    /// @notice Register a file hash
    function stamp(
        bytes32 fileHash,
        bytes32 metadataHash,
        string calldata walrusBlobId,
        string calldata description
    ) external {
        uint256 number = stampCount++;
        stamps[fileHash].push(Stamp({
            fileHash: fileHash,
            metadataHash: metadataHash,
            walrusBlobId: walrusBlobId,
            owner: msg.sender,
            timestamp: block.timestamp,
            description: description
        }));
        stampByNumber[number] = fileHash;

        emit StampCreated(
            fileHash,
            metadataHash,
            walrusBlobId,
            msg.sender,
            block.timestamp,
            number,
            description
        );
    }

    /// @notice Transfer the latest stamp ownership for a file hash
    function transferStamp(bytes32 fileHash, address newOwner) external {
        Stamp[] storage fileStamps = stamps[fileHash];
        require(fileStamps.length > 0, "No stamp found");
        Stamp storage latest = fileStamps[fileStamps.length - 1];
        require(latest.owner == msg.sender, "Not owner");

        emit StampTransferred(fileHash, msg.sender, newOwner, block.timestamp);
        latest.owner = newOwner;
    }

    /// @notice Look up stamps for a file hash
    function getStamps(bytes32 fileHash) external view returns (Stamp[] memory) {
        return stamps[fileHash];
    }

    /// @notice Get latest stamp for a file hash
    function getLatestStamp(bytes32 fileHash) external view returns (Stamp memory) {
        Stamp[] storage fileStamps = stamps[fileHash];
        require(fileStamps.length > 0, "No stamp found");
        return fileStamps[fileStamps.length - 1];
    }

    /// @notice Check if a file hash has been stamped
    function isStamped(bytes32 fileHash) external view returns (bool) {
        return stamps[fileHash].length > 0;
    }

    /// @notice Get stamp count for a file hash
    function getStampCount(bytes32 fileHash) external view returns (uint256) {
        return stamps[fileHash].length;
    }
}
