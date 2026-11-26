#!/usr/bin/env python3
"""Repack a release boot image as a RAM-only Btrfs P0 test (never flash)."""
import argparse
from pathlib import Path
import re
import sys

from importlib.util import module_from_spec, spec_from_file_location


HERE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
PACKER = HERE / "pack-abl-v2.py"
spec = spec_from_file_location("pack_abl_v2", PACKER)
pack = module_from_spec(spec)
spec.loader.exec_module(pack)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("template", type=Path)
    parser.add_argument("ramdisk", type=Path, help="complete gzip initramfs with Btrfs module and RAM test volume")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        header, kernel, _old_ramdisk, dtb = pack.split_boot(args.template.read_bytes())
        cmdline = header[64:576].split(b"\0", 1)[0]
        uuids = re.findall(rb"(?:^| )root=UUID=([0-9a-f-]{36})(?= |$)", cmdline)
        if len(uuids) != 1 or re.search(rb"(?:^| )(?:rdinit|panic|umi_probe_id)=", cmdline):
            raise ValueError("expected the unmodified 90 Hz CSOT release boot command line")
        result = pack.repack(
            header,
            kernel,
            args.ramdisk.read_bytes(),
            dtb,
            uuids[0].decode(),
            append_cmdline=b"rdinit=/umi-p0-btrfs-test panic=10 umi_probe_id=p0-btrfs-20261125",
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("xb") as f:
            f.write(result)
    except (ValueError, OSError) as e:
        parser.exit(1, f"{e}\n")
    print(f"RAM-only Btrfs P0 image; use fastboot boot, never flash: {args.output}")


if __name__ == "__main__":
    main()
