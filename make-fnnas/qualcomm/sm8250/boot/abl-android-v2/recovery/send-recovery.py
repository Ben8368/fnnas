#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Verify a file transfer or pinned Umi GPT metadata (one transaction per boot)."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
import sys
import time

PROTOCOL = b"FNNAS-UMI-RECOVERY/1"
MAX_PAYLOAD = 64 << 20
CHUNK = 16 << 10


def transfer(port, payload, size, boot_sha256, *, deadline, nonce=None):
    if not (0 <= size <= MAX_PAYLOAD) or not re.fullmatch(r"[0-9a-f]{64}", boot_sha256):
        raise ValueError("invalid payload size or base boot SHA-256")
    nonce = secrets.token_hex(16).encode("ascii") if nonce is None else nonce

    def remaining():
        seconds = deadline - time.monotonic()
        if seconds <= 0:
            raise TimeoutError("Recovery transaction deadline elapsed")
        return seconds

    def send(data):
        port.write_timeout = min(5, remaining())
        if port.write(data) != len(data):
            raise OSError("short ACM write")

    def expect(data, stage):
        port.timeout = min(15, remaining())
        # Read in one call with a bounded timeout, not a timeout per byte.
        if port.read(len(data)) != data:
            raise OSError(f"Recovery {stage} mismatch or timeout; reboot before retrying")

    count = str(size).encode("ascii")
    send(b" ".join((PROTOCOL, b"HASH", nonce, count)) + b"\n")
    expect(b" ".join((PROTOCOL, b"READY", nonce, boot_sha256.encode("ascii"))) + b"\n", "READY/boot identity")
    sha = hashlib.sha256()
    left = size
    while left:
        data = payload.read(min(CHUNK, left))
        if not data:
            raise OSError("payload file was truncated")
        sha.update(data)
        send(data)
        left -= len(data)
    if payload.read(1):
        raise OSError("payload file grew during transfer")
    digest = sha.hexdigest()
    expect(b" ".join((PROTOCOL, b"RESULT", nonce, count, digest.encode("ascii"))) + b"\n", "SHA-256 receipt")
    return {"protocol": PROTOCOL.decode("ascii"), "base_boot_sha256": boot_sha256,
            "nonce": nonce.decode("ascii"), "bytes": size, "sha256": digest, "mode": "hash-only"}


def verify_gpt(port, boot_sha256, primary, backup, *, nonce=None):
    if not all(re.fullmatch(r"[0-9a-f]{64}", value) for value in (boot_sha256, primary, backup)):
        raise ValueError("expected pinned lowercase SHA-256 digests of boot and both raw GPT regions")
    nonce = secrets.token_hex(16).encode("ascii") if nonce is None else nonce
    port.write_timeout = 5
    request = b" ".join((PROTOCOL, b"GPT", nonce)) + b"\n"
    if port.write(request) != len(request):
        raise OSError("short ACM write")
    port.timeout = 30
    frame = port.read_until(b"\n", 320)
    fields = frame.rstrip(b"\n").split(b" ")
    if (not frame.endswith(b"\n") or len(fields) != 10 or
            fields[:4] != [PROTOCOL, b"GPT-RESULT", nonce, boot_sha256.encode("ascii")] or
            not re.fullmatch(rb"sd[a-z]+", fields[4]) or fields[5:8] != [b"254778802176", b"4096", b"ram-only"] or
            fields[8:] != [primary.encode("ascii"), backup.encode("ascii")]):
        raise OSError("Recovery UFS geometry, boot identity, or raw GPT hashes do not match the verified baseline")
    return {"protocol": PROTOCOL.decode("ascii"), "base_boot_sha256": boot_sha256,
            "nonce": nonce.decode("ascii"), "device": "/dev/" + fields[4].decode("ascii"),
            "disk_bytes": int(fields[5]), "sector_bytes": int(fields[6]), "mode": "ram-only",
            "primary_gpt_sha256": primary, "backup_gpt_sha256": backup}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True, help="explicit ACM port, e.g. COM9 or /dev/cu.usbmodem…")
    parser.add_argument("--boot-sha256", required=True, help="pinned native base boot digest")
    parser.add_argument("--gpt-pin", nargs=2, metavar=("PRIMARY_SHA256", "BACKUP_SHA256"),
                        help="previously verified raw primary and backup metadata digests; no payload")
    parser.add_argument("payload", type=Path, nargs="?", help="regular file, no larger than 64 MiB")
    args = parser.parse_args()
    if (args.gpt_pin is None) == (args.payload is None):
        parser.error("specify one payload file or --gpt-pin, not both")
    try:
        import serial
    except ImportError:
        parser.exit(1, "Install pyserial==3.5 in the host environment first.\n")
    try:
        if args.gpt_pin is not None:
            with serial.Serial(args.port, 115200, timeout=30, write_timeout=5) as port:
                print(json.dumps(verify_gpt(port, args.boot_sha256, *args.gpt_pin), sort_keys=True))
            return
        # Stat before open to reject devices/FIFOs before a potentially blocking open.
        if not args.payload.is_file():
            raise ValueError("payload must be a regular file")
        with args.payload.open("rb") as payload:
            info = os.fstat(payload.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_PAYLOAD:
                raise ValueError("payload must be a regular file of at most 64 MiB")
            if not re.fullmatch(r"[0-9a-f]{64}", args.boot_sha256):
                raise ValueError("expected a lowercase base boot SHA-256")
            with serial.Serial(args.port, 115200, timeout=15, write_timeout=5) as port:
                report = transfer(port, payload, info.st_size, args.boot_sha256,
                                  deadline=time.monotonic() + 150)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"{exc}\n")
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    sys.exit(main())
