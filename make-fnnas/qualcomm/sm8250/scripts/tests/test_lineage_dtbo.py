# SPDX-License-Identifier: GPL-2.0-only
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("lineage_dtbo", Path(__file__).resolve().parents[1] / "lineage-dtbo.py")
lineage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lineage)


def build(day, epoch, data):
    path = f"/full/umi/202611{day}/dtbo.img"
    return {"date": f"2026-11-{day}", "datetime": epoch, "version": "23.2", "files": [
        {"filename": "dtbo.img", "filepath": path, "url": lineage.MIRROR + path,
         "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}]}


class LineageDtboTests(unittest.TestCase):
    def test_latest_and_verified_cache(self):
        latest = build(22, 2, b"new")
        builds = [build(15, 1, b"old"), latest]
        with tempfile.TemporaryDirectory() as tmp, patch.object(lineage, "DTBO_SIZE", 3):
            out = Path(tmp)
            cache = out / "cache.img"
            cache.write_bytes(b"new")
            def fake_curl(url, path, limit):
                self.assertEqual(url, lineage.API)
                path.write_text(json.dumps(builds))
            with patch.object(lineage, "curl", fake_curl):
                record = lineage.fetch(out, cache)
            self.assertEqual(record["date"], "2026-11-22")
            self.assertEqual(json.loads((out / "lineage-dtbo.json").read_bytes()), record)
            self.assertEqual((out / "dtbo.img").read_bytes(), b"new")

    def test_does_not_fall_back_when_latest_is_missing_or_wrong_board(self):
        newest = build(22, 2, b"new")
        with patch.object(lineage, "DTBO_SIZE", 3):
            newest["files"][0]["url"] = lineage.MIRROR + "/full/other/20261122/dtbo.img"
            with self.assertRaisesRegex(ValueError, "unexpected"):
                lineage.latest([build(15, 1, b"old"), newest])
            newest["files"] = []
            with self.assertRaisesRegex(ValueError, "newest"):
                lineage.latest([build(15, 1, b"old"), newest])

    def test_bad_download_is_not_published(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(lineage, "DTBO_SIZE", 3):
            out = Path(tmp)
            def fake_curl(url, path, limit):
                data = json.dumps([build(22, 2, b"new")]).encode() if url == lineage.API else b"bad"
                path.write_bytes(data)
            with patch.object(lineage, "curl", fake_curl), self.assertRaisesRegex(ValueError, "SHA-256"):
                lineage.fetch(out)
            self.assertEqual(list(out.iterdir()), [])
