#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Assemble an independent Xiaomi umi RAM Recovery; never flash the output."""
import argparse
import gzip
import hashlib
from importlib.util import module_from_spec, spec_from_file_location
import os
from pathlib import Path
import re
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
spec = spec_from_file_location("umi_ram_probe", HERE.parent / "tools" / "make-ram-probe.py")
probe = module_from_spec(spec)
spec.loader.exec_module(probe)

# Keep only known board startup/display knobs. In particular, do not pass the
# donor's root=, rootwait, init=, pstore or any persistent-root options to Linux.
KEEP = frozenset(b"console loglevel keep_bootcon earlycon pd_ignore_unused clk_ignore_unused "
                 b"regulator_ignore_unused fbcon swiotlb".split())


def assemble(base, init, expected):
    if not re.fullmatch(r"[0-9a-f]{64}", expected) or hashlib.sha256(base).hexdigest() != expected:
        raise ValueError("base boot SHA-256 mismatch")
    header, kernel, _, dtb = probe.pack.split_boot(base)
    cmdline = header[64:576].split(b"\0", 1)[0].split()
    if (any(header[608:1632]) or cmdline.count(b"rootfstype=btrfs") != 1
            or cmdline.count(b"rootflags=subvolid=5") != 1
            or sum(arg.startswith(b"root=") for arg in cmdline) != 1
            or not any(re.fullmatch(rb"root=UUID=[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", arg)
                       for arg in cmdline)):
        raise ValueError("expected an explicitly pinned native Umi Btrfs boot image")
    flags = [arg for arg in cmdline if arg.partition(b"=")[0] in KEEP]
    flags.extend((b"rdinit=/init", b"panic=10"))
    archive = (probe.newc_entry("init", 1, 0o100755, init)
               + probe.newc_entry("boot-sha256", 2, 0o100444, expected.encode("ascii") + b"\n")
               + probe.newc_entry("TRAILER!!!", 0, 0, b""))
    return probe.pack.pack_boot(header, kernel, gzip.compress(archive, mtime=0), dtb, b" ".join(flags))


def build_init(path):
    subprocess.run(["go", "build", "-trimpath", "-ldflags=-s -w -buildid=", "-o", str(path),
                    "init_linux.go", "protocol.go", "storage_linux.go"], cwd=HERE, check=True, env={
        **os.environ, "CGO_ENABLED": "0", "GOOS": "linux", "GOARCH": "arm64", "GOARM64": "v8.0",
        "GOTOOLCHAIN": "local", "GOENV": "off", "GOFLAGS": "", "GOWORK": "off",
    })
    return path.read_bytes()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_boot", type=Path, help="native boot.img from the authorized local build")
    parser.add_argument("output", type=Path, help="new RAM-only recovery image")
    parser.add_argument("--boot-sha256", required=True, help="boot.img SHA-256 from native build evidence")
    args = parser.parse_args()
    try:
        if args.output.exists():
            raise ValueError("refusing to overwrite an existing recovery image")
        base = args.base_boot.read_bytes()
        with tempfile.TemporaryDirectory(prefix="umi-recovery-") as tmp:
            image = assemble(base, build_init(Path(tmp) / "init"), args.boot_sha256)
        with args.output.open("xb") as output:
            output.write(image)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"{exc}\n")
    print(f"{hashlib.sha256(image).hexdigest()}  {args.output}")
    print("RAM-only image: use only fastboot boot after stock DTBO preflight and authorization; never flash.")


if __name__ == "__main__":
    main()
