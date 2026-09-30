import glob
import os
import re
import statistics as stats

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

# Tarefa 6b: gráfico novo em potência de 2 (base 20): 20, 40, 80, 160,
# 320, 640 -- 10 repetições cada (o "40" reaproveitado da tarefa 6a, mesmo
# diretório/convenção de nome). Mesma estrutura visual do gráfico 16 (pico
# por repetição, colorido por SCALE_UP real), mas com eixo X em escala
# log2 -- estilo do gráfico 13/17, pedido do usuário.

NB_DIR = "experiment_results/normal_baseline"
OUT_DIR = "results/graficos_apresentacao/01_curva_capacidade_baseline"
os.makedirs(OUT_DIR, exist_ok=True)

BLUE = "#2a78d6"
RED = "#d03b3b"
GREEN = "#1baf7a"
GRAY = "#888888"

AGGREGATE_TARGETS = [20, 40, 80, 160, 320, 640]


def is_fully_empty(summary_path):
    if not os.path.exists(summary_path):
        return True
    df = pd.read_csv(summary_path)
    df = df[df["total_requests"].notna()]
    return df.empty


rows = []
raw_points = []

for agg in AGGREGATE_TARGETS:
    metric_files = sorted(glob.glob(os.path.join(NB_DIR, f"metrics_normal_agg{agg}_WU10_refined_rep*.csv")))
    if not metric_files:
        print(f"[WARNING] Nenhum arquivo para agregado={agg}.")
        continue

    peaks, dropped = [], []
    for mf in metric_files:
        rep = re.search(r"_rep(\d+)\.csv$", mf).group(1)
        sf = os.path.join(NB_DIR, f"normal_traffic_summary_log_agg{agg}_WU10_refined_rep{rep}.csv")
        if is_fully_empty(sf):
            dropped.append(rep)
            continue
        full_df = pd.read_csv(mf)
        peak = full_df["average_cpu_percent"].iloc[1:].max()
        escalou = (full_df["decision"] == "SCALE_UP").any()
        peaks.append(peak)
        raw_points.append((agg, peak, escalou))

    if dropped:
        print(f"[AVISO] agregado={agg}: repetição(ões) {dropped} totalmente vazia(s) excluída(s).")

    n_escalou = sum(1 for a, p, e in raw_points if a == agg and e)
    rows.append(dict(
        aggregate=agg, n=len(peaks),
        peak_mean=stats.mean(peaks),
        peak_std=stats.stdev(peaks) if len(peaks) > 1 else 0.0,
        peak_min=min(peaks), peak_max=max(peaks),
        n_escalou=n_escalou,
    ))

df = pd.DataFrame(rows)
print(df.to_string(index=False))

fig, ax = plt.subplots(figsize=(11, 7))

import random
random.seed(0)
for agg, peak, escalou in raw_points:
    jitter = 2 ** (random.uniform(-0.04, 0.04))
    if escalou:
        ax.scatter(agg * jitter, peak, color=GREEN, marker="o", s=70, zorder=4,
                   edgecolors="white", linewidths=0.8)
    else:
        ax.scatter(agg * jitter, peak, facecolors="none", edgecolors=GRAY, marker="o",
                   s=70, zorder=4, linewidths=1.5)

ax.errorbar(df["aggregate"], df["peak_mean"], yerr=df["peak_std"],
            fmt="-", color=BLUE, linewidth=2, capsize=6, zorder=3,
            label="CPU de pico (média ± desvio entre repetições)")
ax.fill_between(df["aggregate"], df["peak_min"], df["peak_max"], color=BLUE, alpha=0.06,
                 label="faixa min-max entre repetições", zorder=1)

ax.axhline(60, color=RED, linestyle="--", linewidth=1, label="limiar SCALE_UP (60%)", zorder=2)

ax.set_xscale("log", base=2)
ax.set_xticks(AGGREGATE_TARGETS)
ax.set_xticklabels([str(a) for a in AGGREGATE_TARGETS])

from matplotlib.lines import Line2D
handles, labels = ax.get_legend_handles_labels()
handles += [
    Line2D([0], [0], marker="o", color="w", markerfacecolor=GREEN, markersize=9,
           markeredgecolor="white", label="repetição que ESCALOU de verdade"),
    Line2D([0], [0], marker="o", color="w", markerfacecolor="none", markeredgecolor=GRAY,
           markersize=9, markeredgewidth=1.5, label="repetição que NÃO escalou"),
]
labels += ["repetição que ESCALOU de verdade", "repetição que NÃO escalou"]

for _, row in df.iterrows():
    ax.annotate(f"{row['n_escalou']:.0f}/{row['n']:.0f} escalou",
                xy=(row["aggregate"], row["peak_max"]),
                xytext=(0, 10), textcoords="offset points",
                ha="center", fontsize=8.5, color="#333")

ax.set_xlabel("RPS agregado (tráfego normal, WU=10, escala log2)")
ax.set_ylabel("CPU de pico (%)")
ax.set_title(
    "Curva de capacidade -- potência de 2 base 20 (20/40/80/160/320/640)\n"
    "10 repetições/ponto, CPU de pico colorido por SCALE_UP real (\"40\" reaproveitado da tarefa 6a)"
)
ax.legend(handles=handles, labels=labels, loc="upper left", fontsize=8.5)
ax.grid(True, alpha=0.3)

fig.tight_layout()
out_path = os.path.join(OUT_DIR, "23_curva_capacidade_pow2_base20.png")
fig.savefig(out_path, dpi=110)
plt.close(fig)
print(f"\nSalvo: {out_path}")
