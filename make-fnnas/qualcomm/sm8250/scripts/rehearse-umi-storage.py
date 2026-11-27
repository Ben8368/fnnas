#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Rehearse an Umi GPT split/rollback on a new sparse file, never on the phone."""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import stat
import subprocess
import tempfile
from uuid import UUID


PLANNER = runpy.run_path(str(Path(__file__).with_name("plan-umi-storage.py")))


def run(*args, input_text=None):
    proc = subprocess.run(args, input=input_text, capture_output=True, text=True, env=os.environ | {"LC_ALL": "C"})
    if proc.returncode:
        raise RuntimeError(f"{' '.join(args)}: {proc.stderr.strip()} {proc.stdout.strip()}")
    return proc.stdout


@contextmanager
def private_loop(image, *options):
    loop = run("losetup", "--find", "--show", *options, "--", str(image)).strip()
    if not re.fullmatch(r"/dev/loop[0-9]+", loop):
        raise ValueError(f"Unexpected loop device: {loop}")
    try:
        yield loop
    finally:
        run("losetup", "--detach", loop)


def partition_numbers(table):
    device = table["device"]
    if not re.fullmatch(r"/dev/sd[a-z]+", device):
        raise ValueError("expected a captured Umi UFS disk node")
    numbers = {}
    for part in table["partitions"]:
        match = re.fullmatch(re.escape(device) + r"([1-9][0-9]*)", part["node"])
        if not match or int(match[1]) in numbers:
            raise ValueError("unexpected or duplicate captured partition node")
        numbers[int(match[1])] = part
    return numbers


def layout_script(table, pieces, loop):
    uuid = str(UUID(table["id"]))
    count = int(table["table-length"])
    if not max(pieces) <= count <= 256 or not 1 <= table["firstlba"] < table["lastlba"]:
        raise ValueError("unexpected GPT entry array or usable range")
    lines = ["label: gpt", f"label-id: {uuid}", f"first-lba: {table['firstlba']}",
             f"last-lba: {table['lastlba']}", f"table-length: {count}", f"sector-size: {table['sectorsize']}", ""]
    for n, part in sorted(pieces.items()):
        name, attrs = part.get("name", ""), part.get("attrs", "")
        if not re.fullmatch(r"[a-zA-Z0-9_.-]*", name) or not re.fullmatch(r"[a-zA-Z0-9: ,]*", attrs):
            raise ValueError("unexpected partition name or attributes")
        line = (f"{loop}p{n}: start={part['start']}, size={part['size']}, "
                f"type={UUID(part['type'])}, uuid={UUID(part['uuid'])}")
        if name:
            line += f', name="{name}"'
        if attrs:
            line += f', attrs="{attrs}"'
        lines.append(line)
    return "\n".join(lines) + "\n"


def capture(loop, table, pieces):
    run("sfdisk", "--verify", loop)
    captured = json.loads(run("sfdisk", "--json", loop))
    actual = captured["partitiontable"]
    if actual["device"] != loop:
        raise ValueError("unexpected loop in the capture")
    actual["device"] = table["device"]
    renames = {f"{loop}p{n}": entry["node"] for n, entry in pieces.items()}
    for part in actual["partitions"]:
        part["node"] = renames[part["node"]]
    return captured


def rehearse(args):
    original = json.loads(args.gpt_capture.read_text(encoding="utf-8"))
    table = original["partitiontable"]
    filesystem_bytes = args.rootfs.stat().st_size
    result = PLANNER["plan"](original, args.root_device, filesystem_bytes)
    pieces = partition_numbers(table)
    index = next(n for n, p in pieces.items() if p["node"] == args.root_device)
    sector = result["sector_bytes"]
    size = args.disk_bytes
    head = table["firstlba"] * sector
    tail = (table["lastlba"] + 1) * sector
    offset = pieces[index]["start"] * sector
    if (not re.fullmatch(r"[0-9a-f]{64}", args.rootfs_sha256) or size % sector
            or not sector <= head < 1024**2 or not sector <= size - tail < 1024**2):
        raise ValueError("invalid rootfs digest or disk size versus GPT boundaries")
    # The only disk ever passed to sfdisk is a loop created from this private file.
    with tempfile.TemporaryDirectory(prefix="umi-storage-rehearsal-") as tmp:
        image = Path(tmp) / "umi-sparse.img"
        with image.open("xb") as out, args.rootfs.open("rb") as src:
            if not stat.S_ISREG(os.fstat(src.fileno()).st_mode):
                raise ValueError("rootfs input must be a regular image file")
            out.truncate(size)
            out.seek(offset)
            digest = hashlib.sha256()
            while block := src.read(8 * 1024**2):
                digest.update(block)
                out.write(block)
            if digest.hexdigest() != args.rootfs_sha256 or out.tell() != offset + filesystem_bytes:
                raise ValueError("rootfs image differs from the pinned bytes")
        with private_loop(image, "--sector-size", str(sector)) as disk:
            flags = ("--wipe", "never", "--wipe-partitions", "never")
            run("sfdisk", *flags, disk, input_text=layout_script(table, pieces, disk))
            before = capture(disk, table, pieces)
            if before != original:
                raise ValueError("reconstructed GPT differs from the captured partition layout")
            with open(disk, "rb", buffering=0) as device:
                primary = device.read(head)
                device.seek(tail)
                backup = device.read(size - tail)
            print(f"Original GPT reconstructed and verified: {len(pieces)} entries, {sector}-byte sectors", flush=True)
            run("sfdisk", *flags, "-N", str(index), disk, input_text=f"size={result['system']['bytes'] // sector}\n")
            split = capture(disk, table, pieces)
            checked = PLANNER["verify_split"](original, split, args.root_device, filesystem_bytes)
            print(json.dumps(checked, indent=2), flush=True)
            with private_loop(image, "--read-only", "--offset", str(offset),
                              "--sizelimit", str(result["system"]["bytes"])) as root:
                print(run("btrfs", "check", "--readonly", root), end="", flush=True)
            with open(disk, "r+b", buffering=0) as device:
                device.write(primary)
                device.seek(tail)
                device.write(backup)
                os.fsync(device.fileno())
                device.seek(0)
                if device.read(head) != primary:
                    raise ValueError("primary GPT bytes changed during rollback")
                device.seek(tail)
                if device.read(size - tail) != backup:
                    raise ValueError("backup GPT bytes changed during rollback")
            if capture(disk, table, pieces) != original:
                raise ValueError("rolled-back GPT differs from the reconstructed layout")
            print("Rollback verified: byte-identical primary and backup GPT regions on the offline clone.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("gpt_capture", type=Path)
    parser.add_argument("--disk-bytes", type=int, required=True)
    parser.add_argument("--root-device", required=True)
    parser.add_argument("--rootfs", type=Path, required=True)
    parser.add_argument("--rootfs-sha256", required=True)
    args = parser.parse_args()
    try:
        rehearse(args)
    except (OSError, KeyError, RuntimeError, StopIteration, TypeError, ValueError) as exc:
        parser.exit(1, f"Offline rehearsal stopped: {exc}\n")


if __name__ == "__main__":
    main()
