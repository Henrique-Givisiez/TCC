"""
Repetições extras (rep2-rep5) para os 4 cenários em progressão de potência
de 2 do grid atacantes x intensidade (S1/S6/S7/S8 = 40/80/160/320 rps
agregado normal) -- pedido do usuário depois de diagnosticarmos que o
"pico" de CPU usado nos gráficos 48/53 é ruidoso com só 1 repetição
(rajadas aleatórias de Poisson caindo ou não bem num tick de 5s -- ver
changes.txt, análise das células S1/2 atacantes/10-15%). Com 5 repetições
por célula (rep1, já existente, + rep2-rep5 daqui), dá pra tirar
média±desvio-padrão de verdade em vez de uma amostra única.

Mesmos parâmetros de run_atacantes_intensidade_grid.py (mesma
RESULTS_DIR, mesma convenção de nome -- o nome do arquivo já inclui o
número da repetição, então rep2-5 não colidem com os rep1 já coletados).
NÃO mexe em nenhum arquivo já existente.

288 execuções novas (4 cenários x 3 atacantes x 6 intensidades x 4
repetições), 180s cada -- ~14-15h de simulação + overhead de Docker.

Uso: python3 -m experiments.run_atacantes_intensidade_grid_pow2_reps
"""
import os
import shutil
import subprocess

NORMAL_SCENARIOS = {
    "S1": 40,
    "S6": 80,
    "S7": 160,
    "S8": 320,
}
NORMAL_NUM_CLIENTS = 4
NORMAL_WORK_UNITS = 10

ATTACKERS_VALUES = [1, 2, 4]
INTENSITIES_PCT = [1, 5, 10, 15, 20, 25]  # % do agregado normal do cenário -- nunca > 25%
WORK_UNITS = 200000
SIMULATION_DURATION = 180
REPS = [2, 3, 4, 5]  # rep1 já existe (grid original) -- não regerar

RESULTS_DIR = "experiment_results/atacantes_intensidade_grid"
os.makedirs(RESULTS_DIR, exist_ok=True)


def run_point(scenario_name, normal_aggregate_rps, pct, attackers, rep):
    attack_aggregate_rps = normal_aggregate_rps * pct / 100.0
    normal_rps_per_client = normal_aggregate_rps / NORMAL_NUM_CLIENTS
    attack_rps_per_attacker = attack_aggregate_rps / attackers

    print(f"\n===== {scenario_name} ({normal_aggregate_rps} req/s normal) + "
          f"{pct}% ataque (~{attack_aggregate_rps:.3f} req/s, {attackers} atacante(s), "
          f"{attack_rps_per_attacker:.4f} rps/atacante) @ WU={WORK_UNITS} rep={rep} =====",
          flush=True)

    cmd = [
        "python3", "-m", "simulator.main_orchestrator",
        "--normal-clients", "4",
        "--normal-rps", str(normal_rps_per_client),
        "--rps", str(attack_rps_per_attacker),
        "--attackers", str(attackers),
        "--work-units", str(WORK_UNITS),
        "--normal-work-units", str(NORMAL_WORK_UNITS),
        "--duration", str(SIMULATION_DURATION),
    ]
    subprocess.run(cmd)

    suffix = f"{scenario_name}_atk{pct}pct_att{attackers}_wu{WORK_UNITS}_rep{rep}"

    def move_if_exists(src, name_prefix):
        if os.path.exists(src):
            shutil.move(src, os.path.join(RESULTS_DIR, f"{name_prefix}_{suffix}.csv"))
        else:
            print(f"[WARNING] {src} não encontrado.")

    move_if_exists("simulation_metrics.csv", "metrics")
    move_if_exists("attack_summary_log.csv", "attack_summary_log")
    move_if_exists("normal_traffic_summary_log.csv", "normal_traffic_summary_log")
    move_if_exists("rtt_log.csv", "rtt_log")
    move_if_exists("traffic_capture.csv", "traffic_capture")


def main():
    total = len(NORMAL_SCENARIOS) * len(ATTACKERS_VALUES) * len(INTENSITIES_PCT) * len(REPS)
    i = 0
    for scenario_name, agg in NORMAL_SCENARIOS.items():
        for attackers in ATTACKERS_VALUES:
            for pct in INTENSITIES_PCT:
                for rep in REPS:
                    i += 1
                    print(f"\n[{i}/{total}]", flush=True)
                    run_point(scenario_name, agg, pct, attackers, rep)
    print(f"\natacantes_intensidade_grid_pow2_reps: todas as {total} execuções concluídas.", flush=True)


if __name__ == "__main__":
    main()
