#!/usr/bin/env python3
"""Figuras e tabela operacionais da partição TEST; não altera artefatos oficiais."""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parents[1]
VIZ = ROOT / "reports/scientific_campaign_visualization_20261112"
TEMP = ROOT / "reports/investigacao-temporal-energy-20261110"
PLAN = ROOT / "experiments/protocols/energy-powersaver-20261109/plan.json"
SC = ("L2", "A3", "F96")
NAMES = {"L2": "Tráfego legítimo", "A3": "Ataque computacional assimétrico", "F96": "Inundação HTTP"}
COLORS = {"L2": "#416A88", "A3": "#A95F30", "F96": "#215647"}
STYLES = {"L2": "-", "A3": "--", "F96": "-."}
TEXT = "#263238"


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read(path: Path, hashes: dict[str, str]) -> Path:
    assert path.is_file(), path
    hashes[str(path.relative_to(ROOT))] = digest(path)
    return path


def setup_style() -> None:
    plt.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": 9.5,
        "axes.labelcolor": TEXT, "text.color": TEXT,
        "axes.edgecolor": "#9AA3A8", "xtick.color": TEXT, "ytick.color": TEXT,
        "axes.spines.top": False, "axes.spines.right": False,
        "pdf.fonttype": 42, "savefig.facecolor": "white",
    })


def save(fig: plt.Figure, stem: str) -> None:
    directory = OUT / "figures"
    directory.mkdir(parents=True, exist_ok=True)
    fig.savefig(directory / f"{stem}.pdf", facecolor="white", bbox_inches="tight")
    fig.savefig(directory / f"{stem}.png", facecolor="white", bbox_inches="tight", dpi=240)
    plt.close(fig)


def background(ax: plt.Axes) -> None:
    ax.axvspan(150, 270, color="#E7EBED", zorder=0)
    for x in (150, 270):
        ax.axvline(x, color="#A9B1B5", lw=.8, zorder=1)
    ax.set_xlim(30, 390)
    ax.set_xticks([30, 90, 150, 210, 270, 330, 390])
    ax.grid(axis="y", color="#E2E6E8", lw=.7)
    ax.set_axisbelow(True)


def inventory_and_plan(hashes: dict[str, str]) -> pd.DataFrame:
    plan = json.loads(read(PLAN, hashes).read_text())
    expected = {e["id"]: (e["scenario"], int(e["block"])) for e in plan["entries"] if e["partition"] == "TEST"}
    assert len(plan["entries"]) == 80 and len(expected) == 60
    inventory = pd.read_csv(read(VIZ / "inventario_execucoes.csv", hashes))
    inventory = inventory[inventory.partition == "TEST"].copy()
    assert len(inventory) == 60 and set(inventory.entry_id) == set(expected)
    assert all((r.scenario, int(r.block)) == expected[r.entry_id] for r in inventory.itertuples())
    assert inventory.groupby("block").scenario.apply(lambda z: set(z) == set(SC)).all()
    assert inventory.groupby("scenario").size().to_dict() == {s: 20 for s in SC}
    assert inventory.status.eq("completed").all()
    manifest = json.loads(read(VIZ / "manifest.json", hashes).read_text())
    assert manifest["campaign"] == "scientific-energy-powersaver-20261109"
    temporal = json.loads(read(TEMP / "manifesto_entradas.json", hashes).read_text())
    assert "scientific-energy-powersaver-20261109" in json.dumps(temporal)
    return inventory


def resources(inventory: pd.DataFrame, hashes: dict[str, str]) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    rows = []
    native = []
    for r in inventory.itertuples():
        cpu = pd.read_csv(read(VIZ / "processed" / f"docker_{r.entry_id}.csv", hashes))
        mem = pd.read_csv(read(VIZ / "processed" / f"memory_{r.entry_id}.csv", hashes))
        assert set(cpu.state) <= {"valid", "first_read"}
        cpu = cpu[(cpu.t >= 30) & (cpu.t < 390) & (cpu.state == "valid")].copy()
        mem = mem[(mem.t >= 30) & (mem.t < 390)].copy()
        assert cpu.cpu.notna().all() and mem.mem.notna().all()
        assert cpu.t.is_monotonic_increasing and mem.t.is_monotonic_increasing
        assert (cpu.cpu >= 0).all() and (mem.mem >= 0).all()
        cpu["window_start_s"] = (cpu.t // 5 * 5).astype(int)
        mem["window_start_s"] = (mem.t // 5 * 5).astype(int)
        c = cpu.groupby("window_start_s").cpu.agg(cpu_mean_pct="mean", cpu_samples="size")
        m = mem.groupby("window_start_s").mem.agg(memory_mib="mean", memory_samples="size")
        assert list(c.index) == list(range(30, 390, 5))
        assert list(m.index) == list(range(30, 390, 5))
        assert c.cpu_samples.between(4, 6).all() and m.memory_samples.eq(1).all()
        for t, x in c.join(m).iterrows():
            rows.append(dict(entry_id=r.entry_id, scenario=r.scenario, block=int(r.block),
                             window_start_s=int(t), cpu_mean_pct=x.cpu_mean_pct,
                             cpu_samples=int(x.cpu_samples), memory_mib=x.memory_mib,
                             memory_samples=int(x.memory_samples)))
        native.append(dict(entry_id=r.entry_id, cpu_active_mean_pct=float(cpu[(cpu.t >= 150) & (cpu.t < 270)].cpu.mean()),
                           mem_active_mean_mib=float(mem[(mem.t >= 150) & (mem.t < 270)].mem.mean())))
    per_run = pd.DataFrame(rows)
    assert len(per_run) == 60 * 72
    summaries = []
    for (sc, t), z in per_run.groupby(["scenario", "window_start_s"], sort=True):
        summaries.append(dict(scenario=sc, window_start_s=t, valid_cpu_executions=int(z.cpu_mean_pct.count()),
                              cpu_median_pct=float(z.cpu_mean_pct.median()), cpu_q1_pct=float(z.cpu_mean_pct.quantile(.25)),
                              cpu_q3_pct=float(z.cpu_mean_pct.quantile(.75)),
                              valid_memory_executions=int(z.memory_mib.count()),
                              memory_median_mib=float(z.memory_mib.median()),
                              memory_q1_mib=float(z.memory_mib.quantile(.25)),
                              memory_q3_mib=float(z.memory_mib.quantile(.75))))
    summary = pd.DataFrame(summaries)
    assert len(summary) == 3 * 72 and summary.valid_cpu_executions.eq(20).all()
    assert summary.valid_memory_executions.eq(20).all()
    checks = {"cpu_samples_per_5s_min": int(per_run.cpu_samples.min()),
              "cpu_samples_per_5s_max": int(per_run.cpu_samples.max()),
              "memory_samples_per_5s": 1,
              "resource_windows_per_execution": 72,
              "resource_windows_valid_executions": 20}
    return per_run, summary, {"native_active": pd.DataFrame(native), "checks": checks}


def integrate_intervals(pairs: list[tuple[float, float]]) -> np.ndarray:
    """Time integral of queue depth over [0,390), split into one-second bins."""
    changes: dict[float, int] = defaultdict(int)
    for a, b in pairs:
        assert np.isfinite(a) and np.isfinite(b) and b >= a
        if a >= 390 or b <= 0 or a == b:
            continue
        changes[max(0.0, a)] += 1
        changes[min(390.0, b)] -= 1
    changes[0.0] += 0
    changes[390.0] += 0
    area = np.zeros(390, dtype=float)
    depth = 0
    previous = 0.0
    for timestamp, change in sorted(changes.items()):
        while previous < timestamp:
            second = int(previous)
            stop = min(timestamp, float(second + 1))
            area[second] += depth * (stop - previous)
            previous = stop
        depth += change
        assert depth >= 0
    assert depth == 0
    return area


def source_queues(inventory: pd.DataFrame, hashes: dict[str, str]) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    counts = pd.read_csv(read(TEMP / "series_fontes_1s.csv", hashes))
    counts = counts[(counts.cls == "benign") & counts.kind.isin(["submitted", "task_started"])].copy()
    expected_ids = set(inventory.entry_id)
    assert set(counts.id) == expected_ids
    per_source = []
    per_run = []
    total_tasks = 0
    for r in inventory.itertuples():
        raw = ROOT / r.path / "raw"
        origin = json.loads(read(raw / "diagnostics/metadata.json", hashes).read_text())["origin_monotonic"]
        source_inventory = json.loads(read(raw / "source_inventory.json", hashes).read_text())
        benign_sources = [s["source_id"] for s in source_inventory if s["traffic_class"] == "benign"]
        assert len(benign_sources) == 2
        combined = np.zeros(390)
        for source in benign_sources:
            base = raw / "source_artifacts" / source / "output" / "diagnostics"
            summary = json.loads(read(base / "events.summary.json", hashes).read_text())
            assert summary["complete"] and not summary["dropped"] and not summary["write_errors"]
            tasks: dict[str, dict[str, float]] = defaultdict(dict)
            event_counts: dict[str, np.ndarray] = {"submitted": np.zeros(390, dtype=int),
                                                 "task_started": np.zeros(390, dtype=int)}
            lines = 0
            with read(base / "events.jsonl", hashes).open() as f:
                for line in f:
                    if not line.strip():
                        continue
                    lines += 1
                    event = json.loads(line)
                    if event.get("kind") not in event_counts:
                        continue
                    assert event["source_id"] == source
                    attempt = str(event["attempt_id"])
                    assert event["kind"] not in tasks[attempt]
                    t = float(event["at"] - origin)
                    tasks[attempt][event["kind"]] = t
                    if 0 <= t < 390:
                        event_counts[event["kind"]][int(t)] += 1
            assert lines == summary["written"]
            assert all(set(v) == {"submitted", "task_started"} for v in tasks.values())
            reference = counts[(counts.id == r.entry_id) & (counts.source == source)]
            for kind in ("submitted", "task_started"):
                z = reference[reference.kind == kind].set_index("second").reindex(range(390), fill_value=0)
                assert np.array_equal(event_counts[kind], z["count"].to_numpy(dtype=int))
            waiting = integrate_intervals([(v["submitted"], v["task_started"]) for v in tasks.values()])
            combined += waiting
            total_tasks += len(tasks)
            per_source.extend(dict(entry_id=r.entry_id, scenario=r.scenario, block=int(r.block),
                                   source=source, second=second, waiting_mean=float(waiting[second]))
                              for second in range(30, 390))
        per_run.extend(dict(entry_id=r.entry_id, scenario=r.scenario, block=int(r.block),
                            second=second, generator_legitimate_waiting_mean=float(combined[second]))
                       for second in range(30, 390))
    result = pd.DataFrame(per_run)
    assert len(result) == 60 * 360
    return pd.DataFrame(per_source), result, {"legitimate_sources_per_run": 2,
                                               "paired_generator_tasks": total_tasks,
                                               "generator_seconds_per_run": 360}


def victim_queues(inventory: pd.DataFrame, hashes: dict[str, str]) -> pd.DataFrame:
    series = pd.read_csv(read(TEMP / "series_1s.csv", hashes))
    assert len(series) == 60 * 390 and set(series.id) == set(inventory.entry_id)
    series = series[series.second.between(30, 389)].copy()
    assert len(series) == 60 * 360
    assert np.allclose(series.pending, series.waiting + series.running, atol=1e-7, rtol=0)
    assert series.running.between(0, 2.000001).all() and series.waiting.ge(0).all()
    blocks = inventory.set_index("entry_id").block.astype(int)
    series["block"] = series.id.map(blocks)
    return series[["id", "scenario", "block", "second", "waiting", "running", "pending", "pending_end"]].rename(columns={"id": "entry_id", "waiting": "victim_waiting_mean", "running": "victim_running_mean", "pending": "victim_pending_mean", "pending_end": "victim_pending_end"})


def queue_summary(combined: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (scenario, second), z in combined.groupby(["scenario", "second"], sort=True):
        row = {"scenario": scenario, "second": second, "valid_executions": len(z)}
        for field in ("generator_legitimate_waiting_mean", "victim_waiting_mean", "victim_running_mean", "victim_pending_mean"):
            row[field + "_median"] = float(z[field].median())
            row[field + "_q1"] = float(z[field].quantile(.25))
            row[field + "_q3"] = float(z[field].quantile(.75))
        rows.append(row)
    result = pd.DataFrame(rows)
    assert len(result) == 3 * 360 and result.valid_executions.eq(20).all()
    return result


def plot_resources(summary: pd.DataFrame) -> None:
    fig, axes = plt.subplots(2, 1, figsize=(9.5, 5.65), sharex=True,
                             gridspec_kw={"height_ratios": [1, 1], "hspace": .12})
    for ax in axes:
        background(ax)
    for scenario in SC:
        z = summary[summary.scenario == scenario].sort_values("window_start_s")
        x = z.window_start_s.to_numpy()
        axes[0].plot(x, z.cpu_median_pct, color=COLORS[scenario], ls=STYLES[scenario],
                     lw=1.8, label=NAMES[scenario])
        axes[1].plot(x, z.memory_median_mib, color=COLORS[scenario], ls=STYLES[scenario], lw=1.8)
    axes[0].set_ylabel("Utilização de CPU (%)")
    axes[1].set_ylabel("Memória utilizada (MiB)")
    axes[1].set_xlabel("Tempo experimental (s)")
    axes[0].legend(loc="upper left", frameon=False, fontsize=8.8)
    axes[0].text(210, .65, "Emissão ofensiva", transform=axes[0].get_xaxis_transform(),
                 ha="center", va="top", fontsize=8.5, color="#626A70")
    fig.suptitle("Utilização de CPU e memória da aplicação HTTP", fontsize=13, fontweight="bold", y=.995)
    fig.text(.5, .015, "20 execuções por cenário · Mediana entre execuções em janelas de 5 s", ha="center", fontsize=8.5, color=TEXT)
    fig.subplots_adjust(left=.12, right=.99, top=.90, bottom=.14)
    save(fig, "f52d_cpu_memoria")


def plot_queues(summary: pd.DataFrame) -> None:
    fig, axes = plt.subplots(2, 1, figsize=(9.5, 5.65), sharex=True,
                             gridspec_kw={"height_ratios": [1, 1], "hspace": .12})
    for ax in axes:
        background(ax)
    for scenario in SC:
        z = summary[summary.scenario == scenario].sort_values("second")
        x = z.second.to_numpy()
        axes[0].plot(x, z.generator_legitimate_waiting_mean_median, color=COLORS[scenario],
                     ls=STYLES[scenario], lw=1.7, label=NAMES[scenario])
        axes[1].plot(x, z.victim_waiting_mean_median, color=COLORS[scenario],
                     ls=STYLES[scenario], lw=1.7)
    axes[0].set_ylabel("Tarefas legítimas\naguardando despacho")
    axes[0].set_ylim(bottom=0, top=max(.012, 1.15 * float(summary.generator_legitimate_waiting_mean_median.max())))
    axes[1].set_ylabel("Operações aguardando\nexecução na vítima")
    axes[1].set_xlabel("Tempo experimental (s)")
    axes[0].legend(loc="upper left", frameon=False, fontsize=8.8)
    axes[0].text(210, .90, "Emissão ofensiva", transform=axes[0].get_xaxis_transform(),
                 ha="center", va="top", fontsize=8.5, color="#626A70")
    fig.suptitle("Evolução das filas de espera durante os experimentos", fontsize=13, fontweight="bold", y=.995)
    fig.text(.5, .015, "20 execuções por cenário · Mediana entre execuções das médias temporais por segundo", ha="center", fontsize=8.5, color=TEXT)
    fig.subplots_adjust(left=.15, right=.99, top=.90, bottom=.14)
    save(fig, "f52e_filas_espera")


def table_data(inventory: pd.DataFrame, resource_native: pd.DataFrame,
               queues: pd.DataFrame, hashes: dict[str, str]) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    phase = pd.read_csv(read(VIZ / "processed/http_phases.csv", hashes))
    phase = phase[(phase["class"] == "benign") & (phase.phase == "ACTIVE")].copy()
    assert len(phase) == 60 and phase.started.gt(0).all()
    assert (phase.http_2xx_cohort + phase.timeout_cohort + phase.other_cohort == phase.started).all()
    phase["success_pct"] = 100 * phase.http_2xx_cohort / phase.started
    phase["timeout_pct"] = 100 * phase.timeout_cohort / phase.started
    infra = pd.read_csv(read(VIZ / "processed/infrastructure.csv", hashes))
    infra = infra[infra.phase == "ACTIVE"].copy()
    assert len(infra) == 60
    native = resource_native.rename(columns={"entry_id": "id"})
    check = infra.merge(native, left_on="entry_id", right_on="id", validate="one_to_one")
    assert np.allclose(check.cpu_mean, check.cpu_active_mean_pct, atol=1e-9, rtol=0)
    assert np.allclose(check.mem_mean_mib, check.mem_active_mean_mib, atol=1e-9, rtol=0)
    metrics = pd.read_csv(read(TEMP / "metricas_periodo_execucao.csv", hashes))
    metrics = metrics[metrics.phase == "ACTIVE"].copy()
    assert len(metrics) == 60
    q = queues[queues.second.between(150, 269)].groupby("entry_id").agg(
        generator_waiting_active_mean=("generator_legitimate_waiting_mean", "mean"),
        victim_waiting_active_mean=("victim_waiting_mean", "mean"),
        victim_running_active_mean=("victim_running_mean", "mean"),
        victim_pending_end_270=("victim_pending_end", "last")).reset_index()
    qcheck = metrics.merge(q, left_on="id", right_on="entry_id", validate="one_to_one")
    assert np.allclose(qcheck.waiting_mean, qcheck.victim_waiting_active_mean, atol=1e-8, rtol=0)
    assert np.allclose(qcheck.running_mean, qcheck.victim_running_active_mean, atol=1e-8, rtol=0)
    assert np.array_equal(qcheck.pending_end.to_numpy(), qcheck.victim_pending_end_270.to_numpy())
    assert np.allclose(check.waiting_mean.to_numpy(),
                       q.set_index("entry_id").loc[check.entry_id, "victim_waiting_active_mean"].to_numpy(), atol=1e-8, rtol=0)
    base = inventory[["entry_id", "scenario", "block", "attack_nominal_rps"]].copy()
    base = base.merge(phase[["entry_id", "success_pct", "timeout_pct", "duration_2xx_median_ms", "duration_2xx_p95_ms", "started", "http_2xx_cohort", "timeout_cohort", "other_cohort"]], on="entry_id", validate="one_to_one")
    base = base.merge(infra[["entry_id", "cpu_mean", "mem_mean_mib", "workers_two_fraction", "cpu_n", "mem_n"]], on="entry_id", validate="one_to_one")
    base = base.merge(q, on="entry_id", validate="one_to_one")
    base = base.merge(metrics[["id", "attack_http_start", "benign_duration_2xx_ms", "benign_cpu_ms"]].rename(columns={"id": "entry_id"}), on="entry_id", validate="one_to_one")
    base["attack_started_rps"] = base.attack_http_start / 120
    base.loc[base.scenario == "L2", ["attack_nominal_rps", "attack_started_rps"]] = [np.nan, np.nan]
    assert len(base) == 60 and base.groupby("scenario").size().eq(20).all()
    assert base.other_cohort.eq(0).all()
    official = pd.read_csv(read(VIZ / "processed/official_availability.csv", hashes))
    official = official.merge(base[["entry_id", "started", "http_2xx_cohort"]], on="entry_id", validate="one_to_one")
    assert (official.timely_2xx == official.http_2xx_cohort).all()
    official_denom_diff = int((official.starts != official.started).sum())
    summary_spec = [
        ("Sucesso HTTP 2xx legítimo", "%", "success_pct", "observado"),
        ("Timeout legítimo", "%", "timeout_pct", "observado"),
        ("CPU da vítima, snapshots nativos", "%", "cpu_mean", "observado"),
        ("Memória da vítima", "MiB", "mem_mean_mib", "observado"),
        ("Operações aguardando execução", "operações", "victim_waiting_active_mean", "observado"),
        ("Operações pendentes na vítima ao fim de ACTIVE", "operações", "victim_pending_end_270", "observado"),
        ("Inícios HTTP ofensivos", "RPS", "attack_started_rps", "observado"),
        ("Emissão ofensiva nominal", "RPS", "attack_nominal_rps", "configurado"),
    ]
    table = []
    for label, unit, field, kind in summary_spec:
        row = dict(indicador=label, unidade=unit, campo=field, tipo=kind, fase="ACTIVE [150,270)")
        for scenario in SC:
            z = base[base.scenario == scenario][field].dropna()
            row[f"{scenario}_valid_executions"] = len(z)
            row[f"{scenario}_mean"] = float(z.mean()) if len(z) else np.nan
            row[f"{scenario}_sample_sd"] = float(z.std(ddof=1)) if len(z) > 1 and kind == "observado" else np.nan
            if kind == "configurado" and len(z):
                assert z.nunique() == 1
        table.append(row)
    checks = {"official_success_denominator_diff_runs": official_denom_diff,
              "official_success_numerator_matches_runs": 60,
              "table_runs": 60, "table_blocks": 20,
              "table_active_duration_seconds": 120,
              "offensive_nominal_rps": {s: (None if s == "L2" else int(base[base.scenario == s].attack_nominal_rps.iloc[0])) for s in SC}}
    return base, pd.DataFrame(table), checks


def latex_table(table: pd.DataFrame) -> str:
    def fmt(row, scenario):
        mean = row[f"{scenario}_mean"]
        if pd.isna(mean):
            return "\\textemdash{}"
        if row.tipo == "configurado":
            return f"{mean:.0f}"
        decimals = 2 if row.unidade in ("operações", "MiB", "RPS") else 1
        m = f"{mean:.{decimals}f}".replace(".", ",")
        sd = f"{row[f'{scenario}_sample_sd']:.{decimals}f}".replace(".", ",")
        return f"{m}~$\\pm$~{sd}"
    lines = [
        "% Requer \\usepackage{booktabs}. Médias e desvios-padrão entre execuções TEST.",
        "\\begin{table}[htbp]",
        "\\centering",
        "\\caption{Síntese dos indicadores operacionais da campanha definitiva}",
        "\\label{tab:indicadores-operacionais-energy}",
        "\\small",
        "\\begin{tabular}{p{5.1cm}ccc}",
        "\\toprule",
        "Indicador & \\shortstack{Tráfego\\\\legítimo} & \\shortstack{Ataque computacional\\\\assimétrico} & \\shortstack{Inundação\\\\HTTP} \\\\ ",
        "\\midrule",
    ]
    for _, r in table.iterrows():
        label = f"{r.indicador} ({r.unidade})"
        lines.append(f"{label} & {fmt(r, 'L2')} & {fmt(r, 'A3')} & {fmt(r, 'F96')} \\\\ ")
    lines += [
        "\\bottomrule",
        "\\end{tabular}",
        "\\par\\vspace{2pt}",
        "\\parbox{\\linewidth}{\\footnotesize ACTIVE [150,270) s; 20 execuções por cenário. Valores observados: média $\\pm$ desvio-padrão amostral entre execuções. A taxa nominal é parâmetro configurado; \\textemdash{} indica indicador não aplicável. Sucesso 2xx eventual e timeout usam tentativas legítimas iniciadas em ACTIVE. CPU: snapshots nativos da vítima; pendentes: operações na vítima, não HTTP pendente no cliente.}",
        "\\end{table}",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    setup_style()
    hashes: dict[str, str] = {}
    inventory = inventory_and_plan(hashes)
    resource_runs, resource_summary, resource_extra = resources(inventory, hashes)
    source_runs, generator_runs, source_checks = source_queues(inventory, hashes)
    victim_runs = victim_queues(inventory, hashes)
    queue_runs = generator_runs.merge(victim_runs, on=["entry_id", "scenario", "block", "second"], validate="one_to_one")
    assert len(queue_runs) == 60 * 360
    queue_trends = queue_summary(queue_runs)
    table_runs, table, table_checks = table_data(inventory, resource_extra["native_active"], queue_runs, hashes)
    proc = OUT / "processed"
    proc.mkdir(parents=True, exist_ok=True)
    resource_runs.to_csv(proc / "f52d_recursos_por_execucao_5s.csv", index=False)
    resource_summary.to_csv(proc / "f52d_recursos_resumo_5s.csv", index=False)
    source_runs.to_csv(proc / "f52e_geradores_legitimos_por_fonte_1s.csv", index=False)
    queue_runs.to_csv(proc / "f52e_filas_por_execucao_1s.csv", index=False)
    queue_trends.to_csv(proc / "f52e_filas_resumo_1s.csv", index=False)
    table_runs.to_csv(proc / "t52a_indicadores_por_execucao.csv", index=False)
    plot_resources(resource_summary)
    plot_queues(queue_trends)
    tables = OUT / "tables"
    tables.mkdir(parents=True, exist_ok=True)
    table.to_csv(tables / "t52a_indicadores_operacionais.csv", index=False)
    (tables / "t52a_indicadores_operacionais.tex").write_text(latex_table(table), encoding="utf-8")
    checks = {"campaign": "energy-powersaver-20261109", "partition": "TEST", "runs": 60,
              "complete_blocks": 20, **resource_extra["checks"], **source_checks, **table_checks,
              "source_queue_coverage": int(queue_trends.valid_executions.min()),
              "victim_queue_coverage": int(queue_trends.valid_executions.min())}
    (proc / "manifest.json").write_text(json.dumps({"checks": checks, "input_sha256": hashes}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(checks, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
