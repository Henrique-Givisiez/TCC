import csv
import time
import threading
import os

_output_file = None

def configure_output(path):
    global _output_file
    _output_file = str(path)

def output_file():
    if _output_file is not None:
        return _output_file
    from simulator import config
    return config.NORMAL_TRAFFIC_SUMMARY_LOG_FILE

# Espelha attack_summary_logger.py, mas para os workers de tráfego NORMAL
# (normal_traffic.py) -- arquivo separado de config.ATTACK_SUMMARY_LOG_FILE
# de propósito, para não quebrar a convenção já documentada em CLAUDE.md de
# que attack_summary_log.csv só recebe linhas de workers de ATAQUE.

FIELDNAMES = [
    "num_clients",
    "rps_per_worker",
    "planned_total_rps",
    "num_targets",
    "total_requests",
    "elapsed_time_s",
    "real_rps",
    "errors",
]

_lock = threading.Lock()


def init_normal_traffic_summary_log():
    """
    Cria/reinicia o CSV no começo da simulação.
    """
    with _lock:
        with open(output_file(), "w", newline="") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=FIELDNAMES)
            writer.writeheader()


def log_traffic_start(target_urls, rps_per_worker, num_clients):
    """
    Registra o início do tráfego normal.
    """
    num_targets = len(target_urls)
    planned_total_rps = rps_per_worker * num_clients

    row = {
        "num_clients": num_clients,
        "rps_per_worker": rps_per_worker,
        "planned_total_rps": planned_total_rps,
        "num_targets": num_targets,
        "total_requests": "",
        "elapsed_time_s": "",
        "real_rps": "",
        "errors": "",
    }
    _append_row(row)


def log_worker_stop(request_count, error_count, worker_start_time, rps_per_worker):
    """
    Registra o resumo final de uma thread de tráfego normal.
    Deve ser chamado dentro do worker, quando ele termina.
    """
    worker_end_time = time.monotonic()
    elapsed_time_s = worker_end_time - worker_start_time

    real_rps = (
        request_count / elapsed_time_s
        if elapsed_time_s > 0
        else 0.0
    )

    row = {
        "num_clients": "",
        "rps_per_worker": rps_per_worker,
        "planned_total_rps": "",
        "num_targets": "",
        "total_requests": request_count,
        "elapsed_time_s": round(elapsed_time_s, 3),
        "real_rps": round(real_rps, 3),
        "errors": error_count,
    }
    _append_row(row)


def _append_row(row):
    """
    Escrita protegida por lock para evitar conflito entre várias threads.
    """
    with _lock:
        file_exists = os.path.exists(output_file())

        with open(output_file(), "a", newline="") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=FIELDNAMES)

            if not file_exists:
                writer.writeheader()

            writer.writerow(row)
