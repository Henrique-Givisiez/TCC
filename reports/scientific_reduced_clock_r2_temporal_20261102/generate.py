#!/usr/bin/env python3
"""Apresentação offline de registros congelados: nenhum runtime científico importado."""
import argparse
import csv
from decimal import Decimal
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import shlex
import sys

os.environ.setdefault('MPLCONFIGDIR', '/tmp/clock-r2-matplotlib')
os.environ.setdefault('XDG_CACHE_HOME', '/tmp/clock-r2-cache')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
import numpy as np

FEATURES = ['request_starts', 'mean_duration_ms']
ALL_FEATURES = FEATURES + ['mean_cpu_percent', 'ingress_packet_count', 'ingress_tcp_payload_length_sum_bytes']
SCENARIOS = ['C16', 'M16', 'E16']
ALL_BLOCKS = list(range(1, 13))
PLOTS = ['temporal', 'heatmap', 'delay']
METHODS = ['cov', 'zscore', 'ewma', 'cusum-freeze']
LABELS = dict(zip(ALL_FEATURES, ['Inícios HTTP', 'Duração HTTP', 'CPU da vítima', 'Pacotes ingress', 'Payload TCP ingress']))
UNITS = dict(zip(ALL_FEATURES, ['Tentativas\npor janela de 1 s', 'Média por conclusão (ms)',
    'CPU Docker (%)\nmédia dos ticks', 'Registros de pacotes\npor janela de 1 s', 'Payload TCP (bytes)\npor janela de 1 s']))
FEATURE_NOTES = {
    'request_starts': 'Tentativas iniciadas na janela de 1 s; ambas as classes.',
    'mean_duration_ms': 'Duração inteira atribuída pela conclusão; inclui falhas com duração registrada.',
    'mean_cpu_percent': 'Vítima inteira: média de ticks registrados derivados de coleta/cache; não é CPU instantânea.',
    'ingress_packet_count': 'Registros source→proxy; inclui payload zero e retransmissões observadas.',
    'ingress_tcp_payload_length_sum_bytes': 'Soma do payload TCP ingress; não são bytes físicos nem bytes HTTP únicos.'}
TICKS = [30, 90, 150, 210, 270, 330, 390]
SEMANTIC_CODE = ['analysis/detection/scientific/data.py',
    'analysis/detection/scientific/engine.py', 'analysis/detection/scientific/evaluation.py',
    'analysis/detection/scientific/statistics.py', 'analysis/detection/cusum_freeze_run.py',
    'analysis/detection/detectors/cov.py', 'analysis/detection/detectors/zscore.py',
    'analysis/detection/detectors/ewma.py', 'analysis/detection/detectors/cusum_freeze.py',
    'experiments/extract_features.py', 'experiments/feature_schema.py']


def require(condition, message):
    if not condition:
        raise ValueError(message)


def num(value):
    return float(value) if value is not None and value != '' else np.nan


def num_equal(a, b):
    return a is None and b is None or a is not None and b is not None and Decimal(a) == Decimal(b)


def block_tag(blocks):
    if len(blocks) > 1 and blocks == list(range(blocks[0], blocks[-1]+1)):
        return f'B{blocks[0]:02}-B{blocks[-1]:02}'
    return '_'.join(f'B{b:02}' for b in blocks)


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, epilog=
        'Use all sozinho em qualquer seletor para selecionar todos os valores. '
        'Sem seletores: pacote anterior (12 figuras, incluindo D). '
        '--blocks aplica-se apenas a temporal/heatmap; delay sempre usa B01–B12.')
    for name in ('repo', 'plan', 'checkpoint', 'output'):
        ap.add_argument('--' + name, type=Path, required=True)
    ap.add_argument('--checkpoint-sha256', required=True)
    ap.add_argument('--overwrite', action='store_true', help='Permite substituir saídas desta apresentação')
    for name, choices in [('features', ALL_FEATURES), ('scenarios', SCENARIOS),
                          ('blocks', [str(b) for b in ALL_BLOCKS]), ('plots', PLOTS)]:
        ap.add_argument('--' + name, nargs='+', choices=choices+['all'],
                        help='Múltiplos valores separados por espaço; all seleciona todos')
    args = ap.parse_args(argv)
    legacy = all(getattr(args, name) is None for name in ('features', 'scenarios', 'blocks', 'plots'))
    for name, universe, default in [('features', ALL_FEATURES, FEATURES),
            ('scenarios', SCENARIOS, ['M16', 'E16']), ('plots', PLOTS, PLOTS),
            ('blocks', [str(b) for b in ALL_BLOCKS], None)]:
        values = getattr(args, name)
        if values is not None:
            if len(values) != len(set(values)):
                ap.error(f'--{name}: valores repetidos não são permitidos')
            if 'all' in values and len(values) != 1:
                ap.error(f'--{name}: use all sozinho')
            values = list(universe) if values == ['all'] else [v for v in universe if v in values]
        else:
            values = default
        setattr(args, name, values)
    args.blocks = [int(b) for b in args.blocks] if args.blocks is not None else None
    args.legacy = legacy
    args.temporal_blocks = args.blocks if args.blocks is not None else [1]
    args.heatmap_blocks = args.blocks if args.blocks is not None else ALL_BLOCKS
    if 'delay' in args.plots and args.blocks is not None and args.blocks != ALL_BLOCKS:
        print('Aviso: --blocks aplica-se somente a temporal/heatmap; delay usa o resumo congelado '
              'com suporte completo B01–B12, sem estimativa do subconjunto.', file=sys.stderr)
    return args


class Inputs:
    def __init__(self, repo):
        self.repo, self.sources = repo, {}

    def locate(self, path):
        p = Path(path)
        if not p.is_absolute():
            return self.repo / p
        for anchor in ('experiment_results', 'experiments', 'docs', 'analysis', 'reports'):
            if anchor in p.parts:
                return self.repo.joinpath(*p.parts[p.parts.index(anchor):])
        return p

    def track(self, path, expected=None):
        p = self.locate(path).resolve()
        digest = hashlib.sha256(p.read_bytes()).hexdigest()
        require(expected is None or digest == expected, f'SHA256 divergente: {p}')
        self.sources[str(p)] = digest
        return p

    def read(self, path, expected=None):
        return json.loads(self.track(path, expected).read_text())

    def artifact(self, ref):
        return self.read(self.locate(ref['path']) / 'manifest.json', ref['manifest_sha256'])

    def csv(self, path, expected=None):
        with self.track(path, expected).open(newline='') as stream:
            return list(csv.DictReader(stream))

    def linked(self, root, records, relative):
        matches = [r for r in records if r['path'] == relative]
        require(len(matches) == 1, f'Vínculo não único: {relative}')
        ref = matches[0]
        p = self.track(self.locate(root) / relative, ref['sha256'])
        require(p.stat().st_size == ref['bytes'], f'Tamanho divergente: {p}')
        return p


def table(out, name, rows):
    if not rows:
        return
    fields = list(dict.fromkeys(k for r in rows for k in r))
    with (out / 'tables' / (name + '.csv')).open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows({k: None if isinstance(v, (float, np.floating)) and not np.isfinite(v) else v
                          for k, v in r.items()} for r in rows)


def main():
    args = parse_args()
    repo = args.repo.resolve()
    io = Inputs(repo)
    out = io.locate(args.output).resolve()
    require(not any((out / folder).is_symlink() for folder in ('figures', 'tables')),
            'Subdiretórios de saída não podem ser links simbólicos')
    protected = [repo / x for x in ('experiment_results', 'experiments', 'analysis', 'docs',
                 'reports/scientific_reduced_clock_r2_figures_20261031',
                 'reports/scientific_reduced_clock_r2_20261030')]
    require(out != repo and all(out != p and p not in out.parents and out not in p.parents
                                for p in protected), 'Saída sobrepõe fontes protegidas')
    require(len(args.checkpoint_sha256) == 64 and all(c in '0123456789abcdef' for c in args.checkpoint_sha256),
            'Informe SHA256 hexadecimal esperado do checkpoint TEST')
    # Authenticate the TEST root before any output mutation.
    cp = io.read(args.checkpoint, args.checkpoint_sha256)
    require(cp['partition'] == 'TEST', 'Checkpoint deve ser TEST')
    plan = io.read(args.plan, cp['authority']['plan_sha256'])
    if out.exists() and not args.overwrite:
        require(not any(out.iterdir()), 'Saídas existentes; use outro diretório ou --overwrite')
    io.read(plan['protocol']['path'], plan['protocol']['sha256'])
    summary = io.artifact(cp['artifacts']['summary'])
    require(summary['authority'] == cp['authority'] and not summary['missing_runs'], 'Summary incompatível')
    entries = {e['id']: e for e in plan['entries'] if e['partition'] == 'TEST'}
    blocks = sorted({e['block'] for e in entries.values()})
    require(blocks == ALL_BLOCKS, 'Inventário TEST B01–B12 indisponível')
    needed = set()
    for feature in args.features:
        for scenario in args.scenarios:
            for plot, selected_blocks in [('temporal', args.temporal_blocks), ('heatmap', args.heatmap_blocks)]:
                for b in selected_blocks if plot in args.plots else []:
                    needed.add((feature, scenario, b))
    if args.legacy:
        needed.update(('request_starts', s, 1) for s in SCENARIOS)
    needed_ids = {e['id'] for e in entries.values()
                  if any(s == e['scenario'] and b == e['block'] for _, s, b in needed)}
    receipts = {}
    for ref in cp['receipts']:
        if not needed_ids.intersection(Path(ref['path']).parts):
            continue
        doc = io.artifact(ref)
        require(doc['entry'] == entries[doc['entry']['id']], 'Identidade do recibo diverge')
        receipts[doc['entry']['id']] = doc['receipt']
    require(set(receipts) == needed_ids, 'Recibos selecionados incompletos')
    selected = next(b for b in blocks if {e['scenario'] for e in entries.values() if e['block'] == b}
                    == {'C16', 'M16', 'E16'})
    require(selected == 1 and blocks == list(range(1, 13)), 'Seleção B01/B01–B12 indisponível')
    # Reuse the established palette and method labels without calling its main/runtime.
    previous = io.track('reports/scientific_reduced_clock_r2_figures_20261031/generate.py')
    spec = importlib.util.spec_from_file_location('clock_r2_presentation', previous)
    old = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(old)
    names = dict(zip(old.METHODS, old.NAMES))
    names['zscore'] = 'Z-score'
    colors = dict(zip(old.METHODS, old.COLORS))
    for path in SEMANTIC_CODE:
        io.track(path, plan['runtime_hashes'][path])

    data, boundaries, audit, temporal = {}, {}, [], []
    for ref in summary['evaluations']:
        # Manifest reference paths are used only to avoid opening unrelated features.
        # Membership is then checked from the authenticated manifest, never inferred.
        parts = Path(ref['path']).parts
        matches = [(f, entries[eid]['scenario'], entries[eid]['block'])
                   for eid in needed_ids.intersection(parts) for f in args.features if f in parts]
        if not any(key in needed for key in matches):
            continue
        ev = io.artifact(ref)
        feature, entry = ev['feature'][1], ev['entry']
        require(entry == entries[entry['id']] and (feature, entry['scenario'], entry['block']) in needed,
                'Avaliação fora do escopo')
        run = io.artifact(ev['run'])
        source, receipt = run['source'], receipts[entry['id']]
        require(run['authority'] == ev['authority'] == cp['authority'], 'Autoridade divergente')
        require(source['entry_id'] == entry['id'] and source['run_id'] == receipt['run_id']
                and [source['family'], source['feature']] == ev['feature'] and source['partition'] == 'TEST',
                'Fonte divergente')
        fm = io.read(source['feature_manifest'], source['feature_manifest_sha256'])
        dm = io.read(source['dataset_manifest'], source['dataset_manifest_sha256'])
        require(source['feature_manifest_sha256'] == receipt['feature_manifest_sha256'] and
                source['dataset_manifest_sha256'] == receipt['dataset_manifest_sha256'] == fm['dataset_manifest_sha256'],
                'Recibo/features/dataset divergentes')
        require(fm['source_run_id'] == dm['run_id'] == source['run_id'] and
                fm['window']['size_seconds'] == '1', 'Relógio/identidade divergente')
        observable = io.track(source['observable_path'], source['observable_sha256'])
        observable_link = io.linked(io.locate(source['feature_manifest']).parent, fm['outputs'],
                                    str(observable.relative_to(io.locate(source['feature_manifest']).parent)))
        require(observable == observable_link, 'Observável não vinculado')
        obs = io.csv(observable)
        schema = io.read(io.linked(io.locate(source['feature_manifest']).parent,
                                  fm['outputs'], 'feature_schema.json'))
        definition = next(f for f in schema['tables'][source['family']]['fields'] if f['name'] == feature)
        if source['family'] == 'network' and not fm['network_direction']['supported']:
            # Same persisted support rule as load_source; no replacement by zeros.
            obs = [r | {feature: ''} for r in obs]
        cal = io.artifact(run['calibration'])
        require(cal['authority'] == run['authority'] and cal['feature'] == ev['feature'] and
                cal['baseline'] == run['baseline'], 'Calibração/baseline divergente')
        for path in SEMANTIC_CODE:
            require(run['code'][path] == plan['runtime_hashes'][path], 'Semântica congelada divergente')
        event_path = io.linked(io.locate(source['dataset_manifest']).parent, dm['files'], 'raw/attacks/attack_events.csv')
        require(event_path == io.track(ev['truth']['path'], ev['truth']['sha256']), 'Fronteiras não vinculadas')
        events = io.csv(event_path)
        require(len(events) == int(entry['scenario'] != 'C16'), 'Quantidade de eventos divergente')
        event = events[0] if events else None
        require(not event or event['run_id'] == receipt['run_id'], 'Evento de outra execução')
        stop = receipt['operational']['scalars']['stop_command_seconds']
        key = (feature, entry['scenario'], entry['block'])
        require(key not in data, 'Avaliação duplicada')
        window_obs = {int(r['window_index']): r for r in obs if 30 <= num(r['window_start_seconds']) < 390}
        require(set(window_obs) == set(range(30, 390)), 'Lacuna na grade de observação')
        for i, o in window_obs.items():
            require(o['run_id'] == receipt['run_id'] and num(o['window_start_seconds']) == i and
                    num(o['window_end_seconds']) == i+1, 'Grade de observação divergente')
        traces = {}
        for method in METHODS:
            h = cal['thresholds'][method]
            if method == 'cusum-freeze':
                require(run['components'][method]['config']['h'] == h, 'h da transição divergente')
            rows = [r for r in run['methods'][method] if 30 <= num(r['window_start_seconds']) < 390]
            require([r['window_index'] for r in rows] == list(range(30, 390)), 'Grade de escores divergente')
            for r in rows:
                i = r['window_index']
                require(num(r['window_start_seconds']) == i and num(r['window_end_seconds']) == i+1
                        and num(r['available_at_seconds']) == i+1, 'Observação/disponibilidade divergente')
                require((r['score'] is None) == (r['decision'] is None), 'Disponibilidade score/decisão diverge')
                if method == 'cusum-freeze':
                    require(r['candidate'] == r['score'] and
                            num_equal(r['observation'], window_obs[i][feature] or None),
                            'Candidato/observação divergente')
                    if r['decision'] is True:
                        require(r['update_accepted'] is False and r['posterior_state'] == r['previous_state'],
                                'Estado rejeitado não foi preservado')
                temporal.append(dict(entry=entry['id'], feature=feature, scenario=entry['scenario'],
                    block=entry['block'], method=method, observation=window_obs[i][feature], threshold=h) | r)
            # No score comparison, trajectory replay, or decision recomputation.
            require(sum(r['decision'] is None for r in rows) == ev['results'][method]['unavailable'],
                    'Indisponibilidade não corresponde à avaliação')
            first = ev['results'][method]['first_detection_available_at_seconds']
            require(first is None or any(r['decision'] is True and r['available_at_seconds'] == first for r in rows),
                    'Primeira disponibilidade publicada sem decisão persistida')
            traces[method] = rows
            audit.append(dict(entry=entry['id'], feature=feature, method=method, windows=len(rows),
                missing=sum(r['decision'] is None for r in rows), positive=sum(r['decision'] is True for r in rows),
                threshold=h, candidate_observation_binding_checked=method == 'cusum-freeze',
                first_detection_available_at_seconds=first))
        data[key] = dict(entry=entry, obs=window_obs, traces=traces, thresholds=cal['thresholds'],
                         event=event, stop=stop, receipt=receipt, dm=dm, definition=definition)
        boundaries[entry['id']] = dict(entry=entry['id'], block=entry['block'], scenario=entry['scenario'],
            actual_start_seconds=event['actual_start_seconds'] if event else None,
            actual_end_seconds=event['actual_end_seconds'] if event else None, stop_command_seconds=stop)
    require(set(data) == needed, 'Séries selecionadas ausentes ou duplicadas')

    # Explicit overwrite replaces only previously registered presentation outputs.
    # Never let old selections remain in the new output manifest.
    if args.overwrite and (out / 'provenance.json').exists():
        prior = json.loads((out / 'provenance.json').read_text())
        for relative in prior.get('outputs', {}):
            path = (out / relative).resolve()
            require(path.parent in [(out / 'figures').resolve(), (out / 'tables').resolve()],
                    'Proveniência anterior contém saída fora de figures/tables')
        for relative in prior.get('outputs', {}):
            (out / relative).unlink(missing_ok=True)
    out.mkdir(parents=True, exist_ok=True)
    (out / 'figures').mkdir(exist_ok=True)
    (out / 'tables').mkdir(exist_ok=True)
    table(out, 'temporal_records', temporal)
    table(out, 'directed_checks', audit)
    table(out, 'event_boundaries', list(boundaries.values()))
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10,
        'axes.spines.top': False, 'axes.spines.right': False, 'pdf.fonttype': 42,
        'ps.fonttype': 42, 'path.simplify': False, 'axes.titleweight': 'bold'})
    figure_index = []

    def save(fig, name, purpose, caption):
        for ext in ('pdf', 'png'):
            fig.savefig(out / 'figures' / (name + '.' + ext), dpi=300, facecolor='white')
        plt.close(fig)
        figure_index.append((name, purpose, caption))

    def limits(ax, d):
        ax.set_xlim(30, 390)
        ax.set_xticks(TICKS)
        ax.grid(axis='y', alpha=.18)
        if d['event']:
            s, e = (num(d['event'][k]) for k in ('actual_start_seconds', 'actual_end_seconds'))
            ax.axvspan(s, e, color='#E69F00', alpha=.08)
            ax.axvline(s, color='#222222', ls='--', lw=.9)
            ax.axvline(e, color='#222222', lw=.9)
        if d['stop'] is not None:
            ax.axvline(num(d['stop']), color='#CC79A7', ls=':', lw=1.5)

    def timeline(feature, scenario, block, zoom=False):
        d = data[feature, scenario, block]
        fig, axs = plt.subplots(5, 1, figsize=(8.27, 11.69), sharex=True)
        o = list(d['obs'].values())
        axs[0].stairs([num(r[feature]) for r in o], np.arange(30, 391), color='#444444', lw=.8)
        axs[0].set_ylabel(UNITS[feature])
        axs[0].set_title('Observação oficial em [i, i+1) · todas as classes', loc='left', fontsize=10)
        clipped = []
        for ax, method in zip(axs[1:], METHODS):
            rows = d['traces'][method]
            x = [num(r['available_at_seconds']) for r in rows]
            y = [num(r['score']) for r in rows]
            score_line, = ax.plot(x, y, color=colors[method], lw=.75)
            require(np.array_equal(score_line.get_ydata(), np.asarray(y), equal_nan=True) and
                    np.array_equal(score_line.get_xdata(), np.asarray(x)), 'Linha score/tempo divergente')
            positives = [r for r in rows if r['decision'] is True]
            ax.scatter([num(r['available_at_seconds']) for r in positives],
                       [num(r['score']) for r in positives], color=colors[method], s=8, zorder=4)
            h = num(d['thresholds'][method])
            threshold_line = ax.axhline(h, color='#222222', ls='--', lw=1, label=f'Limiar h = {h:.4g}')
            require(list(threshold_line.get_ydata()) == [h, h], 'Limiar desenhado divergente')
            if method == 'cusum-freeze':
                ax.plot(x, [num(r['posterior_state']) for r in rows], color='#666666',
                        ls=':', lw=1, label='Estado posterior (preservado se alarme)')
            ax.set_ylabel('σ / média\n(adimensional)' if method == 'cov' else 'Escore\n(adimensional)')
            title = names[method] + (' · candidato de decisão' if method == 'cusum-freeze' else ' · score persistido')
            if zoom:
                lo, hi = (-.3*h, 3*h)
                ax.set_ylim(lo, hi)
                n = sum(np.isfinite(v) and (v < lo or v > hi) for v in y)
                clipped.append(dict(feature=feature, scenario=scenario, block=block, method=method, lower=lo, upper=hi,
                                    scores_outside_view=n))
                title += f'\nAmpliação vertical: {n} valores fora da vista'
            ax.set_title(title, loc='left', fontsize=10)
            ax.legend(loc='upper right', fontsize=8, framealpha=.9)
        for ax in axs:
            limits(ax, d)
        axs[-1].set_xlabel('Tempo desde a origem do experimento (s)')
        stop = 'não registrado' if d['stop'] is None else f"{num(d['stop']):.6f} s"
        if d['event']:
            s, e = (num(d['event'][k]) for k in ('actual_start_seconds', 'actual_end_seconds'))
            event_text = f'Emissão real: [{s:.6f}; {e:.6f}) s · comando: {stop}'
        else:
            event_text = 'Controle C16: sem evento ofensivo; sem fronteiras de ataque'
        fig.suptitle(f'{LABELS[feature]} · {scenario} · B{block:02}' + (' · AMPLIAÇÃO' if zoom else ''), fontsize=14, y=.985)
        fig.text(.5, .94, event_text, ha='center', fontsize=8)
        fig.text(.5, .925, FEATURE_NOTES[feature], ha='center', fontsize=8)
        fig.text(.5, .025, 'Faixa: emissão (se houver); tracejado: início; contínuo: fim; magenta: comando.\n'
                 'Escores e pontos positivos na disponibilidade (fechamento). Observação na janela de 1 s.\n'
                 + ('Ampliação: limites verticais explícitos; consulte a figura integral para todos os picos.' if zoom else
                    'Resolução de 1 s, sem suavização; escalas verticais independentes. Ponto = decisão positiva.'),
                 ha='center', fontsize=8)
        fig.subplots_adjust(left=.16, right=.98, bottom=.1, top=.9, hspace=.58)
        name = f'T_{feature}_{scenario}' + ('' if args.legacy else f'_B{block:02}') + ('_zoom' if zoom else '')
        save(fig, name, f'Detalhar a trajetória B{block:02}' + (' perto do limiar' if zoom else ''),
             f'{LABELS[feature]}, {scenario}, B{block:02}. ' + FEATURE_NOTES[feature] + ' '
             'Observações oficiais de 1 s, escores e limiares congelados, pontos positivos na disponibilidade; '
             'CUSUM-freeze publica o candidato, com estado posterior secundário. '
             + ('Ampliação vertical explicitamente limitada; figura integral conserva todos os picos.' if zoom else
                'Eixos próprios; sem suavização ou corte de picos.'))
        return clipped

    zoom_rows = []
    for feature in args.features:
        for scenario in args.scenarios:
            if 'temporal' in args.plots:
                for block in args.temporal_blocks:
                    timeline(feature, scenario, block)
                    if feature == 'mean_duration_ms':
                        zoom_rows.extend(timeline(feature, scenario, block, True))
            if 'heatmap' not in args.plots:
                continue
            map_blocks = args.heatmap_blocks
            nblocks = len(map_blocks)
            fig, axs = plt.subplots(4, 1, figsize=(8.27, 11.69), sharex=True)
            for ax, method in zip(axs, METHODS):
                matrix = np.array([[-1 if r['decision'] is None else int(r['decision'])
                    for r in data[feature, scenario, b]['traces'][method]] for b in map_blocks])
                mesh = ax.pcolormesh(np.arange(30, 391), np.arange(nblocks+1), matrix,
                    cmap=ListedColormap(['#999999', '#F0F0F0', colors[method]]),
                    vmin=-1.5, vmax=1.5, edgecolors='none', rasterized=False)
                require(np.array_equal(np.asarray(mesh.get_array()).reshape(matrix.shape), matrix),
                        'Células desenhadas divergem das decisões')
                for j, b in enumerate(map_blocks):
                    d = data[feature, scenario, b]
                    if d['event']:
                        start, end = (num(d['event'][k]) for k in ('actual_start_seconds', 'actual_end_seconds'))
                        ax.plot([start, start], [j+.08, j+.92], color='#222222', ls='--', lw=1)
                        ax.plot([end, end], [j+.08, j+.92], color='#222222', lw=1.2)
                    if d['stop'] is not None:
                        ax.plot([num(d['stop'])]*2, [j+.08, j+.92], color='#CC79A7', ls=':', lw=1)
                ax.set(yticks=np.arange(nblocks)+.5, yticklabels=[f'B{b:02}' for b in map_blocks],
                       ylim=(nblocks, 0), xlim=(30, 390), xticks=TICKS)
                ax.set_title(names[method], loc='left', color=colors[method], fontsize=11)
                ax.legend(handles=[Patch(color='#F0F0F0', label='Negativa'),
                    Patch(color=colors[method], label='Positiva'), Patch(color='#999999', label='Indisponível')],
                    loc='upper right', bbox_to_anchor=(1, 1.23), ncol=3, fontsize=8, frameon=False)
                ax.tick_params(axis='y', labelsize=8)
            axs[-1].set_xlabel('Janela observada [i, i+1) (s desde a origem)')
            fig.suptitle(f'{LABELS[feature]} · {scenario} · {nblocks} '
                         + ('execução' if nblocks == 1 else 'execuções'), fontsize=14, y=.98)
            fig.text(.5, .025, 'Cada célula: janela observada de 1 s (decisão disponível em i+1).\n'
                + ('C16: sem evento ofensivo; nenhuma fronteira de ataque.\n' if scenario == 'C16' else
                   'Tracejado: início real; contínuo: fim real; magenta pontilhado: comando.\n')
                + 'Limites reais por linha, sem realinhamento. POST não representa emissão.', ha='center', fontsize=8)
            fig.subplots_adjust(left=.1, right=.98, bottom=.1, top=.92, hspace=.4)
            name = f'H_{feature}_{scenario}' + ('' if args.legacy else '_' + block_tag(map_blocks))
            save(fig, name, 'Comparar sinalização: ' + block_tag(map_blocks),
                 f'Mapa de decisões persistidas de {LABELS[feature]}, {scenario}. Colunas representam '
                 'janelas observadas [i,i+1), com disponibilidade em i+1; cinza = indisponível, '
                 'claro = negativa, cor do método = positiva. Limites reais por execução, se houver evento. '
                 'C16 não recebe fronteiras inventadas; POST não representa emissão.')
    table(out, 'zoom_limits', zoom_rows)

    delay_rows = []

    def delay_figure(features, scenarios, legacy=False):
        fig, axs = plt.subplots(len(features), len(scenarios), squeeze=False,
                               figsize=(11.69, 8.27) if legacy else (8.27, 4.8))
        for i, feature in enumerate(features):
            for j, scenario in enumerate(scenarios):
                ax = axs[i, j]
                for k, method in enumerate(METHODS):
                    r = summary['results'][f'{feature}/{scenario}/{method}']
                    delay, det = r['delay'], r['detection']
                    mean, ci = delay['mean_seconds'], delay['interval']
                    require(det is None and scenario == 'C16' or
                            det is not None and delay['detected'] == det['successes'] and det['n'] == 12,
                            'Suporte de atraso divergente')
                    label = 'Detecções/avaliados: N/A; misses: N/A' if det is None else (
                        f"{det['successes']}/{det['n']}; {r['misses']} misses")
                    y = 3-k
                    if mean is None:
                        ax.text(.02, y, 'Não aplicável (sem evento)' if scenario == 'C16' else
                                'Não aplicável (sem detecção)', transform=ax.get_yaxis_transform(),
                                va='center', fontsize=8)
                    else:
                        ax.plot(mean, y, 'o' if ci else 'D', color=colors[method], ms=5,
                                markerfacecolor=colors[method] if ci else 'white')
                        if ci:
                            ax.errorbar(mean, y, xerr=[[mean-ci[0]], [ci[1]-mean]], color=colors[method], capsize=3)
                            label = f'{mean:.3f} [{ci[0]:.3f}; {ci[1]:.3f}] s\n' + label
                        else:
                            label = f'{mean:.3f} s; sem IC\n' + label
                    ax.text(1.02, y, label.replace('.', ','), transform=ax.get_yaxis_transform(),
                            va='center', fontsize=8)
                    delay_rows.append(dict(feature=feature, scenario=scenario, method=method, **delay,
                        evaluated=det['n'] if det else None, misses=r['misses'],
                        support_blocks='B01–B12', support_runs=r['n_runs']))
                ax.set(yticks=range(4), yticklabels=[names[m] for m in METHODS[::-1]], ylim=(-.6, 3.6),
                       title=f'{LABELS[feature]} · {scenario}', xlabel='Atraso condicional médio (s)')
                support = [summary['results'][f'{feature}/{scenario}/{m}']['delay'] for m in METHODS]
                upper = max(((d['interval'][1] if d['interval'] else d['mean_seconds'])
                            for d in support if d['mean_seconds'] is not None), default=1.)
                ax.set_xlim(0, upper*1.15)
                ax.grid(axis='x', alpha=.2)
        fig.suptitle('Atraso condicional · IC95% congelado · suporte completo B01–B12', fontsize=12, y=.98)
        fig.text(.5, .025, 'Círculo/barra: média/IC95%; losango vazio: média sem IC. Rótulos: detectados/avaliados; misses.\n'
                 'Disponibilidade no fechamento; não mede tempo computacional. Misses não recebem atraso zero.',
                 ha='center', fontsize=8)
        fig.subplots_adjust(left=.12 if legacy else .2, right=.83 if legacy else .65,
                            bottom=.13 if legacy else .19, top=.87, hspace=.45, wspace=1.25)
        name = 'L_conditional_delay' if legacy else f'L_{features[0]}_{scenarios[0]}_B01-B12'
        save(fig, name, 'Atraso e suporte completo congelado: B01–B12',
             'Médias condicionais e IC95% transcritos do summary TEST, sempre para os 12 blocos. '
             '--blocks não altera esse suporte. Detectados/avaliados e misses explícitos; '
             'C16 é não aplicável. Média sem IC permanece visível; sem detecção não recebe atraso zero. '
             'A disponibilidade atribuída ao fechamento não mede tempo computacional.')

    if 'delay' in args.plots:
        if args.legacy:
            delay_figure(args.features, args.scenarios, True)
        else:
            for feature in args.features:
                for scenario in args.scenarios:
                    delay_figure([feature], [scenario])
    table(out, 'conditional_delay_frozen', delay_rows)

    if args.legacy:
        # Context D follows the original visual-only transformations, using authenticated raw inputs.
        fig, axs = plt.subplots(4, 3, figsize=(11.69, 8.27), sharex=True, sharey='row')
        context_rows = []
        for j, scenario in enumerate(('C16', 'M16', 'E16')):
            d = data['request_starts', scenario, selected]
            ds = io.locate(d['receipt']['dataset'])
            requests = io.csv(io.linked(ds, d['dm']['files'], 'raw/service/request_log.csv'))
            ticks = io.csv(io.linked(ds, d['dm']['files'], 'raw/infrastructure/simulation_metrics.csv'))
            require(all(r['run_id'] == d['receipt']['run_id'] for r in requests), 'Contexto de outra execução')
            edges = np.arange(30, 391, 5)
            centers = (edges[:-1]+edges[1:])/2
            for cohort, label, color, style in [('benign', 'Legítimos', '#0072B2', '-'),
                                               ('all', 'Ambas as classes', '#777777', '--')]:
                req = [r for r in requests if cohort == 'all' or r['traffic_class'] == 'benign']
                ends = np.array([num(r['end_elapsed_seconds']) for r in req])
                durations = np.array([num(r['duration_ms']) for r in req])
                duration = [np.mean(durations[(ends >= a) & (ends < b)]) if np.any((ends >= a) & (ends < b)) else np.nan
                            for a, b in zip(edges[:-1], edges[1:])]
                axs[1, j].plot(centers, duration, color=color, ls=style, lw=.9, label=label)
                starts = np.sort([num(r['elapsed_seconds']) for r in req])
                grid = np.arange(30, 391)
                pending = np.searchsorted(starts, grid, side='left') - np.searchsorted(np.sort(ends[np.isfinite(ends)]), grid, side='left')
                axs[3, j].step(grid, pending, where='post', color=color, ls=style, lw=.9, label=label)
                context_rows.extend(dict(scenario=scenario, cohort=cohort, kind='duration_5s', time_s=t, value=v)
                                    for t, v in zip(centers, duration))
                context_rows.extend(dict(scenario=scenario, cohort=cohort, kind='pending_1s', time_s=t, value=v)
                                    for t, v in zip(grid, pending))
            for cls, label, color in [('benign', 'Legítimos', '#0072B2'), ('attack', 'Ofensivos', '#D55E00')]:
                counts, _ = np.histogram([num(r['elapsed_seconds']) for r in requests if r['traffic_class'] == cls], bins=edges)
                # np.histogram includes the rightmost edge; enforce the original half-open horizon.
                counts[-1] -= sum(num(r['elapsed_seconds']) == 390 and r['traffic_class'] == cls for r in requests)
                axs[0, j].plot(centers, counts/5, color=color, lw=.9, label=label)
                context_rows.extend(dict(scenario=scenario, cohort=cls, kind='starts_rps_5s', time_s=t, value=v)
                                    for t, v in zip(centers, counts/5))
            cpu = [num(r['average_cpu_percent']) if r['active_containers_names'].strip() else np.nan for r in ticks]
            axs[2, j].plot([num(r['elapsed_seconds']) for r in ticks], cpu, color='#009E73', lw=.8)
            context_rows.extend(dict(scenario=scenario, cohort='victim', kind='cpu_native', time_s=num(r['elapsed_seconds']), value=v)
                                for r, v in zip(ticks, cpu))
            axs[0, j].set_title(scenario)
            for ax in axs[:, j]:
                limits(ax, d)
                ax.tick_params(labelsize=8)
            axs[3, j].set_xlabel('Tempo (s)')
        for i, label in enumerate(['Inícios HTTP/s\nbins de 5 s', 'Duração (ms)\nconclusão, 5 s', 'CPU Docker (%)\nticks da vítima', 'Pendentes no cliente\namostra de 1 s']):
            axs[i, 0].set_ylabel(label, fontsize=9)
        for i in (0, 1, 3):
            axs[i, 0].legend(loc='upper left', fontsize=7, framealpha=.8)
        fig.suptitle('D revisada · Contexto operacional · B01', fontsize=14, y=.98)
        fig.text(.5, .025, 'Faixa: emissão real; tracejado: início; contínuo: fim; magenta pontilhado: comando.\n'
                 'Carga e duração: bins auxiliares de 5 s; CPU: ticks; pendências no cliente: 1 s. Exemplo ilustrativo.',
                 ha='center', fontsize=9)
        fig.subplots_adjust(left=.1, right=.98, bottom=.13, top=.91, hspace=.28, wspace=.17)
        save(fig, 'D_context_revised', 'Contextualizar carga, serviço e infraestrutura',
             'Bloco B01: carga realizada e duração por conclusão em bins auxiliares de 5 s; CPU em ticks suportados '
             'da vítima inteira; pendências no cliente amostradas a 1 s. Emissão e comando reais. '
             'Duração auxiliar difere da feature oficial de 1 s e da coorte operacional por início. '
             'CPU não é instantânea. O exemplo não substitui as 12 execuções.')
        table(out, 'D_context_display', context_rows)

    write_index(out, figure_index, audit, args)
    table(out, 'sources', [dict(path=str(Path(p).relative_to(repo)) if repo in Path(p).parents else p, sha256=h)
                           for p, h in sorted(io.sources.items())])
    command = shlex.join([sys.executable, '-B', str(Path(__file__).resolve()),
        '--repo', str(repo), '--plan', str(args.plan), '--checkpoint', str(args.checkpoint),
        '--checkpoint-sha256', args.checkpoint_sha256, '--output', str(out)] +
        ([] if args.legacy else ['--features', *args.features, '--scenarios', *args.scenarios,
         '--plots', *args.plots] + (['--blocks', *map(str, args.blocks)] if args.blocks is not None else [])) +
        (['--overwrite'] if args.overwrite else []))
    provenance = dict(checkpoint_sha256=args.checkpoint_sha256, plan_sha256=cp['authority']['plan_sha256'],
        summary=cp['artifacts']['summary'], selected_block=selected if args.legacy else None,
        selection_rule='Menor bloco TEST completo' if args.legacy else 'Seleção explícita pela CLI',
        selection=dict(legacy=args.legacy, features=args.features, scenarios=args.scenarios, plots=args.plots,
            requested_blocks=args.blocks,
            temporal_blocks=args.temporal_blocks if 'temporal' in args.plots else [],
            heatmap_blocks=args.heatmap_blocks if 'heatmap' in args.plots else [],
            delay_blocks=ALL_BLOCKS if 'delay' in args.plots else [], context=args.legacy),
        observed_definitions={f: next((d['definition'] for key,d in data.items() if key[0] == f), None)
                              for f in args.features},
        python=platform.python_version(), numpy=np.__version__, matplotlib=matplotlib.__version__,
        generator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), command=command,
        source_files=len(io.sources), evaluated_series=len(data), checked_method_series=len(audit),
        transformations=dict(temporal='Transcrição de 1 s; floats somente na renderização; nulos como NaN/lacunas',
            maps='Booleanos persistidos: -1 indisponível, 0 negativo, 1 positivo; coluna [i,i+1)',
            delay='Estimativas/ICs transcritos; nenhuma inferência nova',
            zoom='Somente limites de vista [-0.3h,3h], sem alterar escores; figura integral acompanha',
            context='Transformações auxiliares da D original: bins de 5 s, ticks e contagem de pendências no cliente'),
        prohibited_operations_executed=False, scientific_runtime_imported=False,
        decisions_scores_thresholds_or_intervals_recomputed=False, inconsistencies=[],
        visual_inspection='Inspeção manual registrada separadamente; a geração não certifica revisão visual',
        outputs={str(p.relative_to(out)): hashlib.sha256(p.read_bytes()).hexdigest()
                 for folder in ('figures', 'tables') for p in sorted((out/folder).iterdir())})
    (out / 'provenance.json').write_text(json.dumps(provenance, indent=2, ensure_ascii=False)+'\n')
    (out / 'reproduce.sh').write_text('#!/bin/sh\n'+command+'\n')
    print(json.dumps({k: provenance[k] for k in ('source_files', 'evaluated_series', 'checked_method_series', 'inconsistencies')}))


def write_index(out, figures, audit, args):
    lines = ['# Comportamento temporal dos detectores — clock r2', '',
        'Apresentação offline do TEST congelado. PDFs vetoriais e PNGs a 300 dpi. '
        'Sem seletores, preserva-se o pacote anterior de 12 figuras; seleções explícitas não geram D. '
        'As apresentações anteriores permanecem preservadas.', '',
        f'Seleção: features={args.features}; cenários={args.scenarios}; tipos={args.plots}. '
        f'Temporal: {args.temporal_blocks if "temporal" in args.plots else []}; '
        f'mapas: {args.heatmap_blocks if "heatmap" in args.plots else []}; '
        'atraso: sempre suporte completo B01–B12, independentemente de --blocks.', '',
        '| Figura / arquivos | Finalidade |', '|---|---|']
    for name, purpose, _ in figures:
        lines.append(f'| [{name}](figures/{name}.pdf) · [PNG](figures/{name}.png) | {purpose} |')
    lines += ['', '## Legendas sugeridas', '']
    for name, _, caption in figures:
        lines += [f'**{name}.** {caption}', '']
    lines += ['## Escore, observação e estado', '',
        '| Método | Escore efetivamente exibido e comparado | Escala / decisão |',
        '|---|---|---|',
        '| CoV | `score`: desvio padrão amostral / média das seis observações consecutivas, incluindo a atual; ddof=1. | Adimensional, sem multiplicar por 100; `score > h`. |',
        '| Z-score | `score`: resíduo com sinal padronizado pela média e desvio padrão da baseline congelada. | Adimensional; cauda superior, `score > h`; não usa valor absoluto. |',
        '| EWMA | `score`: EWMA dos resíduos padronizados, λ=0,2, estado inicial zero. | Adimensional; cauda superior, `score > h`; não é a feature em ms. |',
        '| CUSUM-freeze | `candidate == score`: candidato da transição, max(0, estado anterior + resíduo − 0,5). | Adimensional; candidato > h sinaliza e rejeita a atualização; estado posterior preserva o anterior. |', '',
        'As fórmulas descrevem o código: **não são executadas pelo gerador**. Limiares são transcritos de '
        '`run.calibration → thresholds`; o h do CUSUM-freeze também é conferido no componente da transição. '
        'Quando há séries ou mapas, valores exatos, candidato, estado anterior/posterior, observação, decisão '
        'e disponibilidade ficam em tables/temporal_records.csv. Os métodos não compartilham escala numérica.', '',
        '`request_starts` conta tentativas de ambas as classes iniciadas na janela [i,i+1). '
        '`mean_duration_ms` usa a duração inteira das tentativas concluídas nessa janela, incluindo falhas com duração registrada e '
        'requisições iniciadas antes. Ausência de conclusão implica valor ausente, não zero.', '',
        'CPU: média dos ticks registrados em cada janela, derivados de coleta/cache e referentes à vítima inteira; '
        'não é CPU instantânea, média temporal exata ou carga exclusivamente legítima. Pacotes ingress: registros '
        'source→proxy, incluindo payload zero e retransmissões. Payload TCP: soma do campo preservado; '
        'não são bytes físicos ou bytes HTTP únicos. Ausência de suporte de rede permanece ausente.', '',
        'A observação ocupa [i,i+1); escores e pontos positivos das séries são desenhados em '
        '`available_at_seconds`, que neste TEST coincide com i+1. Incluem-se as observações [30,390), '
        'inclusive a última decisão disponível em 390 s. As células dos mapas ocupam a **janela observada**, '
        'não um segundo adicional de emissão ou uma duração do alarme. O estado posterior do CUSUM-freeze '
        'é interno e secundário: sozinho não representa a sinalização. Linhas entre escores ligam amostras '
        'de 1 s para leitura, sem suavizar nem criar novas observações.', '',
        'Início/fim vêm do CSV de eventos vinculado por hash à avaliação e ao dataset; comando vem do '
        'recibo referenciado no checkpoint. O comando não substitui o fim certificado de emissão; E16 pode '
        'ter ambos quase sobrepostos. Valores exatos em tables/event_boundaries.csv quando há séries/mapas. '
        'Nas paradas programadas, o campo de comando é nulo: nenhum instante de comando é inferido '
        'a partir do fim da emissão. POST começa após o fim real e pode conter efeitos residuais.', '',
        '## Uso no TCC e limitações', '',
        'Corpo: D anterior como contexto, atraso condicional e mapas de request_starts M16/E16; '
        'selecionar as trajetórias relevantes à discussão. Apêndice: demais mapas, trajetórias '
        'integrais e ampliações de duração. Séries e mapas foram dimensionados em A4 retrato; atraso e D '
        'em paisagem. Usar PDF em página inteira para manter as fontes legíveis.', '',
        'As ampliações de duração são adicionais, com limites verticais explícitos [-0,3h;3h] nos escores '
        'e contagem dos valores fora da vista em cada painel; as figuras integrais mantêm todos os picos. '
        'A observação mantém amplitude integral em ambas. Não há recorte silencioso.', '',
        'CoV de request_starts mantém médias condicionais sem IC (6 detectados); CoV de duração M16 '
        'tem 0/12 e atraso não aplicável. O IC só existe com suporte previsto no protocolo (≥8 detecções). '
        'Misses são contados separadamente, nunca convertidos em atraso zero. Não há medida de latência '
        'computacional nem decomposição causal do atraso; disponibilidade é atribuída ao fechamento.', '',
        'As séries consumidas preservam candidato e estado posterior. '
        'A disponibilidade examinada é registrada em tables/directed_checks.csv; o gerador preserva nulos e os mapas reservam '
        'cor própria à indisponibilidade. Não são criadas métricas de duração ou persistência de alarmes. '
        'Trajetórias individuais são ilustrativas; os mapas preservam os blocos selecionados e suas exposições. Os ICs são pontuais '
        'e condicionais ao treinamento congelado; não sustentam ranking global.', '',
        '## Fontes e verificações dirigidas', '',
        'Cadeia: checkpoint TEST autenticado por SHA256 exigido na CLI → summary → avaliações → runs '
        'e calibrações; checkpoint → recibos → dataset/features → observáveis e eventos. '
        'Identidades e hashes são conferidos para os arquivos consumidos. Código semântico é lido e '
        'comparado aos hashes do plano/run, sem importar o runtime científico. Não se repete a auditoria '
        'histórica da campanha, a calibração ou o processamento dos detectores.', '',
        f'Foram conferidas {len(audit)} séries de método selecionadas, grade de 360 janelas, disponibilidade, suporte publicado, '
        'vínculo observação/candidato, identidade score/candidato e preservação do estado em alarmes. '
        'A primeira disponibilidade publicada foi localizada em decisão positiva existente. '
        'Os arrays dos mapas são confrontados com as células renderizadas; os atrasos e ICs são '
        'transcritos diretamente, sem reaplicar limiar ou reconstruir trajetórias.', '',
        'Conferências em tables/directed_checks.csv quando houver séries individuais/mapas; [fontes e hashes](tables/sources.csv), '
        '[proveniência e transformações](provenance.json), [comando de reprodução](reproduce.sh), '
        'Inspeção visual deve acompanhar cada seleção exportada. Para repetir no mesmo diretório, acrescentar `--overwrite`; '
        'sem essa opção o gerador recusa saídas existentes. Artefatos científicos e a apresentação anterior '
        'são protegidos inclusive com essa opção.', '',
        'Pendências: escolha editorial final e incorporação ao texto do TCC. Nenhuma inconsistência '
        'de semântica foi encontrada nas evidências consumidas; não há correção científica proposta.', '']
    (out / 'index.md').write_text('\n'.join(lines))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError) as exc:
        print(f'Erro: {exc}', file=sys.stderr)
        sys.exit(2)
