#!/usr/bin/env python3
"""Collect previous-boot Linux console/dmesg records after returning to Android."""
import argparse
from pathlib import Path
import re
import subprocess


RECORD = re.compile(r"(?:console|dmesg)-ramoops-\d+", re.ASCII)
IDENTIFIERS = re.compile(r"(androidboot\.(?:serialno|cpuid)=)[^\s]+", re.IGNORECASE)
CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
MARKER = re.compile(r"UMI_PROBE:|UMI_RAM_ONLY_PID1|Linux version|Kernel panic|Run /umi-probe")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("serial", help="explicit serial from adb devices")
    parser.add_argument("output", type=Path)
    parser.add_argument("--adb", default="adb", help="path to adb executable")
    args = parser.parse_args()
    adb = [args.adb, "-s", args.serial]

    def read(*command):
        return subprocess.run(adb + list(command), check=True, timeout=20, capture_output=True).stdout

    try:
        # Old shells cannot report the remote exit status; never save a partial cat.
        if b"shell_v2" not in read("features").splitlines():
            raise ValueError("adb shell_v2 is required for reliable pstore reads")
        adb.extend(["shell", "-T"])
        listing = read("ls", "-1", "/sys/fs/pstore").decode("ascii", "replace")
        records = sorted(f for f in listing.splitlines() if RECORD.fullmatch(f))
        if not records:
            raise ValueError("no uncompressed ramoops console/dmesg records; not proof of a boot failure")
        chunks = []
        for name in records:
            data = read("cat", f"/sys/fs/pstore/{name}")
            s = CONTROL.sub("?", data.decode("ascii", "replace"))
            s = IDENTIFIERS.sub(r"\1[redacted]", s)
            chunks.append(f"=== {name} ({len(data)} bytes) ===\n{s.rstrip()}\n")
        with args.output.open("x", encoding="utf-8", newline="\n") as report:
            report.write("\n".join(chunks))
    except (OSError, ValueError, subprocess.SubprocessError) as e:
        parser.exit(1, f"Cannot read pstore (use an authorized root adbd if required): {e}\n")
    for chunk in chunks:
        for line in chunk.splitlines():
            if MARKER.search(line):
                print(line.encode("ascii", "replace").decode("ascii"))
    print(f"Saved {len(records)} ramoops record(s) to {args.output}")


if __name__ == "__main__":
    main()
