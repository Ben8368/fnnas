#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Verify one file transfer to Umi RAM Recovery (one transaction per boot)."""
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True, help="explicit ACM port, e.g. COM9 or /dev/cu.usbmodem…")
    parser.add_argument("--boot-sha256", required=True, help="pinned native base boot digest")
    parser.add_argument("payload", type=Path, help="regular file, no larger than 64 MiB")
    args = parser.parse_args()
    try:
        import serial
    except ImportError:
        parser.exit(1, "Install pyserial==3.5 in the host environment first.\n")
    try:
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
