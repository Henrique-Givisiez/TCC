"""Offline authority/configuration validation and service summaries for D2."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from dataclasses import replace
from pathlib import Path

from simulator.experiment_config import ExperimentConfig

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "experiments/protocols/development_d2_endpoint_comparison_20261027/manifest_v3.json"
V1_SCHEMA = "development-endpoint-comparison/v1"
V2_SCHEMA = "development-endpoint-comparison/v2"
V3_SCHEMA = "development-endpoint-comparison/v3"


def verify_approved_checkout(anchor_commit, checkout_commit, approved_hashes, actual_hashes, *, is_ancestor):
    """Approve descendant commits only while the bound source set is byte-identical."""
    if not is_ancestor:
        raise ValueError("Checkout is not a descendant of the approved code anchor")
    if set(approved_hashes) != set(actual_hashes):
        raise ValueError("Approved source set differs from effective source set")
    changed = [path for path, digest in approved_hashes.items() if actual_hashes[path] != digest]
    if changed:
        raise ValueError(f"Approved operational source changed: {changed}")
    return {"approved_anchor_commit": anchor_commit, "effective_checkout_commit": checkout_commit,
            "source_hashes": dict(actual_hashes), "source_tree_unchanged": True}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def validate_plan(manifest_path=DEFAULT_MANIFEST, *, check_outputs=True):
    manifest_path = Path(manifest_path)
    plan = read(manifest_path)
    if plan.get("campaign_schema") not in {V1_SCHEMA, V2_SCHEMA, V3_SCHEMA}:
        raise ValueError("Unknown D2 protocol schema")
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if plan["campaign_schema"] == V1_SCHEMA and head != plan["instrumentation_commit"]:
        raise ValueError(f"Expected instrumentation commit {plan['instrumentation_commit']}, got {head}")
    anchor = plan.get("source_approval", {}).get("anchor_commit", plan["instrumentation_commit"])
    ancestor = subprocess.run(["git", "merge-base", "--is-ancestor", anchor, head], cwd=ROOT).returncode == 0
    for path, expected in plan["runtime_source_hashes"].items():
        if sha(ROOT / path) != expected:
            raise ValueError(f"Operational source changed: {path}")
    checkout_evidence = verify_approved_checkout(anchor, head, plan["runtime_source_hashes"],
        {path: sha(ROOT / path) for path in plan["runtime_source_hashes"]}, is_ancestor=ancestor)
    if plan["campaign_schema"] == V3_SCHEMA:
        approval = plan["source_approval"]
        if approval.get("anchor_commit") != plan["instrumentation_commit"]:
            raise ValueError("D2 source approval anchor differs from instrumentation provenance")
        if approval.get("source_hashes") != plan["runtime_source_hashes"]:
            raise ValueError("Source approval hashes do not match operational hash authority")
        diagnostic = ROOT / plan["docker_access_diagnosis"]["path"]
        if sha(diagnostic) != plan["docker_access_diagnosis"]["sha256"]:
            raise ValueError("Docker access diagnosis document hash mismatch")
        provenance = plan["provenance"]
        parent_path = ROOT / provenance["parent_manifest_path"]
        if sha(parent_path) != provenance["parent_manifest_sha256"]:
            raise ValueError("Parent D2 authority hash mismatch")
        parent = read(parent_path)
        if parent.get("campaign_schema") != V2_SCHEMA or provenance["parent_instrumentation_commit"] != parent["instrumentation_commit"]:
            raise ValueError("D2 v3 parent provenance mismatch")
        transitions = provenance["source_hash_transitions"]
        if set(transitions) != set(plan["runtime_source_hashes"]) or set(transitions) != set(parent["runtime_source_hashes"]):
            raise ValueError("D2 provenance source set differs")
        for source, transition in transitions.items():
            actual, old = sha(ROOT / source), parent["runtime_source_hashes"][source]
            if (transition.get("parent_sha256") != old or transition.get("effective_sha256") != actual
                    or transition.get("effective_sha256") != plan["runtime_source_hashes"][source]
                    or transition.get("changed") != (old != actual)):
                raise ValueError(f"D2 source hash provenance mismatch: {source}")
    if plan["campaign_schema"] == V2_SCHEMA:
        provenance = plan["provenance"]
        parent_path = ROOT / provenance["parent_manifest_path"]
        if sha(parent_path) != provenance["parent_manifest_sha256"]:
            raise ValueError("Parent D2 authority hash mismatch")
        parent = read(parent_path)
        if parent.get("campaign_schema") != V1_SCHEMA or provenance["parent_instrumentation_commit"] != parent["instrumentation_commit"]:
            raise ValueError("D2 v2 parent provenance mismatch")
        transitions = provenance["source_hash_transitions"]
        if set(transitions) != set(plan["runtime_source_hashes"]) or set(transitions) != set(parent["runtime_source_hashes"]):
            raise ValueError("D2 provenance source set differs")
        for source, transition in transitions.items():
            actual = sha(ROOT / source)
            old = parent["runtime_source_hashes"][source]
            if (transition.get("parent_sha256") != old or transition.get("effective_sha256") != actual
                    or transition.get("effective_sha256") != plan["runtime_source_hashes"][source]
                    or transition.get("changed") != (old != actual)):
                raise ValueError(f"D2 source hash provenance mismatch: {source}")
    audit_path = ROOT / plan["seed_audit_path"]
    if sha(audit_path) != plan["seed_audit_sha256"]:
        raise ValueError("Seed audit hash mismatch")
    audit = read(audit_path)
    existing = set()
    from experiments.development_d1 import collect_seeds
    for item in audit["sources"]:
        path = ROOT / item["path"]
        if sha(path) != item["sha256"]:
            raise ValueError(f"Historical seed source changed: {item['path']}")
        seeds = sorted(collect_seeds(read(path)))
        if seeds != item["seeds"]:
            raise ValueError(f"Seed extraction changed: {item['path']}")
        existing.update(seeds)
    generation = plan["seed_generation"]
    generated = {label: int.from_bytes(hashlib.sha256(
        f"{generation['namespace']}:{label}:{generation['indices'][label]}".encode()).digest()[:8], "big")
        for label in ("A", "B", "PROBE")}
    if generated != plan["development_seeds"]:
        raise ValueError("D2 seed derivation differs from reservation")
    if len(set(generated.values())) != 3 or set(generated.values()) & existing:
        raise ValueError("D2 seed collision")
    for evidence in plan["d1_evidence"]["files"]:
        if sha(ROOT / evidence["path"]) != evidence["sha256"]:
            raise ValueError(f"D1 evidence changed: {evidence['path']}")
    d1_synthesis = read(ROOT / plan["d1_evidence"]["synthesis_path"])
    if d1_synthesis["highest_accepted_level"] != "L05":
        raise ValueError("D1 does not contain accepted evidence through L05")
    if plan["entries"][0]["role"] != "capacity_probe":
        raise ValueError("The expensive-endpoint probe must precede comparative runs")
    if plan.get("automatic_progression") is not False or plan.get("maximum_attempts") != 7:
        raise ValueError("D2 must remain entry-gated with a seven-attempt ceiling")
    criteria = plan["criteria"]
    expected_criteria = {"aggregate_start_ratio": [0.8, 1.2], "per_source_start_ratio": [0.65, 1.35],
                         "success_2xx_per_started_min": 0.99, "failures_per_started_max": 0.01,
                         "incomplete_max": 0, "other_response_max": 0,
                         "terminal_success_rps_over_nominal_min": 0.8,
                         "minimum_success_duration_support": 200, "victim_monitor_support": "at least108/120 useful ticks; max supported gap5s",
                         "proxy_monitor_support": "at least90% of 120 expected slots per status/docker source; max success gap5s",
                         "p95_limit_ms": None,
                         "drain": "four source_closed, drained and logger_complete; no forced source termination; elapsed cutoff <=180s."}
    for name, expected in expected_criteria.items():
        if criteria.get(name) != expected:
            raise ValueError(f"D2 decision criterion changed: {name}")
    if plan["fixed_conditions"]["duration_seconds"] != 150 or plan["fixed_conditions"]["warmup_seconds"] != 30 or plan["fixed_conditions"]["useful_interval_seconds"] != [30, 150]:
        raise ValueError("D2 duration or phase boundaries differ from the reviewed schedule")
    if plan["fixed_conditions"]["aggregate_rps"] != 4 or plan["fixed_conditions"]["rps_per_client"] != 1:
        raise ValueError("D2 is not using the common 4 RPS candidate")
    if plan["probe"]["entry_id"] != plan["entries"][0]["id"] or plan["probe"]["retain_4rps"] is None or plan["probe"]["if_inadequate"] is None:
        raise ValueError("D2 probe gate or reduction rule is unspecified")
    revised_order = plan["campaign_schema"] in {V2_SCHEMA, V3_SCHEMA}
    expected_ids = (["d2_probe_expensive_4rps", "d2_A_light", "d2_A_medium", "d2_A_expensive",
                     "d2_B_expensive", "d2_B_medium", "d2_B_light"]
                    if revised_order else
                    ["d2_probe_expensive_4rps", "d2_A_light", "d2_A_medium", "d2_A_expensive",
                     "d2_B_medium", "d2_B_expensive", "d2_B_light"])
    if [entry["id"] for entry in plan["entries"]] != expected_ids:
        raise ValueError("D2 entry order changed")
    expected_endpoints = (["/expensive", "/light", "/medium", "/expensive", "/expensive", "/medium", "/light"]
                          if revised_order else
                          ["/expensive", "/light", "/medium", "/expensive", "/medium", "/expensive", "/light"])
    if [entry["endpoint"] for entry in plan["entries"]] != expected_endpoints:
        raise ValueError("D2 endpoint sequence differs from its versioned order")
    base_config = ExperimentConfig.load(ROOT / "experiments/configs/development_d1_20261027/d1_L01_A.json")
    fixed = replace(base_config, id="d2_fixed", seed=generated["PROBE"],
                    normal_traffic=replace(base_config.normal_traffic, endpoint="/medium"))
    output_paths = set()
    for index, entry in enumerate(plan["entries"], 1):
        path = ROOT / entry["config"]
        if sha(path) != entry["config_sha256"]:
            raise ValueError(f"Config hash mismatch: {entry['id']}")
        config = ExperimentConfig.load(path)
        if json.loads(path.read_text()) != json.loads(config.to_json()) or json.loads(config.to_json()) != entry["effective_configuration"]:
            raise ValueError(f"Incomplete or noncanonical configuration: {entry['id']}")
        replicate = entry["replicate"]
        wanted_seed = generated["PROBE"] if replicate == "PROBE" else generated[replicate]
        wanted = replace(fixed, id=entry["id"], seed=wanted_seed,
                         normal_traffic=replace(fixed.normal_traffic, endpoint=entry["endpoint"]))
        if config != wanted:
            raise ValueError(f"D2 fixed conditions differ for {entry['id']}")
        if entry["order"] != index or entry["rps_per_client"] != 1 or entry["aggregate_rps"] != 4:
            raise ValueError(f"D2 rate/order mismatch: {entry['id']}")
        for output in entry["outputs"].values():
            if output in output_paths:
                raise ValueError(f"Output collision: {output}")
            output_paths.add(output)
            if check_outputs and (ROOT / output).exists():
                raise FileExistsError(f"Output already exists: {output}")
    comparison_entries = plan["entries"][1:]
    for endpoint in ("/light", "/medium", "/expensive"):
        pair = [e for e in comparison_entries if e["endpoint"] == endpoint]
        if len(pair) != 2 or {e["replicate"] for e in pair} != {"A", "B"}:
            raise ValueError(f"Endpoint pairing incomplete: {endpoint}")
        if pair[0]["aggregate_rps"] != pair[1]["aggregate_rps"]:
            raise ValueError(f"Endpoint pair offered rates differ: {endpoint}")
    for output in plan["comparison_outputs"].values():
        if output in output_paths:
            raise ValueError(f"Comparison output collides with an entry output: {output}")
        output_paths.add(output)
        if check_outputs and (ROOT / output).exists():
            raise FileExistsError(f"Comparison output already exists: {output}")
    return {"schema_version": 1, "manifest_sha256": sha(manifest_path), "instrumentation_commit": head,
            "source_checkout": checkout_evidence,
            "configurations": len(plan["entries"]), "comparative_runs": 6, "probe_runs": 1,
            "seed_collisions": [], "outputs_absent": not any((ROOT / p).exists() for p in output_paths) if check_outputs else None,
            "docker_accessed": False, "experiments_executed": False}


def summarize(manifest_path, entry_id, destination):
    from experiments.development_d1 import summarize_entry
    plan = read(manifest_path)
    if plan.get("campaign_schema") not in {V1_SCHEMA, V2_SCHEMA, V3_SCHEMA}:
        raise ValueError("Not a D2 endpoint comparison plan")
    return summarize_entry(manifest_path, entry_id, destination)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    check = sub.add_parser("validate-plan")
    check.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    check.add_argument("--allow-existing-outputs", action="store_true")
    summary = sub.add_parser("summarize")
    summary.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    summary.add_argument("--entry", required=True)
    summary.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "validate-plan":
        result = validate_plan(args.manifest, check_outputs=not args.allow_existing_outputs)
        print(json.dumps(result))
    else:
        result = summarize(args.manifest, args.entry, args.output)
        print(json.dumps({"entry": args.entry, "summary": str(args.output),
                          "source_closed": result["d1_evidence"]["closures"],
                          "observed_drain_seconds": result["d1_evidence"]["observed_drain_seconds"]}))


if __name__ == "__main__":
    main()
