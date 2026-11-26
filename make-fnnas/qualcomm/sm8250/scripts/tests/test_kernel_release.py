"""Regression tests for selecting and consuming released Umi kernels."""

import importlib.util
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
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
    def test_only_accepted_releases_are_selected_numerically(self):
        def release(version, rate="60"):
            source = "a" * 40
            data = {"schema": 1, "repository": "owner/repo", "build_repository": kernel_release.PUBLISH_REPO,
                    "branch": kernel_release.PUBLISH_BRANCH,
                    "version": version, "profile": f"csot-{rate}", "source_commit": source,
                    "linux_commit": "b" * 40, "patches_sha256": "c" * 64,
                    "run_id": 42, "run_attempt": 1, "package_sha256": "d" * 64}
            data["acceptance"] = {**data, "device": "xiaomi-umi", "scope": "kernel", "result": "pass",
                                  "method": "fastboot-boot", "operator": "test", "tested_at": "test",
                                  "evidence_sha256": "e" * 64}
            return {"tag_name": kernel_release.tag_for(version, rate, source), "body": json.dumps(data),
                    "draft": False, "prerelease": False, "assets": [
                        {**asset(version, rate), "digest": "sha256:" + "d" * 64},
                        {"name": "device-evidence.log", "state": "uploaded", "digest": "sha256:" + "e" * 64}]}

        rejected = release("6.18.99")
        rejected["body"] = rejected["body"].replace('"result": "pass"', '"result": "fail"')
        with patch.object(kernel_release, "release_api", side_effect=[
            [rejected, release("6.18.99", "90"), release("6.18.11"), release("6.18.9"), release("6.18.10")],
            {"object": {"type": "commit", "sha": "f" * 40}}, # moved tag
            {"object": {"type": "commit", "sha": "a" * 40}},
            {"object": {"type": "commit", "sha": "a" * 40}},
        ]):
            self.assertEqual(kernel_release.select_asset("owner/repo", "60", "auto")[0], "6.18.10")
        with patch.object(kernel_release, "release_api", return_value=[rejected]):
            with self.assertRaisesRegex(ValueError, "no accepted"):
                kernel_release.select_asset("owner/repo", "60", "auto")

    def test_promotion_rejects_wrong_source_or_attempt_before_download(self):
        p = kernel_release
        source = "a" * 40
        destination = {"private": False, "owner": {"login": p.PUBLISH_OPERATOR}, "full_name": p.PUBLISH_REPO}
        valid = {"head_repository": {"full_name": p.PUBLISH_REPO}, "head_branch": p.PUBLISH_BRANCH,
                 "head_sha": source, "conclusion": "success", "event": "push", "path": p.WORKFLOW,
                 "id": 123, "run_attempt": 2}
        request = SimpleNamespace(source=source, profile="release", run_id=123, run_attempt=2,
                                  release_repo=None, publish=False)
        for name, rejected in {"head_branch": "pr/qualcomm-test", "head_sha": "b" * 40,
                               "run_attempt": 1, "conclusion": "failure", "event": "workflow_dispatch"}.items():
            with self.subTest(name=name), patch.object(p, "gh", side_effect=[json.dumps(destination),
                    json.dumps({**valid, name: rejected})]) as gh:
                with self.assertRaisesRegex(ValueError, "Not a successful build"):
                    p.promote(request)
                self.assertEqual(gh.call_count, 2)  # Never download, tag or publish.

    def test_acceptance_must_name_the_exact_package(self):
        p = kernel_release
        identity = {"run_id": 123, "run_attempt": 2, "source_commit": "a" * 40,
                    "linux_commit": "b" * 40, "profile": "release", "package_sha256": "c" * 64}
        stale = {**identity, "package_sha256": "d" * 64}
        with self.assertRaisesRegex(ValueError, "exact build and package"):
            p.acceptance_record(stale, identity)

    def test_native_acceptance_requires_device_recovery_and_exact_images(self):
        p = kernel_release
        identity = {"run_id": 123, "run_attempt": 1, "source_commit": "a" * 40, "linux_commit": "b" * 40,
                    "version": "6.18.65", "profile": "csot-90", "package_sha256": "c" * 64}
        record = {**identity, "device": "xiaomi-umi", "scope": "kernel", "result": "pass",
                  "method": "native-fastboot-flash", "operator": "operator", "tested_at": "date",
                  "evidence_sha256": "e" * 64, "dtbo_index": 11, "dtbo_sha256": "d" * 64,
                  "boot_sha256": "e" * 64, "rootfs_sha256": "f" * 64}
        p.acceptance_record(record, identity)
        lines = ["UMI_NATIVE: kernel=6.18.65-csot90-sm8250", f"UMI_NATIVE: artifact_sha256={'c' * 64}",
                 *(f"UMI_NATIVE: {key}={record[key]}" for key in
                   ("dtbo_index", "dtbo_sha256", "boot_sha256", "rootfs_sha256"))]
        with self.assertRaisesRegex(ValueError, "incomplete for native-fastboot-flash"):
            p.verify_evidence(record, identity, "\n".join([*lines, "Android sys.boot_completed=1"]))
        p.verify_evidence(record, identity, "\n".join([*lines, "UMI_NATIVE: recovery=fastboot-to-fnos"]))
        with self.assertRaisesRegex(ValueError, "image pair and stock DTBO"):
            p.acceptance_record({**record, "rootfs_sha256": "invalid"}, identity)

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
            kernel_release.pack(kernel, modules, root, "csot-90", "f" * 40)
            provenance = {"source_commit": "f" * 40, "version": version, "profile": "csot-90",
                          "linux_commit": "a" * 40, "patches_sha256": kernel_release.sha256(kernel / "armbian-patches.tsv")}
            tag = kernel_release.tag_for(version, rate, "f" * 40)
            bundle = root / info["name"]
            info.update(size=bundle.stat().st_size, digest="sha256:" + kernel_release.sha256(bundle))
            with patch.object(kernel_release, "urlopen", return_value=io.BytesIO(bundle.read_bytes())):
                kernel_release.fetch("owner/repo", version, rate, info, tag, provenance, root / "unpacked")
            self.assertTrue((root / "unpacked" / module).is_file())
            self.assertEqual(kernel_release.read_kernel(root / "unpacked"), (version, rate, release))
            info["digest"] = "sha256:" + "0" * 64
            with patch.object(kernel_release, "urlopen", return_value=io.BytesIO(bundle.read_bytes())):
                with self.assertRaisesRegex(ValueError, "digest or size mismatch"):
                    kernel_release.fetch("owner/repo", version, rate, info, tag, provenance, root / "bad")
            self.assertFalse((root / "bad").exists())

            candidate = SimpleNamespace(output=root / "candidate", profile="csot-90", package_sha256="0" * 64)
            data = {**provenance, "package_sha256": kernel_release.sha256(bundle)}
            with patch.object(kernel_release, "check_run"), \
                 patch.object(kernel_release, "download_candidate", return_value=(bundle, data)):
                with self.assertRaisesRegex(ValueError, "package SHA-256 mismatch"):
                    kernel_release.fetch_candidate(candidate)
                self.assertFalse(candidate.output.exists())
                candidate.package_sha256 = data["package_sha256"]
                kernel_release.fetch_candidate(candidate)
            self.assertFalse((candidate.output / "promotion.json").exists())
            self.assertEqual(json.loads((candidate.output / "candidate.json").read_text())["status"], "debug-candidate")


if __name__ == "__main__":
    unittest.main()
