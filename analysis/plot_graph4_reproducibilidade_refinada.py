import glob
import os
import re
import statistics as stats

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

# Refaz o gráfico 04 ORIGINAL (04_curva_capacidade_reproducibilidade.png --
# estatística de pico, pontos 40/100/200/400 de amostra única + 250 com 3
# reps destacadas em X vermelho + 300 com losango amarelo de reexecução)
# usando o dado completo já coletado (run_graph4_refined.py, 5-8
# repetições por ponto, soluço já identificado e excluído -- ver
# changes.txt seção 43). Uma curva única e consistente por pico, SEM os
# marcadores especiais de 250/300 (que só existiam porque, na época, só
# esses 2 pontos tinham repetição -- agora todos têm).
#
# Refinamento: mostra também, para cada repetição individual, se ela
# disparou SCALE_UP de verdade ou não -- é isso que explica o desvio-
# padrão alto em 200/250 (mistura de repetições que escalaram com
# repetições que não escalaram) e o desvio baixo em 300 (todas escalam
# igual) -- ver changes.txt.

NB_DIR = "experiment_results/normal_baseline"
OUT_DIR = "results/graficos_apresentacao/01_curva_capacidade_baseline"
os.makedirs(OUT_DIR, exist_ok=True)

BLUE = "#2a78d6"
RED = "#d03b3b"
GREEN = "#1baf7a"
GRAY = "#888888"

AGGREGATE_TARGETS = [40, 100, 150, 200, 250, 300, 350, 400]


def is_fully_empty(summary_path, num_clients=4):
    """Mesmo critério de plot_graph4_refined.py: run sem nenhuma linha de
    worker-stop tem CPU genuinamente anormal (não só falha de log) --
    excluído também do pico, não só do erro."""
    if not os.path.exists(summary_path):
        return True
    df = pd.read_csv(summary_path)
    df = df[df["total_requests"].notna()]
    return df.empty


rows = []
raw_points = []  # (aggregate, peak, escalou: bool) -- 1 por repetição válida

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
        print(f"[AVISO] agregado={agg}: repetição(ões) {dropped} totalmente vazia(s) excluída(s) (mesmo motivo da seção 43).")

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

# Pontos individuais: verde preenchido = disparou SCALE_UP de verdade
# naquela repetição; cinza vazado = não disparou. Pequeno jitter
# horizontal só para não empilhar pontos exatamente em cima uns dos
# outros no mesmo agregado.
import random
random.seed(0)
for agg, peak, escalou in raw_points:
    jitter = agg * random.uniform(-0.02, 0.02)
    if escalou:
        ax.scatter(agg + jitter, peak, color=GREEN, marker="o", s=70, zorder=4,
                   edgecolors="white", linewidths=0.8)
    else:
        ax.scatter(agg + jitter, peak, facecolors="none", edgecolors=GRAY, marker="o",
                   s=70, zorder=4, linewidths=1.5)

ax.errorbar(df["aggregate"], df["peak_mean"], yerr=df["peak_std"],
            fmt="-", color=BLUE, linewidth=2, capsize=6, zorder=3,
            label="CPU de pico (média ± desvio entre repetições)")
ax.fill_between(df["aggregate"], df["peak_min"], df["peak_max"], color=BLUE, alpha=0.06,
                 label="faixa min-max entre repetições", zorder=1)

ax.axhline(60, color=RED, linestyle="--", linewidth=1, label="limiar SCALE_UP (60%)", zorder=2)

# Legenda manual para os pontos individuais (verde/cinza), já que scatter
# em loop não geraria entrada de legenda automática limpa.
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

ax.set_xlabel("RPS agregado (tráfego normal, WU=10)")
ax.set_ylabel("CPU de pico (%)")
ax.set_title(
    "Curva de capacidade do baseline normal (WU=10) -- reprodutibilidade, REFINADA\n"
    "CPU de pico por repetição, colorido por SCALE_UP real -- explica o desvio alto perto do limiar"
)
ax.legend(handles=handles, labels=labels, loc="upper left", fontsize=8.5)
ax.grid(True, alpha=0.3)

fig.tight_layout()
out_path = os.path.join(OUT_DIR, "16_curva_capacidade_reproducibilidade_refinada.png")
fig.savefig(out_path, dpi=110)
plt.close(fig)
print(f"\nSalvo: {out_path}")
