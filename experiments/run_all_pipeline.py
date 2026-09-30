import subprocess
import sys
import time
import glob

# Encadeador mestre: espera a etapa 1 (run_graph4_refined.py, já disparada
# em background separadamente) terminar sozinha, e então roda as etapas
# 2-6 em sequência, sem intervenção manual. Loga tudo num arquivo só
# (pipeline_full.log) e escreve a linha sentinela "PIPELINE_COMPLETO" no
# final, para ser fácil de checar/grep.

NB_DIR = "experiment_results/normal_baseline"
GRAPH4_REFINED_EXPECTED_FILES = 30  # 6 agregados x 5 reps

STEPS = [
    ("analysis.plot_graph4_refined", []),
    ("experiments.run_wu400000_only", []),
    ("analysis.plot_graph05_pow2", []),
    ("experiments.run_experiments_clients_rps", []),
    ("analysis.plot_clients_rps_invariance", []),
]


def log(msg):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)


def wait_for_graph4_refined_data(poll_seconds=60):
    log("Aguardando run_graph4_refined.py (etapa 1, disparada separadamente) terminar...")
    while True:
        n = len(glob.glob(f"{NB_DIR}/metrics_normal_agg*_WU10_refined_rep*.csv"))
        log(f"  progresso etapa 1: {n}/{GRAPH4_REFINED_EXPECTED_FILES} arquivos de métricas presentes")
        if n >= GRAPH4_REFINED_EXPECTED_FILES:
            log("Etapa 1 parece completa (30 arquivos encontrados). Aguardando 30s de margem "
                "para garantir que o último processo terminou de escrever/mover arquivos...")
            time.sleep(30)
            return
        time.sleep(poll_seconds)


def run_step(script, extra_args):
    cmd = ["python3", "-m", script] + extra_args
    log(f"===== Iniciando etapa: {' '.join(cmd)} =====")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        log(f"!!!!! Etapa {script} terminou com código {result.returncode} -- PARANDO o pipeline. !!!!!")
        sys.exit(result.returncode)
    log(f"===== Etapa concluída: {script} =====")


def main():
    wait_for_graph4_refined_data()

    for script, extra_args in STEPS:
        run_step(script, extra_args)

    log("PIPELINE_COMPLETO -- todas as etapas (1-6) terminaram com sucesso.")


if __name__ == "__main__":
    main()
