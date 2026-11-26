"""Exercise the refnos CLI with partitioned ext4 and Btrfs donor fixtures."""
from contextlib import closing
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import tarfile
import tempfile
import unittest

import guestfs


REPO = Path(__file__).resolve().parents[3]
MIB = 1024 * 1024


def populate(guest):
    for directory in ("/usr/trim", "/usr/bin", "/var/lib/dpkg", "/lib/modules/6.18.0-fixture",
                      "/usr/lib/systemd/system", "/boot", "/etc"):
        guest.mkdir_p(directory)
    # ELF64 ET_EXEC with EM_AARCH64, recognized by file(1) without being executed.
    elf = struct.pack("<16sHHIQQQIHHHHHH", b"\x7fELF\x02\x01\x01", 2, 183, 1,
                      0, 0, 0, 0, 64, 56, 0, 64, 0, 0)
    guest.write("/usr/bin/dpkg", elf)
    guest.write("/var/lib/dpkg/status",
                b"Package: dpkg\nStatus: install ok installed\nArchitecture: arm64\nVersion: 1.0\n")
    guest.write("/etc/debian_version", b"13.0\n")
    guest.touch("/usr/trim/fixture")
    guest.chown(123, 456, "/usr/trim/fixture")
    guest.touch("/boot/vmlinuz-6.18.0-fixture")
    guest.touch("/usr/lib/systemd/system/fixture.service")


class BaseImageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        scratch = tempfile.TemporaryDirectory()
        cls.addClassCleanup(scratch.cleanup)
        cls.directory = Path(scratch.name)
        cls.ext4 = cls.directory / "ext4.img"
        cls.btrfs = cls.directory / "btrfs.img"
        with closing(guestfs.GuestFS(python_return_dict=True)) as guest:
            for path, size in ((cls.ext4, 64 * MIB), (cls.btrfs, 128 * MIB)):
                with path.open("wb") as stream:
                    stream.truncate(size)
                guest.add_drive_opts(str(path), format="raw")
            guest.launch()
            ext_disk, btrfs_disk = guest.list_devices()
            guest.part_init(ext_disk, "gpt")
            guest.part_add(ext_disk, "p", 2048, 8191)
            guest.part_add(ext_disk, "p", 8192, -34)
            guest.part_set_name(ext_disk, 2, "ROOTFS")
            ext_root = next(part for part in guest.list_partitions() if guest.part_to_partnum(part) == 2)
            guest.mkfs("ext4", ext_root)
            guest.mount(ext_root, "/")
            populate(guest)
            guest.umount_all()
            guest.mkfs("btrfs", btrfs_disk)
            guest.mount(btrfs_disk, "/")
            guest.btrfs_subvolume_create("/@root")
            guest.umount_all()
            guest.mount_options("subvol=@root", btrfs_disk, "/")
            populate(guest)
            guest.umount_all()
            guest.shutdown()

    def run_inspect(self, image, output, *options):
        return subprocess.run(["bash", REPO / "refnos", "inspect", image, "--output", output, *options],
                              check=False, text=True, capture_output=True)

    def test_partitioned_ext4_archive(self):
        archive = self.directory / "ext4.img.gz"
        with self.ext4.open("rb") as source, gzip.open(archive, "wb") as compressed:
            shutil.copyfileobj(source, compressed)
        sha256 = hashlib.sha256(archive.read_bytes()).hexdigest()
        result = self.directory / "ext4-report"
        rejected = self.run_inspect(archive, result, "--sha256", "0" * 64)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn("SHA-256 differs", rejected.stderr)
        self.assertFalse(result.exists())
        audited = self.run_inspect(archive, result, "--sha256", sha256)
        self.assertEqual(audited.returncode, 0, audited.stderr)
        self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(), sha256)
        info = json.loads((result / "image-info.json").read_text())
        layout = json.loads((result / "partitions.json").read_text())
        self.assertEqual((info["partition_table"], info["root_partition"], info["root_filesystem"]),
                         ("gpt", 2, "ext4"))
        self.assertTrue(info["expected_sha256_checked"])
        self.assertEqual(layout["partitions"][1]["name"], "ROOTFS")
        self.assertEqual(info["rootfs"]["usr_trim_entries"], ["fixture"])
        self.assertIn("dpkg\t1.0\tarm64", (result / "packages.txt").read_text())
        self.assertEqual((result / "services.txt").read_text(), "fixture.service\n")
        self.assertEqual((result / "modules.txt").read_text(), "6.18.0-fixture\n")
        self.assertIn("debian_version: 13.0", (result / "rootfs-report.txt").read_text())

        rootfs = self.directory / "ext4-rootfs.tar"
        command = ["bash", REPO / "refnos", "extract", archive, rootfs, "--sha256"]
        rejected = subprocess.run([*command, "0" * 64], capture_output=True, text=True)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertFalse(rootfs.exists())
        exported = subprocess.run([*command, sha256], capture_output=True, text=True)
        self.assertEqual(exported.returncode, 0, exported.stderr)
        self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(), sha256)
        with tarfile.open(rootfs) as contents:
            fixture, = (item for item in contents if item.name.endswith("usr/trim/fixture"))
            self.assertEqual((fixture.uid, fixture.gid), (123, 456))

    def test_btrfs_nondefault_root_subvolume(self):
        with self.btrfs.open("rb") as image:
            sha256 = hashlib.file_digest(image, "sha256").hexdigest()
        result = self.directory / "btrfs-report"
        audited = self.run_inspect(self.btrfs, result, "--root-partition", "0")
        self.assertEqual(audited.returncode, 0, audited.stderr)
        info = json.loads((result / "image-info.json").read_text())
        self.assertEqual((info["partition_table"], info["root_partition"], info["root_filesystem"]),
                         ("none", 0, "btrfs"))
        partition, = json.loads((result / "partitions.json").read_text())["partitions"]
        subvolume, = partition["subvolumes"]
        self.assertEqual(partition["default_subvolume"], 5)
        self.assertEqual((subvolume["id"], subvolume["path"]), (info["root_subvolume"], "@root"))
        with self.btrfs.open("rb") as image:
            self.assertEqual(hashlib.file_digest(image, "sha256").hexdigest(), sha256)
