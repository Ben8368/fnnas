"""Offline Umi staging policy tests (not a physical boot test)."""
import importlib.util
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest

scripts = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(scripts))
spec = importlib.util.spec_from_file_location("native_rootfs", scripts / "native-rootfs.py")
native = importlib.util.module_from_spec(spec)
spec.loader.exec_module(native)


class NativeRootfsTests(unittest.TestCase):
    def test_prepare_preserves_vendor_userspace_and_drops_donor_mounts(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            root = work / "staging"
            for name in ("etc/systemd/system", "etc/initramfs-tools", "etc/apt", "usr/lib/modules/old",
                         "usr/trim", "usr/src/linux-headers-old", "boot/extlinux"):
                (root / name).mkdir(parents=True)
            (root / "lib").symlink_to("usr/lib", target_is_directory=True)
            (root / "etc/fstab").write_text("/dev/mmcblk0p2 / btrfs defaults 0 1\n"
                                          "/dev/mmcblk0p1 /boot ext4 defaults 0 2\n"
                                          "tmpfs /tmp tmpfs defaults,nosuid 0 0\n")
            (root / "etc/initramfs-tools/update-initramfs.conf").write_text("update_initramfs=yes\n")
            (work / "partitions.json").write_text(json.dumps({"partitions": [
                {"number": 2, "filesystem": "btrfs", "default_subvolume": 5, "subvolumes": []}]}))
            (work / "image-info.json").write_text(json.dumps({"root_partition": 2, "root_subvolume": 5,
                "expected_sha256_checked": True, "rootfs": {"kernel_module_versions": ["old"]}}))
            (work / "packages.txt").write_text("linux-image-old\t1\tarm64\ntrim\t1\tall\n")
            firmware = work / "firmware.tar"
            with tarfile.open(firmware, "w") as archive:
                for path in sorted(native.REQUIRED_FIRMWARE):
                    member = tarfile.TarInfo(path)
                    member.size = 3
                    archive.addfile(member, io.BytesIO(b"abc"))
            uuid = "00000000-0000-4000-8000-000000000000"
            native.prepare(root, work, firmware, native.digest(firmware, "sha256"), uuid)
            self.assertEqual((root / "etc/fstab").read_text(), native.FSTAB.format(uuid=uuid))
            self.assertTrue((root / "usr/trim").is_dir())
            self.assertFalse(list((root / "usr/lib/modules").iterdir()))
            self.assertFalse(list((root / "boot").iterdir()))
            self.assertEqual((root / "etc/systemd/system/resize-rootfs.service").readlink(), Path("/dev/null"))
            self.assertEqual((root / "etc/initramfs-tools/update-initramfs.conf").read_text(), "update_initramfs=no\n")
            self.assertTrue((root / "usr/lib/firmware/qcom/sm8250/a650_zap.mbn").is_file())

    def test_untrusted_firmware_member_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            firmware = root / "bad.tar"
            with tarfile.open(firmware, "w") as archive:
                member = tarfile.TarInfo("qcom/../../outside")
                member.size = 3
                archive.addfile(member, io.BytesIO(b"bad"))
            with self.assertRaisesRegex(ValueError, "Unexpected firmware path"):
                native.install_firmware(root, firmware, native.digest(firmware, "sha256"))
