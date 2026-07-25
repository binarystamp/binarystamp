import { BigInt, Bytes } from "@graphprotocol/graph-ts"
import {
  StampCreated as StampCreatedEvent,
  StampTransferred as StampTransferredEvent
} from "../generated/BinaryStamp/BinaryStamp"
import { Stamp, Transfer, FileHashLookup, OwnerStats } from "../generated/schema"

export function handleStampCreated(event: StampCreatedEvent): void {
  let stampId = event.params.stampNumber.toString()
  let stamp = new Stamp(stampId)

  stamp.fileHash = event.params.fileHash
  stamp.metadataHash = event.params.metadataHash
  stamp.walrusBlobId = event.params.walrusBlobId
  stamp.owner = event.params.owner
  stamp.timestamp = event.params.timestamp
  stamp.stampNumber = event.params.stampNumber
  stamp.description = event.params.description
  stamp.createdAt = event.block.timestamp
  stamp.blockNumber = event.block.number
  stamp.transactionHash = event.transaction.hash
  stamp.save()

  // Update FileHashLookup
  let fileHashHex = event.params.fileHash.toHexString()
  let lookup = FileHashLookup.load(fileHashHex)
  if (lookup == null) {
    lookup = new FileHashLookup(fileHashHex)
    lookup.fileHash = event.params.fileHash
    lookup.stamps = [stampId]
    lookup.latestOwner = event.params.owner
    lookup.stampCount = BigInt.fromI32(1)
    lookup.firstStampedAt = event.block.timestamp
  } else {
    let stamps = lookup.stamps
    stamps.push(stampId)
    lookup.stamps = stamps
    lookup.latestOwner = event.params.owner
    lookup.stampCount = lookup.stampCount.plus(BigInt.fromI32(1))
  }
  lookup.save()

  // Update OwnerStats
  let ownerHex = event.params.owner.toHexString()
  let ownerStats = OwnerStats.load(ownerHex)
  if (ownerStats == null) {
    ownerStats = new OwnerStats(ownerHex)
    ownerStats.stampCount = BigInt.fromI32(1)
    ownerStats.stamps = [stampId]
  } else {
    ownerStats.stampCount = ownerStats.stampCount.plus(BigInt.fromI32(1))
    let stamps = ownerStats.stamps
    stamps.push(stampId)
    ownerStats.stamps = stamps
  }
  ownerStats.save()
}

export function handleStampTransferred(event: StampTransferredEvent): void {
  let transferId = event.transaction.hash.toHexString() + "-" + event.logIndex.toString()
  let transfer = new Transfer(transferId)

  // Find the stamp by fileHash lookup
  let fileHashHex = event.params.fileHash.toHexString()
  let lookup = FileHashLookup.load(fileHashHex)
  if (lookup != null && lookup.stamps.length > 0) {
    let stamps = lookup.stamps
    let latestStampId = stamps[stamps.length - 1]
    transfer.stamp = latestStampId

    // Update the stamp owner
    let stamp = Stamp.load(latestStampId)
    if (stamp != null) {
      stamp.owner = event.params.to
      stamp.save()
    }

    // Update lookup
    lookup.latestOwner = event.params.to
    lookup.save()
  }

  transfer.fileHash = event.params.fileHash
  transfer.from = event.params.from
  transfer.to = event.params.to
  transfer.timestamp = event.params.timestamp
  transfer.blockNumber = event.block.number
  transfer.transactionHash = event.transaction.hash
  transfer.save()
}
