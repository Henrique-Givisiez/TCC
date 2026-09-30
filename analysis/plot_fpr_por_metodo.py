import glob
import os
import re

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

# Fecha a ressalva da seção 75: os sinais individuais (Z-score/CUSUM sem
# o piso de RTT) são muito mais sensíveis que a decisão combinada nos
# casos furtivos (gráficos 35-37) -- mas isso tem custo em falso-positivo?
# Reaproveita os mesmos 160 .xlsx já salvos em clients_rps_grid/ (tráfego
# 100% normal, sem ataque nenhum -- o mesmo dataset do gráfico 32),
# cruzando com o soluço mecânico já identificado -- nenhum reprocessamento
# do detector, nenhum experimento novo.

GRID_DIR = "experiment_results/clients_rps_grid"
OUT_DIR = "results/graficos_apresentacao/03_deteccao_estatistica"
os.makedirs(OUT_DIR, exist_ok=True)

METODOS = {"Al. Ent.": ("Entropia de Shannon", "38"), "Al. Z": ("Z-score", "39"), "Al. CUSUM": ("CUSUM", "40")}


def is_soluco(summary_path, expected_clients):
    if not os.path.exists(summary_path):
        return None
    df = pd.read_csv(summary_path)
    df = df[df["total_requests"].notna()]
    return len(df) < expected_clients


xlsx_files = sorted(glob.glob(os.path.join(GRID_DIR, "rtt_bursts_agg*_clients*_WU10_rep*.xlsx")))
print(f"Processando {len(xlsx_files)} arquivos já existentes...")

rows = []
for xlsx_path in xlsx_files:
    suffix = os.path.basename(xlsx_path)[len("rtt_bursts_"):-len(".xlsx")]
    m = re.match(r"agg(\d+)_clients(\d+)_WU10_rep(\d+)", suffix)
    if not m:
        continue
    clients = int(m.group(2))
    summary_path = os.path.join(GRID_DIR, f"normal_traffic_summary_log_{suffix}.csv")
    soluco = is_soluco(summary_path, clients)

    df = pd.read_excel(xlsx_path)
    row = dict(suffix=suffix, soluco=soluco)
    for col in METODOS:
        row[col] = bool((df[col] == "Sim").any())
    rows.append(row)

df_all = pd.DataFrame(rows)
df_valid = df_all[df_all["soluco"].notna()]

fig, axes = plt.subplots(1, 3, figsize=(16, 6))

for ax, (col, (nome, num)) in zip(axes, METODOS.items()):
    resumo = df_valid.groupby("soluco")[col].agg(
        n_execucoes="size", pct_com_alarme=lambda s: 100.0 * s.sum() / len(s)
    ).reset_index()
    resumo["soluco_label"] = resumo["soluco"].map({True: "COM soluço", False: "limpo"})
    # cor por categoria (não por posição) -- limpo=verde/bom, soluço=vermelho/ruim,
    # mesma convenção do gráfico 32 original.
    cores = resumo["soluco"].map({True: "#d03b3b", False: "#1baf7a"})

    x = range(len(resumo))
    bars = ax.bar(x, resumo["pct_com_alarme"], color=cores)
    ax.set_xticks(list(x))
    ax.set_xticklabels(resumo["soluco_label"])
    ax.set_ylim(0, 100)
    ax.set_ylabel("% de execuções com pelo menos 1 alarme (falso, sem ataque real)")
    for i, v in enumerate(resumo["pct_com_alarme"]):
        n = resumo["n_execucoes"].iloc[i]
        ax.text(i, v + 2, f"{v:.1f}%\n(n={n})", ha="center", fontsize=9)
    ax.set_title(nome, fontsize=11)
    ax.grid(True, alpha=0.3, axis="y")

fig.suptitle(
    "Falso positivo por método INDIVIDUAL (sem piso de RTT) -- clients_rps_grid, 160 execuções\n"
    "Comparar com o gráfico 32 (decisão combinada: 0% limpo / 11.1% soluço)",
    fontsize=13,
)
fig.tight_layout()
out_path = os.path.join(OUT_DIR, "41_fpr_por_metodo.png")
fig.savefig(out_path, dpi=110)
plt.close(fig)
print(f"Salvo: {out_path}")

print("\n" + df_valid.groupby("soluco")[list(METODOS.keys())].mean().to_string())
