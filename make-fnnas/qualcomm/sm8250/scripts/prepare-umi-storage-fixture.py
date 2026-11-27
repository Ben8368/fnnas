#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Prepare regular-file GPT fixtures for the audited 256 GB Umi geometry, never open a disk for writing."""
import argparse
import hashlib
import json
from pathlib import Path
import runpy
import struct
from uuid import UUID
import zlib

PLAN = runpy.run_path(str(Path(__file__).with_name("plan-umi-storage.py")))["plan"]
SECTOR = 4096
LAST = 62_201_855
RAID = UUID("a19d880f-05fc-4d3b-a006-743f0f84911e")


def check(ok, message):
    if not ok:
        raise ValueError(message)


def inspect(raw, backup, table, root):
    # The backup input must NOT contain the final usable sector of userdata.
    check(len(raw) == (5 if backup else 6) * SECTOR, "not the exact metadata-only region")
    off = (4 if backup else 1) * SECTOR
    arr = 0 if backup else 2 * SECTOR
    hdr = bytearray(raw[off:off + 92])
    check(hdr[:8] == b"EFI PART" and struct.unpack_from("<II", hdr, 8) == (0x10000, 92), "GPT version")
    crc, = struct.unpack_from("<I", hdr, 16)
    struct.pack_into("<I", hdr, 16, 0)
    check(zlib.crc32(hdr) == crc, "GPT header CRC")
    geometry = struct.unpack_from("<QQQQ", hdr, 24)
    check(geometry == ((LAST, 1, 6, LAST - 5) if backup else (1, LAST, 6, LAST - 5)), "GPT geometry")
    check(UUID(bytes_le=bytes(hdr[56:72])) == UUID(table["id"]), "wrong disk GUID")
    entry_lba, count, stride, array_crc = struct.unpack_from("<QIII", hdr, 72)
    check((entry_lba, count, stride) == ((LAST - 4 if backup else 2), 64, 128), "unexpected GPT array location")
    entries = raw[arr:arr + count * stride]
    check(zlib.crc32(entries) == array_crc, "GPT array CRC")
    check(not any(entries[34 * stride:]), "GPT entries after userdata are not empty")
    check(len(table["partitions"]) == 34, "expected exactly 34 partitions")
    by_node = {p["node"]: p for p in table["partitions"]}
    check(set(by_node) == {f"/dev/sda{n}" for n in range(1, 35)}, "expected Umi partitions 1 through 34")
    for i in range(34):
        part = by_node[f"/dev/sda{i + 1}"]
        entry = entries[i * stride:(i + 1) * stride]
        check(UUID(part["type"]).bytes_le == entry[:16]
              and UUID(part["uuid"]).bytes_le == entry[16:32], "captured partition identity differs")
        check(struct.unpack_from("<QQ", entry, 32) == (part["start"], part["start"] + part["size"] - 1)
              and entry[56:].decode("utf-16le").rstrip("\0") == part["name"], "captured partition differs")
    check(root["start_lba"] == 2_883_584 and root["node"] == "/dev/sda34", "not the audited Umi layout")
    if not backup:
        check(raw[510:512] == b"\x55\xaa" and raw[450] == 0xee, "unexpected protective MBR")
    return off, arr, entries


def prepare(capture, btrfs_bytes, primary, backup, data_guid=None):
    table = capture["partitiontable"]
    check((table["device"], table["sectorsize"], table["firstlba"], table["lastlba"], str(table["table-length"]))
          == ("/dev/sda", SECTOR, 6, LAST - 5, "64"), "unsupported Umi GPT geometry")
    plan = PLAN(capture, "/dev/sda34", btrfs_bytes)
    headers = [inspect(raw, i == 1, table, plan["system"]) for i, raw in enumerate((primary, backup))]
    check(headers[0][2] == headers[1][2], "primary and backup array bytes disagree")
    entries = bytearray(headers[0][2])
    end = plan["system"]["end_lba_inclusive"]
    struct.pack_into("<Q", entries, 33 * 128 + 40, end)
    if data_guid is not None:
        check(data_guid.int and data_guid != UUID(table["id"]) and all(data_guid != UUID(p["uuid"]) for p in table["partitions"]),
              "new data GUID must be unique")
        # Match the vendor's last full MiB; preserve the small tail before backup GPT.
        data_end = (table["lastlba"] + 1) // 256 * 256 - 1
        struct.pack_into("<16s16sQQQ72s", entries, 34 * 128, RAID.bytes_le, data_guid.bytes_le,
                         end + 1, data_end, 0, "primary".encode("utf-16le"))
    result = []
    for original, (off, arr, _) in zip((primary, backup), headers):
        buf = bytearray(original)
        buf[arr:arr + len(entries)] = entries
        struct.pack_into("<I", buf, off + 88, zlib.crc32(entries))
        struct.pack_into("<I", buf, off + 16, 0)
        struct.pack_into("<I", buf, off + 16, zlib.crc32(buf[off:off + 92]))
        result.append(bytes(buf))
    return result


def read(path, digest, length):
    check(path.is_file() and path.stat().st_size == length, "expected a regular metadata-only file of exact length")
    data = path.read_bytes()
    check(hashlib.sha256(data).hexdigest() == digest, "archived metadata SHA-256 mismatch")
    return data


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("capture", type=Path)
    for key in ("primary", "backup"):
        ap.add_argument("--" + key, type=Path, required=True)
        ap.add_argument("--" + key + "-sha256", required=True)
    ap.add_argument("--btrfs-device-bytes", type=int, required=True)
    ap.add_argument("--test-data-guid", type=UUID, help="also synthesize partition 35 for a VM (not the default)")
    ap.add_argument("--out", type=Path, required=True, help="new directory for private fixture files")
    args = ap.parse_args()
    try:
        capture = json.loads(args.capture.read_text(encoding="utf-8"))
        blocks = prepare(capture, args.btrfs_device_bytes, read(args.primary, args.primary_sha256, 6 * SECTOR),
                         read(args.backup, args.backup_sha256, 5 * SECTOR), args.test_data_guid)
        args.out.mkdir(mode=0o700, exist_ok=False)
        for name, block in zip(("primary.fixture", "backup.fixture"), blocks):
            with (args.out / name).open("xb") as f:
                f.write(block)
            print(hashlib.sha256(block).hexdigest(), name)
    except (ValueError, OSError, KeyError, TypeError, struct.error) as exc:
        ap.exit(1, f"Refusing fixture: {exc}\n")


if __name__ == "__main__":
    main()
