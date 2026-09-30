import subprocess
import itertools
import os
import shutil

# Varredura combinada (Tabela 5, Sotelo Monge et al.): para cada cenário de
# tráfego normal, sobrepõe tráfego de ataque como uma porcentagem do volume
# total de requisições normais daquele cenário.
#
# Os valores de RPS agregado (40/100/200/300) NÃO são os da Tabela 4 do
# artigo (50/60/70/80) — o testbed do artigo é maior/mais complexo, então
# aqueles números não significam a mesma coisa aqui. Recalibrados a partir
# do baseline real deste simulador (run_experiments_normal.py, WU=10, mesmo
# custo usado para tráfego normal abaixo): 40/100/200 já estavam medidos
# (0 SCALE_UP em qualquer um), e 300 foi medido especificamente para este
# ajuste (pico de CPU 53.6%, ainda abaixo do limiar de 60%, mas bem mais
# perto dele que os pontos anteriores — ver changes.txt). 400 já era
# instável (escalona sozinho) e por isso foi descartado como cenário
# "normal". O objetivo é manter o espírito da Tabela 4 (progressão de carga
# leve até perto do limiar, sem NUNCA escalar sozinho) usando pontos
# realmente medidos neste simulador, em vez de números emprestados de um
# testbed com uma curva de capacidade diferente.
NORMAL_SCENARIOS = {
    "S1": 40,
    "S2": 100,
    "S3": 200,
    "S4": 300,
}
ATTACK_INTENSITIES_PCT = [1, 5, 10]

# WU=300000/500000: os dois valores que, na varredura de calibração
# (run_experiments.py), realmente forçam SCALE_UP mantendo o volume de
# requisições (RPS) baixo/stealth — ou seja, os únicos que constituem um
# ataque W-EDoS bem-sucedido pela definição do artigo (custo forçado sem
# aparência de DDoS volumétrico). WU=100000 (usado antes aqui) fica de fora:
# não força scale-up, então não representa o ataque "bem-sucedido" a
# caracterizar neste experimento combinado.
ATTACK_WORK_UNITS_LIST = [300000, 500000]

NORMAL_NUM_CLIENTS = 4      # fixo, mesma contagem usada nas outras varreduras
ATTACK_NUM_ATTACKERS = 4    # fixo
NORMAL_WORK_UNITS = 10
SIMULATION_DURATION = 180

RESULTS_DIR = "experiment_results/combined_sweep"
os.makedirs(RESULTS_DIR, exist_ok=True)

for scenario_name, normal_aggregate_rps in NORMAL_SCENARIOS.items():
    for pct in ATTACK_INTENSITIES_PCT:
        for work_units in ATTACK_WORK_UNITS_LIST:
            # % do volume TOTAL de requisições normais do cenário, convertido para
            # RPS agregado de ataque (a duração se cancela: pct * total_normal_requests / duration == pct * normal_rate).
            attack_aggregate_rps = normal_aggregate_rps * pct / 100.0

            normal_rps_per_client = normal_aggregate_rps / NORMAL_NUM_CLIENTS
            attack_rps_per_attacker = attack_aggregate_rps / ATTACK_NUM_ATTACKERS

            print(f"\n===== {scenario_name} ({normal_aggregate_rps} req/s normal) + {pct}% ataque (~{attack_aggregate_rps:.2f} req/s) @ WU={work_units} =====")

            cmd = [
                # Sem "sudo" -- ver run_experiments_normal.py para a
                # explicação (setcap no tcpdump + Docker sem root; sudo
                # aqui travaria subprocess.run esperando senha interativa).
                "python3", "-m",
                "simulator.main_orchestrator",
                "--normal-clients", "4",
                "--normal-rps", str(normal_rps_per_client),
                "--rps", str(attack_rps_per_attacker),
                "--attackers", str(ATTACK_NUM_ATTACKERS),
                "--work-units", str(work_units),
                "--normal-work-units", str(NORMAL_WORK_UNITS),
                "--duration", str(SIMULATION_DURATION),
            ]

            subprocess.run(cmd)

            # =========================
            # Metrics log
            # =========================
            metrics_filename = f"metrics_{scenario_name}_atk{pct}pct_wu{work_units}.csv"
            shutil.move(
                "simulation_metrics.csv",
                os.path.join(RESULTS_DIR, metrics_filename)
            )

            # =========================
            # Attack summary log
            # =========================
            attack_summary_src = "attack_summary_log.csv"
            attack_summary_filename = f"attack_summary_log_{scenario_name}_atk{pct}pct_wu{work_units}.csv"
            attack_summary_dst = os.path.join(RESULTS_DIR, attack_summary_filename)

            if os.path.exists(attack_summary_src):
                shutil.move(attack_summary_src, attack_summary_dst)
            else:
                print(f"[WARNING] {attack_summary_src} não encontrado.")

            # =========================
            # RTT log
            # =========================
            rtt_log_src = "rtt_log.csv"
            rtt_log_filename = f"rtt_log_{scenario_name}_atk{pct}pct_wu{work_units}.csv"
            rtt_log_dst = os.path.join(RESULTS_DIR, rtt_log_filename)

            if os.path.exists(rtt_log_src):
                shutil.move(rtt_log_src, rtt_log_dst)
            else:
                print(f"[WARNING] {rtt_log_src} não encontrado.")

            # =========================
            # Traffic capture (tcpdump)
            # =========================
            traffic_capture_src = "traffic_capture.csv"
            traffic_capture_filename = f"traffic_capture_{scenario_name}_atk{pct}pct_wu{work_units}.csv"
            traffic_capture_dst = os.path.join(RESULTS_DIR, traffic_capture_filename)

            if os.path.exists(traffic_capture_src):
                shutil.move(traffic_capture_src, traffic_capture_dst)
            else:
                print(f"[WARNING] {traffic_capture_src} não encontrado.")

print("\nAll combined experiments completed.")
