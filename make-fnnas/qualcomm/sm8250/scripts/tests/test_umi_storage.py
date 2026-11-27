# SPDX-License-Identifier: GPL-2.0-only
from copy import deepcopy
import importlib.util
from pathlib import Path
import unittest

file = Path(__file__).resolve().parents[1] / "plan-umi-storage.py"
spec = importlib.util.spec_from_file_location("umi_storage", file)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class UmiStorageTests(unittest.TestCase):
    def setUp(self):
        self.root = "/dev/sda34"
        self.fs = 8_880_390_144
        self.data = {"partitiontable": {"label": "gpt", "unit": "sectors", "device": "/dev/sda",
                                 "sectorsize": 4096, "firstlba": 6, "lastlba": 62_201_850,
                                 "partitions": [{"node": "/dev/sda33", "name": "stock",
                                                 "start": 2_875_392, "size": 8192},
                                                {"node": self.root, "name": "userdata", "start": 2_883_584,
                                                 "size": 59_318_267, "uuid": "0184b13a-ffa2-4eda-88e8-be51c8425080",
                                                 "type": "1B81E7E6-F50D-419B-A739-2AEEF8DA3335"}]}}

    def test_exact_split(self):
        p = mod.plan(self.data, self.root, self.fs)
        self.assertEqual(p["system"]["bytes"], 68_719_476_736)
        self.assertEqual(p["system"]["start_lba"], 2_883_584)
        tail = p["unallocated_tail_for_user_storage"]
        self.assertEqual(tail, {"start_lba": 19_660_800, "end_lba_inclusive": 62_201_850, "bytes": 174_248_144_896})
        self.assertEqual(p["system"]["partuuid"], self.data["partitiontable"]["partitions"][-1]["uuid"])

    def test_wrong_root(self):
        with self.assertRaisesRegex(ValueError, "mounted root"):
            mod.plan(self.data, "/dev/sde", self.fs)

    def test_btrfs_too_large(self):
        with self.assertRaisesRegex(ValueError, "smaller than 64 GiB"):
            mod.plan(self.data, self.root, mod.SYSTEM_BYTES + 1)

    def test_overlapping_partitions(self):
        self.data["partitiontable"]["partitions"][0]["size"] += 1
        with self.assertRaisesRegex(ValueError, "overlapping"):
            mod.plan(self.data, self.root, self.fs)

    def test_unknown_space_after_userdata(self):
        self.data["partitiontable"]["lastlba"] += 1
        with self.assertRaisesRegex(ValueError, "unexpected free tail"):
            mod.plan(self.data, self.root, self.fs)

    def smaller_capture(self):
        after = deepcopy(self.data)
        after["partitiontable"]["partitions"][-1]["size"] = 16_777_216
        return after

    def test_verify_after_rejects_changed_stock_attributes(self):
        after = self.smaller_capture()
        after["partitiontable"]["partitions"][0]["attrs"] = "GUID:60"
        with self.assertRaisesRegex(ValueError, "/dev/sda33"):
            mod.verify_split(self.data, after, self.root, self.fs)

    def test_verify_after_rejects_changed_root_uuid(self):
        after = self.smaller_capture()
        after["partitiontable"]["partitions"][-1]["uuid"] = "1B81E7E6-F50D-419B-A739-2AEEF8DA3335"
        with self.assertRaisesRegex(ValueError, "/dev/sda34"):
            mod.verify_split(self.data, after, self.root, self.fs)

    def test_verify_after_accepts_only_the_size_change(self):
        after = self.smaller_capture()
        self.assertIn("only userdata length changed", mod.verify_split(self.data, after, self.root, self.fs)["mode"])

    def created_fixture(self):
        self.data["partitiontable"]["table-length"] = "64"
        self.data["partitiontable"]["partitions"][0]["uuid"] = "12345678-1234-4321-9876-0123456789ab"
        after = self.smaller_capture()
        after["partitiontable"]["partitions"].append({
            "node": "/dev/sda35", "size": 42540800, "start": 19660800,
            "type": "A19D880F-05FC-4D3B-A006-743F0F84911E",
            "uuid": "89abcdef-0123-4321-9876-0123456789ab"})
        return after

    def test_verify_created(self):
        after = self.created_fixture()
        report = mod.verify_created(self.data, after, self.root, self.fs)
        self.assertEqual(report["data_partition"]["unused_trailing_sectors"], 251)
        self.assertEqual(len(after["partitiontable"]["partitions"]), 3)

    def test_reject_wrong_created_layout(self):
        after = self.created_fixture()
        for key, value in (("start", 19660799), ("size", 42541052), ("size", 1024),
                           ("type", self.data["partitiontable"]["partitions"][-1]["type"]),
                           ("uuid", self.data["partitiontable"]["partitions"][-1]["uuid"]),
                           ("node", "/dev/sdf1")):
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                one = deepcopy(after)
                one["partitiontable"]["partitions"][-1][key] = value
                mod.verify_created(self.data, one, self.root, self.fs)
        after["partitiontable"]["partitions"][0]["size"] -= 1
        with self.assertRaisesRegex(ValueError, "unexpected GPT changes"):
            mod.verify_created(self.data, after, self.root, self.fs)
