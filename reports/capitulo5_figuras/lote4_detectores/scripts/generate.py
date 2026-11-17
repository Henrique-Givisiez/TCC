#!/usr/bin/env python3
"""Organiza resultados oficiais TEST; não executa detectores nem recalcula IC."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parents[1]
CAMP = ROOT / "experiment_results/scientific-energy-powersaver-20261109"
PLAN = ROOT / "experiments/protocols/energy-powersaver-20261109/plan.json"
SUMMARY = CAMP / "analysis/summary/manifest.json"
VIZ = ROOT / "reports/scientific_campaign_visualization_20261112"
FEATURES = ("request_starts", "ingress_packet_count", "ingress_tcp_payload_length_sum_bytes", "mean_duration_ms")
METHODS = ("zscore", "cov", "ewma", "cusum-freeze")
FNAMES = {"request_starts": "Requisições HTTP iniciadas", "ingress_packet_count": "Pacotes TCP ingressantes",
          "ingress_tcp_payload_length_sum_bytes": "Payload TCP ingressante (bytes)",
          "mean_duration_ms": "Duração média HTTP"}
SHORT = {"request_starts": "Requisições HTTP", "ingress_packet_count": "Pacotes TCP",
         "ingress_tcp_payload_length_sum_bytes": "Payload TCP", "mean_duration_ms": "Duração HTTP"}
MNAMES = {"zscore": "Z-Score", "cov": "CoV", "ewma": "EWMA", "cusum-freeze": "CUSUM-freeze"}
COLORS = {"zscore": "#416A88", "cov": "#A95F30", "ewma": "#215647", "cusum-freeze": "#765B83"}


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def authority(doc: dict, plan_hash: str) -> None:
    a = doc["authority"]
    assert Path(a["plan_path"]).resolve() == PLAN.resolve()
    assert a["plan_sha256"] == plan_hash
    assert "scientific_protocol_direct_c135_o3_20261108.json" in a["protocol"]["path"]


def load() -> tuple[dict, dict[str, dict], dict[str, str]]:
    hashes = {str(PLAN.relative_to(ROOT)): digest(PLAN), str(SUMMARY.relative_to(ROOT)): digest(SUMMARY)}
    plan = json.loads(PLAN.read_text())
    summary = json.loads(SUMMARY.read_text())
    authority(summary, hashes[str(PLAN.relative_to(ROOT))])
    assert summary["kind"] == "scientific-summary" and len(plan["entries"]) == 80
    assert len(summary["evaluations"]) == 240 and not summary["missing_runs"]
    assert summary["eligibility"]["eligible"] == 16 and summary["eligibility"]["ineligible"] == 0
    assert summary["eligibility"]["unknown"] == 0
    test = {e["id"]: e for e in plan["entries"] if e["partition"] == "TEST"}
    assert len(test) == 60
    for block in range(1, 21):
        assert {e["scenario"] for e in test.values() if e["block"] == block} == {"L2", "A3", "F96"}
    assert {s: sum(e["scenario"] == s for e in test.values()) for s in ("L2", "A3", "F96")} == {"L2": 20, "A3": 20, "F96": 20}
    assert set(summary["eligibility"]["combinations"]) == {f"{f}/{m}" for f in FEATURES for m in METHODS}
    assert all(summary["eligibility"]["combinations"].values())
    assert set(summary["results"]) == {f"{f}/{s}/{m}" for f in FEATURES for m in METHODS for s in ("L2", "A3", "F96")}
    assert set(summary["scenario_contrasts"]) == {f"{f}/{m}/A3-F96" for f in FEATURES for m in METHODS}
    assert summary["ci"]["level"] == "0.95" and summary["ci"]["resamples"] == 10000
    assert summary["ci"]["unit"] == "whole_TEST_block"
    for feature in FEATURES:
        for stage in ("calibration", "verification"):
            path = CAMP / "analysis" / feature / stage / "manifest.json"
            doc = json.loads(path.read_text())
            authority(doc, hashes[str(PLAN.relative_to(ROOT))])
            hashes[str(path.relative_to(ROOT))] = digest(path)
            if stage == "calibration":
                assert set(doc["thresholds"]) == set(METHODS)
                assert {src["partition"] for src in doc["sources"]} == {"CAL_A"}
            else:
                assert {src["partition"] for src in doc["sources"]} == {"CAL_B"}
                assert doc["approved"] and all(doc["pair_status"][m]["eligible"] for m in METHODS)
    expected_evals = {(f, eid) for f in FEATURES for eid in test}
    observed_evals = set()
    for item in summary["evaluations"]:
        path = Path(item["path"])
        assert CAMP in path.parents and path.name in test
        assert path.parent.name == "evaluation" and path.parent.parent.name in FEATURES
        observed_evals.add((path.parent.parent.name, path.name))
        manifest = path / "manifest.json"
        assert manifest.is_file() and digest(manifest) == item["manifest_sha256"]
    assert observed_evals == expected_evals
    return summary, test, hashes


def extract(summary: dict, test: dict[str, dict]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    main, supplementary, per_run, contrasts = [], [], [], []
    method_counts = {}
    for method in METHODS:
        for feature in FEATURES:
            data = {s: summary["results"][f"{feature}/{s}/{method}"] for s in ("L2", "A3", "F96")}
            for scenario, result in data.items():
                assert result["n_planned"] == result["n_technical_valid"] == result["n_scientifically_evaluated"] == 20
                assert result["n_ineligible"] == 0 and len(result["per_run"]) == 20
                assert result["means"]["decision_coverage"]["estimate"] == 1.0
                assert result["denominators"]["decision_coverage"] == 20
                for r in result["per_run"]:
                    entry, block, metric = r["entry"], r["block"], r["metrics"]
                    assert test[entry]["scenario"] == scenario and test[entry]["block"] == block
                    assert metric["scientifically_evaluated"] and metric["decision_coverage"] == "1"
                    assert metric["unavailable"] == 0
                    per_run.append({"entry_id": entry, "block": block, "scenario": scenario, "feature": feature,
                                    "method": method, "event_detected": metric["event_detected"],
                                    "recall": metric["recall"], "tp": metric["tp"], "fn": metric["fn"],
                                    "fpr_control": metric["fpr"], "control_available": metric["control"]["available"],
                                    "control_positive": metric["control"]["positive"],
                                    "attack_available": metric["attack"]["available"],
                                    "attack_positive": metric["attack"]["positive"],
                                    "delay_s": metric["observed_delay_seconds"],
                                    "censor_at_seconds": metric["censor_at_seconds"],
                                    "event_deadline_seconds": metric["event_deadline_seconds"],
                                    "post_positive_fraction": metric["post_positive_fraction"],
                                    "post_available": metric["post"]["available"],
                                    "post_positive": metric["post"]["positive"]})
            l2, a3, f96 = data["L2"], data["A3"], data["F96"]
            assert l2["denominators"]["fpr"] == 20
            assert l2["means"]["fpr"]["estimate"] is not None
            row = {"detector": MNAMES[method], "caracteristica": FNAMES[feature],
                   "method": method, "feature": feature,
                   "fpr_L2_pct": 100 * l2["means"]["fpr"]["estimate"]}
            supplement = dict(row)
            supplement.update(fpr_L2_ci_low_pct=100 * l2["means"]["fpr"]["interval"][0],
                              fpr_L2_ci_high_pct=100 * l2["means"]["fpr"]["interval"][1],
                              fpr_L2_method=l2["means"]["fpr"]["method"])
            for scenario, result in (("A3", a3), ("F96", f96)):
                detection = result["detection"]
                recall = result["means"]["recall"]
                delay = result["delay"]
                post = result["means"]["post_positive_fraction"]
                assert detection["n"] == recall["n"] == post["n"] == 20
                assert result["denominators"]["recall"] == 20
                assert detection["successes"] == delay["detected"]
                assert (delay["mean_seconds"] is None) == (delay["detected"] == 0)
                row[f"detected_{scenario}_of_20"] = detection["successes"]
                row[f"recall_{scenario}_pct"] = 100 * recall["estimate"]
                supplement.update({f"detection_{scenario}_pct": 100 * detection["estimate"],
                                   f"detection_{scenario}_ci_low_pct": 100 * detection["interval"][0],
                                   f"detection_{scenario}_ci_high_pct": 100 * detection["interval"][1],
                                   f"detection_{scenario}_ci_method": detection["method"],
                                   f"recall_{scenario}_ci_low_pct": 100 * recall["interval"][0],
                                   f"recall_{scenario}_ci_high_pct": 100 * recall["interval"][1],
                                   f"recall_{scenario}_ci_method": recall["method"],
                                   f"delay_{scenario}_detected_runs": delay["detected"],
                                   f"delay_{scenario}_mean_s": delay["mean_seconds"],
                                   f"delay_{scenario}_median_s": delay["median_seconds"],
                                   f"delay_{scenario}_ci_low_s": delay["interval"][0] if delay["interval"] else None,
                                   f"delay_{scenario}_ci_high_s": delay["interval"][1] if delay["interval"] else None,
                                   f"delay_{scenario}_ci_reason": delay["reason"],
                                   f"post_{scenario}_positive_pct": 100 * post["estimate"],
                                   f"post_{scenario}_ci_low_pct": 100 * post["interval"][0],
                                   f"post_{scenario}_ci_high_pct": 100 * post["interval"][1],
                                   f"post_{scenario}_ci_method": post["method"]})
            main.append(row)
            supplementary.append(supplement)
            contrast = summary["scenario_contrasts"][f"{feature}/{method}/A3-F96"]["recall"]
            ci = contrast["estimate"]
            assert contrast["n_pairs"] == ci["n"] == 20 and contrast["blocks"] == list(range(1, 21))
            assert ci["method"] in ("BCa_block_mean", "Hoeffding_degenerate")
            assert ci["interval"] is not None and ci["level"] == 0.95
            assert ci["replicates"] == 10000 and ci["unit"] == "whole_block"
            contrasts.append({"detector": MNAMES[method], "caracteristica": FNAMES[feature],
                              "method": method, "feature": feature, "contrast": "A3-F96",
                              "n_paired_blocks": contrast["n_pairs"], "estimate_pp": 100 * ci["estimate"],
                              "ci_low_pp": 100 * ci["interval"][0], "ci_high_pp": 100 * ci["interval"][1],
                              "ci_level": ci["level"], "ci_method": ci["method"], "resamples": ci["replicates"]})
            method_counts[ci["method"]] = method_counts.get(ci["method"], 0) + 1
    main, supplementary, per_run, contrasts = map(pd.DataFrame, (main, supplementary, per_run, contrasts))
    assert len(main) == len(supplementary) == len(contrasts) == 16 and len(per_run) == 960
    assert per_run.groupby(["feature", "method", "scenario"]).size().eq(20).all()
    assert per_run.groupby(["feature", "method", "scenario"]).block.nunique().eq(20).all()
    for contrast in contrasts.itertuples():
        group = per_run[(per_run.feature == contrast.feature) & (per_run.method == contrast.method)]
        left = group[group.scenario == "A3"].set_index("block").recall.astype(float).sort_index()
        right = group[group.scenario == "F96"].set_index("block").recall.astype(float).sort_index()
        assert np.isclose(100 * (left - right).mean(), contrast.estimate_pp, atol=1e-9, rtol=0)
    for row in main.itertuples():
        group = per_run[(per_run.feature == row.feature) & (per_run.method == row.method)]
        for scenario in ("A3", "F96"):
            subset = group[group.scenario == scenario]
            assert int(subset.event_detected.sum()) == getattr(row, f"detected_{scenario}_of_20")
            assert np.isclose(100 * subset.recall.astype(float).mean(), getattr(row, f"recall_{scenario}_pct"), atol=1e-9, rtol=0)
        assert np.isclose(100 * group[group.scenario == "L2"].fpr_control.astype(float).mean(), row.fpr_L2_pct, atol=1e-9, rtol=0)
    return main, supplementary, per_run, contrasts, method_counts


def latex_table(main: pd.DataFrame) -> str:
    lines = ["% Requer \\usepackage{booktabs}; resultados oficiais TEST.",
             "\\begin{table}[htbp]", "\\centering", "\\caption{Desempenho dos detectores estatísticos nos cenários ofensivos}",
             "\\label{tab:desempenho-detectores}", "\\small", "\\setlength{\\tabcolsep}{3.5pt}",
             "\\begin{tabular}{@{}lp{3.8cm}rrrrr@{}}", "\\toprule",
             "& & \\multicolumn{1}{c}{\\shortstack{Tráfego\\\\legítimo}} & \\multicolumn{2}{c}{\\shortstack{Ataque\\\\computacional\\\\assimétrico}} & \\multicolumn{2}{c}{\\shortstack{Inundação\\\\HTTP}} " + "\\\\",
             "\\cmidrule(lr){3-3}\\cmidrule(lr){4-5}\\cmidrule(l){6-7}",
             "Detector & Característica & FPR (\\%) & Det. & Recall (\\%) & Det. & Recall (\\%) " + "\\\\", "\\midrule"]
    for index, r in main.iterrows():
        detector = r.detector if index % 4 == 0 else ""
        label = r.caracteristica
        fpr = f"{r.fpr_L2_pct:.2f}".replace(".", ",")
        recall_a = f"{r.recall_A3_pct:.1f}".replace(".", ",")
        recall_f = f"{r.recall_F96_pct:.1f}".replace(".", ",")
        lines.append(f"{detector} & {label} & {fpr} & {int(r.detected_A3_of_20)}/20 & {recall_a} & {int(r.detected_F96_of_20)}/20 & {recall_f} " + "\\\\")
        if index in (3, 7, 11):
            lines.append("\\addlinespace[2pt]")
    lines += ["\\bottomrule", "\\end{tabular}", "\\par\\vspace{2pt}",
              "\\parbox{\\linewidth}{\\footnotesize TEST: 20 execuções por cenário em 20 blocos. FPR: referência legítima L2 em [30,390) s. Det.: execuções com detecção durante ACTIVE; recall: média das proporções por execução nas janelas ofensivas válidas. Latências condicionais, alarmes em POST e IC oficiais constam do arquivo complementar.}",
              "\\end{table}", ""]
    return "\n".join(lines)


def plot_contrasts(contrasts: pd.DataFrame) -> None:
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "pdf.fonttype": 42,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "axes.edgecolor": "#9AA3A8", "text.color": "#263238"})
    fig, axes = plt.subplots(4, 1, figsize=(9.4, 8.0), sharex=True, gridspec_kw={"hspace": .32})
    for ax, method in zip(axes, METHODS):
        subset = contrasts[contrasts.method == method].set_index("feature").loc[list(FEATURES)]
        for i, (feature, r) in enumerate(subset.iterrows()):
            y = 3 - i
            degenerate = r.ci_method == "Hoeffding_degenerate"
            ax.plot([r.ci_low_pp, r.ci_high_pp], [y, y], color=COLORS[method], lw=2.2, solid_capstyle="round")
            ax.plot([r.ci_low_pp, r.ci_low_pp], [y-.09, y+.09], color=COLORS[method], lw=1.2)
            ax.plot([r.ci_high_pp, r.ci_high_pp], [y-.09, y+.09], color=COLORS[method], lw=1.2)
            ax.scatter(r.estimate_pp, y, s=36, marker="D" if degenerate else "o",
                       facecolor="white" if degenerate else COLORS[method], edgecolor=COLORS[method], zorder=3)
        ax.axvline(0, color="#4F575B", lw=.95, zorder=0)
        ax.set_yticks(range(4), [SHORT[f] for f in reversed(FEATURES)])
        ax.set_xlim(-85, 70)
        ax.set_ylim(-.5, 3.5)
        ax.grid(axis="x", color="#E4E8EA", lw=.7)
        ax.set_axisbelow(True)
        ax.set_title(MNAMES[method], loc="left", fontsize=11, fontweight="bold", color=COLORS[method], pad=3)
    axes[-1].set_xticks([-80, -60, -40, -20, 0, 20, 40, 60])
    axes[-1].set_xlabel("Diferença de recall por janela (pontos percentuais)")
    fig.suptitle("Diferenças de recall dos detectores entre os mecanismos ofensivos", fontsize=14,
                 fontweight="bold", y=.995)
    fig.text(.5, .035, "Ataque computacional assimétrico − inundação HTTP · IC 95% oficiais: BCa; losango: Hoeffding em caso degenerado",
             ha="center", fontsize=9, color="#263238")
    fig.subplots_adjust(left=.22, right=.985, top=.93, bottom=.105)
    path = OUT / "figures"
    path.mkdir(parents=True, exist_ok=True)
    for ext, opts in (("pdf", {}), ("png", {"dpi": 240})):
        fig.savefig(path / f"f53b_contrastes_recall.{ext}", bbox_inches="tight", facecolor="white", **opts)
    plt.close(fig)


def main() -> None:
    summary, test, hashes = load()
    main_table, supplementary, per_run, contrasts, methods = extract(summary, test)
    for folder in ("tables", "processed"):
        (OUT / folder).mkdir(parents=True, exist_ok=True)
    main_table.to_csv(OUT / "tables/t53a_desempenho_detectores.csv", index=False)
    (OUT / "tables/t53a_desempenho_detectores.tex").write_text(latex_table(main_table), encoding="utf-8")
    supplementary.to_csv(OUT / "tables/metricas_complementares.csv", index=False)
    per_run.to_csv(OUT / "processed/metricas_por_execucao.csv", index=False)
    contrasts.to_csv(OUT / "processed/contrastes_pareados.csv", index=False)
    plot_contrasts(contrasts)
    checks = {"campaign": "energy-powersaver-20261109", "partition": "TEST", "runs": 60,
              "blocks": 20, "combinations": 16, "metrics_per_run_rows": 960,
              "scenario_contrast": "A3-F96", "ci_level": 0.95, "ci_replicates": 10000,
              "recall_contrast_ci_methods": methods, "calibration_inputs": "CAL_A_only"}
    (OUT / "processed/manifest.json").write_text(json.dumps({"checks": checks, "input_sha256": hashes},
                                                         ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(checks, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
