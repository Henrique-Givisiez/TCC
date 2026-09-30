import glob
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from analysis.EntCusumZV3 import analisar_bursts_tunavel

# Fase 5 do plano de análise estatística: re-roda o detector CORRIGIDO
# (changes.txt seção 71) sobre experiment_results/wedos_grid/ e
# experiment_results/combined_sweep/ -- o dataset original que gerou o
# achado documentado no CLAUDE.md ("W-EDoS attack... completely
# undetected... S2 scenario, 1% attack intensity, WU=500000: SCALE_UP in
# 3/3 repetitions, 0 burst-flagged windows out of 56 total"), gerado com a
# versão do detector que TINHA o bug do CUSUM. Pergunta central: a
# correção muda essa conclusão?
#
# Para cada execução, usa o próprio simulation_metrics.csv (coluna
# 'label'=='attack') para determinar a janela REAL de ataque -- mais
# confiável que confiar em config.ATTACK_START_TIME_SECONDS/PULSE_DURATION
# hardcoded, já que esses parâmetros já mudaram entre sessões (ver
# changes.txt) -- e para determinar se SCALE_UP aconteceu de verdade
# (ground truth independente do detector de RTT).

DIRS = ["experiment_results/wedos_grid", "experiment_results/combined_sweep"]
OUT_DIR = "results/graficos_apresentacao/03_deteccao_estatistica"
os.makedirs(OUT_DIR, exist_ok=True)


def mmss_para_seg(s):
    mm, ss = s.split(":")
    return float(mm) * 60 + float(ss)


rows = []
for results_dir in DIRS:
    rtt_files = sorted(glob.glob(os.path.join(results_dir, "rtt_log_*.csv")))
    print(f"\n=== {results_dir}: {len(rtt_files)} arquivos ===")

    for rtt_path in rtt_files:
        suffix = os.path.basename(rtt_path)[len("rtt_log_"):-len(".csv")]
        metrics_path = os.path.join(results_dir, f"metrics_{suffix}.csv")
        old_xlsx_path = os.path.join(results_dir, f"rtt_bursts_{suffix}.xlsx")

        if not os.path.exists(metrics_path):
            print(f"[WARNING] Faltando {metrics_path}, pulando.")
            continue

        metrics = pd.read_csv(metrics_path)
        escalou_real = (metrics["decision"] == "SCALE_UP").any()
        attack_rows = metrics[metrics["label"] == "attack"]
        if attack_rows.empty:
            attack_start_real, attack_end_real = None, None
        else:
            attack_start_real = attack_rows["elapsed_time_s"].min()
            attack_end_real = attack_rows["elapsed_time_s"].max()

        # Resultado ANTIGO (detector com o bug do CUSUM, já em disco)
        n_bursts_antigo = None
        tpr_antigo = float("nan")
        if os.path.exists(old_xlsx_path):
            try:
                old_df = pd.read_excel(old_xlsx_path)
                n_bursts_antigo = int((old_df["Status Burst"] == "DDoS Burst").sum())
                if attack_start_real is not None:
                    tempos_antigo = old_df["Janela (MM:SS.s)"].apply(mmss_para_seg)
                    dentro_antigo = (tempos_antigo >= attack_start_real) & (tempos_antigo <= attack_end_real)
                    is_burst_antigo = old_df["Status Burst"] == "DDoS Burst"
                    if dentro_antigo.sum() > 0:
                        tpr_antigo = 100.0 * (is_burst_antigo & dentro_antigo).sum() / dentro_antigo.sum()
            except Exception as e:
                print(f"[WARNING] Não consegui ler {old_xlsx_path}: {e}")

        # Resultado NOVO (detector corrigido)
        df_res = analisar_bursts_tunavel(input_file=rtt_path, output_prefix=suffix, show_plot=False)
        if df_res is None or df_res.empty:
            print(f"[WARNING] Sem resultado para {rtt_path}.")
            continue

        n_bursts_novo = int((df_res["Status Burst"] == "DDoS Burst").sum())

        tpr_novo = float("nan")
        if attack_start_real is not None:
            tempos = df_res["Janela (MM:SS.s)"].apply(mmss_para_seg)
            dentro = (tempos >= attack_start_real) & (tempos <= attack_end_real)
            is_burst = df_res["Status Burst"] == "DDoS Burst"
            if dentro.sum() > 0:
                tpr_novo = 100.0 * (is_burst & dentro).sum() / dentro.sum()

        rows.append(dict(
            origem=os.path.basename(results_dir), cenario=suffix,
            escalou_real=escalou_real,
            n_bursts_antigo=n_bursts_antigo, n_bursts_novo=n_bursts_novo,
            tpr_antigo=tpr_antigo, tpr_novo=tpr_novo,
        ))

df = pd.DataFrame(rows)
pd.set_option("display.width", 200)
pd.set_option("display.max_rows", 200)
print("\n" + df.to_string(index=False))

csv_out = "experiment_results/resumo_deteccao_wedos_combined_final.csv"
df.to_csv(csv_out, index=False)
print(f"\nSalvo: {csv_out}")

# Foco no achado documentado: execuções que ESCALARAM de verdade
# (SCALE_UP real) -- quantas o detector ANTIGO (com bug) perdeu
# completamente (0 bursts) vs quantas o detector NOVO (corrigido) também
# perde.
escalou = df[df["escalou_real"] == True].copy()
escalou_com_antigo = escalou.dropna(subset=["n_bursts_antigo"])

n_total_escalou = len(escalou)
n_antigo_zero = int((escalou_com_antigo["n_bursts_antigo"] == 0).sum())
n_novo_zero = int((escalou["n_bursts_novo"] == 0).sum())

print(f"\n=== Execuções com SCALE_UP real (ground truth): {n_total_escalou} ===")
print(f"Detector ANTIGO (com bug): {n_antigo_zero}/{len(escalou_com_antigo)} tiveram 0 bursts detectados "
      f"(completamente perdido)")
print(f"Detector NOVO (corrigido): {n_novo_zero}/{n_total_escalou} tiveram 0 bursts detectados "
      f"(completamente perdido)")

# Gráfico resumo (Fase 6): comparação antigo x novo, só nas execuções que
# de fato escalaram (onde a diferença importa).
fig, ax = plt.subplots(figsize=(10, 6))
plot_df = escalou_com_antigo.sort_values("n_bursts_novo")
x = np.arange(len(plot_df))
width = 0.4
ax.bar(x - width / 2, plot_df["n_bursts_antigo"], width, label="Detector ANTIGO (com bug)", color="#d03b3b")
ax.bar(x + width / 2, plot_df["n_bursts_novo"], width, label="Detector NOVO (corrigido)", color="#1baf7a")
ax.set_xticks(x)
ax.set_xticklabels(plot_df["cenario"], rotation=90, fontsize=6)
ax.set_ylabel("nº de janelas marcadas 'DDoS Burst'")
ax.set_title(
    f"Antes x depois da correção do CUSUM -- só execuções com SCALE_UP real (n={len(plot_df)})\n"
    f"Antigo: {n_antigo_zero}/{len(plot_df)} completamente perdidos | "
    f"Novo: {int((plot_df['n_bursts_novo']==0).sum())}/{len(plot_df)} completamente perdidos"
)
ax.legend()
ax.grid(True, alpha=0.3, axis="y")
fig.tight_layout()
out_path = os.path.join(OUT_DIR, "33_deteccao_wedos_antes_depois.png")
fig.savefig(out_path, dpi=110)
plt.close(fig)
print(f"Salvo: {out_path}")
