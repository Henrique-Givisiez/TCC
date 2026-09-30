import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

# Mesma estrutura do gráfico 14/22 (CPU + nº de instâncias, grade 3x3),
# mas para o cenário COMBINADO (ataque + 40 agregado de tráfego normal
# padrão) usando as 5 REPETIÇÕES do experimento de desempate
# (experiment_results/desempate_combinado_isolado/, condição "combinado")
# em vez da amostra única do wu_calibration original que alimenta o
# gráfico 14. "Fecha" o cenário combinado com o mesmo rigor já aplicado
# ao isolado (gráfico 22) e ao heatmap (28) -- nenhum experimento novo,
# o dado já existia desde a investigação da seção 62/66.
#
# Por painel, mostra a repetição mais próxima da MEDIANA das 5 (mesmo
# critério objetivo do gráfico 27 -- não a melhor nem a pior), com a
# taxa de timeout das 5 no título como média±desvio, pra não perder o
# contexto estatístico mesmo mostrando 1 linha só.

DESEMPATE_DIR = "experiment_results/desempate_combinado_isolado"
OUT_DIR = "results/graficos_apresentacao/02_caracterizacao_ataque_wedos"
os.makedirs(OUT_DIR, exist_ok=True)

RPS_VALUES = [1, 5, 10]
WU_VALUES = [100000, 200000, 400000]
WU_COLOR = {100000: "#2a78d6", 200000: "#1baf7a", 400000: "#d03b3b"}
INSTANCE_COLOR = "#555555"
NUM_REPS = 5


def timeout_rate(summary_path):
    if not os.path.exists(summary_path):
        return 0.0
    sdf = pd.read_csv(summary_path)
    sdf = sdf[sdf["total_requests"].notna()]
    ok = sdf["total_requests"].sum()
    timeouts = sdf["errors"].sum()
    return 100.0 * timeouts / (ok + timeouts) if (ok + timeouts) > 0 else 0.0


fig, axes = plt.subplots(len(RPS_VALUES), len(WU_VALUES), figsize=(15, 12.5), sharex=True)

for i, rps in enumerate(RPS_VALUES):
    for j, wu in enumerate(WU_VALUES):
        ax = axes[i][j]
        color = WU_COLOR[wu]

        rates = [timeout_rate(os.path.join(
            DESEMPATE_DIR, f"attack_summary_log_combinado_rps{rps}_att4_WU{wu}_rep{rep}.csv"))
            for rep in range(1, NUM_REPS + 1)]
        mediana = pd.Series(rates).median()
        rep_escolhida = min(range(1, NUM_REPS + 1), key=lambda r: abs(rates[r - 1] - mediana))

        df = pd.read_csv(os.path.join(
            DESEMPATE_DIR, f"metrics_combinado_rps{rps}_att4_WU{wu}_rep{rep_escolhida}.csv"))

        attack_rows = df[df["label"] == "attack"]
        if not attack_rows.empty:
            ax.axvspan(attack_rows["elapsed_time_s"].min(), attack_rows["elapsed_time_s"].max(),
                       color="#d03b3b", alpha=0.06, zorder=0)

        ax.plot(df["elapsed_time_s"], df["average_cpu_percent"], color=color, linewidth=1.8, zorder=3)
        ax.axhline(60, color=color, linestyle=":", linewidth=0.8, alpha=0.5, zorder=1)

        ax2 = ax.twinx()
        ax2.step(df["elapsed_time_s"], df["num_instances"], where="post",
                  color=INSTANCE_COLOR, linewidth=1.3, linestyle="--", alpha=0.8, zorder=2)
        ax2.set_ylim(0, 5)
        ax2.set_yticks([1, 2, 3, 4])

        rate_mean, rate_std = pd.Series(rates).mean(), pd.Series(rates).std()
        ax.set_title(
            f"rps/atacante={rps}, WU={wu:,}".replace(",", ".") +
            f"\n{rate_mean:.1f}%±{rate_std:.1f} timeout (n=5) -- rep{rep_escolhida} (mediana)",
            fontsize=9.5, color=color if rate_mean > 20 else "#333",
        )

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
    "COMBINADO com repetição (ataque + 40 agregado normal) -- CPU e nº de instâncias\n"
    "5 repetições/célula (desempate), mostrando a repetição mais próx. da mediana -- comparar com gráfico 22 (isolado)",
    fontsize=13,
)
fig.tight_layout(rect=[0, 0.08, 1, 0.95])
out_path = os.path.join(OUT_DIR, "29_combinado_repetido_instancias.png")
fig.savefig(out_path, dpi=110)
plt.close(fig)
print(f"Salvo: {out_path}")
