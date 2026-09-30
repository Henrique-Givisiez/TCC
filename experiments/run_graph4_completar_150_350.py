import subprocess
import os
import shutil

# Tarefa 6a: completa a série do gráfico 04/16/18/20 pra 10 repetições em
# cada ponto -- +5 repetições nos 6 pontos já existentes (40/100/200/300/400
# tinham rep1-5, viram rep1-10; 250 tinha rep1-8, vira rep1-13, +5 igual
# combinado) e 2 pontos novos (150, 350) com 10 repetições cada. Mesma
# metodologia de run_graph4_refined.py (WU=10, 4 clientes, sem ataque,
# 180s), salvando no MESMO diretório/convenção de nome
# (experiment_results/normal_baseline/metrics_normal_agg{A}_WU10_refined_rep{N}.csv)
# para os gráficos existentes (16/18/20) e o novo grid pow2 (tarefa 6b,
# que reaproveita o "40" daqui) lerem tudo com o mesmo glob pattern.

NUM_CLIENTS = 4
WORK_UNITS = 10
DURATION = 180

RESULTS_DIR = "experiment_results/normal_baseline"
os.makedirs(RESULTS_DIR, exist_ok=True)

# (agregado, [números de repetição a rodar])
PLANO = [
    (40, list(range(6, 11))),
    (100, list(range(6, 11))),
    (200, list(range(6, 11))),
    (250, list(range(9, 14))),
    (300, list(range(6, 11))),
    (400, list(range(6, 11))),
    (150, list(range(1, 11))),
    (350, list(range(1, 11))),
]

total = sum(len(reps) for _, reps in PLANO)
count = 0

for aggregate, reps in PLANO:
    rps_per_client = aggregate / NUM_CLIENTS
    for rep in reps:
        count += 1
        print(f"\n===== [{count}/{total}] completar_150_350: agregado={aggregate} "
              f"(rps/cliente={rps_per_client}), rep {rep} =====")

        cmd = [
            "python3", "-m",
            "simulator.main_orchestrator",
            "--normal-rps", str(rps_per_client),
            "--normal-work-units", str(WORK_UNITS),
            "--attack-duration", "0",
            "--duration", str(DURATION),
        ]

        subprocess.run(cmd)

        suffix = f"agg{aggregate}_WU{WORK_UNITS}_refined_rep{rep}"

        shutil.move("simulation_metrics.csv", os.path.join(RESULTS_DIR, f"metrics_normal_{suffix}.csv"))

        if os.path.exists("attack_summary_log.csv"):
            os.remove("attack_summary_log.csv")

        normal_summary_src = "normal_traffic_summary_log.csv"
        if os.path.exists(normal_summary_src):
            shutil.move(normal_summary_src, os.path.join(RESULTS_DIR, f"normal_traffic_summary_log_{suffix}.csv"))
        else:
            print(f"[WARNING] {normal_summary_src} não encontrado.")

        rtt_log_src = "rtt_log.csv"
        if os.path.exists(rtt_log_src):
            shutil.move(rtt_log_src, os.path.join(RESULTS_DIR, f"rtt_log_normal_{suffix}.csv"))
        else:
            print(f"[WARNING] {rtt_log_src} não encontrado.")

        traffic_capture_src = "traffic_capture.csv"
        if os.path.exists(traffic_capture_src):
            shutil.move(traffic_capture_src, os.path.join(RESULTS_DIR, f"traffic_capture_normal_{suffix}.csv"))
        else:
            print(f"[WARNING] {traffic_capture_src} não encontrado.")

print("\ncompletar_150_350: todas as execuções concluídas.")
