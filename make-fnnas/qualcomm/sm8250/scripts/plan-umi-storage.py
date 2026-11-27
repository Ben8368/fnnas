#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Preview a Umi 64 GiB userdata / user data split from a captured GPT; never write a device."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys
from uuid import UUID


SYSTEM_BYTES = 64 * 1024**3
ALIGN_BYTES = 1024**2


def natural(value, field, minimum=1):
    if type(value) is not int or value < minimum:
        raise ValueError(f"invalid {field}: expected integer >= {minimum}")
    return value


def plan(capture, root_device, filesystem_bytes):
    table = capture["partitiontable"]
    if table["label"] != "gpt" or table["unit"] != "sectors":
        raise ValueError("expected an sfdisk GPT capture in sectors")
    sector = natural(table["sectorsize"], "sectorsize")
    if sector not in (512, 4096):
        raise ValueError("unexpected Umi GPT sector size")
    first = natural(table["firstlba"], "firstlba")
    end = natural(table["lastlba"], "lastlba") + 1
    parts = sorted(table["partitions"], key=lambda p: natural(p["start"], "partition start"))
    if not parts or parts[-1].get("name") != "userdata" or parts[-1]["node"] != root_device:
        raise ValueError("the mounted root must be the last partition and named userdata")
    if sum(p.get("name") == "userdata" for p in parts) != 1:
        raise ValueError("ambiguous userdata partition")
    previous_end = first
    for p in parts:
        start = p["start"]
        if start < previous_end:
            raise ValueError("overlapping or out-of-range GPT entries")
        previous_end = start + natural(p["size"], "partition size")
        if previous_end > end:
            raise ValueError("partition extends past the usable GPT range")
    if previous_end != end:
        raise ValueError("unexpected free tail after userdata; review the layout manually")
    root = parts[-1]
    UUID(root["uuid"])
    UUID(root["type"])
    filesystem_bytes = natural(filesystem_bytes, "Btrfs device size")
    if not filesystem_bytes < SYSTEM_BYTES:
        raise ValueError("the existing Btrfs device must be smaller than 64 GiB")
    data_start = root["start"] + SYSTEM_BYTES // sector
    if data_start * sector % ALIGN_BYTES:
        raise ValueError("the 64 GiB boundary is not 1 MiB aligned")
    if data_start >= end:
        raise ValueError("no user-data space remains after reserving 64 GiB")
    return {
        "mode": "read-only plan; not an sfdisk input file",
        "device": table["device"],
        "sector_bytes": sector,
        "unchanged_partitions": len(parts) - 1,
        "system": {
            "node": root["node"], "name": root["name"], "partuuid": root["uuid"],
            "type": root["type"], "start_lba": root["start"], "end_lba_inclusive": data_start - 1,
            "bytes": SYSTEM_BYTES, "current_btrfs_device_bytes": filesystem_bytes,
        },
        "unallocated_tail_for_user_storage": {
            "start_lba": data_start, "end_lba_inclusive": end - 1, "bytes": (end - data_start) * sector,
        },
    }


def verify_split(before, after, root_device, filesystem_bytes):
    result = plan(before, root_device, filesystem_bytes)
    expected = deepcopy(before["partitiontable"])
    actual = deepcopy(after["partitiontable"])
    for table in (expected, actual):
        table["partitions"].sort(key=lambda part: part["node"])
    root = next(part for part in expected["partitions"] if part["node"] == root_device)
    root["size"] = result["system"]["bytes"] // result["sector_bytes"]
    if actual != expected:
        before_nodes = {p["node"]: p for p in expected.pop("partitions")}
        after_nodes = {p["node"]: p for p in actual.pop("partitions")}
        changed = sorted(n for n in before_nodes.keys() | after_nodes.keys()
                         if before_nodes.get(n) != after_nodes.get(n))
        raise ValueError(f"unexpected GPT changes: header={actual != expected}, partitions={changed}")
    return result | {"mode": "read-only verification; only userdata length changed"}


def verify_created(before, after, root_device, filesystem_bytes):
    """Check the single-partition layout produced by the pinned ARM64 system-tail path."""
    original = before["partitiontable"]
    disk = original["device"]
    if not root_device.startswith(disk) or not root_device[len(disk):].isdecimal():
        raise ValueError("unexpected UFS root node")
    next_number = int(root_device[len(disk):]) + 1
    node = f"{disk}{next_number}"
    count = original["table-length"]  # sfdisk also emits this GPT field as a string.
    if isinstance(count, str) and count.isascii() and count.isdecimal():
        count = int(count)
    if next_number > natural(count, "GPT table length"):
        raise ValueError("no free GPT entry after root")
    data = deepcopy(after)
    parts = data["partitiontable"]["partitions"]
    added = [p for p in parts if p["node"] == node]
    if len(added) != 1 or any(p["node"] == node for p in original["partitions"]):
        raise ValueError(f"expected exactly one new partition {node}")
    part, = added
    parts.remove(part)
    result = verify_split(before, data, root_device, filesystem_bytes)
    tail = result["unallocated_tail_for_user_storage"]
    start = natural(part["start"], "data partition start")
    size = natural(part["size"], "data partition size")
    slack = tail["end_lba_inclusive"] + 1 - start - size
    if start != tail["start_lba"] or not 0 <= slack * result["sector_bytes"] < ALIGN_BYTES:
        raise ValueError("data partition does not match the planned tail")
    if UUID(part["type"]) != UUID("a19d880f-05fc-4d3b-a006-743f0f84911e"):
        raise ValueError("expected the Linux RAID partition type from the fnOS system-disk path")
    guid = UUID(part["uuid"])
    if not guid.int or str(guid) in {str(UUID(p["uuid"])) for p in original["partitions"]}:
        raise ValueError("missing or reused data PARTUUID")
    return result | {"mode": "read-only GPT verification; not fnOS volume acceptance",
                     "data_partition": {"node": node, "bytes": size * result["sector_bytes"],
                                        "partuuid": str(guid), "unused_trailing_sectors": slack}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("gpt_capture", type=Path)
    parser.add_argument("--root-device", required=True, help="mounted root block device from findmnt")
    parser.add_argument("--btrfs-device-bytes", type=int, required=True, help="Device size from Btrfs usage")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--verify-created", type=Path, help="check the GPT after fnOS makes its single system-tail RAID partition")
    group.add_argument("--verify-after", type=Path, help="verify a subsequent sfdisk JSON capture before creating the data volume")
    args = parser.parse_args()
    try:
        data = json.loads(args.gpt_capture.read_text(encoding="utf-8"))
        if args.verify_created:
            after = json.loads(args.verify_created.read_text(encoding="utf-8"))
            result = verify_created(data, after, args.root_device, args.btrfs_device_bytes)
        elif args.verify_after:
            after = json.loads(args.verify_after.read_text(encoding="utf-8"))
            result = verify_split(data, after, args.root_device, args.btrfs_device_bytes)
        else:
            result = plan(data, args.root_device, args.btrfs_device_bytes)
        print(json.dumps(result, indent=2))
    except (OSError, AttributeError, KeyError, TypeError, ValueError) as exc:
        print(f"Refusing to plan: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
