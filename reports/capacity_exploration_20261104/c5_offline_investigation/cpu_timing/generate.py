"""Build focused CPU timing artifacts from the previously validated 1 s table."""
import csv
import json
from pathlib import Path
import statistics

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(__file__).resolve().parent
rows = list(csv.DictReader((ROOT / "timeline_1s.csv").open()))
selected = [r for r in rows if r["run"] in {"C3_ON_r1", "C5_ON_r1"}]
fields = ["run", "bin", "start_seconds", "end_seconds", "phase", "worker_wait_n",
          "worker_wait_mean_ms", "worker_wait_median_ms", "worker_wait_p95_ms",
          "work_cpu_mean_ms", "work_wall_mean_ms", "workers_mean_active",
          "victim_submitted_not_started_mean", "victim_submitted_not_started_peak",
          "handlers_mean_active", "handlers_peak", "victim_cpu_docker_mean_pct"]
cpu_samples = {}
for run in ("C3_ON_r1", "C5_ON_r1"):
    base = Path("experiment_results/capacity-exploration-20261104") / run / "raw/diagnostics"
    origin = json.loads((base / "metadata.json").read_text())["origin_monotonic"]
    with (base / "victim/events.jsonl").open() as source:
        for line in source:
            event = json.loads(line)
            wc = event.get("worker_clock") or {}
            if event.get("kind") == "handler_finished" and event.get("endpoint") == "/medium" and event.get("request_id") and "work_cpu_seconds" in event and wc.get("pid"):
                start = event.get("work_started_at")
                if start is not None:
                    sec = int(start - origin)
                    cpu_samples.setdefault((run, sec), []).append(float(event["work_cpu_seconds"]) * 1000)
fields += ["cpu_operations_n", "cpu_mean_ms", "cpu_median_ms", "cpu_stdev_ms", "cpu_p95_ms"]
with (OUT / "cpu_timing_1s.csv").open("w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    for r in selected:
        vals = cpu_samples.get((r["run"], int(float(r["bin"]))), [])
        vals_sorted = sorted(vals)
        extra = {"cpu_operations_n": len(vals),
                 "cpu_mean_ms": statistics.mean(vals) if vals else "",
                 "cpu_median_ms": statistics.median(vals) if vals else "",
                 "cpu_stdev_ms": statistics.stdev(vals) if len(vals) > 1 else "",
                 "cpu_p95_ms": vals_sorted[max(0, int(.95 * (len(vals_sorted) - 1)))] if vals else ""}
        w.writerow({**{k: r.get(k, "") for k in fields if k in r}, **extra})

# Per-process worker CPU is available in the diagnostic worker_clock.pid field.
worker_fields = ["run", "worker_pid", "bin", "start_seconds", "operations_n",
                 "cpu_mean_ms", "cpu_median_ms", "cpu_stdev_ms", "cpu_p95_ms",
                 "worker_wait_mean_ms", "pending_mean", "workers_mean_active"]
worker_rows = []
for run in ("C3_ON_r1", "C5_ON_r1"):
    base = Path("experiment_results/capacity-exploration-20261104") / run / "raw/diagnostics"
    origin = json.loads((base / "metadata.json").read_text())["origin_monotonic"]
    per_pid = {}
    with (base / "victim/events.jsonl").open() as source:
        for line in source:
            event = json.loads(line)
            wc = event.get("worker_clock") or {}
            if event.get("kind") != "handler_finished" or event.get("endpoint") != "/medium" or not event.get("request_id") or "work_cpu_seconds" not in event or not wc.get("pid"):
                continue
            start = event.get("work_started_at")
            if start is None:
                continue
            sec = int(start - origin)
            cpu_ms = float(event["work_cpu_seconds"]) * 1000
            per_pid.setdefault((int(wc["pid"]), sec), []).append(cpu_ms)
    run_bins = {int(float(r["bin"])): r for r in selected if r["run"] == run and r["phase"] == "generation"}
    for (pid, sec), vals in sorted(per_pid.items()):
        r = run_bins.get(sec, {})
        vals_sorted = sorted(vals)
        p95 = vals_sorted[max(0, int(.95 * (len(vals_sorted) - 1)))]
        worker_rows.append({"run": run, "worker_pid": pid, "bin": sec, "start_seconds": sec,
            "operations_n": len(vals), "cpu_mean_ms": statistics.mean(vals),
            "cpu_median_ms": statistics.median(vals),
            "cpu_stdev_ms": statistics.stdev(vals) if len(vals) > 1 else "", "cpu_p95_ms": p95,
            "worker_wait_mean_ms": r.get("worker_wait_mean_ms", ""),
            "pending_mean": r.get("victim_submitted_not_started_mean", ""),
            "workers_mean_active": r.get("workers_mean_active", "")})
with (OUT / "worker_cpu_1s.csv").open("w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=worker_fields)
    w.writeheader()
    w.writerows(worker_rows)

colors = {"C3_ON_r1": "#2878b5", "C5_ON_r1": "#d35400"}
labels = {"C3_ON_r1": "C3_ON_r1", "C5_ON_r1": "C5_ON_r1"}
fig, axes = plt.subplots(3, 1, figsize=(10, 9), sharex=True, constrained_layout=True)
for run in colors:
    rr = [r for r in selected if r["run"] == run and r["phase"] == "generation"]
    x = [float(r["start_seconds"]) + .5 for r in rr]
    cpu = [float(r["work_cpu_mean_ms"]) for r in rr]
    wait = [float(r["worker_wait_mean_ms"]) for r in rr]
    pending = [float(r["victim_submitted_not_started_mean"]) for r in rr]
    axes[0].plot(x, cpu, marker="o", ms=3, label=labels[run], color=colors[run])
    axes[1].plot(x, wait, marker="o", ms=3, label=labels[run], color=colors[run])
    axes[2].plot(x, pending, marker="o", ms=3, label=labels[run], color=colors[run])
for ax, title, y in zip(axes, ["CPU por operação", "Espera submit→início do worker", "Submetidas ainda não iniciadas"], ["ms/op", "ms", "operações"]):
    ax.set_ylabel(y)
    ax.set_title(title, loc="left", fontsize=10)
    ax.grid(alpha=.25)
    ax.legend(frameon=False, ncol=2)
axes[0].axhline(11.37, color=colors["C3_ON_r1"], ls=":", alpha=.6)
axes[0].axhline(14.65, color=colors["C5_ON_r1"], ls=":", alpha=.6)
axes[1].axvline(7, color="#555", ls="--", lw=1)
axes[2].axvline(7, color="#555", ls="--", lw=1)
axes[1].text(7.15, axes[1].get_ylim()[1]*.85, "elevação C5 ~7–9 s", fontsize=8)
axes[2].text(7.15, axes[2].get_ylim()[1]*.85, "pendências passam a crescer", fontsize=8)
axes[-1].set_xlabel("Tempo desde o início validado da execução (s)")
fig.suptitle("C3 × C5 — serviço, espera e trabalho pendente (bins de 1 s)")
fig.savefig(OUT / "cpu_timing_backlog.png", dpi=170)
fig.savefig(OUT / "cpu_timing_backlog.svg")
plt.close(fig)

# Compact numerical check of early and late C5 against C3.
for run in colors:
    rr = [r for r in selected if r["run"] == run and r["phase"] == "generation"]
    early = [float(r["work_cpu_mean_ms"]) for r in rr if float(r["start_seconds"]) < 6]
    later = [float(r["work_cpu_mean_ms"]) for r in rr if 8 <= float(r["start_seconds"]) < 14]
    print(run, "early n/mean/median", len(early), round(statistics.mean(early), 3), round(statistics.median(early), 3),
          "later n/mean/median", len(later), round(statistics.mean(later), 3), round(statistics.median(later), 3))
