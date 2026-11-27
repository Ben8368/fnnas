# SPDX-License-Identifier: GPL-2.0-only
"""Host regressions for pre-enrollment USB diagnostics (no USB devices needed)."""
import importlib.util
from pathlib import Path
import subprocess
from types import SimpleNamespace
import unittest

scripts = Path(__file__).resolve().parents[1]
overlay = scripts.parents[2] / "fnnas-files/different-files/xiaomi-umi/rootfs"
spec = importlib.util.spec_from_file_location("capture_usb_console", scripts / "capture-usb-console.py")
capture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capture)


class NativeUsbTests(unittest.TestCase):
    def test_new_console_never_accepts_input(self):
        for pid in (0x0103, 0x0104):
            with self.subTest(pid=pid):
                port = SimpleNamespace(vid=0x1D6B, pid=pid, serial_number="UMI-LOG", device="COM9")
                self.assertEqual(capture.classify_port(port), ("COM9", False))
        port.serial_number = "UMI-ACM"
        self.assertEqual(capture.classify_port(port), ("COM9", True))
        port.serial_number = None
        self.assertIsNone(capture.classify_port(port))

    def test_bootlog_snapshot_only_emits_allowlisted_fields(self):
        result = subprocess.run(["bash", "-c", r'''
            source "$1"
            uname() { echo 6.18.65-csot90-sm8250; }
            findmnt() { echo btrfs; }
            ip() { echo "12: umiusb0 inet 172.16.42.1/24 scope global umiusb0"; }
            systemctl() { echo "private-state"; }
            journalctl() { printf "usb test-token-1\nbtrfs test-token-2\nDSI test-token-3\n"; }
            timeout() { shift; "$@"; }
            boot_fields=$(safe_boot_fields <<< "androidboot.serialno=private-id androidboot.dtbo_idx=11 androidboot.oled_panel_id=0B")
            dtbo=
            snapshot
            safe_boot_fields <<< "androidboot.dtbo_idx=1234 androidboot.oled_panel_id=private-id"
        ''', "bootlog-test", str(overlay / "usr/local/sbin/umi-usb-bootlog")],
            check=True, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.stdout.splitlines(), [
            "UMI_BOOTLOG/1 BEGIN", "kernel=6.18.65-csot90-sm8250", "rootfs=btrfs",
            "dtbo_index=11", "panel_id=0B", "dtbo_sha256=unavailable", "setup_ipv4=172.16.42.1/24",
            "umi-usb-acm.service=unavailable", "umi-usb-network.service=unavailable",
            "trim_init.service=unavailable", "trim_nginx.service=unavailable", "usersrv.service=unavailable",
            "recent_kernel_warnings=3 usb=1 storage=1 display=1", "UMI_BOOTLOG/1 END",
            "dtbo_index=unavailable", "panel_id=unavailable",
        ])
