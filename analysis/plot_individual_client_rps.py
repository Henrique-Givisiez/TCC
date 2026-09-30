import glob
import os
import re
import statistics as stats

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

# Prova, por CLIENTE INDIVIDUAL (não só pela soma), que a decomposição
# clientes x RPS/cliente do grid (plot_clients_rps_invariance.py) foi
# realizada como planejado: cada thread de cliente deveria atingir
# ~RPS_agregado/clientes de verdade. O gráfico 11 só mostra o agregado
# somado -- este mostra o RPS de CADA worker individualmente, contra o
# alvo individual, pedido explícito do usuário. Não sobrescreve nem
# apaga o gráfico 11.
#
# Mesmo critério de exclusão de run incompleto do gráfico 11 (menos linhas
# de worker-stop que clientes configurados -- sintoma do soluço
# transitório, ver changes.txt) -- reaproveitado aqui pela mesma razão.

GRID_DIR = "experiment_results/clients_rps_grid"
OUT_DIR = "results/graficos_apresentacao/01_curva_capacidade_baseline"
os.makedirs(OUT_DIR, exist_ok=True)

AGGREGATE_TARGETS = [16, 32, 64, 128, 256, 512]
CLIENT_COUNTS = [1, 2, 4, 8, 16]
COLORS = {1: "#2a78d6", 2: "#1baf7a", 4: "#e08a1e", 8: "#d03b3b", 16: "#7a3fd6"}
MARKERS = {1: "o", 2: "s", 4: "^", 8: "D", 16: "v"}

rows = []
raw_points = []  # (aggregate, clients, ratio_individual) -- para o strip de fundo

for agg in AGGREGATE_TARGETS:
    for clients in CLIENT_COUNTS:
        target_per_client = agg / clients
        pattern = os.path.join(GRID_DIR, f"normal_traffic_summary_log_agg{agg}_clients{clients}_WU10_rep*.csv")
        ratios = []
        for sf in sorted(glob.glob(pattern)):
            df = pd.read_csv(sf)
            df = df[df["total_requests"].notna()]
            if len(df) < clients:
                continue  # run incompleto (mesmo critério do gráfico 11) -- fora
            for real_rps in df["real_rps"]:
                ratio = real_rps / target_per_client
                ratios.append(ratio)
                raw_points.append((agg, clients, ratio))

        if not ratios:
            continue

        rows.append(dict(
            target_aggregate=agg, clients=clients, n_workers=len(ratios),
            target_per_client=target_per_client,
            ratio_mean=stats.mean(ratios),
            ratio_std=stats.stdev(ratios) if len(ratios) > 1 else 0.0,
        ))

df = pd.DataFrame(rows)
raw = pd.DataFrame(raw_points, columns=["aggregate", "clients", "ratio"])

fig, ax = plt.subplots(figsize=(12, 7))

# Pontos individuais de cada worker (todas as repeticoes), como um "strip"
# de fundo -- mostra a dispersao real cliente-a-cliente, nao so a media.
# Pequeno jitter horizontal (em espaco log2) por nº de clientes, so para
# as 5 nuvens de pontos no mesmo agregado nao ficarem 100% sobrepostas.
JITTER_STEPS = {1: -2, 2: -1, 4: 0, 8: 1, 16: 2}
for clients in CLIENT_COUNTS:
    sub_raw = raw[raw["clients"] == clients]
    offset = 2 ** (JITTER_STEPS[clients] * 0.025)
    xs = sub_raw["aggregate"] * offset
    ax.scatter(xs, sub_raw["ratio"], color=COLORS[clients], alpha=0.15, s=22, zorder=1, linewidths=0)

for clients in CLIENT_COUNTS:
    sub = df[df["clients"] == clients].sort_values("target_aggregate")
    if sub.empty:
        continue
    ax.errorbar(sub["target_aggregate"], sub["ratio_mean"], yerr=sub["ratio_std"],
                fmt=f"{MARKERS[clients]}-", color=COLORS[clients], markersize=8, linewidth=1.8,
                capsize=4, label=f"{clients} cliente(s)", zorder=3)

ax.axhline(1.0, color="#444", linestyle="--", linewidth=1, zorder=2,
           label="alvo individual (RPS agregado / nº clientes)")

ax.set_xscale("log", base=2)
ax.set_xticks(AGGREGATE_TARGETS)
ax.set_xticklabels([str(a) for a in AGGREGATE_TARGETS])
ax.set_xlabel("RPS agregado alvo (WU=10, escala log2)")
ax.set_ylabel("RPS individual alcançado / RPS individual alvo\n(1.0 = cada cliente atingiu exatamente sua fração do agregado)")
ax.set_title(
    "RPS individual por cliente vs. alvo -- prova da decomposição clientes×RPS\n"
    "Pontos claros = cada worker individual (todas as repetições); linhas = média por decomposição"
)
ax.legend(fontsize=8, loc="lower left")
ax.grid(True, alpha=0.3)

fig.tight_layout()
out_path = os.path.join(OUT_DIR, "12_rps_individual_por_cliente.png")
fig.savefig(out_path, dpi=110)
plt.close(fig)
print(f"Salvo: {out_path}")
print(df.to_string(index=False))

csv_out = os.path.join(GRID_DIR, "resumo_rps_individual.csv")
df.to_csv(csv_out, index=False)
print(f"Salvo: {csv_out}")
