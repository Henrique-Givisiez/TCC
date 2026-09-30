import subprocess
import itertools
import os
import shutil

# Repetições extras para os 2 pontos do grid clientes×RPS que deram runs
# catastróficos isolados (agg=256/clientes=8 rep2 e agg=512/clientes=8
# rep5 -- ver changes.txt): a maioria das threads de tráfego normal não
# conseguiu logar o fim, com ~30s a mais de duração e ~55-58% de taxa de
# erro nas poucas que logaram, contra 0% erro nas outras execuções do
# mesmo ponto. Objetivo: ver se o problema se repete (padrão sistemático
# de "8 clientes") ou não reaparece (confirma soluço isolado de
# ambiente, como já visto antes neste projeto -- changes.txt §31).
#
# Reps numerados 6-10 (não sobrescreve rep1-5, os dados originais,
# incluindo os 2 runs ruins, ficam preservados para o registro).

TARGETS = [(256, 8), (512, 8)]
EXTRA_REPS = range(6, 11)  # 6,7,8,9,10 -- 5 repetições extras por ponto
WORK_UNITS = 10
DURATION = 180

RESULTS_DIR = "experiment_results/clients_rps_grid"
os.makedirs(RESULTS_DIR, exist_ok=True)

combos = list(itertools.product(TARGETS, EXTRA_REPS))
total = len(combos)

for i, ((aggregate, clients), rep) in enumerate(combos, start=1):
    rps_per_client = aggregate / clients

    print(f"\n===== [{i}/{total}] extra_reps_clients8: agregado={aggregate}, "
          f"clientes={clients}, rps/cliente={rps_per_client}, rep {rep} =====")

    cmd = [
        "python3", "-m",
        "simulator.main_orchestrator",
        "--normal-rps", str(rps_per_client),
        "--normal-clients", str(clients),
        "--normal-work-units", str(WORK_UNITS),
        "--attack-duration", "0",
        "--duration", str(DURATION),
    ]

    subprocess.run(cmd)

    suffix = f"agg{aggregate}_clients{clients}_WU{WORK_UNITS}_rep{rep}"

    shutil.move("simulation_metrics.csv", os.path.join(RESULTS_DIR, f"metrics_{suffix}.csv"))

    if os.path.exists("attack_summary_log.csv"):
        os.remove("attack_summary_log.csv")

    normal_summary_src = "normal_traffic_summary_log.csv"
    if os.path.exists(normal_summary_src):
        shutil.move(normal_summary_src, os.path.join(RESULTS_DIR, f"normal_traffic_summary_log_{suffix}.csv"))
    else:
        print(f"[WARNING] {normal_summary_src} não encontrado.")

    rtt_log_src = "rtt_log.csv"
    if os.path.exists(rtt_log_src):
        shutil.move(rtt_log_src, os.path.join(RESULTS_DIR, f"rtt_log_{suffix}.csv"))
    else:
        print(f"[WARNING] {rtt_log_src} não encontrado.")

    traffic_capture_src = "traffic_capture.csv"
    if os.path.exists(traffic_capture_src):
        shutil.move(traffic_capture_src, os.path.join(RESULTS_DIR, f"traffic_capture_{suffix}.csv"))
    else:
        print(f"[WARNING] {traffic_capture_src} não encontrado.")

print("\nextra_reps_clients8: todas as execuções concluídas.")
