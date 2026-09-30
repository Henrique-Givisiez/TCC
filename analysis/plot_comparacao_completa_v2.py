import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.gridspec import GridSpec
from matplotlib.lines import Line2D

# Versão 2 da figura de comparação completa (não sobrescreve
# plot_comparacao_completa.py / gráfico 25): para as células cobertas pelo
# experimento de desempate (seção 62/63 -- rps=5 e rps=10, os 3 WU), usa
# as 5 REPETIÇÕES novas da mesma sessão (sobrepostas, linhas finas) em vez
# da amostra única antiga de 15 dias atrás -- resolve o problema notado
# pelo usuário (amostra única do isolado em rps=5/WU=400k parecia "nunca
# diminuir", mas isso não se sustenta com repetição, ver changes.txt).
# rps=1 (não coberto pelo desempate) e o painel de referência do tráfego
# normal continuam usando a amostra única antiga, únicas disponíveis.

WU_CAL_DIR = "experiment_results/wu_calibration"
ISOLADO_DIR = "experiment_results/ataque_isolado"
DESEMPATE_DIR = "experiment_results/desempate_combinado_isolado"
NB_DIR = "experiment_results/normal_baseline"
OUT_DIR = "results/graficos_apresentacao/02_caracterizacao_ataque_wedos"
os.makedirs(OUT_DIR, exist_ok=True)

RPS_VALUES = [1, 5, 10]
WU_VALUES = [100000, 200000, 400000]
WU_COLOR = {100000: "#2a78d6", 200000: "#1baf7a", 400000: "#d03b3b"}
INSTANCE_COLOR = "#555555"
DESEMPATE_RPS = {1, 5, 10}
NUM_REPS_DESEMPATE = 5


def timeout_info(summary_path):
    if not os.path.exists(summary_path):
        return 0, 0.0
    sdf = pd.read_csv(summary_path)
    sdf = sdf[sdf["total_requests"].notna()]
    timeouts = int(sdf["errors"].sum())
    ok = int(sdf["total_requests"].sum())
    rate = 100.0 * timeouts / (ok + timeouts) if (ok + timeouts) > 0 else 0.0
    return timeouts, rate


def plot_single(ax, ax2, df, color, has_attack_window=True):
    if has_attack_window:
        attack_rows = df[df["label"] == "attack"]
        if not attack_rows.empty:
            ax.axvspan(attack_rows["elapsed_time_s"].min(), attack_rows["elapsed_time_s"].max(),
                       color="#d03b3b", alpha=0.06, zorder=0)
    ax.plot(df["elapsed_time_s"], df["average_cpu_percent"], color=color, linewidth=1.6, zorder=3)
    ax2.step(df["elapsed_time_s"], df["num_instances"], where="post",
              color=INSTANCE_COLOR, linewidth=1.1, linestyle="--", alpha=0.8, zorder=2)


def finish_panel(ax, ax2, color, title, ylabel=None):
    ax.axhline(60, color=color, linestyle=":", linewidth=0.8, alpha=0.5, zorder=1)
    ax2.set_ylim(0, 5)
    ax2.set_yticks([1, 2, 3, 4])
    ax2.tick_params(labelsize=7, colors=INSTANCE_COLOR)
    ax.set_ylim(0, 260)
    ax.set_title(title, fontsize=8.5)
    ax.grid(True, alpha=0.2)
    ax.tick_params(labelsize=7)
    if ylabel:
        ax.set_ylabel(ylabel, fontsize=8)


fig = plt.figure(figsize=(15, 27))
gs = GridSpec(7, 3, figure=fig, height_ratios=[0.7] + [1] * 6, hspace=0.55, wspace=0.35)

# ---- Painel único: NORMAL isolado (topo) -- amostra única, sem opção de repetição aqui ----
ax_normal = fig.add_subplot(gs[0, 1])
df_normal = pd.read_csv(os.path.join(NB_DIR, "metrics_normal_agg40_WU10_refined_rep1.csv"))
t_n, r_n = timeout_info(os.path.join(NB_DIR, "normal_traffic_summary_log_agg40_WU10_refined_rep1.csv"))
ax2_normal = ax_normal.twinx()
plot_single(ax_normal, ax2_normal, df_normal, "#7a3fd6", has_attack_window=False)
finish_panel(ax_normal, ax2_normal, "#7a3fd6",
             f"NORMAL isolado (referência) -- 40 agregado, WU=10\n{t_n} timeouts ({r_n:.1f}%)",
             ylabel="CPU média (%)")
fig.add_subplot(gs[0, 0]).axis("off")
fig.add_subplot(gs[0, 2]).axis("off")

# ---- Grade pareada: COMBINADO x ISOLADO ----
for i, rps in enumerate(RPS_VALUES):
    row_comb = 1 + i * 2
    row_isol = 2 + i * 2
    usa_desempate = rps in DESEMPATE_RPS

    for j, wu in enumerate(WU_VALUES):
        color = WU_COLOR[wu]

        for row, condicao_label, condicao_dir in [(row_comb, "COMBINADO", "combinado"),
                                                    (row_isol, "ISOLADO", "isolado")]:
            ax = fig.add_subplot(gs[row, j])
            ax2 = ax.twinx()

            if usa_desempate:
                # Pega a taxa de timeout de cada uma das 5 repetições e
                # escolhe pra plotar a que fica mais perto da MEDIANA das
                # 5 -- não a melhor nem a pior, a mais "típica"/menos
                # outlier, critério objetivo (não é só uma escolha visual).
                rates = []
                for rep in range(1, NUM_REPS_DESEMPATE + 1):
                    _, rate = timeout_info(os.path.join(
                        DESEMPATE_DIR, f"attack_summary_log_{condicao_dir}_rps{rps}_att4_WU{wu}_rep{rep}.csv"))
                    rates.append(rate)
                mediana = pd.Series(rates).median()
                rep_escolhida = min(range(1, NUM_REPS_DESEMPATE + 1), key=lambda r: abs(rates[r - 1] - mediana))

                df_rep = pd.read_csv(os.path.join(
                    DESEMPATE_DIR, f"metrics_{condicao_dir}_rps{rps}_att4_WU{wu}_rep{rep_escolhida}.csv"))
                plot_single(ax, ax2, df_rep, color)

                rate_txt = f"{sum(rates)/len(rates):.1f}%±{pd.Series(rates).std():.1f} (n=5)"
                title = (f"{condicao_label} -- rps={rps}, WU={wu:,}".replace(",", ".") +
                          f"\n{rate_txt} timeout -- rep{rep_escolhida} (mais próx. da mediana)")
            else:
                base_dir = WU_CAL_DIR if condicao_dir == "combinado" else ISOLADO_DIR
                fname = f"metrics_rps{rps}_att4_WU{wu}.csv"
                summary_name = (f"attack_summary_log_{rps}_4_WU{wu}.csv" if condicao_dir == "combinado"
                                 else f"attack_summary_log_rps{rps}_att4_WU{wu}.csv")
                df1 = pd.read_csv(os.path.join(base_dir, fname))
                plot_single(ax, ax2, df1, color)
                t1, r1 = timeout_info(os.path.join(base_dir, summary_name))
                title = (f"{condicao_label} -- rps={rps}, WU={wu:,}".replace(",", ".") +
                          f"\n{t1} timeouts ({r1:.1f}%) -- amostra única")

            finish_panel(ax, ax2, color, title, ylabel="CPU média (%)" if j == 0 else None)
            if row == 6:
                ax.set_xlabel("tempo (s)", fontsize=8)

legend_elems = [
    Line2D([0], [0], color=WU_COLOR[100000], lw=2, label="CPU média -- WU=100.000"),
    Line2D([0], [0], color=WU_COLOR[200000], lw=2, label="CPU média -- WU=200.000"),
    Line2D([0], [0], color=WU_COLOR[400000], lw=2, label="CPU média -- WU=400.000"),
    Line2D([0], [0], color="#7a3fd6", lw=2, label="CPU média -- normal isolado (referência)"),
    Line2D([0], [0], color=INSTANCE_COLOR, lw=1.1, ls="--", label="nº de instâncias (eixo direito)"),
    Line2D([0], [0], color="#888", lw=0.8, ls=":", label="limiar SCALE_UP (60%)"),
    Line2D([0], [0], color="#d03b3b", lw=6, alpha=0.15, label="janela de ataque"),
]
fig.legend(handles=legend_elems, loc="lower center", ncol=3, fontsize=9, bbox_to_anchor=(0.5, 0.002))

fig.suptitle(
    "Comparação completa v2: rps=5/10 mostram a repetição mais próxima da mediana das 5 do desempate\n"
    "(mesma sessão, não a melhor/pior); rps=1 e normal continuam amostra única (não recoletados)",
    fontsize=13,
)
fig.tight_layout(rect=[0, 0.03, 1, 0.96])
out_path = os.path.join(OUT_DIR, "27_comparacao_completa_v2.png")
fig.savefig(out_path, dpi=105)
plt.close(fig)
print(f"Salvo: {out_path}")
