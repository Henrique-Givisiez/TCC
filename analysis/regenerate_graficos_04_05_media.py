import os
import statistics as stats

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

# Regera os graficos 04 e 05 (results/graficos_apresentacao/) usando CPU MEDIA em vez
# de CPU DE PICO como estatistica de comparacao entre cenarios, mantendo os
# arquivos antigos intocados (saida com sufixo _MEDIA, nome novo, nao
# sobrescreve os originais 04_curva_capacidade_reproducibilidade.png e
# 05_wu_calibration_resumo_atual.png). Justificativa completa (por que media
# em vez de pico) esta em changes.txt.
#
# So le CSVs ja existentes em experiment_results/ -- nao roda nenhuma
# simulacao nova.

NB_DIR = "experiment_results/normal_baseline"
WU_DIR = "experiment_results/wu_calibration"
OUT_DIR = "results/graficos_apresentacao/01_curva_capacidade_baseline"
os.makedirs(OUT_DIR, exist_ok=True)

BLUE = "#2a78d6"
GREEN = "#1baf7a"
RED = "#d03b3b"
ORANGE = "#e08a1e"


def mean_cpu(path, label_filter=None):
    """Media de average_cpu_percent, descartando a primeira linha (t=0, antes
    do trafego estabilizar) e, se label_filter for dado, restrita as linhas
    daquele label (ex.: 'attack') -- nunca a media do arquivo inteiro, que
    dilui o sinal com o periodo de warmup/idle."""
    df = pd.read_csv(path)
    df = df.iloc[1:]  # descarta a amostra t=0.01 (sempre 0.0, antes do trafego iniciar)
    if label_filter is not None:
        df = df[df["label"] == label_filter]
    return df["average_cpu_percent"].mean()


# =====================================================================
# Grafico 04 -- curva de capacidade do baseline normal (WU=10), MEDIA
# =====================================================================

# Pontos de amostra unica (sem repeticao disponivel)
single_points = [
    (40, os.path.join(NB_DIR, "metrics_normal_rps10_WU10.csv")),
    (100, os.path.join(NB_DIR, "metrics_normal_rps25_WU10.csv")),
    (200, os.path.join(NB_DIR, "metrics_normal_rps50_WU10.csv")),
    (400, os.path.join(NB_DIR, "metrics_normal_rps100_WU10.csv")),
]
single_x = [p[0] for p in single_points]
single_y = [mean_cpu(p[1]) for p in single_points]

# 250 agregado -- 3 repeticoes originais (rps62.5 x 4 clientes)
rep250_files = [
    os.path.join(NB_DIR, f"metrics_normal_rps62.5_WU10_rep{i}.csv") for i in (1, 2, 3)
]
rep250_vals = [mean_cpu(f) for f in rep250_files]

# 300 agregado -- todas as repeticoes reais disponiveis (rps75 x 4 clientes):
# a reexecucao atualmente salva em metrics_normal_rps75_WU10.csv + os 6 lotes
# de reproducibilidade (loteA/loteB) de wedos_repro_test.py. A 1a amostra
# isolada (53.6% de pico, mencionada no RESUMO_MADRUGADA_12_08.txt) foi
# sobrescrita no disco e nao pode ser recuperada -- nao esta incluida aqui.
rep300_files = [os.path.join(NB_DIR, "metrics_normal_rps75_WU10.csv")]
for lote in ("loteA", "loteB"):
    for i in (1, 2, 3):
        rep300_files.append(
            os.path.join(NB_DIR, f"metrics_normal_rps75_WU10_repro_{lote}_rep{i}.csv")
        )
rep300_vals = [mean_cpu(f) for f in rep300_files]

fig, ax = plt.subplots(figsize=(11, 7))

ax.plot(single_x, single_y, "o-", color=BLUE, markersize=10, linewidth=2,
        label="CPU media (1 amostra)")

ax.scatter([250] * len(rep250_vals), rep250_vals, color=RED, marker="x", s=140,
           linewidths=3, label=f"CPU media (250 agregado, {len(rep250_vals)} repeticoes)")

mean300 = stats.mean(rep300_vals)
std300 = stats.stdev(rep300_vals)
ax.errorbar([300], [mean300], yerr=[std300], fmt="D", color=ORANGE, markersize=14,
            capsize=8, elinewidth=2,
            label=f"300 agregado, media={mean300:.1f}% +/- {std300:.1f}pp ({len(rep300_vals)} reps)")
ax.scatter([300] * len(rep300_vals), rep300_vals, color=ORANGE, marker=".", s=60, alpha=0.5, zorder=1)

ax.axhline(60, color=RED, linestyle="--", linewidth=1, label="limiar SCALE_UP (60%)")

ax.set_xlabel("RPS agregado (trafego normal, WU=10)")
ax.set_ylabel("CPU media (%)")
ax.set_title(
    "Curva de capacidade do baseline normal (WU=10) -- CPU MEDIA, nao pico\n"
    "Mesma base de dados do grafico 04 original, estatistica trocada de pico para media"
)
ax.legend(loc="upper left")
ax.grid(True, alpha=0.3)
fig.tight_layout()
out04 = os.path.join(OUT_DIR, "04_curva_capacidade_reproducibilidade_MEDIA.png")
fig.savefig(out04, dpi=110)
plt.close(fig)
print(f"Salvo: {out04}")
print(f"  40/100/200/400 (1 amostra, media): {[round(v,1) for v in single_y]}")
print(f"  250 (3 reps, media de cada rep): {[round(v,1) for v in rep250_vals]}")
print(f"  300 ({len(rep300_vals)} reps, media de cada rep): {[round(v,1) for v in rep300_vals]} "
      f"-> media={mean300:.1f} desvio={std300:.1f}")


# =====================================================================
# Grafico 05 -- wu_calibration, CPU MEDIA (painel esquerdo) + erros (direito,
# inalterado -- ja era uma boa evidencia de saturacao antes da mudanca)
# =====================================================================

rps_values = [1, 5, 10]
wu_values = [100000, 200000, 500000]
colors = {100000: BLUE, 200000: GREEN, 500000: RED}

mean_cpu_grid = {}
err_grid = {}
for rps in rps_values:
    for wu in wu_values:
        mf = os.path.join(WU_DIR, f"metrics_rps{rps}_att4_WU{wu}.csv")
        mean_cpu_grid[(rps, wu)] = mean_cpu(mf, label_filter="attack")

        af = os.path.join(WU_DIR, f"attack_summary_log_{rps}_4_WU{wu}.csv")
        adf = pd.read_csv(af)
        ok = adf["total_requests"].sum(skipna=True)
        err = adf["errors"].sum(skipna=True)
        err_grid[(rps, wu)] = err

fig, axes = plt.subplots(1, 2, figsize=(15, 6))

x = range(len(rps_values))
width = 0.25
for i, wu in enumerate(wu_values):
    vals = [mean_cpu_grid[(rps, wu)] for rps in rps_values]
    offset = (i - 1) * width
    axes[0].bar([xi + offset for xi in x], vals, width=width,
                color=colors[wu], label=f"WU={wu:,}".replace(",", "."))
axes[0].axhline(60, color=RED, linestyle="--", linewidth=1)
axes[0].set_xticks(list(x))
axes[0].set_xticklabels([f"rps={r}" for r in rps_values])
axes[0].set_ylabel("CPU media (%) -- so janelas de ataque")
axes[0].set_title("wu_calibration -- CPU MEDIA (nao pico)")
axes[0].legend()
axes[0].grid(True, alpha=0.3, axis="y")

for i, wu in enumerate(wu_values):
    vals = [err_grid[(rps, wu)] for rps in rps_values]
    offset = (i - 1) * width
    axes[1].bar([xi + offset for xi in x], vals, width=width, color=colors[wu],
                label=f"WU={wu:,}".replace(",", "."))
axes[1].set_xticks(list(x))
axes[1].set_xticklabels([f"rps={r}" for r in rps_values])
axes[1].set_ylabel("Total de erros de requisicao")
axes[1].set_title("wu_calibration (pos-fix) -- falhas de requisicao (sem mudanca)")
axes[1].legend()
axes[1].grid(True, alpha=0.3, axis="y")

fig.suptitle("Estado atual da varredura de calibracao de WU -- CPU MEDIA em vez de pico")
fig.tight_layout()
out05 = os.path.join(OUT_DIR, "05_wu_calibration_resumo_MEDIA.png")
fig.savefig(out05, dpi=110)
plt.close(fig)
print(f"Salvo: {out05}")
for rps in rps_values:
    for wu in wu_values:
        print(f"  rps={rps:>2} WU={wu:>6}: media={mean_cpu_grid[(rps,wu)]:6.1f}  erros={err_grid[(rps,wu)]:6.0f}")
