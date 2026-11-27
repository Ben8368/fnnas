#!/usr/bin/env python3
"""Preflight Android DTBO overlays against a Umi release base DTB (host only)."""
import argparse
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile


DT_TABLE_MAGIC = 0xD7B7AB1E
FDT_MAGIC = b"\xd0\x0d\xfe\xed"


def table_layout(table):
    if len(table) < 32:
        raise ValueError("truncated Android DTBO table header")
    magic, total, hsize, esize, count, entries, _, version = struct.unpack_from(">8I", table)
    if magic != DT_TABLE_MAGIC or version != 0:
        raise ValueError("expected an uncompressed Android DTBO v0 table")
    end_entries = entries + esize * count
    if not (32 <= hsize <= entries <= end_entries <= total <= len(table) and esize >= 32):
        raise ValueError("invalid Android DTBO table bounds")
    return esize, count, entries, end_entries, total


def extract_entry(table, index):
    esize, count, entries, end_entries, total = table_layout(table)
    if index < 0 or index >= count:
        raise ValueError(f"DTBO index {index} outside table (entries={count})")
    length, start = struct.unpack_from(">2I", table, entries + esize * index)
    if length < 40 or not (end_entries <= start <= start + length <= total):
        raise ValueError(f"invalid DTBO payload bounds for index {index}")
    blob = table[start : start + length]
    if blob[:4] != FDT_MAGIC or not 40 <= struct.unpack_from(">I", blob, 4)[0] <= length:
        raise ValueError(f"entry {index} is not a complete FDT")
    return blob


def properties(fdt, node):
    # Distinguish a genuinely absent node from an unreadable or invalid FDT.
    nodes = subprocess.check_output(["fdtget", "-l", str(fdt), "/"], text=True).splitlines()
    if node not in nodes:
        return set()
    props = subprocess.check_output(["fdtget", "-p", str(fdt), f"/{node}"], text=True)
    return set(props.splitlines())


def live_tree(blob, scratch):
    """Canonical live DT after dropping only inert overlay data and symbol metadata."""
    status = subprocess.check_output(['fdtget', '-t', 's', blob, '/abl_ovf', 'status'], text=True)
    if status.strip() != 'disabled':
        raise ValueError('ABL quarantine must remain disabled')
    shutil.copyfile(blob, scratch)
    for node in ('/abl_ovf', '/__symbols__'):
        subprocess.run(['fdtput', '-r', scratch, node], check=True)
    return subprocess.check_output(['dtc', '-q', '-s', '-I', 'dtb', '-O', 'dts', scratch])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("table", type=Path, help="Android DTBO image (read only)")
    p.add_argument("index", help="selected DTBO index, or 'all' for an official replacement image")
    p.add_argument("base_dtb", type=Path, help="independent base DTB extracted from a boot image")
    p.add_argument('--protect-live', action='store_true', help='reject changes outside disabled vendor targets')
    args = p.parse_args()
    index = args.index
    try:
        table = args.table.read_bytes()
        _, count, _, _, _ = table_layout(table)
        if not count:
            raise ValueError("empty DTBO table")
        indices = range(count) if args.index == "all" else (int(args.index),)
        with tempfile.TemporaryDirectory(prefix="umi-dtbo-") as tmp:
            scratch = Path(tmp)
            overlay, applied = scratch / "selected.dtbo", scratch / "applied.dtb"
            symbols = properties(args.base_dtb, "__symbols__")
            before = live_tree(args.base_dtb, scratch / "before") if args.protect_live else None
            for index in indices:
                overlay.write_bytes(extract_entry(table, index))
                missing = properties(overlay, "__fixups__") - symbols
                if missing:
                    raise ValueError("missing overlay symbols: " + ", ".join(sorted(missing)))
                subprocess.run(["fdtoverlay", "-i", str(args.base_dtb), "-o",
                                str(applied), str(overlay)], check=True)
                if args.protect_live and before != live_tree(applied, scratch / "after"):
                    raise ValueError("overlay modified the live hardware tree")
    except (ValueError, OSError, subprocess.CalledProcessError) as e:
        p.exit(1, f"DTBO preflight failed (index {index}): {e}\n")
    label = f"all {count} entries" if args.index == "all" else f"index {index}"
    print(f"DTBO {label}: overlay preflight passed against {args.base_dtb}")


if __name__ == "__main__":
    main()
