#!/usr/bin/env python3
"""Proxy clock r2: estatísticas descritivas offline, sem runtime experimental."""
import argparse
from collections import Counter
from decimal import Decimal, InvalidOperation
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import platform
import re
import shlex
import sys

os.environ.setdefault('MPLCONFIGDIR', '/tmp/clock-r2-matplotlib')
os.environ.setdefault('XDG_CACHE_HOME', '/tmp/clock-r2-cache')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np

SCENARIOS = ['C16', 'M16', 'E16']
PHASES = ['PRE', 'ACTIVE', 'POST']
CLASSES = ['benign', 'attack']
COLORS = {'benign': '#0072B2', 'attack': '#D55E00', 'cpu': '#009E73', 'memory': '#0072B2', 'status': '#7A5195'}
AUXILIARY = {'monitoring', 'setup', 'capture_audit'}
CODE = ['simulator/proxy_monitor.py', 'simulator/http_proxy.py', 'simulator/config.py',
        'experiments/dataset_schema.py', 'analysis/detection/scientific/evaluation.py']
EXHAUSTION = re.compile(r'worker_connections (?:are )?not enough|too many open files|'
    r'\b(?:EMFILE|ENFILE)\b|cannot allocate memory|accept4?\(\).*failed|socket\(\).*failed', re.I)
MIB = 2**20


def require(condition, message):
    if not condition:
        raise ValueError(message)


def scalar_time(raw):
    """Only a single finite nonnegative time in seconds; never sum upstream attempts."""
    if raw is None or str(raw).strip() == '':
        return None, 'missing'
    text = str(raw).strip()
    if text == '-':
        return None, 'marker_no_value'
    if ',' in text or ':' in text:
        return None, 'multiple_upstreams'
    try:
        value = Decimal(text)
    except InvalidOperation:
        return None, 'malformed'
    if not value.is_finite():
        return None, 'nonfinite'
    if value < 0:
        return None, 'negative'
    return float(value), 'valid'


def log_elapsed(raw, epoch):
    try:
        value = Decimal(str(raw)) - epoch
        return float(value) if value.is_finite() else None
    except (InvalidOperation, TypeError):
        return None


def phase_for(time, phases):
    if time is None:
        return None
    return next((name for name, (a, b) in phases.items() if a <= time < b), None)


def mean(values):
    values = [v for v in values if v is not None and math.isfinite(v)]
    return float(np.mean(values)) if values else None


def support(times, a, b):
    """Occupied touched 1-s bins and maximum point spacing, not continuous coverage."""
    ts = sorted(t for t in times if a <= t < b)
    possible = math.ceil(b) - math.floor(a)
    occupied = len({math.floor(t) for t in ts})
    return dict(n=len(ts), touched_bins_1s=possible, occupied_bins_1s=occupied,
        empty_bins_1s=possible-occupied, occupied_bins_fraction=occupied/possible,
        max_gap_including_edges_seconds=max(np.diff([a, *ts, b])),
        first_seconds=ts[0] if ts else None, last_seconds=ts[-1] if ts else None)


def native_line(ax, times, values, **kwargs):
    """NaNs break failed reads; unobserved spacings >1.5 s get explicit breaks too."""
    x, y, gaps = [], [], []
    for i, (t, v) in enumerate(zip(times, values)):
        if i and t-times[i-1] > 1.5:
            x.append(float('nan')); y.append(float('nan'))
            gaps.append((times[i-1], t))
        x.append(t); y.append(float('nan') if v is None else v)
    ax.plot(x, y, lw=.8, marker='.', ms=2, **kwargs)
    return gaps


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for key in ['repo', 'plan', 'checkpoint', 'output']:
        ap.add_argument('--'+key, type=Path, required=True)
    ap.add_argument('--checkpoint-sha256', required=True)
    ap.add_argument('--temporal-block', type=int, choices=range(1, 13), default=None,
                    help='Padrão: B01, menor bloco completo; escolha explícita de 1 a 12')
    ap.add_argument('--overwrite', action='store_true')
    args = ap.parse_args()
    repo = args.repo.resolve()
    util_path = repo/'reports/scientific_reduced_clock_r2_temporal_20261102/generate.py'
    spec = importlib.util.spec_from_file_location('clock_r2_presentation_utils', util_path)
    util = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(util)  # IO/table helpers only; no detector or main call.
    io = util.Inputs(repo)
    io.track(util_path)
    out = io.locate(args.output).resolve()
    protected = [repo/x for x in ['experiment_results', 'experiments', 'simulator', 'analysis', 'docs',
        'reports/scientific_reduced_clock_r2_figures_20261031',
        'reports/scientific_reduced_clock_r2_20261030',
        'reports/scientific_reduced_clock_r2_temporal_20261102',
        'reports/scientific_reduced_clock_r2_temporal_cli_20261102']]
    require(out != repo and all(out != p and p not in out.parents and out not in p.parents for p in protected),
            'Saída sobrepõe artefatos ou apresentações protegidos')
    require(not any((out/f).is_symlink() for f in ['figures', 'tables']), 'Saída não pode usar links simbólicos')
    if out.exists() and not args.overwrite:
        require(all(p.name in {'generate.py', 'test_proxy.py'} for p in out.iterdir()),
                'Saídas existentes: escolha outro diretório ou --overwrite')
    require(re.fullmatch('[0-9a-f]{64}', args.checkpoint_sha256), 'SHA256 esperado deve ter 64 caracteres hexadecimais')
    cp = io.read(args.checkpoint, args.checkpoint_sha256)
    require(cp['partition'] == 'TEST', 'Checkpoint deve ser TEST')
    plan = io.read(args.plan, cp['authority']['plan_sha256'])
    io.read(plan['protocol']['path'], plan['protocol']['sha256'])
    for name in CODE:
        io.track(name, plan['runtime_hashes'][name])
    for name in ['inventory.md', 'index.md', 'pending.md']:
        io.track(repo/'reports/scientific_reduced_clock_r2_figures_20261031'/name)
    for name in ['report.md', 'methodology_note.md']:
        io.track(repo/'reports/scientific_reduced_clock_r2_20261030'/name)
    for name in ['docs/proxy_observability.md', 'docs/http_timing_audit.md', 'docs/http_proxy.md']:
        io.track(name)
    entries = {e['id']:e for e in plan['entries'] if e['partition'] == 'TEST'}
    complete = sorted(b for b in {e['block'] for e in entries.values()} if
        {e['scenario'] for e in entries.values() if e['block'] == b} == set(SCENARIOS))
    require(complete == list(range(1, 13)), 'Esperados os 12 trios completos TEST')
    block = complete[0] if args.temporal_block is None else args.temporal_block
    receipts = {}
    for ref in cp['receipts']:
        doc = io.artifact(ref)
        require(doc['entry'] == entries[doc['entry']['id']], 'Recibo fora do plano')
        receipts[doc['entry']['id']] = doc['receipt']
    require(set(receipts) == set(entries), 'Recibos incompletos/duplicados')

    phase_rows, native_rows, log_rows, bin_rows = [], [], [], []
    run_rows, diagnostic, diagnostic_lines, exclusions = [], [], [], []
    selected = {}
    issues = []
    for eid, receipt in sorted(receipts.items()):
        entry = entries[eid]
        base = dict(entry=eid, run_id=receipt['run_id'], block=entry['block'], scenario=entry['scenario'])
        ds = io.locate(receipt['dataset'])
        dm = io.read(ds/'dataset_manifest.json', receipt['dataset_manifest_sha256'])
        require(dm['run_id'] == receipt['run_id'], 'Run do dataset diverge')
        def linked(relative):
            return io.linked(ds, dm['files'], relative)
        status = io.read(linked(dm['run_status']))
        require(status['run_id'] == receipt['run_id'] and status['experiment_id'] == eid
                and status['status'] == 'completed', 'Execução não concluída ou identidade divergente')
        epoch = Decimal(str(status['experiment_start_timestamp']))
        identity = io.read(linked('evidence/proxy/proxy_identity.json'))
        monitor_summary = io.read(linked('evidence/proxy/monitor_summary.json'))
        require(identity['run_id'] == monitor_summary['run_id'] == receipt['run_id'] and
                monitor_summary['container_id'] == identity['id'], 'Identidade do proxy diverge')
        with linked('evidence/proxy/monitor_samples.jsonl').open() as stream:
            samples = [json.loads(line) for line in stream]
        require(all(s['run_id'] == receipt['run_id'] and s['container_id'] == identity['id'] for s in samples),
                'Amostras de outro proxy/run')
        requests = io.csv(linked('raw/service/request_log.csv'))
        clients = {r['request_id']:r for r in requests}
        require(len(clients) == len(requests) and all(r['run_id'] == receipt['run_id'] for r in requests),
                'IDs de cliente duplicados ou de outra execução')
        events = io.csv(linked('raw/attacks/attack_events.csv'))
        require(len(events) == int(entry['scenario'] != 'C16'), 'Quantidade de eventos divergente')
        event = events[0] if events else None
        require(not event or event['run_id'] == receipt['run_id'], 'Evento de outra execução')
        start = float(event['actual_start_seconds']) if event else None
        end = float(event['actual_end_seconds']) if event else 270.
        phases = dict(PRE=(30.,150.), ACTIVE=(150.,end), POST=(end,390.))
        for name, (a,b) in phases.items():
            official = receipt['operational']['phases'][name]
            require(a == float(official['start_seconds']) and b == float(official['bin_end_seconds']),
                    'Limites operacionais divergentes')
        stop = receipt['operational']['scalars']['stop_command_seconds']
        stop = float(stop) if stop is not None else None
        exposure = float(receipt['operational']['exposure_seconds']) if event else 0.
        require(not event or math.isclose(exposure, end-start, abs_tol=1e-9), 'Exposição/evento diverge')
        reads = []
        for s in samples:
            d, z = s['docker'], s['status']
            for source in ['docker','status']:
                require(s[source]['duration_seconds'] >= 0, 'Duração de coleta inválida')
            ddata, zdata = d['data'] if d['success'] else {}, z['data'] if z['success'] else {}
            native = dict(base, sequence=s['monitoring_query_sequence'],
                docker_seconds=d['elapsed_seconds'], docker_epoch=d['timestamp'],
                docker_duration_seconds=d['duration_seconds'], docker_success=d['success'], docker_error=d['error'],
                docker_read=ddata.get('docker_read'), delta_state=ddata.get('delta_state'),
                observed_interval_seconds=ddata.get('observed_interval_seconds'),
                cpu_percent=ddata.get('cpu_percent'), memory_bytes=ddata.get('memory_usage_bytes'),
                memory_mib=ddata['memory_usage_bytes']/MIB if ddata.get('memory_usage_bytes') is not None else None,
                status_seconds=z['elapsed_seconds'], status_epoch=z['timestamp'],
                status_duration_seconds=z['duration_seconds'], status_success=z['success'], status_error=z['error'],
                active_connections=zdata.get('active_connections'), accepted=zdata.get('accepted_connections_total'),
                handled=zdata.get('handled_connections_total'))
            require(z['success'] or native['active_connections'] is None, 'Falha de status virou valor')
            require(ddata.get('delta_state') != 'first_read' or native['cpu_percent'] is None, 'Primeira CPU preenchida')
            reads.append(native)
        for source in ['status','docker']:
            failures = sum(not s[source]['success'] for s in samples)
            require(failures == monitor_summary['source_errors'][source], 'Contagem de erros diverge do summary')
        native_rows.extend(reads)

        with linked('evidence/proxy/proxy_access.log').open() as stream:
            access = [json.loads(line) for line in stream]
        own_logs, ids, reasons = [], Counter(), Counter()
        field_reasons = Counter()
        for line_number, row in enumerate(access, 1):
            rid, log_phase = row.get('request_id',''), row.get('phase','')
            client = clients.get(rid)
            cls = client['traffic_class'] if client else None
            if log_phase in AUXILIARY:
                selection_reason = 'aux_'+log_phase
            elif log_phase:
                selection_reason = 'unknown_log_phase'
            elif not rid:
                selection_reason = 'missing_request_id'
            elif client is None:
                selection_reason = 'unmatched_request_id'
            elif cls not in CLASSES:
                selection_reason = 'unknown_client_class'
            else:
                selection_reason = 'scientific'
                ids[rid] += 1
            ts = log_elapsed(row.get('timestamp'), epoch)
            upstream, upstream_reason = scalar_time(row.get('upstream_time'))
            address = row.get('upstream')
            if upstream_reason == 'valid':
                if address is None or str(address).strip() in {'','-'}:
                    upstream_reason = 'missing_upstream_address'
                elif ',' in address or re.search(r'\s:\s', address):
                    upstream_reason = 'multiple_upstream_addresses'
            upstream_ms = upstream*1000 if upstream_reason == 'valid' else None
            if selection_reason != 'scientific':
                final_reason = selection_reason
            elif ts is None:
                final_reason = 'invalid_log_timestamp'
            elif upstream_reason != 'valid':
                final_reason = 'upstream_'+upstream_reason
            else:
                final_reason = 'valid_scientific_upstream'
            record = dict(base, access_line=line_number, request_id=rid, log_phase=log_phase,
                traffic_class=cls, client_outcome=client.get('outcome') if client else None,
                log_epoch=row.get('timestamp'), log_seconds=ts, operational_phase=phase_for(ts,phases),
                http_status=row.get('status'), upstream_address=address, upstream_status=row.get('upstream_status'),
                raw_upstream_time=row.get('upstream_time'), upstream_time_reason=upstream_reason,
                upstream_ms=upstream_ms if selection_reason == 'scientific' and ts is not None else None,
                selection_reason=selection_reason, final_reason=final_reason)
            for field in ['request_time','connect_time']:
                value, reason = scalar_time(row.get(field))
                record['raw_'+field] = row.get(field)
                record[field+'_seconds'] = value
                record[field+'_reason'] = reason
            for field in ['upstream_time','request_time','connect_time']:
                field_reasons[field, record[field+'_reason']] += 1
            reasons[final_reason] += 1
            own_logs.append(record)
        missing_clients = clients.keys()-ids.keys()
        duplicates = sum(v-1 for v in ids.values())
        require(not missing_clients and not duplicates, 'Associação cliente/access incompleta ou duplicada; investigar sem corrigir congelados')
        require(sum(reasons.values()) == len(access), 'Exclusões de logs não conservam total')
        log_rows.extend(own_logs)
        for reason,count in reasons.items():
            exclusions.append(dict(base, scope='all_access', field='selection', reason=reason, count=count))
        for (field,reason),count in field_reasons.items():
            exclusions.append(dict(base, scope='all_access', field=field, reason=reason, count=count))
        # Emit explicit zero counts too, so absent reasons are not ambiguous.
        for cls in CLASSES:
            subset = [r for r in own_logs if r['selection_reason']=='scientific' and r['traffic_class']==cls]
            counts = Counter(r['final_reason'] for r in subset)
            for reason in ['valid_scientific_upstream','upstream_missing','upstream_marker_no_value',
                    'upstream_multiple_upstreams','upstream_multiple_upstream_addresses','upstream_missing_upstream_address',
                    'upstream_malformed','upstream_negative','upstream_nonfinite','invalid_log_timestamp']:
                exclusions.append(dict(base,scope='scientific_'+cls,field='upstream_time',reason=reason,count=counts[reason]))
        for phase,(a,b) in phases.items():
            pr = dict(base,phase=phase,start_seconds=a,end_seconds=b,phase_duration_seconds=b-a,
                event_start_seconds=start,event_end_seconds=end if event else None,
                stop_command_seconds=stop,offensive_exposure_seconds=exposure,
                offensive_overlap_phase_seconds=max(0.,min(b,end)-max(a,start)) if event else 0.)
            for key,time_key in [('cpu_percent','docker_seconds'),('memory_mib','docker_seconds'),
                                  ('active_connections','status_seconds')]:
                valid = [r for r in reads if a<=r[time_key]<b and r[key] is not None]
                pr[key+'_sample_mean'] = mean([r[key] for r in valid])
                pr[key+'_sample_max'] = max((r[key] for r in valid),default=None)
                pr.update({key+'_'+k:v for k,v in support([r[time_key] for r in valid],a,b).items()})
            cpu = [r for r in reads if a<=r['docker_seconds']<b and r['cpu_percent'] is not None]
            intervals = [r['observed_interval_seconds'] for r in cpu if r['observed_interval_seconds'] is not None]
            pr['cpu_query_interval_min_seconds'] = min(intervals,default=None)
            pr['cpu_query_interval_max_seconds'] = max(intervals,default=None)
            pr['cpu_query_intervals_crossing_phase_start'] = sum(r['observed_interval_seconds'] is not None and
                r['docker_seconds']-r['observed_interval_seconds']<a for r in cpu)
            pr['status_failed_reads'] = sum(a<=r['status_seconds']<b and not r['status_success'] for r in reads)
            pr['docker_failed_reads'] = sum(a<=r['docker_seconds']<b and not r['docker_success'] for r in reads)
            logs_phase = [r for r in own_logs if r['log_seconds'] is not None and a<=r['log_seconds']<b]
            pr['access_records'] = len(logs_phase)
            for tag in sorted(AUXILIARY):
                pr['excluded_'+tag] = sum(r['selection_reason']=='aux_'+tag for r in logs_phase)
            for cls in CLASSES:
                scientific = [r for r in logs_phase if r['selection_reason']=='scientific' and r['traffic_class']==cls]
                valid = [r for r in scientific if r['final_reason']=='valid_scientific_upstream']
                pr['upstream_'+cls+'_mean_ms'] = mean([r['upstream_ms'] for r in valid])
                pr['upstream_'+cls+'_scientific_records'] = len(scientific)
                pr['upstream_'+cls+'_valid'] = len(valid)
                pr['upstream_'+cls+'_unusable'] = len(scientific)-len(valid)
                pr.update({'upstream_'+cls+'_'+k:v for k,v in support([r['log_seconds'] for r in valid],a,b).items()})
                for reason in ['missing','marker_no_value','multiple_upstreams','multiple_upstream_addresses',
                               'missing_upstream_address','malformed','negative','nonfinite']:
                    pr['upstream_'+cls+'_excluded_'+reason] = sum(r['upstream_time_reason']==reason for r in scientific)
                require(pr['upstream_'+cls+'_valid']+pr['upstream_'+cls+'_unusable']==len(scientific), 'Suporte upstream não conserva total')
            phase_rows.append(pr)
        rr = dict(base,monitor_records=len(samples),status_failures=sum(not r['status_success'] for r in reads),
            cpu_missing=sum(r['cpu_percent'] is None for r in reads),memory_missing=sum(r['memory_mib'] is None for r in reads),
            access_records=len(access),scientific_records=sum(r['selection_reason']=='scientific' for r in own_logs),
            valid_scientific_upstream=reasons['valid_scientific_upstream'],
            excluded_monitoring=reasons['aux_monitoring'],excluded_setup=reasons['aux_setup'],excluded_capture_audit=reasons['aux_capture_audit'],
            unmatched_client_ids=len(missing_clients),duplicate_scientific_ids=duplicates,
            log_ids_without_client=sum(r['selection_reason']=='unmatched_request_id' for r in own_logs),
            scientific_before_30=sum(r['selection_reason']=='scientific' and r['log_seconds'] is not None and r['log_seconds']<30 for r in own_logs),
            scientific_from_390=sum(r['selection_reason']=='scientific' and r['log_seconds'] is not None and r['log_seconds']>=390 for r in own_logs),
            event_start_seconds=start,event_end_seconds=end if event else None,stop_command_seconds=stop,
            offensive_exposure_seconds=exposure)
        for cls in CLASSES:
            own=[r for r in own_logs if r['selection_reason']=='scientific' and r['traffic_class']==cls]
            rr['scientific_'+cls+'_records']=len(own)
            rr['valid_'+cls+'_upstream']=sum(r['final_reason']=='valid_scientific_upstream' for r in own)
        run_rows.append(rr)

        config = linked('metadata/topology/proxy/proxy_config.conf').read_text()
        io.track(linked('evidence/proxy/nginx_build.txt'))
        match = re.search(r'worker_connections\s+(\d+)\s*;',config)
        worker = re.search(r'worker_processes\s+(\d+)\s*;',config)
        diag = dict(base,configured_worker_connections=int(match[1]) if match else None,
            configured_workers=int(worker[1]) if worker else None,
            upstream_keepalive=int(re.search(r'\bkeepalive\s+(\d+)\s*;',config)[1]),
            upstream_tries=int(re.search(r'proxy_next_upstream_tries\s+(\d+)\s*;',config)[1]),
            worker_rlimit_nofile_directive=bool(re.search(r'\bworker_rlimit_nofile\b',config)),
            proxy_next_upstream_off=bool(re.search(r'proxy_next_upstream\s+off;',config)),
            observed_active_max_all=max((r['active_connections'] for r in reads if r['active_connections'] is not None),default=None),
            observed_active_max_30_390=max((r['active_connections'] for r in reads if 30<=r['status_seconds']<390 and r['active_connections'] is not None),default=None),
            observed_accept_minus_handled_max=max((r['accepted']-r['handled'] for r in reads if r['accepted'] is not None),default=None))
        for filename in ['proxy_error.log','container_output.log']:
            lines = linked('evidence/proxy/'+filename).read_text().splitlines()
            diag[filename+'_lines'] = len(lines)
            diag[filename+'_limit_warnings'] = sum('worker_connections exceed open file resource limit' in l for l in lines)
            diag[filename+'_exhaustion_messages'] = sum(bool(EXHAUSTION.search(l)) for l in lines)
            for n,line in enumerate(lines,1):
                limits = re.search(r'getrlimit\(RLIMIT_NOFILE\): (\d+):(\d+)',line)
                if limits:
                    diag['startup_nofile_soft'],diag['startup_nofile_hard'] = map(int,limits.groups())
                if '[warn]' in line or '[error]' in line or '[crit]' in line or '[alert]' in line or limits or EXHAUSTION.search(line):
                    diagnostic_lines.append(dict(base,file=filename,line_number=n,text=line,
                        explicit_exhaustion=bool(EXHAUSTION.search(line))))
        diagnostic.append(diag)
        if entry['block']==block:
            selected[entry['scenario']] = dict(reads=reads,event=event,start=start,end=end,stop=stop)
            for cls in CLASSES:
                for a in range(30,390,5):
                    own = [r for r in own_logs if r['selection_reason']=='scientific' and r['traffic_class']==cls and
                           r['log_seconds'] is not None and a<=r['log_seconds']<a+5]
                    valid = [r for r in own if r['final_reason']=='valid_scientific_upstream']
                    bin_rows.append(dict(base,traffic_class=cls,start_seconds=a,end_seconds=a+5,
                        scientific_records=len(own),valid_upstream=len(valid),excluded_upstream=len(own)-len(valid),
                        mean_upstream_ms=mean([r['upstream_ms'] for r in valid])))

    require(len(phase_rows)==108 and len(selected)==3, 'Fases/seleção temporal incompletas')
    # Directed reconciliation with the existing proxy inventory, not a historical replay.
    require(sum(r['status_failures'] for r in run_rows)==119, 'Falhas stub_status divergem do inventário anterior')
    require(sum(r['cpu_missing'] for r in run_rows)==36, 'Primeiras leituras sem delta divergem do inventário')
    if args.overwrite and (out/'provenance.json').exists():
        prior=json.loads((out/'provenance.json').read_text())
        for relative in prior.get('outputs',{}):
            path=(out/relative).resolve()
            require(out in path.parents and (path.parent in {(out/'figures').resolve(),(out/'tables').resolve()}
                or path.parent==out and path.name in {'index.md','methodology.md','nginx_limits.md'}),
                'Saída anterior fora do diretório de apresentação')
        for relative in prior.get('outputs',{}):
            (out/relative).unlink(missing_ok=True)
    out.mkdir(parents=True,exist_ok=True)
    (out/'tables').mkdir(exist_ok=True);(out/'figures').mkdir(exist_ok=True)
    def table(name,rows): util.table(out,name,rows)
    table('per_run_phase',phase_rows);table('native_monitor_reads',native_rows)
    table('access_association',log_rows);table('upstream_bins_5s',bin_rows)
    table('per_run_support',run_rows);table('exclusions_by_reason',exclusions)
    table('nginx_limits_by_run',diagnostic);table('nginx_documentary_lines',diagnostic_lines)
    summaries = []
    for phase in PHASES:
        for scenario in SCENARIOS:
            for metric in ['cpu_percent_sample_mean','memory_mib_sample_mean','upstream_benign_mean_ms']:
                values = [r[metric] for r in phase_rows if r['phase']==phase and r['scenario']==scenario and r[metric] is not None]
                summaries.append(dict(phase=phase,scenario=scenario,metric=metric,n_runs=len(values),
                    mean_of_run_means=mean(values),median_of_run_means=float(np.median(values)) if values else None,
                    min_run_mean=min(values,default=None),max_run_mean=max(values,default=None)))
    table('descriptive_run_summaries',summaries)
    plots(out,selected,block,bin_rows,phase_rows)
    write_docs(out,block,args,run_rows,phase_rows,summaries,diagnostic,issues)
    table('sources',[dict(path=str(Path(p).relative_to(repo)) if repo in Path(p).parents else p,sha256=h)
        for p,h in sorted(io.sources.items())])
    command = shlex.join([sys.executable,'-B',str(Path(__file__).resolve()),'--repo',str(repo),
        '--plan',str(args.plan),'--checkpoint',str(args.checkpoint),'--checkpoint-sha256',args.checkpoint_sha256,
        '--temporal-block',str(block),'--output',str(out)] + (['--overwrite'] if args.overwrite else []))
    provenance = dict(checkpoint_sha256=args.checkpoint_sha256,plan_sha256=cp['authority']['plan_sha256'],
        command=command,temporal_block=block,selection_rule='Menor bloco completo independente dos valores' if args.temporal_block is None else 'Bloco explicitamente escolhido pela CLI',
        comparison_blocks=list(range(1,13)),source_files=len(io.sources),python=platform.python_version(),
        matplotlib=matplotlib.__version__,numpy=np.__version__,generator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        scientific_runtime_imported=False,new_inferential_metrics=False,issues=issues,
        transformations=dict(memory='bytes / 2**20',cpu='média amostral por timestamp próprio Docker; não ponderada',
            upstream='ID dentro do run; exclusão auxiliar e campos não escalares; segundos × 1000; média por conclusão/log na fase',
            temporal='bins upstream de 5 s; recursos nativos; lacunas >1.5 s interrompem linhas; NaNs preservados',
            descriptive_summary='média/mediana/mínimo/máximo das 12 médias por execução, sem pooling, IC ou teste',
            support='ocupação de bins globais de 1 s tocados pela fase e distância máxima entre pontos incluindo bordas, não cobertura contínua'),
        outputs={str(p.relative_to(out)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(out.rglob('*')) if p.is_file() and (p.parent.name in {'tables','figures'} or p.name in {'index.md','methodology.md','nginx_limits.md'})})
    (out/'provenance.json').write_text(json.dumps(provenance,indent=2,ensure_ascii=False)+'\n')
    (out/'reproduce.sh').write_text('#!/bin/sh\n'+command+'\n')
    print(json.dumps(dict(runs=len(run_rows),phases=len(phase_rows),status_failures=119,cpu_first_missing=36,
        access_records=sum(r['access_records'] for r in run_rows),output=str(out)),ensure_ascii=False))


def plots(out,selected,block,bins,phases):
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'pdf.fonttype':42,'ps.fonttype':42,
        'axes.spines.top':False,'axes.spines.right':False,'path.simplify':False})
    def save(fig,name):
        for ext in ['pdf','png']:fig.savefig(out/'figures'/(name+'.'+ext),dpi=300,facecolor='white')
        plt.close(fig)
    fig,axs=plt.subplots(4,3,figsize=(11.69,8.27),sharex=True,sharey='row')
    for j,scenario in enumerate(SCENARIOS):
        d=selected[scenario]
        for i,key,time_key,color in [(0,'cpu_percent','docker_seconds',COLORS['cpu']),
                (1,'memory_mib','docker_seconds',COLORS['memory']),(2,'active_connections','status_seconds',COLORS['status'])]:
            reads=[r for r in d['reads'] if 30<=r[time_key]<390]
            native_line(axs[i,j],[r[time_key] for r in reads],[r[key] for r in reads],color=color)
        for cls,label in [('benign','Legítimas'),('attack','Ofensivas')]:
            own=[r for r in bins if r['scenario']==scenario and r['traffic_class']==cls]
            axs[3,j].plot([(r['start_seconds']+r['end_seconds'])/2 for r in own],
                [r['mean_upstream_ms'] if r['mean_upstream_ms'] is not None else np.nan for r in own],
                color=COLORS[cls],lw=.9,marker='.',ms=2,label=label)
        for ax in axs[:,j]:
            ax.set_xlim(30,390);ax.set_xticks([30,90,150,210,270,330,390]);ax.grid(axis='y',alpha=.2)
            ax.tick_params(labelsize=8)
            if d['event']:
                ax.axvspan(d['start'],d['end'],color='#E69F00',alpha=.08)
                ax.axvline(d['start'],ls='--',color='#333333',lw=.8)
                ax.axvline(d['end'],color='#333333',lw=.8)
            if d['stop'] is not None:ax.axvline(d['stop'],color='#CC79A7',ls=':',lw=1.2)
        axs[0,j].set_title(scenario+(' · sem evento' if not d['event'] else ''))
        axs[3,j].set_xlabel('Tempo desde a origem (s)')
    for i,label in enumerate(['CPU Docker (%)\ndelta de contadores','Memória bruta (MiB)','Conexões ativas\nstub_status','Upstream (ms)\nmédia por conclusão, 5 s']):axs[i,0].set_ylabel(label,fontsize=9)
    axs[3,0].legend(fontsize=8,loc='upper left')
    fig.suptitle(f'Proxy NGINX · exemplo ilustrativo B{block:02}',fontsize=15,y=.98)
    fig.text(.5,.025,'Recursos/status: timestamps próprios, leituras nativas; falhas e lacunas >1,5 s interrompem linhas.\n'
        'Faixa: emissão real; tracejado: início; contínuo: fim; magenta: comando. Exemplo não substitui as 12 execuções.',ha='center',fontsize=8)
    fig.subplots_adjust(left=.1,right=.98,bottom=.13,top=.91,hspace=.3,wspace=.18)
    save(fig,f'P_proxy_temporal_B{block:02}')
    fig,axs=plt.subplots(3,3,figsize=(11.69,8.27),sharey='row')
    metrics=['cpu_percent_sample_mean','memory_mib_sample_mean','upstream_benign_mean_ms']
    labels=['CPU média amostral (%)','Memória média amostral (MiB)','Upstream legítimo médio (ms)']
    colors=plt.get_cmap('tab20')(np.linspace(0,.95,12))
    for i,(metric,label) in enumerate(zip(metrics,labels)):
        for j,phase in enumerate(PHASES):
            ax=axs[i,j]
            for b in range(1,13):
                own=[next(r for r in phases if r['block']==b and r['scenario']==s and r['phase']==phase) for s in SCENARIOS]
                x=np.arange(3)+(b-6.5)*.018
                # Each point is one run, not a raw monitoring sample.
                ax.plot(x,[r[metric] if r[metric] is not None else np.nan for r in own],
                    'o-',color=colors[b-1],ms=3.5,lw=.7,alpha=.85)
            ax.set_xticks(range(3),SCENARIOS);ax.set_xlim(-.2,2.2);ax.grid(axis='y',alpha=.2)
            if i==0:ax.set_title(phase)
            if j==0:ax.set_ylabel(label,fontsize=9)
    handles=[Line2D([],[],color=colors[b-1],marker='o',lw=.8,label=f'B{b:02}') for b in range(1,13)]
    fig.legend(handles=handles,loc='lower center',bbox_to_anchor=(.5,.055),ncol=12,frameon=False,fontsize=8)
    fig.suptitle('Proxy NGINX · valores individuais nas 12 execuções por cenário',fontsize=14,y=.98)
    fig.text(.5,.018,'PRE [30,150); ACTIVE [150,fim real); POST [fim real,390). Em C16: fronteira operacional em 270 s.\n'
        'Recursos: médias amostrais; upstream legítimo: conclusões/logs na fase. Linhas ligam o mesmo bloco; sem IC ou teste.',ha='center',fontsize=8)
    fig.subplots_adjust(left=.1,right=.98,bottom=.17,top=.9,hspace=.3,wspace=.18)
    save(fig,'Q_proxy_individual_runs_phases')


def write_docs(out,block,args,runs,phases,summaries,diagnostic,issues):
    fmt=lambda x: 'ausente' if x is None else f'{x:.3f}'.replace('.',',')
    lines=['# Proxy NGINX — apresentação descritiva clock r2','',
        f'36 execuções TEST, 12 blocos por cenário. Temporal: B{block:02}. Somente artefatos existentes; '
        'novas agregações estritamente descritivas, sem ICs ou testes inferenciais. Nenhum detector foi executado.','',
        '| Figura | Finalidade e legenda sugerida |','|---|---|',
        f'| [Temporal PDF](figures/P_proxy_temporal_B{block:02}.pdf) · [PNG](figures/P_proxy_temporal_B{block:02}.png) | '
        f'Exemplo ilustrativo B{block:02}, uma coluna por cenário: CPU Docker, memória bruta, conexões ativas e média upstream '
        'por conclusão/log em bins de 5 s, separando legítimos/ofensivos. Escalas comuns por variável; leituras nativas com lacunas. '
        'Faixa e linhas marcam emissão real e comando quando existem. Não substitui as 12 repetições. |',
        '| [Individuais PDF](figures/Q_proxy_individual_runs_phases.pdf) · [PNG](figures/Q_proxy_individual_runs_phases.png) | '
        'Cada ponto é uma média de uma execução/fase; linhas unem cenários do mesmo bloco. CPU e memória usam médias amostrais; '
        'upstream legítimo usa conclusões/logs na fase, não coorte por início. PRE/ACTIVE/POST separados; sem pooling, IC ou teste. |','',
        '## Resumo descritivo','',
        'A tabela abaixo mostra a mediana das 12 médias por execução, com mínimo–máximo entre essas médias. '
        'Não representa percentis das requisições ou limites de confiança.','',
        '| Fase | Cenário | CPU (%) | Memória (MiB) | Upstream legítimo (ms) |','|---|---|---:|---:|---:|']
    for phase in PHASES:
        for scenario in SCENARIOS:
            own=[r for r in summaries if r['phase']==phase and r['scenario']==scenario]
            cells=[fmt(r['median_of_run_means'])+' ['+fmt(r['min_run_mean'])+'; '+fmt(r['max_run_mean'])+']' for r in own]
            lines.append('| '+phase+' | '+scenario+' | '+' | '.join(cells)+' |')
    totals={k:sum(r[k] for r in runs) for k in ['monitor_records','status_failures','cpu_missing','access_records',
        'scientific_records','valid_scientific_upstream','excluded_monitoring','excluded_setup','excluded_capture_audit']}
    lines+=['',f"Suporte: {totals['monitor_records']} leituras pareadas, {totals['status_failures']} falhas de parsing de status "
        f"e {totals['cpu_missing']} primeiras CPU sem delta, preservadas como ausentes. "
        f"Access: {totals['access_records']} linhas; {totals['scientific_records']} científicas, "
        f"das quais {totals['valid_scientific_upstream']} com upstream escalar utilizável. "
        f"Excluídas como auxiliares: monitoring={totals['excluded_monitoring']}, setup={totals['excluded_setup']}, "
        f"capture_audit={totals['excluded_capture_audit']}. Contagens completas incluem PRE-aquecimento e cauda; "
        'as figuras e fases restringem-se a [30,390).','',
        '| Classe científica, em todo o arquivo | Tempos upstream válidos | Não utilizáveis |',
        '|---|---:|---:|']
    for cls,label in [('benign','Legítima'),('attack','Ofensiva')]:
        count=sum(r['scientific_'+cls+'_records'] for r in runs)
        valid=sum(r['valid_'+cls+'_upstream'] for r in runs)
        lines.append(f'| {label} | {valid} | {count-valid} |')
    lines+=['',
        'Os motivos de ausência, marcador, upstream múltiplo, endereço ausente/múltiplo, texto malformado, '
        'negativo e não finito têm contagem explícita por run/classe na tabela de exclusões, inclusive zeros. '
        'As 14.094 consultas monitoring sem upstream não entram na população científica.','',
        'Os valores contextualizam as execuções observadas sob suas exposições reais. Não identificam capacidade máxima, '
        'saturação, overhead de monitoramento ou causa do comprometimento. As médias de E16 descrevem exposições '
        'variáveis sob a política de proteção, não dose igual.','',
        '## Tabelas, definições e reprodução','',
        '- [Por execução/fase](tables/per_run_phase.csv): médias, n válido, ocupação de bins, lacunas e tempos não utilizáveis por classe/motivo.',
        '- [Resumo entre execuções](tables/descriptive_run_summaries.csv): cada run tem peso igual; não há pooling de amostras.',
        '- [Leituras nativas](tables/native_monitor_reads.csv): todos os instantes, flags de sucesso, CPU nula inicial e falhas de status.',
        '- [Access/IDs](tables/access_association.csv): linha do log, ID, classe do cliente, timestamp, tempos brutos e motivos de exclusão.',
        '- [Suporte por execução](tables/per_run_support.csv) e [exclusões](tables/exclusions_by_reason.csv).',
        '- [Bins ilustrativos de 5 s](tables/upstream_bins_5s.csv): n total científico, n válido, excluídos e média por classe.',
        '- [Nota metodológica](methodology.md), [diagnóstico NGINX](nginx_limits.md), [fontes/hashes](tables/sources.csv), [proveniência](provenance.json).','',
        'Reprodução na raiz do repositório: ver [reproduce.sh](reproduce.sh), usando apenas Python/NumPy/Matplotlib locais. '
        'O SHA256 esperado do TEST é obrigatório. `--temporal-block` seleciona outro bloco; as comparações continuam '
        'incluindo os 12. Sem a opção, escolhe-se o menor bloco completo sem olhar valores. Saídas existentes exigem '
        '`--overwrite`; artefatos congelados e apresentações anteriores são protegidos.','',
        'Pendências: diagramação no TCC; não há evidência para determinar a ocupação de descritores por worker, picos entre '
        'amostras, efeito causal de componentes ou overhead isolado do monitor. A cobertura de bins não é cobertura física contínua.','']
    example=shlex.join(['.venv/bin/python','-B','reports/scientific_reduced_clock_r2_proxy_20261102/generate.py',
        '--repo','.', '--plan',str(args.plan),'--checkpoint',str(args.checkpoint),
        '--checkpoint-sha256',args.checkpoint_sha256,'--temporal-block',str(block),
        '--output','reports/proxy_clock_r2_reproduzido'])
    lines+=['## Comando exato para uma nova saída','', 'Na raiz do repositório:', '', '```bash',example,'```','',
        'Conferências desta entrega: [verification.json](verification.json) e [inspeção visual](visual_review.md). '
        'O gerador não certifica automaticamente a inspeção de figuras futuras.','']
    (out/'index.md').write_text('\n'.join(lines))
    (out/'methodology.md').write_text('''# Definições metodológicas — proxy

**CPU.** `simulator/proxy_monitor.py::resources` lê a convenção Docker: delta de uso da CPU do container / delta de CPU do host × CPUs online × 100. A primeira leitura não tem delta e permanece nula. As demais são os valores preservados, sem recalcular contadores. Pode exceder 100%. `docker_read` guarda o timestamp do daemon; `observed_interval_seconds` mede distância monotônica entre começos das consultas bem-sucedidas, aproximando o intervalo do daemon, com incerteza de chamada. Os contadores crus e extremos físicos completos não estão preservados. Usa-se **média amostral**, não ponderação temporal presumida. Amostras são atribuídas pelo timestamp da consulta; um delta pode atravessar a fronteira de fase, contado em `cpu_query_intervals_crossing_phase_start`, sem repartição inventada.

**Memória.** `memory_usage_bytes` é uso bruto de memória do cgroup, incluindo cache contabilizado pelo Docker; não é RSS ou memória sem cache. Conversão somente para apresentação: bytes / 2²⁰ = MiB. Média aritmética das leituras válidas atribuídas à fase, igualmente não ponderada no tempo.

**Conexões.** `status.data.active_connections` é o gauge de conexões ativas de clientes do stub_status no instante da consulta, incluindo consultas do próprio monitor. Não mede fila de legítimos nem total de sockets/FDs do worker; sockets upstream também consomem recursos. Falhas `invalid stub_status response` permanecem `success=False`, valor vazio; não se recupera corpo nem se transforma falha em zero. A série não conecta NaNs nem espaçamentos maiores que 1,5 s (1,5 vezes a cadência nominal de 1 s). As leituras nativas são pontos ligados apenas entre observações vizinhas sem essa lacuna; não são interpoladas ou reamostradas.

**Tempos e origem.** Docker e status usam seus próprios `elapsed_seconds`, registrados imediatamente antes da chamada, desde a âncora monotônica do experimento, e guardam também epoch e duração da coleta. Não se usa o timestamp externo da linha para ambos. Access usa `$msec` no instante de conclusão/escrita do log, subtraindo a âncora epoch `run_status.experiment_start_timestamp` com Decimal antes da renderização. A resolução do log é de milissegundos; relógio de parede pode divergir do monotônico, sem medição contínua de drift. O instante de resposta da consulta não antecede o fim da coleta. Nada é convertido em disponibilidade de detector.

**Upstream.** A configuração preservada vincula `upstream_time` a `$upstream_response_time`, em segundos, apresentado em ms (×1000). É o intervalo da tentativa upstream até sua finalização, incluindo conexão quando criada, espera/processamento/recepção. Não é RTT puro proxy–vítima, nem somente tempo de CPU do serviço. `request_time` e `connect_time` são guardados e classificados separadamente; não se subtraem para estimar overhead puro.

**IDs e exclusões.** A associação usa exclusivamente o request_id do CSV de clientes do mesmo run. A classe vem de `traffic_class`, nunca da fase nominal ou do IP. São excluídos antes das estatísticas científicas os registros com headers `phase=monitoring`, `setup`, `capture_audit`, fases desconhecidas, IDs vazios/não associados e classes não reconhecidas. Cada linha tem um motivo final exclusivo; o ledger também guarda os motivos de parsing por campo, que não devem ser somados aos motivos finais como se fossem linhas adicionais.

Aceita-se upstream escalar, finito, não negativo, com endereço upstream presente e único. Zero numérico é válido; célula vazia/None, marcador `-`, múltiplos tempos ou endereços, texto malformado, negativo e não finito recebem categorias distintas. Não se soma nem escolhe uma tentativa de uma lista de upstreams. Campos auxiliares request_time/connect_time têm parsing independente e não substituem upstream_time ausente. Não se excluem falhas/abortos HTTP quando há associação científica e tempo upstream válido.

**Populações e fases.** Fases operacionais já definidas em `scientific/evaluation.py::impact`: PRE [30,150), ACTIVE [150,e), POST [e,390), sendo e o fim real de emissão; em C16 usa-se 270 s como fronteira operacional, sem inventar evento ofensivo. A pequena diferença entre início real s e 150 s permanece na tabela. Recursos usam os instantes registrados dentro da fase. Upstream usa conclusões/logs na fase, incluindo requisições iniciadas antes. Isso difere da coorte por início usada em indicadores operacionais de serviço da campanha. A emissão é [s,e), não o período de drenagem ou o comando de parada.

**Suporte.** As tabelas informam n válido, número de bins globais de 1 s tocados pela fase, bins com leitura válida e bins vazios, e a maior distância entre pontos válidos incluindo bordas. Fases fracionárias podem tocar bins parciais. Ocupação de bins não comprova observação uniforme, integral ou contínua. Para upstream, bins ocupados descrevem conclusões utilizáveis, não garantem integridade temporal do coletor. Linhas auxiliares e requisições científicas fora de [30,390) ficam no ledger e são excluídas da comparação. Bins de 5 s sem tempos válidos permanecem vazios, inclusive toda a classe ofensiva C16. Não se conecta um bin vazio.

**Comparação.** Cada ponto é uma execução/fase; as três colunas representam PRE/ACTIVE/POST. As linhas ligam o mesmo bloco entre cenários. Resumos dão média, mediana, mínimo e máximo das 12 médias por execução; não agregam todas as amostras como réplicas independentes. Não há novos ICs, testes ou efeitos causais estimados. As leituras incluem o próprio monitor; não existe contrafactual sem monitor para isolar seu overhead.
''')
    warnings = sum(r['proxy_error.log_limit_warnings'] for r in diagnostic)
    exhaustion = sum(r['proxy_error.log_exhaustion_messages']+r['container_output.log_exhaustion_messages'] for r in diagnostic)
    max_active = max(r['observed_active_max_30_390'] for r in diagnostic)
    soft = sorted({r.get('startup_nofile_soft') for r in diagnostic},key=str)
    hard = sorted({r.get('startup_nofile_hard') for r in diagnostic},key=str)
    (out/'nginx_limits.md').write_text(f'''# Aviso de limite de conexões — diagnóstico documental

Conferência somente offline dos 36 datasets vinculados ao checkpoint TEST, sem consultar limites atuais do host/container ou alterar a configuração histórica.

| Dimensão | Evidência e limite da interpretação |
|---|---|
| Configuração | Um worker e `worker_connections 4096`; keepalive upstream 32; retries off/uma tentativa; sem diretiva `worker_rlimit_nofile` nos arquivos preservados. Conferência por run em [nginx_limits_by_run.csv](tables/nginx_limits_by_run.csv). |
| Limite comprovado na inicialização | Logs `getrlimit(RLIMIT_NOFILE)` registram soft={soft}, hard={hard}. O aviso compara 4096 com soft=1024. Trata-se do processo de inicialização do NGINX; não é leitura contínua de `/proc/<worker>/limits` ou do uso de FDs de cada worker. Sem diretiva de alteração, a herança é compatível com esse soft, mas a evidência não comprova o limite de cada worker durante toda a campanha. |
| Uso observado | Máximo amostrado de conexões ativas em [30,390): **{max_active}**. Esse gauge é de conexões de clientes do stub_status, inclui monitoring e não conta todos os descritores/upstreams. Não se divide seu valor por 1024/4096 para obter utilização de FDs ou capacidade. |
| Esgotamento explícito | {exhaustion} mensagens encontradas nos error logs e container outputs para os padrões documentados abaixo. Ausência de correspondência não comprova ausência de gargalo, picos, falhas não registradas ou limitação por outro recurso. |

Foram encontradas {warnings} linhas do aviso nos error logs (config test e inicialização podem emitir mensagens semelhantes); os container outputs contêm cópias/avisos adicionais e não devem ser somados como incidentes distintos. As linhas e posições preservadas estão em [nginx_documentary_lines.csv](tables/nginx_documentary_lines.csv). Há também mensagens de ciclo de vida; não são falhas HTTP.

A busca registrou `worker_connections [are] not enough`, `too many open files`, EMFILE/ENFILE, `cannot allocate memory`, `accept/accept4() ... failed` e `socket() ... failed`, com expressão exata no gerador. Outros erros/warnings explícitos são preservados no ledger documental. Os access logs mantêm status HTTP em seu ledger, mas status de erro por si só não identifica esgotamento de FDs.

`worker_connections` é um teto configurado de conexões do worker, abrangendo clientes e conexões com servidores upstream. Não equivale ao número de clientes atendíveis: sockets backend/keepalive, descritores de logs e outros usos competem com o limite de arquivos. Não existe nesta evidência uma série de FDs abertos, contagem completa dos sockets upstream, backlog, perdas antes do NGINX ou pico contínuo. O stub_status é amostrado aproximadamente a cada segundo e tem 119 falhas de parsing preservadas; o pico observado é apenas um valor registrado, não o pico real garantido.

A CPU observada e a busca sem mensagens explícitas não demonstram ausência de gargalo. Tampouco o aviso isolado demonstra saturação ou que o comprometimento do serviço foi causado pelo proxy. Não se estima capacidade máxima, overhead isolado de monitoramento ou efeito causal de configuração.
''')


if __name__=='__main__':
    try:
        main()
    except (ValueError,OSError,KeyError) as exc:
        print('Erro: '+str(exc),file=sys.stderr)
        sys.exit(2)
