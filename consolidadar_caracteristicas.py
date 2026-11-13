#!/usr/bin/env python3
"""Consolida cinco sinais TEST por fase e contrastes pareados por bloco.
Executar na raiz do repositório TCC; não altera fontes científicas.
"""
from pathlib import Path
import argparse
import numpy as np
import pandas as pd

FEATURES = [
    'ingress_packet_count', 'ingress_tcp_payload_length_sum_bytes',
    'request_starts', 'mean_duration_ms', 'mean_cpu_percent',
]
PHASES = {'PRE': (30, 150), 'ACTIVE': (150, 270), 'POST': (270, 390)}
SCENARIOS = ['L2', 'A3', 'F96']


def summarize(values):
    x = np.asarray(values, dtype=float)
    x = x[np.isfinite(x)]
    return dict(
        n=len(x),
        mean=float(x.mean()) if len(x) else np.nan,
        sd=float(x.std(ddof=1)) if len(x) > 1 else np.nan,
        median=float(np.median(x)) if len(x) else np.nan,
        p95=float(np.percentile(x, 95)) if len(x) else np.nan,
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', type=Path, default=Path('.'))
    ap.add_argument(
        '--output',
        type=Path,
        default=Path('reports/consolidacao_fases_tcc'),
    )
    args = ap.parse_args()

    root = args.root.resolve()
    src = root / 'reports/scientific_campaign_visualization_20261112'

    inv = pd.read_csv(src / 'inventario_execucoes.csv')
    inv = inv[inv.partition == 'TEST'][
        ['entry_id', 'scenario', 'block']
    ]

    assert len(inv) == 60
    assert set(inv.scenario) == set(SCENARIOS)
    assert inv.groupby('block').scenario.nunique().eq(3).all()
    assert inv.block.nunique() == 20

    sig = pd.read_csv(src / 'processed/signals.csv')

    assert {
        'entry_id', 'feature', 'window_index', 'value'
    } <= set(sig.columns)

    # signals.csv já contém scenario e block.
    # Verificar consistência com o inventário oficial antes do merge.
    check_cols = [
        c for c in ('scenario', 'block') if c in sig.columns
    ]

    if check_cols:
        check = sig[['entry_id'] + check_cols].merge(
            inv,
            on='entry_id',
            how='inner',
            validate='many_to_one',
            suffixes=('_signal', '_inventory'),
        )

        for col in check_cols:
            left = check[f'{col}_signal']
            right = check[f'{col}_inventory']

            if col == 'block':
                valid = left.isna() | (
                    pd.to_numeric(left, errors='coerce')
                    == pd.to_numeric(right, errors='coerce')
                )
            else:
                valid = left.isna() | (left == right)

            if not valid.all():
                raise ValueError(
                    f'Inconsistência em {col} entre signals.csv '
                    'e inventário TEST'
                )

    # Remover as colunas duplicadas antes do merge.
    sig = sig.drop(columns=check_cols).merge(
        inv,
        on='entry_id',
        how='inner',
        validate='many_to_one',
    )

    assert set(sig.feature) == set(FEATURES), set(sig.feature)

    sig = sig[sig.window_index.between(30, 389)].copy()

    sig['phase'] = pd.cut(
        sig.window_index,
        bins=[30, 150, 270, 390],
        labels=list(PHASES),
        right=False,
    )

    assert sig.phase.notna().all()

    if sig.duplicated(
        ['entry_id', 'feature', 'window_index']
    ).any():
        raise ValueError('Janelas duplicadas em TEST')

    # Cada execução é uma unidade experimental.
    runs = []

    for (eid, sc, block, feature, phase), g in sig.groupby(
        ['entry_id', 'scenario', 'block', 'feature', 'phase'],
        observed=True,
    ):
        assert len(g) == 120, (
            eid, feature, phase, len(g)
        )

        z = summarize(g.value)

        runs.append(dict(
            entry_id=eid,
            scenario=sc,
            block=int(block),
            feature=feature,
            phase=str(phase),
            n_windows=120,
            n_valid=z['n'],
            n_missing=120 - z['n'],
            mean=z['mean'],
            sd_within_run=z['sd'],
            median=z['median'],
            p95=z['p95'],
        ))

    run = pd.DataFrame(runs)

    assert len(run) == 60 * 5 * 3, len(run)

    # Estatísticas entre execuções.
    overview = []

    for (sc, feature, phase), g in run.groupby(
        ['scenario', 'feature', 'phase']
    ):
        z = summarize(g['mean'])

        overview.append(dict(
            scenario=sc,
            feature=feature,
            phase=phase,
            runs=len(g),
            runs_with_mean=z['n'],
            mean_of_run_means=z['mean'],
            sd_between_runs=z['sd'],
            median_run_mean=z['median'],
            p95_run_mean=z['p95'],
            valid_windows=int(g.n_valid.sum()),
            missing_windows=int(g.n_missing.sum()),
            mean_within_run_sd=float(
                g.sd_within_run.mean()
            ),
            mean_of_run_p95=float(g.p95.mean()),
        ))

    summary = pd.DataFrame(overview)

    # Mudanças dentro da mesma execução.
    wide = run.pivot(
        index=['block', 'scenario', 'entry_id', 'feature'],
        columns='phase',
        values='mean',
    ).reset_index()

    wide['active_minus_pre'] = wide['ACTIVE'] - wide['PRE']
    wide['post_minus_pre'] = wide['POST'] - wide['PRE']

    phases = []

    for (scenario, feature), g in wide.groupby(
        ['scenario', 'feature']
    ):
        for name in [
            'active_minus_pre',
            'post_minus_pre',
        ]:
            z = summarize(g[name])

            phases.append(dict(
                scenario=scenario,
                feature=feature,
                contrast=name,
                **z,
            ))

    phase_delta = pd.DataFrame(phases)

    # Contrastes respeitando os blocos pareados.
    contrasts = []

    for feature, g in wide.groupby('feature'):
        for metric in [
            'active_minus_pre',
            'post_minus_pre',
        ]:
            pivot = g.pivot(
                index='block',
                columns='scenario',
                values=metric,
            )

            assert len(pivot) == 20

            for sc in ['A3', 'F96']:
                d = pivot[sc] - pivot['L2']
                z = summarize(d)

                contrasts.append(dict(
                    feature=feature,
                    contrast=f'{sc}_minus_L2_on_{metric}',
                    **z,
                ))

            d = pivot['A3'] - pivot['F96']
            z = summarize(d)

            contrasts.append(dict(
                feature=feature,
                contrast=f'A3_minus_F96_on_{metric}',
                **z,
            ))

    paired = pd.DataFrame(contrasts)

    # Exportação sem alterar os dados originais.
    out = (
        (root / args.output).resolve()
        if not args.output.is_absolute()
        else args.output
    )

    out.mkdir(parents=True, exist_ok=True)

    outputs = [
        ('caracteristicas_por_execucao_fase', run),
        ('resumo_caracteristicas_por_cenario_fase', summary),
        ('mudancas_intracenario', phase_delta),
        ('contrastes_pareados_de_mudancas', paired),
    ]

    for name, df in outputs:
        df.to_csv(
            out / (name + '.csv'),
            index=False,
            float_format='%.9g',
        )

    print('Concluído:', out)
    print('Execuções:', run.entry_id.nunique())
    print(
        'Linhas execução × característica × fase:',
        len(run),
    )
    print('Resumo:', len(summary))
    print('Mudanças:', len(phase_delta))
    print('Contrastes:', len(paired))
    print(
        'Importante: contrastes são descritivos; '
        'nenhum IC ou teste de hipótese foi calculado.'
    )


if __name__ == '__main__':
    main()