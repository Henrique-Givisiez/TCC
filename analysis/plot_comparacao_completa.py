import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.gridspec import GridSpec
from matplotlib.lines import Line2D

from simulator import config

# Figura única comparando os 3 cenários no mesmo estilo visual (CPU + nº
# de instâncias): NORMAL isolado (painel único, topo, sem grade -- não
# tem eixo rps/WU de ataque pra variar), COMBINADO (ataque + 40 agregado
# de tráfego normal padrão, gráfico 14) e ISOLADO (só ataque, gráfico 22),
# pareados lado a lado por rps/WU pra comparação direta. Reaproveita os 3
# conjuntos de dados já existentes -- nenhum experimento novo.

WU_CAL_DIR = "experiment_results/wu_calibration"
ISOLADO_DIR = "experiment_results/ataque_isolado"
NB_DIR = "experiment_results/normal_baseline"
OUT_DIR = "results/graficos_apresentacao/02_caracterizacao_ataque_wedos"
os.makedirs(OUT_DIR, exist_ok=True)

RPS_VALUES = [1, 5, 10]
WU_VALUES = [100000, 200000, 400000]
WU_COLOR = {100000: "#2a78d6", 200000: "#1baf7a", 400000: "#d03b3b"}
INSTANCE_COLOR = "#555555"


def plot_panel(ax, df, color, title, has_attack_window=True):
    if has_attack_window:
        attack_rows = df[df["label"] == "attack"]
        if not attack_rows.empty:
            ax.axvspan(attack_rows["elapsed_time_s"].min(), attack_rows["elapsed_time_s"].max(),
                       color="#d03b3b", alpha=0.06, zorder=0)
    ax.plot(df["elapsed_time_s"], df["average_cpu_percent"], color=color, linewidth=1.6, zorder=3)
    ax.axhline(config.CPU_THRESHOLD_SCALE_UP, color=color, linestyle=":", linewidth=0.8, alpha=0.5, zorder=1)
    ax.axhline(config.CPU_THRESHOLD_SCALE_DOWN, color=INSTANCE_COLOR, linestyle=":", linewidth=0.8, alpha=0.5, zorder=1)

    ax2 = ax.twinx()
    ax2.step(df["elapsed_time_s"], df["num_instances"], where="post",
              color=INSTANCE_COLOR, linewidth=1.1, linestyle="--", alpha=0.8, zorder=2)
    ax2.set_ylim(0, 5)
    ax2.set_yticks([1, 2, 3, 4])
    ax2.tick_params(labelsize=7, colors=INSTANCE_COLOR)
    ax2.set_ylabel("nº de instâncias", fontsize=7, color=INSTANCE_COLOR)

    ax.set_ylim(0, 260)
    ax.set_title(title, fontsize=8.5)
    ax.grid(True, alpha=0.2)
    ax.tick_params(labelsize=7)
    return ax2


def timeout_info(summary_path):
    if not os.path.exists(summary_path):
        return 0, 0.0
    sdf = pd.read_csv(summary_path)
    sdf = sdf[sdf["total_requests"].notna()]
    timeouts = int(sdf["errors"].sum())
    ok = int(sdf["total_requests"].sum())
    rate = 100.0 * timeouts / (ok + timeouts) if (ok + timeouts) > 0 else 0.0
    return timeouts, rate


fig = plt.figure(figsize=(15, 27))
gs = GridSpec(7, 3, figure=fig, height_ratios=[0.7] + [1] * 6, hspace=0.55, wspace=0.35)

# ---- Painel único: NORMAL isolado (topo, span das 3 colunas) ----
ax_normal = fig.add_subplot(gs[0, 1])
df_normal = pd.read_csv(os.path.join(NB_DIR, "metrics_normal_agg40_WU10_refined_rep1.csv"))
t_n, r_n = timeout_info(os.path.join(NB_DIR, "normal_traffic_summary_log_agg40_WU10_refined_rep1.csv"))
plot_panel(ax_normal, df_normal, "#7a3fd6",
           f"NORMAL isolado (referência) -- 40 agregado, WU=10\n{t_n} timeouts ({r_n:.1f}%)",
           has_attack_window=False)
ax_normal.set_ylabel("CPU média (%)", fontsize=8)
fig.add_subplot(gs[0, 0]).axis("off")
fig.add_subplot(gs[0, 2]).axis("off")

# ---- Grade pareada: COMBINADO x ISOLADO, por rps (linhas) x WU (colunas) ----
for i, rps in enumerate(RPS_VALUES):
    row_comb = 1 + i * 2
    row_isol = 2 + i * 2
    for j, wu in enumerate(WU_VALUES):
        color = WU_COLOR[wu]

        # COMBINADO (wu_calibration original -- ataque + 40 agregado normal)
        ax_c = fig.add_subplot(gs[row_comb, j])
        df_c = pd.read_csv(os.path.join(WU_CAL_DIR, f"metrics_rps{rps}_att4_WU{wu}.csv"))
        t_c, r_c = timeout_info(os.path.join(WU_CAL_DIR, f"attack_summary_log_{rps}_4_WU{wu}.csv"))
        plot_panel(ax_c, df_c, color,
                   f"COMBINADO -- rps={rps}, WU={wu:,}".replace(",", ".") + f"\n{t_c} timeouts ({r_c:.1f}%)")
        if j == 0:
            ax_c.set_ylabel("CPU média (%)", fontsize=8)

        # ISOLADO (sem tráfego normal)
        ax_i = fig.add_subplot(gs[row_isol, j])
        df_i = pd.read_csv(os.path.join(ISOLADO_DIR, f"metrics_rps{rps}_att4_WU{wu}.csv"))
        t_i, r_i = timeout_info(os.path.join(ISOLADO_DIR, f"attack_summary_log_rps{rps}_att4_WU{wu}.csv"))
        plot_panel(ax_i, df_i, color,
                   f"ISOLADO -- rps={rps}, WU={wu:,}".replace(",", ".") + f"\n{t_i} timeouts ({r_i:.1f}%)")
        if j == 0:
            ax_i.set_ylabel("CPU média (%)", fontsize=8)
        if row_isol == 6:
            ax_i.set_xlabel("tempo (s)", fontsize=8)

legend_elems = [
    Line2D([0], [0], color=WU_COLOR[100000], lw=2, label="CPU média -- WU=100.000"),
    Line2D([0], [0], color=WU_COLOR[200000], lw=2, label="CPU média -- WU=200.000"),
    Line2D([0], [0], color=WU_COLOR[400000], lw=2, label="CPU média -- WU=400.000"),
    Line2D([0], [0], color="#7a3fd6", lw=2, label="CPU média -- normal isolado (referência)"),
    Line2D([0], [0], color=INSTANCE_COLOR, lw=1.1, ls="--", label="nº de instâncias (eixo direito)"),
    Line2D([0], [0], color="#888", lw=0.8, ls=":",
           label=f"limiar SCALE_UP ({config.CPU_THRESHOLD_SCALE_UP:.0f}%)"),
    Line2D([0], [0], color=INSTANCE_COLOR, lw=0.8, ls=":",
           label=f"limiar SCALE_DOWN ({config.CPU_THRESHOLD_SCALE_DOWN:.0f}%)"),
    Line2D([0], [0], color="#d03b3b", lw=6, alpha=0.15, label="janela de ataque"),
]
fig.legend(handles=legend_elems, loc="lower center", ncol=3, fontsize=9, bbox_to_anchor=(0.5, 0.002))

fig.suptitle(
    "Comparação completa: NORMAL isolado × COMBINADO (ataque+normal) × ISOLADO (só ataque)\n"
    "Cada par COMBINADO/ISOLADO no mesmo rps/WU aparece empilhado, pra comparação direta",
    fontsize=14,
)
fig.tight_layout(rect=[0, 0.03, 1, 0.965])
out_path = os.path.join(OUT_DIR, "25_comparacao_completa_instancias.png")
fig.savefig(out_path, dpi=105)
plt.close(fig)
print(f"Salvo: {out_path}")
