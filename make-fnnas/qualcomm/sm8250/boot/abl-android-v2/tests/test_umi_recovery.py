# SPDX-License-Identifier: GPL-2.0-only
"""Recovery packaging, fail-closed host checks, and the optional ARM64 PTY peer."""
import gzip
import hashlib
from importlib.util import module_from_spec, spec_from_file_location
import io
import os
from pathlib import Path
import subprocess
import time
import unittest

from test_umi_boot_tools import boot_header, fdt_header, pack, UUID


def load(name):
    path = Path(__file__).resolve().parents[1] / "recovery" / f"{name}.py"
    spec = spec_from_file_location(name, path)
    mod = module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


build = load("build-recovery")
host = load("send-recovery")
NONCE = b"b" * 32
BASE = "a" * 64
KERNEL = gzip.compress(b"test kernel")
DTB = fdt_header()
DONOR_RAMDISK = gzip.compress(b"DONOR_DATA")


class PackagingTests(unittest.TestCase):
    def fixture(self, flags=b"rootfstype=btrfs rootflags=subvolid=5"):
        return pack.repack(boot_header(), KERNEL, DONOR_RAMDISK, DTB, UUID,
                           append_cmdline=b"console=tty0 rootwait init=/somewhere " + flags)

    def test_independent_ramdisk_and_cmdline(self):
        base = self.fixture()
        sha = hashlib.sha256(base).hexdigest()
        header, kernel, ramdisk, dtb = pack.split_boot(build.assemble(base, b"TEST_PID1", sha))
        self.assertEqual(kernel, KERNEL)
        self.assertEqual(dtb, DTB)
        self.assertEqual(header[64:576].split(b"\0", 1)[0], b"console=tty0 rdinit=/init panic=10")
        self.assertEqual(gzip.decompress(ramdisk), build.probe.newc_entry("init", 1, 0o100755, b"TEST_PID1")
                         + build.probe.newc_entry("boot-sha256", 2, 0o100444, sha.encode() + b"\n")
                         + build.probe.newc_entry("TRAILER!!!", 0, 0, b""))

    def test_reject_unpinned_or_non_native_boot(self):
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            build.assemble(self.fixture(), b"init", BASE)
        for flags in (b"", b"rootfstype=ext4", b"rootfstype=btrfs", b"rootfstype=btrfs rootflags=subvolid=6"):
            base = self.fixture(flags)
            with self.assertRaisesRegex(ValueError, "native Umi Btrfs"):
                build.assemble(base, b"init", hashlib.sha256(base).hexdigest())


class FakeSerial:
    def __init__(self, ready, result=b""):
        self.rx = iter((ready, result))
        self.tx = bytearray()

    def write(self, data):
        self.tx.extend(data)
        return len(data)

    def read(self, count):
        return next(self.rx)[:count]


class TransferTests(unittest.TestCase):
    def transfer(self, port, payload=b"data", *, size=4):
        return host.transfer(port, io.BytesIO(payload), size, BASE,
                             nonce=NONCE, deadline=time.monotonic()+5)

    def ready(self, digest=BASE):
        return b" ".join((host.PROTOCOL, b"READY", NONCE, digest.encode())) + b"\n"

    def test_boot_mismatch_does_not_send_payload(self):
        for response in (self.ready("c" * 64), self.ready().replace(NONCE, b"0" * 32), b"", b"login:"):
            port = FakeSerial(response)
            with self.assertRaisesRegex(OSError, "READY/boot identity"):
                self.transfer(port)
            self.assertEqual(port.tx, b" ".join((host.PROTOCOL, b"HASH", NONCE, b"4")) + b"\n")

    def test_bad_receipt_and_mutable_file(self):
        with self.assertRaisesRegex(OSError, "SHA-256 receipt"):
            self.transfer(FakeSerial(self.ready()))
        with self.assertRaisesRegex(OSError, "truncated"):
            self.transfer(FakeSerial(self.ready()), b"a")
        with self.assertRaisesRegex(OSError, "grew"):
            self.transfer(FakeSerial(self.ready()), b"data!")
        with self.assertRaises(ValueError):
            self.transfer(FakeSerial(self.ready()), size=host.MAX_PAYLOAD + 1)

    def test_read_only_gpt_matches_verified_raw_backups(self):
        class Port(FakeSerial):
            def read_until(self, terminator, size):
                return self.read(size)

        primary, backup = "c" * 64, "d" * 64
        response = b" ".join((host.PROTOCOL, b"GPT-RESULT", NONCE, BASE.encode(), b"sda",
                              b"254778802176", b"4096", b"ram-only", primary.encode(), backup.encode())) + b"\n"
        port = Port(response)
        result = host.verify_gpt(port, BASE, primary, backup, nonce=NONCE)
        self.assertEqual(result["device"], "/dev/sda")
        self.assertEqual(port.tx, b" ".join((host.PROTOCOL, b"GPT", NONCE)) + b"\n")
        for bad in (response[:-1], response.replace(backup.encode(), b"e"*64),
                    response.replace(b"ram-only", b"root-mounted"), response.replace(b"4096", b"512")):
            with self.assertRaisesRegex(OSError, "do not match"):
                host.verify_gpt(Port(bad), BASE, primary, backup, nonce=NONCE)

    @unittest.skipUnless(os.environ.get("UMI_RECOVERY_PEER"), "requires cross-built ARM64 PTY peer")
    def test_host_to_arm64_over_pty(self):
        import pty
        import serial

        master, slave = pty.openpty()
        try:
            payload = bytes(range(256)) * 32768  # 8 MiB, including terminal control bytes
            with serial.Serial(os.ttyname(slave), 115200, timeout=15, write_timeout=5) as port:
                with subprocess.Popen(["qemu-aarch64-static", os.environ["UMI_RECOVERY_PEER"],
                                       "-test.run=^TestStdioPeer$"], stdin=master, stdout=master,
                                      env={**os.environ, "UMI_RECOVERY_STDIO": "1"}) as peer:
                    try:
                        report = self.transfer(port, payload, size=len(payload))
                        self.assertEqual(report["bytes"], len(payload))
                        self.assertEqual(report["sha256"], hashlib.sha256(payload).hexdigest())
                        self.assertEqual(peer.wait(timeout=5), 0)
                    finally:
                        if peer.poll() is None:
                            peer.kill()
        finally:
            os.close(master)
            os.close(slave)
