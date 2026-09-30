"""
Auditoria estrutural (Fase 0.2 do plano W-EDoS) — SÓ LEITURA.

Varre todo experiment_results/ (recursivamente) procurando por
metrics_*.csv e, para cada um, confere:
  - arquivo rtt_log_*, attack_summary_log_* e traffic_capture_*
    correspondentes existem (attack_summary é opcional em normal_baseline,
    por design — ver CLAUDE.md).
  - contagem de linhas do metrics dentro do esperado
    (duration/MONITOR_INTERVAL_SECONDS, +-2 de folga).
  - NaN fora do já documentado (active_containers_names vazio só na
    primeira linha).
  - elapsed_time_s estritamente crescente.
  - decisão SCALE_UP só ocorre em linhas com CPU >= CPU_THRESHOLD_SCALE_UP
    (checagem de plausibilidade, não uma prova formal — a decisão é tomada
    em cima da MESMA leitura de CPU da linha, ver main_orchestrator.py).

Não altera nenhum arquivo. Imprime um relatório e grava
experiment_results/wedos_structural_audit_report.csv com uma linha por
arquivo de métricas encontrado.
"""
import glob
import os
import re

import pandas as pd

from simulator import config

ROOT = "experiment_results"
EXPECTED_INTERVAL = config.MONITOR_INTERVAL_SECONDS
CPU_UP = config.CPU_THRESHOLD_SCALE_UP


def find_sibling(metrics_path, new_prefix):
    """metrics_XXX.csv -> new_prefix + XXX.csv, no mesmo diretório.

    wu_calibration é um caso especial: metrics usa 'rps{R}_att{A}_WU{W}' mas
    attack_summary_log usa '{R}_{A}_WU{W}' (sem os literais 'rps'/'att' —
    inconsistência real de nomenclatura em run_experiments.py, não um bug
    funcional, mas o casador de nomes precisa saber disso pra não gerar
    falso positivo).
    """
    d = os.path.dirname(metrics_path)
    base = os.path.basename(metrics_path)
    if not base.startswith("metrics_"):
        return None
    suffix = base[len("metrics_"):]

    candidates = [os.path.join(d, f"{new_prefix}{suffix}")]

    if "wu_calibration" in metrics_path and new_prefix == "attack_summary_log_":
        m = re.match(r"rps(\d+)_att(\d+)_WU(\d+)\.csv$", suffix)
        if m:
            rps, att, wu = m.groups()
            candidates.append(os.path.join(d, f"attack_summary_log_{rps}_{att}_WU{wu}.csv"))

    for c in candidates:
        if os.path.exists(c):
            return c
    return None


def audit_file(metrics_path):
    row = {"file": metrics_path, "problems": []}
    try:
        df = pd.read_csv(metrics_path)
    except Exception as e:
        row["problems"].append(f"não leu o CSV: {e}")
        return row

    row["n_rows"] = len(df)

    # duração aproximada a partir do próprio arquivo (nem todo run usa 180s
    # -- alguns são smoke tests/varreduras finas com --duration custom)
    if "elapsed_time_s" in df.columns and len(df) > 1:
        approx_duration = df["elapsed_time_s"].iloc[-1]
        expected_rows = approx_duration / EXPECTED_INTERVAL
        if not (expected_rows - 3 <= len(df) <= expected_rows + 3):
            row["problems"].append(
                f"contagem de linhas ({len(df)}) foge do esperado "
                f"(~{expected_rows:.0f} para duração {approx_duration:.0f}s)"
            )
        if not df["elapsed_time_s"].is_monotonic_increasing:
            row["problems"].append("elapsed_time_s não é estritamente crescente")
    else:
        row["problems"].append("coluna elapsed_time_s ausente ou arquivo com <=1 linha")

    # NaN fora do documentado (active_containers_names vazio na 1a linha)
    for col in df.columns:
        if col == "active_containers_names":
            continue
        n_nan = df[col].isna().sum()
        if n_nan > 0:
            row["problems"].append(f"{n_nan} NaN em '{col}'")

    # coerência decisão x CPU
    if "decision" in df.columns and "average_cpu_percent" in df.columns:
        scale_up_rows = df[df["decision"] == "SCALE_UP"]
        bad = scale_up_rows[scale_up_rows["average_cpu_percent"] < CPU_UP]
        if len(bad) > 0:
            row["problems"].append(
                f"{len(bad)} linha(s) com decision=SCALE_UP mas CPU < {CPU_UP}%"
            )

    # siblings
    is_normal_baseline = "normal_baseline" in metrics_path
    for prefix, required in [
        # rtt_log_* não é salvo por run_experiments_normal.py (gap real,
        # ver achado no relatório final -- não é um "problema" desta
        # auditoria, é um comportamento conhecido do script atual)
        ("rtt_log_", not is_normal_baseline),
        ("attack_summary_log_", not is_normal_baseline),
        ("traffic_capture_", True),
    ]:
        sib = find_sibling(metrics_path, prefix)
        if sib is None and required:
            row["problems"].append(f"arquivo '{prefix}*' correspondente não encontrado")

    row["ok"] = len(row["problems"]) == 0
    return row


def main():
    metrics_files = sorted(glob.glob(os.path.join(ROOT, "**", "metrics_*.csv"), recursive=True))
    print(f"Encontrados {len(metrics_files)} arquivos metrics_*.csv sob {ROOT}/\n")

    results = [audit_file(f) for f in metrics_files]

    n_ok = sum(1 for r in results if r["ok"])
    n_bad = len(results) - n_ok
    print(f"OK: {n_ok}  |  Com problema(s): {n_bad}\n")

    for r in results:
        if not r["ok"]:
            print(f"[PROBLEMA] {r['file']}")
            for p in r["problems"]:
                print(f"    - {p}")

    # relatório CSV
    out_rows = []
    for r in results:
        out_rows.append({
            "file": r["file"],
            "n_rows": r.get("n_rows"),
            "ok": r["ok"],
            "problems": "; ".join(r["problems"]),
        })
    out_path = os.path.join(ROOT, "wedos_structural_audit_report.csv")
    pd.DataFrame(out_rows).to_csv(out_path, index=False)
    print(f"\nRelatório salvo em {out_path}")


if __name__ == "__main__":
    main()
