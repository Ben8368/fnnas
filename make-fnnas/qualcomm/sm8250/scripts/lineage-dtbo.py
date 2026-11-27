#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Resolve and verify the latest official LineageOS Umi DTBO (no device I/O)."""
import argparse
from datetime import date
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

API = "https://download.lineageos.org/api/v2/devices/umi/builds"
MIRROR = "https://mirrorbits.lineageos.org"
DTBO_SIZE = 32 * 1024 * 1024  # Dedicated Umi DTBO partition.


def latest(builds):
    if (not isinstance(builds, list) or not builds or
            any(not isinstance(b, dict) or type(b.get("datetime")) is not int for b in builds)):
        raise ValueError("invalid official Umi build listing")
    epoch = max(b["datetime"] for b in builds)
    candidates = [b for b in builds if b["datetime"] == epoch]
    if len(candidates) != 1:
        raise ValueError("ambiguous newest official Umi build")
    build, = candidates
    build_date = date.fromisoformat(build["date"])
    lookup = f"/full/umi/{build_date:%Y%m%d}/dtbo.img"
    images = [f for f in build["files"] if f.get("filename") == "dtbo.img"]
    if len(images) != 1:
        raise ValueError("the newest official Umi build must provide exactly one dtbo.img")
    image, = images
    sha = image.get("sha256", "")
    if (image.get("filepath") != lookup or image.get("url") != MIRROR + lookup or
            image.get("size") != DTBO_SIZE or not re.fullmatch(r"[0-9a-f]{64}", sha)):
        raise ValueError("unexpected official Umi DTBO metadata")
    return {"source": "LineageOS", "device": "umi", "api": API, "date": build_date.isoformat(),
            "version": build["version"], "url": image["url"], "size": DTBO_SIZE, "sha256": sha}


def curl(url, output, limit):
    subprocess.run(["curl", "--fail", "--silent", "--show-error", "--location", "--max-redirs", "5",
                    "--proto", "=https", "--proto-redir", "=https", "--retry", "2", "--max-time", "120",
                    "--max-filesize", str(limit), "--output", str(output), url], check=True)


def fetch(out, cache=None):
    with tempfile.TemporaryDirectory(prefix="umi-lineage-", dir=out) as tmp:
        work = Path(tmp)
        listing = work / "builds.json"
        curl(API, listing, 1024 * 1024)
        record = latest(json.loads(listing.read_bytes()))
        if cache is not None and cache.is_file() and cache.stat().st_size == DTBO_SIZE:
            with cache.open("rb") as src:
                if hashlib.file_digest(src, "sha256").hexdigest() == record["sha256"]:
                    shutil.copyfile(cache, work / "dtbo.img")
        image = work / "dtbo.img"
        if not image.exists():
            curl(record["url"], image, record["size"])
        with image.open("rb") as src:
            if image.stat().st_size != record["size"] or hashlib.file_digest(src, "sha256").hexdigest() != record["sha256"]:
                raise ValueError("size or SHA-256 mismatch for official Umi DTBO")
        meta = work / "lineage-dtbo.json"
        meta.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        for path in (image, meta):
            path.rename(out / path.name)
        return record


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("output", type=Path, help="existing private staging directory")
    p.add_argument("--cache", type=Path, help="optional cached image; used only if it matches the latest official bytes")
    args = p.parse_args()
    try:
        if any(path.exists() or path.is_symlink() for path in (args.output / "dtbo.img", args.output / "lineage-dtbo.json")):
            raise ValueError("output already exists")
        record = fetch(args.output, args.cache)
    except (ValueError, KeyError, TypeError, OSError, AttributeError, subprocess.CalledProcessError) as e:
        p.exit(1, f"Official Umi DTBO resolution failed: {e}\n")
    print(f"LineageOS {record['version']} {record['date']} Umi DTBO: SHA-256 {record['sha256']}")


if __name__ == "__main__":
    main()
