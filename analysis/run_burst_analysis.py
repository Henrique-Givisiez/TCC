import glob
import os

from analysis.EntCusumZV3 import analisar_bursts_tunavel

# Roda a detecção de bursts (EntCusumZV3) sobre cada rtt_log_*.csv salvo por
# qualquer varredura (run_experiments.py, run_experiments_combined.py), em
# vez de só sobre o rtt_log.csv solto da última execução. Busca recursiva
# porque cada varredura agora salva em seu próprio subdiretório dentro de
# experiment_results/ (normal_baseline/, wu_calibration/, combined_sweep/).
# Saídas (.xlsx/.png) vão para o mesmo subdiretório de cada rtt_log_*.csv,
# com o mesmo sufixo no nome.

RESULTS_DIR = "experiment_results"

rtt_log_files = sorted(glob.glob(os.path.join(RESULTS_DIR, "**", "rtt_log_*.csv"), recursive=True))

if not rtt_log_files:
    print(f"[WARNING] Nenhum rtt_log_*.csv encontrado em {RESULTS_DIR}/.")

for rtt_log_file in rtt_log_files:
    print(f"\n===== Analisando {rtt_log_file} =====")
    analisar_bursts_tunavel(input_file=rtt_log_file, show_plot=False)

print(f"\nAnálise de bursts concluída para {len(rtt_log_files)} arquivo(s).")
