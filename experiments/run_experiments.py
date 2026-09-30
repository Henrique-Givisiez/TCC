import subprocess
import itertools
import os
import shutil
from experiments.result_archive import move_result
from datetime import datetime

RPS_VALUES = [1,5,10]
ATTACKERS_VALUES = [4]
WORK_UNITS_VALUES = [100000,200000,500000]

RESULTS_DIR = "experiment_results/wu_calibration"
os.makedirs(RESULTS_DIR, exist_ok=True)

for rps, attackers, work_units in itertools.product(RPS_VALUES, ATTACKERS_VALUES, WORK_UNITS_VALUES):

    print(f"\n===== Running Experiment RPS={rps}, ATTACKERS={attackers}, WORK_UNITS={work_units} =====")

    cmd = [
        # Sem "sudo" -- ver run_experiments_normal.py para a explicação
        # (setcap no tcpdump + Docker sem root; sudo aqui travaria
        # subprocess.run esperando senha interativa).
        "python3", "-m",
        "simulator.main_orchestrator",
        "--rps", str(rps),
        "--attackers", str(attackers),
        "--work-units", str(work_units),
        "--duration", "180"
    ]

    subprocess.run(cmd)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # =========================
    # Metrics log
    # =========================
    metrics_filename = (
        f"metrics_rps{rps}_att{attackers}_WU{work_units}.csv"
    )

    move_result(
        "simulation_metrics.csv",
        os.path.join(RESULTS_DIR, metrics_filename)
    )

        # =========================
    # Attack summary log
    # =========================
    attack_summary_src = "attack_summary_log.csv"
    attack_summary_filename = f"attack_summary_log_{rps}_{attackers}_WU{work_units}.csv"
    attack_summary_dst = os.path.join(RESULTS_DIR, attack_summary_filename)

    if os.path.exists(attack_summary_src):
        shutil.move(attack_summary_src, attack_summary_dst)
    else:
        print(f"[WARNING] {attack_summary_src} não encontrado.")

    # =========================
    # RTT log
    # =========================
    # rtt_log.csv é sobrescrito a cada execução do orchestrator (ver
    # normal_traffic.save_rtt_log), então precisa ser movido aqui como os
    # outros logs, ou cada iteração da varredura apaga o RTT da anterior.
    rtt_log_src = "rtt_log.csv"
    rtt_log_filename = f"rtt_log_rps{rps}_att{attackers}_WU{work_units}.csv"
    rtt_log_dst = os.path.join(RESULTS_DIR, rtt_log_filename)

    if os.path.exists(rtt_log_src):
        shutil.move(rtt_log_src, rtt_log_dst)
    else:
        print(f"[WARNING] {rtt_log_src} não encontrado.")

    # =========================
    # Traffic capture (tcpdump)
    # =========================
    # Mesmo problema do rtt_log.csv: traffic_capture.csv é sobrescrito a
    # cada execução (ver tcpdump_sniffer.TcpdumpSniffer._init_csv), então
    # sem mover aqui só a última execução da varredura fica preservada.
    traffic_capture_src = "traffic_capture.csv"
    traffic_capture_filename = f"traffic_capture_rps{rps}_att{attackers}_WU{work_units}.csv"
    traffic_capture_dst = os.path.join(RESULTS_DIR, traffic_capture_filename)

    if os.path.exists(traffic_capture_src):
        shutil.move(traffic_capture_src, traffic_capture_dst)
    else:
        print(f"[WARNING] {traffic_capture_src} não encontrado.")

print("\nAll experiments completed.")