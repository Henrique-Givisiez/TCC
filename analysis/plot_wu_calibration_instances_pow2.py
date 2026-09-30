import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

# Complementa o gráfico 05 (WU em potência de 2): aquele só mostra o
# resumo final (CPU média e total de erros) por combinação de RPS/WU --
# este mostra a SÉRIE TEMPORAL de cada uma das 9 combinações, com CPU e
# nº de instâncias lado a lado, pra deixar visível o mecanismo por trás
# dos erros: um pico de sobrecarga logo no início do ataque (antes do
# autoscaler conseguir subir mais instâncias), que ou se recupera (CPU
# volta a um nível baixo depois de escalar) ou nunca se recupera (CPU
# fica travada em nível alto o resto do run) -- ver changes.txt para a
# discussão completa que motivou este gráfico.

WU_DIR = "experiment_results/wu_calibration"
OUT_DIR = "results/graficos_apresentacao/01_curva_capacidade_baseline"
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

        # Janela de ataque: direto do dado (linhas com label=='attack'),
        # em vez de repetir as constantes de config.py aqui.
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

        # Total de timeouts dessa combinação, pro leitor relacionar visual -> número.
        # Chamados "timeout" (não "erro" genérico) porque é exatamente isso que
        # requests.exceptions.RequestException captura aqui: o cliente desistiu
        # depois de 2s sem resposta -- ver changes.txt §31/40 sobre a mecânica.
        summary_path = os.path.join(WU_DIR, f"attack_summary_log_{rps}_4_WU{wu}.csv")
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

# Legenda manual única pra figura inteira (uma linha por WU + instâncias + limiar)
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
    "wu_calibration (potência de 2) -- CPU e nº de instâncias ao longo do tempo\n"
    "Mostra se o sistema se recupera depois do pico de sobrecarga no início do ataque, ou fica travado",
    fontsize=13,
)
fig.tight_layout(rect=[0, 0.08, 1, 0.95])
out_path = os.path.join(OUT_DIR, "14_wu_calibration_instancias_pow2.png")
fig.savefig(out_path, dpi=110)
plt.close(fig)
print(f"Salvo: {out_path}")
