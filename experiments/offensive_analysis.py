"""Read-only offensive characterization; no collection, detectors or calibration."""
import argparse
from collections import Counter
import csv
import hashlib
import json
import math
from pathlib import Path
import subprocess

from experiments.exploratory_analysis import Reader, describe as existing_describe
from experiments.export_dataset import placement
from experiments.validate_dataset import validate_dataset
from simulator.diagnostics import computational_state
from simulator.source_aggregate import identified_admission_errors

VERSION = 'offensive-characterization-v1'


def describe(values):
    result=existing_describe(values)
    result['median']=result['p50']
    result['max']=result['maximum']
    return result


def phase(t, start, end):
    return 'pre' if t < start else 'attack' if t < end else 'post'


def http_metrics(requests, start, end, nominal):
    starts = [r for r in requests if start <= float(r['elapsed_seconds']) < end]
    completed = [r for r in requests if r.get('end_elapsed_seconds') not in ('', None)]
    return dict(starts_total=len(requests), starts_in_window=len(starts), completions=len(completed),
        incomplete=len(requests)-len(completed), nominal_rps=nominal, denominator_seconds=end-start,
        realized_start_rps=len(starts)/(end-start), realized_minus_nominal=len(starts)/(end-start)-nominal,
        status_codes=dict(Counter(str(r['http_status']) for r in completed if r.get('http_status'))),
        outcomes=dict(Counter(r['outcome'] for r in requests)),
        timeouts=sum('Timeout' in (r.get('error_type') or '') for r in completed),
        connection_errors=sum('Connection' in (r.get('error_type') or '') for r in completed),
        duration_ms=describe(float(r['duration_ms']) for r in completed if r.get('duration_ms') not in ('',None)),
        duration_basis='known completions only; not imputed for censored attempts',
        completions_after_end=sum(float(r['end_elapsed_seconds'])>=end for r in completed),
        last_start=max((float(r['elapsed_seconds']) for r in requests),default=None),
        last_completion=max((float(r['end_elapsed_seconds']) for r in completed),default=None))


def state_before(events, at, complete):
    state = computational_state(events, math.nextafter(at, -math.inf), observation_complete=complete)
    if not complete or state['errors']:
        return dict(status='unknown', counts=None, errors=state['errors'])
    return dict(status='observed', counts=state['counts'], errors=[])


def cadence(samples, phases):
    times = sorted(samples)
    gaps = [b-a for a,b in zip(times,times[1:])]
    return dict(samples=len(times), intervals_seconds=describe(gaps),
        gaps_over_1s=[dict(start=a,end=b,seconds=b-a) for a,b in zip(times,times[1:]) if b-a>1],
        phase_samples={name:sum(a<=t<b for t in times) for name,(a,b) in phases.items()},
        interpolation=False)


def characterize(config, requests, journal, events, metrics, raw_cpu, origin, clock_ok, writer):
    a=config['attack']; S=a['start_seconds']; E=S+a['duration_seconds']; T=config['duration_seconds']
    phases={'pre':[0,S], 'attack':[S,E], 'post':[E,T]}
    limits=[]
    if not clock_ok: limits.append('Victim/global clock comparison unavailable; computational global timeline unknown.')
    closures=[e for e in events if e['kind']=='computation_observation_closed']
    seen=Counter((e.get('operation_id'),e['kind']) for e in events if e.get('operation_id'))
    duplicates=[str(k) for k,n in seen.items() if n>1]
    sequence_ok=[e.get('sequence') for e in events]==list(range(1,len(events)+1))
    complete=bool(writer and writer.get('complete') and writer.get('observation_complete') and
        writer.get('written')==len(events) and len(closures)==1 and closures[0].get('observation_complete') and not duplicates and sequence_ok)
    if not complete: limits.append('Computational observation incomplete; absence of residual work cannot be established.')
    if closures and computational_state(events, closures[0]['at'], observation_complete=complete)['errors']:
        complete=False
        limits.append('Missing or inconsistent computational transitions; state unknown.')
    groups={}
    for cls,generator in [('benign','normal'),('attack','attack')]:
        own=[r for r in requests if r['generator']==generator]
        settings=config['normal_traffic'] if generator=='normal' else a
        nominal=settings['rate']*settings['clients' if generator=='normal' else 'attackers']
        groups[cls]=http_metrics(own,0 if cls=='benign' else S,T if cls=='benign' else E,nominal)
        groups[cls]['phases']={name:http_metrics([r for r in own if lo<=float(r['elapsed_seconds'])<hi],lo,hi,nominal if cls=='benign' or name=='attack' else 0) for name,(lo,hi) in phases.items() if hi>lo}
    attack_requests=[r for r in requests if r['generator']=='attack']
    violations=[r['request_id'] for r in attack_requests if not S<=float(r['elapsed_seconds'])<E]
    lifecycle=identified_admission_errors(journal)
    emission=dict(events=dict(Counter(e['kind'] for e in journal)),
        resolutions=dict(Counter(e['payload']['decision'] for e in journal if e['kind']=='task_resolution')),
        reconciliation_errors=lifecycle, outside_window=violations)
    per_source={source:dict(Counter(e['kind'] for e in journal if e['source_id']==source)) for source in sorted({e['source_id'] for e in journal})}
    # Worker timestamps are compared to global time only after clock certification.
    work=[e for e in events if e['kind']=='work_completed' and e.get('traffic_class')=='attack']
    opmap={}
    for e in events:
        if e.get('operation_id'): opmap.setdefault(e['operation_id'],{})[e['kind']]=e
    request_map={r['request_id']:r for r in requests}
    mismatches=[]; matched=set()
    for op in opmap.values():
        submitted=op.get('work_submitted')
        if not submitted or not submitted.get('request_id'): continue
        rid=submitted['request_id']; request=request_map.get(rid)
        if request is None or any(submitted.get(k)!=request.get(k) for k in ('run_id','event_id','traffic_class')):
            mismatches.append(rid)
        else: matched.add(rid)
    final_state=state_before(events,math.nextafter(closures[0]['at'],math.inf),complete) if closures else dict(status='unknown',counts=None)
    at_E=state_before(events,origin+E,complete) if clock_ok else dict(status='unknown',counts=None)
    last=max((e['work_finished_at']-origin for e in work),default=None) if clock_ok else None
    residual=dict(state_at_E=at_E, final_state=final_state,
        completions_after_E=sum(e['work_finished_at']>=origin+E for e in work) if clock_ok else None,
        last_observed_completion=last, last_completion_minus_E=last-E if last is not None else None,
        drainage='not_established: absence of later ingress requires external proof')
    computational={}
    for cls in ('benign','attack','unknown'):
        own=[op for op in opmap.values() if next(iter(op.values())).get('traffic_class','unknown')==cls]
        computational[cls]=dict(events=dict(Counter(e['kind'] for op in own for e in op.values())),
            wait_ms=describe((op['work_started']['at']-op['work_submitted']['at'])*1000 for op in own if 'work_started' in op and 'work_submitted' in op),
            cpu_operation_ms=describe(op['work_completed']['work_cpu_seconds']*1000 for op in own if 'work_completed' in op),
            wall_ms=describe((op['work_completed']['work_finished_at']-op['work_completed']['work_started_at'])*1000 for op in own if 'work_completed' in op))
    series=[]
    for i in range(math.ceil(T)):
        b=min(i+1,T)
        state=state_before(events,origin+b,complete) if clock_ok and closures and origin+b<=closures[0]['at'] else dict(status='unknown',counts=None)
        for cls,generator in [('benign','normal'),('attack','attack'),('unknown',None)]:
            own=[r for r in requests if r['generator']==generator]
            source_ids={e['source_id'] for e in journal if (e['source_id'].startswith('attack_') if cls=='attack' else e['source_id'].startswith('normal_') if cls=='benign' else False)}
            row=dict(start=i,end=b,phase=phase(i,S,E),traffic_class=cls,
                admissions=sum(e['kind']=='admission' and e['source_id'] in source_ids and i<=e['payload'].get('elapsed_seconds',-1)<b for e in journal),
                http_starts=sum(i<=float(r['elapsed_seconds'])<b for r in own),
                http_completions=sum(r.get('end_elapsed_seconds') not in ('',None) and i<=float(r['end_elapsed_seconds'])<b for r in own),
                computation_state=state['status'])
            for kind in ('submitted','task_started'):
                row[kind]=sum(e['kind']==kind and e['source_id'] in source_ids and i<=e['payload'].get('elapsed_seconds',-1)<b for e in journal)
            row['expired_before_http']=sum(e['kind']=='task_resolution' and e['payload'].get('decision')=='expired_before_http' and e['source_id'] in source_ids and i<=e['payload'].get('elapsed_seconds',-1)<b for e in journal)
            for kind in ('work_submitted','work_started','work_completed','work_failed'):
                row[kind]=sum(e['kind']==kind and e.get('traffic_class','unknown')==cls and origin+i<=e['at']<origin+b for e in events) if clock_ok else None
            for key in ('waiting','running','pending','completed'):
                row[key+'_at_end_left']=state['counts'][cls][key] if state['counts'] else None
            series.append(row)
    if any(b-a>1 for a,b in zip(sorted(float(m['elapsed_seconds']) for m in metrics), sorted(float(m['elapsed_seconds']) for m in metrics)[1:])):
        limits.append('CPU tick series is sparse; 1-second event bins are not 1-second CPU observations.')
    return dict(phases=phases,groups=groups,emission=emission,per_source=per_source,
        computation=computational,residual=residual,
        integrity=dict(computation_complete=complete,duplicates=duplicates,writer_sequence_valid=sequence_ok,
            correlated_requests=len(matched),correlation_mismatches=mismatches,
            requests_without_observed_submission=sorted(set(request_map)-matched)),
        cpu=dict(ticks=cadence([float(m['elapsed_seconds']) for m in metrics],phases),
                 raw=cadence([m['monotonic']-origin for m in raw_cpu],phases) if clock_ok else None,
                 tick_cpu_percent=describe(float(m['average_cpu_percent']) for m in metrics if m.get('active_containers_names')),
                 tick_memory_mib=describe(float(m['mem_usage']) for m in metrics if m.get('active_containers_names'))),
        limitations=limits),series


def analyze(run, output):
    run=Path(run).resolve(); dataset=run if (run/'dataset_manifest.json').exists() else run/'dataset'
    output=Path(output).resolve()
    if output==run or run in output.parents or output in run.parents:
        raise ValueError('analysis output must be separate from input tree')
    reader=Reader(dataset)
    validation=validate_dataset(dataset)
    # Reader verifies each indexed file, including evidence not used in metrics.
    for entry in reader.manifest['files']:
        p=dataset/entry['path']
        if not p.resolve().is_relative_to(dataset) or p.is_symlink() or p.stat().st_size!=entry['bytes'] or hashlib.sha256(p.read_bytes()).hexdigest()!=entry['sha256']:
            raise ValueError('artifact hash/path mismatch: '+entry['path'])
    missing=[]
    def optional(name, kind):
        if placement(Path(name))[0] not in reader.index:
            missing.append(name); return [] if kind in ('lines','csv') else {}
        return getattr(reader,kind)(name)
    config=reader.json('effective_config.json'); status=reader.json('run_status.json')
    if not config['attack']['enabled'] or config['attack']['profile']!='continuous':
        raise ValueError('characterization requires one enabled continuous offensive mechanism')
    inventory=reader.json('source_inventory.json');journal=[]
    for source in inventory:journal+=optional('source_artifacts/'+source['source_id']+'/output/journal.jsonl','lines')
    meta=optional('diagnostics/metadata.json','json');clock=optional('diagnostics/victim_clock_validation.json','json')
    clock_ok=clock.get('comparable') is True and meta.get('run_id')==status['run_id']
    summary,series=characterize(config,reader.csv('request_log.csv'),journal,
        optional('diagnostics/victim/events.jsonl','lines'),reader.csv('simulation_metrics.csv'),
        optional('victim_stats.jsonl','lines'),meta.get('origin_monotonic',0),clock_ok,
        optional('diagnostics/victim/events.summary.json','json'))
    try:commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    except (OSError,subprocess.CalledProcessError):commit=None
    summary.update(version=VERSION,analyzer_commit=commit,analyzer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        dataset=str(dataset),run_id=status['run_id'],configuration=config,mechanism=config['attack'].get('mechanism') or 'not_declared',
        validation=dict(dataset_valid=validation['dataset_valid'],analysis_eligible=validation['analysis_eligible'],
            failed_checks=[c for c in validation['checks'] if not c['passed']]),capture=status.get('capture_results'),
        missing_inputs=missing,inputs=reader.inputs,manifest_sha256=hashlib.sha256((dataset/'dataset_manifest.json').read_bytes()).hexdigest())
    if missing:summary['limitations'].append('Missing evidence: '+', '.join(missing))
    certificate_path=(run/'raw/operational_policy.json') if (run/'raw').is_dir() else dataset.parent/'raw/operational_policy.json'
    summary['operational_certificate']={'status':'unavailable'}
    if certificate_path.is_file():
        certificate=json.loads(certificate_path.read_text())
        exported=certificate.get('export'); execution=certificate.get('execution')
        bound=isinstance(exported,dict) and isinstance(execution,dict) and exported.get('sha256')==summary['manifest_sha256'] and execution.get('run_id')==status['run_id']
        summary['operational_certificate']=dict(path=str(certificate_path),sha256=hashlib.sha256(certificate_path.read_bytes()).hexdigest(),bound_to_manifest=bound,certification=certificate.get('certification') if bound else 'unverified',cleanup_verified=certificate.get('cleanup_verified') if bound else None)
    output.mkdir(parents=True,exist_ok=False)
    (output/'summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
    with (output/'timeseries.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(series[0]));writer.writeheader();writer.writerows(series)
    report=['# Caracterização ofensiva offline', '', 'Run: '+status['run_id'],
        'Dataset: '+str(dataset), '',
        '| Grupo | Inícios | Conclusões | RPS nominal | RPS iniciado | HTTP médio ms |',
        '|---|---:|---:|---:|---:|---:|']
    for cls,g in summary['groups'].items():
        report.append(f"| {cls} | {g['starts_total']} | {g['completions']} | {g['nominal_rps']} | {g['realized_start_rps']:.6f} | {g['duration_ms'].get('mean')} |")
    report += ['', '| Computação | Espera média ms | CPU/op média ms | Duração média ms |', '|---|---:|---:|---:|']
    for cls,g in summary['computation'].items():
        report.append(f"| {cls} | {g['wait_ms']['mean']} | {g['cpu_operation_ms']['mean']} | {g['wall_ms']['mean']} |")
    report += ['', 'RPS ofensivo = inícios em [S,E)/(E−S); legítimo = inícios em [0,T)/T.',
        'Durações descrevem apenas conclusões disponíveis; p95 por posto mais próximo. Sem imputação.',
        '', 'Residual: '+json.dumps(summary['residual']),
        '', 'Integridade: '+json.dumps(summary['integrity']),
        '', 'Validação: '+json.dumps(summary['validation']),
        '', 'CPU: '+json.dumps(summary['cpu']),
        '', 'Limitações: '+json.dumps(summary['limitations']),
        '', 'Bins de eventos [t,t+1). Estados no limite esquerdo do término do bin.',
        'Sem interpolação de CPU; não se afirma Poisson homogêneo, recuperação ou ausência de ingressos tardios.',
        'Detalhes estruturados, denominadores, fases e proveniência em summary.json.']
    (output/'report.md').write_text('\n'.join(report)+'\n')
    return summary


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();summary=analyze(args.run,args.output)
    print(json.dumps(dict(run_id=summary['run_id'],integrity=summary['integrity'],residual=summary['residual'])))

if __name__=='__main__': main()
