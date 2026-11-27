# SPDX-License-Identifier: GPL-2.0-only
import runpy
import struct
import unittest
from pathlib import Path
from uuid import UUID
import zlib

M = runpy.run_path(str(Path(__file__).resolve().parents[1] / "prepare-umi-storage-fixture.py"))
S, LAST, prepare = M["SECTOR"], M["LAST"], M["prepare"]


class FixtureTests(unittest.TestCase):
    def setUp(self):
        self.guid = UUID(int=1000)
        entries = bytearray(64 * 128)
        parts = []
        for i in range(34):
            start = 6 + i if i < 33 else 2_883_584
            end = start if i < 33 else LAST - 5
            name = f"p{i}" if i < 33 else "userdata"
            guid = UUID(int=100 + i)
            struct.pack_into("<16s16sQQQ72s", entries, i * 128, UUID(int=7).bytes_le, guid.bytes_le,
                             start, end, 1 << 60, name.encode("utf-16le"))
            parts.append(dict(node=f"/dev/sda{i+1}", name=name, start=start, size=end-start+1,
                              type=str(UUID(int=7)), uuid=str(guid)))
        self.gpt = {"partitiontable": dict(label="gpt", unit="sectors", device="/dev/sda", firstlba=6,
                                           lastlba=LAST-5, sectorsize=S, partitions=parts, id=str(self.guid),
                                           **{"table-length": "64"})}
        self.regions = []
        for backup in (False, True):
            buf = bytearray(b"\xa5" * ((5 if backup else 6)*S))  # preserve non-zero padding
            head = (4 if backup else 1)*S
            arr = 0 if backup else 2*S
            buf[arr:arr + len(entries)] = entries
            if not backup:
                buf[450] = 0xee
                buf[510:512] = b"\x55\xaa"
            struct.pack_into("<8sIIIIQQQQ16sQIII", buf, head, b"EFI PART", 0x10000, 92, 0, 0,
                             LAST if backup else 1, 1 if backup else LAST, 6, LAST-5, self.guid.bytes_le,
                             LAST-4 if backup else 2, 64, 128, zlib.crc32(entries))
            struct.pack_into("<I", buf, head+16, zlib.crc32(buf[head:head+92]))
            self.regions.append(bytes(buf))

    def test_allowlisted_diffs_and_crcs(self):
        for guid in (None, UUID(int=999)):
            out = prepare(self.gpt, 8 << 30, *self.regions, guid)
            for i in (0, 1):
                head, arr = (4*S, 0) if i else (S, 2*S)
                allowed = set(range(head+16, head+20)) | set(range(head+88, head+92))
                allowed.update(range(arr+33*128+40, arr+33*128+48))
                if guid:
                    allowed.update(range(arr+34*128, arr+35*128))
                    self.assertEqual(struct.unpack_from("<QQ", out[i], arr+34*128+32), (19660800, 62201599))
                changed = {j for j,(a,b) in enumerate(zip(self.regions[i], out[i])) if a != b}
                self.assertTrue(changed and changed <= allowed)
                h = bytearray(out[i][head:head+92]); crc, = struct.unpack_from("<I", h, 16)
                struct.pack_into("<I", h, 16, 0)
                self.assertEqual(crc, zlib.crc32(h))
                self.assertEqual(struct.unpack_from("<I", h, 88)[0], zlib.crc32(out[i][arr:arr+8192]))

    def test_rejects_damaged_or_wrong_layout(self):
        p, b = self.regions
        for bad in (b + bytes(S), b[:80] + bytes([b[80]^1]) + b[81:], b[:4*S] + bytes(S)):
            with self.assertRaises(ValueError):
                prepare(self.gpt, 8 << 30, p, bad)
        for guid in (self.guid, UUID(int=101), UUID(int=0)):
            with self.assertRaises(ValueError):
                prepare(self.gpt, 8 << 30, p, b, guid)
        self.gpt["partitiontable"]["partitions"][0]["uuid"] = str(UUID(int=19))
        with self.assertRaises(ValueError):
            prepare(self.gpt, 8 << 30, p, b)
