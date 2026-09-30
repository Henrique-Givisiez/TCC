import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from simulator import config

# Continuação da investigação (seção 90 do changes.txt): a hipótese de fila
# de computação foi refutada (nenhum sinal de backlog crescendo entre as
# requisições bem-sucedidas). Próxima hipótese: esgotamento de portas/perda
# de keep-alive -- se conexões TCP estão sendo derrubadas sob carga, o
# cliente (requests.Session, que tenta reutilizar a conexão) é forçado a
# abrir uma conexão NOVA (porta efêmera nova) a cada tentativa, em vez de
# reaproveitar uma existente. Isso apareceria como um número de portas de
# origem ÚNICAS por janela de tempo muito alto (perto do nº de pacotes
# cliente->servidor da janela) exatamente no período em que os timeouts
# disparam -- ao contrário de keep-alive saudável, onde poucas portas são
# reaproveitadas por muitas requisições.
#
# Observação: o tcpdump aqui roda com -q (modo quieto), então as flags TCP
# (SYN/RST/FIN) não são capturadas em traffic_capture.csv -- não dá pra
# contar RSTs diretamente. Port churn é o proxy disponível nos dados já
# coletados, sem precisar recapturar nada.
#
# Célula analisada: mesma da seção 90 -- S4 (300 rps agregado normal), 1
# atacante, 15% de intensidade, WU=200000, rep1.

GRID_DIR = "experiment_results/atacantes_intensidade_grid"
OUT_DIR = "results/graficos_apresentacao/02_caracterizacao_ataque_wedos"
os.makedirs(OUT_DIR, exist_ok=True)

SUFFIX = "S4_atk15pct_att1_wu200000_rep1"
WINDOW_S = config.MONITOR_INTERVAL_SECONDS  # 5s, mesmo passo dos ticks do orquestrador

cap = pd.read_csv(os.path.join(GRID_DIR, f"traffic_capture_{SUFFIX}.csv"))
metrics = pd.read_csv(os.path.join(GRID_DIR, f"metrics_{SUFFIX}.csv"))

server_ports = set(range(config.STARTING_HOST_PORT,
                          config.STARTING_HOST_PORT + config.MAX_INSTANCES))

# Pacotes cliente -> servidor: dst_port é uma das portas publicadas das instâncias,
# src_port é a porta efêmera do lado do cliente (requests.Session).
c2s = cap[cap["dst_port"].isin(server_ports)].copy()
print(f"Total de pacotes capturados: {len(cap)}  |  cliente->servidor: {len(c2s)}")

c2s["window"] = (c2s["timestamp"] // WINDOW_S) * WINDOW_S

churn = c2s.groupby("window").agg(
    pacotes=("src_port", "size"),
    portas_unicas=("src_port", "nunique"),
).reset_index()
churn["churn_ratio"] = churn["portas_unicas"] / churn["pacotes"]

print(churn.to_string(index=False))
print(f"\nMédia geral de portas únicas/pacote: {churn['churn_ratio'].mean():.3f} "
      f"(1.0 = toda conexão é nova, keep-alive não está sendo reaproveitado; "
      f"perto de 0 = poucas conexões reaproveitadas por muitos pacotes)")

fig, (ax_pkt, ax_churn) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)

ax_pkt.plot(churn["window"], churn["pacotes"], color="tab:blue", label="Pacotes cliente->servidor / janela")
ax_pkt.plot(churn["window"], churn["portas_unicas"], color="tab:orange", label="Portas de origem únicas / janela")
ax_pkt.axvspan(config.ATTACK_START_TIME_SECONDS,
               config.ATTACK_START_TIME_SECONDS + config.PULSE_DURATION,
               color="orange", alpha=0.08, label="Janela do ataque")
for t in metrics.loc[metrics["decision"] == "SCALE_UP", "elapsed_time_s"]:
    ax_pkt.axvline(t, color="green", lw=0.8, alpha=0.5)
ax_pkt.set_ylabel(f"Contagem por janela de {WINDOW_S}s")
ax_pkt.set_title(f"Port churn -- {SUFFIX}\n(linhas verdes = SCALE_UP disparado)")
ax_pkt.legend(loc="upper right", fontsize=8)

ax_churn.plot(churn["window"], churn["churn_ratio"], color="tab:red")
ax_churn.axvspan(config.ATTACK_START_TIME_SECONDS,
                  config.ATTACK_START_TIME_SECONDS + config.PULSE_DURATION,
                  color="orange", alpha=0.08)
ax_churn.axhline(1.0, color="black", lw=1, linestyle=":", label="1.0 = toda porta é nova (sem reuso)")
ax_churn.set_ylabel("Portas únicas / pacotes (por janela)")
ax_churn.set_xlabel("Tempo decorrido (s)")
ax_churn.set_ylim(0, 1.05)
ax_churn.legend(loc="upper right", fontsize=8)

fig.tight_layout()
out_path = os.path.join(OUT_DIR, "51_port_churn_S4_att1_15pct.png")
fig.savefig(out_path, dpi=150, bbox_inches="tight")
plt.close(fig)
print(f"\nSalvo: {out_path}")
