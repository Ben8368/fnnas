#!/usr/bin/env python3
"""Repack the known ABL Android v2 layout with a new kernel/initrd/DTB."""
import argparse
import hashlib
from pathlib import Path
import re
import struct


def layout(template):
    if template[:8] != b"ANDROID!" or len(template) < 4096:
        raise ValueError("expected a complete Android boot header")
    ks, kaddr, rs, raddr, second_size, _, _, page, version, _ = struct.unpack_from(
        "<10I", template, 8
    )
    recovery_size, _, header_size, ds, dtb_addr = struct.unpack_from("<IQIIQ", template, 1632)
    if (page, version, header_size, second_size, recovery_size) != (4096, 2, 1660, 0, 0):
        raise ValueError("unexpected ABL boot layout")

    return (ks, rs, ds), (kaddr, raddr, dtb_addr), page


def split_boot(image):
    sizes, _, page = layout(image)
    pos = page
    parts = []
    for size, magic in zip(sizes, (b"\x1f\x8b", b"\x1f\x8b", b"\xd0\x0d\xfe\xed")):
        part = image[pos : pos + size]
        if len(part) != size or not part.startswith(magic):
            raise ValueError("truncated or invalid boot segment")
        parts.append(part)
        pos = (pos + size + page - 1) // page * page
    if pos != len(image):
        raise ValueError("unexpected padding or trailing data in boot image")
    return image[:page], *parts


def repack(template, kernel, ramdisk, dtb, root_uuid, *, append_cmdline=b"", native_cmdline=None):
    cmdline = template[64:576].split(b"\0", 1)[0]
    extra = template[608:1632].split(b"\0", 1)[0]
    if extra:
        raise ValueError("unexpected extended command line")
    if not re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", root_uuid):
        raise ValueError("invalid root UUID")
    cmdline, count = re.subn(rb"(?<=root=UUID=)[0-9a-f-]{36}\b", root_uuid.encode(), cmdline)
    if count != 1:
        raise ValueError("expected exactly one root UUID in template")
    if native_cmdline is not None:
        if any(c < 32 or c > 126 for c in native_cmdline):
            raise ValueError("MiSeed command line must be printable ASCII")
        args = native_cmdline.split()
        if args.count(b"rdinit=/init") != 1:
            raise ValueError("unexpected MiSeed rescue command line")
        args.remove(b"rdinit=/init")
        storage = {b"root", b"rootwait", b"rootdelay", b"swiotlb", b"loop.max_part", b"pstore.backend"}
        if any(arg.split(b"=", 1)[0] in storage | {b"rdinit", b"init", b"consoleblank"} for arg in args):
            raise ValueError("unexpected MiSeed rescue command line")
        cmdline = b" ".join(args + [
            arg for arg in cmdline.split() if arg.split(b"=", 1)[0] in storage
        ])
    if append_cmdline:
        if any(c < 32 or c > 126 for c in append_cmdline):
            raise ValueError("extra command line must be printable ASCII")
        cmdline += b" " + append_cmdline
    return pack_boot(template, kernel, ramdisk, dtb, cmdline)


def pack_boot(template, kernel, ramdisk, dtb, cmdline):
    _, (kaddr, raddr, dtb_addr), page = layout(template)
    if kernel[:2] != b"\x1f\x8b" or ramdisk[:2] != b"\x1f\x8b" or dtb[:4] != b"\xd0\x0d\xfe\xed":
        raise ValueError("expected gzip kernel, gzip ramdisk, and valid DTB magic")
    if kaddr + len(kernel) > raddr or raddr + len(ramdisk) > dtb_addr:
        raise ValueError("boot segments overlap in the template load layout")
    if any(c < 32 or c > 126 for c in cmdline):
        raise ValueError("boot command line must be printable ASCII")
    if len(cmdline) >= 512:
        raise ValueError("boot command line does not fit in the primary field")
    header = bytearray(template[:page])
    header[64:576] = cmdline.ljust(512, b"\0")
    for offset, payload in [(8, kernel), (16, ramdisk), (1648, dtb)]:
        struct.pack_into("<I", header, offset, len(payload))
    # Android v2 ID: SHA-1 over each segment followed by its little-endian size.
    digest = hashlib.sha1()
    for payload in (kernel, ramdisk, b"", b"", dtb):
        digest.update(payload)
        digest.update(struct.pack("<I", len(payload)))
    header[576:608] = digest.digest().ljust(32, b"\0")
    return bytes(header) + b"".join(p + bytes(-len(p) % page) for p in (kernel, ramdisk, dtb))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for path in ("template", "kernel", "ramdisk", "dtb", "output"):
        parser.add_argument(path, type=Path)
    parser.add_argument("root_uuid")
    parser.add_argument("--native-btrfs", action="store_true")
    parser.add_argument("--native-cmdline", type=Path, help="command line from the pinned MiSeed build")
    args = parser.parse_args()
    with args.template.open("rb") as template:
        header = template.read(4096)
    native_cmdline = args.native_cmdline.read_bytes().rstrip(b"\n") if args.native_cmdline else None
    result = repack(header, args.kernel.read_bytes(), args.ramdisk.read_bytes(),
                    args.dtb.read_bytes(), args.root_uuid, native_cmdline=native_cmdline,
                    append_cmdline=b"rootfstype=btrfs rootflags=subvolid=5 printk.devkmsg=on" if args.native_btrfs else b"")
    args.output.write_bytes(result)


if __name__ == "__main__":
    main()
