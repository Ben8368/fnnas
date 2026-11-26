"""Package built Umi kernels and select the latest promoted 6.18.y release."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tarfile
import tempfile
from urllib.error import HTTPError
from urllib.request import Request, urlopen


TAG = "kernel_fnnas"
VERSION = r"6\.18\.(?:0|[1-9][0-9]*)"
ASSET = re.compile(rf"(?P<version>{VERSION})-qualcomm-sm8250-xiaomi-umi-csot(?P<rate>60|90)\.tar\.gz")
BOOT_FILES = ("arch/arm64/boot/Image", "boot-csot.dtb", "native-display-cmdline")
FILES = (*BOOT_FILES, "include/config/kernel.release", ".config", "System.map",
         "SHA256SUMS", "refresh", "kernel-source.tsv")


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_kernel(root):
    for name in FILES:
        if not (root / name).is_file():
            raise ValueError(f"Missing kernel file: {name}")
    version, commit = (root / "kernel-source.tsv").read_text().split()
    rate = (root / "refresh").read_text().strip()
    release = f"{version}-csot{rate}-sm8250"
    if (not re.fullmatch(VERSION, version) or not re.fullmatch(r"[0-9a-f]{40}", commit)
            or rate not in ("60", "90")
            or (root / "include/config/kernel.release").read_text().strip() != release):
        raise ValueError("Umi kernel source, refresh rate and kernel.release do not agree")
    expected = {name: sha256(root / name) for name in BOOT_FILES}
    actual = {}
    for line in (root / "SHA256SUMS").read_text().splitlines():
        digest, name = line.split(maxsplit=1)
        if name in actual:
            raise ValueError(f"Duplicate boot checksum for {name}")
        actual[name] = digest
    if actual != expected:
        raise ValueError("Umi boot files failed SHA256SUMS verification")
    return version, rate, release


def pack(kernel, module_root, output):
    version, rate, release = read_kernel(kernel)
    module_path = f"lib/modules/{release}"
    if not (module_root / module_path / "modules.dep").is_file():
        raise ValueError(f"Missing installed module index for {release}")
    name = f"{version}-qualcomm-sm8250-xiaomi-umi-csot{rate}.tar.gz"
    with tempfile.TemporaryDirectory(dir=output) as work:
        bundle = Path(work) / name
        with tarfile.open(bundle, "w:gz", compresslevel=3) as archive:
            for name_in_bundle in FILES:
                archive.add(kernel / name_in_bundle, arcname=name_in_bundle)
            archive.add(module_root / module_path, arcname=module_path)
        # Never overwrite an existing package for this version and profile.
        os.link(bundle, output / name)
    print(output / name)


def release_api(repo, path):
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "fnnas-umi-kernel"}
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(f"https://api.github.com/repos/{repo}/{path}", headers=headers)
    with urlopen(request, timeout=60) as response:
        return json.load(response)


def select_asset(repo, rate, version):
    try:
        release = release_api(repo, f"releases/tags/{TAG}")
    except HTTPError as error:
        if error.code == 404:
            raise ValueError(f"{repo} has no published {TAG} release") from error
        raise
    if release["draft"] or release["prerelease"]:
        raise ValueError(f"{repo}/{TAG} is not a final release")
    release_id = int(release["id"])
    candidates = []
    page = 1
    while True:
        assets = release_api(repo, f"releases/{release_id}/assets?per_page=100&page={page}")
        for asset in assets:
            match = ASSET.fullmatch(asset["name"])
            if not match or match["rate"] != rate or asset["state"] != "uploaded":
                continue
            candidate = match["version"]
            if version == "auto" or candidate == version:
                candidates.append((int(candidate.rsplit(".", 1)[1]), candidate, asset))
        if len(assets) < 100:
            break
        page += 1
    if not candidates:
        raise ValueError(f"{repo}/{TAG} has no published Umi CSOT {rate} Hz kernel for {version}")
    _, version, asset = max(candidates, key=lambda candidate: candidate[0])
    return version, asset


def fetch(repo, version, rate, asset, output):
    if output.exists() or output.is_symlink():
        raise ValueError(f"Output already exists: {output}")
    digest = asset.get("digest") or ""
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise ValueError(f"GitHub did not provide a SHA-256 digest for {asset['name']}")
    url = f"https://github.com/{repo}/releases/download/{TAG}/{asset['name']}"
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as work:
        bundle = Path(work) / asset["name"]
        with urlopen(url, timeout=120) as response, bundle.open("wb") as stream:
            shutil.copyfileobj(response, stream)
        if bundle.stat().st_size != asset["size"] or f"sha256:{sha256(bundle)}" != digest:
            raise ValueError(f"Release asset digest or size mismatch: {asset['name']}")
        unpacked = Path(work) / "kernel"
        module_path = f"lib/modules/{version}-csot{rate}-sm8250"
        with tarfile.open(bundle, "r:gz") as archive:
            members = archive.getmembers()
            seen = set()
            for member in members:
                name = member.name
                allowed = (name in FILES and member.isfile()) or (
                    (name == module_path or name.startswith(module_path + "/"))
                    and (member.isdir() or member.isfile())
                )
                if not allowed or name in seen or ".." in Path(name).parts:
                    raise ValueError(f"Unexpected kernel archive member: {name}")
                seen.add(name)
            archive.extractall(unpacked, members=members, filter="data")
        actual_version, actual_rate, _ = read_kernel(unpacked)
        if (actual_version, actual_rate) != (version, rate) or not (unpacked / module_path / "modules.dep").is_file():
            raise ValueError(f"Archive contents do not match {asset['name']}")
        unpacked.rename(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("query", "fetch"):
        request = commands.add_parser(command)
        request.add_argument("--repo", default="Ben8368/fnnas")
        request.add_argument("--refresh", choices=("60", "90"), default="60")
        request.add_argument("--version", default="auto")
        if command == "fetch":
            request.add_argument("output", type=Path)
    package = commands.add_parser("pack")
    package.add_argument("kernel", type=Path)
    package.add_argument("module_root", type=Path)
    package.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "pack":
            pack(args.kernel, args.module_root, args.output)
            return
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9_.-]+", args.repo):
            raise ValueError("Use OWNER/REPO for the GitHub release repository")
        if args.version != "auto" and not re.fullmatch(VERSION, args.version):
            raise ValueError("Select auto or a concrete 6.18.x release")
        version, asset = select_asset(args.repo, args.refresh, args.version)
        if args.command == "fetch":
            fetch(args.repo, version, args.refresh, asset, args.output)
        print(f"{version}\t{asset['name']}")
    except (OSError, ValueError, KeyError, tarfile.TarError) as error:
        parser.exit(1, f"Umi kernel release: {error}\n")


if __name__ == "__main__":
    main()
