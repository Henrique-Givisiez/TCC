"""Write a cumulative, evidence-linked D1 continuation synthesis."""
from __future__ import annotations

import json
from pathlib import Path

from experiments import development_d1_ops as ops


def create():
    plan, _ = ops.get_plan()
    base = ops.BASE
    out_json = base / "analysis/d1_final_synthesis_capturefix_v2.json"
    out_md = base / "analysis/d1_final_synthesis_capturefix_v2.md"
    if out_json.exists() or out_md.exists():
        raise FileExistsError("Synthesis output exists; refusing overwrite")
    original = ops.read(ops.MANIFEST)
    entries = {e["id"]: e for e in original["entries"]}
    entries.update({e["id"]: e for e in plan["entries"]})
    runs = []
    for entry_id in plan["attempt_order"]:
        entry = entries[entry_id]
        review_path = ops.ROOT / entry["outputs"]["review"]
        if not review_path.is_file():
            runs.append({"entry": entry_id, "level": entry["level"], "replicate": entry["replicate"],
                         "status": "not_run", "accepted": False, "review_path": None})
            continue
        review = ops.read(review_path)
        service = review.get("service", {})
        victim = review.get("resources", {}).get("victim", {})
        proxy = review.get("resources", {}).get("proxy", {}).get("sources", {}).get("docker", {})
        criterion = next((c for c in review.get("criteria", []) if c.get("name") == "capture"), {})
        evidence = criterion.get("observed", {})
        processes = evidence.get("processes", {}) if isinstance(evidence, dict) else {}
        accepted = all(c.get("passed") for c in review.get("criteria", []))
        runs.append({
            "entry": entry_id, "level": entry["level"], "replicate": entry["replicate"],
            "seed": entry["effective_configuration"]["seed"],
            "status": "preserved_technical_failure" if entry_id == "d1_L04_B" else ("accepted" if accepted else "rejected"),
            "accepted": accepted, "failed_criteria": [c["name"] for c in review.get("criteria", []) if not c.get("passed")],
            "review_path": str(entry["outputs"]["review"]),
            "service": {"nominal_rps": service.get("nominal_aggregate_rps"), "starts": service.get("useful_starts"),
                        "effective_rps": service.get("effective_aggregate_rps"), "adherence": service.get("adherence"),
                        "success_2xx": service.get("cohort_outcomes", {}).get("success_2xx"),
                        "http_failures": service.get("cohort_outcomes", {}).get("http_error"),
                        "transport_failures": service.get("cohort_outcomes", {}).get("transport_error"),
                        "client_failures": service.get("cohort_outcomes", {}).get("client_error"),
                        "other_responses": service.get("cohort_outcomes", {}).get("other_response"),
                        "incomplete": service.get("incomplete_no_end"), "late_starts": service.get("late_starts"),
                        "success_duration_2xx_ms": service.get("success_duration_2xx_ms")},
            "resources": {"victim_cpu_mean": victim.get("cpu_docker_percent", {}).get("mean"),
                          "victim_memory_application_mib_mean": victim.get("memory_application_mib", {}).get("mean"),
                          "victim_support": f"{victim.get('supported_useful_ticks', 0)}/{victim.get('expected_useful_ticks', 0)}",
                          "proxy_cpu_mean": proxy.get("cpu_docker_percent", {}).get("mean"),
                          "proxy_memory_raw_bytes_mean": proxy.get("memory_raw_bytes", {}).get("mean"),
                          "proxy_support": f"{proxy.get('successful_useful', 0)}/{proxy.get('attempted_useful', 0)}"},
            "capture": {"criterion_passed": criterion.get("passed"), "instrumentation": "capturefix" if processes else "legacy",
                        "reports": {k: v.get("capture_counters") for k, v in processes.items() if v},
                        "legacy_diagnostic": evidence.get("diagnostics") if isinstance(evidence, dict) else None}
        })
    pairs = {}
    for level in (4, 5):
        path = base / "analysis" / f"d1_L{level:02d}_pair_review.json"
        pairs[f"L{level:02d}"] = ops.read(path).get("replicas_accepted") if path.is_file() else None
    highest = max((int(level[1:]) for level, ok in pairs.items() if ok), default=3)
    if highest >= 5:
        range_text = "Critérios atendidos até 64 RPS agregados, o teto testado; sem estimativa de capacidade máxima."
    elif highest >= 4:
        range_text = "Critérios atendidos até 32 RPS agregados (L04); L05/64 RPS não foi aceito ou não foi concluído."
    else:
        range_text = "Nenhum par acima de L03/16 RPS agregados foi aceito."
    report = {"schema_version": 1, "continuation_manifest": str(ops.CONTINUATION.relative_to(ops.ROOT)),
              "continuation_manifest_sha256": ops.sha(ops.CONTINUATION), "instrumentation_commit": plan["instrumentation_commit"],
              "maximum_attempts": plan["maximum_attempts"], "attempt_order": plan["attempt_order"], "runs": runs,
              "pairs": pairs, "highest_accepted_level": f"L{highest:02d}", "range_conclusion": range_text,
              "instrumentation_comparability": "L01–L04/B original used legacy capture evidence; d1_L04_B_CF1 and subsequent runs use capturefix. Original configs, seeds, service criteria and L01 reference remain bound to the original plan. The original d1_L04_B remains a technical failure.",
              "resource_limits": ["Victim CPU is aggregated/cached, not per-logical-CPU utilization.",
                                  "Victim memory follows the application-memory convention; proxy memory is raw and includes cache.",
                                  "Proxy CPU includes monitor workload."],
              "no_capacity_claim": "Passing through 64 RPS is attainment at the tested ceiling only; do not extend the grid automatically."}
    ops.put(out_json, report)
    cols = ("entry", "status", "nominal_rps", "starts", "effective_rps", "adherence", "success_2xx",
            "http_failures", "transport_failures", "client_failures", "incomplete", "mean_ms", "p50_ms", "p95_ms",
            "victim_cpu_mean", "victim_memory_application_mib_mean", "proxy_cpu_mean", "proxy_memory_raw_bytes_mean", "capture")
    lines = ["# Síntese DEVELOPMENT D1", "", range_text, "",
             f"Instrumentação capturefix vinculada ao commit `{plan['instrumentation_commit']}`. A tentativa d1_L04_B original permanece falha técnica; d1_L04_B_CF1 é o representante B aceito de L04.",
             "", "| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for row in runs:
        service, resources = row.get("service", {}), row.get("resources", {})
        duration = service.get("success_duration_2xx_ms") or {}
        values = {**row, **service, **resources, "mean_ms": duration.get("mean"), "p50_ms": duration.get("p50"),
                  "p95_ms": duration.get("p95"), "capture": row.get("capture", {}).get("instrumentation")}
        lines.append("| " + " | ".join(str(values.get(c, "")) for c in cols) + " |")
    lines += ["", "Pareamento por seed não implica trajetórias idênticas. CPU da vítima é agregada/cached; CPU do proxy inclui monitoramento. As convenções de memória diferem.",
              "Capturas legadas não têm relatórios independentes por processo; capturefix exige estatísticas completas e zero drops em CSV e PCAP.",
              "A aprovação no teto testado não autoriza ampliar a grade."]
    with out_md.open("x") as stream:
        stream.write("\n".join(lines) + "\n")
    return {"synthesis": str(out_json), "pairs": pairs, "highest_accepted_level": f"L{highest:02d}"}


if __name__ == "__main__":
    print(json.dumps(create()))
