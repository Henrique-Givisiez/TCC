import subprocess
import sys
import time

STEPS = [
    "experiments.run_desempate_rps1",
    "analysis.plot_desempate_combinado_isolado",
    "analysis.plot_comparacao_completa_v2",
]


def log(msg):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def main():
    for script in STEPS:
        log(f"===== Iniciando etapa: {script} =====")
        result = subprocess.run(["python3", "-m", script])
        if result.returncode != 0:
            log(f"!!!!! Etapa {script} falhou (código {result.returncode}) -- PARANDO. !!!!!")
            sys.exit(result.returncode)
        log(f"===== Etapa concluída: {script} =====")
    log("PIPELINE_COMPLETO -- desempate rps=1 + replots terminados com sucesso.")


if __name__ == "__main__":
    main()
