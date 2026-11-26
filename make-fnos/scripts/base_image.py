"""Download a pinned fnOS archive or inventory a read-only disk image."""
import argparse
from contextlib import closing, contextmanager
import gzip
from hashlib import file_digest
import json
import lzma
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import tomllib
from urllib.parse import urlsplit


PROJECT = Path(__file__).resolve().parents[1]
SOURCE_LOCK = PROJECT / "sources/fnos-arm64.lock"
DEFAULT_REPORT = PROJECT.parent / "out/base-image-report"
# The guest disk is opened read-only; keep Btrfs mounts read-only as well.
MOUNT_OPTIONS = {"ext4": "ro,noload", "btrfs": "ro"}
SERVICE_DIRS = ("/etc/systemd/system", "/usr/lib/systemd/system", "/lib/systemd/system")


def digest(path, algorithm):
    with path.open("rb") as stream:
        return file_digest(stream, algorithm).hexdigest()


def sha256_value(value):
    if not re.fullmatch(r"[0-9a-fA-F]{64}", value):
        raise argparse.ArgumentTypeError("expected a 64-digit SHA-256")
    return value.lower()


def download(args):
    with args.lock.open("rb") as stream:
        source = tomllib.load(stream)["source"]
    if not source.get("sha256"):
        raise ValueError("the source lock needs a verified SHA-256 before downloading")
    expected = sha256_value(source["sha256"])
    if source.get("requires_signed_url") and not args.url:
        raise ValueError("pass the temporary link from the official download page using --url")
    url = args.url or source["image_url"]
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username is not None:
        raise ValueError("the download requires an HTTPS URL without user credentials")
    output = args.output.absolute()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() or output.is_symlink():
        raise FileExistsError(f"output already exists: {output}")
    with tempfile.TemporaryDirectory(dir=output.parent, prefix=".fnos-download-") as scratch:
        archive = Path(scratch) / "archive"
        process = subprocess.run(
            ["curl", "--fail", "--location", "--proto", "=https", "--proto-redir", "=https",
             "--retry", "3", "--output", str(archive), "--", url],
            check=False,
        )
        if process.returncode != 0:
            raise RuntimeError(f"archive download failed (curl exit {process.returncode})")
        if digest(archive, "sha256") != expected:
            raise ValueError("downloaded archive SHA-256 differs from the source lock")
        if source.get("official_md5") and digest(archive, "md5") != source["official_md5"].lower():
            raise ValueError("downloaded archive MD5 differs from the official value in the lock")
        os.link(archive, output)
    print(output)


@contextmanager
def raw_image(image):
    with image.open("rb") as stream:
        magic = stream.read(6)
    decompressors = {b"\x1f\x8b": gzip.open, b"\xfd7zXZ\x00": lzma.open}
    for prefix, open_archive in decompressors.items():
        if magic.startswith(prefix):
            with tempfile.TemporaryDirectory(prefix="fnos-audit-") as scratch:
                raw = Path(scratch) / "disk.img"
                with open_archive(image, "rb") as source, raw.open("wb") as target:
                    shutil.copyfileobj(source, target, length=1024 * 1024)
                yield raw
            return
    yield image


def partition_layout(guest, disk):
    devices = guest.list_partitions()
    partitions = []
    table = "none"
    if devices:
        table = guest.part_get_parttype(disk)
        by_number = {guest.part_to_partnum(device): device for device in devices}
        for part in guest.part_list(disk):
            number = part["part_num"]
            if number in by_number:
                partitions.append({
                    "number": number,
                    "device": by_number[number],
                    "start_bytes": part["part_start"],
                    "size_bytes": part["part_size"],
                    "name": guest.part_get_name(disk, number) if table == "gpt" else None,
                })
    else:
        partitions.append({
            "number": 0, "device": disk, "start_bytes": 0,
            "size_bytes": guest.blockdev_getsize64(disk), "name": None,
        })
    for part in partitions:
        signature = guest.blkid(part["device"])
        part.update(filesystem=signature.get("TYPE"), label=signature.get("LABEL"),
                    uuid=signature.get("UUID"))
    return {"partition_table": table, "partitions": partitions}


@contextmanager
def mounted(guest, part, subvolume=None):
    options = MOUNT_OPTIONS[part["filesystem"]]
    if subvolume is not None:
        options += f",subvolid={subvolume}"
    guest.mount_options(options, part["device"], "/")
    try:
        yield
    finally:
        guest.umount_all()


def has_fnos(guest):
    return (guest.is_dir("/usr/trim", followsymlinks=True)
            and guest.is_file("/var/lib/dpkg/status", followsymlinks=True))


def root_candidates(guest, part, subvolume):
    with mounted(guest, part, subvolume):
        if has_fnos(guest):
            actual_id = guest.btrfs_subvolume_get_default("/") if (
                part["filesystem"] == "btrfs" and subvolume is None
            ) else subvolume
            return [(part, actual_id)]
    if part["filesystem"] != "btrfs" or subvolume is not None:
        return []
    with mounted(guest, part, 5):
        subvolumes = [5] + [item["btrfssubvolume_id"] for item in guest.btrfs_subvolume_list("/")]
    matches = []
    for candidate in sorted(set(subvolumes)):
        with mounted(guest, part, candidate):
            if has_fnos(guest):
                matches.append((part, candidate))
    return matches


def check_arm64(guest):
    architecture = guest.file_architecture("/usr/bin/dpkg")
    if architecture not in {"aarch64", "arm64"}:
        raise ValueError(f"expected ARM64 dpkg ELF, found {architecture}")


def inventory(guest):
    check_arm64(guest)
    status = guest.read_file("/var/lib/dpkg/status").decode("utf-8", errors="replace")
    packages = []
    for stanza in status.split("\n\n"):
        fields = dict(line.split(": ", 1) for line in stanza.splitlines()
                      if line and not line[0].isspace() and ": " in line)
        if fields.get("Status", "").split()[-1:] == ["installed"]:
            packages.append("\t".join(fields[key] for key in ("Package", "Version", "Architecture")))
    if not packages:
        raise ValueError("the root filesystem has no installed dpkg packages")
    services = set()
    for directory in SERVICE_DIRS:
        if guest.is_dir(directory, followsymlinks=True):
            services.update(name for name in guest.ls(directory) if name.endswith(".service"))
    modules = []
    if guest.is_dir("/lib/modules", followsymlinks=True):
        modules = [name for name in guest.ls("/lib/modules")
                   if guest.is_dir(f"/lib/modules/{name}", followsymlinks=True)]
    boot = []
    if guest.is_dir("/boot", followsymlinks=True):
        boot = [name for name in guest.ls("/boot") if name.startswith(("vmlinuz", "Image", "initrd"))]
    debian_path = "/etc/debian_version"
    debian = guest.cat(debian_path).strip() if guest.is_file(debian_path, followsymlinks=True) else None
    stats = guest.statvfs("/")
    rootfs = {
        "architecture": "arm64",
        "debian_version": debian,
        "kernel_module_versions": sorted(modules),
        "rootfs_boot_files": sorted(boot),
        "filesystem_bytes": stats["blocks"] * stats["frsize"],
        "used_bytes": (stats["blocks"] - stats["bfree"]) * stats["frsize"],
        "usr_trim_present": True,
        "usr_trim_entries": sorted(guest.ls("/usr/trim")),
        "installed_package_count": len(packages),
        "service_count": len(services),
    }
    return rootfs, sorted(packages), sorted(services), sorted(modules)


def input_digest(image, expected):
    sha256 = digest(image, "sha256")
    if expected == "locked":
        with SOURCE_LOCK.open("rb") as stream:
            expected = tomllib.load(stream)["source"].get("sha256")
        if not expected:
            raise ValueError("the source lock needs a verified SHA-256")
        expected = sha256_value(expected)
    if expected and sha256 != expected:
        raise ValueError("input SHA-256 differs from the expected value")
    return sha256


def image_path(path):
    image = path.resolve(strict=True)
    if not image.is_file() or image.stat().st_size == 0:
        raise ValueError("provide a nonempty regular disk image file")
    return image


@contextmanager
def open_disk(source):
    try:
        import guestfs
    except ImportError as exc:
        raise ValueError("install python3-guestfs on Linux and use its system Python") from exc

    with raw_image(source) as raw, closing(guestfs.GuestFS(python_return_dict=True)) as guest:
        guest.add_drive_opts(str(raw), readonly=True, format="raw")
        guest.launch()
        yield guest, raw


def select_root(guest, layout, args):
    candidates = []
    for part in layout["partitions"]:
        fstype = part["filesystem"]
        if fstype not in MOUNT_OPTIONS or args.root_partition not in (None, part["number"]):
            continue
        if args.root_subvolume is None or fstype == "btrfs":
            candidates.extend(root_candidates(guest, part, args.root_subvolume))
    if not candidates:
        types = ", ".join(f'{p["number"]}={p["filesystem"] or "unknown"}' for p in layout["partitions"])
        raise ValueError(f"no ext4/Btrfs fnOS RootFS with /usr/trim and dpkg status ({types})")
    if len(candidates) > 1:
        labels = ", ".join(f'{p["number"]}/{sub}' for p, sub in candidates)
        raise ValueError(f"multiple fnOS RootFS candidates (partition/subvolume: {labels}); select explicitly")
    return candidates[0]


def extract(args):
    source = image_path(args.image)
    output = args.archive.absolute()
    if output.exists() or output.is_symlink():
        raise FileExistsError(f"archive already exists: {output}")
    input_digest(source, args.sha256)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent, prefix=".fnos-rootfs-") as scratch:
        archive = Path(scratch) / "rootfs.tar"
        with open_disk(source) as (guest, _):
            disk, = guest.list_devices()
            part, subvolume = select_root(guest, partition_layout(guest, disk), args)
            with mounted(guest, part, subvolume):
                check_arm64(guest)
                guest.tar_out("/", str(archive), numericowner=True, xattrs=True, acls=True, selinux=True)
        os.link(archive, output)
    print(output)


def inspect(args):
    source = image_path(args.image)
    output = args.output.absolute()
    if output.exists() or output.is_symlink():
        raise FileExistsError(f"report directory already exists: {output}")
    sha256 = input_digest(source, args.sha256)
    with open_disk(source) as (guest, raw):
        disk, = guest.list_devices()
        layout = partition_layout(guest, disk)
        part, subvolume = select_root(guest, layout, args)
        with mounted(guest, part, subvolume):
            rootfs, packages, services, modules = inventory(guest)
        if part["filesystem"] == "btrfs":
            with mounted(guest, part, 5):
                part["default_subvolume"] = guest.btrfs_subvolume_get_default("/")
                part["subvolumes"] = [
                    {"id": item["btrfssubvolume_id"], "path": item["btrfssubvolume_path"],
                     "parent_id": item["btrfssubvolume_top_level_id"]}
                    for item in guest.btrfs_subvolume_list("/")
                ]
        raw_size = raw.stat().st_size
    board = json.loads((PROJECT / "boards/xiaomi-umi.yml").read_text(encoding="utf-8"))
    info = {
        "image": source.name,
        "sha256": sha256,
        "expected_sha256_checked": args.sha256 is not None,
        "source_bytes": source.stat().st_size,
        "raw_image_bytes": raw_size,
        "partition_table": layout["partition_table"],
        "root_partition": part["number"],
        "root_filesystem": part["filesystem"],
        "root_subvolume": subvolume,
        "target": board,
        "rootfs": rootfs,
    }
    reports = {
        "image-info.json": json.dumps(info, indent=2) + "\n",
        "partitions.json": json.dumps(layout, indent=2) + "\n",
        "packages.txt": "\n".join(["Package\tVersion\tArchitecture", *packages]) + "\n",
        "services.txt": "".join(f"{line}\n" for line in services),
        "modules.txt": "".join(f"{line}\n" for line in modules),
        "rootfs-report.txt": "".join(f"{key}: {value}\n" for key, value in (
            ("root_partition", part["number"]), ("root_filesystem", part["filesystem"]),
            ("root_subvolume", subvolume), *rootfs.items()
        )),
    }
    output.mkdir(parents=True)
    try:
        for filename, contents in reports.items():
            (output / filename).write_text(contents, encoding="utf-8")
    except OSError:
        shutil.rmtree(output)
        raise
    print(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    download_parser = commands.add_parser("download", help="fetch a SHA-256-pinned archive")
    download_parser.add_argument("output", type=Path, help="new archive path")
    download_parser.add_argument("--lock", default=SOURCE_LOCK, type=Path)
    download_parser.add_argument("--url", help="temporary HTTPS link from the official download page")
    download_parser.set_defaults(run=download)
    inspect_parser = commands.add_parser("inspect", help="audit a raw image or its gzip/xz archive")
    inspect_parser.add_argument("image", type=Path)
    inspect_parser.add_argument("--output", default=DEFAULT_REPORT, type=Path, help="new report directory")
    inspect_parser.set_defaults(run=inspect)
    extract_parser = commands.add_parser("extract", help="export the selected RootFS to a new tar archive")
    extract_parser.add_argument("image", type=Path)
    extract_parser.add_argument("archive", type=Path)
    extract_parser.set_defaults(run=extract)
    for command in (inspect_parser, extract_parser):
        command.add_argument("--sha256", type=lambda value: value if value == "locked" else sha256_value(value),
                             required=command is extract_parser,
                             help="expected digest of the input file, or locked")
        command.add_argument("--root-partition", type=int, help="partition number (0 for unpartitioned)")
        command.add_argument("--root-subvolume", type=int, help="Btrfs subvolume ID")
    args = parser.parse_args()
    try:
        args.run(args)
    except (OSError, EOFError, lzma.LZMAError, KeyError, ValueError, RuntimeError,
            argparse.ArgumentTypeError) as exc:
        parser.exit(1, f"fnOS {args.command}: {exc}\n")


if __name__ == "__main__":
    main()
