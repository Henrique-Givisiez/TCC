import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from simulator import config

# Reprocessa o scoring de run_burst_detection_combinado.py (SEM rodar o
# detector de novo -- lê os .xlsx já salvos por aquele script) com uma
# métrica de "fora da janela de ataque" mais honesta.
#
# Achado ao inspecionar o resultado bruto: quase toda repetição tinha
# exatamente 1 janela "pré-ataque" marcada como burst -- não é falso
# positivo espúrio. Cada janela do detector cobre window_seconds=20s de
# largura e desliza só stride_seconds=10s por vez (overlap 50%); o
# "tempo" reportado na tabela é a MÉDIA do tempo_rel das amostras DENTRO
# da janela, não o início dela -- então uma janela cujo centro reportado
# cai a, por ex., t=17s já fisicamente contém uma fração real de tráfego
# de ataque (que começa em t=20s), porque a janela se estende até t=27-37s.
# Contar isso como "falso positivo" penaliza o detector por reagir RÁPIDO
# ao início real do ataque, não por errar.
#
# Correção: classifica cada janela marcada 'DDoS Burst' em 3 categorias
# em vez de 2:
#   - dentro: tempo em [ATTACK_START, ATTACK_END] -- TPR de sempre
#   - zona de transição: tempo fora desse intervalo mas a menos de
#     window_seconds de distância de uma das duas bordas -- não conta
#     como falso positivo real (a janela do detector fisicamente
#     sobrepõe o início/fim do ataque)
#   - falso positivo real: tempo a mais de window_seconds de qualquer
#     borda -- aí sim é alarme sem nenhuma sobreposição física possível
#     com o ataque.

DESEMPATE_DIR = "experiment_results/desempate_combinado_isolado"
OUT_DIR = "results/graficos_apresentacao/03_deteccao_estatistica"
os.makedirs(OUT_DIR, exist_ok=True)

RPS_VALUES = [1, 5, 10]
WU_VALUES = [100000, 200000, 400000]
NUM_REPS = 5
WINDOW_SECONDS = 20  # tem que bater com o default usado em run_burst_detection_combinado.py

ATTACK_START = config.ATTACK_START_TIME_SECONDS
ATTACK_END = ATTACK_START + config.PULSE_DURATION


def mmss_para_seg(s):
    mm, ss = s.split(":")
    return float(mm) * 60 + float(ss)


rows = []
for rps in RPS_VALUES:
    for wu in WU_VALUES:
        tpr_vals, fp_real_vals, fp_transicao_vals = [], [], []
        n_escalou, n_total = 0, 0
        for rep in range(1, NUM_REPS + 1):
            suffix = f"combinado_rps{rps}_att4_WU{wu}_rep{rep}"
            xlsx_path = os.path.join(DESEMPATE_DIR, f"rtt_bursts_{suffix}.xlsx")
            metrics_path = os.path.join(DESEMPATE_DIR, f"metrics_{suffix}.csv")
            if not os.path.exists(xlsx_path):
                print(f"[WARNING] Faltando {xlsx_path}")
                continue
            n_total += 1
            if os.path.exists(metrics_path):
                metrics = pd.read_csv(metrics_path)
                if not (metrics["decision"] == "SCALE_UP").any():
                    continue  # sem dano real -- não entra na média de TPR
            n_escalou += 1

            df_res = pd.read_excel(xlsx_path)
            tempos = df_res["Janela (MM:SS.s)"].apply(mmss_para_seg)
            dentro_ataque = (tempos >= ATTACK_START) & (tempos <= ATTACK_END)
            zona_transicao = (~dentro_ataque) & (
                (np.abs(tempos - ATTACK_START) <= WINDOW_SECONDS) |
                (np.abs(tempos - ATTACK_END) <= WINDOW_SECONDS)
            )
            fora_real = ~dentro_ataque & ~zona_transicao
            is_burst = df_res["Status Burst"] == "DDoS Burst"

            n_dentro = dentro_ataque.sum()
            n_fora_real = fora_real.sum()
            tpr = 100.0 * (is_burst & dentro_ataque).sum() / n_dentro if n_dentro > 0 else float("nan")
            fp_real = 100.0 * (is_burst & fora_real).sum() / n_fora_real if n_fora_real > 0 else float("nan")
            fp_transicao_n = int((is_burst & zona_transicao).sum())

            tpr_vals.append(tpr)
            fp_real_vals.append(fp_real)
            fp_transicao_vals.append(fp_transicao_n)

        rows.append(dict(
            rps=rps, wu=wu, n=len(tpr_vals), n_escalou=n_escalou, n_total=n_total,
            tpr_mean=np.nanmean(tpr_vals) if tpr_vals else float("nan"),
            tpr_std=np.nanstd(tpr_vals, ddof=1) if len(tpr_vals) > 1 else 0.0,
            fp_real_mean=np.nanmean(fp_real_vals) if fp_real_vals else float("nan"),
            fp_real_std=np.nanstd(fp_real_vals, ddof=1) if len(fp_real_vals) > 1 else 0.0,
            fp_transicao_total=sum(fp_transicao_vals),
        ))

df = pd.DataFrame(rows)
pd.set_option("display.width", 160)
print("\n" + df.to_string(index=False))

csv_out = os.path.join(DESEMPATE_DIR, "resumo_deteccao_combinado_v2.csv")
df.to_csv(csv_out, index=False)
print(f"Salvo: {csv_out}")

# Painel único de TPR: o painel de "falso positivo real" (fora da zona de
# transição) ficou vazio (NaN) em quase toda célula -- não por erro de
# cálculo, mas porque é estruturalmente impossível medir aqui: janela de
# ataque [20,160] + margem de transição de ±20s cobre [0,20]∪[140,180],
# ou seja, a simulação inteira de 180s já está dentro do ataque OU da
# vizinhança imediata dele. Não sobra nenhum trecho "seguramente livre de
# qualquer contaminação" nesse dataset para medir falso positivo de
# verdade -- isso exige dado SEM ataque nenhum (normal_baseline ou
# clients_rps_grid), próximo passo natural (ver changes.txt).
fig, ax = plt.subplots(figsize=(10, 7.3))

matrix = np.full((len(RPS_VALUES), len(WU_VALUES)), np.nan)
std_matrix = np.full((len(RPS_VALUES), len(WU_VALUES)), np.nan)
transicao_matrix = np.full((len(RPS_VALUES), len(WU_VALUES)), 0)
n_escalou_matrix = np.full((len(RPS_VALUES), len(WU_VALUES)), 0)
n_total_matrix = np.full((len(RPS_VALUES), len(WU_VALUES)), 0)
for _, row in df.iterrows():
    i = RPS_VALUES.index(int(row["rps"]))
    j = WU_VALUES.index(int(row["wu"]))
    matrix[i, j] = row["tpr_mean"]
    std_matrix[i, j] = row["tpr_std"]
    transicao_matrix[i, j] = row["fp_transicao_total"]
    n_escalou_matrix[i, j] = row["n_escalou"]
    n_total_matrix[i, j] = row["n_total"]

im = ax.imshow(matrix, cmap="YlGn", aspect="auto", origin="upper", vmin=0, vmax=100)
ax.set_xticks(range(len(WU_VALUES)))
ax.set_xticklabels([f"WU={wu:,}".replace(",", ".") for wu in WU_VALUES])
ax.set_yticks(range(len(RPS_VALUES)))
ax.set_yticklabels([f"{r} rps/atacante" for r in RPS_VALUES])
ax.set_xlabel("work units por requisição de ataque")
ax.set_ylabel("RPS por atacante (4 atacantes fixos)")
for i in range(len(RPS_VALUES)):
    for j in range(len(WU_VALUES)):
        val, std = matrix[i, j], std_matrix[i, j]
        n_escalou = int(n_escalou_matrix[i, j])
        n_total = int(n_total_matrix[i, j])
        if np.isnan(val):
            label = f"{n_escalou}/{n_total} escalaram\n(sem dano real)" if n_total else "sem dado\n(execução ausente)"
            ax.text(j, i, label, ha="center", va="center", color="#999", fontsize=8.5)
            continue
        n_trans = int(transicao_matrix[i, j])
        color = "white" if val > 55 else "black"
        label = f"{val:.0f}%±{std:.0f}\n({n_escalou}/{n_total} escalaram)"
        if n_trans:
            label += f"\n+{n_trans} na cauda pós-ataque"
        ax.text(j, i, label, ha="center", va="center", color=color, fontsize=9)
cbar = fig.colorbar(im, ax=ax, label="% de janelas de ataque detectadas")
cbar.ax.invert_yaxis()

fig.suptitle(
    "Detecção de burst (CUSUM/Z-score corrigidos) -- cenário COMBINADO\n"
    "Taxa de detecção dentro da janela de ataque real -- só execuções com SCALE_UP real (proxy de TPR)",
    fontsize=11.5,
)
fig.tight_layout()
out_path = os.path.join(OUT_DIR, "31_deteccao_combinado_tpr_fpr.png")
fig.savefig(out_path, dpi=110)
plt.close(fig)
print(f"Salvo (sobrescrito): {out_path}")
