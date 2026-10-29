"""Single prospective E16 readiness/run operations; no E8 or batching. Importing this module never uses Docker.

Preflight inspects images/daemon and capture readiness, but generates no HTTP load.
Run is separate and requires an explicit entry authorization flag; never batches.
The readiness/run implementation is adapted from D1 without altering D1/D2 files.
"""
import argparse
import os
from types import SimpleNamespace
from datetime import datetime
import hashlib
import importlib
import importlib.metadata
import io
import json
import re
import signal
import socket
import subprocess
import tarfile
import time
from pathlib import Path

from experiments.development_d1_ops import (now, sha, read, put, find_entry, entry_paths,
    preflight_records, select_successful_preflight, ensure_single_experimental_attempt,
    process_rows)
from experiments.stress_e16 import ROOT, DEFAULT_MANIFEST, validate_plan, ENTRY_ID

ACTIVE_MANIFEST = DEFAULT_MANIFEST
BASE = ROOT / 'experiment_results/development-stress-e16-20261029'
REVIEWED_PREDECESSOR = None


def get_plan():
    return read(ACTIVE_MANIFEST), validate_plan(ACTIVE_MANIFEST, check_outputs=False)


def target_commit(plan):
    return plan['instrumentation_commit']


def prior_snapshot(ops):
    # Historical audit already concluded; bind only the evidence used here.
    plan=read(ACTIVE_MANIFEST)
    return {x['path']:x['sha256'] for x in plan['evidence']}


def check_predecessors(plan, index):
    if index != 0 or len(plan['entries']) != 1 or plan['entries'][0]['id'] != ENTRY_ID:
        raise ValueError('Only one prospective E16; no E8 or historical gate override')
    predecessor=read(ROOT/plan['predecessor']['path'])
    if not predecessor['operations']['cleanup_verified']:raise ValueError('E12 cleanup unverified')
    idle=time.time()-predecessor['operations']['cleanup']['observed_epoch']
    if idle<60:raise ValueError('Need >=60 seconds idle after E12 cleanup')
    return [dict(entry='stress_E12_A',review_sha256=plan['predecessor']['sha256'],idle_seconds=idle)]


def preflight(entry_id):
    plan, plan_validation = get_plan()
    entry = find_entry(plan, entry_id)
    index = plan["entries"].index(entry)
    outputs = entry_paths(entry)
    present = [str(path) for path in outputs.values() if path.exists()]
    if present:
        raise FileExistsError(f"Refusing existing entry outputs: {present}")
    predecessor_evidence = check_predecessors(plan, index)
    reference_evidence = plan['secondary_reference']
    entry_ops = BASE / "operations" / entry_id
    entry_ops.mkdir(parents=True, exist_ok=True)
    prior_reports = preflight_records(entry_ops)
    if prior_reports and time.time()-min(datetime.fromisoformat(read(p)['started_utc']).timestamp() for p in prior_reports.values()) > 600:
        raise RuntimeError('Administrative allowance exhausted; no new readiness or experiment')
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
        if subprocess.run(["git", "merge-base", "--is-ancestor", target_commit(plan), head]).returncode:
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
            raise RuntimeError("Running container found before prospective E16")
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
        from experiments.stress_e16_runtime import RESOURCE_SCRIPT, resources
        probe_container=client.containers.run(config.SOURCE_IMAGE, detach=True,
            entrypoint=['python','-c'], command=['import time; time.sleep(30)'],
            network_mode='none', restart_policy={'Name':'no'})
        created.append(probe_container)
        report['checks']['effective_resource_probe']=resources(probe_container)
        report['checks']['resource_scope']='Disposable idle process; actual victim rechecked before source release, no load.'
        probe_container.stop(timeout=2); probe_container.remove(); created.remove(probe_container)
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
    started = min(datetime.fromisoformat(read(path)['started_utc']).timestamp() for path in preflight_records(entry_ops).values())
    remaining = 1080 - (time.time() - started)
    if remaining < 480:
        raise RuntimeError('18-minute envelope lacks nominal/drain/idle reserve; do not start')
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
    image_ids = {name:readiness_client.images.get(name).id for name in ready['checks']['images']}
    readiness_client.close()
    if any(image_ids[name] != evidence['id'] for name,evidence in ready['checks']['images'].items()):
        raise RuntimeError('Image identity changed after the selected preflight')
    if active_containers:
        raise RuntimeError(f"Running containers found immediately before run: {active_containers}")
    try:
        probe = socket.socket()
        probe.bind(("127.0.0.1", 8080))
        probe.close()
    except OSError as exc:
        raise RuntimeError("Port 8080 is not free immediately before run") from exc
    cmd = [".venv/bin/python", "-B", "-m", "experiments.stress_e16_runtime", "--config", entry["config"],
           "--output", entry["outputs"]["raw"], "--dataset-output", entry["outputs"]["dataset"]]
    put(entry_ops / "attempt.json", {"command": cmd, "invoked_utc": now(), "invoked_epoch": time.time(),
        "attempt_number": 1, "automatic_retry": False, "authorization_scope": entry_id,
        "manifest_sha256": sha(ACTIVE_MANIFEST), "preflight_id": preflight_id,
        "preflight_path": str(preflight_path.relative_to(ROOT)), "preflight_sha256": sha(preflight_path),
        "effective_checkout_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "approved_source_hashes": current_tool_hashes})
    with (entry_ops / "execution.log").open("x") as stream:
        started = time.monotonic()
        process=subprocess.Popen(cmd, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            process.wait(timeout=max(420,remaining-100))
        except subprocess.TimeoutExpired:
            os.killpg(process.pid,signal.SIGINT)
            try: process.wait(timeout=35)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=5)
        result=SimpleNamespace(returncode=process.returncode)
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
    print(json.dumps(dict(entry=entry_id,returncode=execution['returncode'],attempts_remaining=0,execution_result=str(entry_ops/'execution_result.json'))))
    if result.returncode:
        raise SystemExit(result.returncode)


def main():
    global REVIEWED_PREDECESSOR
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--predecessor-review-sha256')
    sub = parser.add_subparsers(dest='action', required=True)
    for action in ('preflight', 'run'):
        command = sub.add_parser(action)
        command.add_argument('--entry', required=True, choices=(ENTRY_ID,))
        if action == 'run':
            command.add_argument('--preflight-id', required=True)
            command.add_argument('--authorize-entry', required=True)
    args = parser.parse_args()
    REVIEWED_PREDECESSOR = args.predecessor_review_sha256
    if args.action == 'preflight':
        preflight(args.entry)
    else:
        if args.authorize_entry != args.entry:
            raise ValueError('Authorization must name exactly the selected pilot')
        run_entry(args.entry, args.preflight_id)


if __name__ == '__main__':
    main()
