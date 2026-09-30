import csv
import time
import threading
import os

from simulator import config

FIELDNAMES = [
    "num_attackers",
    "rps_per_worker",
    "planned_total_rps",
    "num_targets",
    "total_requests",
    "elapsed_time_s",
    "real_rps",
    "errors"
]

_lock = threading.Lock()


def init_attack_summary_log():
    """
    Cria/reinicia o CSV no começo da simulação.
    """
    with _lock:
        with open(config.ATTACK_SUMMARY_LOG_FILE, "w", newline="") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=FIELDNAMES)
            writer.writeheader()


def log_attack_start(target_urls, rps_per_worker, num_attackers):
    """
    Registra o início de um flood HTTP.
    """
    num_targets = len(target_urls)
    planned_total_rps = rps_per_worker * num_attackers

    row = {
        "num_attackers": num_attackers,
        "rps_per_worker": rps_per_worker,
        "planned_total_rps": planned_total_rps,
        "num_targets": num_targets,
        "total_requests": "",
        "elapsed_time_s": "",
        "real_rps": "",
        "errors": ""
}
    _append_row(row)


def log_worker_stop(request_count, error_count, worker_start_time, rps_per_worker):
    """
    Registra o resumo final de uma thread atacante.
    Deve ser chamado dentro do worker, quando ele termina.
    """
    worker_end_time = time.monotonic()
    elapsed_time_s = worker_end_time - worker_start_time

    actual_rps = (
        request_count / elapsed_time_s
        if elapsed_time_s > 0
        else 0.0
    )

    current_thread = threading.current_thread()

    real_rps = (
    request_count / elapsed_time_s
    if elapsed_time_s > 0
    else 0.0
)

    row = {
        "num_attackers": "",
        "rps_per_worker": rps_per_worker,
        "planned_total_rps": "",
        "num_targets": "",
        "total_requests": request_count,
        "elapsed_time_s": round(elapsed_time_s, 3),
        "real_rps": round(real_rps, 3),
        "errors": error_count
}

    _append_row(row)


def _append_row(row):
    """
    Escrita protegida por lock para evitar conflito entre várias threads.
    """
    with _lock:
        file_exists = os.path.exists(config.ATTACK_SUMMARY_LOG_FILE)

        with open(config.ATTACK_SUMMARY_LOG_FILE, "a", newline="") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=FIELDNAMES)

            if not file_exists:
                writer.writeheader()

            writer.writerow(row)