#!/usr/bin/env python3
"""Apresentação offline de registros congelados: nenhum runtime científico importado."""
import argparse
import csv
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
METHODS = ['cov', 'zscore', 'ewma', 'cusum-freeze']
LABELS = {'request_starts': 'Inícios HTTP', 'mean_duration_ms': 'Duração HTTP'}
UNITS = {'request_starts': 'Tentativas\npor janela de 1 s', 'mean_duration_ms': 'Média por conclusão (ms)'}
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
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ('repo', 'plan', 'checkpoint', 'output'):
        ap.add_argument('--' + name, type=Path, required=True)
    ap.add_argument('--checkpoint-sha256', required=True)
    ap.add_argument('--overwrite', action='store_true', help='Permite substituir arquivos da apresentação de saída')
    args = ap.parse_args()
    repo = args.repo.resolve()
    io = Inputs(repo)
    out = io.locate(args.output).resolve()
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
        existing = [p for p in out.iterdir() if p.name != 'generate.py']
        require(not existing, 'Saídas existentes; use outro diretório ou --overwrite')
    io.read(plan['protocol']['path'], plan['protocol']['sha256'])
    summary = io.artifact(cp['artifacts']['summary'])
    require(summary['authority'] == cp['authority'] and not summary['missing_runs'], 'Summary incompatível')
    entries = {e['id']: e for e in plan['entries'] if e['partition'] == 'TEST'}
    receipts = {}
    for ref in cp['receipts']:
        doc = io.artifact(ref)
        require(doc['entry'] == entries[doc['entry']['id']], 'Identidade do recibo diverge')
        receipts[doc['entry']['id']] = doc['receipt']
    require(set(entries) == set(receipts) and len(entries) == 36, 'TEST incompleto')
    blocks = sorted({e['block'] for e in entries.values()})
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
    for path in ('index.md', 'inventory.md', 'pending.md'):
        io.track(previous.parent / path)
    for path in ('report.md', 'methodology_note.md'):
        io.track(repo / 'reports/scientific_reduced_clock_r2_20261030' / path)

    data, boundaries, audit, temporal = {}, {}, [], []
    for ref in summary['evaluations']:
        # Manifest reference paths are used only to avoid opening unrelated features.
        # Membership is then checked from the authenticated manifest, never inferred.
        if not any('/' + f + '/' in ref['path'] for f in FEATURES):
            continue
        ev = io.artifact(ref)
        feature, entry = ev['feature'][1], ev['entry']
        require(entry == entries[entry['id']] and feature in FEATURES, 'Avaliação fora do escopo')
        if entry['scenario'] == 'C16' and entry['block'] != selected:
            continue
        run = io.artifact(ev['run'])
        source, receipt = run['source'], receipts[entry['id']]
        require(run['authority'] == ev['authority'] == cp['authority'], 'Autoridade divergente')
        require(source['entry_id'] == entry['id'] and source['run_id'] == receipt['run_id']
                and source['feature'] == feature and source['partition'] == 'TEST', 'Fonte divergente')
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
                    require(r['candidate'] == r['score'] and r['observation'] == (window_obs[i][feature] or None),
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
                         event=event, stop=stop, receipt=receipt, dm=dm)
        boundaries[entry['id']] = dict(entry=entry['id'], block=entry['block'], scenario=entry['scenario'],
            actual_start_seconds=event['actual_start_seconds'] if event else None,
            actual_end_seconds=event['actual_end_seconds'] if event else None, stop_command_seconds=stop)
    require(len(data) == 50, 'Esperadas 48 séries ofensivas e duas C16 de B01')
    for feature in FEATURES:
        for scenario in ('M16', 'E16'):
            require(all((feature, scenario, b) in data for b in blocks), 'Bloco ausente nos mapas')

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

    def timeline(feature, scenario, zoom=False):
        d = data[feature, scenario, selected]
        fig, axs = plt.subplots(5, 1, figsize=(8.27, 11.69), sharex=True)
        o = list(d['obs'].values())
        axs[0].stairs([num(r[feature]) for r in o], np.arange(30, 391), color='#444444', lw=.8)
        axs[0].set_ylabel(UNITS[feature])
        axs[0].set_title('Observação oficial em [i, i+1) · ambas as classes', loc='left', fontsize=10)
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
                clipped.append(dict(feature=feature, scenario=scenario, method=method, lower=lo, upper=hi,
                                    scores_outside_view=n))
                title += f'\nAmpliação vertical: {n} valores fora da vista'
            ax.set_title(title, loc='left', fontsize=10)
            ax.legend(loc='upper right', fontsize=8, framealpha=.9)
        for ax in axs:
            limits(ax, d)
        axs[-1].set_xlabel('Tempo desde a origem do experimento (s)')
        s, e = (num(d['event'][k]) for k in ('actual_start_seconds', 'actual_end_seconds'))
        stop = 'não registrado' if d['stop'] is None else f"{num(d['stop']):.6f} s"
        fig.suptitle(f'{LABELS[feature]} · {scenario} · B01' + (' · AMPLIAÇÃO' if zoom else ''), fontsize=14, y=.985)
        fig.text(.5, .935, f'Emissão real: [{s:.6f}; {e:.6f}) s · comando: {stop}', ha='center', fontsize=8)
        fig.text(.5, .025, 'Faixa: emissão; tracejado vertical: início; contínuo vertical: fim; magenta: comando.\n'
                 'Escores e pontos positivos na disponibilidade (fechamento). Observação na janela de 1 s.\n'
                 + ('Ampliação: limites verticais explícitos; consulte a figura integral para todos os picos.' if zoom else
                    'Resolução de 1 s, sem suavização; escalas verticais independentes. Ponto = decisão positiva.'),
                 ha='center', fontsize=8)
        fig.subplots_adjust(left=.16, right=.98, bottom=.1, top=.9, hspace=.58)
        name = f'T_{feature}_{scenario}' + ('_zoom' if zoom else '')
        save(fig, name, 'Detalhar a trajetória B01' + (' perto do limiar' if zoom else ''),
             f'{LABELS[feature]}, {scenario}, B01 (menor bloco completo, seleção independente dos resultados). '
             'Observações oficiais de 1 s, escores e limiares congelados, pontos positivos na disponibilidade; '
             'CUSUM-freeze publica o candidato, com estado posterior secundário. '
             + ('Ampliação vertical explicitamente limitada; figura integral conserva todos os picos.' if zoom else
                'Eixos próprios; sem suavização ou corte de picos.'))
        return clipped

    zoom_rows = []
    for feature in FEATURES:
        for scenario in ('M16', 'E16'):
            timeline(feature, scenario)
            if feature == 'mean_duration_ms':
                zoom_rows.extend(timeline(feature, scenario, True))
            fig, axs = plt.subplots(4, 1, figsize=(8.27, 11.69), sharex=True)
            for ax, method in zip(axs, METHODS):
                matrix = np.array([[-1 if r['decision'] is None else int(r['decision'])
                    for r in data[feature, scenario, b]['traces'][method]] for b in blocks])
                mesh = ax.pcolormesh(np.arange(30, 391), np.arange(13), matrix,
                    cmap=ListedColormap(['#999999', '#F0F0F0', colors[method]]),
                    vmin=-1.5, vmax=1.5, edgecolors='none', rasterized=False)
                require(np.array_equal(np.asarray(mesh.get_array()).reshape(matrix.shape), matrix),
                        'Células desenhadas divergem das decisões')
                for j, b in enumerate(blocks):
                    d = data[feature, scenario, b]
                    s, e = (num(d['event'][k]) for k in ('actual_start_seconds', 'actual_end_seconds'))
                    ax.plot([s, s], [j+.08, j+.92], color='#222222', ls='--', lw=1)
                    ax.plot([e, e], [j+.08, j+.92], color='#222222', lw=1.2)
                    if d['stop'] is not None:
                        ax.plot([num(d['stop'])]*2, [j+.08, j+.92], color='#CC79A7', ls=':', lw=1)
                ax.set(yticks=np.arange(12)+.5, yticklabels=[f'B{b:02}' for b in blocks],
                       ylim=(12, 0), xlim=(30, 390), xticks=TICKS)
                ax.set_title(names[method], loc='left', color=colors[method], fontsize=11)
                ax.legend(handles=[Patch(color='#F0F0F0', label='Negativa'),
                    Patch(color=colors[method], label='Positiva'), Patch(color='#999999', label='Indisponível')],
                    loc='upper right', bbox_to_anchor=(1, 1.23), ncol=3, fontsize=8, frameon=False)
                ax.tick_params(axis='y', labelsize=8)
            axs[-1].set_xlabel('Janela observada [i, i+1) (s desde a origem)')
            fig.suptitle(f'{LABELS[feature]} · {scenario} · 12 execuções', fontsize=14, y=.98)
            fig.text(.5, .025, 'Cada célula: janela observada de 1 s (decisão disponível em i+1).\n'
                'Tracejado: início real; contínuo: fim real; magenta pontilhado: comando.\n'
                'Após o fim real: POST, inclusive alarmes residuais; exposições não realinhadas.', ha='center', fontsize=8)
            fig.subplots_adjust(left=.1, right=.98, bottom=.1, top=.92, hspace=.4)
            save(fig, f'H_{feature}_{scenario}', 'Comparar a sinalização entre B01–B12',
                 f'Mapa de decisões persistidas de {LABELS[feature]}, {scenario}. Colunas representam '
                 'janelas observadas [i,i+1), com disponibilidade em i+1; cinza = indisponível, '
                 'claro = negativa, cor do método = positiva. Limites reais por execução, sem realinhamento do fim. '
                 'PRE e POST permanecem visíveis; POST não representa emissão.')
    table(out, 'zoom_limits', zoom_rows)

    delay_rows = []
    fig, axs = plt.subplots(2, 2, figsize=(11.69, 8.27))
    for i, feature in enumerate(FEATURES):
        for j, scenario in enumerate(('M16', 'E16')):
            ax = axs[i, j]
            for k, method in enumerate(METHODS):
                r = summary['results'][f'{feature}/{scenario}/{method}']
                delay, det = r['delay'], r['detection']
                mean, ci = delay['mean_seconds'], delay['interval']
                require(delay['detected'] == det['successes'], 'Suporte de atraso divergente')
                label = f"{det['successes']}/{det['n']}; {r['misses']} misses"
                y = 3-k
                if mean is None:
                    ax.text(.02, y, 'Não aplicável (sem detecção)', transform=ax.get_yaxis_transform(),
                            va='center', fontsize=8)
                else:
                    ax.plot(mean, y, 'o' if ci else 'D', color=colors[method], ms=5,
                            markerfacecolor=colors[method] if ci else 'white')
                    if ci:
                        ax.errorbar(mean, y, xerr=[[mean-ci[0]], [ci[1]-mean]], color=colors[method], capsize=3)
                        label = f'{mean:.3f} [{ci[0]:.3f}; {ci[1]:.3f}] s\n' + label
                    else:
                        label = f'{mean:.3f} s; sem IC\n' + label
                label = label.replace('.', ',')
                ax.text(1.02, y, label, transform=ax.get_yaxis_transform(), va='center', fontsize=8)
                delay_rows.append(dict(feature=feature, scenario=scenario, method=method, **delay,
                    evaluated=det['n'], misses=r['misses']))
            ax.set(yticks=range(4), yticklabels=[names[m] for m in METHODS[::-1]], ylim=(-.6, 3.6),
                   title=f'{LABELS[feature]} · {scenario}', xlabel='Atraso condicional médio (s)')
            support = [summary['results'][f'{feature}/{scenario}/{m}']['delay'] for m in METHODS]
            upper = max((d['interval'][1] if d['interval'] else d['mean_seconds'])
                        for d in support if d['mean_seconds'] is not None)
            ax.set_xlim(0, upper*1.15)
            ax.grid(axis='x', alpha=.2)
    fig.suptitle('Atraso entre eventos detectados · estimativas e IC95% congelados', fontsize=14, y=.98)
    fig.text(.5, .025, 'Círculo e barra: média e IC95%; losango vazio: média existente sem IC. Rótulos: detectados/avaliados; misses.\n'
             'Disponibilidade atribuída ao fechamento da janela; não mede tempo computacional. Misses não recebem atraso zero.',
             ha='center', fontsize=9)
    fig.subplots_adjust(left=.12, right=.83, bottom=.13, top=.9, hspace=.45, wspace=1.25)
    save(fig, 'L_conditional_delay', 'Apresentar atraso e suporte dos quatro métodos',
         'Médias condicionais e IC95% transcritos do summary TEST. Detectados/avaliados e misses explícitos. '
         'Losango vazio mantém média sem IC; ausência de detecção é não aplicável. '
         'A disponibilidade é atribuída ao fechamento da janela e não mede tempo computacional.')
    table(out, 'conditional_delay_frozen', delay_rows)

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

    write_index(out, figure_index, audit)
    table(out, 'sources', [dict(path=str(Path(p).relative_to(repo)) if repo in Path(p).parents else p, sha256=h)
                           for p, h in sorted(io.sources.items())])
    command = shlex.join([sys.executable, '-B', str(Path(__file__).resolve()),
        '--repo', str(repo), '--plan', str(args.plan), '--checkpoint', str(args.checkpoint),
        '--checkpoint-sha256', args.checkpoint_sha256, '--output', str(out)] + (['--overwrite'] if args.overwrite else []))
    provenance = dict(checkpoint_sha256=args.checkpoint_sha256, plan_sha256=cp['authority']['plan_sha256'],
        summary=cp['artifacts']['summary'], selected_block=selected,
        selection_rule='Menor bloco TEST completo, sem consultar resultados',
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
        visual_inspection='Ver visual_review.md (registro separado da geração)',
        outputs={str(p.relative_to(out)): hashlib.sha256(p.read_bytes()).hexdigest()
                 for folder in ('figures', 'tables') for p in sorted((out/folder).iterdir())})
    (out / 'provenance.json').write_text(json.dumps(provenance, indent=2, ensure_ascii=False)+'\n')
    (out / 'reproduce.sh').write_text('#!/bin/sh\n'+command+'\n')
    print(json.dumps({k: provenance[k] for k in ('source_files', 'evaluated_series', 'checked_method_series', 'inconsistencies')}))


def write_index(out, figures, audit):
    lines = ['# Comportamento temporal dos detectores — clock r2', '',
        'Apresentação offline do TEST congelado. PDFs vetoriais e PNGs a 300 dpi. '
        'B01 é o menor bloco completo, escolhido sem consultar os resultados. A D original permanece preservada.', '',
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
        'Valores exatos, candidato, estado anterior/posterior, observação, decisão e disponibilidade ficam em '
        '[temporal_records.csv](tables/temporal_records.csv). Os métodos não compartilham escala numérica.', '',
        '`request_starts` conta tentativas de ambas as classes iniciadas na janela [i,i+1). '
        '`mean_duration_ms` usa a duração inteira das tentativas concluídas nessa janela, incluindo falhas e '
        'requisições iniciadas antes. Ausência de conclusão implica valor ausente, não zero.', '',
        'A observação ocupa [i,i+1); escores e pontos positivos das séries são desenhados em '
        '`available_at_seconds`, que neste TEST coincide com i+1. Incluem-se as observações [30,390), '
        'inclusive a última decisão disponível em 390 s. As células dos mapas ocupam a **janela observada**, '
        'não um segundo adicional de emissão ou uma duração do alarme. O estado posterior do CUSUM-freeze '
        'é interno e secundário: sozinho não representa a sinalização. Linhas entre escores ligam amostras '
        'de 1 s para leitura, sem suavizar nem criar novas observações.', '',
        'Início/fim vêm do CSV de eventos vinculado por hash à avaliação e ao dataset; comando vem do '
        'recibo referenciado no checkpoint. O comando não substitui o fim certificado de emissão; E16 pode '
        'ter ambos quase sobrepostos. Valores exatos em [event_boundaries.csv](tables/event_boundaries.csv). '
        'Nas paradas programadas, o campo de comando é nulo: nenhum instante de comando é inferido '
        'a partir do fim da emissão. POST começa após o fim real e pode conter efeitos residuais.', '',
        '## Uso no TCC e limitações', '',
        'Corpo: D revisada como contexto, atraso condicional e mapas de request_starts M16/E16; '
        'selecionar as trajetórias B01 relevantes à discussão. Apêndice: demais mapas, quatro trajetórias '
        'integrais e ampliações de duração. Séries e mapas foram dimensionados em A4 retrato; atraso e D '
        'em A4 paisagem. Usar PDF em página inteira para manter as fontes legíveis.', '',
        'As ampliações de duração são adicionais, com limites verticais explícitos [-0,3h;3h] nos escores '
        'e contagem dos valores fora da vista em cada painel; as figuras integrais mantêm todos os picos. '
        'A observação mantém amplitude integral em ambas. Não há recorte silencioso.', '',
        'CoV de request_starts mantém médias condicionais sem IC (6 detectados); CoV de duração M16 '
        'tem 0/12 e atraso não aplicável. O IC só existe com suporte previsto no protocolo (≥8 detecções). '
        'Misses são contados separadamente, nunca convertidos em atraso zero. Não há medida de latência '
        'computacional nem decomposição causal do atraso; disponibilidade é atribuída ao fechamento.', '',
        'Todos os campos necessários ao escopo estão persistidos, inclusive candidato e estado posterior. '
        'Não há lacunas de decisão no horizonte examinado; o gerador preserva nulos e os mapas reservam '
        'cor própria à indisponibilidade. Não são criadas métricas de duração ou persistência de alarmes. '
        'B01 é ilustrativo; os mapas preservam as 12 execuções e suas exposições. Os ICs são pontuais '
        'e condicionais ao treinamento congelado; não sustentam ranking global.', '',
        '## Fontes e verificações dirigidas', '',
        'Cadeia: checkpoint TEST autenticado por SHA256 exigido na CLI → summary → avaliações → runs '
        'e calibrações; checkpoint → recibos → dataset/features → observáveis e eventos. '
        'Identidades e hashes são conferidos para os arquivos consumidos. Código semântico é lido e '
        'comparado aos hashes do plano/run, sem importar o runtime científico. Não se repete a auditoria '
        'histórica da campanha, a calibração ou o processamento dos detectores.', '',
        f'Foram conferidas {len(audit)} séries de método (50 combinações feature/execução; '
        '48 ofensivas e duas C16 B01), grade de 360 janelas, disponibilidade, suporte publicado, '
        'vínculo observação/candidato, identidade score/candidato e preservação do estado em alarmes. '
        'A primeira disponibilidade publicada foi localizada em decisão positiva existente. '
        'Os arrays dos mapas são confrontados com as células renderizadas; os atrasos e ICs são '
        'transcritos diretamente, sem reaplicar limiar ou reconstruir trajetórias.', '',
        '[Conferências](tables/directed_checks.csv), [fontes e hashes](tables/sources.csv), '
        '[proveniência e transformações](provenance.json), [comando de reprodução](reproduce.sh), '
        '[inspeção visual](visual_review.md). Para repetir no mesmo diretório, acrescentar `--overwrite`; '
        'sem essa opção o gerador recusa saídas existentes. Artefatos científicos e a apresentação anterior '
        'são protegidos inclusive com essa opção.', '',
        'Pendências: escolha editorial final e incorporação ao texto do TCC. Nenhuma inconsistência '
        'de semântica foi encontrada nas evidências consumidas; não há correção científica proposta.', '']
    (out / 'index.md').write_text('\n'.join(lines))


if __name__ == '__main__':
    main()
