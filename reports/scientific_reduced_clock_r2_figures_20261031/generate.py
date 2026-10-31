#!/usr/bin/env python3
"""Offline presentation of frozen clock-r2 outputs; never imports scientific runtime."""
import argparse
import csv
import hashlib
import json
import os
from collections import Counter, defaultdict
from pathlib import Path

os.environ.setdefault('MPLCONFIGDIR', '/tmp/clock-r2-matplotlib')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np

METHODS = ['cov', 'cusum-freeze', 'ewma', 'zscore']
NAMES = ['CoV', 'CUSUM-freeze', 'EWMA', 'z-score']
COLORS = ['#0072B2', '#D55E00', '#009E73', '#CC79A7']
FEATURES = ['request_starts', 'mean_duration_ms', 'mean_cpu_percent',
            'ingress_packet_count', 'ingress_tcp_payload_length_sum_bytes']
LABELS = ['Inícios HTTP', 'Duração HTTP', 'CPU da vítima', 'Pacotes ingress', 'Payload TCP ingress']
SCENARIOS = ['C16', 'M16', 'E16']


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--repo', type=Path, required=True)
    ap.add_argument('--plan', type=Path, required=True)
    ap.add_argument('--checkpoint', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    repo = args.repo.resolve()
    def locate(p):
        p = Path(p)
        if not p.is_absolute():
            return repo / p
        # Frozen references retain original checkout paths; support a relocated copy.
        for anchor in ('experiment_results', 'experiments', 'docs'):
            if anchor in p.parts:
                return repo.joinpath(*p.parts[p.parts.index(anchor):])
        return p
    out = args.output.resolve()
    frozen = repo / 'experiment_results'
    if out == frozen or frozen in out.parents or out == repo:
        raise ValueError('Output must be a separate presentation directory')
    out.mkdir(parents=True, exist_ok=True)
    (out / 'figures').mkdir(exist_ok=True)
    (out / 'tables').mkdir(exist_ok=True)
    sources = {}
    def track(p, expected=None):
        p = locate(p)
        if p not in sources:
            sources[p] = hashlib.sha256(p.read_bytes()).hexdigest()
        if expected and sources[p] != expected:
            raise ValueError('Frozen reference hash mismatch: ' + str(p))
        return p
    def read(p, expected=None):
        return json.loads(track(p, expected).read_text())
    def artifact(ref):
        return read(locate(ref['path']) / 'manifest.json', ref['manifest_sha256'])
    def csvread(p):
        with locate(p).open(newline='') as stream:
            return list(csv.DictReader(stream))
    def table(name, rows):
        if not rows:
            return
        fields = list(dict.fromkeys(k for row in rows for k in row))
        with (out / 'tables' / (name + '.csv')).open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            # Auxiliary nulls remain empty; zeros retain their observed meaning.
            writer.writerows({k: (None if isinstance(v, (float, np.floating)) and not np.isfinite(v) else v)
                              for k, v in row.items()} for row in rows)
    def save(fig, name):
        for ext in ('pdf', 'png'):
            fig.savefig(out / 'figures' / (name + '.' + ext), dpi=300,
                        bbox_inches='tight', facecolor='white')
        plt.close(fig)
    def num(value):
        return float(value) if value is not None and value != '' else np.nan
    def estimate(doc):
        ci = doc.get('interval')
        return dict(estimate=doc.get('estimate', doc.get('mean_seconds')),
                    ci_low=ci[0] if ci else None, ci_high=ci[1] if ci else None,
                    n=doc.get('n', doc.get('detected')), ci_method=doc.get('method'))

    plan = read(args.plan)
    cp = read(args.checkpoint)
    track(args.plan, cp['authority']['plan_sha256'])
    assert cp['partition'] == 'TEST'
    read(plan['protocol']['path'], plan['protocol']['sha256'])
    summary = artifact(cp['artifacts']['summary'])
    assert summary['authority'] == cp['authority']
    # Inspect only currently used links, rather than replaying the historical graph.
    receipts = {}
    for ref in cp['receipts']:
        doc = artifact(ref)
        receipts[doc['entry']['id']] = (doc['entry'], doc['receipt'])
    assert len(receipts) == 36 and not summary['missing_runs']
    entries = {e['id']: e for e in plan['entries'] if e['partition'] == 'TEST'}
    assert entries.keys() == receipts.keys()
    for eid, (entry, _) in receipts.items():
        assert entry == entries[eid]
    primary = {}
    evalrows = []
    for ref in summary['evaluations']:
        doc = artifact(ref)
        entry = doc['entry']
        assert entry == entries[entry['id']]
        if doc['feature'][1] == 'request_starts':
            primary[entry['id']] = doc
        for method, values in doc['results'].items():
            evalrows.append(dict(entry=entry['id'], block=entry['block'],
                                 scenario=entry['scenario'], feature=doc['feature'][1],
                                 method=method, **values))
    # Nested values are not needed here: frozen evaluation results are scalar.
    table('evaluation_by_run', evalrows)
    detection, metrics = [], []
    for key, values in summary['results'].items():
        feature, scenario, method = key.split('/')
        base = dict(feature=feature, scenario=scenario, method=method)
        d = values['detection']
        detection.append(dict(**base, **(estimate(d) if d else dict(estimate=None)),
                              detected=d['successes'] if d else None,
                              evaluated=d['n'] if d else None, misses=values['misses']))
        for metric in ['fpr', 'recall', 'delay', 'any_false_alarm', 'post_fpr']:
            metrics.append(dict(**base, metric=metric, **estimate(values[metric])))
    table('event_detection', detection)
    table('window_delay_post_metrics', metrics)
    ops = summary['operational']
    op_rows, op_map = [], {}
    for scenario, data in ops['by_scenario'].items():
        for item in data['individual_runs']:
            op = item['operational']
            op_map[scenario, item['block']] = op
            op_rows.append(dict(entry=item['entry'], block=item['block'], scenario=scenario,
                                early_stop=op['early_stop'], recovery=op['recovery_confirmed'],
                                **op['scalars']))
    table('operational_by_run', op_rows)
    contrasts = []
    for metric, values in ops['paired_E16_minus_M16'].items():
        contrasts.append(dict(metric=metric, contrast='E16-M16', **estimate(values)))
    table('operational_contrasts_frozen', contrasts)
    table('operational_summaries_frozen', [dict(scenario=c, metric=k, **estimate(v))
          for c, data in ops['by_scenario'].items() for k, v in data['means'].items()])
    def fmt(value, scale=1):
        return 'indisponível' if value is None else f'{float(value)*scale:.3f}'.replace('.', ',')
    def formatted(doc, scale=1):
        bounds = doc.get('interval')
        return fmt(doc.get('estimate', doc.get('mean_seconds')), scale) + (' [' +
                fmt(bounds[0], scale) + '; ' + fmt(bounds[1], scale) + ']' if bounds else ' [IC indisponível]')
    contrast_defs = [('ACTIVE/mean_cpu_docker_percent', 'CPU da vítima', 'p.p.', 1),
                     ('ACTIVE/mean_all_ms', 'Duração HTTP legítima', 'ms', 1),
                     ('ACTIVE/timeout_fraction', 'Timeouts legítimos', 'p.p.', 100)]
    lines = ['| Variável ACTIVE | Unidade da diferença | E16−M16 [IC95%] | Pares |',
             '|---|---|---:|---:|']
    tex = [r'\begin{tabular}{llrr}', r'\hline', r'Variável ACTIVE & Unidade & E16--M16 [IC95\%] & Pares \\', r'\hline']
    for key, label, unit, scale in contrast_defs:
        doc = ops['paired_E16_minus_M16'][key]
        lines.append(f'| {label} | {unit} | {formatted(doc, scale)} | {doc["n"]} |')
        tex.append(f'{label} & {unit} & {formatted(doc, scale)} & {doc["n"]} ' + r'\\')
    tex += [r'\hline', r'\end{tabular}']
    (out/'tables/C_contrasts.md').write_text('\n'.join(lines)+'\n')
    (out/'tables/C_contrasts.tex').write_text('\n'.join(tex)+'\n')
    lines = ['| Cenário | Método | FPR por janela (%) [IC95%] | Runs com algum FP (%) [IC95%] |',
             '|---|---|---:|---:|']
    for scenario in SCENARIOS:
        for method, label in zip(METHODS, NAMES):
            doc = summary['results'][f'request_starts/{scenario}/{method}']
            lines.append(f'| {scenario} | {label} | {formatted(doc["fpr"], 100)} | {formatted(doc["any_false_alarm"], 100)} |')
    (out/'tables/B_fpr_vs_runs.md').write_text('\n'.join(lines)+'\n')

    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10,
                         'axes.spines.top': False, 'axes.spines.right': False,
                         'pdf.fonttype': 42, 'ps.fonttype': 42, 'axes.titleweight': 'bold'})
    fig, axs = plt.subplots(5, 2, figsize=(12, 12), sharex=True)
    for i, feature in enumerate(FEATURES):
        for j, scenario in enumerate(['M16', 'E16']):
            ax = axs[i, j]
            for k, method in enumerate(METHODS):
                values = summary['results'][f'{feature}/{scenario}/{method}']
                d = values['detection']
                x, lo, hi = d['estimate'], *d['interval']
                ax.errorbar(x * 100, 3-k, xerr=[[100*(x-lo)], [100*(hi-x)]],
                            fmt='o', color=COLORS[k], capsize=3, ms=5)
                ax.text(107, 3-k, f"{d['successes']}/{d['n']}; {values['misses']} misses",
                        va='center', fontsize=9)
            ax.set(yticks=range(4), yticklabels=NAMES[::-1] if j == 0 else [],
                   ylim=(-.6, 3.65), xlim=(-5, 170), xticks=[0, 25, 50, 75, 100],
                   title=f'{scenario} · {LABELS[i]}')
            ax.grid(axis='x', alpha=.2)
            if i == 4:
                ax.set_xlabel('Eventos detectados (%) · IC95% congelado')
    fig.suptitle('A · Detecção por evento nas cinco features', fontsize=16, y=.995)
    fig.text(.5, .008, '12 eventos por célula. C16 não possui eventos. ICs pontuais; sem ranking global.', ha='center')
    fig.tight_layout(rect=(0, .025, 1, .98), h_pad=1.4, w_pad=1.2)
    save(fig, 'A_detection')

    fig, ax = plt.subplots(figsize=(9, 5))
    for k, method in enumerate(METHODS):
        for j, scenario in enumerate(SCENARIOS):
            d = summary['results'][f'request_starts/{scenario}/{method}']['fpr']
            x, (lo, hi) = d['estimate'], d['interval']
            ax.errorbar(j + (k-1.5)*.14, x*100, yerr=[[100*(x-lo)], [100*(hi-x)]],
                        fmt='o', color=COLORS[k], capsize=4, label=NAMES[k] if j == 0 else None)
    ax.set(xticks=range(3), xticklabels=SCENARIOS, ylabel='FPR por janela benigna (%)',
           title='B · Falsos alarmes em request_starts', ylim=(0, 5.1))
    ax.legend(ncol=2, loc='upper left', frameon=False)
    ax.grid(axis='y', alpha=.2)
    fig.text(.5, .02, 'Média de 12 blocos e IC95% congelado. Em M16/E16, benignas incluem POST e efeitos residuais.\n'
             'FPR por janela difere da proporção de execuções com qualquer falso alarme (tabela auxiliar).', ha='center', fontsize=9)
    fig.tight_layout(rect=(0, .1, 1, 1))
    save(fig, 'B_false_alarms')

    complete = sorted(b for c, b in op_map if c == 'M16' and ('E16', b) in op_map)
    assert len(complete) == 12
    keys = ['ACTIVE/mean_cpu_docker_percent', 'ACTIVE/mean_all_ms', 'ACTIVE/timeout_fraction']
    titles = ['CPU da vítima · ambas as cargas', 'Duração HTTP · legítimos', 'Timeouts · legítimos']
    units = ['CPU Docker (%)', 'Média por coorte (ms)', 'Fração da coorte (%)']
    fig, axs = plt.subplots(1, 3, figsize=(12, 5.2))
    blockcolors = plt.get_cmap('tab20')(np.linspace(0, .95, 12))
    for ax, key, title, unit in zip(axs, keys, titles, units):
        scale = 100 if key.endswith('timeout_fraction') else 1
        for k, b in enumerate(complete):
            jitter = (k-5.5)*.012
            y = [num(op_map[c, b]['scalars'][key])*scale for c in ['M16', 'E16']]
            ax.plot([jitter, 1+jitter], y, '-o', color=blockcolors[k], alpha=.85, lw=1, ms=4)
        ax.set(xticks=[0, 1], xticklabels=['M16', 'E16'], xlim=(-.22, 1.22), title=title, ylabel=unit)
        ax.grid(axis='y', alpha=.2)
    handles = [Line2D([], [], color=blockcolors[k], marker='o', label=f'B{b:02}') for k, b in enumerate(complete)]
    fig.legend(handles=handles, loc='lower center', bbox_to_anchor=(.5, .065), ncol=6, frameon=False, fontsize=9)
    fig.suptitle('C · Impacto em ACTIVE: 12 pares de execuções', fontsize=15)
    fig.text(.5, .015, 'Exposições realizadas diferentes; E16 sob política de proteção. Não é uma comparação sob dose igual.', ha='center', fontsize=9)
    fig.tight_layout(rect=(0, .19, 1, .95), w_pad=2)
    save(fig, 'C_paired_service')

    # Objective selection independent of observed values or alarm shape.
    blocks = sorted({e['block'] for e in entries.values()})
    selected = next(b for b in blocks if {e['scenario'] for e in entries.values() if e['block'] == b} == set(SCENARIOS))
    selected_entries = {e['scenario']: e for e in entries.values() if e['block'] == selected}
    temporal_rows, alarm_rows, event_rows, proxy_rows = [], [], [], []
    issues = []
    selected_data = {}
    for eid, (entry, receipt) in sorted(receipts.items()):
        ds = locate(receipt['dataset'])
        dm = read(ds / 'dataset_manifest.json', receipt['dataset_manifest_sha256'])
        assert dm['run_id'] == receipt['run_id']
        assert receipt['operational'] == primary[eid]['operational']
        files = {f['path']: f for f in dm['files']}
        def linked(relative):
            f = files[relative]
            p = track(ds / relative, f['sha256'])
            assert p.stat().st_size == f['bytes']
            return p
        status = read(linked(dm['run_status']))
        assert status['run_id'] == receipt['run_id'] and status['status'] == 'completed'
        epoch = num(status['experiment_start_timestamp'])
        requests = csvread(linked('raw/service/request_log.csv'))
        assert all(x['run_id'] == receipt['run_id'] for x in requests)
        reqids = {x['request_id'] for x in requests}
        # Per-run proxy completeness is descriptive inventory, not a new outcome metric.
        base = dict(entry=eid, block=entry['block'], scenario=entry['scenario'], run_id=receipt['run_id'])
        pr = dict(base, dataset_manifest=str((ds / 'dataset_manifest.json').relative_to(repo)),
                  missing_artifacts=json.dumps(dm['missing_artifacts']), requests_client=len(requests))
        required = ['monitor_samples.jsonl', 'monitor_summary.json', 'proxy_identity.json',
                    'proxy_access.log', 'proxy_error.log', 'container_output.log',
                    'monitor_interfaces.txt', 'monitor_networks.json']
        for name in required:
            rel = 'evidence/proxy/' + name
            pr[name + '_present'] = rel in files
            if rel in files:
                linked(rel)
                pr[name + '_bytes'] = files[rel]['bytes']
        for relative in ['evidence/proxy/nginx_build.txt', 'evidence/proxy/readiness.json',
                         'metadata/topology/proxy/proxy_config.conf',
                         'metadata/topology/proxy/backend_inventory.json', 'raw/service/routing_evidence.jsonl']:
            pr[relative+'_present'] = relative in files
            if relative in files:
                linked(relative)
        if not all(pr[n+'_present'] for n in required):
            issues.append(eid + ': missing proxy files')
            proxy_rows.append(pr)
            continue
        identity = read(ds / 'evidence/proxy/proxy_identity.json')
        ms = read(ds / 'evidence/proxy/monitor_summary.json')
        assert identity['run_id'] == ms['run_id'] == receipt['run_id']
        with (ds / 'evidence/proxy/monitor_samples.jsonl').open() as stream:
            samples = [json.loads(line) for line in stream]
        assert all(x['run_id'] == receipt['run_id'] and x['container_id'] == identity['id'] for x in samples)
        pr['monitor_records'] = len(samples)
        pr['thread_alive'] = ms.get('thread_alive')
        pr['fatal_error'] = ms.get('fatal_error')
        for source in ['status', 'docker']:
            good = [x[source] for x in samples if x[source]['success']]
            ts = [x['elapsed_seconds'] for x in good]
            inner = sorted(t for t in ts if 30 <= t <= 390)
            gaps = np.diff([30, *inner, 390])
            pr.update({source+'_success': len(good), source+'_failed': len(samples)-len(good),
                       source+'_summary_errors': ms['source_errors'][source],
                       source+'_first_s': min(ts) if ts else None,
                       source+'_last_s': max(ts) if ts else None,
                       source+'_max_gap_30_390_s': float(max(gaps)),
                       source+'_bins_1s_present_30_390': len({int(t) for t in inner if t < 390}),
                       source+'_max_collection_duration_s': max((x['duration_seconds'] for x in good), default=None)})
            pr[source+'_error_kinds'] = json.dumps(Counter(x[source]['error'] for x in samples if not x[source]['success']))
            if pr[source+'_failed'] != ms['source_errors'][source]:
                issues.append(eid + ': proxy summary/error count differs for ' + source)
            if source == 'docker':
                pr['cpu_values'] = sum(x['data']['cpu_percent'] is not None for x in good)
                pr['memory_values'] = sum(x['data']['memory_usage_bytes'] is not None for x in good)
                pr['docker_delta_states'] = json.dumps(Counter(x['data']['delta_state'] for x in good))
                interfaces = sorted({k for x in good for k in x['data']['interfaces']})
                pr['interfaces'] = ','.join(interfaces)
                for interface in interfaces:
                    for field in ['rx_bytes', 'tx_bytes', 'rx_bytes_per_second', 'tx_bytes_per_second']:
                        pr[interface+'_'+field+'_values'] = sum(x['data']['interfaces'].get(interface, {}).get(field) is not None for x in good)
            else:
                for field in ['active_connections', 'accepted_connections_total', 'handled_connections_total',
                              'requests_total', 'reading_connections', 'writing_connections', 'waiting_connections']:
                    pr[field+'_values'] = sum(x['data'].get(field) is not None for x in good)
                for field in ['accepted_connections_total', 'handled_connections_total', 'requests_total']:
                    vs = [x['data'][field] for x in good]
                    pr[field+'_decreases'] = sum(b < a for a, b in zip(vs, vs[1:]))
        with (ds / 'evidence/proxy/proxy_access.log').open() as stream:
            logs = [json.loads(line) for line in stream]
        logids = Counter(x['request_id'] for x in logs if x.get('request_id'))
        times = [float(x['timestamp'])-epoch for x in logs]
        pr.update(access_records=len(logs), access_first_s=min(times), access_last_s=max(times),
                  access_before_origin=sum(t < 0 for t in times), access_after_390=sum(t >= 390 for t in times),
                  phases=json.dumps(Counter(x.get('phase', '') for x in logs)),
                  client_ids_missing_in_access=len(reqids-logids.keys()),
                  access_ids_not_in_client=len(logids.keys()-reqids),
                  access_duplicate_ids=sum(v-1 for v in logids.values()),
                  upstream_values=sum(x.get('upstream') not in ('', '-', None) for x in logs),
                  request_time_values=sum(x.get('request_time') not in ('', '-', None) for x in logs),
                  upstream_time_values=sum(x.get('upstream_time') not in ('', '-', None) for x in logs),
                  connect_time_values=sum(x.get('connect_time') not in ('', '-', None) for x in logs),
                  error_log_lines=len((ds / 'evidence/proxy/proxy_error.log').read_text().splitlines()))
        proxy_rows.append(pr)
        if entry['block'] != selected:
            continue
        evs = csvread(linked('raw/attacks/attack_events.csv'))
        event = evs[0] if evs else None
        event_rows.append(dict(base, actual_start_s=event['actual_start_seconds'] if event else None,
                               actual_end_s=event['actual_end_seconds'] if event else None,
                               stop_command_s=receipt['operational']['scalars']['stop_command_seconds']))
        metrics_native = csvread(linked('raw/infrastructure/simulation_metrics.csv'))
        run = artifact(primary[eid]['run'])
        assert run['source']['run_id'] == receipt['run_id']
        for method, rows in run['methods'].items():
            for row in rows:
                alarm_rows.append(dict(**base, method=method, window_start_s=row['window_start_seconds'],
                                       window_end_s=row['window_end_seconds'],
                                       available_at_s=row['available_at_seconds'], decision=row['decision']))
        edges = np.arange(30, 391, 5)
        centers = (edges[:-1] + edges[1:])/2
        byclass = {c: [x for x in requests if x['traffic_class'] == c] for c in ['benign', 'attack']}
        vals = {}
        for c, cohort in byclass.items():
            starts = np.array([num(x['elapsed_seconds']) for x in cohort])
            # Empty offensive class in C16 is a verified absence, not missing data.
            vals[c+'_rps'] = np.histogram(starts, edges)[0]/5
        for name, cohort in [('benign', byclass['benign']), ('all', requests)]:
            end = np.array([num(x['end_elapsed_seconds']) for x in cohort])
            durations = np.array([num(x['duration_ms']) for x in cohort])
            vals[name+'_duration'] = np.array([np.mean(durations[(end >= a) & (end < b)])
                    if np.any((end >= a) & (end < b)) else np.nan for a, b in zip(edges[:-1], edges[1:])])
            st = np.sort([num(x['elapsed_seconds']) for x in cohort])
            en = np.sort(end[np.isfinite(end)])
            # Existing pending definition: start < t and (end missing or end >= t).
            grid = np.arange(30, 391)
            vals[name+'_pending'] = np.searchsorted(st, grid, side='left') - np.searchsorted(en, grid, side='left')
        for i, t in enumerate(centers):
            temporal_rows.append(dict(**base, start_s=edges[i], end_s=edges[i+1],
                                     benign_start_rps=vals['benign_rps'][i], attack_start_rps=vals['attack_rps'][i],
                                     benign_conclusion_duration_ms=vals['benign_duration'][i],
                                     all_conclusion_duration_ms=vals['all_duration'][i]))
        table('D_pending_'+entry['scenario'], [dict(time_s=int(t), benign=vals['benign_pending'][i],
                all_classes=vals['all_pending'][i]) for i, t in enumerate(grid)])
        table('D_victim_ticks_'+entry['scenario'], metrics_native)
        selected_data[entry['scenario']] = dict(vals=vals, centers=centers, grid=grid,
                                               metrics=metrics_native, run=run, event=event,
                                               stop=receipt['operational']['scalars']['stop_command_seconds'])
    table('proxy_inventory_by_run', proxy_rows)
    table('D_visual_aggregates_5s', temporal_rows)
    table('D_existing_alarms', alarm_rows)
    table('D_event_boundaries', event_rows)

    fig, axs = plt.subplots(5, 3, figsize=(15, 12), sharex=True, sharey='row')
    for j, scenario in enumerate(SCENARIOS):
        data = selected_data[scenario]
        v, t = data['vals'], data['centers']
        axs[0, j].plot(t, v['benign_rps'], color='#0072B2', label='Legítimos', lw=1.1)
        axs[0, j].plot(t, v['attack_rps'], color='#D55E00', label='Ofensivos', lw=1.1)
        axs[0, j].set_title(scenario)
        axs[1, j].plot(t, v['all_duration'], color='#777777', ls='--', label='Ambas as classes', lw=1)
        axs[1, j].plot(t, v['benign_duration'], color='#0072B2', label='Só legítimos', lw=1.2)
        ms = data['metrics']
        tx = [num(x['elapsed_seconds']) for x in ms]
        yy = [num(x['average_cpu_percent']) if x['active_containers_names'].strip() else np.nan for x in ms]
        axs[2, j].plot(tx, yy, color='#009E73', lw=1, label='Vítima · ambas as cargas')
        axs[3, j].step(data['grid'], v['all_pending'], color='#777777', ls='--', label='Ambas as classes', where='post', lw=1)
        axs[3, j].step(data['grid'], v['benign_pending'], color='#0072B2', label='Só legítimos', where='post', lw=1)
        ax = axs[4, j]
        for k, method in enumerate(METHODS):
            rows = data['run']['methods'][method]
            available = [num(x['available_at_seconds']) for x in rows if x['decision'] is True]
            missing = [num(x['available_at_seconds']) for x in rows if x['decision'] is None]
            ax.plot(available, [3-k]*len(available), '|', color=COLORS[k], ms=7, mew=1)
            if missing:
                ax.plot(missing, [3-k]*len(missing), 'x', color='#999999', ms=3)
        ax.set(yticks=range(4), yticklabels=NAMES[::-1], ylim=(-.6, 3.6), xlabel='Tempo desde o início (s)')
        for i in range(5):
            a = axs[i, j]
            a.set_xlim(30, 390)
            a.set_xticks([30, 90, 150, 210, 270, 330, 390])
            a.grid(axis='y', alpha=.15)
            ev = data['event']
            if ev:
                start, end = num(ev['actual_start_seconds']), num(ev['actual_end_seconds'])
                a.axvspan(start, end, color='#E69F00', alpha=.09)
                a.axvline(start, color='#444444', ls='--', lw=.9)
                a.axvline(end, color='#444444', ls='-', lw=.9)
            if data['stop'] is not None:
                a.axvline(num(data['stop']), color='#CC79A7', ls=':', lw=1.6)
        ev = data['event']
        text = 'Sem emissão ofensiva' if not ev else f"Início {num(ev['actual_start_seconds']):.3f} s · fim {num(ev['actual_end_seconds']):.3f} s"
        if data['stop'] is not None:
            text += f"\nComando {num(data['stop']):.3f} s (próximo ao fim)"
        axs[0, j].text(.02, .98, text, transform=axs[0, j].transAxes, va='top', fontsize=8,
                       bbox=dict(facecolor='white', edgecolor='none', alpha=.8))
    for i, ylabel in enumerate(['Inícios HTTP/s\n(bins de 5 s)', 'Duração HTTP (ms)\npor conclusão, bins de 5 s',
                                 'CPU Docker (%)\nticks registrados', 'Pendentes no cliente\n(tentativas, amostra a 1 s)', 'Alarmes existentes\nrequest_starts']):
        axs[i, 0].set_ylabel(ylabel)
    for i in range(4):
        if i < 4:
            axs[i, 0].legend(loc='upper left' if i != 0 else 'lower left', fontsize=8, frameon=False)
    fig.suptitle(f'D · Evolução temporal ilustrativa — bloco B{selected:02}', fontsize=16, y=.995)
    fig.text(.5, .008, 'Faixa: emissão real; tracejado: início; contínuo: fim; pontilhado magenta: comando de parada.\n'
             'Alarmes na disponibilidade atribuída (fechamento de 1 s). O exemplo não substitui as 12 repetições.', ha='center', fontsize=10)
    fig.tight_layout(rect=(0, .04, 1, .98), h_pad=1.1, w_pad=1.8)
    save(fig, 'D_time_evolution')
    table('sources', [dict(path=str(p.relative_to(repo)) if repo in p.parents else str(p), sha256=h) for p, h in sorted(sources.items())])
    provenance = dict(selected_block=selected, selection_rule='Lowest numbered complete TEST block, without using metric values',
                      selected_entries={c: e['id'] for c, e in selected_entries.items()},
                      plan=str(locate(args.plan)), checkpoint=str(locate(args.checkpoint)),
                      summary=cp['artifacts']['summary'], verified_source_files=len(sources),
                      existing_evaluations=len(summary['evaluations']), proxy_runs=len(proxy_rows),
                      inconsistencies=issues,
                      proxy_support=dict(status_failures=sum(x.get('status_failed', 0) for x in proxy_rows),
                                         docker_failures=sum(x.get('docker_failed', 0) for x in proxy_rows),
                                         null_cpu_first_reads=sum(x.get('docker_success', 0)-x.get('cpu_values', 0) for x in proxy_rows)),
                      matplotlib_version=matplotlib.__version__, numpy_version=np.__version__,
                      no_scientific_runtime_imported=True, no_confidence_intervals_computed=True,
                      generator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                      transformations='See index.md. Display means and counts only; no new inferential metrics.',
                      units='CSV official fractions remain 0..1. Plot B/detection/timeouts multiply by 100.')
    (out / 'provenance.json').write_text(json.dumps(provenance, indent=2, ensure_ascii=False)+'\n')
    print(json.dumps(provenance, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
