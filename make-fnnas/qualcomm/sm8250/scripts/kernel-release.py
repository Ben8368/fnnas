"""Package built Umi kernels and select the latest promoted 6.18.y release."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile
from urllib.error import HTTPError
from urllib.request import Request, urlopen


PUBLISH_REPO = "Ben8368/fnnas"
PUBLISH_OPERATOR = "Ben8368"
PUBLISH_BRANCH = "codex/qualcomm-sm8250"
WORKFLOW = ".github/workflows/build-kernel.yml"
SHA = r"[0-9a-f]{40}"
HASH = r"[0-9a-f]{64}"
PROFILE_RATE = {"release": "60", "csot-60": "60", "csot-90": "90"}
VERSION = r"6\.18\.(?:0|[1-9][0-9]*)"
ASSET = re.compile(rf"(?P<version>{VERSION})-qualcomm-sm8250-xiaomi-umi-csot(?P<rate>60|90)\.tar\.gz")
BOOT_FILES = ("arch/arm64/boot/Image", "boot-csot.dtb", "native-display-cmdline")
FILES = (*BOOT_FILES, "include/config/kernel.release", ".config", "System.map",
         "SHA256SUMS", "refresh", "kernel-source.tsv", "armbian-patches.tsv", "display-source.sha", "build.json")


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_kernel(root):
    for name in FILES[:-1]:
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


def pack(kernel, module_root, output, profile, source):
    version, rate, release = read_kernel(kernel)
    module_path = f"lib/modules/{release}"
    if not (module_root / module_path / "modules.dep").is_file():
        raise ValueError(f"Missing installed module index for {release}")
    name = f"{version}-qualcomm-sm8250-xiaomi-umi-csot{rate}.tar.gz"
    with tempfile.TemporaryDirectory(dir=output) as work:
        bundle = Path(work) / name
        identity = Path(work) / "build.json"
        identity.write_text(json.dumps({
            "version": version, "profile": profile, "source_commit": source,
            "linux_commit": (kernel / "kernel-source.tsv").read_text().split()[1],
            "patches_sha256": sha256(kernel / "armbian-patches.tsv"),
        }, sort_keys=True) + "\n")
        if PROFILE_RATE.get(profile) != rate or not re.fullmatch(SHA, source):
            raise ValueError("Build profile or source SHA does not match the package")
        with tarfile.open(bundle, "w:gz", compresslevel=3) as archive:
            for name_in_bundle in FILES[:-1]:
                archive.add(kernel / name_in_bundle, arcname=name_in_bundle)
            archive.add(identity, arcname="build.json")
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


def tag_for(version, rate, source):
    return f"umi-kernel-{version}-csot{rate}-{source}"


def acceptance_record(record, context):
    required = {"source_commit", "linux_commit", "profile", "run_id", "run_attempt", "package_sha256"}
    if any(record[key] != context[key] for key in required):
        raise ValueError("Acceptance does not identify the exact build and package")
    if (record["result"] != "pass" or record["device"] != "xiaomi-umi"
            or record["method"] != "fastboot-boot" or record["scope"] != "kernel"
            or not record["operator"].strip() or not record["tested_at"].strip()
            or not re.fullmatch(HASH, record["evidence_sha256"])):
        raise ValueError("Missing passed no-flash physical Umi kernel acceptance")


def describe_release(repo, release, rate, requested):
    prefix = "umi-kernel-"
    if release["draft"] or release["prerelease"] or not release["tag_name"].startswith(prefix):
        return None
    data = json.loads(release["body"])
    version, source = data["version"], data["source_commit"]
    if (data["schema"] != 1 or data["repository"] != repo or data["branch"] != PUBLISH_BRANCH
            or not re.fullmatch(VERSION, version) or (requested != "auto" and version != requested)
            or not re.fullmatch(SHA, source) or not re.fullmatch(SHA, data["linux_commit"])
            or not re.fullmatch(HASH, data["patches_sha256"]) or PROFILE_RATE.get(data["profile"]) != rate
            or any(type(data[key]) is not int or data[key] < 1 for key in ("run_id", "run_attempt"))
            or release["tag_name"] != tag_for(version, rate, source)):
        return None
    acceptance_record(data["acceptance"], data)
    assets = {asset["name"]: asset for asset in release["assets"] if asset["state"] == "uploaded"}
    package = assets[f"{version}-qualcomm-sm8250-xiaomi-umi-csot{rate}.tar.gz"]
    if (not re.fullmatch(HASH, data["package_sha256"])
            or package["digest"] != f"sha256:{data['package_sha256']}"
            or assets["device-evidence.log"]["digest"] != f"sha256:{data['acceptance']['evidence_sha256']}"):
        return None
    tag = release_api(repo, f"git/ref/tags/{release['tag_name']}")["object"]
    if tag["type"] != "commit" or tag["sha"] != source:
        return None
    return version, package, release["tag_name"], data


def select_asset(repo, rate, version):
    candidates = []
    page = 1
    while True:
        releases = release_api(repo, f"releases?per_page=100&page={page}")
        for release in releases:
            try:
                candidate = describe_release(repo, release, rate, version)
            except (KeyError, TypeError, ValueError):
                continue
            except HTTPError as error:
                if error.code != 404:
                    raise
                continue
            if candidate:
                candidates.append(candidate)
        if len(releases) < 100:
            break
        page += 1
    if not candidates:
        raise ValueError(f"{repo} has no accepted Umi CSOT {rate} Hz kernel for {version}")
    # REST returns newest releases first. For the same version prefer the first eligible promotion.
    return max(candidates, key=lambda item: int(item[0].rsplit(".", 1)[1]))


def fetch(repo, version, rate, asset, tag, provenance, output):
    if output.exists() or output.is_symlink():
        raise ValueError(f"Output already exists: {output}")
    digest = asset.get("digest") or ""
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise ValueError(f"GitHub did not provide a SHA-256 digest for {asset['name']}")
    url = f"https://github.com/{repo}/releases/download/{tag}/{asset['name']}"
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
        build = read_build(unpacked)
        if any(build[key] != provenance[key] for key in build):
            raise ValueError("Published provenance differs from the kernel bundle")
        (unpacked / "promotion.json").write_text(json.dumps({**provenance, "tag": tag}, indent=2) + "\n")
        unpacked.rename(output)


def read_build(root):
    version, rate, _ = read_kernel(root)
    build = json.loads((root / "build.json").read_text())
    if (set(build) != {"source_commit", "linux_commit", "profile", "version", "patches_sha256"}
            or PROFILE_RATE.get(build["profile"]) != rate or build["version"] != version
            or not re.fullmatch(SHA, build["source_commit"])
            or build["linux_commit"] != (root / "kernel-source.tsv").read_text().split()[1]
            or build["patches_sha256"] != sha256(root / "armbian-patches.tsv")):
        raise ValueError("Build identity differs from the kernel bundle")
    return build


def gh(*arguments):
    return subprocess.check_output(["gh", *arguments], text=True).strip()


def promote(args):
    if args.publish and gh("api", "user", "--jq", ".login").casefold() != PUBLISH_OPERATOR.casefold():
        raise ValueError("Publication requires the authorized maintainer's local GitHub credential")
    if args.profile not in PROFILE_RATE or not re.fullmatch(SHA, args.source):
        raise ValueError("Require a full source SHA and a release profile")
    if min(args.run_id, args.run_attempt) < 1:
        raise ValueError("Require positive run ID and attempt")
    repo = PUBLISH_REPO
    run = json.loads(gh("api", f"repos/{repo}/actions/runs/{args.run_id}/attempts/{args.run_attempt}"))
    if (run["head_repository"]["full_name"] != repo or run["head_branch"] != PUBLISH_BRANCH
            or run["head_sha"] != args.source or run["conclusion"] != "success"
            or run["event"] != "push" or run["path"].split("@", 1)[0] != WORKFLOW
            or run["id"] != args.run_id or run["run_attempt"] != args.run_attempt):
        raise ValueError("Not a successful build of the explicitly authorized branch, SHA and attempt")
    tip = json.loads(gh("api", f"repos/{repo}/branches/codex%2Fqualcomm-sm8250"))["commit"]["sha"]
    relation = json.loads(gh("api", f"repos/{repo}/compare/{args.source}...{tip}"))["status"]
    if relation not in {"ahead", "identical"}:
        raise ValueError("Source commit is no longer on the authorized development branch")
    with tempfile.TemporaryDirectory() as work:
        root = Path(work)
        gh("run", "download", str(args.run_id), "--repo", repo, "--dir", work,
           "--name", f"umi-{args.profile}-{args.run_id}-{args.run_attempt}")
        rate = PROFILE_RATE[args.profile]
        bundles = [path for path in root.iterdir() if ASSET.fullmatch(path.name)]
        if len(bundles) != 1 or not bundles[0].is_file():
            raise ValueError("Expected one kernel bundle")
        bundle, = bundles
        # Read only identity files; never extract a CI archive onto the publishing host.
        with tarfile.open(bundle, "r:gz") as archive:
            identity = json.load(archive.extractfile("build.json"))
            patches = archive.extractfile("armbian-patches.tsv").read()
            linux = archive.extractfile("kernel-source.tsv").read().decode().split()
        match = ASSET.fullmatch(bundle.name)
        version = match["version"]
        if (identity != {"source_commit": args.source, "linux_commit": linux[1], "profile": args.profile,
                         "version": version, "patches_sha256": hashlib.sha256(patches).hexdigest()}
                or match["rate"] != rate or linux[0] != version or not re.fullmatch(SHA, linux[1])
                or (root / "project.sha").read_text().strip() != args.source
                or (root / "armbian-patches.tsv").read_bytes() != patches):
            raise ValueError("Artifact provenance does not match the run")
        data = {**identity, "schema": 1, "repository": repo, "branch": PUBLISH_BRANCH,
                "run_id": args.run_id, "run_attempt": args.run_attempt, "package_sha256": sha256(bundle)}
        record = json.loads(args.acceptance.read_text(encoding="utf-8"))
        acceptance_record(record, data)
        evidence = root / "device-evidence.log"
        if not args.evidence.is_file() or not args.evidence.stat().st_size:
            raise ValueError("Provide the actual physical-device evidence log")
        shutil.copyfile(args.evidence, evidence)
        if sha256(evidence) != record["evidence_sha256"]:
            raise ValueError("Physical device evidence digest mismatch")
        text = evidence.read_text(encoding="utf-8", errors="replace")
        expected_lines = (
            f"UMI_PROBE: PID1 kernel={version}-csot{rate}-sm8250",
            f"UMI_PROBE: artifact_sha256={data['package_sha256']}",
            "UMI_PROBE_REPORT_END",
            "Android sys.boot_completed=1",
        )
        if not set(expected_lines) <= set(text.splitlines()):
            raise ValueError("Evidence is missing the exact package ID, PID 1, USB report or Android recovery")
        data["acceptance"] = record
        tag = tag_for(version, rate, args.source)
        print(json.dumps({**data, "tag": tag}, indent=2))
        if not args.publish:
            return
        notes = root / "notes.json"
        notes.write_text(json.dumps(data, indent=2) + "\n")
        # Explicitly create a lightweight ref to the tested SHA. Existing refs are never reused.
        gh("api", "--method", "POST", f"repos/{repo}/git/refs", "-f", f"ref=refs/tags/{tag}",
           "-f", f"sha={args.source}")
        gh("release", "create", tag, str(bundle), str(evidence), "--repo", repo, "--verify-tag",
           "--title", tag, "--notes-file", str(notes), "--draft", "--latest=false")
        draft = json.loads(gh("release", "view", tag, "--repo", repo, "--json", "databaseId"))
        release_id = draft["databaseId"]
        uploaded = json.loads(gh("api", f"repos/{repo}/releases/{release_id}/assets"))
        digests = {asset["name"]: asset.get("digest") for asset in uploaded if asset["state"] == "uploaded"}
        if digests != {path.name: f"sha256:{sha256(path)}" for path in (bundle, evidence)}:
            raise ValueError(f"Asset digest mismatch; {tag} remains a draft")
        ref = json.loads(gh("api", f"repos/{repo}/git/ref/tags/{tag}"))["object"]
        if ref["type"] != "commit" or ref["sha"] != args.source:
            raise ValueError(f"Tag moved; {tag} remains a draft")
        print(gh("release", "edit", tag, "--repo", repo, "--draft=false", "--latest=false"))


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
    package.add_argument("--profile", required=True, choices=PROFILE_RATE)
    package.add_argument("--source", required=True)
    promotion = commands.add_parser("promote", help="verify a physical acceptance and optionally publish")
    promotion.add_argument("--source", required=True)
    promotion.add_argument("--profile", required=True, choices=PROFILE_RATE)
    promotion.add_argument("--run-id", required=True, type=int)
    promotion.add_argument("--run-attempt", required=True, type=int)
    promotion.add_argument("--acceptance", required=True, type=Path)
    promotion.add_argument("--evidence", required=True, type=Path)
    promotion.add_argument("--publish", action="store_true", help="create tag and release (default: verify only)")
    args = parser.parse_args()
    try:
        if args.command == "promote":
            promote(args)
            return
        if args.command == "pack":
            pack(args.kernel, args.module_root, args.output, args.profile, args.source)
            return
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9_.-]+", args.repo):
            raise ValueError("Use OWNER/REPO for the GitHub release repository")
        if args.version != "auto" and not re.fullmatch(VERSION, args.version):
            raise ValueError("Select auto or a concrete 6.18.x release")
        version, asset, tag, provenance = select_asset(args.repo, args.refresh, args.version)
        if args.command == "fetch":
            fetch(args.repo, version, args.refresh, asset, tag, provenance, args.output)
        print(f"{version}\t{asset['name']}")
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError, tarfile.TarError) as error:
        parser.exit(1, f"Umi kernel release: {error}\n")


if __name__ == "__main__":
    main()
