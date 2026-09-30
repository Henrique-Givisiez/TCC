import subprocess
import os
import shutil

# Completa o experimento de desempate (seção 62) com o rps=1 que tinha
# ficado de fora por decisão de escopo -- 5 repetições x 2 condições x 3
# WU = 30 execuções. Mesmo diretório/convenção de nome de
# run_desempate_combinado_isolado.py, pra somar ao dado já existente
# (rps=5/10) em vez de criar um conjunto separado.

RPS_VALUES = [1]
WU_VALUES = [100000, 200000, 400000]
ATTACKERS = 4
DURATION = 180
NUM_REPS = 5

RESULTS_DIR = "experiment_results/desempate_combinado_isolado"
os.makedirs(RESULTS_DIR, exist_ok=True)

CONDICOES = {
    "combinado": "10",
    "isolado": "0",
}

total = len(RPS_VALUES) * len(WU_VALUES) * NUM_REPS * len(CONDICOES)
count = 0

for rps in RPS_VALUES:
    for wu in WU_VALUES:
        for rep in range(1, NUM_REPS + 1):
            for condicao, normal_rps in CONDICOES.items():
                count += 1
                print(f"\n===== [{count}/{total}] desempate_rps1: {condicao} rps={rps} WU={wu} rep={rep} =====")

                cmd = [
                    "python3", "-m",
                    "simulator.main_orchestrator",
                    "--rps", str(rps),
                    "--attackers", str(ATTACKERS),
                    "--work-units", str(wu),
                    "--normal-clients", "4",
                    "--normal-rps", normal_rps,
                    "--duration", str(DURATION),
                ]

                subprocess.run(cmd)

                suffix = f"{condicao}_rps{rps}_att{ATTACKERS}_WU{wu}_rep{rep}"

                shutil.move("simulation_metrics.csv", os.path.join(RESULTS_DIR, f"metrics_{suffix}.csv"))

                if os.path.exists("attack_summary_log.csv"):
                    shutil.move("attack_summary_log.csv", os.path.join(RESULTS_DIR, f"attack_summary_log_{suffix}.csv"))

                if os.path.exists("rtt_log.csv"):
                    shutil.move("rtt_log.csv", os.path.join(RESULTS_DIR, f"rtt_log_{suffix}.csv"))

                if os.path.exists("traffic_capture.csv"):
                    shutil.move("traffic_capture.csv", os.path.join(RESULTS_DIR, f"traffic_capture_{suffix}.csv"))

                if condicao == "combinado" and os.path.exists("normal_traffic_summary_log.csv"):
                    shutil.move("normal_traffic_summary_log.csv",
                                os.path.join(RESULTS_DIR, f"normal_traffic_summary_log_{suffix}.csv"))
                elif os.path.exists("normal_traffic_summary_log.csv"):
                    os.remove("normal_traffic_summary_log.csv")

print("\ndesempate_rps1: todas as execuções concluídas.")
