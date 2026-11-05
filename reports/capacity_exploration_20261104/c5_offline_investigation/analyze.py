"""Read-only reconstruction of the existing C3/C5/P5 capacity artifacts."""
from __future__ import annotations

import csv
import hashlib
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path("experiment_results/capacity-exploration-20261104")
OUT = Path("reports/capacity_exploration_20261104/c5_offline_investigation")
RUNS = ("C3_ON_r1", "C3_OFF_r1", "C5_ON_r1", "P5_128rps")
DIAGNOSTIC_RUNS = ("C3_ON_r1", "C5_ON_r1", "P5_128rps")

def generation_duration(run):
    """Configured generation horizon; pilot P5 is 12 s, main runs are 20 s."""
    return float(run["config"]["duration_seconds"])


def read_json(path):
    return json.loads(Path(path).read_text())


def jsonl(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def csv_rows(path):
    with Path(path).open(newline="") as stream:
        return list(csv.DictReader(stream))


def write_csv(path, rows):
    rows = list(rows)
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with Path(path).open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def stats(values):
    vals = sorted(float(v) for v in values if v is not None and math.isfinite(float(v)))
    n = len(vals)
    return {
        "n": n,
        "mean": statistics.mean(vals) if n else None,
        "median": statistics.median(vals) if n else None,
        "p95": vals[max(0, math.ceil(.95 * n) - 1)] if n else None,
        "maximum": max(vals) if n else None,
        "minimum": min(vals) if n else None,
        "sample_sd": statistics.stdev(vals) if n > 1 else None,
    }


def paired_association(rows):
    pairs = [(float(r["work_wait_ms"]), float(r["duration_ms"])) for r in rows
             if r.get("work_wait_ms") is not None and r.get("duration_ms") is not None]
    waits, http = [x for x, _ in pairs], [y for _, y in pairs]
    if len(pairs) < 2:
        correlation = None
    else:
        mx, my = statistics.mean(waits), statistics.mean(http)
        sx, sy = statistics.stdev(waits), statistics.stdev(http)
        correlation = (sum((x-mx)*(y-my) for x, y in pairs) / (len(pairs)-1) / (sx*sy)) if sx and sy else None
    residual = [y-x for x, y in pairs]
    return {
        "paired_n": len(pairs), "pearson_r_descriptive": correlation,
        "worker_wait_mean_ms": stats(waits)["mean"], "http_duration_mean_ms": stats(http)["mean"],
        "http_minus_wait_mean_ms": stats(residual)["mean"],
        "worker_wait_to_http_mean_ratio": stats(waits)["mean"] / stats(http)["mean"] if pairs and stats(http)["mean"] else None,
        "http_minus_wait_p95_ms": stats(residual)["p95"],
    }


def counts_summary(times, width, horizon):
    n = math.ceil(horizon / width)
    counts = [0] * n
    for t in times:
        if 0 <= t < horizon:
            counts[min(int(t / width), n - 1)] += 1
    mu = statistics.mean(counts) if counts else None
    var = statistics.variance(counts) if len(counts) > 1 else None
    return {
        "windows": n,
        "mean_per_window": mu,
        "sample_variance": var,
        "variance_to_mean": var / mu if var is not None and mu else None,
        "max_per_window": max(counts, default=0),
        "counts": counts,
    }


def occupancy(intervals, left, right):
    """Time-weighted active count over [left,right), with maximum and area."""
    if right <= left:
        raise ValueError("non-positive bin width")
    events = []
    for start, end in intervals:
        if end < start:
            raise ValueError("negative interval")
        a, b = max(start, left), min(end, right)
        if b > a:
            events.extend(((a, 1), (b, -1)))
    active = peak = 0
    area = 0.0
    previous = left
    for at, delta in sorted(events, key=lambda item: (item[0], item[1])):
        area += (at - previous) * active
        active += delta
        peak = max(peak, active)
        if active < 0:
            raise ValueError("negative reconstructed concurrency")
        previous = at
    area += (right - previous) * active
    return {"mean": area / (right - left), "maximum": peak}


def load_run(name):
    folder = ROOT / name
    raw = folder / "raw"
    config = read_json(raw / "effective_config.json")
    status = read_json(raw / "run_status.json")
    summary = read_json(folder / "capacity_summary.json")
    execution = read_json(folder / "execution_result.json")
    verification = read_json(folder / "verification/verification.json")
    capture_csv = read_json(raw / "traffic_capture.csv.capture.json")["capture_counters"]
    capture_pcap = read_json(raw / "source_artifacts/traffic_capture.pcap.capture.json")["capture_counters"]
    if status["status"] != "completed" or not status["producers_drained"]:
        raise ValueError(f"run not complete/drained: {name}")
    if execution["status"] != "completed_normally" or execution["safety_interrupted"]:
        raise ValueError(f"unexpected execution status: {name}")
    if not verification["accepted"]:
        raise ValueError(f"verification not accepted: {name}")
    if capture_csv["packets_dropped_by_kernel"] != 0 or capture_pcap["packets_dropped_by_kernel"] != 0:
        raise ValueError(f"capture drops reported: {name}")
    if summary["failures"]:
        raise ValueError(f"HTTP failures recorded: {name}")
    return {
        "name": name,
        "folder": folder,
        "raw": raw,
        "config": config,
        "status": status,
        "summary": summary,
        "execution": execution,
        "verification": verification,
        "capture_csv": capture_csv,
        "capture_pcap": capture_pcap,
        "origin": float(status["experiment_start_monotonic"]),
    }


def clock_audit(run):
    raw = run["raw"]
    source_clock = read_json(raw / "source_artifacts/clock_validation.json")
    victim_path = raw / "diagnostics/victim_clock_validation.json"
    victim_clock = read_json(victim_path) if victim_path.exists() else None
    if run["name"] in DIAGNOSTIC_RUNS:
        if not source_clock.get("comparable") or not victim_clock or not victim_clock.get("comparable"):
            raise ValueError(f"cross-domain clock audit failed: {run['name']}")
        host_kernel = source_clock["host"]["kernel"]
        for audit in (source_clock, victim_clock):
            if audit["host"]["kernel"] != host_kernel or audit["host"].get("timens_offsets") != "monotonic           0         0\nboottime            0         0\n":
                raise ValueError(f"host timer namespace/offset proof differs: {run['name']}")
            for item in audit.get("sources", []):
                for sample in item.get("samples", []):
                    if sample.get("kernel") != host_kernel or sample.get("timens_offsets") != audit["host"].get("timens_offsets"):
                        raise ValueError(f"clock kernel/offset sample mismatch: {run['name']}")
    for component, audit in (("source", source_clock), ("victim", victim_clock)):
        if not audit:
            continue
        widths = [s.get("bracket_width_seconds") for item in audit.get("sources", []) for s in item.get("samples", [])]
        comparable = [s.get("checks", {}).get("comparable") for item in audit.get("sources", []) for s in item.get("samples", [])]
        if comparable and not all(comparable):
            raise ValueError(f"uncomparable {component} clock samples: {run['name']}")
    return source_clock, victim_clock


def diagnostic_data(run):
    """Load and reconcile source/victim diagnostic events for one instrumented run."""
    raw, origin, name = run["raw"], run["origin"], run["name"]
    req_rows = csv_rows(raw / "request_log.csv")
    requests = {r["request_id"]: r for r in req_rows}
    if len(requests) != len(req_rows):
        raise ValueError(f"duplicate request IDs in client log: {name}")
    sources = read_json(raw / "source_inventory.json")
    source_events = {}
    attempts_by_source = {}
    request_source = {}
    source_writer_audit = []
    source_threads = {}
    for source in sources:
        sid = source["source_id"]
        folder = raw / "source_artifacts" / sid / "output"
        event_path = folder / "diagnostics/events.jsonl"
        writer = read_json(folder / "diagnostics/events.summary.json")
        events = jsonl(event_path)
        if not writer["complete"] or writer["written"] != len(events) or writer["dropped"] or writer["write_errors"]:
            raise ValueError(f"incomplete source log: {name}/{sid}")
        if writer["context"].get("run_id") != run["status"]["run_id"]:
            raise ValueError(f"source log run_id mismatch: {name}/{sid}")
        source_events[sid] = events
        grouped = defaultdict(dict)
        for event in events:
            aid, kind = event.get("attempt_id"), event["kind"]
            if aid:
                if kind in grouped[aid]:
                    raise ValueError(f"duplicate attempt event {name}/{sid}/{aid}/{kind}")
                grouped[aid][kind] = event
            if kind == "http_started":
                rid = event.get("request_id")
                if rid not in requests:
                    raise ValueError(f"HTTP start not in scientific request log: {name}/{rid}")
                if rid in request_source:
                    raise ValueError(f"duplicate source HTTP ID: {name}/{rid}")
                request_source[rid] = sid
        attempts_by_source[sid] = grouped
        source_threads[sid] = int(source["send_workers"])
        final = read_json(folder / "final_status.json")
        if not final.get("drained") or not final.get("logger_complete"):
            raise ValueError(f"source did not drain cleanly: {name}/{sid}")
        source_writer_audit.append({
            "source_id": sid,
            "events": len(events),
            "offered": writer["offered"],
            "written": writer["written"],
            "dropped": writer["dropped"],
            "write_errors": writer["write_errors"],
            "queue_remaining": writer["queue_remaining"],
            "complete": writer["complete"],
            "send_workers": source_threads[sid],
            "source_closed_drained": final["drained"],
        })
    if set(request_source) != set(requests):
        raise ValueError(f"source/client request IDs differ: {name} missing={len(set(requests)-set(request_source))} extra={len(set(request_source)-set(requests))}")

    victim_path = raw / "diagnostics/victim/events.jsonl"
    victim_events_all = jsonl(victim_path)
    victim_writer = read_json(raw / "diagnostics/victim/events.summary.json")
    if not victim_writer["complete"] or victim_writer["written"] != len(victim_events_all) or victim_writer["dropped"] or victim_writer["write_errors"]:
        raise ValueError(f"incomplete victim log: {name}")
    if victim_writer["clock"]["time_namespace"] != run["summary"]["victim"]["handler_wall_seconds"].get("time_namespace", victim_writer["clock"]["time_namespace"]):
        # Summary may not persist this field; the actual worker-clock check below is authoritative.
        pass
    victim_events = [e for e in victim_events_all if e.get("request_id") in requests]
    starts, finishes = {}, {}
    for e in victim_events:
        rid = e["request_id"]
        if e["kind"] == "handler_started":
            if rid in starts:
                raise ValueError(f"duplicate handler start: {name}/{rid}")
            starts[rid] = e
        elif e["kind"] == "handler_finished":
            if rid in finishes:
                raise ValueError(f"duplicate handler finish: {name}/{rid}")
            finishes[rid] = e
    if set(starts) != set(requests) or set(finishes) != set(requests):
        raise ValueError(f"victim/client ID coverage differs: {name}, start={len(starts)}, finish={len(finishes)}, request={len(requests)}")

    parent_namespace = victim_writer["clock"]["time_namespace"]
    source_waits, attempts_rows = [], []
    for sid, grouped in attempts_by_source.items():
        for aid, attempt in grouped.items():
            submit = attempt.get("submitted")
            task_start = attempt.get("task_started")
            http_start = attempt.get("http_started")
            if submit and task_start:
                delta = task_start["at"] - submit["at"]
                if delta < 0:
                    raise ValueError("negative source submit-to-task interval")
                source_waits.append((sid, submit["at"] - origin, delta * 1000))
            planned_at = submit.get("planned_at") if submit else None
            task_to_http = (http_start["at"] - task_start["at"]) * 1000 if http_start and task_start else None
            plan_to_submit = (submit["at"] - planned_at) * 1000 if submit and planned_at is not None else None
            submit_to_task = (task_start["at"] - submit["at"]) * 1000 if task_start and submit else None
            rid = http_start.get("request_id") if http_start else None
            attempts_rows.append({
                "run": name, "source_id": sid, "attempt_id": aid, "request_id": rid,
                "planned_at_elapsed": planned_at - origin if planned_at is not None else None,
                "sampled_interval_seconds": attempt.get("planned", {}).get("sampled_interval"),
                "submitted_at_elapsed": submit["at"] - origin if submit else None,
                "task_started_at_elapsed": task_start["at"] - origin if task_start else None,
                "http_started_at_elapsed": http_start["at"] - origin if http_start else None,
                "plan_to_submit_ms": plan_to_submit,
                "submit_to_task_ms": submit_to_task,
                "task_to_http_ms": task_to_http,
                "has_http_finish": "http_finished" in attempt,
                "has_task_finish": "task_finished" in attempt,
            })

    req_details = []
    handler_intervals, worker_intervals, victim_wait_intervals = [], [], []
    for rid, request in requests.items():
        start, end = starts[rid], finishes[rid]
        end_event = end["handler_finished_at"]
        if end.get("worker_clock", {}).get("time_namespace") != parent_namespace:
            raise ValueError(f"incomparable worker clock for {name}/{rid}")
        submitted, work_start, work_end = end["work_submitted_at"], end["work_started_at"], end["work_finished_at"]
        handler_start = start["handler_started_at"]
        if not (handler_start <= submitted <= work_start <= work_end <= end["work_result_observed_at"] <= end_event):
            raise ValueError(f"handler/work event order invalid: {name}/{rid}")
        handler_intervals.append((handler_start - origin, end_event - origin))
        worker_intervals.append((work_start - origin, work_end - origin))
        victim_wait_intervals.append((submitted - origin, work_start - origin))
        http_start_elapsed = float(request["elapsed_seconds"])
        http_end_elapsed = float(request["end_elapsed_seconds"]) if request["end_elapsed_seconds"] else None
        diagnostic_start_elapsed = next(
            e["at"] - origin for e in source_events[request_source[rid]]
            if e["kind"] == "http_started" and e.get("request_id") == rid
        )
        if abs(http_start_elapsed - diagnostic_start_elapsed) > 1e-5:
            raise ValueError(f"scientific and diagnostic HTTP start mismatch: {name}/{rid}")
        req_details.append({
            "run": name, "request_id": rid, "source_id": request_source[rid],
            "start_elapsed": http_start_elapsed,
            "end_elapsed": http_end_elapsed,
            "duration_ms": float(request["duration_ms"]) if request["duration_ms"] else None,
            "outcome": request["outcome"], "http_status": request["http_status"] or None,
            "handler_started_elapsed": handler_start - origin,
            "work_submitted_elapsed": submitted - origin,
            "work_started_elapsed": work_start - origin,
            "work_finished_elapsed": work_end - origin,
            "work_result_observed_elapsed": end["work_result_observed_at"] - origin,
            "handler_finished_elapsed": end_event - origin,
            "handler_to_submit_ms": (submitted - handler_start) * 1000,
            "work_wait_ms": (work_start - submitted) * 1000,
            "work_wall_ms": (work_end - work_start) * 1000,
            "work_cpu_ms": float(end["work_cpu_seconds"]) * 1000,
            "result_transport_ms": (end["work_result_observed_at"] - work_end) * 1000,
            "post_work_handler_ms": (end_event - end["work_result_observed_at"]) * 1000,
            "handler_wall_ms": (end_event - handler_start) * 1000,
            "handler_active_at_start": start.get("active_handlers_at_start"),
            "handler_active_at_finish": end.get("active_handlers_at_finish"),
        })

    # Source-owned local elapsed durations are exact within each source. Inter-source
    # binning uses the clock audit above and the recorded host experiment origin.
    return {
        "requests": req_details,
        "attempts": attempts_rows,
        "source_events": source_events,
        "source_waits": source_waits,
        "handler_intervals": handler_intervals,
        "worker_intervals": worker_intervals,
        "victim_wait_intervals": victim_wait_intervals,
        "source_audit": source_writer_audit,
        "victim_audit": {
            "events": len(victim_events_all), "offered": victim_writer["offered"],
            "written": victim_writer["written"], "dropped": victim_writer["dropped"],
            "write_errors": victim_writer["write_errors"],
            "queue_remaining": victim_writer["queue_remaining"], "complete": victim_writer["complete"],
            "worker_clock_namespace": parent_namespace,
        },
        "source_inventory": sources,
        "victim_events": victim_events,
    }


def timeline(run, diagnostic, width):
    origin, name = run["origin"], run["name"]
    duration = generation_duration(run)
    max_elapsed = max(
        [duration]
        + [r["end_elapsed"] for r in diagnostic["requests"] if r["end_elapsed"] is not None]
        + [b - origin for intervals in (diagnostic["handler_intervals"], diagnostic["worker_intervals"]) for _, b in intervals]
    )
    bins = math.ceil(max_elapsed / width)
    metrics = csv_rows(run["raw"] / "simulation_metrics.csv")
    watchdog = jsonl(run["folder"] / "watchdog.jsonl")
    starts = defaultdict(list)
    completed = defaultdict(list)
    source_http = defaultdict(Counter)
    for request in diagnostic["requests"]:
        idx = math.floor(request["start_elapsed"] / width) if request["start_elapsed"] >= 0 else -1
        if 0 <= idx < bins:
            starts[idx].append(request)
            source_http[(idx, request["source_id"])]["starts"] += 1
        if request["end_elapsed"] is not None and request["end_elapsed"] >= 0:
            idx_end = math.floor(request["end_elapsed"] / width)
            if 0 <= idx_end < bins:
                completed[idx_end].append(request)
    attempts = diagnostic["attempts"]
    submitted_bins = defaultdict(Counter)
    source_wait_bins = defaultdict(list)
    for a in attempts:
        if a["submitted_at_elapsed"] is not None and 0 <= a["submitted_at_elapsed"] < bins * width:
            idx = math.floor(a["submitted_at_elapsed"] / width)
            submitted_bins[(idx, a["source_id"])]["submitted"] += 1
        if a["task_started_at_elapsed"] is not None and 0 <= a["task_started_at_elapsed"] < bins * width:
            idx = math.floor(a["task_started_at_elapsed"] / width)
            submitted_bins[(idx, a["source_id"])]["task_started"] += 1
        if a["submitted_at_elapsed"] is not None and a["submit_to_task_ms"] is not None and 0 <= a["submitted_at_elapsed"] < bins * width:
            idx = math.floor(a["submitted_at_elapsed"] / width)
            source_wait_bins[(idx, a["source_id"])].append(a["submit_to_task_ms"])

    wait_by_bin = defaultdict(list)
    work_by_bin = defaultdict(list)
    cpu_values = defaultdict(list)
    for req in diagnostic["requests"]:
        if 0 <= req["work_submitted_elapsed"] < bins * width:
            wait_by_bin[math.floor(req["work_submitted_elapsed"] / width)].append(req["work_wait_ms"])
        if 0 <= req["work_started_elapsed"] < bins * width:
            work_by_bin[math.floor(req["work_started_elapsed"] / width)].append(req)
    for metric in metrics:
        elapsed = float(metric["elapsed_seconds"])
        if 0 <= elapsed < bins * width and metric["active_containers_names"]:
            cpu_values[math.floor(elapsed / width)].append(float(metric["average_cpu_percent"]))

    host_by_bin = defaultdict(list)
    memory_by_bin = defaultdict(list)
    for item in watchdog:
        elapsed = float(item["monotonic"]) - origin
        if 0 <= elapsed < bins * width:
            idx = math.floor(elapsed / width)
            if item.get("host_busy_percent") is not None:
                host_by_bin[idx].append(float(item["host_busy_percent"]))
            if item.get("available_bytes") is not None:
                memory_by_bin[idx].append(float(item["available_bytes"]) / 1024**2)

    result = []
    for idx in range(bins):
        left, right = idx * width, (idx + 1) * width
        reqs = starts[idx]
        wait_values = wait_by_bin[idx]
        work_values = work_by_bin[idx]
        handlers = occupancy(diagnostic["handler_intervals"], left, right)
        workers = occupancy(diagnostic["worker_intervals"], left, right)
        victim_pending = occupancy(diagnostic["victim_wait_intervals"], left, right)
        source_pending_by_id = {}
        for sid in {s["source_id"] for s in diagnostic["source_audit"]}:
            intervals = []
            for attempt in attempts:
                if attempt["source_id"] == sid and attempt["submitted_at_elapsed"] is not None and attempt["task_started_at_elapsed"] is not None:
                    intervals.append((attempt["submitted_at_elapsed"], attempt["task_started_at_elapsed"]))
            source_pending_by_id[sid] = occupancy(intervals, left, right)
        row = {
            "run": name, "width_seconds": width, "bin": idx, "start_seconds": left,
            "end_seconds": right, "phase": "generation" if left < duration else "drain",
            "http_starts": len(reqs), "http_completions": len(completed[idx]),
            "http_failures": sum(r["outcome"] != "response" for r in reqs),
            "http_duration_n": len([r for r in reqs if r["duration_ms"] is not None]),
            "http_duration_mean_ms": stats([r["duration_ms"] for r in reqs])["mean"],
            "http_duration_median_ms": stats([r["duration_ms"] for r in reqs])["median"],
            "http_duration_p95_ms": stats([r["duration_ms"] for r in reqs])["p95"],
            "http_duration_max_ms": stats([r["duration_ms"] for r in reqs])["maximum"],
            "worker_wait_n": len(wait_values), "worker_wait_mean_ms": stats(wait_values)["mean"],
            "worker_wait_median_ms": stats(wait_values)["median"], "worker_wait_p95_ms": stats(wait_values)["p95"],
            "worker_wait_max_ms": stats(wait_values)["maximum"],
            "work_wall_mean_ms": stats([r["work_wall_ms"] for r in work_values])["mean"],
            "work_cpu_mean_ms": stats([r["work_cpu_ms"] for r in work_values])["mean"],
            "handlers_mean_active": handlers["mean"], "handlers_peak": handlers["maximum"],
            "workers_mean_active": workers["mean"], "workers_peak": workers["maximum"],
            "victim_submitted_not_started_mean": victim_pending["mean"],
            "victim_submitted_not_started_peak": victim_pending["maximum"],
            "source_submitted_not_started_mean_sum": sum(x["mean"] for x in source_pending_by_id.values()),
            "source_submitted_not_started_peak_sum": sum(x["maximum"] for x in source_pending_by_id.values()),
            "victim_cpu_docker_mean_pct": stats(cpu_values[idx])["mean"],
            "host_busy_mean_pct": stats(host_by_bin[idx])["mean"],
            "host_busy_max_pct": stats(host_by_bin[idx])["maximum"],
            "host_available_min_mib": min(memory_by_bin[idx], default=None),
        }
        for sid in sorted(source_pending_by_id):
            row[f"{sid}_pending_peak"] = source_pending_by_id[sid]["maximum"]
            row[f"{sid}_starts"] = source_http[(idx, sid)]["starts"]
            row[f"{sid}_submitted"] = submitted_bins[(idx, sid)]["submitted"]
            row[f"{sid}_task_started"] = submitted_bins[(idx, sid)]["task_started"]
            delays = stats(source_wait_bins[(idx, sid)])
            row[f"{sid}_submit_to_task_n"] = delays["n"]
            row[f"{sid}_submit_to_task_mean_ms"] = delays["mean"]
            row[f"{sid}_submit_to_task_p95_ms"] = delays["p95"]
        result.append(row)
    return result


def run_summaries(run, diagnostic):
    name, origin = run["name"], run["origin"]
    duration = generation_duration(run)
    requests = diagnostic["requests"]
    in_plan = [r for r in requests if 0 <= r["start_elapsed"] < duration]
    completed_in_plan = [r for r in requests if r["end_elapsed"] is not None and 0 <= r["end_elapsed"] < duration]
    tail = [r for r in requests if r["end_elapsed"] is not None and r["end_elapsed"] >= duration]
    worker_intervals = diagnostic["worker_intervals"]
    worker_time = occupancy(worker_intervals, 0, duration)
    # Use exact sweep to calculate time with both pool slots occupied.
    events = []
    for a, b in worker_intervals:
        a, b = max(a, 0), min(b, duration)
        if b > a:
            events.extend(((a, 1), (b, -1)))
    active = 0
    previous = 0.0
    both_seconds = 0.0
    busy_seconds = 0.0
    peak = 0
    for at, delta in sorted(events, key=lambda item: (item[0], item[1])):
        if active > 0:
            busy_seconds += at - previous
        if active >= 2:
            both_seconds += at - previous
        active += delta
        peak = max(peak, active)
        previous = at
    if active > 0:
        busy_seconds += duration - previous
    if active >= 2:
        both_seconds += duration - previous
    source_rows = []
    for sid, grouped in _groups(diagnostic["attempts"], "source_id").items():
        source_requests = [r for r in requests if r["source_id"] == sid]
        starts_100 = counts_summary([r["start_elapsed"] for r in source_requests], .1, duration)
        starts_250 = counts_summary([r["start_elapsed"] for r in source_requests], .25, duration)
        waits = [a["submit_to_task_ms"] for a in grouped if a["submit_to_task_ms"] is not None]
        pending_intervals = [(a["submitted_at_elapsed"], a["task_started_at_elapsed"]) for a in grouped
                             if a["submitted_at_elapsed"] is not None and a["task_started_at_elapsed"] is not None]
        pend = occupancy(pending_intervals, 0, duration)
        source_rows.append({
            "run": name, "source_id": sid, "configured_rate_rps": run["config"]["normal_traffic"]["rate"],
            "send_threads": next(s["send_workers"] for s in diagnostic["source_inventory"] if s["source_id"] == sid),
            "source_requests": len(source_requests),
            "source_starts_rps_in_generation": len([r for r in source_requests if 0 <= r["start_elapsed"] < duration]) / duration,
            "planned_interval_mean_ms": stats([a["sampled_interval_seconds"] * 1000 for a in grouped
                                                if a.get("sampled_interval_seconds") is not None])["mean"],
            "planned_attempts": sum("planned_at_elapsed" in a and a["planned_at_elapsed"] is not None for a in grouped),
            "plan_to_submit_mean_ms": stats([a["plan_to_submit_ms"] for a in grouped])["mean"],
            "plan_to_submit_p95_ms": stats([a["plan_to_submit_ms"] for a in grouped])["p95"],
            "submit_to_task_mean_ms": stats(waits)["mean"], "submit_to_task_p50_ms": stats(waits)["median"],
            "submit_to_task_p95_ms": stats(waits)["p95"], "submit_to_task_max_ms": stats(waits)["maximum"],
            "task_to_http_mean_ms": stats([a["task_to_http_ms"] for a in grouped])["mean"],
            "task_to_http_p95_ms": stats([a["task_to_http_ms"] for a in grouped])["p95"],
            "submitted_not_started_peak": pend["maximum"], "submitted_not_started_mean": pend["mean"],
            "starts_100ms_fano": starts_100["variance_to_mean"], "starts_100ms_max": starts_100["max_per_window"],
            "starts_250ms_fano": starts_250["variance_to_mean"], "starts_250ms_max": starts_250["max_per_window"],
            "http_duration_mean_ms": stats([r["duration_ms"] for r in source_requests])["mean"],
            "http_duration_p95_ms": stats([r["duration_ms"] for r in source_requests])["p95"],
        })
    summary = run["summary"]
    return {
        "run": name, "run_id": run["status"]["run_id"],
        "sources": run["config"]["normal_traffic"]["clients"],
        "rate_per_source": run["config"]["normal_traffic"]["rate"],
        "nominal_aggregate_rps": run["config"]["normal_traffic"]["clients"] * run["config"]["normal_traffic"]["rate"],
        "generation_seconds": duration,
        "http_starts_in_generation": len(in_plan), "http_starts_rps": len(in_plan) / duration,
        "http_starts_tail": sum(r["start_elapsed"] >= duration for r in requests),
        "http_completions_in_generation": len(completed_in_plan),
        "http_completions_in_drain": len(tail),
        "unfinished_http": sum(r["end_elapsed"] is None for r in requests),
        "http_failures": sum(r["outcome"] != "response" for r in requests),
        "http_duration_mean_ms": stats([r["duration_ms"] for r in requests])["mean"],
        "http_duration_median_ms": stats([r["duration_ms"] for r in requests])["median"],
        "http_duration_p95_ms": stats([r["duration_ms"] for r in requests])["p95"],
        "http_duration_max_ms": stats([r["duration_ms"] for r in requests])["maximum"],
        "handler_events_matched": len(requests),
        "handler_concurrency_peak_reconstructed": occupancy(diagnostic["handler_intervals"], 0, duration)["maximum"],
        "handler_concurrency_mean_reconstructed": occupancy(diagnostic["handler_intervals"], 0, duration)["mean"],
        "worker_operations_submitted_in_generation": sum(0 <= r["work_submitted_elapsed"] < duration for r in requests),
        "worker_wait_mean_ms": stats([r["work_wait_ms"] for r in requests])["mean"],
        "worker_wait_median_ms": stats([r["work_wait_ms"] for r in requests])["median"],
        "worker_wait_p95_ms": stats([r["work_wait_ms"] for r in requests])["p95"],
        "worker_wait_max_ms": stats([r["work_wait_ms"] for r in requests])["maximum"],
        "work_wall_mean_ms": stats([r["work_wall_ms"] for r in requests])["mean"],
        "work_wall_p95_ms": stats([r["work_wall_ms"] for r in requests])["p95"],
        "work_cpu_mean_ms": stats([r["work_cpu_ms"] for r in requests])["mean"],
        "work_cpu_p95_ms": stats([r["work_cpu_ms"] for r in requests])["p95"],
        "work_worker_occupancy_mean_of_2": worker_time["mean"] / 2,
        "workers_mean_active": worker_time["mean"],
        "workers_peak_reconstructed": peak,
        "both_workers_active_fraction": both_seconds / duration,
        "worker_busy_core_seconds": busy_seconds,
        "cpu_demand_cores_lambda_times_mean_cpu": (
            sum(1 for r in requests if 0 <= r["work_submitted_elapsed"] < duration) / duration
            * stats([r["work_cpu_ms"] for r in requests if 0 <= r["work_submitted_elapsed"] < duration])["mean"] / 1000
        ),
        "naive_two_worker_rate_from_mean_cpu_rps": 2 / (stats([r["work_cpu_ms"] for r in requests if 0 <= r["work_submitted_elapsed"] < duration])["mean"] / 1000),
        "progression_gate_allowed": summary["progression"]["allowed"],
        "progression_gate_reasons": ";".join(summary["progression"]["reasons"]),
        "diagnostic_source_drops": sum(s["dropped"] for s in diagnostic["source_audit"]),
        "diagnostic_victim_drops": diagnostic["victim_audit"]["dropped"],
        "cpu_docker_mean_pct": summary["cpu_docker_percent"]["mean"],
        "cpu_docker_max_pct": summary["cpu_docker_percent"]["maximum"],
        "source_rows": source_rows,
    }


def _groups(rows, key):
    out = defaultdict(list)
    for row in rows:
        out[row[key]].append(row)
    return out


def inventory_and_audit(runs, diagnostic_by_name):
    inventory = []
    input_paths = []
    for run in runs:
        raw, name = run["raw"], run["name"]
        source_clock, victim_clock = clock_audit(run)
        fields = [
            "raw/effective_config.json", "raw/run_status.json", "raw/request_log.csv",
            "raw/simulation_metrics.csv", "raw/victim_stats.jsonl", "raw/traffic_capture.csv",
            "raw/traffic_capture.csv.capture.json", "raw/source_artifacts/traffic_capture.pcap",
            "raw/source_artifacts/traffic_capture.pcap.capture.json", "verification/verification.json",
            "capacity_summary.json", "diagnostic_summary.json", "watchdog.jsonl",
        ]
        for rel in fields:
            path = run["folder"] / rel
            if path.exists():
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                input_paths.append({"run": name, "path": str(path), "size_bytes": path.stat().st_size, "sha256": digest})
        diag = diagnostic_by_name.get(name)
        if diag:
            diagnostic_rel = [
                "raw/diagnostics/victim/events.jsonl",
                "raw/diagnostics/victim/events.summary.json",
            ] + [
                f"raw/source_artifacts/{source['source_id']}/output/diagnostics/events.jsonl"
                for source in diag["source_inventory"]
            ] + [
                f"raw/source_artifacts/{source['source_id']}/output/diagnostics/events.summary.json"
                for source in diag["source_inventory"]
            ]
            for rel in diagnostic_rel:
                path = run["folder"] / rel
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                input_paths.append({"run": name, "path": str(path), "size_bytes": path.stat().st_size, "sha256": digest})
        inventory.append({
            "run": name, "run_id": run["status"]["run_id"], "status": run["status"]["status"],
            "drained": run["status"]["producers_drained"], "topology": run["config"]["topology"]["mode"],
            "endpoint": run["config"]["normal_traffic"]["endpoint"],
            "sources": run["config"]["normal_traffic"]["clients"],
            "rate_per_source": run["config"]["normal_traffic"]["rate"],
            "duration_seconds": run["config"]["duration_seconds"],
            "diagnostics_enabled": run["config"].get("diagnostics", {}).get("enabled", False),
            "source_clock_comparable": bool(source_clock.get("comparable")),
            "victim_clock_comparable": bool(victim_clock and victim_clock.get("comparable")),
            "source_clock_samples": sum(len(x["samples"]) for x in source_clock.get("sources", [])),
            "source_clock_max_bracket_ms": max([s["bracket_width_seconds"] * 1000 for x in source_clock.get("sources", []) for s in x["samples"]] or [None]),
            "victim_clock_max_bracket_ms": max([s["bracket_width_seconds"] * 1000 for x in (victim_clock or {}).get("sources", []) for s in x["samples"]] or [None]),
            "source_writer_records": sum(x["events"] for x in diag["source_audit"]) if diag else None,
            "source_writer_dropped": sum(x["dropped"] for x in diag["source_audit"]) if diag else None,
            "victim_writer_records": diag["victim_audit"]["events"] if diag else None,
            "victim_writer_dropped": diag["victim_audit"]["dropped"] if diag else None,
            "csv_capture_packets": run["capture_csv"].get("packets_captured"),
            "pcap_capture_packets": run["capture_pcap"].get("packets_captured"),
            "csv_capture_dropped": run["capture_csv"].get("packets_dropped_by_kernel"),
            "pcap_capture_dropped": run["capture_pcap"].get("packets_dropped_by_kernel"),
            "features_accepted": run["verification"]["accepted"],
            "verification_features": ";".join(f["column"]+":"+f["status"] for f in run["verification"]["features"]),
        })
    return inventory, input_paths


def plot_outputs(timelines, source_rows):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    duration = 20.0  # C3/C5 main runs share the configured 20 s generation period.
    selected = {name: [r for r in timelines if r["run"] == name and r["width_seconds"] == 1.0 and r["start_seconds"] < duration]
                for name in ("C3_ON_r1", "C5_ON_r1")}
    colors = {"C3_ON_r1": "#1769aa", "C5_ON_r1": "#c33d3d"}
    fig, axes = plt.subplots(3, 1, figsize=(12, 9), sharex=True, constrained_layout=True)
    for name, rows in selected.items():
        x = [r["start_seconds"] + .5 for r in rows]
        axes[0].plot(x, [r["http_duration_mean_ms"] for r in rows], color=colors[name], label=f"{name} média")
        axes[0].plot(x, [r["http_duration_p95_ms"] for r in rows], color=colors[name], linestyle="--", label=f"{name} p95")
        axes[1].plot(x, [r["worker_wait_mean_ms"] for r in rows], color=colors[name], label=f"{name} média")
        axes[1].plot(x, [r["worker_wait_p95_ms"] for r in rows], color=colors[name], linestyle="--", label=f"{name} p95")
        axes[2].plot(x, [r["http_starts"] for r in rows], color=colors[name], label=name)
    axes[0].set_ylabel("Duração HTTP (ms)"); axes[0].set_title("Duração por segundo do início HTTP; p95 com ~120 observações/s")
    axes[1].set_ylabel("Espera pelo worker (ms)"); axes[1].set_title("Espera alocada ao segundo da submissão do trabalho")
    axes[2].set_ylabel("Inícios HTTP / s"); axes[2].set_title("Taxa observada por janela de 1 s")
    axes[2].set_xlabel("Segundos após a origem experimental")
    for ax in axes:
        ax.axvspan(duration, 25, color="#dddddd", alpha=.4)
        ax.grid(alpha=.2); ax.legend(ncol=2, fontsize=8)
    fig.suptitle("C3 × C5 — métricas medidas; faixa cinza é drenagem")
    fig.savefig(OUT / "c3_c5_timeline_1s.png", dpi=160); fig.savefig(OUT / "c3_c5_timeline_1s.svg"); plt.close(fig)

    c5 = [r for r in timelines if r["run"] == "C5_ON_r1" and r["width_seconds"] == .25]
    fig, axes = plt.subplots(4, 1, figsize=(13, 11), sharex=True, constrained_layout=True)
    x = [r["start_seconds"] + .125 for r in c5]
    axes[0].plot(x, [r["http_starts"] for r in c5], color="#1769aa", label="inícios HTTP")
    axes[0].plot(x, [r["source_submitted_not_started_peak_sum"] for r in c5], color="#d17c00", label="pendências fontes (soma de picos no intervalo)")
    axes[1].plot(x, [r["handlers_mean_active"] for r in c5], label="handlers ativos, média temporal")
    axes[1].plot(x, [r["workers_mean_active"] for r in c5], label="workers ativos, média temporal")
    axes[1].plot(x, [r["victim_submitted_not_started_mean"] for r in c5], label="submetido ainda não iniciado, média temporal")
    axes[2].plot(x, [r["worker_wait_mean_ms"] for r in c5], label="espera média por submissão", color="#c33d3d")
    axes[2].plot(x, [r["worker_wait_p95_ms"] for r in c5], label="espera p95 por submissão", linestyle="--", color="#8b1e1e")
    axes[3].plot(x, [r["victim_cpu_docker_mean_pct"] for r in c5], label="CPU Docker vítima")
    axes[3].plot(x, [r["host_busy_mean_pct"] for r in c5], label="CPU host ocupado")
    axes[0].set_ylabel("req/bin ou tarefas"); axes[1].set_ylabel("concorrência")
    axes[2].set_ylabel("ms"); axes[3].set_ylabel("% (escalas distintas)"); axes[3].set_xlabel("Segundos após origem; bin 250 ms")
    for ax in axes:
        ax.axvspan(duration, max([duration, *x]), color="#dddddd", alpha=.4)
        ax.grid(alpha=.2); ax.legend(ncol=2, fontsize=8)
    fig.suptitle("C5 — resolução de 250 ms; a faixa cinza indica drenagem")
    fig.savefig(OUT / "c5_detailed_timeline_250ms.png", dpi=160); fig.savefig(OUT / "c5_detailed_timeline_250ms.svg"); plt.close(fig)

    c5_sources = [r for r in source_rows if r["run"] == "C5_ON_r1"]
    fig, axes = plt.subplots(len(c5_sources), 1, figsize=(12, 2.7 * len(c5_sources)), sharex=True, constrained_layout=True)
    if len(c5_sources) == 1:
        axes = [axes]
    for ax, source in zip(axes, c5_sources):
        series = [r for r in timelines if r["run"] == "C5_ON_r1" and r["width_seconds"] == .25]
        key = source["source_id"]
        xx = [r["start_seconds"] + .125 for r in series]
        ax.step(xx, [r.get(f"{key}_starts", 0) for r in series], where="mid", label=f"{key} HTTP starts/250 ms")
        ax.plot(xx, [r.get(f"{key}_pending_peak", 0) for r in series], label="submitted−task_started peak, bin")
        ax.set_ylabel("count"); ax.set_title(f"C5 {key}"); ax.grid(alpha=.2); ax.legend(fontsize=8)
    axes[-1].set_xlabel("Segundos após origem; bin 250 ms")
    for ax in axes:
        ax.axvspan(duration, max([duration, *[r["start_seconds"] + .125 for r in series]]), color="#dddddd", alpha=.4)
    fig.suptitle("C5 — variação por fonte; pendências são diferença derivada, não API da fila")
    fig.savefig(OUT / "c5_sources_timeline_250ms.png", dpi=160); fig.savefig(OUT / "c5_sources_timeline_250ms.svg"); plt.close(fig)


def main():
    runs = [load_run(name) for name in RUNS]
    diagnostics = {}
    source_rows = []
    request_tables = {}
    run_rows = []
    association_rows = []
    all_timelines = []
    for run in runs:
        if run["name"] not in DIAGNOSTIC_RUNS:
            # OFF has no internal source/victim event streams by design. The scientific
            # client/server records remain available, but stage-level attribution does not.
            req = csv_rows(run["raw"] / "request_log.csv")
            duration = generation_duration(run)
            summary = run["summary"]
            starts = [float(r["elapsed_seconds"]) for r in req if r["elapsed_seconds"]]
            durations = [float(r["duration_ms"]) for r in req if r["duration_ms"]]
            cpu = summary.get("cpu_docker_percent", {})
            run_rows.append({
                "run": run["name"], "run_id": run["status"]["run_id"], "sources": run["config"]["normal_traffic"]["clients"],
                "rate_per_source": run["config"]["normal_traffic"]["rate"], "nominal_aggregate_rps": 128,
                "generation_seconds": duration, "http_starts_in_generation": sum(0 <= t < duration for t in starts),
                "http_starts_rps": sum(0 <= t < duration for t in starts) / duration,
                "http_duration_mean_ms": stats(durations)["mean"], "http_duration_median_ms": stats(durations)["median"],
                "http_duration_p95_ms": stats(durations)["p95"], "http_duration_max_ms": stats(durations)["maximum"],
                "http_failures": summary.get("failures"), "cpu_docker_mean_pct": cpu.get("mean"),
                "cpu_docker_max_pct": cpu.get("maximum"),
                "diagnostic_stage_data": "not collected by configuration",
            })
            continue
        diag = diagnostic_data(run)
        diagnostics[run["name"]] = diag
        summary = run_summaries(run, diag)
        association_rows.append({"run": run["name"], **paired_association(diag["requests"])})
        source_rows.extend(summary.pop("source_rows"))
        run_rows.append(summary)
        request_tables[run["name"]] = diag["requests"]
        for width in (1.0, .25, .1):
            all_timelines.extend(timeline(run, diag, width))

    # Ensure C3 OFF matches the same client-log schema and run shape; diagnostics are
    # deliberately unavailable there, so it is a separate, incomplete causal comparator.
    source_by_name = {r["name"]: r for r in runs}
    c3off = source_by_name["C3_OFF_r1"]
    if c3off["config"].get("diagnostics", {}).get("enabled"):
        raise ValueError("C3_OFF unexpectedly has diagnostics enabled")

    write_csv(OUT / "run_comparison.csv", run_rows)
    write_csv(OUT / "paired_wait_http_association.csv", association_rows)
    write_csv(OUT / "source_details.csv", source_rows)
    write_csv(OUT / "timeline_1s.csv", [r for r in all_timelines if r["width_seconds"] == 1.0])
    write_csv(OUT / "timeline_250ms.csv", [r for r in all_timelines if r["width_seconds"] == .25])
    write_csv(OUT / "timeline_100ms.csv", [r for r in all_timelines if r["width_seconds"] == .1])

    # A single row per run/bin-size summarizes observed count clustering without a
    # Poisson fit or significance test. Rates are computed over the generation window.
    arrival_rows = []
    for name, diag in diagnostics.items():
        duration = generation_duration(source_by_name[name])
        for width in (.1, .25, 1.0):
            counts = counts_summary([r["start_elapsed"] for r in diag["requests"]], width, duration)
            arrival_rows.append({"run": name, "bin_width_seconds": width,
                **{k: v for k, v in counts.items() if k != "counts"}})
            for sid in sorted({r["source_id"] for r in diag["requests"]}):
                source_counts = counts_summary([r["start_elapsed"] for r in diag["requests"] if r["source_id"] == sid], width, duration)
                arrival_rows.append({"run": name, "bin_width_seconds": width, "source_id": sid,
                    **{k: v for k, v in source_counts.items() if k != "counts"}})
    write_csv(OUT / "arrival_dispersion.csv", arrival_rows)

    inventory, input_hashes = inventory_and_audit(runs, diagnostics)
    write_csv(OUT / "artifact_inventory.csv", inventory)
    plot_outputs(all_timelines, source_rows)

    manifests = []
    for run in runs:
        source_close_times = []
        for source in read_json(run["raw"] / "source_inventory.json"):
            if run["name"] in DIAGNOSTIC_RUNS:
                events = diagnostics[run["name"]]["source_events"][source["source_id"]]
                source_close_times.extend(e["at"] - run["origin"] for e in events if e["kind"] == "source_closed")
        manifests.append({
            "run": run["name"], "run_id": run["status"]["run_id"],
            "diagnostics_enabled": run["config"].get("diagnostics", {}).get("enabled", False),
            "input_origin_monotonic": run["origin"],
            "generation_seconds": generation_duration(run),
            "source_closed_elapsed_max": max(source_close_times) if source_close_times else None,
            "capture_drops_csv": run["capture_csv"].get("packets_dropped_by_kernel"),
            "capture_drops_pcap": run["capture_pcap"].get("packets_dropped_by_kernel"),
            "verification_accepted": run["verification"]["accepted"],
            "diagnostic_joined_http_count": len(diagnostics[run["name"]]["requests"]) if run["name"] in diagnostics else None,
        })

    manifest = {
        "analysis": "offline descriptive reconstruction; no experiment, container, or traffic execution",
        "repository_branch": "refactor/project-organization",
        "repository_head": "0e8928c71159bedab14c4987e109f5040c28d570",
        "runs": manifests,
        "input_files_sha256": input_hashes,
        "alignment": {
            "origin": "run_status.json experiment_start_monotonic, host CLOCK_MONOTONIC",
            "basis": "source_artifacts/clock_validation.json and diagnostics/victim_clock_validation.json both comparable; same host kernel, zero timens offsets; worker_clock namespace must match victim writer namespace",
            "source_vs_victim_comparison": "same host monotonic domain as validated; 100/250 ms binned coincidence remains descriptive and sensitive to bin boundaries",
            "durations": "source attempt stages within each source clock; handler/work stages within validated victim/worker monotonic clock; HTTP duration from the client record within its own clock",
        },
        "count_windows": "half-open bins [k*w,(k+1)*w) relative to experiment origin; request starts assigned by actual client http_started event",
        "worker_wait": "work_started_at - work_submitted_at from completed handler records; includes scheduler/IPC/queue effects and is not private executor queue time",
        "worker_occupancy": "interval overlap of work_started_at to work_finished_at, clipped to time bins; at most two workers expected",
        "victim_pending": "overlap of work_submitted_at to work_started_at; derived submitted-not-started work, not direct queue-depth telemetry",
        "source_pending": "overlap of source submitted.at to task_started.at; derived ThreadPoolExecutor submitted-not-started work, not a private queue API",
        "drain": "generation horizon read from each run's effective configuration (P5 is 12 s; C3/C5 are 20 s); starts and completions after that horizon are separate, and tail completions do not count as generated rate",
        "limitations": ["one C5 ON repetition", "C3 OFF lacks diagnostic stage events", "no source-container CPU samples", "100/250 ms time-bin results depend on boundary alignment", "host CPU/memory stats are aggregate and cannot exclude local scheduler/frequency effects"],
    }
    (OUT / "analysis_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

    # Include exact 100/250 ms and 1 s rate dispersion on summary rows.
    (OUT / "inventory_note.json").write_text(json.dumps({
        "artifact_inventory": inventory,
        "source_log_integrity": {name: diag["source_audit"] for name, diag in diagnostics.items()},
        "victim_log_integrity": {name: diag["victim_audit"] for name, diag in diagnostics.items()},
    }, indent=2) + "\n")
    print(json.dumps({"runs": RUNS, "outputs": sorted(p.name for p in OUT.iterdir()),
                      "summaries": run_rows, "source_details": source_rows}, indent=2))


if __name__ == "__main__":
    main()
