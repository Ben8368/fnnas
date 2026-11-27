"""Fixture-level regression tests; no fastboot, device access, or third-party packages."""
import gzip
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import shutil
import struct
import sys
import unittest
from unittest import mock
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import subprocess
import tempfile


TOOLS = Path(__file__).resolve().parents[1] / "tools"


def load(name):
    spec = spec_from_file_location(name.replace("-", "_"), TOOLS / f"{name}.py")
    mod = module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


check = load("check-installed-dtbo")
pack = load("pack-abl-v2")
probe = load("make-ram-probe")
UUID = "3f6d6892-a13f-4967-8126-4ad0a3740eef"


def fdt_header(size=40):
    return struct.pack(">II", 0xD00DFEED, size) + bytes(32)


def boot_header():
    h = bytearray(4096)
    h[:8] = b"ANDROID!"
    struct.pack_into("<10I", h, 8, 0, 0x8000, 0, 0x1000000, 0, 0, 0, 4096, 2, 0)
    struct.pack_into("<IQIIQ", h, 1632, 0, 0, 1660, 0, 0x1F00000)
    h[64:64+len(UUID)+10] = ("root=UUID=" + UUID).encode()
    return h


class ProbeLogTests(unittest.TestCase):
    def test_transfer_status_and_protocol(self):
        reader = load("read-ram-probe-log")
        for features, cat_ok in [(b"cmd\n", False), (b"cmd\nshell_v2\n", False),
                                 (b"cmd\nshell_v2\n", True)]:
            with self.subTest(features=features, cat_ok=cat_ok), tempfile.TemporaryDirectory() as tmp:
                dest = Path(tmp) / "report"

                def adb(argv, **opts):
                    self.assertEqual(argv[:3], ["adb", "-s", "device"])
                    self.assertTrue(opts["check"])
                    if argv[3:] == ["features"]:
                        data = features
                    else:
                        self.assertIn(b"shell_v2", features)
                        self.assertEqual(argv[3:5], ["shell", "-T"])
                        if argv[5] == "ls":
                            data = b"console-ramoops-0\n"
                        elif not cat_ok:
                            raise subprocess.CalledProcessError(1, argv, output=b"partial")
                        else:
                            data = b"Linux version: fixture\n"
                    return subprocess.CompletedProcess(argv, 0, stdout=data)

                with mock.patch.object(subprocess, "run", side_effect=adb), \
                        mock.patch("sys.argv", ["read", "device", str(dest)]), \
                        redirect_stderr(StringIO()), redirect_stdout(StringIO()):
                    if cat_ok:
                        reader.main()
                        self.assertIn("Linux version: fixture", dest.read_text())
                    else:
                        with self.assertRaises(SystemExit):
                            reader.main()
                        self.assertFalse(dest.exists())


class DtboTableTests(unittest.TestCase):
    def fixture(self, payload, *, start=64):
        return (struct.pack(">8I", check.DT_TABLE_MAGIC, 64 + len(payload), 32, 32, 1, 32, 4096, 0)
                + struct.pack(">8I", len(payload), start, 0, 0, 0, 0, 0, 0) + payload)

    def test_read_table_with_partition_padding(self):
        blob = fdt_header()
        self.assertEqual(check.extract_entry(self.fixture(blob) + bytes(4096), 0), blob)

    def test_reject_invalid_indices_lengths_and_offsets(self):
        blob = fdt_header()
        good = self.fixture(blob)
        for data, index in [(good, -1), (good, 1), (good[:-1], 0),
                            (self.fixture(blob, start=32), 0), (self.fixture(fdt_header(99)), 0)]:
            with self.subTest(index=index, data_len=len(data)), self.assertRaises(ValueError):
                check.extract_entry(data, index)

    @unittest.skipUnless(shutil.which("dtc"), "requires device-tree-compiler")
    def test_all_entries_rejects_an_unsafe_later_overlay(self):
        with tempfile.TemporaryDirectory() as tmp:
            base, overlay, table = (Path(tmp) / name for name in ("base.dtb", "overlay.dtbo", "table.img"))
            dts = '/dts-v1/; / { abl_ovf { status = "disabled"; sink: sink {}; }; live: live {}; };'
            subprocess.run(["dtc", "-q", "-@", "-o", base], input=dts, text=True, check=True)
            entries = []
            for target in ("sink", "live"):
                dts = f"/dts-v1/; /plugin/; &{target} {{ marker = <1>; }};"
                subprocess.run(["dtc", "-q", "-@", "-o", overlay], input=dts, text=True, check=True)
                entries.append(overlay.read_bytes())
            offset = 96
            header = struct.pack(">8I", check.DT_TABLE_MAGIC, offset + sum(map(len, entries)), 32, 32, 2, 32, 4096, 0)
            for entry in entries:
                header += struct.pack(">8I", len(entry), offset, 0, 0, 0, 0, 0, 0)
                offset += len(entry)
            table.write_bytes(header + b"".join(entries))
            cmd = [sys.executable, check.__file__, table]
            subprocess.run(cmd + ["0", base, "--protect-live"], check=True, capture_output=True)
            result = subprocess.run(cmd + ["all", base, "--protect-live"], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("index 1", result.stderr)
            self.assertIn("overlay modified the live hardware tree", result.stderr)

    @unittest.skipUnless(shutil.which("dtc"), "requires device-tree-compiler")
    def test_live_protection_checks_overlay_targets_and_quarantine_status(self):
        base_dts = """/dts-v1/; / {
            display: display { status = "okay"; };
            quarantine: abl_ovf { status = "disabled"; sink: sink {}; };
        };"""
        scenarios = (
            ("&sink { vendor = <1>; };", None),
            ('&display { status = "disabled"; };', "overlay modified the live hardware tree"),
            ('&quarantine { status = "okay"; };', "ABL quarantine must remain disabled"),
        )
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "base.dtb"
            overlay = Path(tmp) / "overlay.dtbo"
            table = Path(tmp) / "table.img"
            command = ["dtc", "-q", "-@", "-o"]
            subprocess.run(command + [base], input=base_dts, text=True, check=True)
            for fragment, error in scenarios:
                with self.subTest(fragment=fragment):
                    subprocess.run(command + [overlay], input="/dts-v1/; /plugin/; " + fragment,
                                   text=True, check=True)
                    table.write_bytes(self.fixture(overlay.read_bytes()))
                    result = subprocess.run(
                        [sys.executable, check.__file__, table, "0", base, "--protect-live"],
                        capture_output=True, text=True,
                    )
                    if error is None:
                        self.assertEqual(result.returncode, 0, result.stderr)
                    else:
                        self.assertNotEqual(result.returncode, 0)
                        self.assertIn(error, result.stderr)


class BootLayoutTests(unittest.TestCase):
    def setUp(self):
        self.header = boot_header()
        self.kernel = gzip.compress(b"kernel")
        self.ramdisk = gzip.compress(b"ramdisk")
        self.dtb = fdt_header()

    def test_probe_addition_preserves_release_segments(self):
        cpio = probe.newc_entry("umi-probe", 1, 0o100755, b"probe\n")
        self.assertEqual(len(cpio) % 4, 0)
        self.assertTrue(cpio.startswith(b"070701"))
        rd = self.ramdisk + gzip.compress(cpio, mtime=0)
        img = pack.repack(self.header, self.kernel, rd, self.dtb, UUID,
                          append_cmdline=b"rdinit=/umi-probe panic=10")
        h, k, r, d = pack.split_boot(img)
        self.assertIn(b"rdinit=/umi-probe", h[64:576])
        self.assertEqual((k, r, d), (self.kernel, rd, self.dtb))
        self.assertEqual(gzip.decompress(r), b"ramdisk" + cpio)
        with self.assertRaises(ValueError):
            pack.split_boot(img[:-4096])

    def test_probe_packages_gpu_and_display_helpers(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            release = path / "release.img"
            release.write_bytes(pack.repack(self.header, self.kernel, self.ramdisk, self.dtb, UUID))
            display = path / "display"
            gpu = path / "gpu"
            arm64 = b"\x7fELF\x02\x01" + bytes(12) + b"\xb7\x00"
            display.write_bytes(arm64 + b"display-tool")
            gpu.write_bytes(arm64 + b"gpu-tool")
            result = path / "probe.img"
            with mock.patch("sys.argv", ["make-ram-probe", str(release), str(result),
                                         "--display-vblank", str(display), "--gpu-check", str(gpu)]), \
                    redirect_stdout(StringIO()):
                probe.main()
            _, kernel, ramdisk, dtb = pack.split_boot(result.read_bytes())
            self.assertEqual((kernel, dtb), (self.kernel, self.dtb))
            self.assertTrue(ramdisk.startswith(self.ramdisk))
            helpers = gzip.decompress(ramdisk[len(self.ramdisk):])
            self.assertIn(probe.newc_entry("umi-display-vblank", 2, 0o100755, display.read_bytes()), helpers)
            self.assertIn(probe.newc_entry("umi-gpu-check", 3, 0o100755, gpu.read_bytes()), helpers)

    def test_miseed_display_replaces_legacy_console_and_preserves_root(self):
        args = (self.kernel, self.ramdisk, self.dtb, UUID)
        with self.assertRaisesRegex(ValueError, 'MiSeed rescue command line'):
            pack.repack(self.header, *args, native_cmdline=b'console=tty0')
        cmd = ('console=tty0 consoleblank=60 fw_devlink=off root=UUID=' + UUID + ' rootwait').encode()
        self.header[64:576] = cmd.ljust(512, b'\0')
        display = b'console=ttyMSM0,115200n8 console=tty0 fbcon=font:TER16x32,rotate:3'
        header, *segments = pack.split_boot(
            pack.repack(self.header, *args, native_cmdline=display + b' rdinit=/init')
        )
        self.assertEqual(header[64:576].rstrip(b'\0'), display + b' root=UUID=' + UUID.encode() + b' rootwait')
        self.assertEqual(segments, list(args[:3]))

    def test_reject_overlong_cmdline(self):
        with self.assertRaisesRegex(ValueError, "command line does not fit"):
            pack.repack(self.header, self.kernel, self.ramdisk, self.dtb, UUID,
                        append_cmdline=b"x" * 512)


if __name__ == "__main__":
    unittest.main()
