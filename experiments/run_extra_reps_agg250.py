import subprocess
import os
import shutil

# Repetições extras pro ponto de 250 agregado do gráfico 04 refinado, que
# teve 1 repetição (rep1) suspeita: só 3/4 threads de tráfego normal
# logaram o fim, e a taxa de erro combinada ficou em ~14% contra ~0% nas
# outras 4 repetições -- mesma classe de soluço transitório já vista na
# seção 40 (8 clientes). Objetivo: confirmar se é soluço isolado (não se
# repete) ou algo sistemático nesse ponto específico do grid.
#
# NÃO EXECUTAR junto com outro lote de experimentos Docker rodando ao
# mesmo tempo -- rodar depois que qualquer outro lote em andamento
# terminar, para não confundir contenção de recurso simultânea com o
# fenômeno que estamos tentando isolar (fila combinada com o usuário).
#
# Reps numerados 6-8 (não sobrescreve rep1-5, dados originais preservados).

AGGREGATE = 250
NUM_CLIENTS = 4
EXTRA_REPS = range(6, 9)  # 6,7,8 -- 3 repetições extras
WORK_UNITS = 10
DURATION = 180

RESULTS_DIR = "experiment_results/normal_baseline"
os.makedirs(RESULTS_DIR, exist_ok=True)

rps_per_client = AGGREGATE / NUM_CLIENTS

for rep in EXTRA_REPS:
    print(f"\n===== extra_reps_agg250: agregado={AGGREGATE} (rps/cliente={rps_per_client}), rep {rep} =====")

    cmd = [
        "python3", "-m",
        "simulator.main_orchestrator",
        "--normal-clients", "4",
        "--normal-rps", str(rps_per_client),
        "--normal-work-units", str(WORK_UNITS),
        "--attack-duration", "0",
        "--duration", str(DURATION),
    ]

    subprocess.run(cmd)

    suffix = f"agg{AGGREGATE}_WU{WORK_UNITS}_refined_rep{rep}"

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

print("\nextra_reps_agg250: todas as execuções concluídas.")
