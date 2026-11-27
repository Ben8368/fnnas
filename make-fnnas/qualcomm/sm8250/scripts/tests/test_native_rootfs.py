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
            for name in ("etc/systemd/system", "etc/initramfs-tools", "etc/apt", "usr/lib/systemd/system",
                         "usr/lib/modules/old",
                         "usr/trim", "usr/src/linux-headers-old", "boot/extlinux", "root", "etc/kernel/postinst.d"):
                (root / name).mkdir(parents=True)
            overlay = scripts.parents[2] / "fnnas-files/different-files/xiaomi-umi/rootfs"
            for name in native.CONSOLE_FILES:
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((overlay / name).read_bytes())
            legacy_rule = root / native.LEGACY_USB_GETTY_RULE
            legacy_rule.parent.mkdir(parents=True, exist_ok=True)
            legacy_rule.write_bytes((overlay / native.LEGACY_USB_GETTY_RULE).read_bytes())
            dnsmasq = root / "usr/sbin/dnsmasq"
            dnsmasq.parent.mkdir(parents=True)
            dnsmasq.touch(mode=0o755)
            donor_getty_want = root / native.DONOR_GETTY_WANT
            donor_getty_want.parent.mkdir(parents=True, exist_ok=True)
            donor_getty_want.symlink_to("/lib/systemd/system/serial-getty@.service")
            wsdd2 = root / native.WSD_DAEMON
            wsdd2.touch(mode=0o755)
            (root / native.WSD_UNIT).write_text("[Service]\nExecStart=/usr/trim/bin/wsdd2 -4\n")
            pstore_link = root / native.PSTORE_LINK
            pstore_link.parent.mkdir()
            pstore_link.symlink_to("/lib/systemd/system/systemd-pstore.service")
            hook = root / "etc/kernel/postinst.d/10-sync-dtb"
            hook.touch(mode=0o755)
            (root / "root").chmod(0o777)
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
            self.assertEqual(hook.stat().st_mode & 0o111, 0)
            self.assertEqual((root / "root").stat().st_mode & 0o777, 0o700)
            self.assertFalse(list((root / "usr/lib/modules").iterdir()))
            self.assertFalse(list((root / "boot").iterdir()))
            self.assertEqual((root / "etc/systemd/system/resize-rootfs.service").readlink(), Path("/dev/null"))
            self.assertEqual((root / "etc/systemd/system/multi-user.target.wants/umi-usb-acm.service").readlink(),
                             Path("/usr/lib/systemd/system/umi-usb-acm.service"))
            self.assertEqual((root / native.USB_GETTY_MASK).readlink(), Path("/dev/null"))
            self.assertFalse(legacy_rule.exists())
            self.assertFalse(donor_getty_want.is_symlink())
            self.assertEqual((root / "etc/systemd/system" / native.DONOR_GETTY).readlink(), Path("/dev/null"))
            self.assertEqual((root / native.WSD_DROPIN).read_text(), native.WSD_CONFIG)
            self.assertIn("ExecStart=/usr/trim/bin/wsdd2 -4", (root / native.WSD_UNIT).read_text())
            self.assertFalse((root / "etc/systemd/system/serial-getty@.service").is_symlink())
            for name, mode in native.CONSOLE_FILES.items():
                self.assertEqual((root / name).stat().st_mode & 0o777, mode)
            self.assertEqual((root / "usr/local/sbin/umi-serial-console").stat().st_mode & 0o777, 0o755)
            self.assertEqual((root / "usr/local/sbin/umi-power").stat().st_mode & 0o777, 0o755)
            self.assertIn("Storage=persistent", (root / "etc/systemd/journald.conf.d/90-umi-boot-log.conf").read_text())
            self.assertEqual(pstore_link.readlink(), Path("/lib/systemd/system/systemd-pstore.service"))
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
