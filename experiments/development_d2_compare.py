"""Descriptive D2 per-run and paired-endpoint comparisons; no causal claim."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from experiments import development_d1_ops as ops
from experiments.development_d2 import validate_plan


def compare(manifest_path):
    manifest_path = Path(manifest_path)
    plan = ops.read(manifest_path)
    validate_plan(manifest_path, check_outputs=False)
    rows = []
    for entry in plan["entries"]:
        if entry.get("role") == "capacity_probe":
            continue
        path = ops.ROOT / entry["outputs"]["review"]
        if not path.is_file():
            raise FileNotFoundError(f"Missing completed run review: {path}")
        review = ops.read(path)
        failed = [c["name"] for c in review["criteria"] if not c["passed"]]
        service = review["service"]
        victim = review["resources"]["victim"]
        proxy = review["resources"]["proxy"]
        cap = next(c for c in review["criteria"] if c["name"] == "capture")
        reports = cap["observed"]["processes"]
        captures = {name: {"accepted": item["accepted"], "returncode": item["returncode"],
                           **item["capture_counters"]} for name, item in reports.items()}
        duration = service["success_duration_2xx_ms"]
        rows.append({
            "entry": entry["id"], "endpoint": entry["endpoint"], "replicate": entry["replicate"],
            "seed": entry["effective_configuration"]["seed"], "order": entry["order"],
            "review_accepted": not failed, "failed_criteria": failed,
            "starts": service["useful_starts"], "nominal_aggregate_rps": service["nominal_aggregate_rps"],
            "effective_aggregate_rps": service["effective_aggregate_rps"], "adherence": service["adherence"],
            "success_2xx": service["cohort_outcomes"]["success_2xx"],
            "http_failures": service["cohort_outcomes"]["http_error"],
            "transport_failures": service["cohort_outcomes"]["transport_error"],
            "client_failures": service["cohort_outcomes"]["client_error"],
            "other_responses": service["cohort_outcomes"]["other_response"],
            "incomplete": service["incomplete_no_end"],
            "duration_2xx_ms": {"support": duration["n"], "mean": duration["mean"], "p50": duration["p50"], "p95": duration["p95"]},
            "victim": {"cpu_mean": victim["cpu_docker_percent"]["mean"],
                       "memory_application_mib_mean": victim["memory_application_mib"]["mean"],
                       "supported": victim["supported_useful_ticks"], "expected": victim["expected_useful_ticks"]},
            "proxy": {"cpu_mean": proxy["sources"]["docker"]["cpu_docker_percent"]["mean"],
                      "memory_raw_bytes_mean": proxy["sources"]["docker"]["memory_raw_bytes"]["mean"],
                      "status_support": proxy["sources"]["status"]["successful_useful"],
                      "docker_support": proxy["sources"]["docker"]["successful_useful"],
                      "expected_slots": 120},
            "captures": captures,
            "drain_seconds": review["timing"]["drain_observed_seconds"]
        })
    paired = {}
    for endpoint in ("/light", "/medium", "/expensive"):
        pair = {row["replicate"]: row for row in rows if row["endpoint"] == endpoint}
        if set(pair) != {"A", "B"}:
            raise ValueError(f"Incomplete endpoint pair: {endpoint}")
        a, b = pair["A"], pair["B"]
        paired[endpoint] = {"A_entry": a["entry"], "B_entry": b["entry"],
                            "same_seed_by_endpoint_pair": a["seed"] == b["seed"],
                            "descriptive": {"starts_A_minus_B": a["starts"]-b["starts"],
                                            "effective_rps_A_minus_B": float(a["effective_aggregate_rps"])-float(b["effective_aggregate_rps"]),
                                            "mean_ms_A_minus_B": float(a["duration_2xx_ms"]["mean"])-float(b["duration_2xx_ms"]["mean"]),
                                            "p50_ms_A_minus_B": float(a["duration_2xx_ms"]["p50"])-float(b["duration_2xx_ms"]["p50"]),
                                            "p95_ms_A_minus_B": float(a["duration_2xx_ms"]["p95"])-float(b["duration_2xx_ms"]["p95"]),
                                            "victim_cpu_mean_A_minus_B": float(a["victim"]["cpu_mean"])-float(b["victim"]["cpu_mean"]),
                                            "victim_memory_MiB_A_minus_B": float(a["victim"]["memory_application_mib_mean"])-float(b["victim"]["memory_application_mib_mean"]),
                                            "proxy_cpu_mean_A_minus_B": float(a["proxy"]["cpu_mean"])-float(b["proxy"]["cpu_mean"]),
                                            "proxy_memory_bytes_A_minus_B": float(a["proxy"]["memory_raw_bytes_mean"])-float(b["proxy"]["memory_raw_bytes_mean"])}}
    work = {"/light": 10000, "/medium": 100000, "/expensive": 1000000}
    report = {"schema_version": 1, "manifest": str(manifest_path), "manifest_sha256": ops.sha(manifest_path),
              "instrumentation_commit": plan["instrumentation_commit"], "probe_review": plan["probe"]["review_path"],
              "common_aggregate_rps": 4, "runs": rows, "paired_replicates": paired,
              "server_operation_work_units_per_request": work,
              "interpretation_limits": ["Work-unit ratios are not measured duration or cost ratios.",
                                        "Two explorative repetitions per endpoint do not establish a population effect.",
                                        "Seed pairing does not guarantee identical timing trajectories.",
                                        "Order, environment and collection quality can confound endpoint differences; interpret together with per-run evidence.",
                                        "p95 is descriptive for D2, not an automatic cross-endpoint pass threshold.",
                                        "Victim CPU is aggregate/cached; proxy CPU includes monitoring; memory conventions differ."]}
    out_json = ops.ROOT / plan["comparison_outputs"]["json"]
    out_md = ops.ROOT / plan["comparison_outputs"]["markdown"]
    if out_json.exists() or out_md.exists():
        raise FileExistsError("Comparison output exists; refusing overwrite")
    ops.put(out_json, report)
    columns = ("entry", "endpoint", "replicate", "seed", "starts", "effective_aggregate_rps", "adherence", "success_2xx",
               "http_failures", "transport_failures", "incomplete", "mean_ms", "p50_ms", "p95_ms", "victim_cpu", "victim_mem_MiB",
               "proxy_cpu", "proxy_mem_bytes", "victim_support", "proxy_status", "proxy_docker", "csv_drops", "pcap_drops")
    lines = ["# DEVELOPMENT D2 — comparação exploratória por execução", "", "Taxa comum configurada: 4 RPS agregados; p95 mostrado apenas como métrica descritiva.",
             "", "| " + " | ".join(columns) + " |", "|" + "---|" * len(columns)]
    for row in rows:
        duration, victim, proxy, captures = row["duration_2xx_ms"], row["victim"], row["proxy"], row["captures"]
        vals = [row["entry"], row["endpoint"], row["replicate"], row["seed"], row["starts"], row["effective_aggregate_rps"], row["adherence"],
                row["success_2xx"], row["http_failures"], row["transport_failures"], row["incomplete"], duration["mean"], duration["p50"], duration["p95"],
                victim["cpu_mean"], victim["memory_application_mib_mean"], proxy["cpu_mean"], proxy["memory_raw_bytes_mean"],
                f"{victim['supported']}/{victim['expected']}", f"{proxy['status_support']}/120", f"{proxy['docker_support']}/120",
                captures["csv"]["packets_dropped_by_kernel"], captures["pcap"]["packets_dropped_by_kernel"]]
        lines.append("| " + " | ".join(map(str, vals)) + " |")
    lines += ["", "Pareamento A/B usa seeds comuns entre endpoints dentro de cada repetição. As duas sequências cíclicas invertem a ordem relativa dos endpoints; não eliminam deriva ambiental nem efeitos de ordem.",
              "As iterações 10× das rotas são especificações do código, não uma razão de custo medido. Não atribua diferenças automaticamente ao endpoint sem inspecionar suporte, capturas, aderência, ordem e evidência por run."]
    with out_md.open("x") as stream:
        stream.write("\n".join(lines)+"\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    report = compare(args.manifest)
    print(json.dumps({"runs": len(report["runs"]), "paired_endpoints": list(report["paired_replicates"]),
                      "comparison": report["manifest"]}))


if __name__ == "__main__":
    main()
