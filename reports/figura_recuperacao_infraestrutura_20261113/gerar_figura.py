#!/usr/bin/env python3
"""Adaptação visual da B1-A, somente a partir de CSVs processados."""
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter, MaxNLocator
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
B1 = ROOT / 'reports/investigacao_recuperacao_pos_ataque_20261113/processed'
INV = ROOT / 'reports/scientific_campaign_visualization_20261112/inventario_execucoes.csv'
STYLES = {
    'L2': ('L2 — Legítimo', '#28618b', '-'),
    'A3': ('A3 — Assimetria', '#bd4e33', '-.'),
    'F96': ('F96 — Flooding', '#6a4e9b', '--'),
}


def load_and_validate():
    inv = pd.read_csv(INV)
    inv = inv.loc[inv.partition.eq('TEST'), ['entry_id', 'scenario', 'block']]
    assert len(inv) == 60 and inv.entry_id.is_unique
    assert inv.scenario.value_counts().to_dict() == {'L2': 20, 'A3': 20, 'F96': 20}
    assert inv.block.nunique() == 20
    assert inv.groupby(['block', 'scenario']).size().eq(1).all()

    raw = pd.read_csv(B1 / 'tracos_5s_por_execucao.csv')
    assert set(raw.entry_id) == set(inv.entry_id)
    assert not raw.duplicated(['entry_id', 't']).any()
    assert raw.groupby('entry_id').t.nunique().eq(50).all()
    z = raw.loc[raw.t.ge(242.5) & raw.t.le(387.5)].copy()
    expected_t = np.arange(242.5, 390, 5)
    assert len(expected_t) == 30 and len(z) == 1800
    assert set(z.t) == set(expected_t)
    assert z.groupby(['entry_id', 't']).size().eq(1).all()
    assert z.groupby(['scenario', 't']).size().eq(20).all()
    assert np.isfinite(z[['waiting_mean', 'workers_two_fraction']].to_numpy()).all()
    assert z.waiting_mean.ge(0).all()
    assert z.workers_two_fraction.between(0, 1).all()
    check = z[['entry_id', 'scenario', 'block']].drop_duplicates().merge(
        inv, on='entry_id', validate='one_to_one', suffixes=('_trace', '_inventory'))
    assert (check.scenario_trace == check.scenario_inventory).all()
    assert (check.block_trace == check.block_inventory).all()

    # The six five-second values in each POST subinterval must reproduce the
    # already published per-run 30-second means from B1.
    post = pd.read_csv(B1 / 'post_por_execucao.csv')
    checks = 0
    for j in range(4):
        start = 270 + 30*j
        actual = z.loc[z.t.ge(start+2.5) & z.t.lt(start+30), :]
        assert actual.groupby('entry_id').size().eq(6).all()
        actual = actual.groupby('entry_id')[['waiting_mean', 'workers_two_fraction']].mean()
        expected = post.loc[post.interval.eq(f'POST-{j+1}')].set_index('entry_id')
        assert set(actual.index) == set(expected.index)
        for metric in actual.columns:
            assert np.allclose(actual[metric], expected.reindex(actual.index)[metric],
                               atol=1e-7, rtol=1e-7), (j, metric)
            checks += len(actual)
    print(f'Validação: 60 TEST; 20 por cenário; 20 blocos; 30 intervalos de 5 s por execução; '
          f'{checks} médias conferidas com B1; cobertura 100%.')
    return z


def main():
    z = load_and_validate()
    grouped = (z.groupby(['scenario', 't'])[['waiting_mean', 'workers_two_fraction']]
               .agg(['mean', 'std', 'count']))
    assert grouped.xs('count', axis=1, level=1).eq(20).all().all()
    assert np.isfinite(grouped.to_numpy()).all()

    plt.rcParams.update({
        'font.family': 'DejaVu Sans', 'font.size': 9.5,
        'axes.titlesize': 10.5, 'axes.labelsize': 9.5,
        'xtick.labelsize': 8.5, 'ytick.labelsize': 8.5,
        'legend.fontsize': 9, 'pdf.fonttype': 42,
        'savefig.facecolor': 'white',
    })
    fig, axes = plt.subplots(2, 1, figsize=(7.6, 5.55), sharex=True,
                             constrained_layout=True)
    fig.set_constrained_layout_pads(w_pad=.025, h_pad=.035, hspace=.07)
    formatter = FuncFormatter(lambda x, _: f'{x:,.0f}'.replace(',', '.'))
    for ax, metric, scale, title, ylabel in [
        (axes[0], 'waiting_mean', 1, '(a) Operações aguardando',
         'Operações aguardando (média)'),
        (axes[1], 'workers_two_fraction', 100, '(b) Ocupação dos workers',
         'Tempo com dois workers ocupados (%)'),
    ]:
        ax.set_facecolor('white')
        ax.axvspan(240, 270, color='#c8af69', alpha=.075, zorder=0)
        ax.axvline(270, color='#555555', lw=.85, ls=':', zorder=1)
        # L2 is drawn last so its near-zero queue trace remains visible.
        for scenario in ('A3', 'F96', 'L2'):
            g = grouped.loc[scenario]
            mean = g[(metric, 'mean')].to_numpy() * scale
            sd = g[(metric, 'std')].to_numpy() * scale
            lower = np.maximum(0, mean - sd)
            upper = np.minimum(100, mean + sd) if scale == 100 else mean + sd
            label, color, style = STYLES[scenario]
            ax.fill_between(g.index.to_numpy(), lower, upper, color=color,
                            alpha=.105, linewidth=0, zorder=2)
            ax.plot(g.index.to_numpy(), mean, color=color, ls=style,
                    lw=1.55, label=label, zorder=4 if scenario == 'L2' else 3)
        ax.set(title=title, ylabel=ylabel, xlim=(240, 390))
        ax.set_xticks([240, 270, 300, 330, 360, 390])
        ax.yaxis.set_major_locator(MaxNLocator(nbins=5))
        ax.yaxis.set_major_formatter(formatter)
        ax.grid(alpha=.16, linewidth=.6)
        ax.set_axisbelow(True)
        ax.spines[['top', 'right']].set_visible(False)
    axes[0].annotate('Fim do ataque', xy=(270, 1), xycoords=('data', 'axes fraction'),
                     xytext=(5, -5), textcoords='offset points', va='top',
                     color='#555555', fontsize=8.5)
    axes[0].set_ylim(bottom=0)
    axes[1].set_ylim(0, 100)
    axes[1].set_xlabel('Tempo relativo à execução (s)')
    handles, labels = axes[0].get_legend_handles_labels()
    by_label = dict(zip(labels, handles))
    labels = [STYLES[sc][0] for sc in ('L2', 'A3', 'F96')]
    fig.legend([by_label[x] for x in labels], labels, loc='lower center',
               bbox_to_anchor=(.5, -.075), ncol=3, frameon=False,
               borderaxespad=.3)
    fig.savefig(OUT/'figura_recuperacao_infraestrutura.png', dpi=300,
                bbox_inches='tight')
    fig.savefig(OUT/'figura_recuperacao_infraestrutura.pdf',
                bbox_inches='tight')
    plt.close(fig)
    print('PNG e PDF gerados: média ± 1 DP amostral entre 20 execuções; sem suavização.')


if __name__ == '__main__':
    main()
