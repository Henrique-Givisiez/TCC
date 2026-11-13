#!/usr/bin/env python3
"""Figura 2 × 2 das quatro características temporais na partição TEST."""
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter, MaxNLocator
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
SOURCE = ROOT / 'reports/scientific_campaign_visualization_20261112'
CONSOLIDATION = ROOT / 'reports/consolidacao_fases_tcc/caracteristicas_por_execucao_fase.csv'
FEATURES = [
    ('ingress_packet_count', '(a) Pacotes TCP', 'Pacotes/janela de 1 s'),
    ('ingress_tcp_payload_length_sum_bytes', '(b) Payload TCP', 'Bytes/janela de 1 s'),
    ('request_starts', '(c) Requisições iniciadas', 'Requisições/janela de 1 s'),
    ('mean_duration_ms', '(d) Duração HTTP', 'Duração média por janela (ms)'),
]
SCENARIOS = ('L2', 'A3', 'F96')
STYLES = {
    'L2': ('L2 — Legítimo', '#28618b', '-'),
    'A3': ('A3 — Assimetria', '#bd4e33', '-.'),
    'F96': ('F96 — Flooding', '#6a4e9b', '--'),
}
PHASES = {'PRE': (30, 150), 'ACTIVE': (150, 270), 'POST': (270, 390)}


def load_and_validate():
    inv = pd.read_csv(SOURCE / 'inventario_execucoes.csv')
    inv = inv.loc[inv.partition.eq('TEST'), ['entry_id', 'scenario', 'block']].copy()
    assert len(inv) == 60 and inv.entry_id.is_unique
    assert inv.scenario.value_counts().to_dict() == {'L2': 20, 'A3': 20, 'F96': 20}
    assert inv.block.nunique() == 20
    assert inv.groupby(['block', 'scenario']).size().eq(1).all()

    s = pd.read_csv(SOURCE / 'processed/signals.csv')
    s = s[s.entry_id.isin(inv.entry_id) & s.feature.isin([x[0] for x in FEATURES])].copy()
    assert set(s.feature) == {x[0] for x in FEATURES}
    assert not s.duplicated(['entry_id', 'feature', 'window_index']).any()
    s = s.drop(columns=['scenario', 'block', 'partition']).merge(inv, on='entry_id', validate='many_to_one')
    s = s[s.window_index.between(30, 389)].copy()
    assert len(s) == 60 * 4 * 360
    assert s.groupby(['entry_id', 'feature']).window_index.nunique().eq(360).all()
    assert np.isfinite(s.value.to_numpy()).all()  # cobertura integral; sem preenchimento
    assert s.groupby(['scenario', 'feature', 'window_index']).size().eq(20).all()

    # A média da curva ao longo de cada fase deve reproduzir a média de fase
    # calculada por execução na consolidação preexistente.
    consolidated = pd.read_csv(CONSOLIDATION)
    consolidated = consolidated[consolidated.feature.isin([x[0] for x in FEATURES])]
    checks = 0
    for phase, (start, stop) in PHASES.items():
        assert stop - start == 120 and start in (30, 150, 270)
        actual = (s[s.window_index.between(start, stop - 1)]
                  .groupby(['entry_id', 'feature']).value.mean())
        expected = consolidated[consolidated.phase.eq(phase)].set_index(['entry_id', 'feature'])['mean']
        assert actual.index.equals(expected.index) or set(actual.index) == set(expected.index)
        expected = expected.reindex(actual.index)
        assert np.allclose(actual.to_numpy(), expected.to_numpy(), atol=1e-6, rtol=1e-7)
        checks += len(actual)
    print(f'Validação: 60 TEST, 20 por cenário, 20 blocos, 4 sinais, 360 janelas; '
          f'{checks} médias execução × fase conferidas; cobertura 100%.')
    return s


def main():
    s = load_and_validate()
    grouped = (s.groupby(['feature', 'scenario', 'window_index']).value
               .agg(mean='mean', sd=lambda x: x.std(ddof=1), n='count').reset_index())
    assert grouped.n.eq(20).all()
    assert np.isfinite(grouped[['mean', 'sd']].to_numpy()).all()

    plt.rcParams.update({
        'font.family': 'DejaVu Sans', 'font.size': 9.5,
        'axes.titlesize': 10.5, 'axes.labelsize': 9.5,
        'xtick.labelsize': 8.5, 'ytick.labelsize': 8.5,
        'legend.fontsize': 9, 'pdf.fonttype': 42,
        'savefig.facecolor': 'white',
    })
    fig, axes = plt.subplots(2, 2, figsize=(7.6, 6.65), sharex=True,
                             constrained_layout=True)
    fig.set_constrained_layout_pads(w_pad=.025, h_pad=.035, hspace=.07, wspace=.06)
    formatter = FuncFormatter(lambda x, _: f'{x:,.0f}'.replace(',', '.'))
    for ax, (feature, title, ylabel) in zip(axes.flat, FEATURES):
        ax.set_facecolor('white')
        ax.axvspan(150, 270, color='#c8af69', alpha=.075, zorder=0)
        for boundary in (150, 270):
            ax.axvline(boundary, color='#555555', lw=.85, ls=':', zorder=1)
        for scenario in SCENARIOS:
            g = grouped[(grouped.feature == feature) & (grouped.scenario == scenario)]
            label, color, style = STYLES[scenario]
            t = g.window_index.to_numpy()
            mean = g['mean'].to_numpy()
            sd = g.sd.to_numpy()
            ax.fill_between(t, np.maximum(0, mean-sd), mean+sd,
                            color=color, alpha=.105, linewidth=0, zorder=2)
            ax.plot(t, mean, color=color, ls=style, lw=1.45,
                    label=label, zorder=3)
        ax.set(title=title, ylabel=ylabel, xlim=(30, 390))
        ax.set_xticks([30, 90, 150, 210, 270, 330, 390])
        ax.yaxis.set_major_locator(MaxNLocator(nbins=5))
        ax.yaxis.set_major_formatter(formatter)
        ax.grid(alpha=.16, linewidth=.6)
        ax.set_axisbelow(True)
        ax.spines[['top', 'right']].set_visible(False)
    for ax in axes[1, :]:
        ax.set_xlabel('Tempo relativo à execução (s)')
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc='lower center', bbox_to_anchor=(.5, -.055),
               ncol=3, frameon=False, borderaxespad=.3)
    fig.savefig(OUT/'figura_caracteristicas_temporais.png', dpi=300, bbox_inches='tight')
    fig.savefig(OUT/'figura_caracteristicas_temporais.pdf', bbox_inches='tight')
    plt.close(fig)
    print('Figura PNG e PDF gerada a partir das médias e DP entre 20 execuções por segundo.')


if __name__ == '__main__':
    main()
