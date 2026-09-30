"""
Fase 1 do plano de ML (ver changes.txt): varre todos os runs já coletados em
experiment_results/ e extrai features por janela deslizante (20s, passo 10s,
mesmos parâmetros do EntCusumZV3.py) para treinar os classificadores.

Entropia/Z-score/CUSUM são RECALCULADOS aqui (não lidos dos .xlsx que o
EntCusumZV3.py já gerou) por dois motivos: (1) o .xlsx só guarda o tempo
médio das amostras da janela, formatado como texto "MM:SS.s" arredondado --
não dá pra reconstruir os limites exatos [t_start, t_end) da janela com
confiança, e esses limites são necessários pra alinhar o rótulo com a coluna
'label' real de cada run; (2) os valores no .xlsx são strings arredondadas a
1-2 casas decimais. A lógica de cálculo é a mesma do EntCusumZV3.py, exceto
que o baseline pré-ataque usa o início REAL do ataque daquele run específico
(lido da coluna 'label' de simulation_metrics.csv), não a constante fixa
config.ATTACK_START_TIME_SECONDS -- os sweep scripts podem sobrescrever o
início do ataque via --attack-start, e config.py não reflete isso quando
lido depois, offline, num processo separado.

Colunas de saída, três grupos:
  - FEATURES (entram no treino do ML): rtt_mean/std/median/p90/p95/p99/cv/
    skew/min/max, request_count, unique_src_ports, entropy, delta_entropy,
    max_z, cusum.
  - METADADO (não entram como feature; usados em análises auxiliares, ex.:
    cruzar erro do ML com colapso do autoscaler -- ver changes.txt §92-93):
    avg_cpu_percent, num_instances, any_scale_up.
  - RÓTULO E CONTROLE: label (attack/benign), is_transition, is_hiccup,
    config_key (chave de agrupamento pro split da Fase 4), scenario, wu,
    intensity_pct, num_attackers, rep, run_id.
  - SAÍDA DO DETECTOR CLÁSSICO (não é feature -- só pra comparação na Fase
    6): clf_alarm_entropy, clf_alarm_z, clf_alarm_cusum, clf_status_burst.
"""
import argparse
import glob
import os
import re
import sys

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

from simulator import config

WINDOW_SECONDS = 20
STRIDE_SECONDS = 10  # overlap 50%, igual ao default do EntCusumZV3.py
MIN_SAMPLES_PER_WINDOW = 10  # mesma justificativa do EntCusumZV3.py
Z_THRESHOLD = 3.5
BASELINE_RATIO = 1.8
DELTA_ENTROPY_THRESHOLD = 1.5
TRANSITION_MARGIN_SECONDS = WINDOW_SECONDS
LABEL_OVERLAP_THRESHOLD = 0.5
TRUNCATED_RUN_FRACTION = 0.8  # run truncado = terminou com <80% da duração configurada

BASE_DIRS = [
    "experiment_results/desempate_combinado_isolado",
    "experiment_results/wedos_grid",
    "experiment_results/combined_sweep",
    "experiment_results/clients_rps_grid",
    "experiment_results/normal_baseline",
    "experiment_results/atacantes_intensidade_grid",
]

OUTPUT_PATH = "results/ml_dataset/features_raw.csv"

# Pacotes cliente->servidor: dst_port cai na faixa de portas publicadas das
# instâncias (STARTING_HOST_PORT..+MAX_INSTANCES-1). Contar src_port único
# nesse subconjunto é a assinatura de churn de porta (perda de keep-alive)
# descoberta em sessão anterior -- ver CLAUDE.md.
SERVER_PORTS = set(range(config.STARTING_HOST_PORT, config.STARTING_HOST_PORT + config.MAX_INSTANCES))


def discover_runs(base_dirs):
    runs = []
    for d in base_dirs:
        for metrics_path in sorted(glob.glob(os.path.join(d, "metrics_*.csv"))):
            suffix = os.path.basename(metrics_path)[len("metrics_"):-len(".csv")]
            run = {
                "dir": d,
                "suffix": suffix,
                "run_id": f"{os.path.basename(d)}/{suffix}",
                "metrics_path": metrics_path,
                "rtt_path": os.path.join(d, f"rtt_log_{suffix}.csv"),
                "traffic_path": os.path.join(d, f"traffic_capture_{suffix}.csv"),
                "attack_summary_path": os.path.join(d, f"attack_summary_log_{suffix}.csv"),
                "normal_summary_path": os.path.join(d, f"normal_traffic_summary_log_{suffix}.csv"),
            }
            if not os.path.exists(run["attack_summary_path"]):
                run["attack_summary_path"] = None
            if not os.path.exists(run["normal_summary_path"]):
                run["normal_summary_path"] = None
            runs.append(run)
    return runs


def parse_scenario_metadata(dir_name, suffix):
    base = os.path.basename(dir_name)

    def grab(pattern, cast=str):
        m = re.search(pattern, suffix)
        return cast(m.group(1)) if m else None

    meta = {
        "source_dir": base,
        "scenario": grab(r"(S\d+)"),
        "wu": grab(r"[Ww][Uu](\d+)", int),
        "intensity_pct": grab(r"atk([\d.]+)pct", float),
        "num_attackers": grab(r"(?:^|_)att(\d+)(?:_|$)", int),
        "rep": grab(r"rep(\d+)$", int),
        "aggregate_rps": grab(r"agg(\d+)", int),
        "num_clients": grab(r"clients(\d+)", int),
        "combinado_rps": grab(r"(?:^|_)rps(\d+)", int),
        "stage": grab(r"(stage1[ab])"),
        "kind": grab(r"^(combinado|isolado)"),
    }
    # config_key = tudo do sufixo menos o número da repetição -- usado pro
    # split por configuração na Fase 4 (garante que repetições do mesmo
    # cenário não caiam divididas entre treino e teste).
    config_key = re.sub(r"_rep\d+$", "", suffix)
    meta["config_key"] = f"{base}/{config_key}"
    return meta


def detect_hiccup_reasons(run, metrics_df):
    reasons = []
    for path, expected_col in (
        (run["attack_summary_path"], "num_attackers"),
        (run["normal_summary_path"], "num_clients"),
    ):
        if path is None:
            continue
        try:
            raw = pd.read_csv(path)
        except Exception as exc:
            reasons.append(f"falha ao ler {os.path.basename(path)}: {exc}")
            continue
        if raw.empty or expected_col not in raw.columns:
            continue
        expected = raw[expected_col].dropna()
        if expected.empty:
            continue
        expected_n = expected.iloc[0]
        completed = raw["total_requests"].notna().sum() if "total_requests" in raw.columns else 0
        if completed < expected_n:
            reasons.append(
                f"{os.path.basename(path)}: esperado={expected_n:g} completos={completed}"
            )

    if not metrics_df.empty:
        t_max = metrics_df["elapsed_time_s"].max()
        if t_max < TRUNCATED_RUN_FRACTION * config.SIMULATION_DURATION_SECONDS:
            reasons.append(
                f"run truncado: durou {t_max:.1f}s de "
                f"{config.SIMULATION_DURATION_SECONDS}s esperados"
            )
    return reasons


def compute_attack_window(metrics_df):
    attack_rows = metrics_df.loc[metrics_df["label"] == "attack", "elapsed_time_s"]
    if attack_rows.empty:
        return None, None
    return attack_rows.min(), attack_rows.max()


def build_windows(t_max):
    windows = []
    t_start = 0.0
    while t_start < t_max:
        windows.append((t_start, t_start + WINDOW_SECONDS))
        t_start += STRIDE_SECONDS
    return windows


def overlap_seconds(a_start, a_end, b_start, b_end):
    return max(0.0, min(a_end, b_end) - max(a_start, b_start))


def compute_rtt_baseline(rtt_df, attack_start_rel):
    if attack_start_rel is not None:
        baseline = rtt_df.loc[rtt_df["tempo_rel"] < attack_start_rel, "rtt"]
    else:
        baseline = pd.Series(dtype=float)
    if len(baseline) >= 10:
        return baseline.mean(), baseline.std()
    return rtt_df["rtt"].mean(), rtt_df["rtt"].std()


def compute_cusum_series(rtt_df, baseline_mean, kappa):
    cusum = np.empty(len(rtt_df))
    c = 0.0
    for idx, val in enumerate(rtt_df["rtt"].values):
        c = max(0.0, c + (val - baseline_mean) - kappa)
        cusum[idx] = c
    return cusum


def extract_run_rows(run):
    metrics_df = pd.read_csv(run["metrics_path"])
    if metrics_df.empty or "label" not in metrics_df.columns:
        return [], "metrics_vazio_ou_sem_label"

    if not os.path.exists(run["rtt_path"]):
        return [], "rtt_log_ausente"
    rtt_df = pd.read_csv(run["rtt_path"])
    if rtt_df.empty:
        return [], "rtt_log_vazio"
    rtt_df = rtt_df.sort_values("timestamp").reset_index(drop=True)
    rtt_df["tempo_rel"] = rtt_df["timestamp"] - rtt_df["timestamp"].min()

    traffic_df = None
    if os.path.exists(run["traffic_path"]):
        traffic_df = pd.read_csv(run["traffic_path"])

    hiccup_reasons = detect_hiccup_reasons(run, metrics_df)
    is_hiccup = len(hiccup_reasons) > 0

    attack_start_rel, attack_end_rel = compute_attack_window(metrics_df)

    baseline_mean, baseline_std = compute_rtt_baseline(rtt_df, attack_start_rel)
    kappa = 0.5 * baseline_std
    h = 5 * baseline_std
    cusum_series = compute_cusum_series(rtt_df, baseline_mean, kappa)
    rtt_df["_cusum"] = cusum_series
    val_min, val_max = rtt_df["rtt"].min(), rtt_df["rtt"].max()

    t_max = metrics_df["elapsed_time_s"].max()
    windows = build_windows(min(t_max, rtt_df["tempo_rel"].max()))

    meta = parse_scenario_metadata(run["dir"], run["suffix"])

    rows = []
    entropia_anterior = None
    stats_anterior = None
    for t_start, t_end in windows:
        janela = rtt_df.loc[(rtt_df["tempo_rel"] >= t_start) & (rtt_df["tempo_rel"] < t_end)]
        if len(janela) < MIN_SAMPLES_PER_WINDOW:
            continue

        rtt_vals = janela["rtt"]
        hist, _ = np.histogram(rtt_vals, bins=10, range=(val_min, val_max), density=True)
        probs = hist / np.sum(hist) if np.sum(hist) > 0 else np.zeros(10)
        entropy = scipy_stats.entropy(probs[probs > 0], base=2) if np.any(probs > 0) else 0.0
        delta_entropy = abs(entropy - entropia_anterior) if entropia_anterior is not None else 0.0
        alarm_entropy = delta_entropy > DELTA_ENTROPY_THRESHOLD
        entropia_anterior = entropy

        max_z = 0.0
        alarm_z = False
        if stats_anterior and stats_anterior["std"] > 0:
            zs = np.abs((rtt_vals - stats_anterior["media"]) / stats_anterior["std"])
            max_z = zs.max()
            alarm_z = max_z > Z_THRESHOLD
        stats_anterior = {"media": rtt_vals.mean(), "std": rtt_vals.std()}

        cusum_atual = janela["_cusum"].iloc[-1]
        alarm_cusum = cusum_atual > h
        clf_status_burst = rtt_vals.mean() > (baseline_mean * BASELINE_RATIO) and (alarm_z or alarm_cusum)

        unique_ports = 0
        if traffic_df is not None and not traffic_df.empty:
            tw = traffic_df.loc[
                (traffic_df["timestamp"] >= t_start)
                & (traffic_df["timestamp"] < t_end)
                & (traffic_df["dst_port"].isin(SERVER_PORTS))
            ]
            unique_ports = tw["src_port"].nunique()

        mrows = metrics_df.loc[
            (metrics_df["elapsed_time_s"] >= t_start) & (metrics_df["elapsed_time_s"] < t_end)
        ]
        avg_cpu = mrows["average_cpu_percent"].mean() if not mrows.empty else np.nan
        num_instances = mrows["num_instances"].iloc[-1] if not mrows.empty else np.nan
        any_scale_up = bool((mrows["decision"] == "SCALE_UP").any()) if not mrows.empty else False

        is_transition = False
        if attack_start_rel is not None:
            if overlap_seconds(t_start, t_end, attack_start_rel - TRANSITION_MARGIN_SECONDS,
                                attack_start_rel + TRANSITION_MARGIN_SECONDS) > 0:
                is_transition = True
            if overlap_seconds(t_start, t_end, attack_end_rel - TRANSITION_MARGIN_SECONDS,
                                attack_end_rel + TRANSITION_MARGIN_SECONDS) > 0:
                is_transition = True

        if attack_start_rel is not None:
            atk_overlap = overlap_seconds(t_start, t_end, attack_start_rel, attack_end_rel)
            label = "attack" if (atk_overlap / WINDOW_SECONDS) >= LABEL_OVERLAP_THRESHOLD else "benign"
        else:
            label = "benign"

        rows.append({
            "run_id": run["run_id"],
            **meta,
            "window_start_s": t_start,
            "window_end_s": t_end,
            "rtt_mean": rtt_vals.mean(),
            "rtt_std": rtt_vals.std(),
            "rtt_median": rtt_vals.median(),
            "rtt_p90": rtt_vals.quantile(0.90),
            "rtt_p95": rtt_vals.quantile(0.95),
            "rtt_p99": rtt_vals.quantile(0.99),
            "rtt_cv": (rtt_vals.std() / rtt_vals.mean()) if rtt_vals.mean() else np.nan,
            "rtt_skew": scipy_stats.skew(rtt_vals),
            "rtt_min": rtt_vals.min(),
            "rtt_max": rtt_vals.max(),
            "request_count": len(janela),
            "unique_src_ports": unique_ports,
            "entropy": entropy,
            "delta_entropy": delta_entropy,
            "max_z": max_z,
            "cusum": cusum_atual,
            "avg_cpu_percent": avg_cpu,
            "num_instances": num_instances,
            "any_scale_up": any_scale_up,
            "label": label,
            "is_transition": is_transition,
            "is_hiccup": is_hiccup,
            "hiccup_reasons": "; ".join(hiccup_reasons),
            "clf_alarm_entropy": alarm_entropy,
            "clf_alarm_z": alarm_z,
            "clf_alarm_cusum": alarm_cusum,
            "clf_status_burst": clf_status_burst,
        })

    return rows, None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None,
                         help="Processa só os N primeiros runs (teste rápido)")
    parser.add_argument("--dirs", nargs="*", default=BASE_DIRS,
                         help="Subconjunto de diretórios de experiment_results/ a processar")
    parser.add_argument("--output", default=OUTPUT_PATH)
    args = parser.parse_args()

    runs = discover_runs(args.dirs)
    if args.limit:
        runs = runs[: args.limit]
    print(f"[INFO] {len(runs)} runs encontrados em {len(args.dirs)} diretórios.")

    all_rows = []
    skipped = []
    hiccup_runs = 0
    for i, run in enumerate(runs, 1):
        try:
            rows, skip_reason = extract_run_rows(run)
        except Exception as exc:
            skipped.append((run["run_id"], f"erro: {exc}"))
            continue
        if skip_reason:
            skipped.append((run["run_id"], skip_reason))
            continue
        if rows and rows[0]["is_hiccup"]:
            hiccup_runs += 1
        all_rows.extend(rows)
        if i % 100 == 0:
            print(f"[INFO] {i}/{len(runs)} runs processados...")

    if not all_rows:
        print("[ERRO] Nenhuma janela extraída -- abortando sem escrever saída.")
        sys.exit(1)

    df = pd.DataFrame(all_rows)
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    df.to_csv(args.output, index=False)

    n_attack = (df["label"] == "attack").sum()
    n_benign = (df["label"] == "benign").sum()
    n_transition = df["is_transition"].sum()
    n_hiccup_rows = df["is_hiccup"].sum()

    print(f"\n[OK] {len(df)} janelas escritas em {args.output}")
    print(f"  runs processados: {len(runs) - len(skipped)}/{len(runs)} "
          f"({len(skipped)} pulados, {hiccup_runs} com soluço detectado)")
    print(f"  janelas: {n_attack} attack / {n_benign} benign "
          f"({n_transition} em transição, {n_hiccup_rows} de runs com soluço)")
    if skipped:
        print(f"\n[AVISO] {len(skipped)} runs pulados:")
        for run_id, reason in skipped[:30]:
            print(f"  - {run_id}: {reason}")
        if len(skipped) > 30:
            print(f"  ... e mais {len(skipped) - 30}")


if __name__ == "__main__":
    main()
