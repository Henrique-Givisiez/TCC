"""Offline DEVELOPMENT D2 authority and configuration checks."""
import json
import unittest

from experiments import development_d1_ops as ops
from experiments.development_d2 import validate_plan


MANIFEST = ops.ROOT / "experiments/protocols/development_d2_endpoint_comparison_20261027/manifest_v2.json"


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
        self.assertEqual(plan["campaign_schema"], "development-endpoint-comparison/v2")
        self.assertEqual(plan["provenance"]["parent_manifest_path"],
                         "experiments/protocols/development_d2_endpoint_comparison_20261027/manifest.json")
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


if __name__ == "__main__":
    unittest.main()
