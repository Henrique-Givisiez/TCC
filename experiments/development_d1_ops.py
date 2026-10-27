"""Single-entry DEVELOPMENT D1 operations; never batches or retries runs.

Examples:
  python -m experiments.development_d1_ops preflight --entry d1_L03_A
  python -m experiments.development_d1_ops run --entry d1_L03_A --preflight-id pf-0001
  python -m experiments.development_d1_ops postprocess --entry d1_L03_A
  python -m experiments.development_d1_ops review --entry d1_L03_A
  python -m experiments.development_d1_ops pair-review --level L03

Every command is exclusive and entry-scoped. `run` only invokes one manifest
entry. Pair review never starts an experiment.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib
import importlib.metadata
import io
import json
import os
import re
import signal
import socket
import subprocess
import sys
import tarfile
import time
from pathlib import Path

ROOT = Path.cwd()
BASE = ROOT / "experiment_results/development-d1-20261027"
MANIFEST = ROOT / "experiments/protocols/development_d1_20261027/manifest.json"
CONTINUATION_V1 = ROOT / "experiments/protocols/development_d1_20261027/continuation_capturefix_v1.json"
CONTINUATION = ROOT / "experiments/protocols/development_d1_20261027/continuation_capturefix_v2.json"
D2_MANIFEST_V1 = ROOT / "experiments/protocols/development_d2_endpoint_comparison_20261027/manifest.json"
D2_MANIFEST_V2 = ROOT / "experiments/protocols/development_d2_endpoint_comparison_20261027/manifest_v2.json"
D2_MANIFEST_V3 = ROOT / "experiments/protocols/development_d2_endpoint_comparison_20261027/manifest_v3.json"
D2_MANIFEST = ROOT / "experiments/protocols/development_d2_endpoint_comparison_20261027/manifest_v4.json"
ACTIVE_MANIFEST = MANIFEST
EXPECTED_HEAD = "20bfd3fb66a6c3fe51a1fad9f11455a85dee8412"


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def put(path, obj):
    with Path(path).open("x") as stream:
        json.dump(obj, stream, indent=2, default=str, allow_nan=False)
        stream.write("\n")


def get_plan():
    plan = read(ACTIVE_MANIFEST)
    global BASE
    if plan.get("campaign_schema") in {"development-endpoint-comparison/v1", "development-endpoint-comparison/v2", "development-endpoint-comparison/v3", "development-endpoint-comparison/v4"}:
        BASE = ROOT / plan["results_root"]
        from experiments.development_d2 import validate_plan
        validation = validate_plan(ACTIVE_MANIFEST, check_outputs=False)
        return plan, validation
    if ACTIVE_MANIFEST == CONTINUATION:
        parent_path = ROOT / plan["parent_manifest_path"]
        parent = read(parent_path)
        if sha(parent_path) != plan["parent_manifest_sha256"]:
            raise ValueError("Parent continuation manifest hash mismatch")
        if sha(ROOT / plan["diagnosis_path"]) != plan["diagnosis_sha256"]:
            raise ValueError("Capture diagnosis hash mismatch")
        current_head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
        if current_head != plan["instrumentation_commit"]:
            raise ValueError("Current HEAD differs from continuation's recorded instrumentation commit")
        if plan.get("maximum_attempts") != 11:
            raise ValueError("Unexpected continuation attempt budget")
        for path, expected in plan["runtime_source_hashes"].items():
            if sha(ROOT / path) != expected:
                raise ValueError(f"Continuation code hash mismatch: {path}")
        entries = plan["entries"]
        if [e["id"] for e in entries] != ["d1_L04_B_CF1", "d1_L04_A", "d1_L05_A", "d1_L05_B"]:
            raise ValueError("Continuation entries or order changed")
        if plan["pairing"]["L04"] != {"A": "d1_L04_A", "B": "d1_L04_B_CF1", "excluded_historical_attempt": "d1_L04_B"}:
            raise ValueError("L04 pair does not bind the accepted replacement B")
        base = read(MANIFEST)
        v1_path = ROOT / plan["parent_manifest_path"]
        if v1_path != CONTINUATION_V1 or parent.get("continuation_schema") != "development-d1-continuation/v1":
            raise ValueError("Unexpected parent continuation")
        for entry in entries:
            if sha(ROOT / entry["config"]) != entry["config_sha256"]:
                raise ValueError(f"Configuration hash mismatch: {entry['id']}")
            cfg = read(ROOT / entry["config"])
            if cfg != entry["effective_configuration"]:
                raise ValueError(f"Effective configuration mismatch: {entry['id']}")
            from simulator.experiment_config import ExperimentConfig
            ExperimentConfig.load(ROOT / entry["config"])
            if entry["id"] == "d1_L04_B_CF1":
                old = find_entry(base, "d1_L04_B")["effective_configuration"]
                if {**old, "id": cfg["id"]} != cfg or cfg["seed"] != 3803721254044484793:
                    raise ValueError("Accepted L04/B representative changed beyond its new ID/seed")
            else:
                historical = find_entry(base, entry["id"])
                if historical["config_sha256"] != entry["config_sha256"] or historical["effective_configuration"] != cfg:
                    raise ValueError(f"Historical config/seed changed: {entry['id']}")
        old_failure = read(BASE / "analysis/d1_L04_B-review.json")
        if old_failure["decision"].get("d1_L04_B_all_criteria_pass") is not False:
            raise ValueError("Original L04/B technical failure was reclassified")
        accepted_b = read(BASE / "analysis/d1_L04_B_CF1-review.json")
        if accepted_b["authority"]["manifest_sha256"] != plan["representative_b"]["manifest_sha256"]:
            raise ValueError("L04/B representative review manifest binding changed")
        if sha(BASE / "analysis/d1_L04_B_CF1-review.json") != plan["representative_b"]["review_sha256"]:
            raise ValueError("L04/B representative review hash mismatch")
        if not all(c["passed"] for c in accepted_b["criteria"]):
            raise ValueError("L04/B representative review is no longer accepted")
        reference = read(BASE / "analysis/d1_L01_reference.json")
        if reference["p95_ref_ms"] != plan["fixed_reference"]["p95_ref_ms"] or reference["next_levels_duration_limit_ms"] != plan["fixed_reference"]["progression_limit_ms"]:
            raise ValueError("Fixed L01 reference changed")
        ids = [e["id"] for e in entries]
        paths = [str(path) for e in entries for path in entry_paths(e).values()]
        if len(paths) != len(set(paths)):
            raise ValueError("Continuation output paths collide")
        if not all(e["outputs"]["raw"].endswith(e["id"]) for e in entries):
            raise ValueError("Entry output identities do not match IDs")
        return plan, {"manifest_sha256": sha(CONTINUATION), "parent_manifest_sha256": sha(parent_path),
                      "instrumentation_commit": current_head, "bound_parent": True, "entry_ids": ids,
                      "accepted_representative_b": True, "historical_failure_preserved": True}
    if ACTIVE_MANIFEST == CONTINUATION_V1:
        parent = read(MANIFEST)
        if sha(MANIFEST) != plan["parent_manifest_sha256"]:
            raise ValueError("Parent manifest hash mismatch")
        if sha(ROOT / plan["diagnosis_path"]) != plan["diagnosis_sha256"]:
            raise ValueError("Capture diagnosis hash mismatch")
        if plan.get("maximum_attempts") != 11:
            raise ValueError("Unexpected continuation attempt budget")
        for path, expected in plan["runtime_source_hashes"].items():
            if sha(ROOT / path) != expected:
                raise ValueError(f"Continuation code hash mismatch: {path}")
        entry = find_entry(plan, "d1_L04_B_CF1")
        if sha(ROOT / entry["config"]) != entry["config_sha256"]:
            raise ValueError("Replacement configuration hash mismatch")
        config = read(ROOT / entry["config"])
        original = find_entry(parent, "d1_L04_B")["effective_configuration"]
        if {**original, "id": config["id"]} != config:
            raise ValueError("Replacement config changed fields beyond its new ID")
        if config["seed"] != 3803721254044484793:
            raise ValueError("Replacement no longer retains replicate B seed")
        previous = read(ROOT / "experiment_results/development-d1-20261027/analysis/d1_L04_B-review.json")
        if previous["decision"].get("d1_L04_B_all_criteria_pass") is not False:
            raise ValueError("Historical failed L04/B classification changed")
        return plan, {"manifest_sha256": sha(CONTINUATION), "parent_manifest_sha256": sha(MANIFEST),
                      "bound_parent": True, "entry_count": len(plan["entries"])}
    from experiments.development_d1 import validate_plan
    validation = validate_plan(MANIFEST, check_outputs=False)
    if validation["manifest_sha256"] != sha(MANIFEST):
        raise ValueError("Manifest hash changed during validation")
    return plan, validation


def find_entry(plan, entry_id):
    matches = [entry for entry in plan["entries"] if entry["id"] == entry_id]
    if len(matches) != 1:
        raise ValueError(f"Unknown or duplicate manifest entry: {entry_id}")
    return matches[0]


def entry_paths(entry):
    return {key: ROOT / value for key, value in entry["outputs"].items()}


def check_predecessors(plan, index):
    """Require the ordered predecessor and, at level changes, its accepted pair."""
    entry = plan["entries"][index]
    if ACTIVE_MANIFEST == CONTINUATION_V1 and entry_id_is_replacement(entry):
        prior = BASE / "analysis/d1_completed_runs_through_L04B_attempt.json"
        if not prior.is_file():
            raise ValueError("Missing historical completed-runs evidence")
        return [{"entry": "d1_L04_B", "review_sha256": sha(BASE / "analysis/d1_L04_B-review.json"),
                 "classification": "preserved_technical_failure_not_eligible"},
                {"prior_completed_runs_sha256": sha(prior), "accepted_through": "L03 A/B"}]
    if index == 0:
        return []
    previous = plan["entries"][index - 1]
    review_path = ROOT / previous["outputs"]["review"]
    if not review_path.is_file():
        raise ValueError(f"Missing accepted review for immediate predecessor {previous['id']}")
    review = read(review_path)
    failed = [criterion["name"] for criterion in review["criteria"] if not criterion["passed"]]
    if failed:
        raise ValueError(f"Predecessor failed criteria: {failed}")
    evidence = [{"entry": previous["id"], "review_sha256": sha(review_path), "all_criteria_pass": True}]
    if entry["level"] != previous["level"]:
        pair_path = BASE / "analysis" / f"d1_L{previous['level']:02d}_pair_review.json"
        if not pair_path.is_file():
            raise ValueError(f"Missing accepted pair review for level L{previous['level']:02d}")
        pair = read(pair_path)
        if not pair.get("replicas_accepted", pair.get("L02_A_and_B_all_criteria_pass", False)):
            raise ValueError(f"Pair review rejected level L{previous['level']:02d}")
        evidence.append({"pair": f"L{previous['level']:02d}", "review_sha256": sha(pair_path), "accepted": True})
    return evidence


def entry_id_is_replacement(entry):
    return entry.get("replacement_of") == "d1_L04_B"


def target_commit(plan):
    if plan.get("continuation_schema") == "development-d1-continuation/v2" or plan.get("campaign_schema") in {"development-endpoint-comparison/v1", "development-endpoint-comparison/v2", "development-endpoint-comparison/v3", "development-endpoint-comparison/v4"}:
        return plan["instrumentation_commit"]
    return EXPECTED_HEAD


def preflight_records(entry_ops):
    records = {}
    legacy = entry_ops / "preflight.json"
    if legacy.is_file():
        records["pf-0001"] = legacy
    for directory in entry_ops.glob("pf-[0-9][0-9][0-9][0-9]"):
        report = directory / "report.json"
        if report.is_file():
            records[directory.name] = report
    return records


def resolve_preflight(entry_ops, preflight_id):
    if not preflight_id or not re.fullmatch(r"pf-[0-9]{4}", preflight_id):
        raise ValueError("Select an explicit preflight id (for example pf-0002)")
    records = preflight_records(entry_ops)
    if preflight_id not in records:
        raise FileNotFoundError(f"No report for selected preflight {preflight_id}")
    return records[preflight_id]


def select_successful_preflight(entry_ops, preflight_id, entry_id, authority_sha256):
    path = resolve_preflight(entry_ops, preflight_id)
    report = read(path)
    if (not report.get("ready") or report.get("preflight_id") != preflight_id
            or report.get("approved_entry") != entry_id
            or report.get("manifest_sha256") != authority_sha256):
        raise RuntimeError("Selected preflight is not a successful match for this entry and authority")
    return path, report


def ensure_single_experimental_attempt(entry_ops):
    if (entry_ops / "attempt.json").exists():
        raise RuntimeError("Attempt record exists; retries are forbidden")


def prior_snapshot(ops):
    files = {}
    for path in BASE.rglob("*"):
        if path.is_file() and ops not in path.parents:
            files[str(path.relative_to(ROOT))] = sha(path)
    return files


def process_rows():
    rows = subprocess.check_output(["ps", "-eo", "pid=,comm=,args="], text=True).splitlines()
    found = []
    for row in rows:
        fields = row.strip().split(None, 2)
        if len(fields) != 3:
            continue
        _, comm, args = fields
        if comm == "tcpdump" or ("python" in comm and any(token in args for token in (
            "-m simulator.", "-m experiments.dataset_run", "-m experiments.stage14",
            "-m pilot_stage13.", "source_runner", "simple_server.py"))):
            found.append(row)
    return found


def preflight(entry_id):
    plan, plan_validation = get_plan()
    entry = find_entry(plan, entry_id)
    index = plan["entries"].index(entry)
    outputs = entry_paths(entry)
    present = [str(path) for path in outputs.values() if path.exists()]
    if present:
        raise FileExistsError(f"Refusing existing entry outputs: {present}")
    predecessor_evidence = check_predecessors(plan, index)
    reference_path = BASE / "analysis/d1_L01_reference.json"
    if plan.get("campaign_schema") in {"development-endpoint-comparison/v1", "development-endpoint-comparison/v2", "development-endpoint-comparison/v3", "development-endpoint-comparison/v4"}:
        reference = None
        reference_evidence = None
    else:
        reference = read(reference_path)
        if reference["p95_ref_ms"] != "56.79376310008592650" or reference["next_levels_duration_limit_ms"] != "250":
            raise ValueError("L01 service reference or progression ceiling changed")
        reference_evidence = {"path": str(reference_path.relative_to(ROOT)), "sha256": sha(reference_path),
            "p95_ref_ms": reference["p95_ref_ms"], "limit_ms": reference["next_levels_duration_limit_ms"]}
    entry_ops = BASE / "operations" / entry_id
    entry_ops.mkdir(parents=True, exist_ok=True)
    if (entry_ops / "attempt.json").exists():
        raise RuntimeError("Experimental attempt already exists; no retry is permitted")
    known = set(preflight_records(entry_ops)) | {p.name for p in entry_ops.glob("pf-[0-9][0-9][0-9][0-9]")}
    number = max([int(re.search(r"[0-9]{4}$", item).group()) for item in known] or [0]) + 1
    preflight_id = f"pf-{number:04d}"
    ops = entry_ops / preflight_id
    ops.mkdir(parents=False, exist_ok=False)
    report_path = ops / "report.json"
    previous_files = prior_snapshot(ops)
    put(ops / "previous_hashes.json", previous_files)
    put(ops / "preparation.json", {"entry": entry_id, "preflight_id": preflight_id, "observed_utc": now(), "previous_file_count": len(previous_files)})
    report = {"preflight_id": preflight_id, "manifest_sha256": sha(ACTIVE_MANIFEST), "started_utc": now(), "scope": "Readiness only; no scientific request generation", "approved_entry": entry_id,
              "approved_commit": target_commit(plan), "effective_checkout_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(), "checks": {"plan": plan_validation,
              "outputs_absent": {key: not path.exists() for key, path in outputs.items()},
              "predecessors": predecessor_evidence,
              "service_reference": reference_evidence}}
    recovery_entry = plan["entries"][index - 1] if index else None
    if ACTIVE_MANIFEST == CONTINUATION_V1 and entry_id_is_replacement(entry):
        recovery_entry = find_entry(read(MANIFEST), "d1_L04_B")
    clients = []
    created = []
    try:
        if recovery_entry:
            previous_review = read(ROOT / recovery_entry["outputs"]["review"])
            idle = time.time() - previous_review["timing"]["cleanup_observation"]["epoch"]
            report["checks"]["recovery"] = {"previous_entry": recovery_entry["id"],
                "elapsed_seconds_at_preflight": idle, "minimum_seconds": 60, "passed": idle >= 60}
            if idle < 60:
                raise RuntimeError(f"Recovery interval not satisfied: {idle:.3f}s < 60s")
        if any(not value for value in report["checks"]["outputs_absent"].values()):
            raise ValueError("Selected entry output already exists")
        if any(sha(ROOT / path) != digest for path, digest in previous_files.items()):
            raise ValueError("Prior evidence changed after snapshot")
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
        report["checks"]["head"] = head
        if head != target_commit(plan) and plan.get("campaign_schema") not in {"development-endpoint-comparison/v1", "development-endpoint-comparison/v2", "development-endpoint-comparison/v3", "development-endpoint-comparison/v4"}:
            raise ValueError(f"Expected checkout {target_commit(plan)}, got {head}")
        report["checks"]["git_status"] = subprocess.check_output(["git", "status", "--short"], text=True)
        cfg = ROOT / entry["config"]
        report["checks"]["config_sha256"] = sha(cfg)
        if report["checks"]["config_sha256"] != entry["config_sha256"]:
            raise ValueError("Manifest-bound configuration hash mismatch")
        report["checks"]["operational_code_sha256"] = {
            **plan.get("runtime_source_hashes", {}),
            "experiments/development_d1_ops.py": sha(ROOT / "experiments/development_d1_ops.py"),
            "experiments/development_d1_review.py": sha(ROOT / "experiments/development_d1_review.py")}
        from simulator import config
        for module in ("docker", "requests", "numpy", "pandas", "scipy", "matplotlib", "openpyxl"):
            importlib.import_module(module)
        report["checks"]["dependencies"] = {m: importlib.metadata.version(m) for m in
            ("docker", "requests", "numpy", "pandas", "scipy", "matplotlib", "openpyxl")}
        pip = subprocess.run([".venv/bin/python", "-m", "pip", "check"], text=True, capture_output=True)
        report["checks"]["pip_check"] = {"returncode": pip.returncode, "stdout": pip.stdout, "stderr": pip.stderr}
        if pip.returncode:
            raise RuntimeError("pip check failed")
        competing = process_rows()
        report["checks"]["competing_processes"] = competing
        if competing:
            raise RuntimeError("Competing simulator/capture process found")
        import docker
        client = docker.DockerClient(base_url=config.DOCKER_ENGINE_SOCKET)
        report["checks"]["docker_version"] = client.version()
        containers = client.containers.list(all=True)
        report["checks"]["containers_before"] = [{"id": c.id, "name": c.name, "status": c.status} for c in containers]
        if any(c.status == "running" for c in containers):
            raise RuntimeError("Running container found before D1")
        image_names = (config.DOCKER_IMAGE_NAME, config.SOURCE_IMAGE, config.PROXY_IMAGE + "@" + config.PROXY_IMAGE_DIGEST)
        report["checks"]["images"] = {name: {"id": client.images.get(name).id,
            "repo_digests": client.images.get(name).attrs.get("RepoDigests", [])} for name in image_names}
        source_map = {"__init__.py", "experiment_config.py", "service_destination.py", "ground_truth.py", "request_logger.py",
                      "normal_traffic.py", "traffic_injectorV0.py", "normal_traffic_summary_logger.py", "attack_summary_logger.py",
                      "source_journal.py", "source_runner.py", "attack_patterns.py"}
        checks = []
        image_files = [(config.DOCKER_IMAGE_NAME, {"simple_server.py": ROOT / "simulator/app/simple_server.py"})]
        image_files.append((config.SOURCE_IMAGE, {f"simulator/{p.name}": p for p in (ROOT / "simulator").glob("*.py") if p.name in source_map}))
        for image, mapping in image_files:
            for remote, local in mapping.items():
                container = client.containers.create(image)
                created.append(container)
                chunks, _ = container.get_archive("/app/" + remote)
                with tarfile.open(fileobj=io.BytesIO(b"".join(chunks))) as archive:
                    payload = archive.extractfile(archive.getmembers()[0]).read()
                checks.append({"image": image, "path": remote, "image_sha256": hashlib.sha256(payload).hexdigest(),
                               "host_sha256": sha(local), "match": hashlib.sha256(payload).hexdigest() == sha(local)})
                container.remove()
                created.remove(container)
        report["checks"]["image_source_files"] = checks
        if not checks or not all(item["match"] for item in checks):
            raise RuntimeError("Image source differs from checkout")
        sock = socket.socket()
        try:
            sock.bind(("127.0.0.1", 8080))
        finally:
            sock.close()
        report["checks"]["port_8080_free"] = True
        report["checks"]["tcpdump_capabilities"] = subprocess.check_output(["getcap", "/usr/bin/tcpdump"], text=True)
        capture_path = ops / "capture_readiness.pcap"
        with (ops / "capture_readiness.stderr").open("x") as stderr:
            capture = subprocess.Popen(["tcpdump", "--immediate-mode", "-i", "lo", "-p", "-nn", "-w", str(capture_path),
                                        "tcp and port 1"], stdout=subprocess.DEVNULL, stderr=stderr)
            time.sleep(1)
            if capture.poll() is None:
                capture.send_signal(signal.SIGINT)
            rc = capture.wait(timeout=5)
        diagnostic = (ops / "capture_readiness.stderr").read_text()
        report["checks"]["capture"] = {"returncode": rc, "diagnostic": diagnostic, "probe_traffic_generated": False}
        if rc or "listening on" not in diagnostic:
            raise RuntimeError("Capture readiness failed")
        report["ready"] = True
        report["report_path"] = str(report_path.relative_to(ROOT))
    except BaseException as exc:
        report["ready"] = False
        report["error"] = repr(exc)
        raise
    finally:
        for container in created:
            try:
                container.remove()
            except Exception as exc:
                report.setdefault("inspection_cleanup_errors", []).append(repr(exc))
        if clients:
            pass
        if "client" in locals():
            client.close()
        report["finished_utc"] = now()
        report["report_path"] = str(report_path.relative_to(ROOT))
        put(report_path, report)
    print(json.dumps({"entry": entry_id, "preflight_id": preflight_id, "ready": report.get("ready"), "report": str(report_path)}))


def run_entry(entry_id, preflight_id):
    plan, _ = get_plan()
    entry = find_entry(plan, entry_id)
    index = plan["entries"].index(entry)
    entry_ops = BASE / "operations" / entry_id
    preflight_path, ready = select_successful_preflight(entry_ops, preflight_id, entry_id, sha(ACTIVE_MANIFEST))
    if ready["approved_commit"] != target_commit(plan):
        raise RuntimeError("Selected preflight code authority differs from this manifest")
    ops = entry_ops / preflight_id
    current_tool_hashes = {path: sha(ROOT / path) for path in ready["checks"].get("operational_code_sha256", {})}
    if current_tool_hashes != ready["checks"].get("operational_code_sha256", {}):
        raise RuntimeError("Operational utility changed after preflight")
    check_predecessors(plan, index)
    for path in entry_paths(entry).values():
        if path.exists():
            raise FileExistsError(f"Refusing existing output {path}")
    previous_files = read(ops / "previous_hashes.json")
    changed = [p for p, digest in previous_files.items() if sha(ROOT / p) != digest]
    if changed:
        raise RuntimeError(f"Prior artifact hash mismatch: {changed[:5]}")
    ensure_single_experimental_attempt(entry_ops)
    previous = plan["entries"][index - 1] if index else None
    if ACTIVE_MANIFEST == CONTINUATION_V1 and entry_id_is_replacement(entry):
        previous = find_entry(read(MANIFEST), "d1_L04_B")
    if previous:
        prior_review = read(ROOT / previous["outputs"]["review"])
        elapsed = time.time() - prior_review["timing"]["cleanup_observation"]["epoch"]
        if elapsed < 60:
            raise RuntimeError(f"Recovery interval not satisfied: {elapsed:.3f}s < 60s")
    active = process_rows()
    if active:
        raise RuntimeError(f"Competing simulator/capture process found immediately before run: {active}")
    import docker
    from simulator import config
    readiness_client = docker.DockerClient(base_url=config.DOCKER_ENGINE_SOCKET)
    active_containers = [c.id for c in readiness_client.containers.list(all=True) if c.status == "running"]
    readiness_client.close()
    if active_containers:
        raise RuntimeError(f"Running containers found immediately before run: {active_containers}")
    try:
        probe = socket.socket()
        probe.bind(("127.0.0.1", 8080))
        probe.close()
    except OSError as exc:
        raise RuntimeError("Port 8080 is not free immediately before run") from exc
    cmd = [".venv/bin/python", "-B", "-m", "experiments.dataset_run", "--config", entry["config"],
           "--output", entry["outputs"]["raw"], "--dataset-output", entry["outputs"]["dataset"]]
    put(entry_ops / "attempt.json", {"command": cmd, "invoked_utc": now(), "invoked_epoch": time.time(),
        "attempt_number": 1, "automatic_retry": False, "authorization_scope": entry_id,
        "manifest_sha256": sha(ACTIVE_MANIFEST), "preflight_id": preflight_id,
        "preflight_path": str(preflight_path.relative_to(ROOT)), "preflight_sha256": sha(preflight_path),
        "effective_checkout_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "approved_source_hashes": current_tool_hashes})
    with (entry_ops / "execution.log").open("x") as stream:
        started = time.monotonic()
        result = subprocess.run(cmd, stdout=stream, stderr=subprocess.STDOUT)
    execution = {"returncode": result.returncode, "command_return_observed_utc": now(),
                 "command_return_observed_epoch": time.time(), "wall_seconds": time.monotonic() - started}
    put(entry_ops / "execution_result.json", execution)
    client = docker.DockerClient(base_url=config.DOCKER_ENGINE_SOCKET)
    containers = [{"id": c.id, "name": c.name, "status": c.status} for c in client.containers.list(all=True)]
    port = subprocess.run(["ss", "-ltn", "sport = :8080"], text=True, capture_output=True)
    cleanup = {"observed_utc": now(), "observed_epoch": time.time(), "containers": containers,
               "matching_processes": process_rows(), "port_8080": port.stdout, "port_check_returncode": port.returncode,
               "no_active_containers": not any(c["status"] == "running" for c in containers)}
    cleanup["no_scientific_processes"] = not cleanup["matching_processes"]
    put(entry_ops / "cleanup_observation.json", cleanup)
    client.close()
    print(json.dumps(execution))
    if result.returncode:
        raise SystemExit(result.returncode)


def postprocess(entry_id):
    plan, _ = get_plan()
    entry = find_entry(plan, entry_id)
    ops = BASE / "operations" / entry_id
    if not (ops / "execution_result.json").is_file():
        raise RuntimeError("No completed attempt")
    records = []
    commands = [
        [".venv/bin/python", "-B", "-m", "experiments.validate_dataset", entry["outputs"]["dataset"],
         "--output", entry["outputs"]["validation"]],
        [".venv/bin/python", "-B", "-m", "experiments.development_d1", "summarize", "--manifest",
         str(ACTIVE_MANIFEST.relative_to(ROOT)), "--entry", entry_id,
         "--output", entry["outputs"]["analysis"]]
    ]
    if (ops / "postprocess.json").exists():
        raise RuntimeError("Postprocess record exists; no automatic retry")
    for label, command in zip(("dataset_validation", "service_summary"), commands):
        log = ops / f"{label}.log"
        with log.open("x") as stream:
            started = now()
            result = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT)
        records.append({"command": command, "returncode": result.returncode, "started_utc": started, "finished_utc": now()})
        if result.returncode:
            break
    put(ops / "postprocess.json", records)
    print(json.dumps({"entry": entry_id, "commands": records}))
    if any(item["returncode"] for item in records):
        raise SystemExit(1)


def review_entry(entry_id):
    command = [".venv/bin/python", "-B", "-m", "experiments.development_d1_review", "--manifest",
               str(ACTIVE_MANIFEST.relative_to(ROOT)), "--entry", entry_id]
    subprocess.run(command, check=True)


def pair_review(level, dry_run=False):
    plan, _ = get_plan()
    number = int(level.removeprefix("L"))
    entries = [e for e in plan["entries"] if e["level"] == number]
    if len(entries) != 2 or {e["replicate"] for e in entries} != {"A", "B"}:
        raise ValueError(f"Expected exactly A/B entries for L{number:02d}")
    entries.sort(key=lambda e: e["replicate"])
    reviews = {e["id"]: read(ROOT / e["outputs"]["review"]) for e in entries}
    checks = {key: all(c["passed"] for c in value["criteria"]) for key, value in reviews.items()}
    accepted = all(checks.values())
    next_entries = [e for e in plan["entries"] if e["level"] == number + 1]
    next_entry = min(next_entries, key=lambda e: e["order"]) if next_entries else None
    output = BASE / "analysis" / f"d1_L{number:02d}_pair_review.json"
    pair_markdown = BASE / "analysis" / f"d1_L{number:02d}_pair_review.md"
    cumulative_json = BASE / "analysis" / f"d1_completed_runs_after_L{number:02d}.json"
    cumulative_md = BASE / "analysis" / f"d1_completed_runs_after_L{number:02d}.md"
    if not dry_run and any(path.exists() for path in (output, pair_markdown, cumulative_json, cumulative_md)):
        raise FileExistsError("Pair review output exists; never overwrite")
    reference_path = BASE / "analysis/d1_L01_reference.json"
    reference = read(reference_path)
    if reference["p95_ref_ms"] != "56.79376310008592650" or reference["next_levels_duration_limit_ms"] != "250":
        raise ValueError("L01 reference changed; stop progression")
    def metrics(review):
        service = review["service"]
        victim, proxy = review["resources"]["victim"], review["resources"]["proxy"]
        duration = service["success_duration_2xx_ms"]
        return {"nominal_rps": service["nominal_aggregate_rps"], "starts": service["useful_starts"], "effective_rps": service["effective_aggregate_rps"],
            "adherence": service["adherence"], "success_2xx": service["cohort_outcomes"]["success_2xx"],
            "http_failures": service["cohort_outcomes"]["http_error"], "transport_failures": service["cohort_outcomes"]["transport_error"],
            "client_failures": service["cohort_outcomes"]["client_error"], "other_responses": service["cohort_outcomes"]["other_response"],
            "incomplete": service["incomplete_no_end"], "duration_support": duration["n"], "mean_ms": duration["mean"],
            "p50_ms": duration["p50"], "p95_ms": duration["p95"], "victim_cpu_mean": victim["cpu_docker_percent"]["mean"],
            "victim_memory_application_mib": victim["memory_application_mib"]["mean"],
            "victim_support": f"{victim['supported_useful_ticks']}/{victim['expected_useful_ticks']}",
            "proxy_cpu_mean": proxy["sources"]["docker"]["cpu_docker_percent"]["mean"],
            "proxy_memory_raw_bytes": proxy["sources"]["docker"]["memory_raw_bytes"]["mean"],
            "proxy_status_support": f"{proxy['sources']['status']['successful_useful']}/{proxy['sources']['status']['attempted_useful']}",
            "proxy_docker_support": f"{proxy['sources']['docker']['successful_useful']}/{proxy['sources']['docker']['attempted_useful']}",
            "drain_seconds": review["timing"]["drain_observed_seconds"]}
    pair_metrics = {key: metrics(value) for key, value in reviews.items()}
    report = {"schema_version": 1, "created_utc": now(), "level": f"L{number:02d}",
              "replica_reviews": {key: str(next(e["outputs"]["review"] for e in entries if e["id"] == key)) for key in reviews},
              "replicas_accepted": accepted, "criteria": checks, "replica_metrics": pair_metrics,
              "next_entry": next_entry["id"] if next_entry else None,
              "next_entry_permitted_after_readiness": bool(accepted and next_entry),
              "service_reference": {"path": str(reference_path.relative_to(ROOT)), "sha256": sha(reference_path),
                  "p95_ref_ms": reference["p95_ref_ms"], "limit_ms": reference["next_levels_duration_limit_ms"]},
              "reference_unchanged": True,
              "interpretation": "Pairing by replicate label or seed does not assert identical request trajectories. Memory differences are descriptive and not attributed automatically to rate or seed."}
    if not dry_run:
        put(output, report)
    cumulative = []
    for candidate in plan["entries"]:
        path = ROOT / candidate["outputs"]["review"]
        if path.is_file():
            review = read(path)
            cumulative.append({"entry": candidate["id"], "seed": candidate["effective_configuration"]["seed"],
                               **metrics(review)})
    if not dry_run:
        put(cumulative_json, {"schema_version": 1, "created_utc": now(), "runs": cumulative,
                    "service_reference": report["service_reference"], "memory_interpretation": report["interpretation"]})
    columns = ("entry", "nominal_rps", "starts", "effective_rps", "adherence", "success_2xx",
               "http_failures", "transport_failures", "client_failures", "incomplete", "mean_ms", "p50_ms", "p95_ms",
               "victim_cpu_mean", "victim_memory_application_mib", "proxy_cpu_mean", "proxy_memory_raw_bytes",
               "victim_support", "proxy_status_support", "proxy_docker_support", "drain_seconds")
    lines = [f"# D1 — runs concluídos até L{number:02d}", "",
             f"Referência p95_ref={reference['p95_ref_ms']} ms; teto={reference['next_levels_duration_limit_ms']} ms. Ambos permanecem fixos.",
             "", "| " + " | ".join(columns) + " |", "|" + "---|" * len(columns)]
    for run in cumulative:
        lines.append("| " + " | ".join(str(run.get(column, "")) for column in columns) + " |")
    lines += ["", "Memória vítima é métrica de aplicação com subtração de cache; proxy é memória bruta incluindo cache. CPU da vítima é agregada/cached; proxy inclui custo do monitor. Não atribuir diferenças automaticamente à taxa ou seed.",
              "Pareamento por seed não implica trajetórias temporais idênticas. Revisões completas estão nos relatórios por execução."]
    if not dry_run:
        with cumulative_md.open("x") as stream:
            stream.write("\n".join(lines) + "\n")
        pair_lines = [f"# D1 — comparação do par L{number:02d}", "",
                      f"Ambas as revisões passam: {accepted}. Próxima entrada ordenada: {report['next_entry'] or 'nenhuma'}.",
                      f"Referência fixa: p95_ref={reference['p95_ref_ms']} ms; teto={reference['next_levels_duration_limit_ms']} ms.",
                      "", "| Medida | A | B |", "|---|---:|---:|"]
        for key in pair_metrics[entries[0]["id"]]:
            pair_lines.append(f"| {key} | {pair_metrics[entries[0]['id']][key]} | {pair_metrics[entries[1]['id']][key]} |")
        pair_lines += ["", report["interpretation"],
                       "CPU vítima é agregada/cached; proxy inclui custo do monitor. Memória vítima subtrai cache; memória bruta do proxy inclui cache."]
        with pair_markdown.open("x") as stream:
            stream.write("\n".join(pair_lines) + "\n")
    print(json.dumps({"dry_run": dry_run, "pair": f"L{number:02d}", "accepted": accepted,
                      "next_entry": report["next_entry"], "permitted": report["next_entry_permitted_after_readiness"],
                      "metrics": pair_metrics}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", choices=(str(MANIFEST.relative_to(ROOT)), str(CONTINUATION_V1.relative_to(ROOT)), str(CONTINUATION.relative_to(ROOT)), str(D2_MANIFEST_V1.relative_to(ROOT)), str(D2_MANIFEST_V2.relative_to(ROOT)), str(D2_MANIFEST_V3.relative_to(ROOT)), str(D2_MANIFEST.relative_to(ROOT))),
                        default=str(MANIFEST.relative_to(ROOT)))
    sub = parser.add_subparsers(dest="action", required=True)
    for action in ("preflight", "run", "postprocess", "review"):
        command = sub.add_parser(action)
        command.add_argument("--entry", required=True)
        if action == "run":
            command.add_argument("--preflight-id", required=True, help="Successful readiness report to bind to this one attempt")
    pair = sub.add_parser("pair-review")
    pair.add_argument("--level", required=True)
    pair.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    global ACTIVE_MANIFEST
    ACTIVE_MANIFEST = ROOT / args.manifest
    if args.action == "preflight":
        preflight(args.entry)
    elif args.action == "run":
        run_entry(args.entry, args.preflight_id)
    elif args.action == "postprocess":
        postprocess(args.entry)
    elif args.action == "review":
        review_entry(args.entry)
    else:
        pair_review(args.level, args.dry_run)


if __name__ == "__main__":
    main()
