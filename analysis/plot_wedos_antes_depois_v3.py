import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# Versão 3 do gráfico 33/34 -- correção de consistência de métrica, não
# correção de bug. O gráfico 34 (v2) media "pelo menos 1 alarme em
# qualquer lugar da execução inteira" (métrica por EXECUÇÃO); os gráficos
# 35-37 medem "% de janelas DENTRO do período real de ataque" (métrica
# por JANELA, mais rigorosa). As duas são válidas isoladamente, mas
# misturadas na mesma seção do relatório sem aviso, criam risco real de
# comparação incorreta entre gráficos. Esta versão usa tpr_novo/tpr_antigo
# (já calculados por run_burst_detection_wedos_final.py com a métrica por
# janela) para os dois lados da comparação antes/depois -- uma só
# definição de "detectado" em toda a seção. Não sobrescreve o 33 nem o 34.

IN_CSV = "experiment_results/resumo_deteccao_wedos_combined_final.csv"
OUT_DIR = "results/graficos_apresentacao/03_deteccao_estatistica"
os.makedirs(OUT_DIR, exist_ok=True)

df = pd.read_csv(IN_CSV)
extra = df["cenario"].str.extract(r"^(S[1-4])_atk(\d+)pct")
df["cenario_S"] = extra[0]
df["intensidade_pct"] = extra[1].astype("Int64")
df = df.dropna(subset=["cenario_S", "intensidade_pct"])

S_VALUES = ["S1", "S2", "S3", "S4"]
PCT_VALUES = [1, 5, 10]
S_RPS_FUNDO = {"S1": 40, "S2": 100, "S3": 200, "S4": 300}

tpr_matrix = np.full((len(S_VALUES), len(PCT_VALUES)), np.nan)
tpr_antigo_matrix = np.full((len(S_VALUES), len(PCT_VALUES)), np.nan)
n_matrix = np.full((len(S_VALUES), len(PCT_VALUES)), 0)

for i, s in enumerate(S_VALUES):
    for j, pct in enumerate(PCT_VALUES):
        cell = df[(df["cenario_S"] == s) & (df["intensidade_pct"] == pct)]
        escalou = cell[cell["escalou_real"] == True].dropna(subset=["tpr_novo"])
        if escalou.empty:
            continue
        tpr_matrix[i, j] = escalou["tpr_novo"].mean()
        tpr_antigo_matrix[i, j] = escalou["tpr_antigo"].mean()
        n_matrix[i, j] = len(escalou)

fig, ax = plt.subplots(figsize=(9.5, 7))
im = ax.imshow(tpr_matrix, cmap="RdYlGn", aspect="auto", origin="upper", vmin=0, vmax=100)

ax.set_xticks(range(len(PCT_VALUES)))
ax.set_xticklabels([f"{p}% do agregado" for p in PCT_VALUES])
ax.set_yticks(range(len(S_VALUES)))
ax.set_yticklabels([f"{s} ({S_RPS_FUNDO[s]} rps normal)" for s in S_VALUES])
ax.set_xlabel("intensidade do ataque (% do RPS agregado de fundo -- NÃO é rps do atacante)")
ax.set_ylabel("cenário de fundo (S1-S4 = nível de tráfego normal de base)")

for i in range(len(S_VALUES)):
    for j in range(len(PCT_VALUES)):
        tpr = tpr_matrix[i, j]
        if np.isnan(tpr):
            ax.text(j, i, "sem dado\n(nenhum SCALE_UP\nreal nesta célula)", ha="center", va="center",
                    color="#999", fontsize=8)
            continue
        n = int(n_matrix[i, j])
        tpr_antigo = tpr_antigo_matrix[i, j]
        diff = abs(tpr - tpr_antigo)
        igual = "idêntico ao antigo" if diff < 0.5 else f"antigo: {tpr_antigo:.0f}%"
        color = "white" if tpr < 35 or tpr > 70 else "black"
        label = f"{tpr:.0f}% detectado\n(n={n} com SCALE_UP real)\n{igual}"
        ax.text(j, i, label, ha="center", va="center", color=color, fontsize=9)

cbar = fig.colorbar(im, ax=ax, label="% de JANELAS dentro do ataque real marcadas 'DDoS Burst'")
cbar.ax.invert_yaxis()

ax.set_title(
    "Antes × depois da correção do CUSUM -- agregado por cenário (métrica por janela)\n"
    "Mesma definição de \"detectado\" dos gráficos 35-37 -- % de janelas dentro do ataque real, não execuções inteiras",
    fontsize=11,
)
fig.tight_layout()
out_path = os.path.join(OUT_DIR, "45_wedos_antes_depois_v3_por_janela.png")
fig.savefig(out_path, dpi=110)
plt.close(fig)
print(f"Salvo: {out_path}")

# comparação rápida com o resultado do gráfico 34 (execução inteira), pra
# deixar registrado se a conclusão "idêntico ao antigo" se mantém com a
# métrica mais rigorosa
diffs = np.abs(tpr_matrix - tpr_antigo_matrix)
diffs_validas = diffs[~np.isnan(diffs)]
print(f"\nMaior diferença antigo x novo (métrica por janela): {diffs_validas.max():.2f} pontos percentuais")
print(f"Células com diferença > 0.5pp: {(diffs_validas > 0.5).sum()} de {len(diffs_validas)}")
