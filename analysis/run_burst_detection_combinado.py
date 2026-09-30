import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from simulator import config
from analysis.EntCusumZV3 import analisar_bursts_tunavel

# Fase 2+4 do plano de análise estatística (CUSUM/Entropia/Z-score,
# combinada com o usuário): roda o detector CORRIGIDO (ver changes.txt --
# bug do CUSUM contando amostra 2x, faixa de entropia fixa) sobre as 9
# células x 5 repetições do cenário COMBINADO (ataque + 40 agregado de
# tráfego normal, experiment_results/desempate_combinado_isolado/,
# condição "combinado") -- dado já existente, nenhum experimento novo.
#
# Isolado (attack-only) fica de fora aqui de propósito: rtt_log.csv nesse
# cenário só começa a ter amostra quando o ataque começa (sem tráfego
# normal rodando antes), então não existe uma janela "antes do ataque"
# de verdade para servir de baseline -- ver discussão com o usuário
# (changes.txt).
#
# Para cada execução, calcula:
#   - taxa de detecção DENTRO da janela real de ataque (proxy de TPR):
#     fração de janelas do detector, com centro dentro de
#     [ATTACK_START, ATTACK_START+PULSE_DURATION], marcadas 'DDoS Burst'
#   - taxa de falso positivo FORA da janela de ataque (proxy de FPR):
#     idem, mas fora dela (inclui o período pré-ataque e o pós-ataque)
# Agrega por célula (média das 5 repetições) e monta heatmap + tabela.

DESEMPATE_DIR = "experiment_results/desempate_combinado_isolado"
OUT_DIR = "results/graficos_apresentacao/03_deteccao_estatistica"
os.makedirs(OUT_DIR, exist_ok=True)

RPS_VALUES = [1, 5, 10]
WU_VALUES = [100000, 200000, 400000]
NUM_REPS = 5

ATTACK_START = config.ATTACK_START_TIME_SECONDS
ATTACK_END = ATTACK_START + config.PULSE_DURATION


def mmss_para_seg(s):
    mm, ss = s.split(":")
    return float(mm) * 60 + float(ss)


rows = []
for rps in RPS_VALUES:
    for wu in WU_VALUES:
        tpr_vals, fpr_vals, n_bursts_vals = [], [], []
        for rep in range(1, NUM_REPS + 1):
            suffix = f"combinado_rps{rps}_att4_WU{wu}_rep{rep}"
            rtt_path = os.path.join(DESEMPATE_DIR, f"rtt_log_{suffix}.csv")
            if not os.path.exists(rtt_path):
                print(f"[WARNING] Faltando {rtt_path}")
                continue

            df_res = analisar_bursts_tunavel(
                input_file=rtt_path, output_prefix=suffix, show_plot=False)
            if df_res is None or df_res.empty:
                continue

            tempos = df_res["Janela (MM:SS.s)"].apply(mmss_para_seg)
            dentro_ataque = (tempos >= ATTACK_START) & (tempos <= ATTACK_END)
            is_burst = df_res["Status Burst"] == "DDoS Burst"

            n_dentro = dentro_ataque.sum()
            n_fora = (~dentro_ataque).sum()
            tpr = 100.0 * (is_burst & dentro_ataque).sum() / n_dentro if n_dentro > 0 else float("nan")
            fpr = 100.0 * (is_burst & ~dentro_ataque).sum() / n_fora if n_fora > 0 else float("nan")

            tpr_vals.append(tpr)
            fpr_vals.append(fpr)
            n_bursts_vals.append(int(is_burst.sum()))

        if tpr_vals:
            rows.append(dict(
                rps=rps, wu=wu, n=len(tpr_vals),
                tpr_mean=np.nanmean(tpr_vals), tpr_std=np.nanstd(tpr_vals, ddof=1) if len(tpr_vals) > 1 else 0.0,
                fpr_mean=np.nanmean(fpr_vals), fpr_std=np.nanstd(fpr_vals, ddof=1) if len(fpr_vals) > 1 else 0.0,
                n_bursts_mean=np.mean(n_bursts_vals),
            ))

df = pd.DataFrame(rows)
pd.set_option("display.width", 160)
print("\n" + df.to_string(index=False))

csv_out = os.path.join(DESEMPATE_DIR, "resumo_deteccao_combinado.csv")
df.to_csv(csv_out, index=False)
print(f"Salvo: {csv_out}")

# Heatmap: TPR (esquerda) e FPR (direita), mesmo estilo dos gráficos 21/28/30.
fig, axes = plt.subplots(1, 2, figsize=(15, 6.5))

for ax, col, std_col, titulo, cmap in [
    (axes[0], "tpr_mean", "tpr_std", "Taxa de detecção DENTRO da janela de ataque\n(proxy de TPR)", "YlGn"),
    (axes[1], "fpr_mean", "fpr_std", "Taxa de alarme FORA da janela de ataque\n(proxy de FPR)", "YlOrRd"),
]:
    matrix = np.full((len(RPS_VALUES), len(WU_VALUES)), np.nan)
    std_matrix = np.full((len(RPS_VALUES), len(WU_VALUES)), np.nan)
    for _, row in df.iterrows():
        i = RPS_VALUES.index(int(row["rps"]))
        j = WU_VALUES.index(int(row["wu"]))
        matrix[i, j] = row[col]
        std_matrix[i, j] = row[std_col]

    im = ax.imshow(matrix, cmap=cmap, aspect="auto", origin="upper", vmin=0, vmax=100)
    ax.set_xticks(range(len(WU_VALUES)))
    ax.set_xticklabels([f"WU={wu:,}".replace(",", ".") for wu in WU_VALUES])
    ax.set_yticks(range(len(RPS_VALUES)))
    ax.set_yticklabels([f"{r} rps/atacante" for r in RPS_VALUES])
    ax.set_xlabel("work units por requisição de ataque")
    for i in range(len(RPS_VALUES)):
        for j in range(len(WU_VALUES)):
            val, std = matrix[i, j], std_matrix[i, j]
            if np.isnan(val):
                continue
            color = "white" if val > 55 else "black"
            ax.text(j, i, f"{val:.0f}%±{std:.0f}\n(n=5)", ha="center", va="center", color=color, fontsize=10)
    ax.set_title(titulo, fontsize=10.5)
    fig.colorbar(im, ax=ax, label="%")

fig.suptitle(
    "Detecção de burst (CUSUM/Z-score corrigidos) -- cenário COMBINADO, 5 repetições/célula\n"
    "EntCusumZV3.py sobre rtt_log.csv, comparado à janela real de ataque conhecida",
    fontsize=13,
)
fig.tight_layout()
out_path = os.path.join(OUT_DIR, "31_deteccao_combinado_tpr_fpr.png")
fig.savefig(out_path, dpi=110)
plt.close(fig)
print(f"Salvo: {out_path}")
