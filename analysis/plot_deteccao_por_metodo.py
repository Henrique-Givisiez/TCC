import glob
import os
import re

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from simulator import config

# Decompõe a decisão combinada dos gráficos 31/34 ("Status Burst" = piso de
# RTT E (Z-score OU CUSUM), entropia só diagnóstica) nos 3 sinais
# INDIVIDUAIS já calculados e salvos em cada rtt_bursts_*.xlsx ('Al. Ent.',
# 'Al. Z', 'Al. CUSUM'), sem o piso de RTT -- mostra a sensibilidade "crua"
# de cada método sozinho, isolada do freio que já sabemos ser o principal
# responsável por bloquear a detecção nos casos diluídos (changes.txt §72).
# Reaproveita os .xlsx já salvos (desempate_combinado_isolado e
# wedos_grid/combined_sweep) -- nenhum reprocessamento do detector, nenhum
# experimento novo.

DESEMPATE_DIR = "experiment_results/desempate_combinado_isolado"
WEDOS_DIRS = ["experiment_results/wedos_grid", "experiment_results/combined_sweep"]
OUT_DIR = "results/graficos_apresentacao/03_deteccao_estatistica"
os.makedirs(OUT_DIR, exist_ok=True)

METODOS = {"Al. Ent.": ("Entropia de Shannon", "35"), "Al. Z": ("Z-score", "36"), "Al. CUSUM": ("CUSUM", "37")}
RPS_VALUES = [1, 5, 10]
WU_VALUES = [100000, 200000, 400000]
S_VALUES = ["S1", "S2", "S3", "S4"]
PCT_VALUES = [1, 5, 10]


def mmss_para_seg(s):
    mm, ss = s.split(":")
    return float(mm) * 60 + float(ss)


def tpr_from_xlsx(xlsx_path, metrics_path, coluna_alarme):
    """TPR do sinal individual (sem piso de RTT): % de janelas DENTRO da
    janela real de ataque marcadas 'Sim' naquela coluna."""
    if not os.path.exists(xlsx_path) or not os.path.exists(metrics_path):
        return None
    metrics = pd.read_csv(metrics_path)
    attack_rows = metrics[metrics["label"] == "attack"]
    if attack_rows.empty:
        return None
    attack_start, attack_end = attack_rows["elapsed_time_s"].min(), attack_rows["elapsed_time_s"].max()

    df = pd.read_excel(xlsx_path)
    tempos = df["Janela (MM:SS.s)"].apply(mmss_para_seg)
    dentro = (tempos >= attack_start) & (tempos <= attack_end)
    if dentro.sum() == 0:
        return None
    alarme = df[coluna_alarme] == "Sim"
    return 100.0 * (alarme & dentro).sum() / dentro.sum()


# ---------------------------------------------------------------------
# Painel 1: desempate combinado (rps x WU, 5 reps/célula)
# Filtrado por SCALE_UP real (mesmo critério do painel 2 e dos gráficos
# 31/45) -- antes media sensibilidade mesmo em células sem nenhum dano
# real (ex.: rps=1/WU=100k, 0/5 escalaram), inconsistente com o painel 2.
# ---------------------------------------------------------------------
def build_desempate_matrix(coluna_alarme):
    matrix = np.full((len(RPS_VALUES), len(WU_VALUES)), np.nan)
    n_escalou_matrix = np.full((len(RPS_VALUES), len(WU_VALUES)), 0)
    n_total_matrix = np.full((len(RPS_VALUES), len(WU_VALUES)), 0)
    for i, rps in enumerate(RPS_VALUES):
        for j, wu in enumerate(WU_VALUES):
            vals, n_total = [], 0
            for rep in range(1, 6):
                suffix = f"combinado_rps{rps}_att4_WU{wu}_rep{rep}"
                xlsx_path = os.path.join(DESEMPATE_DIR, f"rtt_bursts_{suffix}.xlsx")
                metrics_path = os.path.join(DESEMPATE_DIR, f"metrics_{suffix}.csv")
                if not os.path.exists(metrics_path):
                    continue
                n_total += 1
                metrics = pd.read_csv(metrics_path)
                if not (metrics["decision"] == "SCALE_UP").any():
                    continue
                tpr = tpr_from_xlsx(xlsx_path, metrics_path, coluna_alarme)
                if tpr is not None:
                    vals.append(tpr)
            n_total_matrix[i, j] = n_total
            if vals:
                matrix[i, j] = np.mean(vals)
                n_escalou_matrix[i, j] = len(vals)
    return matrix, n_escalou_matrix, n_total_matrix


# ---------------------------------------------------------------------
# Painel 2: wedos_grid + combined_sweep (S1-S4 x intensidade agregado)
# ---------------------------------------------------------------------
def build_wedos_matrix(coluna_alarme):
    rows = []
    for results_dir in WEDOS_DIRS:
        for rtt_path in sorted(glob.glob(os.path.join(results_dir, "rtt_log_*.csv"))):
            suffix = os.path.basename(rtt_path)[len("rtt_log_"):-len(".csv")]
            metrics_path = os.path.join(results_dir, f"metrics_{suffix}.csv")
            xlsx_path = os.path.join(results_dir, f"rtt_bursts_{suffix}.xlsx")
            if not os.path.exists(metrics_path):
                continue
            extra = re.match(r"^(S[1-4])_atk(\d+)pct", suffix)
            if not extra:
                continue
            metrics = pd.read_csv(metrics_path)
            escalou_real = (metrics["decision"] == "SCALE_UP").any()
            tpr = tpr_from_xlsx(xlsx_path, metrics_path, coluna_alarme) if escalou_real else None
            rows.append(dict(s=extra.group(1), pct=int(extra.group(2)), escalou_real=escalou_real, tpr=tpr))

    df = pd.DataFrame(rows)
    matrix = np.full((len(S_VALUES), len(PCT_VALUES)), np.nan)
    n_escalou_matrix = np.full((len(S_VALUES), len(PCT_VALUES)), 0)
    n_total_matrix = np.full((len(S_VALUES), len(PCT_VALUES)), 0)
    for i, s in enumerate(S_VALUES):
        for j, pct in enumerate(PCT_VALUES):
            cell = df[(df["s"] == s) & (df["pct"] == pct)] if not df.empty else df
            n_total_matrix[i, j] = len(cell)
            escalou_cell = cell[cell["escalou_real"] == True].dropna(subset=["tpr"])
            n_escalou_matrix[i, j] = len(escalou_cell)
            if len(escalou_cell):
                matrix[i, j] = escalou_cell["tpr"].mean()
    return matrix, n_escalou_matrix, n_total_matrix


def draw_heatmap(ax, matrix, n_escalou_matrix, n_total_matrix, row_labels, col_labels, xlabel, ylabel, cmap):
    im = ax.imshow(matrix, cmap=cmap, aspect="auto", origin="upper", vmin=0, vmax=100)
    ax.set_xticks(range(len(col_labels)))
    ax.set_xticklabels(col_labels, fontsize=9)
    ax.set_yticks(range(len(row_labels)))
    ax.set_yticklabels(row_labels, fontsize=9)
    ax.set_xlabel(xlabel, fontsize=9)
    ax.set_ylabel(ylabel, fontsize=9)
    for i in range(len(row_labels)):
        for j in range(len(col_labels)):
            val = matrix[i, j]
            n_escalou = int(n_escalou_matrix[i, j])
            n_total = int(n_total_matrix[i, j])
            if np.isnan(val):
                label = f"{n_escalou}/{n_total} escalaram\n(sem dano real)" if n_total else "sem dado\n(execução ausente)"
                ax.text(j, i, label, ha="center", va="center", color="#999", fontsize=8)
                continue
            color = "white" if val > 60 else "black"
            ax.text(j, i, f"{val:.0f}%\n({n_escalou}/{n_total} escalaram)", ha="center", va="center",
                    color=color, fontsize=9)
    return im


S_RPS_FUNDO = {"S1": 40, "S2": 100, "S3": 200, "S4": 300}


for coluna_alarme, (nome_metodo, num_grafico) in METODOS.items():
    mat_desempate, n_escalou_desempate, n_total_desempate = build_desempate_matrix(coluna_alarme)
    mat_wedos, n_escalou_wedos, n_total_wedos = build_wedos_matrix(coluna_alarme)

    fig, axes = plt.subplots(1, 2, figsize=(15, 6.5))

    im1 = draw_heatmap(
        axes[0], mat_desempate, n_escalou_desempate, n_total_desempate,
        [f"{r} rps/atacante" for r in RPS_VALUES], [f"WU={wu:,}".replace(",", ".") for wu in WU_VALUES],
        "work units por requisição", "RPS por atacante",
        "YlGn" if coluna_alarme != "Al. Ent." else "PuBu",
    )
    axes[0].set_title(
        "Desempate combinado (rps × WU)\n"
        "RPS aqui é do ATACANTE -- só execuções com SCALE_UP real",
        fontsize=10.5,
    )
    cbar1 = fig.colorbar(im1, ax=axes[0], label=f"% de janelas de ataque com alarme '{nome_metodo}'")
    cbar1.ax.invert_yaxis()

    im2 = draw_heatmap(
        axes[1], mat_wedos, n_escalou_wedos, n_total_wedos,
        [f"{s} ({S_RPS_FUNDO[s]} rps normal)" for s in S_VALUES], [f"{p}% do agregado" for p in PCT_VALUES],
        "intensidade do ataque (% do RPS agregado de fundo)", "cenário de fundo (S1-S4 = tráfego normal de base)",
        "YlGn" if coluna_alarme != "Al. Ent." else "PuBu",
    )
    axes[1].set_title(
        "wedos_grid + combined_sweep (S1-S4 × intensidade)\n"
        "S1-S4 NÃO é RPS do atacante -- só execuções com SCALE_UP real",
        fontsize=10.5,
    )
    cbar2 = fig.colorbar(im2, ax=axes[1], label=f"% de janelas de ataque com alarme '{nome_metodo}'")
    cbar2.ax.invert_yaxis()

    fig.suptitle(
        f"Sensibilidade INDIVIDUAL do método: {nome_metodo}\n"
        "Sinal isolado, SEM o piso de RTT da decisão combinada (Status Burst) -- ver changes.txt",
        fontsize=13,
    )
    fig.tight_layout()
    out_path = os.path.join(OUT_DIR, f"{num_grafico}_sensibilidade_{coluna_alarme.replace('. ', '').replace('.', '').lower()}.png")
    fig.savefig(out_path, dpi=110)
    plt.close(fig)
    print(f"Salvo: {out_path}")
