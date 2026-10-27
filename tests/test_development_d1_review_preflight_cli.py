"""CLI contract tests for review-to-attempt preflight binding; synthetic only."""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]


class ReviewPreflightCliTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.manifest = self.root / "manifest.json"
        plan = {"results_root": "results", "entries": [{"id": "fixture-run", "outputs": {
            "raw": "results/raw/fixture-run", "dataset": "results/dataset/fixture-run",
            "analysis": "results/analysis/fixture-run", "review": "results/reviews/fixture-run.json"}}]}
        self.manifest.write_text(json.dumps(plan))
        self.manifest_hash = self.sha(self.manifest)
        self.ops = self.root / "results/operations/fixture-run"
        self.ops.mkdir(parents=True)
        self.legacy = self.ops / "preflight.json"
        self.legacy.write_text(json.dumps({"ready": False, "error": "legacy failed readiness"}))
        self.legacy_bytes = self.legacy.read_bytes()
        report_dir = self.ops / "pf-0002"
        report_dir.mkdir()
        self.report_path = report_dir / "report.json"
        self.report = {"preflight_id": "pf-0002", "approved_entry": "fixture-run",
                       "manifest_sha256": self.manifest_hash, "ready": True}
        self.write_report()
        self.attempt = {"preflight_id": "pf-0002", "preflight_path": "results/operations/fixture-run/pf-0002/report.json",
                        "preflight_sha256": self.sha(self.report_path), "authorization_scope": "fixture-run",
                        "manifest_sha256": self.manifest_hash}
        self.write_attempt()

    def tearDown(self):
        self.temporary.cleanup()

    @staticmethod
    def sha(path):
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()

    def write_report(self):
        self.report_path.write_text(json.dumps(self.report))

    def write_attempt(self):
        (self.ops / "attempt.json").write_text(json.dumps(self.attempt))

    def cli(self):
        env = dict(os.environ)
        env["PYTHONPATH"] = str(REPO) + os.pathsep + env.get("PYTHONPATH", "")
        return subprocess.run([sys.executable, "-B", "-m", "experiments.development_d1_review",
            "--manifest", "manifest.json", "--entry", "fixture-run", "--preflight-binding-only"],
            cwd=self.root, env=env, text=True, capture_output=True)

    def test_cli_uses_new_bound_success_and_preserves_failed_legacy_record(self):
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        evidence = json.loads(result.stdout)
        self.assertEqual(evidence["preflight_id"], "pf-0002")
        self.assertEqual(evidence["preflight_path"], "results/operations/fixture-run/pf-0002/report.json")
        self.assertTrue(evidence["ready"])
        self.assertEqual(self.legacy.read_bytes(), self.legacy_bytes)

    def test_cli_rejects_wrong_path_hash_entry_manifest_or_not_ready(self):
        mutations = {
            "path": lambda: self.attempt.update(preflight_path="results/operations/other/report.json"),
            "hash": lambda: self.attempt.update(preflight_sha256="0" * 64),
            "attempt_entry": lambda: self.attempt.update(authorization_scope="other-run"),
            "manifest": lambda: self.attempt.update(manifest_sha256="bad-manifest"),
            "report_entry": lambda: self.report.update(approved_entry="other-run"),
            "report_manifest": lambda: self.report.update(manifest_sha256="bad-manifest"),
            "not_ready": lambda: self.report.update(ready=False),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                self.report = {"preflight_id": "pf-0002", "approved_entry": "fixture-run",
                               "manifest_sha256": self.manifest_hash, "ready": True}
                self.attempt = {"preflight_id": "pf-0002", "preflight_path": "results/operations/fixture-run/pf-0002/report.json",
                    "preflight_sha256": "", "authorization_scope": "fixture-run", "manifest_sha256": self.manifest_hash}
                mutate()
                self.write_report()
                if label not in {"hash", "path", "attempt_entry", "manifest"}:
                    self.attempt["preflight_sha256"] = self.sha(self.report_path)
                elif label == "hash":
                    self.attempt["preflight_sha256"] = "0" * 64
                else:
                    self.attempt["preflight_sha256"] = self.sha(self.report_path)
                self.write_attempt()
                result = self.cli()
                self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertEqual(self.legacy.read_bytes(), self.legacy_bytes)


if __name__ == "__main__":
    unittest.main()
