#!/usr/bin/env python3
"""Generate Chapter 5 exploratory figures from previously audited summaries only."""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from statistics import mean

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parents[1]
FIG = OUT / "figures"
PROCESSED = OUT / "processed"
A2 = ROOT / "reports/a2_endpoint_characterization_20261112"
B1 = ROOT / "reports/b1_attack_characterization_20261112"
B2 = ROOT / "reports/b2_combined_characterization_20261112"

BLUE = "#416A88"       # legitimate/reference
ORANGE = "#A95F30"     # computational asymmetry
GREEN = "#397C69"      # flooding, concurrency 64
GREEN_DARK = "#215647" # flooding, concurrency 96
GREY = "#767D83"
TIMEOUT = "#626A70"
OTHER = "#B8BEC2"
TEXT = "#263238"


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def number(row: dict[str, str], field: str) -> float:
    value = row[field]
    if value == "":
        raise ValueError(f"Missing {field}: {row}")
    return float(value)


def integer(row: dict[str, str], field: str) -> int:
    value = number(row, field)
    if value != int(value):
        raise ValueError(f"Noninteger {field}: {row}")
    return int(value)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def save(fig: plt.Figure, name: str) -> None:
    fig.savefig(FIG / f"{name}.pdf", bbox_inches="tight", facecolor="white")
    fig.savefig(FIG / f"{name}.png", dpi=240, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def write_csv(name: str, data: list[dict]) -> None:
    with (PROCESSED / name).open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(data[0]))
        writer.writeheader()
        writer.writerows(data)


def style() -> None:
    plt.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": 9.5,
        "axes.labelcolor": TEXT, "text.color": TEXT,
        "axes.edgecolor": "#9AA3A8", "xtick.color": TEXT, "ytick.color": TEXT,
        "axes.spines.top": False, "axes.spines.right": False,
        "pdf.fonttype": 42, "savefig.facecolor": "white",
    })


def grid(ax) -> None:
    ax.grid(axis="y", color="#E2E6E8", linewidth=.7, zorder=0)
    ax.set_axisbelow(True)


def figure_b() -> dict:
    source = A2 / "processed/summary.csv"
    manifest = json.loads((A2 / "manifest.json").read_text(encoding="utf-8"))
    data = rows(source)
    by_run = {r["run"]: r for r in data}
    if set(by_run) != {"M_A", "M_B", "E_A", "E_B"} or len(data) != 4:
        raise ValueError("A2 must have exactly four named runs")
    if manifest["runs"] != ["M_A", "M_B", "E_A", "E_B"] or manifest["period_s"] != [0, 60]:
        raise ValueError("A2 manifest differs from declared comparison")
    groups = {"/medium": [by_run["M_A"], by_run["M_B"]],
              "/expensive": [by_run["E_A"], by_run["E_B"]]}
    out = []
    for endpoint, group in groups.items():
        for r in group:
            if r["endpoint"] != endpoint or integer(r, "n_http") != integer(r, "responses_200") or integer(r, "timeouts"):
                raise ValueError(f"A2 endpoint/outcome mismatch: {r['run']}")
            if number(r, "rps_nominal") != 2:
                raise ValueError("A2 traffic mismatch")
            out.append(dict(run=r["run"], endpoint=endpoint, window_start_s=0, window_end_s=60,
                            cpu_worker_mean_ms=number(r, "cpu_worker_mean_ms"),
                            cpu_docker_mean_pct=number(r, "cpu_docker_mean_pct"),
                            http_mean_ms=number(r, "http_mean_ms"),
                            http_2xx=integer(r, "responses_200"), http_starts=integer(r, "n_http"),
                            rps_started=number(r, "rps_started")))
    write_csv("f51b_endpoints.csv", out)

    fig, ax = plt.subplots(figsize=(6.9, 4.2), layout="constrained")
    fig.suptitle("F5.1-B  Custo computacional dos endpoints", fontsize=12, fontweight="bold")
    for x, endpoint in enumerate(groups):
        vals = [number(r, "cpu_worker_mean_ms") for r in groups[endpoint]]
        color = BLUE if endpoint == "/medium" else ORANGE
        for offset, row, value in zip((-.08, .08), groups[endpoint], vals):
            ax.scatter(x + offset, value, s=76, color=color, edgecolors="white", linewidths=.9, zorder=4)
            ax.annotate(row["run"].split("_")[1], (x + offset, value), xytext=(0, 8),
                        textcoords="offset points", ha="center", fontsize=8)
        ax.hlines(mean(vals), x-.19, x+.19, color=TEXT, linewidth=2.2, zorder=3)
        ax.annotate(f"média {mean(vals):.1f}", (x+.21, mean(vals)),
                    xytext=(3, 0), textcoords="offset points", va="center", fontsize=8.5)
    ax.set_xticks([0, 1], ["/medium\n(n=2)", "/expensive\n(n=2)"])
    ax.set_xlim(-.45, 1.55)
    ax.set_ylim(0, max(number(r, "cpu_worker_mean_ms") for r in data)*1.25)
    ax.set_ylabel("CPU média por operação computacional (ms)")
    ax.set_xlabel("Endpoint — duas execuções por condição, [0,60) s")
    grid(ax)
    save(fig, "F5.1-B_custo_endpoints")
    return {"runs": list(by_run), "n_per_endpoint": 2, "means_ms": {k: mean(number(r, "cpu_worker_mean_ms") for r in v) for k, v in groups.items()}}


def figure_d() -> dict:
    source = B1 / "processed/summary.csv"
    manifest = json.loads((B1 / "manifest.json").read_text(encoding="utf-8"))
    by_id = {r["id"]: r for r in rows(source)}
    inventory = {r["id"]: r for r in rows(B1 / "inventario_execucoes.csv")}
    ids = [f"F{i}" for i in range(1, 6)]
    if not all(k in by_id for k in ids) or manifest["attack_interval_s"] != [30, 60]:
        raise ValueError("B1 flooding inventory/window mismatch")
    out = []
    for k in ids:
        r = by_id[k]
        item = inventory[k]
        nominal = number(r, "nominal_rps")
        started = integer(r, "http_started")
        submitted = integer(r, "submitted")
        expired = integer(r, "abandoned_admission")
        if (r["mechanism"] != "flooding" or r["endpoint"] != "/medium" or
            integer(r, "sources") != 2 or submitted-started != expired or
            integer(r, "not_http_started") != expired or
            not np.isclose(number(r, "rps_started"), started/30) or
            number(item, "concurrency") != 64 or
            number(item, "nominal_rps_aggregate") != nominal or
            item["attack_interval"] != "[30,60)" or
            item["campaign"] != manifest["source_runs"][k] or
            integer(r, "timeouts") != 0):
            raise ValueError(f"B1 counts/configuration mismatch in {k}")
        out.append(dict(run=k, nominal_rps=nominal, started_rps=started/30,
                        submitted=submitted, http_started=started,
                        expired_before_http=expired,
                        http_finished_within_rps=number(r, "rps_finished_within"),
                        configured_concurrency=number(item, "concurrency"),
                        window_start_s=30, window_end_s=60))
    write_csv("f51d_flooding.csv", out)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11.8, 4.5), layout="constrained")
    fig.suptitle("F5.1-D  Limite observado de geração do flooding isolado", fontsize=12, fontweight="bold")
    x = [r["nominal_rps"] for r in out]
    y = [r["started_rps"] for r in out]
    ax1.plot([0, max(x)], [0, max(x)], color=GREY, linestyle="--", linewidth=1.2,
             label="Igualdade nominal = iniciado")
    ax1.plot(x, y, color=GREEN, linewidth=2, marker="o", markersize=7,
             label="Inícios HTTP observados")
    for r in out:
        ax1.annotate(f"{r['run']}  {r['started_rps']:.1f}",
                     (r["nominal_rps"], r["started_rps"]),
                     xytext=(5, 7), textcoords="offset points", fontsize=8)
    ax1.set_xlim(0, max(x)*1.10)
    ax1.set_ylim(0, max(x)*1.08)
    ax1.set_xticks(x)
    ax1.set_xlabel("Intensidade ofensiva nominal (RPS)")
    ax1.set_ylabel("Inícios HTTP ofensivos / 30 s (RPS)")
    ax1.set_title("A  Taxa efetivamente iniciada", loc="left", fontweight="bold")
    ax1.legend(loc="upper left", frameon=False, fontsize=8)
    grid(ax1)

    positions = np.arange(len(out))
    bars = ax2.bar(positions, [r["expired_before_http"] for r in out],
                   width=.62, color=GREEN, edgecolor=GREEN_DARK, linewidth=.7)
    for bar, r in zip(bars, out):
        ax2.annotate(f"{r['expired_before_http']:,}".replace(",", "."),
                     (bar.get_x()+bar.get_width()/2, bar.get_height()),
                     xytext=(0, 5), textcoords="offset points", ha="center", fontsize=8.5)
    ax2.set_xticks(positions, ids)
    ax2.set_ylim(0, max(r["expired_before_http"] for r in out)*1.16)
    ax2.set_xlabel("Configuração (32, 64, 128, 192, 256 RPS nominais)")
    ax2.set_ylabel("Admissões expiradas antes do HTTP (contagem)")
    ax2.set_title("B  Tarefas sem início HTTP", loc="left", fontweight="bold")
    grid(ax2)
    fig.supxlabel("Uma execução por intensidade · duas fontes · /medium · concorrência 64 · emissão [30,60) s", fontsize=8)
    save(fig, "F5.1-D_limite_geracao_flooding")
    return {"runs": ids, "nominal_rps": x, "started_rps": y,
            "expired_before_http": [r["expired_before_http"] for r in out]}


def figure_e() -> dict:
    manifest = json.loads((B2 / "manifest.json").read_text(encoding="utf-8"))
    inv = {r["id"]: r for r in rows(B2 / "inventario_execucoes.csv")}
    phase = {(r["id"], r["class"], r["phase"]): r for r in rows(B2 / "processed/phase_summary.csv")}
    summary = {(r["id"], r["class"]): r for r in rows(B2 / "processed/summary.csv")}
    ids = ["B2-L", "B2-A", "B2-F", "B2-F96"]
    labels = ["Somente legítimo\nB2-L", "Assimetria\nB2-A", "Flooding 64\nB2-F", "Flooding 96\nB2-F96"]
    colors = [BLUE, ORANGE, GREEN, GREEN_DARK]
    if not all(k in inv for k in ids):
        raise ValueError("B2 inventory incomplete")
    if not all(inv[k]["path"].startswith("experiment_results/b2-") and
               inv[k]["status"] == "completed" for k in ids):
        raise ValueError("B2 provenance/status mismatch")
    if not all(any(inv[k]["path"] in path for path in manifest["inputs_sha256"])
               for k in ids):
        raise ValueError("B2 manifest lacks a run input")
    if not (number(inv["B2-F"], "attack_nominal_rps") ==
            number(inv["B2-F96"], "attack_nominal_rps") == 64):
        raise ValueError("B2 F64/F96 nominal rates differ")
    if (number(inv["B2-F"], "attack_concurrency") != 64 or
        number(inv["B2-F96"], "attack_concurrency") != 96):
        raise ValueError("B2 F64/F96 concurrency mismatch")
    out = []
    for k in ids:
        r = phase[(k, "benign", "ACTIVE")]
        i = inv[k]
        if (integer(i, "legitimate_sources") != 2 or
            number(i, "legitimate_nominal_rps") != 16 or
            i["legitimate_endpoint"] != "/medium" or
            number(r, "start_s") != 30 or number(r, "end_s") != 60):
            raise ValueError(f"B2 legitimate configuration/window mismatch: {k}")
        starts = integer(r, "started")
        ok = integer(r, "http_2xx_start_cohort")
        timeout = integer(r, "timeout_start_cohort")
        other = integer(r, "other_start_cohort")
        if starts != ok+timeout+other or starts == 0:
            raise ValueError(f"B2 outcome denominator mismatch: {k}")
        attack_rate = (number(summary[(k, "attack")], "rps_started_active")
                       if (k, "attack") in summary else None)
        out.append(dict(run=k, window_start_s=30, window_end_s=60,
                        legitimate_starts=starts, legitimate_2xx=ok,
                        legitimate_timeouts=timeout, legitimate_other=other,
                        success_fraction=ok/starts, timeout_fraction=timeout/starts,
                        other_fraction=other/starts,
                        median_2xx_ms=number(r, "success_median_ms"),
                        n_duration_2xx=ok, attack_nominal_rps=(number(i, "attack_nominal_rps") if k!="B2-L" else ""),
                        attack_started_rps=attack_rate if attack_rate is not None else "",
                        attack_concurrency=i["attack_concurrency"]))
    write_csv("f51e_atendimento_combinado.csv", out)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12.8, 4.7), layout="constrained")
    fig.suptitle("F5.1-E  Atendimento legítimo nos cenários combinados", fontsize=12, fontweight="bold")
    pos = np.arange(4)
    values = [r["median_2xx_ms"] for r in out]
    bars = ax1.bar(pos, values, width=.65, color=colors, edgecolor=TEXT, linewidth=.45)
    for bar, r in zip(bars, out):
        ax1.annotate(f"{r['median_2xx_ms']:.0f} ms\nn={r['n_duration_2xx']}",
                     (bar.get_x()+bar.get_width()/2, bar.get_height()),
                     xytext=(0, 5), textcoords="offset points", ha="center", fontsize=8)
    ax1.set_xticks(pos, labels)
    ax1.set_ylim(0, max(values)*1.22)
    ax1.set_ylabel("Mediana da duração HTTP dos 2xx (ms)")
    ax1.set_title("A  Somente respostas legítimas 2xx", loc="left", fontweight="bold")
    grid(ax1)

    ok = [100*r["success_fraction"] for r in out]
    timeout = [100*r["timeout_fraction"] for r in out]
    other = [100*r["other_fraction"] for r in out]
    ax2.bar(pos, ok, width=.65, color=BLUE, label="HTTP 2xx", edgecolor="white", linewidth=.5)
    ax2.bar(pos, timeout, bottom=ok, width=.65, color=TIMEOUT, label="Timeout do cliente",
            edgecolor="white", linewidth=.5)
    ax2.bar(pos, other, bottom=np.array(ok)+np.array(timeout), width=.65,
            color=OTHER, label="Outros", edgecolor="white", linewidth=.5)
    for x, r in zip(pos, out):
        if r["legitimate_2xx"]:
            ax2.text(x, 100*r["success_fraction"]/2,
                     f"{r['legitimate_2xx']}/{r['legitimate_starts']}",
                     ha="center", va="center", color="white" if r["success_fraction"]>.15 else TEXT,
                     fontsize=8, fontweight="bold")
        if r["legitimate_timeouts"]:
            ax2.text(x, 100*r["success_fraction"]+50*r["timeout_fraction"],
                     f"{r['legitimate_timeouts']} timeouts", ha="center", va="center",
                     color="white", fontsize=8)
    ax2.set_xticks(pos, labels)
    ax2.set_ylim(0, 105)
    ax2.set_ylabel("Desfechos / tentativas legítimas iniciadas (%)")
    ax2.set_title("B  Todas as tentativas legítimas iniciadas", loc="left", fontweight="bold")
    ax2.legend(loc="upper center", ncol=3, frameon=False, fontsize=8, bbox_to_anchor=(.5, 1.02))
    grid(ax2)
    rate64 = next(r["attack_started_rps"] for r in out if r["run"] == "B2-F")
    rate96 = next(r["attack_started_rps"] for r in out if r["run"] == "B2-F96")
    fig.supxlabel(f"ACTIVE [30,60) s · uma execução por condição · flooding: 64 RPS nominais em ambos; "
                 f"HTTP ofensivo iniciado: 64→{rate64:.1f}, 96→{rate96:.1f} RPS", fontsize=8)
    save(fig, "F5.1-E_atendimento_legitimo_combinado")
    return {"runs": ids, "legitimate_outcomes": {r["run"]: [r["legitimate_2xx"],r["legitimate_timeouts"],r["legitimate_other"]] for r in out},
            "flooding_started_rps": {"64": rate64, "96": rate96},
            "flooding_96_has_more_timeouts": out[3]["timeout_fraction"]>out[2]["timeout_fraction"],
            "flooding_96_has_more_http_starts": rate96>rate64}


def main() -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    PROCESSED.mkdir(parents=True, exist_ok=True)
    style()
    checks = {"F5.1-B": figure_b(), "F5.1-D": figure_d(), "F5.1-E": figure_e()}
    inputs = [A2 / "processed/summary.csv", A2 / "manifest.json",
              B1 / "processed/summary.csv", B1 / "inventario_execucoes.csv",
              B1 / "manifest.json",
              B2 / "inventario_execucoes.csv", B2 / "processed/summary.csv",
              B2 / "processed/phase_summary.csv", B2 / "manifest.json"]
    record = {"source_campaigns": ["endpoint-characterization-a2-20261106T200836Z",
                                   "b12-isolated-20261107T200251Z", "b2-l-20261107T232559Z",
                                   "b2-a-20261107T234426Z", "b2-f-20261108T000313Z",
                                   "b2-f96-20261108T002312Z"],
              "inputs_sha256": {str(p.relative_to(ROOT)): sha256(p) for p in inputs},
              "script_sha256": sha256(Path(__file__)), "checks": checks,
              "figures": [str(p.relative_to(OUT)) for p in sorted(FIG.iterdir()) if p.suffix in (".pdf", ".png")],
              "derived": [str(p.relative_to(OUT)) for p in sorted(PROCESSED.glob("*.csv"))]}
    (PROCESSED / "manifest.json").write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(checks, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
