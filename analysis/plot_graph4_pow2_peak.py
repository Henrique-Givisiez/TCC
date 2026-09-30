import glob
import os
import statistics as stats

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

# Versão "por pico" (como o gráfico 04 original) do gráfico 04, mas com
# RPS agregado em potência de 2 (16, 32, 64, 128, 256, 512) em vez dos
# valores originais (40, 100, 200, 250, 300, 400). Reaproveita dados já
# coletados em experiment_results/clients_rps_grid/ (mesma configuração de
# base do gráfico 04: WU=10, tráfego normal isolado, sem ataque) --
# especificamente o subconjunto de 4 clientes, mesma convenção de nº de
# clientes do gráfico 04 original, para ficar comparável 1:1. 5 repetições
# por ponto (bem mais que a 1 amostra do gráfico antigo).
#
# Estatística: MÉDIA DOS PICOS ± desvio-padrão entre repetições -- não é o
# pico de uma única execução (frágil, ver changes.txt), mas também não é a
# média das janelas de uma execução (esse já é o gráfico 04 REFINADA) --
# aqui cada repetição contribui com seu próprio pico, e reportamos a
# média/desvio desses picos. Mais o % de repetições que dispararam
# SCALE_UP de verdade, para deixar claro que picos altos == escalonamento
# real (ver changes.txt sobre pico vs média).

GRID_DIR = "experiment_results/clients_rps_grid"
OUT_DIR = "results/graficos_apresentacao/01_curva_capacidade_baseline"
os.makedirs(OUT_DIR, exist_ok=True)

BLUE = "#2a78d6"
RED = "#d03b3b"

AGGREGATE_TARGETS = [16, 32, 64, 128, 256, 512]
CLIENTS = 4

rows = []
for agg in AGGREGATE_TARGETS:
    files = sorted(glob.glob(os.path.join(GRID_DIR, f"metrics_agg{agg}_clients{CLIENTS}_WU10_rep*.csv")))
    if not files:
        print(f"[WARNING] Sem dados para agregado={agg}, clientes={CLIENTS}.")
        continue

    peaks, scale_up_flags = [], []
    for f in files:
        df = pd.read_csv(f).iloc[1:]  # descarta t=0
        peaks.append(df["average_cpu_percent"].max())
        scale_up_flags.append((df["decision"] == "SCALE_UP").any())

    rows.append(dict(
        aggregate=agg, n=len(peaks),
        peak_mean=stats.mean(peaks),
        peak_std=stats.stdev(peaks) if len(peaks) > 1 else 0.0,
        peak_min=min(peaks), peak_max=max(peaks),
        scale_up_pct=100.0 * sum(scale_up_flags) / len(scale_up_flags),
    ))

df = pd.DataFrame(rows)
print(df.to_string(index=False))

fig, ax = plt.subplots(figsize=(11, 7))

ax.errorbar(df["aggregate"], df["peak_mean"], yerr=df["peak_std"],
            fmt="o-", color=BLUE, markersize=10, linewidth=2, capsize=6,
            label=f"CPU de pico (média ± desvio, {CLIENTS} clientes, 5 reps/ponto)")

# Mostra também a faixa min-max dos picos, para dar uma ideia da variação
# real entre repetições sem exagerar com barra de erro em cima de barra.
ax.fill_between(df["aggregate"], df["peak_min"], df["peak_max"], color=BLUE, alpha=0.08)

ax.axhline(60, color=RED, linestyle="--", linewidth=1, label="limiar SCALE_UP (60%)")

for _, row in df.iterrows():
    ax.annotate(f"{row['scale_up_pct']:.0f}% das reps\nescalou de verdade",
                xy=(row["aggregate"], row["peak_mean"]),
                xytext=(0, 14), textcoords="offset points",
                ha="center", fontsize=8, color="#444")

ax.set_xscale("log", base=2)
ax.set_xticks(AGGREGATE_TARGETS)
ax.set_xticklabels([str(a) for a in AGGREGATE_TARGETS])
ax.set_xlabel(f"RPS agregado (tráfego normal, WU=10, {CLIENTS} clientes, escala log2)")
ax.set_ylabel("CPU de pico (%)")
ax.set_title(
    "Curva de capacidade por PICO -- potências de 2\n"
    "Média dos picos ± desvio entre 5 repetições (faixa sombreada = min-max)"
)
ax.legend(loc="upper left", fontsize=9)
ax.grid(True, alpha=0.3)

fig.tight_layout()
out_path = os.path.join(OUT_DIR, "13_curva_capacidade_pico_pow2.png")
fig.savefig(out_path, dpi=110)
plt.close(fig)
print(f"\nSalvo: {out_path}")

csv_out = os.path.join(GRID_DIR, "resumo_graph4_pico_pow2.csv")
df.to_csv(csv_out, index=False)
print(f"Salvo: {csv_out}")
