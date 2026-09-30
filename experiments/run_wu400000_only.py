import subprocess
import itertools
import os
import shutil
from experiments.result_archive import move_result

# Complemento pontual a run_experiments.py: só WU=400000 (potência de 2 a
# partir de 100000/200000, no lugar de 500000 -- pedido do usuário, ver
# changes.txt). NÃO mexe em run_experiments.py nem nos dados já coletados
# de WU=100000/200000/500000 -- só adiciona os 3 arquivos que faltam
# (rps=1,5,10 x attackers=4 x WU=400000), com a MESMA convenção de nome de
# run_experiments.py, para cair ao lado dos arquivos existentes em
# experiment_results/wu_calibration/.

RPS_VALUES = [1, 5, 10]
ATTACKERS_VALUES = [4]
WORK_UNITS_VALUES = [400000]

RESULTS_DIR = "experiment_results/wu_calibration"
os.makedirs(RESULTS_DIR, exist_ok=True)

for rps, attackers, work_units in itertools.product(RPS_VALUES, ATTACKERS_VALUES, WORK_UNITS_VALUES):

    print(f"\n===== WU400000-only: RPS={rps}, ATTACKERS={attackers}, WORK_UNITS={work_units} =====")

    cmd = [
        "python3", "-m",
        "simulator.main_orchestrator",
        "--rps", str(rps),
        "--attackers", str(attackers),
        "--work-units", str(work_units),
        "--duration", "180",
    ]

    subprocess.run(cmd)

    move_result(
        "simulation_metrics.csv",
        os.path.join(RESULTS_DIR, f"metrics_rps{rps}_att{attackers}_WU{work_units}.csv")
    )

    attack_summary_src = "attack_summary_log.csv"
    attack_summary_dst = os.path.join(RESULTS_DIR, f"attack_summary_log_{rps}_{attackers}_WU{work_units}.csv")
    if os.path.exists(attack_summary_src):
        shutil.move(attack_summary_src, attack_summary_dst)
    else:
        print(f"[WARNING] {attack_summary_src} não encontrado.")

    rtt_log_src = "rtt_log.csv"
    rtt_log_dst = os.path.join(RESULTS_DIR, f"rtt_log_rps{rps}_att{attackers}_WU{work_units}.csv")
    if os.path.exists(rtt_log_src):
        shutil.move(rtt_log_src, rtt_log_dst)
    else:
        print(f"[WARNING] {rtt_log_src} não encontrado.")

    traffic_capture_src = "traffic_capture.csv"
    traffic_capture_dst = os.path.join(RESULTS_DIR, f"traffic_capture_rps{rps}_att{attackers}_WU{work_units}.csv")
    if os.path.exists(traffic_capture_src):
        shutil.move(traffic_capture_src, traffic_capture_dst)
    else:
        print(f"[WARNING] {traffic_capture_src} não encontrado.")

    # normal_traffic_summary_log.csv: run_experiments.py (a varredura
    # original) não movia esse arquivo -- mantido consistente aqui também,
    # até porque wu_calibration roda COM ataque + tráfego normal fixo (não
    # é o foco desta análise pontual).
    if os.path.exists("normal_traffic_summary_log.csv"):
        os.remove("normal_traffic_summary_log.csv")

print("\nWU400000-only: todas as execuções concluídas.")
