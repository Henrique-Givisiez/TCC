import glob
import os
import re
import statistics as stats

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# Exploratório, pedido do usuário: "faça um gráfico igual ao 23 mas com os
# quartis, só para ver como fica" -- mesma base de dados e mesma estrutura
# visual do gráfico 23 (pico por repetição, colorido por SCALE_UP real),
# mas com um boxplot de quartis (Tukey, k=1.5) sobreposto por agregado, e
# os pontos que o IQR marcaria como outlier destacados em vermelho. Não
# substitui nem altera o gráfico 23 -- só uma visualização lado a lado
# para decidir se quartis ajudam ou atrapalham (ver changes.txt e memória
# feedback_no_iqr_outliers -- decisão já é não usar IQR como filtro; isso
# aqui é só a demonstração visual pedida).

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


def tukey_outlier_mask(values, k=1.5):
    values = np.array(values, dtype=float)
    q1, q3 = np.percentile(values, [25, 75])
    iqr = q3 - q1
    lo, hi = q1 - k * iqr, q3 + k * iqr
    return (values < lo) | (values > hi)


rows = []
raw_points = []
peaks_por_agg = {}

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

    peaks_por_agg[agg] = peaks
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

# quais pontos o IQR marcaria como outlier, por agregado
outliers = set()  # (agg, peak) -- identifica o ponto exato
for agg, peaks in peaks_por_agg.items():
    mask = tukey_outlier_mask(peaks)
    for p, is_out in zip(peaks, mask):
        if is_out:
            outliers.add((agg, round(p, 4)))

print(f"\nIQR (Tukey, k=1.5) marcaria {len(outliers)} outlier(s) no total:")
for agg, p in sorted(outliers):
    print(f"  agg={agg}: peak={p}")

fig, ax = plt.subplots(figsize=(12, 7.5))

# boxplot de quartis por agregado, posicionado no valor real do agregado
# (largura proporcional em escala log)
box_data = [peaks_por_agg[agg] for agg in AGGREGATE_TARGETS if agg in peaks_por_agg]
box_positions = [agg for agg in AGGREGATE_TARGETS if agg in peaks_por_agg]
box_widths = [agg * 0.22 for agg in box_positions]
bp = ax.boxplot(
    box_data, positions=box_positions, widths=box_widths, showfliers=False,
    patch_artist=True, zorder=2, manage_ticks=False,
)
for patch in bp["boxes"]:
    patch.set_facecolor("#f0c419")
    patch.set_alpha(0.25)
    patch.set_edgecolor("#b8930f")
for element in ["whiskers", "caps", "medians"]:
    for line in bp[element]:
        line.set_color("#b8930f")
        line.set_linewidth(1.3)

import random
random.seed(0)
for agg, peak, escalou in raw_points:
    jitter = 2 ** (random.uniform(-0.04, 0.04))
    is_outlier = (agg, round(peak, 4)) in outliers
    if is_outlier:
        # anel vermelho por trás do ponto normal, pra destacar sem
        # esconder a cor de escalou/não-escalou
        ax.scatter(agg * jitter, peak, facecolors="none", edgecolors=RED, marker="o",
                   s=170, zorder=3.5, linewidths=2.2)
    if escalou:
        ax.scatter(agg * jitter, peak, color=GREEN, marker="o", s=70, zorder=4,
                   edgecolors="white", linewidths=0.8)
    else:
        ax.scatter(agg * jitter, peak, facecolors="none", edgecolors=GRAY, marker="o",
                   s=70, zorder=4, linewidths=1.5)

ax.errorbar(df["aggregate"], df["peak_mean"], yerr=df["peak_std"],
            fmt="-", color=BLUE, linewidth=1.6, capsize=5, zorder=2.8, alpha=0.75,
            label="CPU de pico (média ± desvio entre repetições)")

ax.axhline(60, color=RED, linestyle="--", linewidth=1, label="limiar SCALE_UP (60%)", zorder=1.5)

ax.set_xscale("log", base=2)
ax.set_xticks(AGGREGATE_TARGETS)
ax.set_xticklabels([str(a) for a in AGGREGATE_TARGETS])
ax.set_xlim(15, 900)

from matplotlib.lines import Line2D
from matplotlib.patches import Patch
handles, labels = ax.get_legend_handles_labels()
handles += [
    Patch(facecolor="#f0c419", alpha=0.25, edgecolor="#b8930f", label="caixa = Q1-Q3 (IQR), linha = mediana"),
    Line2D([0], [0], marker="o", color="w", markerfacecolor=GREEN, markersize=9,
           markeredgecolor="white", label="repetição que ESCALOU de verdade"),
    Line2D([0], [0], marker="o", color="w", markerfacecolor="none", markeredgecolor=GRAY,
           markersize=9, markeredgewidth=1.5, label="repetição que NÃO escalou"),
    Line2D([0], [0], marker="o", color="w", markerfacecolor="none", markeredgecolor=RED,
           markersize=11, markeredgewidth=2.2, label="IQR marcaria como outlier (fora de Q1/Q3 ± 1.5×IQR)"),
]
labels += [
    "caixa = Q1-Q3 (IQR), linha = mediana",
    "repetição que ESCALOU de verdade",
    "repetição que NÃO escalou",
    "IQR marcaria como outlier (fora de Q1/Q3 ± 1.5×IQR)",
]

for _, row in df.iterrows():
    ax.annotate(f"{row['n_escalou']:.0f}/{row['n']:.0f} escalou",
                xy=(row["aggregate"], row["peak_max"]),
                xytext=(0, 10), textcoords="offset points",
                ha="center", fontsize=8.5, color="#333")

ax.set_xlabel("RPS agregado (tráfego normal, WU=10, escala log2)")
ax.set_ylabel("CPU de pico (%)")
ax.set_title(
    "Curva de capacidade -- potência de 2 base 20, COM QUARTIS (exploratório)\n"
    "Mesmos dados do gráfico 23 -- caixa de Tukey por agregado, outliers do IQR marcados em vermelho"
)
ax.legend(handles=handles, labels=labels, loc="upper left", fontsize=8)
ax.grid(True, alpha=0.3)

fig.tight_layout()
out_path = os.path.join(OUT_DIR, "42_curva_capacidade_pow2_base20_quartis.png")
fig.savefig(out_path, dpi=110)
plt.close(fig)
print(f"\nSalvo: {out_path}")
