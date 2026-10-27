"""Write an auditable descriptive D2 synthesis; never starts experiments."""
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
        review_path = ops.ROOT / entry["outputs"]["review"]
        base = {"entry": entry["id"], "endpoint": entry["endpoint"], "replicate": entry["replicate"],
                "role": entry.get("role"), "order": entry["order"], "seed": entry["effective_configuration"]["seed"]}
        if not review_path.is_file():
            rows.append({**base, "status": "not_reviewed"})
            continue
        review = ops.read(review_path)
        failed = [c["name"] for c in review["criteria"] if not c["passed"]]
        service = review["service"]
        victim, proxy = review["resources"]["victim"], review["resources"]["proxy"]
        cap = next(c for c in review["criteria"] if c["name"] == "capture")
        captures = {name: {"accepted": p["accepted"], "returncode": p["returncode"], **p["capture_counters"]}
                    for name, p in cap["observed"]["processes"].items()}
        dur = service["success_duration_2xx_ms"]
        rows.append({**base, "status": "reviewed", "review_accepted": not failed, "failed_criteria": failed,
            "starts": service["useful_starts"], "nominal_aggregate_rps": service["nominal_aggregate_rps"],
            "effective_aggregate_rps": service["effective_aggregate_rps"], "adherence": service["adherence"],
            "success_2xx": service["cohort_outcomes"]["success_2xx"], "http_failures": service["cohort_outcomes"]["http_error"],
            "transport_failures": service["cohort_outcomes"]["transport_error"], "client_failures": service["cohort_outcomes"]["client_error"],
            "other_responses": service["cohort_outcomes"]["other_response"], "incomplete": service["incomplete_no_end"],
            "duration_2xx_ms": {"support": dur["n"], "mean": dur["mean"], "p50": dur["p50"], "p95": dur["p95"]},
            "victim": {"cpu_mean": victim["cpu_docker_percent"]["mean"], "memory_application_mib_mean": victim["memory_application_mib"]["mean"],
                       "supported": victim["supported_useful_ticks"], "expected": victim["expected_useful_ticks"]},
            "proxy": {"cpu_mean": proxy["sources"]["docker"]["cpu_docker_percent"]["mean"],
                      "memory_raw_bytes_mean": proxy["sources"]["docker"]["memory_raw_bytes"]["mean"],
                      "status_support": proxy["sources"]["status"]["successful_useful"], "docker_support": proxy["sources"]["docker"]["successful_useful"], "expected_slots": 120},
            "captures": captures, "drain_seconds": review["timing"]["drain_observed_seconds"]})
    comparative = [r for r in rows if r.get("role") == "comparative" and r["status"] == "reviewed"]
    paired = {}
    for endpoint in ("/light", "/medium", "/expensive"):
        pair = {r["replicate"]: r for r in comparative if r["endpoint"] == endpoint}
        if set(pair) != {"A", "B"}:
            paired[endpoint] = {"status": "incomplete", "available": sorted(pair)}
            continue
        a, b = pair["A"], pair["B"]
        paired[endpoint] = {"status": "complete", "same_seed": a["seed"] == b["seed"],
            "A_minus_B": {"starts": a["starts"]-b["starts"], "effective_rps": float(a["effective_aggregate_rps"])-float(b["effective_aggregate_rps"]),
            **{f"{metric}_ms": float(a["duration_2xx_ms"][metric])-float(b["duration_2xx_ms"][metric]) for metric in ("mean", "p50", "p95")},
            "success_2xx": a["success_2xx"]-b["success_2xx"], "http_failures": a["http_failures"]-b["http_failures"],
            "transport_failures": a["transport_failures"]-b["transport_failures"], "incomplete": a["incomplete"]-b["incomplete"],
            "victim_cpu_mean": float(a["victim"]["cpu_mean"])-float(b["victim"]["cpu_mean"]),
            "victim_memory_MiB": float(a["victim"]["memory_application_mib_mean"])-float(b["victim"]["memory_application_mib_mean"]),
            "proxy_cpu_mean": float(a["proxy"]["cpu_mean"])-float(b["proxy"]["cpu_mean"]),
            "proxy_memory_bytes": float(a["proxy"]["memory_raw_bytes_mean"])-float(b["proxy"]["memory_raw_bytes_mean"])}}
    within = {}
    for rep in ("A", "B"):
        ordered = sorted((r for r in comparative if r["replicate"] == rep), key=lambda r:r["order"])
        within[rep] = [{"earlier": x["endpoint"], "later": y["endpoint"], "earlier_entry": x["entry"], "later_entry": y["entry"],
                        "p95_later_minus_earlier_ms": float(y["duration_2xx_ms"]["p95"])-float(x["duration_2xx_ms"]["p95"])} for x,y in zip(ordered, ordered[1:])]
    work = {"/light":10000,"/medium":100000,"/expensive":1000000}
    report = {"schema_version":2,"manifest":str(manifest_path),"manifest_sha256":ops.sha(manifest_path),
        "instrumentation_commit":plan["instrumentation_commit"],"common_aggregate_rps":4,"runs":rows,"paired_replicates":paired,
        "within_replicate_ordered_endpoint_contrasts_p95":within,"server_operation_work_units_per_request":work,
        "interpretation_limits":["Work-unit ratios are not measured duration or cost ratios.","Two repetitions are exploratory and descriptive.",
        "Seed pairing does not guarantee identical timing trajectories.","Opposite A/B pair precedence does not eliminate period effects or environmental drift.",
        "p95 is descriptive in D2, with no inherited absolute D1 limit.","Victim CPU is aggregate/cached; proxy CPU includes monitoring; memory conventions differ.",
        "Client in-flight requests are observed client concurrency, not direct server queue or tasks waiting to send."]}
    out_json, out_md = (ops.ROOT / plan["comparison_outputs"][k] for k in ("json","markdown"))
    if out_json.exists() or out_md.exists(): raise FileExistsError("Comparison output exists; refusing overwrite")
    ops.put(out_json, report)
    cols = ["entry","endpoint","replicate","status","starts","effective_aggregate_rps","success_2xx","http_failures","transport_failures","incomplete","mean","p50","p95","victim_cpu","victim_mem_MiB","proxy_cpu","proxy_mem_bytes","capture_csv_drops","capture_pcap_drops"]
    lines=["# DEVELOPMENT D2 — síntese exploratória","","Ordem A: light → medium → expensive; B: expensive → medium → light. A inversão muda a precedência dos pares, mas não elimina efeitos de período/deriva. p95 é descritivo.","","|"+"|".join(cols)+"|","|"+"---|"*len(cols)]
    for r in rows:
        if r["status"] != "reviewed": vals=[r["entry"],r["endpoint"],r["replicate"],"não revisado"]+(["—"]*(len(cols)-4))
        else:
            d,v,p,c=r["duration_2xx_ms"],r["victim"],r["proxy"],r["captures"]
            vals=[r["entry"],r["endpoint"],r["replicate"],"aceito" if r["review_accepted"] else "reprovado",r["starts"],r["effective_aggregate_rps"],r["success_2xx"],r["http_failures"],r["transport_failures"],r["incomplete"],d["mean"],d["p50"],d["p95"],v["cpu_mean"],v["memory_application_mib_mean"],p["cpu_mean"],p["memory_raw_bytes_mean"],c.get("csv",{}).get("packets_dropped_by_kernel"),c.get("pcap",{}).get("packets_dropped_by_kernel")]
        lines.append("|"+"|".join(map(str,vals))+"|")
    lines += ["","### Contrastes dentro de cada ordem","",json.dumps(within,ensure_ascii=False,indent=2),"","### Diferenças pareadas A − B por endpoint","",json.dumps(paired,ensure_ascii=False,indent=2),"","Interprete junto de suporte, captura, aderência e ambiente. Recursos e latências são medidas descritivas; as diferenças não são atribuídas automaticamente ao endpoint. O resultado informa planejamento de D3, não capacidade nem razão de custo."]
    with out_md.open("x") as f:f.write("\n".join(lines)+"\n")
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--manifest",type=Path,required=True);a=p.parse_args()
    report=compare(a.manifest);print(json.dumps({"runs":len(report["runs"]),"reviewed":sum(x["status"]=="reviewed" for x in report["runs"]),"comparison":report["manifest"]}))

if __name__=="__main__":main()
