import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

# Mesma estrutura do gráfico 14 (plot_wu_calibration_instances_pow2.py),
# mas com o dado de ATAQUE ISOLADO (run_ataque_isolado.py, --normal-rps 0
# de verdade) -- para comparar lado a lado com o gráfico 14, que sempre
# teve 40 agregado de tráfego normal padrão junto sem ninguém ter pedido.

WU_DIR = "experiment_results/ataque_isolado"
OUT_DIR = "results/graficos_apresentacao/02_caracterizacao_ataque_wedos"
os.makedirs(OUT_DIR, exist_ok=True)

RPS_VALUES = [1, 5, 10]
WU_VALUES = [100000, 200000, 400000]
WU_COLOR = {100000: "#2a78d6", 200000: "#1baf7a", 400000: "#d03b3b"}
INSTANCE_COLOR = "#555555"

fig, axes = plt.subplots(len(RPS_VALUES), len(WU_VALUES), figsize=(15, 12.5), sharex=True)

for i, rps in enumerate(RPS_VALUES):
    for j, wu in enumerate(WU_VALUES):
        ax = axes[i][j]
        path = os.path.join(WU_DIR, f"metrics_rps{rps}_att4_WU{wu}.csv")
        df = pd.read_csv(path)

        attack_rows = df[df["label"] == "attack"]
        if not attack_rows.empty:
            ax.axvspan(attack_rows["elapsed_time_s"].min(), attack_rows["elapsed_time_s"].max(),
                       color="#d03b3b", alpha=0.06, zorder=0)

        color = WU_COLOR[wu]
        ax.plot(df["elapsed_time_s"], df["average_cpu_percent"], color=color, linewidth=1.8, zorder=3)
        ax.axhline(60, color=color, linestyle=":", linewidth=0.8, alpha=0.5, zorder=1)

        ax2 = ax.twinx()
        ax2.step(df["elapsed_time_s"], df["num_instances"], where="post",
                  color=INSTANCE_COLOR, linewidth=1.3, linestyle="--", alpha=0.8, zorder=2)
        ax2.set_ylim(0, 5)
        ax2.set_yticks([1, 2, 3, 4])

        summary_path = os.path.join(WU_DIR, f"attack_summary_log_rps{rps}_att4_WU{wu}.csv")
        timeouts, ok, rate = 0, 0, 0.0
        if os.path.exists(summary_path):
            sdf = pd.read_csv(summary_path)
            sdf = sdf[sdf["total_requests"].notna()]
            timeouts = int(sdf["errors"].sum())
            ok = int(sdf["total_requests"].sum())
            rate = 100.0 * timeouts / (ok + timeouts) if (ok + timeouts) > 0 else 0.0

        ax.set_title(f"rps/atacante={rps}, WU={wu:,}".replace(",", ".") + f" -- {timeouts} timeouts ({rate:.1f}%)",
                     fontsize=10, color=color if timeouts > 200 else "#333")

        if i == len(RPS_VALUES) - 1:
            ax.set_xlabel("tempo (s)", fontsize=9)
        if j == 0:
            ax.set_ylabel("CPU média (%)", fontsize=9)
        if j == len(WU_VALUES) - 1:
            ax2.set_ylabel("nº instâncias (tracejado)", fontsize=9, color=INSTANCE_COLOR)

        ax.set_ylim(0, 260)
        ax.grid(True, alpha=0.2)
        ax.tick_params(labelsize=8)
        ax2.tick_params(labelsize=8, colors=INSTANCE_COLOR)

from matplotlib.lines import Line2D
legend_elems = [
    Line2D([0], [0], color=WU_COLOR[100000], lw=2, label="CPU média -- WU=100.000"),
    Line2D([0], [0], color=WU_COLOR[200000], lw=2, label="CPU média -- WU=200.000"),
    Line2D([0], [0], color=WU_COLOR[400000], lw=2, label="CPU média -- WU=400.000"),
    Line2D([0], [0], color=INSTANCE_COLOR, lw=1.3, ls="--", label="nº de instâncias (eixo direito)"),
    Line2D([0], [0], color="#888", lw=0.8, ls=":", label="limiar SCALE_UP (60%)"),
    Line2D([0], [0], color="#d03b3b", lw=6, alpha=0.15, label="janela de ataque"),
]
fig.legend(handles=legend_elems, loc="lower center", ncol=3, fontsize=9, bbox_to_anchor=(0.5, 0.005))

fig.suptitle(
    "Ataque ISOLADO (sem tráfego normal, --normal-rps 0 de verdade) -- CPU e nº de instâncias\n"
    "Comparar com o gráfico 14 (mesmos parâmetros, mas com 40 agregado de tráfego normal padrão junto)",
    fontsize=13,
)
fig.tight_layout(rect=[0, 0.08, 1, 0.95])
out_path = os.path.join(OUT_DIR, "22_ataque_isolado_instancias.png")
fig.savefig(out_path, dpi=110)
plt.close(fig)
print(f"Salvo: {out_path}")
