"""
Fase 2 do plano W-EDoS — consolida métricas de EntCusumZV3.py (entropia de
Shannon + Z-score + CUSUM) para os candidatos identificados na Fase 1 como
"melhor W-EDoS".

Pressupõe que run_burst_analysis.py (já existente, não alterado) já rodou
sobre a árvore experiment_results/ inteira e gerou os .xlsx correspondentes
a cada rtt_log_*.csv -- este script só LÊ esses .xlsx de volta e agrega,
evitando recomputar a mesma análise duas vezes.

Uso:
  python3 -m analysis.run_burst_analysis    # (uma vez, gera/atualiza todos os xlsx)
  python3 -m analysis.wedos_ent_cusum_report <glob_de_rtt_logs> [--out out.csv]

Exemplo:
  python3 -m analysis.wedos_ent_cusum_report "experiment_results/wedos_grid/rtt_log_*best*.csv"
"""
import argparse
import glob
import os

import pandas as pd


def summarize_one(rtt_log_path):
    d = os.path.dirname(rtt_log_path)
    base = os.path.splitext(os.path.basename(rtt_log_path))[0]
    output_prefix = base[len("rtt_log_"):] if base.startswith("rtt_log_") else base
    xlsx_path = os.path.join(d, f"rtt_bursts_{output_prefix}.xlsx")

    if not os.path.exists(xlsx_path):
        return dict(file=rtt_log_path,
                    error=f"{xlsx_path} não encontrado -- rode run_burst_analysis.py primeiro")

    df = pd.read_excel(xlsx_path)

    # Baseline/piso não estão no xlsx (só nos janelas) -- recalcula aqui
    # rapidamente a partir do próprio rtt_log, replicando exatamente a mesma
    # fórmula de EntCusumZV3.py (baseline = amostras antes do ataque, ver
    # config.ATTACK_START_TIME_SECONDS), só para exibir na tabela.
    from simulator import config
    raw = pd.read_csv(rtt_log_path).sort_values("timestamp").reset_index(drop=True)
    raw["tempo_rel"] = raw["timestamp"] - raw["timestamp"].min()
    baseline = raw.loc[raw["tempo_rel"] < config.ATTACK_START_TIME_SECONDS, "rtt"]
    if len(baseline) >= 10:
        baseline_mean, baseline_std, baseline_n = baseline.mean(), baseline.std(), len(baseline)
    else:
        baseline_mean, baseline_std, baseline_n = raw["rtt"].mean(), raw["rtt"].std(), len(raw)
    burst_floor = baseline_mean * 1.8
    total_windows = len(df)
    bursts = df[df["Status Burst"] == "DDoS Burst"]
    n_bursts = len(bursts)

    return dict(
        file=rtt_log_path,
        baseline_mean_ms=float(baseline_mean) if baseline_mean else None,
        baseline_std_ms=float(baseline_std) if baseline_std else None,
        baseline_n_samples=int(baseline_n) if baseline_n else None,
        burst_floor_ms=float(burst_floor) if burst_floor else None,
        total_windows=total_windows,
        bursts_detected=n_bursts,
        detection_rate=round(n_bursts / total_windows, 3) if total_windows else None,
        avg_entropy=round(df["Entropia"].astype(float).mean(), 3) if total_windows else None,
        avg_max_z=round(df["Max Z"].astype(float).mean(), 3) if total_windows else None,
        max_max_z=round(df["Max Z"].astype(float).max(), 3) if total_windows else None,
        avg_cusum=round(df["CUSUM"].astype(float).mean(), 1) if total_windows else None,
        max_cusum=round(df["CUSUM"].astype(float).max(), 1) if total_windows else None,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("pattern", help="glob de rtt_log_*.csv a processar")
    parser.add_argument("--out", default="experiment_results/wedos_ent_cusum_summary.csv")
    args = parser.parse_args()

    files = sorted(glob.glob(args.pattern))
    print(f"Processando {len(files)} arquivo(s) de rtt_log...\n")

    rows = [summarize_one(f) for f in files]
    df_out = pd.DataFrame(rows)
    df_out.to_csv(args.out, index=False)
    print(f"\n{df_out.to_string(index=False)}\n")
    print(f"Resumo salvo em {args.out}")
