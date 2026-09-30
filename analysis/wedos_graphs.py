"""
Fase 3 do plano W-EDoS — gráficos de visualização, no mesmo estilo de
generate_presentation_graphs.py (não alterado, só reaproveitado como
referência de estilo/paleta).

Lê dados já coletados em experiment_results/wedos_grid/ (Fase 1),
experiment_results/wedos_failure/ (Fase 4) e os pontos de reprodutibilidade
(Fase 0.3, normal_baseline/wu_calibration com sufixo _repro_lote*), mais os
.xlsx já gerados por run_burst_analysis.py. Não roda nenhuma simulação.

Uso: python3 -m analysis.wedos_graphs   (roda tudo que tiver dado disponível; pula
com aviso o que faltar, em vez de quebrar)
"""
import glob
import os
import re

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from simulator import config

GRID_DIR = "experiment_results/wedos_grid"
FAILURE_DIR = "experiment_results/wedos_failure"
NB_DIR = "experiment_results/normal_baseline"
WC_DIR = "experiment_results/wu_calibration"
OUT_DIR = "results/graficos_apresentacao/02_caracterizacao_ataque_wedos"
os.makedirs(OUT_DIR, exist_ok=True)

BLUE = "#2a78d6"
GREEN = "#1baf7a"
RED = "#d03b3b"
ORANGE = "#e08a2b"

# pct aceita decimal (ex.: "0.5pct") e o stage aceita o sufixo opcional
# "_confirm" (ex.: "stage1b_confirm") -- antes disso, 8 arquivos legítimos
# (as 3 reps de 0.5%, as 2 reps extras de confirmação do candidato principal,
# e as 3 reruns do "mistério S3") eram descartados silenciosamente por não
# bater com o regex, faltando nos gráficos 06/07 sem nenhum aviso.
GRID_RE = re.compile(r"metrics_(S\d)_atk([\d.]+)pct_wu(\d+)_(stage1[ab](?:_confirm)?)_rep(\d+)\.csv$")


def carregar_grid():
    linhas = []
    for f in sorted(glob.glob(os.path.join(GRID_DIR, "metrics_S*.csv"))):
        m = GRID_RE.search(os.path.basename(f))
        if not m:
            continue
        cenario, pct_str, wu, stage, rep = m.groups()
        # pct_str preserva a formatação exata do nome de arquivo em disco
        # ("1", "0.5", "10", ...) -- reconstruir os outros caminhos a partir
        # dela, não do float, senão "1.0pct" não bate com "1pct" no disco.
        pct, wu, rep = float(pct_str), int(wu), int(rep)
        df = pd.read_csv(f)

        rtt_bursts_path = os.path.join(
            GRID_DIR, f"rtt_bursts_{cenario}_atk{pct_str}pct_wu{wu}_{stage}_rep{rep}.xlsx"
        )
        bursts = total_janelas = None
        if os.path.exists(rtt_bursts_path):
            bdf = pd.read_excel(rtt_bursts_path)
            bursts = int((bdf["Status Burst"] == "DDoS Burst").sum())
            total_janelas = len(bdf)

        errs = 0
        asum_path = os.path.join(
            GRID_DIR, f"attack_summary_log_{cenario}_atk{pct_str}pct_wu{wu}_{stage}_rep{rep}.csv"
        )
        if os.path.exists(asum_path):
            adf = pd.read_csv(asum_path)
            errs = int(pd.to_numeric(adf.get("errors"), errors="coerce").sum())

        linhas.append(dict(
            cenario=cenario, pct=pct, wu=wu, stage=stage, rep=rep,
            peak_cpu=df["average_cpu_percent"].max(),
            avg_cpu=df["average_cpu_percent"].mean(),
            scaleups=int((df["decision"] == "SCALE_UP").sum()),
            bursts=bursts, total_janelas=total_janelas,
            detection_rate=(bursts / total_janelas) if (bursts is not None and total_janelas) else None,
            errors=errs,
        ))
    return pd.DataFrame(linhas)


def plot_heatmap(grid):
    # Só a Stage1A testou a grade CHEIA (4 cenários x 3 intensidades) em
    # cada WU -- a Stage1B testa só 1 cenário/intensidade por WU (refino de
    # fronteira, não grade completa), então incluí-la aqui deixava a maioria
    # dos painéis quase em branco (só 1 célula preenchida por WU), parecendo
    # dado faltando em vez de "não fazia parte deste desenho experimental".
    # A Stage1B tem seu próprio gráfico (10_wedos_refinamento_fronteiras.png).
    grid = grid[grid["stage"] == "stage1a"]
    if grid.empty:
        print("[SKIP] heatmap: sem dados de stage1a em wedos_grid/")
        return
    cenarios = sorted(grid["cenario"].unique())
    pcts = sorted(grid["pct"].unique())
    wus = sorted(grid["wu"].unique())

    fig, axes = plt.subplots(1, len(wus), figsize=(5.5 * len(wus), 5.8), squeeze=False)
    axes = axes[0]
    vmax = max(grid["peak_cpu"].max(), 60)
    for ax, wu in zip(axes, wus):
        mat = np.full((len(cenarios), len(pcts)), np.nan)
        scaled = np.zeros((len(cenarios), len(pcts)), dtype=bool)
        for i, sc in enumerate(cenarios):
            for j, pct in enumerate(pcts):
                sub = grid[(grid.cenario == sc) & (grid.pct == pct) & (grid.wu == wu)]
                if len(sub):
                    mat[i, j] = sub["peak_cpu"].mean()
                    scaled[i, j] = (sub["scaleups"] > 0).any()
        im = ax.imshow(mat, cmap="Blues", vmin=0, vmax=vmax, aspect="auto")
        ax.set_xticks(range(len(pcts)))
        ax.set_xticklabels([f"{p:g}%" for p in pcts])
        ax.set_yticks(range(len(cenarios)))
        ax.set_yticklabels(cenarios)
        ax.set_xlabel("Intensidade do ataque")
        ax.set_title(f"WU = {wu:,}".replace(",", "."))
        for i in range(len(cenarios)):
            for j in range(len(pcts)):
                if np.isnan(mat[i, j]):
                    continue
                marca = " ▲" if scaled[i, j] else ""
                cor_texto = "white" if mat[i, j] > vmax * 0.6 else "black"
                ax.text(j, i, f"{mat[i, j]:.0f}%{marca}", ha="center", va="center",
                        color=cor_texto, fontsize=11, fontweight="bold")
    axes[0].set_ylabel("Cenário de tráfego normal (S1→S4 = volume crescente)")
    fig.suptitle("Pico de CPU por cenário × intensidade × custo (WU) — grade completa (Stage 1A)\n"
                  "▲ = pelo menos 1 SCALE_UP disparado nessa execução", fontsize=12, y=1.02)
    fig.tight_layout()
    caminho = os.path.join(OUT_DIR, "06_wedos_heatmap_cpu.png")
    fig.savefig(caminho, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"[OK] {caminho}")


def plot_efetividade_furtividade(grid):
    sub = grid.dropna(subset=["detection_rate"])
    if sub.empty:
        print("[SKIP] scatter efetividade x furtividade: sem detection_rate calculada "
              "(rode run_burst_analysis.py antes)")
        return
    fig, ax = plt.subplots(figsize=(8, 6.5))
    for wu, marker in zip(sorted(sub["wu"].unique()), ["o", "s", "^", "D", "P", "X"]):
        s = sub[sub.wu == wu]
        sc = ax.scatter(s["pct"], s["peak_cpu"], c=s["detection_rate"], cmap="RdYlGn_r",
                         vmin=0, vmax=1, s=110, marker=marker, edgecolor="black", linewidth=0.5,
                         label=f"WU={wu:,}".replace(",", "."))
    ax.axhline(config.CPU_THRESHOLD_SCALE_UP, color=RED, linestyle="--", linewidth=1,
               label=f"limiar SCALE_UP ({config.CPU_THRESHOLD_SCALE_UP:.0f}%)")
    ax.set_xlabel("Intensidade do ataque (% do RPS normal) — furtividade de VOLUME")
    ax.set_ylabel("Pico de CPU (%) — efetividade")
    ax.set_title("Melhor W-EDoS = canto superior esquerdo, cor verde\n"
                  "(alto impacto em CPU, baixo volume, baixa taxa de detecção)")
    ax.legend(fontsize=8, loc="lower right")
    ax.grid(True, alpha=0.25)
    cbar = fig.colorbar(sc, ax=ax)
    cbar.set_label("Taxa de detecção pelo EntCusumZV3 (0=furtivo, 1=sempre detectado)")
    fig.tight_layout()
    caminho = os.path.join(OUT_DIR, "07_wedos_efetividade_furtividade.png")
    fig.savefig(caminho, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"[OK] {caminho}")


def plot_refinamento_fronteiras(grid):
    # Complementa o heatmap (que agora só mostra a Stage1A): esta é a
    # visualização certa para a Stage1B, que testa 1 cenário/intensidade por
    # vez ao longo de vários WU, com repetições reais -- uma reta com barra
    # de erro por cenário é mais honesta aqui do que uma matriz cheia de
    # células em branco.
    grupos = [("S1", 10.0, "S1 — 10% de intensidade"),
              ("S2", 1.0, "S2 — 1% de intensidade"),
              ("S3", 1.0, "S3 — 1% de intensidade")]
    disponiveis = [g for g in grupos if not grid[(grid.cenario == g[0]) & (grid.pct == g[1])].empty]
    if not disponiveis:
        print("[SKIP] refinamento de fronteiras: sem dados de stage1b em wedos_grid/")
        return

    fig, axes = plt.subplots(1, len(disponiveis), figsize=(6 * len(disponiveis), 5), squeeze=False)
    axes = axes[0]
    sc_plot = None
    for ax, (cenario, pct, titulo) in zip(axes, disponiveis):
        sub = grid[(grid.cenario == cenario) & (grid.pct == pct)]
        agg = sub.groupby("wu").agg(
            cpu_media=("peak_cpu", "mean"), cpu_std=("peak_cpu", "std"),
            taxa_scaleup=("scaleups", lambda s: (s > 0).mean()), n=("peak_cpu", "size"),
        ).reset_index().sort_values("wu")
        ax.errorbar(agg["wu"], agg["cpu_media"], yerr=agg["cpu_std"].fillna(0),
                     color="black", linewidth=1, capsize=4, zorder=2)
        sc_plot = ax.scatter(agg["wu"], agg["cpu_media"], c=agg["taxa_scaleup"], cmap="RdYlGn_r",
                              vmin=0, vmax=1, s=90, edgecolor="black", linewidth=0.6, zorder=3)
        for _, row in agg.iterrows():
            ax.annotate(f"n={int(row['n'])}", (row["wu"], row["cpu_media"]),
                        textcoords="offset points", xytext=(0, 8), fontsize=7, ha="center")

        if cenario == "S2" and pct == 1.0:
            sub05 = grid[(grid.cenario == "S2") & (grid.pct == 0.5)]
            if not sub05.empty:
                agg05 = sub05.groupby("wu").agg(cpu_media=("peak_cpu", "mean"),
                                                 cpu_std=("peak_cpu", "std")).reset_index()
                ax.errorbar(agg05["wu"], agg05["cpu_media"], yerr=agg05["cpu_std"].fillna(0),
                             color=ORANGE, linestyle="--", marker="s", markersize=6,
                             capsize=4, label="0.5% (comparação)", zorder=2)
                ax.legend(fontsize=8)

        ax.axhline(config.CPU_THRESHOLD_SCALE_UP, color=RED, linestyle=":", linewidth=1)
        ax.set_xlabel("Custo por requisição de ataque (WU)")
        ax.set_ylabel("Pico de CPU (%) — média ± desvio entre repetições")
        ax.set_title(titulo)
        ax.grid(True, alpha=0.25)

    if sc_plot is not None:
        cbar = fig.colorbar(sc_plot, ax=list(axes), fraction=0.02, pad=0.02)
        cbar.set_label("Fração de repetições com SCALE_UP")
    fig.suptitle("Stage 1B — refino fino nas fronteiras (repetições reais)\n"
                 "rótulo \"n=\" = nº de repetições nesse WU", fontsize=12, y=1.04)
    caminho = os.path.join(OUT_DIR, "10_wedos_refinamento_fronteiras.png")
    fig.savefig(caminho, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"[OK] {caminho}")


def plot_reprodutibilidade():
    padrao = os.path.join(NB_DIR, "metrics_normal_rps75_WU10_repro_lote*_rep*.csv")
    arquivos = sorted(glob.glob(padrao))
    if not arquivos:
        print("[SKIP] reprodutibilidade: sem arquivos _repro_lote*")
        return
    linhas = []
    for f in arquivos:
        m = re.search(r"_repro_lote([AB])_rep(\d+)\.csv$", f)
        if not m:
            continue
        lote, rep = m.groups()
        df = pd.read_csv(f)
        linhas.append(dict(lote=lote, rep=int(rep), peak_cpu=df["average_cpu_percent"].max(),
                            scaleups=int((df["decision"] == "SCALE_UP").sum())))
    rdf = pd.DataFrame(linhas)

    fig, ax = plt.subplots(figsize=(7, 5.5))
    cores = {"A": BLUE, "B": ORANGE}
    for lote in sorted(rdf["lote"].unique()):
        sub = rdf[rdf.lote == lote]
        ax.scatter([lote] * len(sub), sub["peak_cpu"], color=cores[lote], s=90, zorder=3)
        ax.scatter([lote], [sub["peak_cpu"].mean()], color=cores[lote], marker="_", s=800,
                   linewidth=3, zorder=4)
    ax.axhline(config.CPU_THRESHOLD_SCALE_UP, color=RED, linestyle="--", linewidth=1,
               label=f"limiar SCALE_UP ({config.CPU_THRESHOLD_SCALE_UP:.0f}%)")
    ax.set_ylabel("Pico de CPU (%)")
    ax.set_xlabel("Lote (A = ambiente recém-reiniciado, B = após dezenas de execuções)")
    ax.set_title("Teste de reprodutibilidade — candidato S4=300 agregado, WU=10\n"
                  "traço horizontal = média do lote")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.25, axis="y")
    fig.tight_layout()
    caminho = os.path.join(OUT_DIR, "08_wedos_reprodutibilidade_loteA_loteB.png")
    fig.savefig(caminho, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"[OK] {caminho}")


def plot_fronteira_falha():
    arquivos = sorted(glob.glob(os.path.join(FAILURE_DIR, "attack_summary_log_*.csv")))
    if not arquivos:
        print("[SKIP] fronteira de falha: sem dados em wedos_failure/")
        return
    linhas = []
    pat = re.compile(r"attack_summary_log_(wu|rps|attackers)_rps(\d+)_att(\d+)_WU(\d+)_rep(\d+)\.csv$")
    for f in arquivos:
        m = pat.search(os.path.basename(f))
        if not m:
            continue
        axis, rps, att, wu, rep = m.groups()
        adf = pd.read_csv(f)
        ok = pd.to_numeric(adf.get("total_requests"), errors="coerce").sum()
        err = pd.to_numeric(adf.get("errors"), errors="coerce").sum()
        total = (ok or 0) + (err or 0)
        error_rate = (err / total) if total else None
        linhas.append(dict(axis=axis, rps=int(rps), attackers=int(att), wu=int(wu),
                            rep=int(rep), error_rate=error_rate))
    fdf = pd.DataFrame(linhas).dropna(subset=["error_rate"])
    if fdf.empty:
        print("[SKIP] fronteira de falha: attack_summary_log sem linhas de worker (total_requests/errors)")
        return

    axis_param = {"wu": ("wu", "Work Units (custo por requisição)"),
                  "rps": ("rps", "RPS por atacante"),
                  "attackers": ("attackers", "Nº de atacantes")}
    axes_presentes = [a for a in axis_param if a in fdf["axis"].unique()]
    if not axes_presentes:
        print("[SKIP] fronteira de falha: eixos não reconhecidos")
        return

    fig, axes = plt.subplots(1, len(axes_presentes), figsize=(5.5 * len(axes_presentes), 4.8), squeeze=False)
    axes = axes[0]
    for ax, axis in zip(axes, axes_presentes):
        col, label = axis_param[axis]
        sub = fdf[fdf.axis == axis].groupby(col)["error_rate"].agg(["mean", "std", "count"]).reset_index()
        ax.errorbar(sub[col], sub["mean"] * 100, yerr=sub["std"].fillna(0) * 100,
                    marker="o", color=BLUE, capsize=4)
        ax.axhline(1, color=ORANGE, linestyle="--", linewidth=1, label="falha leve (1%)")
        ax.axhline(10, color=RED, linestyle="--", linewidth=1, label="falha severa (10%)")
        ax.set_xlabel(label)
        ax.set_ylabel("Taxa de erro de requisição (%)")
        ax.set_title(f"Eixo: {label}")
        ax.grid(True, alpha=0.25)
        ax.legend(fontsize=8)
    fig.suptitle("Fase 4 — fronteira de falha por eixo (OFAT)", fontsize=12, y=1.03)
    fig.tight_layout()
    caminho = os.path.join(OUT_DIR, "09_wedos_fronteira_falha.png")
    fig.savefig(caminho, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"[OK] {caminho}")


if __name__ == "__main__":
    grid = carregar_grid()
    print(f"Carregados {len(grid)} pontos de experiment_results/wedos_grid/\n")
    plot_heatmap(grid)
    plot_efetividade_furtividade(grid)
    plot_refinamento_fronteiras(grid)
    plot_reprodutibilidade()
    plot_fronteira_falha()
    print(f"\nGráficos salvos em {OUT_DIR}/")
