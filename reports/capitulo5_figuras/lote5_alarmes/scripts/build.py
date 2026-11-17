#!/usr/bin/env python3
"""Decisões TEST oficiais: proporções temporais e POST, sem executar detectores."""

from __future__ import annotations

import hashlib
import json
import sys
from decimal import Decimal
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parents[1]
VIZ = ROOT / "reports/scientific_campaign_visualization_20261112"
CAMP = ROOT / "experiment_results/scientific-energy-powersaver-20261109"
sys.path.insert(0, str(ROOT / "reports/capitulo5_figuras/lote4_detectores/scripts"))
from generate import FEATURES, METHODS, MNAMES, SHORT, load  # noqa: E402

SCENARIOS = (("A3", "Ataque computacional assimétrico", "assimetrico"),
             ("F96", "Inundação HTTP", "flooding"))
FEATURE_NAMES = ("Requisições HTTP", "Pacotes TCP", "Payload TCP", "Duração HTTP")
COLORS = ("#416A88", "#A95F30", "#215647", "#765B83")
STYLES = ("-", "--", "-.", ":")


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def source_rows() -> tuple[pd.DataFrame, dict, dict, dict[str, str]]:
    official, test, hashes = load()
    audit = json.loads((VIZ / "manifest.json").read_text())
    assert audit["campaign"] == "scientific-energy-powersaver-20261109"
    source = VIZ / "processed/detectors.csv"
    hashes[str(source.relative_to(ROOT))] = digest(source)
    rows = pd.read_csv(source, usecols=["entry_id", "scenario", "block", "feature", "method", "t",
                                        "decision", "threshold", "unavailable_reason"])
    assert len(rows) == 60 * 16 * 391 and set(rows.entry_id) == set(test)
    assert set(rows.feature) == set(FEATURES) and set(rows.method) == set(METHODS)
    assert rows.groupby(["entry_id", "feature", "method"]).size().eq(391).all()
    assert rows.groupby(["entry_id", "feature", "method"]).t.nunique().eq(391).all()
    assert set(rows.t) == set(range(1, 392))
    assert rows.apply(lambda r: test[r.entry_id]["scenario"] == r.scenario and
                      test[r.entry_id]["block"] == r.block, axis=1).all()
    grouped = {(entry, feature, method): z.sort_values("t") for (entry, feature, method), z
               in rows.groupby(["entry_id", "feature", "method"], sort=False)}
    # Confronta cada decisão do CSV auditado com o TEST manifest oficial.
    for feature in FEATURES:
        calibration = json.loads((CAMP / "analysis" / feature / "calibration/manifest.json").read_text())
        for entry_id in test:
            path = CAMP / "analysis" / feature / "TEST" / entry_id / "manifest.json"
            hashes[str(path.relative_to(ROOT))] = digest(path)
            doc = json.loads(path.read_text())
            assert doc["evaluated"] and doc["source"]["entry_id"] == entry_id
            assert doc["source"]["partition"] == "TEST"
            for method in METHODS:
                expected = doc["methods"][method]
                z = grouped[(entry_id, feature, method)]
                assert len(expected) == len(z) == 391
                assert np.allclose(z.threshold, float(calibration["thresholds"][method]), atol=1e-12, rtol=0)
                for csv, official_row in zip(z.itertuples(index=False), expected):
                    assert csv.t == int(official_row["window_end_seconds"])
                    assert csv.t - 1 == int(official_row["window_start_seconds"])
                    assert float(official_row["available_at_seconds"]) <= 391
                    decision = official_row["decision"]
                    assert (pd.isna(csv.decision) and decision is None) or (
                        not pd.isna(csv.decision) and csv.decision is decision)
                    assert (pd.isna(csv.unavailable_reason) and official_row["unavailable_reason"] is None) or (
                        csv.unavailable_reason == official_row["unavailable_reason"])
    rows = rows[rows.t.between(31, 390)].copy()
    rows["second"] = rows.t - 1
    assert len(rows) == 60 * 16 * 360
    assert rows.decision.notna().all()
    assert rows.groupby(["entry_id", "feature", "method"]).second.nunique().eq(360).all()
    return rows, official, test, hashes


def per_run_checks(rows: pd.DataFrame, official: dict) -> pd.DataFrame:
    records = []
    grouped = {(entry, feature, method): z.sort_values("second") for (entry, feature, method), z
               in rows.groupby(["entry_id", "feature", "method"], sort=False)}
    for feature in FEATURES:
        for method in METHODS:
            for scenario in ("L2", "A3", "F96"):
                result = official["results"][f"{feature}/{scenario}/{method}"]
                for run in result["per_run"]:
                    metrics = run["metrics"]
                    z = grouped[(run["entry"], feature, method)]
                    assert len(z) == 360 and z.decision.notna().all()
                    assert float(metrics["decision_coverage"]) == 1.0
                    valid = z.decision.astype(bool)
                    pre = z.second.between(30, 149)
                    if scenario != "L2":
                        assert int(valid[pre].sum()) == metrics["pre"]["positive"]
                    if scenario == "L2":
                        assert int(valid.sum()) == metrics["control"]["positive"]
                        assert metrics["control"]["available"] == 360
                        assert np.isclose(float(metrics["fpr"]), valid.mean(), atol=1e-12, rtol=0)
                        continue
                    end = Decimal(metrics["event_deadline_seconds"])
                    start = end - Decimal(metrics["exposure_seconds"])
                    attack = z.second.map(lambda t: Decimal(int(t)) >= start and Decimal(int(t + 1)) <= end)
                    post = z.second.map(lambda t: t >= 270 and Decimal(int(t)) >= end)
                    assert int(attack.sum()) == metrics["attack"]["available"]
                    assert int(post.sum()) == metrics["post"]["available"]
                    assert int(valid[attack].sum()) == metrics["attack"]["positive"]
                    assert int(valid[post].sum()) == metrics["post"]["positive"]
                    assert np.isclose(float(metrics["recall"]), valid[attack].mean(), atol=1e-12, rtol=0)
                    assert np.isclose(float(metrics["post_positive_fraction"]), valid[post].mean(), atol=1e-12, rtol=0)
                    records.append({"entry_id": run["entry"], "block": run["block"], "scenario": scenario,
                                    "feature": feature, "method": method,
                                    "attack_valid_windows": int(attack.sum()),
                                    "attack_positive_windows": int(valid[attack].sum()),
                                    "post_valid_windows": int(post.sum()),
                                    "post_positive_windows": int(valid[post].sum()),
                                    "post_alarm_fraction": float(metrics["post_positive_fraction"]),
                                    "post_alarm_pct": 100 * float(metrics["post_positive_fraction"]),
                                    "event_start_s": float(start), "event_end_s": float(end)})
    result = pd.DataFrame(records)
    assert len(result) == 16 * 2 * 20
    assert result.groupby(["scenario", "feature", "method"]).block.nunique().eq(20).all()
    return result


def temporal(rows: pd.DataFrame) -> pd.DataFrame:
    summary = rows.groupby(["scenario", "method", "feature", "second"], sort=False).decision.agg(
        available_executions="count", alarm_executions=lambda a: int(a.astype(bool).sum())).reset_index()
    summary["alarm_pct"] = 100 * summary.alarm_executions / summary.available_executions
    summary["scheduled_phase"] = np.select([summary.second < 150, summary.second < 270],
                                             ["PRE", "ACTIVE"], default="POST")
    summary["missing_executions"] = 20 - summary.available_executions
    assert len(summary) == 3 * 16 * 360
    assert summary.available_executions.eq(20).all()
    assert summary.alarm_executions.between(0, 20).all()
    return summary


def post_summary(per_run: pd.DataFrame, official: dict) -> pd.DataFrame:
    records = []
    for (scenario, method, feature), z in per_run.groupby(["scenario", "method", "feature"], sort=False):
        estimate = official["results"][f"{feature}/{scenario}/{method}"]["means"]["post_positive_fraction"]
        assert estimate["n"] == len(z) == 20
        assert np.isclose(z.post_alarm_fraction.mean(), estimate["estimate"], atol=1e-12, rtol=0)
        records.append({"scenario": scenario, "method": method, "feature": feature,
                        "post_alarm_mean_pct": 100 * estimate["estimate"],
                        "valid_executions": len(z), "valid_windows_min": int(z.post_valid_windows.min()),
                        "valid_windows_max": int(z.post_valid_windows.max()),
                        "ci_low_pct": 100 * estimate["interval"][0],
                        "ci_high_pct": 100 * estimate["interval"][1],
                        "ci_method": estimate["method"]})
    result = pd.DataFrame(records)
    assert len(result) == 32
    return result


def style() -> None:
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9.5, "pdf.fonttype": 42,
                         "text.color": "#263238", "axes.labelcolor": "#263238",
                         "axes.edgecolor": "#9AA3A8", "axes.spines.top": False,
                         "axes.spines.right": False, "savefig.facecolor": "white"})


def save(fig: plt.Figure, name: str) -> None:
    directory = OUT / "figures"
    directory.mkdir(parents=True, exist_ok=True)
    fig.savefig(directory / f"{name}.pdf", bbox_inches="tight", facecolor="white")
    fig.savefig(directory / f"{name}.png", bbox_inches="tight", facecolor="white", dpi=240)
    plt.close(fig)


def plot_temporal(summary: pd.DataFrame, scenario: str, title: str, stem: str) -> None:
    fig, axes = plt.subplots(4, 1, figsize=(9.5, 8.0), sharex=True,
                             gridspec_kw={"hspace": .14})
    for ax, method in zip(axes, METHODS):
        ax.axvspan(150, 270, color="#E7EBED", zorder=0)
        for boundary in (150, 270):
            ax.axvline(boundary, color="#A9B1B5", lw=.8, zorder=1)
        for feature, label, color, linestyle in zip(FEATURES, FEATURE_NAMES, COLORS, STYLES):
            z = summary[(summary.scenario == scenario) & (summary.method == method) &
                        (summary.feature == feature)].sort_values("second")
            assert len(z) == 360
            xs = np.r_[z.second.to_numpy(), 390]
            ys = np.r_[z.alarm_pct.to_numpy(), z.alarm_pct.iloc[-1]]
            ax.step(xs, ys, where="post", color=color, ls=linestyle, lw=1.15, label=label)
        ax.set_ylim(0, 102)
        ax.set_yticks([0, 50, 100])
        ax.set_xlim(30, 390)
        ax.set_ylabel("Execuções com\nalarme (%)")
        ax.text(.01, .92, MNAMES[method], transform=ax.transAxes, va="top", fontsize=10,
                fontweight="bold", color="#263238")
        ax.grid(axis="y", color="#E2E6E8", lw=.65)
        ax.set_axisbelow(True)
    axes[0].text(210, .91, "Emissão ofensiva", transform=axes[0].get_xaxis_transform(),
                 ha="center", va="top", fontsize=8.5, color="#646D72")
    axes[-1].set_xticks([30, 90, 150, 210, 270, 330, 390])
    axes[-1].set_xlabel("Tempo experimental (s)")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", bbox_to_anchor=(.5, .064),
               ncol=4, frameon=False, fontsize=8.6)
    fig.suptitle(f"Evolução temporal dos alarmes — {title}", fontsize=13,
                 fontweight="bold", y=.994)
    fig.text(.5, .018, "20 execuções por cenário · Proporção por segundo · Decisões válidas",
             ha="center", fontsize=8.5, color="#263238")
    fig.subplots_adjust(left=.13, right=.99, top=.93, bottom=.16)
    save(fig, f"f53c_alarmes_{stem}")


def plot_post(summary: pd.DataFrame) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(9.5, 4.55), sharey=True)
    cmap = plt.get_cmap("cividis")
    for ax, (scenario, title, _) in zip(axes, SCENARIOS):
        matrix = np.array([[summary[(summary.scenario == scenario) & (summary.method == m) &
                                     (summary.feature == f)].post_alarm_mean_pct.iloc[0]
                            for f in FEATURES] for m in METHODS])
        im = ax.imshow(matrix, cmap=cmap, vmin=0, vmax=60, interpolation="nearest", aspect="equal")
        ax.set_title(title, fontsize=11, fontweight="bold", pad=10)
        ax.set_xticks(range(4), ("Requisições\nHTTP", "Pacotes\nTCP", "Payload\nTCP", "Duração\nHTTP"), fontsize=9)
        ax.set_yticks(range(4), [MNAMES[m] for m in METHODS], fontsize=10)
        ax.tick_params(length=0, pad=6)
        ax.set_xticks(np.arange(-.5, 4, 1), minor=True)
        ax.set_yticks(np.arange(-.5, 4, 1), minor=True)
        ax.grid(which="minor", color="white", linewidth=.8)
        ax.tick_params(which="minor", bottom=False, left=False)
        for y in range(4):
            for x in range(4):
                value = matrix[y, x]
                red, green, blue, _ = cmap(value / 60)
                luminance = .2126 * red + .7152 * green + .0722 * blue
                ax.text(x, y, f"{value:.1f}%".replace(".", ","), ha="center", va="center",
                        color="white" if luminance < .48 else "#17202A", fontsize=10, fontweight="bold")
        for spine in ax.spines.values():
            spine.set_visible(False)
    colorbar = fig.colorbar(im, cax=fig.add_axes([.91, .255, .016, .51]), ticks=[0, 15, 30, 45, 60])
    colorbar.set_label("Janelas com alarme (%)", labelpad=9)
    colorbar.outline.set_visible(False)
    fig.suptitle("Alarmes após a emissão ofensiva", fontsize=14, fontweight="bold", y=.96)
    fig.text(.5, .045, "Período pós-ataque [270,390) s · Média das proporções por execução · 20 execuções por cenário",
             ha="center", fontsize=9, color="#263238")
    fig.subplots_adjust(left=.135, right=.89, top=.79, bottom=.21, wspace=.18)
    save(fig, "f53d_alarmes_post")


def main() -> None:
    style()
    rows, official, test, hashes = source_rows()
    by_run = per_run_checks(rows, official)
    per_second = temporal(rows)
    post = post_summary(by_run, official)
    lot4 = ROOT / "reports/capitulo5_figuras/lote4_detectores"
    main_table = pd.read_csv(lot4 / "tables/t53a_desempenho_detectores.csv")
    heatmap_data = pd.read_csv(lot4 / "processed/recalls_e_contrastes.csv")
    complement = pd.read_csv(lot4 / "tables/metricas_complementares.csv")
    for path in (lot4 / "tables/t53a_desempenho_detectores.csv",
                 lot4 / "processed/recalls_e_contrastes.csv",
                 lot4 / "tables/metricas_complementares.csv"):
        hashes[str(path.relative_to(ROOT))] = digest(path)
    assert len(main_table) == len(heatmap_data) == len(complement) == 16
    for row in main_table.itertuples():
        counterpart = heatmap_data[(heatmap_data.method == row.method) &
                                   (heatmap_data.feature == row.feature)].iloc[0]
        other = complement[(complement.method == row.method) &
                           (complement.feature == row.feature)].iloc[0]
        for scenario, _, _ in SCENARIOS:
            z = by_run[(by_run.scenario == scenario) & (by_run.method == row.method) &
                       (by_run.feature == row.feature)]
            calculated = 100 * (z.attack_positive_windows / z.attack_valid_windows).mean()
            expected = getattr(row, f"recall_{scenario}_pct")
            assert np.isclose(calculated, expected, atol=1e-10, rtol=0)
            assert np.isclose(expected, counterpart[f"recall_{scenario}_pct"], atol=1e-12, rtol=0)
            official_post = post[(post.scenario == scenario) & (post.method == row.method) &
                                 (post.feature == row.feature)].post_alarm_mean_pct.iloc[0]
            assert np.isclose(official_post, other[f"post_{scenario}_positive_pct"], atol=1e-10, rtol=0)
    (OUT / "processed").mkdir(parents=True, exist_ok=True)
    (OUT / "tables").mkdir(parents=True, exist_ok=True)
    per_second.to_csv(OUT / "processed/proporcao_alarmes_por_segundo.csv", index=False)
    by_run.to_csv(OUT / "processed/alarmes_post_por_execucao.csv", index=False)
    post.to_csv(OUT / "tables/alarmes_post_resumo.csv", index=False)
    for scenario, title, stem in SCENARIOS:
        plot_temporal(per_second, scenario, title, stem)
    plot_post(post)
    checks = {"campaign": "energy-powersaver-20261109", "partition": "TEST", "executions": len(test),
              "blocks": 20, "combinations": 16, "official_test_manifests_checked": 240,
              "decision_rows_all": 60 * 16 * 391, "decision_rows_30_390": len(rows),
              "valid_executions_per_second_min": int(per_second.available_executions.min()),
              "valid_executions_per_second_max": int(per_second.available_executions.max()),
              "official_attack_recall_checked": len(by_run),
              "official_post_fraction_checked": len(by_run),
              "post_summary_combinations": len(post), "lote4_recall_matches": 32,
              "lote4_post_matches": 32}
    (OUT / "processed/manifest.json").write_text(json.dumps({"checks": checks, "input_sha256": hashes},
                                                         ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(checks, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
