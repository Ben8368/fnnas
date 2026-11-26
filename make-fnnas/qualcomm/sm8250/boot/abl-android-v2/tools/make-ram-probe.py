#!/usr/bin/env python3
"""Build a RAM-only, timed Xiaomi umi probe from a release boot (never flash)."""
import argparse
import gzip
from pathlib import Path
import re

from importlib.util import module_from_spec, spec_from_file_location


HERE = Path(__file__).resolve().parent
PACKER = HERE / "pack-abl-v2.py"
spec = spec_from_file_location("pack_abl_v2", PACKER)
pack = module_from_spec(spec)
spec.loader.exec_module(pack)


def pad4(data):
    return data + bytes(-len(data) % 4)


def newc_entry(name, inode, mode, data):
    name = name.encode("ascii") + b"\0"
    fields = (inode, mode, 0, 0, 1, 0, len(data), 0, 0, 0, 0, len(name), 0)
    return pad4(b"070701" + b"".join(f"{v:08x}".encode() for v in fields) + name) + pad4(data)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("boot", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("--base-dtb", type=Path, help="override DTB only for a baseline comparison")
    p.add_argument("--display-vblank", type=Path, help="include a static ARM64 DRM callback probe")
    p.add_argument("--gpu-check", type=Path, help="include a static ARM64 MSM initialization probe")
    p.add_argument("--package-sha256", help="Embed the exact kernel bundle digest in the physical acceptance log")
    args = p.parse_args()
    try:
        header, kernel, ramdisk, dtb = pack.split_boot(args.boot.read_bytes())
        cmdline = header[64:576].split(b"\0", 1)[0]
        uuid = re.findall(rb"(?:^| )root=UUID=([0-9a-f-]{36})(?= |$)", cmdline)
        if len(uuid) != 1 or re.search(rb"(?:^| )(?:rdinit|panic|umi_probe_id)=", cmdline):
            raise ValueError("expected an unmodified release command line with one root UUID")
        if args.base_dtb:
            dtb = args.base_dtb.read_bytes()
        script = (HERE / "umi-ram-probe.sh").read_bytes()
        if args.package_sha256:
            if args.base_dtb or not re.fullmatch(r"[0-9a-f]{64}", args.package_sha256):
                raise ValueError("package acceptance requires a SHA-256 and the unmodified bundle DTB")
            marker = b'log "PID1 kernel=$(uname -r)"'
            if script.count(marker) != 1:
                raise ValueError("missing probe identity insertion point")
            script = script.replace(marker, marker + b"\nlog artifact_sha256=" + args.package_sha256.encode())
        probe = newc_entry("umi-probe", 1, 0o100755, script)
        for inode, (name, path) in enumerate((
            ("umi-display-vblank", args.display_vblank), ("umi-gpu-check", args.gpu_check)
        ), start=2):
            if path is None:
                continue
            sampler = path.read_bytes()
            if not sampler.startswith(b"\x7fELF\x02\x01") or sampler[18:20] != b"\xb7\x00":
                raise ValueError(f"expected a little-endian ARM64 ELF probe: {path}")
            probe += newc_entry(name, inode, 0o100755, sampler)
        probe += newc_entry("TRAILER!!!", 0, 0, b"")
        boot = pack.repack(header, kernel, ramdisk + gzip.compress(probe, mtime=0), dtb,
                           uuid[0].decode(), append_cmdline=b"rdinit=/umi-probe panic=10")
        with args.output.open("xb") as f:
            f.write(boot)
    except (ValueError, OSError) as e:
        p.exit(1, f"{e}\n")
    print(f"RAM probe only; use fastboot boot, never flash: {args.output}")


if __name__ == "__main__":
    main()
