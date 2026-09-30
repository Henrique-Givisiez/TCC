import subprocess
import itertools
import os
import shutil

# Ataque ISOLADO de verdade -- sem tráfego normal nenhum (--normal-rps 0,
# que agora desliga de vez em vez de cair no fallback de 1req/s, ver
# normal_traffic.py). Mesmos parâmetros de rps/atacante e WU do gráfico
# 14 (wu_calibration original sempre teve 40 agregado de tráfego normal
# padrão junto -- essa é a primeira vez que isolamos o ataque puro).
# 1 repetição por combinação, mesmo padrão do wu_calibration original.

RPS_VALUES = [1, 5, 10]
WU_VALUES = [100000, 200000, 400000]
ATTACKERS = 4
DURATION = 180

RESULTS_DIR = "experiment_results/ataque_isolado"
os.makedirs(RESULTS_DIR, exist_ok=True)

for rps, wu in itertools.product(RPS_VALUES, WU_VALUES):
    print(f"\n===== ataque_isolado: rps/atacante={rps}, WU={wu} =====")

    cmd = [
        "python3", "-m",
        "simulator.main_orchestrator",
        "--rps", str(rps),
        "--attackers", str(ATTACKERS),
        "--work-units", str(wu),
        "--normal-rps", "0",
        "--duration", str(DURATION),
    ]

    subprocess.run(cmd)

    suffix = f"rps{rps}_att{ATTACKERS}_WU{wu}"

    shutil.move("simulation_metrics.csv", os.path.join(RESULTS_DIR, f"metrics_{suffix}.csv"))

    attack_summary_src = "attack_summary_log.csv"
    if os.path.exists(attack_summary_src):
        shutil.move(attack_summary_src, os.path.join(RESULTS_DIR, f"attack_summary_log_{suffix}.csv"))
    else:
        print(f"[WARNING] {attack_summary_src} não encontrado.")

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

    # normal_traffic_summary_log.csv: com --normal-rps 0, o tráfego normal
    # nunca inicia, então esse arquivo só tem a linha de cabeçalho -- sem
    # dado útil, descartado (mesma convenção de run_experiments_normal.py
    # pro attack_summary_log quando não há ataque).
    if os.path.exists("normal_traffic_summary_log.csv"):
        os.remove("normal_traffic_summary_log.csv")

print("\nataque_isolado: todas as execuções concluídas.")
