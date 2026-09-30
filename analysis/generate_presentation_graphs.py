import glob
import os
import re

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from simulator import config

# Gera os gráficos usados na apresentação ao orientador, a partir dos dados já
# coletados em experiment_results/combined_sweep/ (varredura combinada, o
# experimento equivalente à Tabela 5 de Sotelo Monge et al.) e das saídas já
# calculadas por EntCusumZV3.py (entropia, Z-score, CUSUM) para os mesmos
# arquivos. Não roda nenhuma simulação nem reimplementa a lógica de detecção —
# só lê os CSVs/XLSX já gerados e desenha.

COMBINED_DIR = "experiment_results/combined_sweep"
# Gráfico 01 (varredura combinada, sem detecção) fica em caracterização de
# ataque; 02/03 (detecção estatística em ação) ficam em detecção estatística
# -- pastas diferentes, por isso dois OUT_DIR em vez de um só (ver reorg
# changes.txt).
OUT_DIR_ATAQUE = "results/graficos_apresentacao/02_caracterizacao_ataque_wedos"
OUT_DIR_DETECCAO = "results/graficos_apresentacao/03_deteccao_estatistica"
os.makedirs(OUT_DIR_ATAQUE, exist_ok=True)
os.makedirs(OUT_DIR_DETECCAO, exist_ok=True)

BLUE = "#2a78d6"
GREEN = "#1baf7a"
RED = "#d03b3b"


def carregar_grid():
    linhas = []
    for f in sorted(glob.glob(os.path.join(COMBINED_DIR, "metrics_S*_wu*.csv"))):
        nome = os.path.basename(f)
        m = re.match(r"metrics_(S\d)_atk(\d+)pct_wu(\d+)\.csv", nome)
        cenario, pct, wu = m.group(1), int(m.group(2)), int(m.group(3))
        df = pd.read_csv(f)
        xlsx = os.path.join(COMBINED_DIR, f"rtt_bursts_{cenario}_atk{pct}pct_wu{wu}.xlsx")
        bdf = pd.read_excel(xlsx)
        bursts = int((bdf["Status Burst"] == "DDoS Burst").sum())
        linhas.append(dict(
            cenario=cenario, pct=pct, wu=wu, bursts=bursts, total_janelas=len(bdf),
            peak_cpu=df["average_cpu_percent"].max(),
            peak_rtt=df["avg_rtt_ms"].max(),
            scaleups=int((df["decision"] == "SCALE_UP").sum()),
        ))
    return pd.DataFrame(linhas)


def plot_tabela5(grid):
    """Heatmap da varredura combinada: nº de janelas com burst por cenário x intensidade x custo (WU)."""
    cenarios = ["S1", "S2", "S3", "S4"]
    pcts = [1, 5, 10]
    wus = [300000, 500000]
    vmax = max(grid["bursts"].max(), 1)

    fig, axes = plt.subplots(1, 2, figsize=(11, 5.8))
    for ax, wu in zip(axes, wus):
        mat = np.zeros((len(cenarios), len(pcts)))
        for i, sc in enumerate(cenarios):
            for j, pct in enumerate(pcts):
                row = grid[(grid.cenario == sc) & (grid.pct == pct) & (grid.wu == wu)]
                mat[i, j] = row["bursts"].values[0]

        im = ax.imshow(mat, cmap="Blues", vmin=0, vmax=vmax, aspect="auto")
        ax.set_xticks(range(len(pcts)))
        ax.set_xticklabels([f"{p}%" for p in pcts])
        ax.set_yticks(range(len(cenarios)))
        ax.set_yticklabels(cenarios)
        ax.set_xlabel("Intensidade do ataque")
        ax.set_title(f"Custo do ataque (WU) = {wu:,}".replace(",", "."))
        for i in range(len(cenarios)):
            for j in range(len(pcts)):
                val = mat[i, j]
                cor_texto = "white" if val > vmax * 0.6 else "black"
                ax.text(j, i, f"{int(val)}", ha="center", va="center",
                        color=cor_texto, fontsize=13, fontweight="bold")
    axes[0].set_ylabel("Cenário de tráfego normal (S1→S4 = volume crescente)")

    fig.suptitle("Varredura combinada (equivalente à Tabela 5)\n"
                  "nº de janelas de 20s classificadas como \"burst\" pelo detector estatístico",
                  fontsize=12, y=0.99)
    fig.subplots_adjust(top=0.80, right=0.85)
    cax = fig.add_axes([0.89, 0.15, 0.02, 0.55])
    fig.colorbar(im, cax=cax, label="janelas com burst (de ~18 por execução)")
    caminho = os.path.join(OUT_DIR_ATAQUE, "01_tabela5_heatmap.png")
    fig.savefig(caminho, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"[OK] {caminho}")


def carregar_execucao(cenario, pct, wu):
    prefixo = f"{cenario}_atk{pct}pct_wu{wu}"
    metrics = pd.read_csv(os.path.join(COMBINED_DIR, f"metrics_{prefixo}.csv"))
    bursts = pd.read_excel(os.path.join(COMBINED_DIR, f"rtt_bursts_{prefixo}.xlsx"))

    def mmss_para_seg(s):
        mm, ss = s.split(":")
        return float(mm) * 60 + float(ss)

    bursts["t"] = bursts["Janela (MM:SS.s)"].apply(mmss_para_seg)

    rtt_log = pd.read_csv(os.path.join(COMBINED_DIR, f"rtt_log_{prefixo}.csv"))
    rtt_log = rtt_log.sort_values("timestamp").reset_index(drop=True)
    rtt_log["tempo_rel"] = rtt_log["timestamp"] - rtt_log["timestamp"].min()
    baseline = rtt_log.loc[rtt_log["tempo_rel"] < config.ATTACK_START_TIME_SECONDS, "rtt"]
    baseline_mean, baseline_std = baseline.mean(), baseline.std()

    meta = dict(
        attack_start=config.ATTACK_START_TIME_SECONDS,
        attack_end=config.ATTACK_START_TIME_SECONDS + config.PULSE_DURATION,
        rtt_threshold=baseline_mean * 1.8,
        z_threshold=3.5,
        cusum_h=5 * baseline_std,
        cpu_up=config.CPU_THRESHOLD_SCALE_UP,
    )
    return metrics, bursts, meta, prefixo


def plot_deteccao(cenario, pct, wu):
    """Painel com RTT, CPU, instâncias, entropia, Z-score e CUSUM para uma execução real."""
    metrics, bursts, meta, prefixo = carregar_execucao(cenario, pct, wu)
    burst_times = bursts.loc[bursts["Status Burst"] == "DDoS Burst", "t"].values

    fig, axes = plt.subplots(6, 1, figsize=(11, 15), sharex=True)

    def sombrear(ax):
        ax.axvspan(meta["attack_start"], meta["attack_end"], color="orange", alpha=0.12,
                   label="janela de ataque")
        for bt in burst_times:
            ax.axvline(bt, color=RED, alpha=0.15, linewidth=1)
        ax.grid(True, alpha=0.25)

    # 1) RTT médio por janela (o mesmo dado usado pelo detector estatístico)
    ax = axes[0]
    ax.plot(bursts["t"], bursts["Média RTT"], color=BLUE, marker="o", markersize=3, linewidth=1.5)
    ax.axhline(meta["rtt_threshold"], color=RED, linestyle="--", linewidth=1,
               label=f"piso de burst ({meta['rtt_threshold']:.0f}ms)")
    marcados = bursts[bursts["Status Burst"] == "DDoS Burst"]
    ax.scatter(marcados["t"], marcados["Média RTT"], color=RED, zorder=5, s=35, label="janela com burst")
    sombrear(ax)
    ax.set_ylabel("RTT médio\npor janela (ms)")
    ax.legend(fontsize=8, loc="upper right")
    ax.set_title(f"Detecção estatística em ação — cenário {cenario}, {pct}% de intensidade, "
                 f"custo (WU) = {wu:,}".replace(",", "."), fontsize=12)

    # 2) CPU média (%)
    ax = axes[1]
    ax.plot(metrics["elapsed_time_s"], metrics["average_cpu_percent"], color=BLUE, linewidth=1.5)
    ax.axhline(meta["cpu_up"], color=RED, linestyle="--", linewidth=1,
               label=f"limiar SCALE_UP ({meta['cpu_up']:.0f}%)")
    sombrear(ax)
    ax.set_ylabel("CPU média (%)")
    ax.legend(fontsize=8, loc="upper right")

    # 3) Instâncias ativas (escala própria — nº de containers, não é %, por isso painel separado)
    ax = axes[2]
    ax.step(metrics["elapsed_time_s"], metrics["num_instances"], color=GREEN, where="post", linewidth=1.5)
    sombrear(ax)
    ax.set_ylabel("Instâncias\nativas")
    ax.set_ylim(0, 5)

    # 4) Entropia de Shannon
    ax = axes[3]
    ax.plot(bursts["t"], bursts["Entropia"], color=BLUE, marker="o", markersize=3, linewidth=1.5)
    ax.scatter(marcados["t"], marcados["Entropia"], color=RED, zorder=5, s=35)
    sombrear(ax)
    ax.set_ylabel("Entropia de\nShannon")

    # 5) Z-score
    ax = axes[4]
    ax.plot(bursts["t"], bursts["Max Z"], color=BLUE, marker="o", markersize=3, linewidth=1.5)
    ax.axhline(meta["z_threshold"], color=RED, linestyle="--", linewidth=1,
               label=f"limiar Z ({meta['z_threshold']})")
    ax.scatter(marcados["t"], marcados["Max Z"], color=RED, zorder=5, s=35)
    sombrear(ax)
    ax.set_ylabel("Z-score\n(máx. da janela)")
    ax.legend(fontsize=8, loc="upper right")

    # 6) CUSUM
    ax = axes[5]
    ax.plot(bursts["t"], bursts["CUSUM"], color=BLUE, marker="o", markersize=3, linewidth=1.5)
    ax.axhline(meta["cusum_h"], color=RED, linestyle="--", linewidth=1,
               label=f"limiar de alarme ({meta['cusum_h']:.0f})")
    ax.scatter(marcados["t"], marcados["CUSUM"], color=RED, zorder=5, s=35)
    sombrear(ax)
    ax.set_ylabel("CUSUM (soma\nacumulada)")
    ax.legend(fontsize=8, loc="upper right")

    axes[-1].set_xlabel("Tempo desde o início da simulação (s)")
    fig.tight_layout()
    caminho = os.path.join(OUT_DIR_DETECCAO, f"02_deteccao_{prefixo}.png")
    fig.savefig(caminho, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"[OK] {caminho}")


def plot_resumo_bursts(grid):
    """Gráfico de barras simples: total de janelas com burst por cenário, separado por WU (sem eixo duplo)."""
    cenarios = ["S1", "S2", "S3", "S4"]
    wus = [300000, 500000]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), sharey=True)
    largura = 0.25
    for ax, wu in zip(axes, wus):
        sub = grid[grid.wu == wu]
        x = np.arange(len(cenarios))
        for k, pct in enumerate([1, 5, 10]):
            valores = [sub[(sub.cenario == sc) & (sub.pct == pct)]["bursts"].values[0] for sc in cenarios]
            ax.bar(x + (k - 1) * largura, valores, width=largura, label=f"{pct}%", color=[BLUE, GREEN, RED][k])
        ax.set_xticks(x)
        ax.set_xticklabels(cenarios)
        ax.set_title(f"WU = {wu:,}".replace(",", "."))
        ax.grid(True, axis="y", alpha=0.25)
    axes[0].set_ylabel("Janelas com burst detectado")
    axes[1].legend(title="Intensidade", fontsize=8)
    fig.suptitle("Resumo da varredura combinada por cenário e intensidade", fontsize=12)
    fig.tight_layout()
    caminho = os.path.join(OUT_DIR_DETECCAO, "03_resumo_bursts_por_cenario.png")
    fig.savefig(caminho, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"[OK] {caminho}")


if __name__ == "__main__":
    grid = carregar_grid()
    plot_tabela5(grid)
    plot_resumo_bursts(grid)
    # Exemplo representativo: forte detecção real, sem falhas de requisição.
    plot_deteccao("S2", 10, 500000)
    print(f"\nGráficos salvos em {OUT_DIR_ATAQUE}/ e {OUT_DIR_DETECCAO}/")
