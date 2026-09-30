import glob
import os
import re

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from analysis.EntCusumZV3 import analisar_bursts_tunavel

# Fase 3 do plano de análise estatística: mede FALSO POSITIVO de verdade,
# usando experiment_results/clients_rps_grid/ -- tráfego 100% normal, SEM
# NENHUM ataque (dado já existente, nenhum experimento novo). Diferente do
# cenário combinado (seção anterior), aqui QUALQUER 'DDoS Burst' marcado é,
# por definição, um alarme falso -- não existe ataque nenhum pra detectar
# de verdade.
#
# Pergunta central: o detector confunde o SOLUÇO TRANSITÓRIO (perda de
# keep-alive, seção 42/54 do changes.txt -- não é ataque, é um artefato de
# ambiente) com um burst real? Cruza a contagem de alarmes com o mesmo
# critério MECÂNICO de detecção de soluço já usado em
# plot_clients_rps_invariance.py (menos linhas de worker-stop no
# normal_traffic_summary_log do que clientes configurados).

GRID_DIR = "experiment_results/clients_rps_grid"
OUT_DIR = "results/graficos_apresentacao/03_deteccao_estatistica"
os.makedirs(OUT_DIR, exist_ok=True)


def is_soluco(summary_path, expected_clients):
    if not os.path.exists(summary_path):
        return None  # sem dado pra decidir
    df = pd.read_csv(summary_path)
    df = df[df["total_requests"].notna()]
    return len(df) < expected_clients


rtt_files = sorted(glob.glob(os.path.join(GRID_DIR, "rtt_log_agg*_clients*_WU10_rep*.csv")))
print(f"Analisando {len(rtt_files)} arquivos de {GRID_DIR}...")

rows = []
for i, rtt_path in enumerate(rtt_files, start=1):
    m = re.search(r"rtt_log_agg(\d+)_clients(\d+)_WU10_rep(\d+)\.csv", os.path.basename(rtt_path))
    if not m:
        continue
    agg, clients, rep = int(m.group(1)), int(m.group(2)), int(m.group(3))
    suffix = f"agg{agg}_clients{clients}_WU10_rep{rep}"

    summary_path = os.path.join(GRID_DIR, f"normal_traffic_summary_log_{suffix}.csv")
    soluco = is_soluco(summary_path, clients)

    df_res = analisar_bursts_tunavel(input_file=rtt_path, output_prefix=suffix, show_plot=False)
    if df_res is None or df_res.empty:
        continue

    n_bursts = int((df_res["Status Burst"] == "DDoS Burst").sum())
    n_janelas = len(df_res)

    rows.append(dict(aggregate=agg, clients=clients, rep=rep, soluco=soluco,
                      n_bursts=n_bursts, n_janelas=n_janelas,
                      taxa_alarme=100.0 * n_bursts / n_janelas if n_janelas else 0.0))

    if i % 20 == 0:
        print(f"  ... {i}/{len(rtt_files)} processados")

df = pd.DataFrame(rows)
csv_out = os.path.join(GRID_DIR, "resumo_deteccao_clients_grid.csv")
df.to_csv(csv_out, index=False)
print(f"Salvo: {csv_out}")

# Resumo: taxa de alarme (qualquer burst >0) separado por grupo soluço/limpo.
df_valid = df[df["soluco"].notna()]
resumo = df_valid.groupby("soluco").agg(
    n_execucoes=("n_bursts", "size"),
    pct_com_algum_alarme=("n_bursts", lambda s: 100.0 * (s > 0).sum() / len(s)),
    media_bursts_por_execucao=("n_bursts", "mean"),
).reset_index()
resumo["soluco"] = resumo["soluco"].map({True: "COM soluço (mecânico)", False: "limpo (mecânico)"})
print("\n" + resumo.to_string(index=False))

fig, ax = plt.subplots(figsize=(8, 6))
x = range(len(resumo))
bars = ax.bar(x, resumo["pct_com_algum_alarme"], color=["#d03b3b", "#1baf7a"])
ax.set_xticks(list(x))
ax.set_xticklabels(resumo["soluco"])
ax.set_ylabel("% de execuções com pelo menos 1 alarme falso ('DDoS Burst')")
ax.set_ylim(0, 100)
for i, v in enumerate(resumo["pct_com_algum_alarme"]):
    n = resumo["n_execucoes"].iloc[i]
    ax.text(i, v + 2, f"{v:.1f}%\n(n={n})", ha="center", fontsize=10)
ax.set_title(
    "Falso positivo em tráfego 100% normal (sem ataque) -- clients_rps_grid\n"
    "O detector confunde o soluço transitório com um burst real?"
)
ax.grid(True, alpha=0.3, axis="y")
fig.tight_layout()
out_path = os.path.join(OUT_DIR, "32_falso_positivo_soluco.png")
fig.savefig(out_path, dpi=110)
plt.close(fig)
print(f"Salvo: {out_path}")
