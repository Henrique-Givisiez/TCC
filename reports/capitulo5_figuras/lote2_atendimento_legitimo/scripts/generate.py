#!/usr/bin/env python3
"""Figuras descritivas do atendimento legítimo, campanha TEST definitiva."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import FuncFormatter, FixedLocator


ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "reports/scientific_campaign_visualization_20261112"
TEMPORAL = ROOT / "reports/investigacao-temporal-energy-20261110"
PLAN = ROOT / "experiments/protocols/energy-powersaver-20261109/plan.json"
SCENARIOS = ("L2", "A3", "F96")
NAMES = {
    "L2": "Tráfego legítimo",
    "A3": "Ataque computacional assimétrico",
    "F96": "Inundação HTTP",
}
COLORS = {"L2": "#416A88", "A3": "#A95F30", "F96": "#215647"}
STYLES = {"L2": "-", "A3": "--", "F96": "-."}
TEXT = "#263238"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def checked(path: Path, hashes: dict[str, str]) -> Path:
    assert path.is_file(), path
    hashes[str(path.relative_to(ROOT))] = sha256(path)
    return path


def style() -> None:
    plt.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": 9.5,
        "axes.labelcolor": TEXT, "text.color": TEXT,
        "axes.edgecolor": "#9AA3A8", "xtick.color": TEXT, "ytick.color": TEXT,
        "axes.spines.top": False, "axes.spines.right": False,
        "pdf.fonttype": 42, "savefig.facecolor": "white",
    })


def save(fig: plt.Figure, name: str) -> None:
    target = OUT / "figures"
    target.mkdir(parents=True, exist_ok=True)
    fig.savefig(target / f"{name}.pdf", bbox_inches="tight", facecolor="white")
    fig.savefig(target / f"{name}.png", bbox_inches="tight", facecolor="white", dpi=240)
    plt.close(fig)


def phase_background(ax: plt.Axes) -> None:
    ax.axvspan(150, 270, color="#E7EBED", zorder=0)
    for boundary in (150, 270):
        ax.axvline(boundary, color="#A9B1B5", lw=.8, zorder=1)
    ax.set_xlim(30, 390)
    ax.set_xticks([30, 90, 150, 210, 270, 330, 390])
    ax.grid(axis="y", color="#E2E6E8", lw=.7)
    ax.set_axisbelow(True)


def validate_and_load() -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    hashes: dict[str, str] = {}
    plan = json.loads(checked(PLAN, hashes).read_text())
    entries = [e for e in plan["entries"] if e["partition"] == "TEST"]
    expected = {e["id"]: (e["scenario"], int(e["block"])) for e in entries}
    assert len(expected) == 60
    assert all(sum(sc == s for sc, _ in expected.values()) == 20 for s in SCENARIOS)
    assert {b for _, b in expected.values()} == set(range(1, 21))
    for b in range(1, 21):
        assert {s for s, bb in expected.values() if bb == b} == set(SCENARIOS)

    inventory = pd.read_csv(checked(SOURCE / "inventario_execucoes.csv", hashes))
    inventory = inventory[inventory.partition == "TEST"].copy()
    assert set(inventory.entry_id) == set(expected)
    assert all(expected[r.entry_id] == (r.scenario, int(r.block)) for r in inventory.itertuples())
    assert inventory.status.eq("completed").all()
    assert inventory.legitimate_sources.eq(2).all() and inventory.legitimate_nominal_rps.eq(16).all()
    for r in inventory.itertuples():
        cfg = json.loads(checked(ROOT / r.path / "dataset/metadata/effective_config.json", hashes).read_text())
        assert cfg["normal_traffic"]["request_timeout_seconds"] == 2.0
        assert cfg["attack"]["request_timeout_seconds"] == 2.0
        assert cfg["attack"]["start_seconds"] == 150
        assert cfg["attack"]["duration_seconds"] == 120

    viz_manifest = json.loads(checked(SOURCE / "manifest.json", hashes).read_text())
    assert viz_manifest["campaign"] == "scientific-energy-powersaver-20261109"
    temporal_inputs = json.loads(checked(TEMPORAL / "manifesto_entradas.json", hashes).read_text())
    assert "scientific-energy-powersaver-20261109" in json.dumps(temporal_inputs)

    series = pd.read_csv(checked(TEMPORAL / "series_1s.csv", hashes))
    assert len(series) == 60 * 390
    assert set(series.id) == set(expected)
    assert all(expected[r.id][0] == r.scenario for r in series[["id", "scenario"]].drop_duplicates().itertuples(index=False))
    assert series.groupby("id").second.apply(lambda x: x.tolist() == list(range(390))).all()
    series = series[(series.second >= 30) & (series.second < 390)].copy()
    assert len(series) == 60 * 360
    assert series.loc[series.benign_ok.eq(0), "benign_duration_2xx_ms"].isna().all()
    assert series.loc[series.benign_ok.gt(0), "benign_duration_2xx_ms"].notna().all()

    phases = pd.read_csv(checked(SOURCE / "processed/http_phases.csv", hashes))
    active = phases[(phases["class"] == "benign") & (phases.phase == "ACTIVE")].copy()
    assert len(active) == 60 and set(active.entry_id) == set(expected)
    assert all(expected[r.entry_id] == (r.scenario, int(r.block)) for r in active.itertuples())
    assert active.started.gt(0).all()
    assert (active.http_2xx_cohort + active.timeout_cohort + active.other_cohort == active.started).all()
    by_run = series[(series.second >= 150) & (series.second < 270)].groupby("id")[["benign_http_start", "benign_ok", "benign_timeout"]].sum()
    compared_duration_bins = 0
    max_individual_2xx_ms = 0.0
    individual_2xx_above_timeout = 0
    for r in active.itertuples():
        assert (by_run.loc[r.entry_id].to_numpy() == [r.started, r.http_2xx_cohort, r.timeout_cohort]).all()
        http = pd.read_csv(checked(SOURCE / "processed" / f"http_{r.entry_id}.csv", hashes))
        benign = http[http.traffic_class == "benign"].copy()
        benign["second"] = np.floor(benign.elapsed_seconds).astype(int)
        observed_2xx = benign[(benign.category == "http_2xx") & benign.elapsed_seconds.between(30, 390, inclusive="left")]
        max_individual_2xx_ms = max(max_individual_2xx_ms, float(observed_2xx.duration_ms.max()))
        individual_2xx_above_timeout += int(observed_2xx.duration_ms.gt(2000).sum())
        active_http = benign[(benign.elapsed_seconds >= 150) & (benign.elapsed_seconds < 270)]
        cats = active_http.category.value_counts()
        assert cats.get("http_2xx", 0) == r.http_2xx_cohort
        assert cats.get("timeout", 0) == r.timeout_cohort
        assert len(active_http) - cats.get("http_2xx", 0) - cats.get("timeout", 0) == r.other_cohort
        valid = benign[(benign.category == "http_2xx") & benign.second.between(30, 389)]
        means = valid.groupby("second").duration_ms.mean()
        observed = series[series.id == r.entry_id].set_index("second").benign_duration_2xx_ms
        assert set(means.index) == set(observed[observed.notna()].index)
        assert np.allclose(means.to_numpy(), observed.loc[means.index].to_numpy(), atol=1e-9, rtol=0)
        compared_duration_bins += len(means)

    official = pd.read_csv(checked(SOURCE / "processed/official_availability.csv", hashes))
    assert len(official) == 60 and set(official.entry_id) == set(expected)
    comparison = active.merge(official, on=["entry_id", "scenario", "block"], validate="one_to_one")
    assert len(comparison) == 60
    assert (comparison.http_2xx_cohort == comparison.timely_2xx).all()
    checks = {
        "campaign": "energy-powersaver-20261109", "partition": "TEST",
        "runs": 60, "complete_blocks": 20, "runs_per_scenario": 20,
        "client_timeout_seconds": 2.0,
        "duration_bins_crosschecked_with_http_csv": compared_duration_bins,
        "max_individual_benign_2xx_ms_30_390": max_individual_2xx_ms,
        "individual_benign_2xx_above_2000_ms_30_390": individual_2xx_above_timeout,
        "official_denominator_diff_runs": int((comparison.started != comparison.starts).sum()),
        "official_denominator_diff_by_scenario": {
            s: int(((comparison.scenario == s) & (comparison.started != comparison.starts)).sum())
            for s in SCENARIOS
        },
        "active_outcomes": {
            s: {k: int(v) for k, v in active[active.scenario == s][["started", "http_2xx_cohort", "timeout_cohort", "other_cohort"]].sum().items()}
            for s in SCENARIOS
        },
    }
    return series, active, {"hashes": hashes, "checks": checks}


def derive_duration(series: pd.DataFrame, meta: dict) -> pd.DataFrame:
    summary = (series.groupby(["scenario", "second"], sort=True).benign_duration_2xx_ms
               .agg(valid_executions="count", median_ms="median",
                    q1_ms=lambda x: x.quantile(.25), q3_ms=lambda x: x.quantile(.75))
               .reset_index())
    assert len(summary) == 3 * 360
    summary.loc[summary.valid_executions.eq(0), ["median_ms", "q1_ms", "q3_ms"]] = np.nan
    assert (summary.median_ms.isna() == summary.q1_ms.isna()).all()
    assert (summary.median_ms.isna() == summary.q3_ms.isna()).all()
    assert (summary.loc[summary.valid_executions.gt(0), "q1_ms"] <= summary.loc[summary.valid_executions.gt(0), "median_ms"]).all()
    assert (summary.loc[summary.valid_executions.gt(0), "median_ms"] <= summary.loc[summary.valid_executions.gt(0), "q3_ms"]).all()
    meta["checks"]["max_temporal_median_ms"] = float(summary.median_ms.max())
    meta["checks"]["max_temporal_q3_ms"] = float(summary.q3_ms.max())
    meta["checks"]["max_per_run_second_mean_ms"] = float(series.benign_duration_2xx_ms.max())
    meta["checks"]["duration_coverage"] = {
        s: {phase: {
            "valid_execution_seconds": int(x.valid_executions.sum()),
            "possible_execution_seconds": int(len(x) * 20),
            "seconds_without_valid_execution": int(x.valid_executions.eq(0).sum()),
        } for phase, x in (("PRE", z[(z.second >= 30) & (z.second < 150)]),
                            ("ACTIVE", z[(z.second >= 150) & (z.second < 270)]),
                            ("POST", z[(z.second >= 270) & (z.second < 390)]))}
        for s, z in summary.groupby("scenario")
    }
    return summary


def figure_duration(summary: pd.DataFrame) -> None:
    fig, (ax, coverage) = plt.subplots(2, 1, figsize=(9.5, 5.9), sharex=True,
                                       gridspec_kw={"height_ratios": [3.6, 1.1], "hspace": .13})
    for axis in (ax, coverage):
        phase_background(axis)
    for s in SCENARIOS:
        z = summary[summary.scenario == s].sort_values("second")
        x = z.second.to_numpy(); median = z.median_ms.to_numpy(dtype=float)
        q1 = z.q1_ms.to_numpy(dtype=float); q3 = z.q3_ms.to_numpy(dtype=float)
        ax.plot(x, median, color=COLORS[s], ls=STYLES[s], lw=1.65, label=NAMES[s], zorder=3)
        ax.fill_between(x, q1, q3, color=COLORS[s], alpha=.14, linewidth=0, zorder=2)
        coverage.step(x, z.valid_executions.to_numpy(), where="post", color=COLORS[s],
                      ls=STYLES[s], lw=1.3)
    ax.set_yscale("log")
    ax.set_ylim(25, 2500)
    ax.yaxis.set_major_locator(FixedLocator([40, 100, 200, 500, 1000, 2000]))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}".replace(",", ".")))
    ax.set_ylabel("Duração HTTP legítima 2xx (ms)\nescala logarítmica")
    ax.legend(loc="upper left", ncol=1, frameon=False, fontsize=9)
    coverage.set_ylim(-.5, 20.8)
    coverage.set_yticks([0, 10, 20])
    coverage.set_ylabel("Execuções com\n2xx válido")
    coverage.set_xlabel("Tempo experimental (s)")
    fig.suptitle("Evolução da duração das requisições HTTP legítimas", fontsize=13, fontweight="bold", y=.995)
    fig.text(.5, .055, "Média 2xx por execução e segundo; linha: mediana; banda: intervalo interquartil (Q1–Q3)", ha="center", fontsize=8.3, color=TEXT)
    fig.text(.5, .035, "20 execuções por cenário · coorte de início HTTP · sem 2xx = duração ausente", ha="center", fontsize=8.3, color=TEXT)
    fig.text(.5, .015, "PRE [30,150) s · ACTIVE [150,270) s (faixa cinza) · POST [270,390) s", ha="center", fontsize=8.3, color=TEXT)
    fig.subplots_adjust(left=.13, right=.99, top=.89, bottom=.18)
    save(fig, "f52a_duracao_http_legitima")


def derive_timeouts_5s(series: pd.DataFrame, meta: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    windowed = series.copy()
    windowed["window_start_s"] = (windowed.second // 5) * 5
    per_run = (windowed.groupby(["id", "scenario", "window_start_s"], sort=True)
               [["benign_http_start", "benign_timeout"]].sum().reset_index()
               .rename(columns={"id": "entry_id", "benign_http_start": "started", "benign_timeout": "timeouts"}))
    assert len(per_run) == 60 * 72
    assert per_run.window_start_s.between(30, 385).all()
    assert per_run.started.ge(per_run.timeouts).all()
    per_run["timeout_pct"] = np.where(per_run.started.gt(0), 100 * per_run.timeouts / per_run.started, np.nan)
    assert not any((per_run.window_start_s.lt(150) & (per_run.window_start_s + 5).gt(150)) |
                   (per_run.window_start_s.lt(270) & (per_run.window_start_s + 5).gt(270)))
    summary = (per_run.groupby(["scenario", "window_start_s"], sort=True).timeout_pct
               .agg(valid_executions="count", median_pct="median",
                    q1_pct=lambda x: x.quantile(.25), q3_pct=lambda x: x.quantile(.75))
               .reset_index())
    assert len(summary) == 3 * 72
    assert (summary.median_pct.isna() == summary.q1_pct.isna()).all()
    assert (summary.median_pct.isna() == summary.q3_pct.isna()).all()
    meta["checks"]["timeout_5s"] = {
        "windows_per_run": 72,
        "min_starts_per_run_window": int(per_run.started.min()),
        "max_starts_per_run_window": int(per_run.started.max()),
        "windows_without_starts": int(per_run.started.eq(0).sum()),
        "valid_executions_per_scenario_window_min": int(summary.valid_executions.min()),
    }
    return per_run, summary


def figure_duration_timeouts(duration: pd.DataFrame, timeouts: pd.DataFrame) -> None:
    fig, (ax, lower) = plt.subplots(2, 1, figsize=(9.5, 5.75), sharex=True,
                                    gridspec_kw={"height_ratios": [3.0, 1.55], "hspace": .12})
    for axis in (ax, lower):
        phase_background(axis)
    for s in SCENARIOS:
        z = duration[duration.scenario == s].sort_values("second")
        x = z.second.to_numpy()
        # All three summaries use the same nonmissing per-run second means.
        ax.fill_between(x, z.q1_ms.to_numpy(dtype=float), z.q3_ms.to_numpy(dtype=float),
                        color=COLORS[s], alpha=.085, linewidth=0, zorder=2)
        ax.plot(x, z.median_ms.to_numpy(dtype=float), color=COLORS[s], ls=STYLES[s],
                lw=1.9, label=NAMES[s], zorder=4)
        t = timeouts[timeouts.scenario == s].sort_values("window_start_s")
        tx = np.append(t.window_start_s.to_numpy(), 390)
        q1 = np.append(t.q1_pct.to_numpy(dtype=float), float(t.q1_pct.iloc[-1]))
        q3 = np.append(t.q3_pct.to_numpy(dtype=float), float(t.q3_pct.iloc[-1]))
        median = np.append(t.median_pct.to_numpy(dtype=float), float(t.median_pct.iloc[-1]))
        lower.fill_between(tx, q1, q3,
                           step="post", color=COLORS[s], alpha=.085, linewidth=0, zorder=2)
        lower.step(tx, median, where="post", color=COLORS[s],
                   ls=STYLES[s], lw=1.8, zorder=4)
    ax.axhline(2000, color="#767D83", lw=1.0, ls=(0, (3, 3)), zorder=3)
    ax.annotate("Limite de espera do cliente (2 s)", xy=(388, 2000), xytext=(-3, 6),
                textcoords="offset points", ha="right", va="bottom", fontsize=8.3,
                color="#626A70")
    ax.set_yscale("log")
    ax.set_ylim(25, max(2500, 1.12 * float(duration.q3_ms.max())))
    ax.yaxis.set_major_locator(FixedLocator([40, 100, 200, 500, 1000, 2000]))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}".replace(",", ".")))
    ax.set_ylabel("Duração HTTP legítima 2xx (ms)\nescala logarítmica · 1 s")
    ax.legend(loc="upper left", bbox_to_anchor=(0, .83), ncol=1, frameon=False, fontsize=8.8)
    ax.text(210, .55, "Emissão ofensiva", transform=ax.get_xaxis_transform(),
            ha="center", va="center", fontsize=8.5, color="#626A70")
    lower.set_ylim(-3, 103)
    lower.set_yticks([0, 25, 50, 75, 100])
    lower.set_ylabel("Timeouts legítimos (%)\ncoortes de 5 s")
    lower.set_xlabel("Tempo experimental (s)")
    fig.suptitle("Evolução do atendimento HTTP legítimo durante os experimentos", fontsize=13,
                 fontweight="bold", y=.995)
    fig.text(.5, .015, "20 execuções por cenário · linhas: medianas · bandas: intervalos interquartis", ha="center", fontsize=8.5, color=TEXT)
    fig.subplots_adjust(left=.13, right=.99, top=.89, bottom=.14)
    save(fig, "f52a_duracao_http_timeouts_alternativa")


def derive_outcomes(active: pd.DataFrame, meta: dict) -> pd.DataFrame:
    out = active[["entry_id", "scenario", "block", "started", "http_2xx_cohort", "timeout_cohort", "other_cohort"]].copy()
    for name, count in (("success_pct", "http_2xx_cohort"), ("timeout_pct", "timeout_cohort"), ("other_pct", "other_cohort")):
        out[name] = 100 * out[count] / out.started
    assert np.allclose(out[["success_pct", "timeout_pct", "other_pct"]].sum(axis=1), 100)
    assert out.other_cohort.eq(0).all()
    meta["checks"]["active_medians_pct"] = {
        s: {"http_2xx": float(z.success_pct.median()), "timeout": float(z.timeout_pct.median())}
        for s, z in out.groupby("scenario")
    }
    return out


def figure_outcomes(out: pd.DataFrame) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(9.5, 4.8), sharey=True, gridspec_kw={"wspace": .14})
    labels = ["Tráfego\nlegítimo", "Ataque\ncomputacional\nassimétrico", "Inundação\nHTTP"]
    for ax, (field, heading) in zip(axes, (("success_pct", "A  Respostas HTTP 2xx"),
                                            ("timeout_pct", "B  Timeouts do cliente"))):
        for block in range(1, 21):
            z = out[out.block == block].set_index("scenario").loc[list(SCENARIOS)]
            ax.plot(range(3), z[field].to_numpy(), color="#A7AFB4", alpha=.42,
                    lw=.75, zorder=1)
        for j, s in enumerate(SCENARIOS):
            z = out[out.scenario == s]
            ax.scatter(np.full(20, j), z[field], color=COLORS[s], s=16, alpha=.86,
                       edgecolors="white", linewidths=.25, zorder=3)
            median = float(z[field].median())
            ax.plot(j, median, marker="_", color=TEXT, ms=18, mew=2.3, zorder=4)
            label = (f"{median:.1f}".replace(".", ",").removesuffix(",0") + "%")
            ax.annotate(label, (j, median), xytext=(13, 0), textcoords="offset points",
                        ha="left", va="center", fontsize=9, color=TEXT, zorder=5,
                        bbox={"facecolor": "white", "edgecolor": "none", "alpha": .85, "pad": .4})
        ax.set_xticks(range(3), labels, fontsize=9)
        ax.set_xlim(-.25, 2.68)
        ax.set_ylim(-3, 103)
        ax.set_yticks([0, 25, 50, 75, 100])
        ax.grid(axis="y", color="#E2E6E8", lw=.7)
        ax.set_axisbelow(True)
        ax.set_title(heading, loc="left", fontsize=10.5, fontweight="bold")
    axes[0].set_ylabel("Proporção das tentativas legítimas iniciadas (%)")
    fig.suptitle("Sucesso e timeouts das requisições HTTP legítimas", fontsize=13, fontweight="bold", y=.995)
    fig.text(.5, .035, "ACTIVE [150,270) s · 20 blocos pareados · Um ponto por execução · traços escuros: medianas", ha="center", fontsize=8.5, color=TEXT)
    fig.subplots_adjust(left=.11, right=.99, top=.82, bottom=.21)
    save(fig, "f52c_sucesso_timeouts")


def main() -> None:
    style()
    series, active, meta = validate_and_load()
    duration = derive_duration(series, meta)
    outcomes = derive_outcomes(active, meta)
    timeout_runs, timeout_summary = derive_timeouts_5s(series, meta)
    active_timeouts = timeout_runs[timeout_runs.window_start_s.between(150, 269)]
    active_totals = active_timeouts.groupby("entry_id")[["started", "timeouts"]].sum()
    for r in active.itertuples():
        assert (active_totals.loc[r.entry_id].to_numpy() == [r.started, r.timeout_cohort]).all()
    processed = OUT / "processed"
    processed.mkdir(parents=True, exist_ok=True)
    for name, data in (("f52a_duracao_por_segundo.csv", duration),
                       ("f52c_desfechos_por_execucao.csv", outcomes)):
        path = processed / name
        assert path.read_bytes() == data.to_csv(index=False).encode(), f"Previously derived data changed: {path}"
    original = {}
    for extension in ("pdf", "png"):
        path = OUT / "figures" / f"f52a_duracao_http_legitima.{extension}"
        original[extension] = sha256(path)
    timeout_runs.to_csv(processed / "f52a_timeouts_5s_por_execucao.csv", index=False)
    timeout_summary.to_csv(processed / "f52a_timeouts_5s_resumo.csv", index=False)
    figure_duration_timeouts(duration, timeout_summary)
    figure_outcomes(outcomes)
    for extension, digest in original.items():
        assert sha256(OUT / "figures" / f"f52a_duracao_http_legitima.{extension}") == digest
    meta["checks"]["original_f52a_preserved_sha256"] = original
    (processed / "manifest.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(meta["checks"], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
