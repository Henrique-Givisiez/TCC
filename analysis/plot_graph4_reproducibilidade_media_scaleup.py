import glob
import os
import re
import statistics as stats

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

# Mesma estrutura de plot_graph4_reproducibilidade_refinada.py (gráfico
# 16 -- pico por repetição, colorido por SCALE_UP real), mas com CPU
# MÉDIA da execução inteira em vez de pico -- pedido do usuário, para
# comparar lado a lado os dois pontos de vista (a mesma discussão de
# pico vs. média de todo o resto da sessão, agora nesta série
# específica). Novo arquivo, não sobrescreve o gráfico 16.
#
# Expectativa: como a média suaviza o pico pontual que dispara o
# SCALE_UP (um blip de poucos segundos dentro de 180s), os pontos verdes
# (escalou) e cinzas (não escalou) no mesmo agregado devem ficar bem mais
# próximos entre si aqui do que ficavam no gráfico por pico.

NB_DIR = "experiment_results/normal_baseline"
OUT_DIR = "results/graficos_apresentacao/01_curva_capacidade_baseline"
os.makedirs(OUT_DIR, exist_ok=True)

BLUE = "#2a78d6"
RED = "#d03b3b"
GREEN = "#1baf7a"
GRAY = "#888888"

AGGREGATE_TARGETS = [40, 100, 150, 200, 250, 300, 350, 400]


def is_fully_empty(summary_path, num_clients=4):
    """Mesmo critério das seções 43/54: run sem nenhuma linha de
    worker-stop tem CPU genuinamente anormal (não só falha de log) --
    excluído também da média, não só do erro."""
    if not os.path.exists(summary_path):
        return True
    df = pd.read_csv(summary_path)
    df = df[df["total_requests"].notna()]
    return df.empty


rows = []
raw_points = []  # (aggregate, media, escalou: bool) -- 1 por repetição válida

for agg in AGGREGATE_TARGETS:
    metric_files = sorted(glob.glob(os.path.join(NB_DIR, f"metrics_normal_agg{agg}_WU10_refined_rep*.csv")))
    if not metric_files:
        print(f"[WARNING] Nenhum arquivo para agregado={agg}.")
        continue

    medias, dropped = [], []
    for mf in metric_files:
        rep = re.search(r"_rep(\d+)\.csv$", mf).group(1)
        sf = os.path.join(NB_DIR, f"normal_traffic_summary_log_agg{agg}_WU10_refined_rep{rep}.csv")
        if is_fully_empty(sf):
            dropped.append(rep)
            continue
        full_df = pd.read_csv(mf)
        media = full_df["average_cpu_percent"].iloc[1:].mean()
        escalou = (full_df["decision"] == "SCALE_UP").any()
        medias.append(media)
        raw_points.append((agg, media, escalou))

    if dropped:
        print(f"[AVISO] agregado={agg}: repetição(ões) {dropped} totalmente vazia(s) excluída(s) (mesmo motivo das seções 43/54).")

    n_escalou = sum(1 for a, m, e in raw_points if a == agg and e)
    rows.append(dict(
        aggregate=agg, n=len(medias),
        media_mean=stats.mean(medias),
        media_std=stats.stdev(medias) if len(medias) > 1 else 0.0,
        media_min=min(medias), media_max=max(medias),
        n_escalou=n_escalou,
    ))

df = pd.DataFrame(rows)
print(df.to_string(index=False))

fig, ax = plt.subplots(figsize=(11, 7))

import random
random.seed(0)
for agg, media, escalou in raw_points:
    jitter = agg * random.uniform(-0.02, 0.02)
    if escalou:
        ax.scatter(agg + jitter, media, color=GREEN, marker="o", s=70, zorder=4,
                   edgecolors="white", linewidths=0.8)
    else:
        ax.scatter(agg + jitter, media, facecolors="none", edgecolors=GRAY, marker="o",
                   s=70, zorder=4, linewidths=1.5)

ax.errorbar(df["aggregate"], df["media_mean"], yerr=df["media_std"],
            fmt="-", color=BLUE, linewidth=2, capsize=6, zorder=3,
            label="CPU média da execução (média ± desvio entre repetições)")
ax.fill_between(df["aggregate"], df["media_min"], df["media_max"], color=BLUE, alpha=0.06,
                 label="faixa min-max entre repetições", zorder=1)

ax.axhline(60, color=RED, linestyle="--", linewidth=1, label="limiar SCALE_UP (60%)", zorder=2)

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
                xy=(row["aggregate"], row["media_max"]),
                xytext=(0, 10), textcoords="offset points",
                ha="center", fontsize=8.5, color="#333")

ax.set_xlabel("RPS agregado (tráfego normal, WU=10)")
ax.set_ylabel("CPU média da execução (%)")
ax.set_title(
    "Curva de capacidade do baseline normal (WU=10) -- reprodutibilidade, por MÉDIA\n"
    "CPU média por repetição, colorido por SCALE_UP real -- comparar com o gráfico 16 (por pico)"
)
ax.legend(handles=handles, labels=labels, loc="upper left", fontsize=8.5)
ax.grid(True, alpha=0.3)

fig.tight_layout()
out_path = os.path.join(OUT_DIR, "18_curva_capacidade_reproducibilidade_media_scaleup.png")
fig.savefig(out_path, dpi=110)
plt.close(fig)
print(f"\nSalvo: {out_path}")
