"""Offline DEVELOPMENT D2 authority and configuration checks."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from experiments import development_d1_ops as ops
from experiments.development_d2 import validate_plan
from experiments.development_d2 import verify_approved_checkout


MANIFEST = ops.ROOT / "experiments/protocols/development_d2_endpoint_comparison_20261027/manifest_v3.json"


class D2PreparationTests(unittest.TestCase):
    def test_manifest_configs_seeds_order_and_outputs_validate_offline(self):
        result = validate_plan(MANIFEST)
        self.assertEqual(result["configurations"], 7)
        self.assertEqual(result["comparative_runs"], 6)
        self.assertEqual(result["probe_runs"], 1)
        self.assertFalse(result["docker_accessed"])
        self.assertFalse(result["experiments_executed"])
        plan = json.loads(MANIFEST.read_text())
        self.assertEqual([e["endpoint"] for e in plan["entries"][1:]],
                         ["/light", "/medium", "/expensive", "/expensive", "/medium", "/light"])
        self.assertEqual(plan["campaign_schema"], "development-endpoint-comparison/v3")
        self.assertEqual(plan["provenance"]["parent_manifest_path"],
                         "experiments/protocols/development_d2_endpoint_comparison_20261027/manifest_v2.json")
        self.assertEqual(plan["source_approval"]["anchor_commit"], plan["instrumentation_commit"])
        self.assertEqual(plan["source_approval"]["source_hashes"], plan["runtime_source_hashes"])
        self.assertTrue(all("parent_sha256" in x and "effective_sha256" in x
                            for x in plan["provenance"]["source_hash_transitions"].values()))
        for endpoint in ("/light", "/medium", "/expensive"):
            pair = [e for e in plan["entries"][1:] if e["endpoint"] == endpoint]
            self.assertEqual(pair[0]["effective_configuration"]["seed"], plan["development_seeds"]["A"])
            self.assertEqual(pair[1]["effective_configuration"]["seed"], plan["development_seeds"]["B"])
            self.assertEqual(pair[0]["aggregate_rps"], pair[1]["aggregate_rps"])
        self.assertIsNone(plan["criteria"]["p95_limit_ms"])

    def test_shared_operations_gate_requires_probe_review_before_comparison(self):
        old_manifest = ops.ACTIVE_MANIFEST
        try:
            ops.ACTIVE_MANIFEST = ops.D2_MANIFEST
            plan, evidence = ops.get_plan()
            self.assertEqual(evidence["comparative_runs"], 6)
            self.assertEqual(ops.check_predecessors(plan, 0), [])
            with self.assertRaisesRegex(ValueError, "Missing accepted review"):
                ops.check_predecessors(plan, 1)
        finally:
            ops.ACTIVE_MANIFEST = old_manifest

    def test_preflight_history_retries_readiness_but_run_selects_successful_id(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            failed = root / "preflight.json"
            failed.write_text(json.dumps({"ready": False, "error": "fixture denial"}))
            original = failed.read_bytes()
            next_dir = root / "pf-0002"
            next_dir.mkdir()
            report = next_dir / "report.json"
            report.write_text(json.dumps({"preflight_id": "pf-0002", "ready": True,
                "approved_entry": "probe", "manifest_sha256": "authority"}))
            selected, data = ops.select_successful_preflight(root, "pf-0002", "probe", "authority")
            self.assertEqual(selected, report)
            self.assertTrue(data["ready"])
            self.assertEqual(failed.read_bytes(), original)
            with self.assertRaisesRegex(RuntimeError, "not a successful match"):
                ops.select_successful_preflight(root, "pf-0001", "probe", "authority")

    def test_second_experimental_attempt_is_blocked(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            ops.ensure_single_experimental_attempt(root)
            (root / "attempt.json").write_text("{}")
            with self.assertRaisesRegex(RuntimeError, "retries are forbidden"):
                ops.ensure_single_experimental_attempt(root)

    def test_approved_sources_allow_descendant_commit_but_reject_changed_source(self):
        approved = {"simulator/source.py": "abc123"}
        accepted = verify_approved_checkout("base", "later-commit", approved,
                                            dict(approved), is_ancestor=True)
        self.assertEqual(accepted["effective_checkout_commit"], "later-commit")
        with self.assertRaisesRegex(ValueError, "source changed"):
            verify_approved_checkout("base", "later-commit", approved,
                                     {"simulator/source.py": "changed"}, is_ancestor=True)
        with self.assertRaisesRegex(ValueError, "not a descendant"):
            verify_approved_checkout("base", "unrelated", approved,
                                     dict(approved), is_ancestor=False)

    def test_real_later_git_commit_is_allowed_when_approved_source_is_identical(self):
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            def git(*args):
                return subprocess.check_output(["git", *args], cwd=repo, text=True).strip()
            git("init", "-q")
            git("config", "user.email", "offline@example.invalid")
            git("config", "user.name", "Offline Fixture")
            source = repo / "runtime.py"
            source.write_text("approved = True\n")
            git("add", "runtime.py")
            git("commit", "-qm", "approved source")
            anchor = git("rev-parse", "HEAD")
            expected = {"runtime.py": ops.sha(source)}
            unrelated = repo / "notes.txt"
            unrelated.write_text("later commit\n")
            git("add", "notes.txt")
            git("commit", "-qm", "documentation only")
            later = git("rev-parse", "HEAD")
            ancestor = subprocess.run(["git", "merge-base", "--is-ancestor", anchor, later], cwd=repo).returncode == 0
            verify_approved_checkout(anchor, later, expected, {"runtime.py": ops.sha(source)}, is_ancestor=ancestor)
            source.write_text("approved = False\n")
            self.assertNotEqual(ops.sha(source), expected["runtime.py"])
            with self.assertRaisesRegex(ValueError, "source changed"):
                verify_approved_checkout(anchor, later, expected, {"runtime.py": ops.sha(source)}, is_ancestor=ancestor)


if __name__ == "__main__":
    unittest.main()
