// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title BinaryStamp ENS CCIP-Read Resolver (EIP-3668)
/// @notice Offchain resolver that redirects ENS lookups to our gateway
interface IExtendedResolver {
    function resolve(bytes calldata name, bytes calldata data) external view returns (bytes memory);
}

interface ISupportsInterface {
    function supportsInterface(bytes4 interfaceId) external pure returns (bool);
}

contract BinaryStampResolver is IExtendedResolver, ISupportsInterface {
    string[] public urls;
    address public owner;

    // ENS resolver interface IDs
    bytes4 constant private ADDR_INTERFACE_ID = 0x3b3b57de;           // addr(bytes32)
    bytes4 constant private ADDRESS_INTERFACE_ID = 0xf1cb7e06;        // addr(bytes32,uint256)
    bytes4 constant private TEXT_INTERFACE_ID = 0x59d1d43c;            // text(bytes32,string)
    bytes4 constant private CONTENTHASH_INTERFACE_ID = 0xbc1c58d1;     // contenthash(bytes32)
    bytes4 constant private EXTENDED_RESOLVER_ID = 0x9061b923;         // resolve(bytes,bytes)
    bytes4 constant private SUPPORTS_INTERFACE_ID = 0x01ffc9a7;        // supportsInterface(bytes4)

    // EIP-3668 OffchainLookup error
    error OffchainLookup(
        address sender,
        string[] urls,
        bytes callData,
        bytes4 callbackFunction,
        bytes extraData
    );

    constructor(string[] memory _urls) {
        urls = _urls;
        owner = msg.sender;
    }

    /// @notice EIP-3668: resolve triggers OffchainLookup
    function resolve(bytes calldata name, bytes calldata data)
        external
        view
        override
        returns (bytes memory)
    {
        revert OffchainLookup(
            address(this),
            urls,
            abi.encode(name, data),
            this.resolveWithProof.selector,
            abi.encode(name, data)
        );
    }

    /// @notice Callback after offchain lookup
    function resolveWithProof(bytes calldata response, bytes calldata extraData)
        external
        pure
        returns (bytes memory)
    {
        return response;
    }

    /// @notice Update gateway URLs
    function setUrls(string[] memory _urls) external {
        require(msg.sender == owner, "Not owner");
        urls = _urls;
    }

    /// @notice EIP-165 interface support
    /// Declares support for all standard ENS resolver interfaces.
    /// Actual resolution goes through resolve(bytes,bytes) -> CCIP-Read gateway.
    function supportsInterface(bytes4 interfaceId)
        external
        pure
        override
        returns (bool)
    {
        return
            interfaceId == EXTENDED_RESOLVER_ID ||
            interfaceId == SUPPORTS_INTERFACE_ID ||
            interfaceId == ADDR_INTERFACE_ID ||
            interfaceId == ADDRESS_INTERFACE_ID ||
            interfaceId == TEXT_INTERFACE_ID ||
            interfaceId == CONTENTHASH_INTERFACE_ID;
    }
}
