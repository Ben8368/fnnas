"""Regression tests for selecting and consuming released Umi kernels."""

import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location(
    "kernel_release", Path(__file__).resolve().parents[1] / "kernel-release.py"
)
kernel_release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kernel_release)


def asset(version, rate, state="uploaded"):
    return {"name": f"{version}-qualcomm-sm8250-xiaomi-umi-csot{rate}.tar.gz", "state": state}


class KernelReleaseTests(unittest.TestCase):
    def test_release_selection_is_numeric_paginated_and_profile_specific(self):
        release = {"id": 1, "draft": False, "prerelease": False}
        first_page = [asset("6.18.99", "90"), asset("6.18.9", "60")] + [
            {"name": f"6.18.{i}-rockchip.tar.gz"} for i in range(98)
        ]
        latest = asset("6.18.10", "60")
        second_page = [latest, asset("6.18.200", "60", state="starter"),
                       asset("6.18.201-rc1", "60"), asset("6.19.300", "60")]
        for requested, expected, selected in [("auto", "6.18.10", latest),
                                              ("6.18.9", "6.18.9", first_page[1])]:
            with patch.object(kernel_release, "release_api", side_effect=[release, first_page, second_page]):
                self.assertEqual(kernel_release.select_asset("owner/repo", "60", requested), (expected, selected))
        with patch.object(kernel_release, "release_api", side_effect=[release, [latest]]):
            with self.assertRaisesRegex(ValueError, "no published Umi CSOT 90 Hz kernel"):
                kernel_release.select_asset("owner/repo", "90", "auto")

    def test_package_round_trip_and_digest_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            kernel = root / "build"
            version, rate = "6.18.65", "90"
            release = f"{version}-csot{rate}-sm8250"
            for name in kernel_release.FILES:
                file = kernel / name
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text(name)
            (kernel / "kernel-source.tsv").write_text(f"{version}\t{'a' * 40}\n")
            (kernel / "refresh").write_text(rate + "\n")
            (kernel / "include/config/kernel.release").write_text(release + "\n")
            (kernel / "SHA256SUMS").write_text("".join(
                f"{kernel_release.sha256(kernel / name)}  {name}\n" for name in kernel_release.BOOT_FILES
            ))
            modules = root / "module-root"
            module = Path("lib/modules") / release / "modules.dep"
            (modules / module).parent.mkdir(parents=True)
            (modules / module).touch()
            info = asset(version, rate)
            kernel_release.pack(kernel, modules, root)
            bundle = root / info["name"]
            info.update(size=bundle.stat().st_size, digest="sha256:" + kernel_release.sha256(bundle))
            with patch.object(kernel_release, "urlopen", return_value=io.BytesIO(bundle.read_bytes())):
                kernel_release.fetch("owner/repo", version, rate, info, root / "unpacked")
            self.assertTrue((root / "unpacked" / module).is_file())
            self.assertEqual(kernel_release.read_kernel(root / "unpacked"), (version, rate, release))
            info["digest"] = "sha256:" + "0" * 64
            with patch.object(kernel_release, "urlopen", return_value=io.BytesIO(bundle.read_bytes())):
                with self.assertRaisesRegex(ValueError, "digest or size mismatch"):
                    kernel_release.fetch("owner/repo", version, rate, info, root / "bad")
            self.assertFalse((root / "bad").exists())


if __name__ == "__main__":
    unittest.main()
