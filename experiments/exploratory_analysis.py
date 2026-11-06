"""Read-only exploratory A1/A2 descriptions. No detector inputs or inference."""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
import math
from pathlib import Path
import statistics
from urllib.parse import urlsplit
from experiments.export_dataset import placement
from experiments.summarize_diagnostics import stats

VERSION = 'I2-v1'
A1 = {(2, 8): 'L2', (4, 4): 'L6', (2, 16): 'L3', (4, 8): 'L7'}
ROLES = ['M_A', 'E_A', 'E_B', 'M_B']


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def number(value):
    if isinstance(value, bool): raise ValueError('boolean measurement')
    value = float(value)
    if not math.isfinite(value): raise ValueError('nonfinite measurement')
    return value


def describe(values):
    values = list(values)
    return dict(stats(values), sample_sd=statistics.stdev(values) if len(values)>1 else None,
                sum=sum(values) if values else None,
                p99=sorted(values)[math.ceil(.99*len(values))-1] if len(values)>=100 else None)


def ratio(a, b):
    return a/b if a is not None and b is not None and b>0 else None


class Reader:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.inputs = {}
        self.manifest = None
        self.index = {}
        if (self.root/'dataset_manifest.json').exists():
            self.manifest = self.json_path(self.root/'dataset_manifest.json')
            for f in self.manifest['files']:
                if f['path'] in self.index: raise ValueError('duplicate manifest path')
                self.index[f['path']] = f

    def json_path(self, path):
        data = path.read_bytes(); self.inputs[str(path)] = hashlib.sha256(data).hexdigest()
        return json.loads(data)

    def path(self, relative):
        name = placement(Path(relative))[0] if self.manifest else relative
        p = self.root/name
        if p.is_symlink() or not p.resolve().is_relative_to(self.root): raise ValueError('unsafe input path')
        if self.manifest:
            entry = self.index.get(name)
            if not entry or p.stat().st_size != entry['bytes'] or digest(p) != entry['sha256']:
                raise ValueError('manifest binding mismatch: '+name)
        self.inputs[str(p)] = digest(p)
        return p

    def json(self, name): return json.loads(self.path(name).read_text())
    def lines(self, name):
        lines = self.path(name).read_text().splitlines(keepends=True)
        if any(not l.endswith('\n') for l in lines): raise ValueError('truncated JSONL: '+name)
        return [json.loads(l) for l in lines]
    def csv(self, name):
        with self.path(name).open(newline='') as f:
            rows = list(csv.DictReader(f))
        if any(None in r or any(v is None for v in r.values()) for r in rows):
            raise ValueError('malformed CSV: '+name)
        return rows


def analyze_run(spec, mode):
    result = dict(path=str(spec['path']), role=spec.get('role'), issues=[], warnings=[], counts={},
                  eligible=False, operations=[], phases=[], temporal=[], provenance={})
    read = Reader(spec['path'])
    try:
        _analyze(read, result, spec, mode)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        result['issues'].append('input: '+str(exc))
    result['provenance'].update(version=VERSION, inputs=read.inputs,
        processor_sha256=digest(__file__), time_basis='run_status.experiment_start_monotonic; HTTP elapsed from shared experiment origin',
        percentiles='nearest rank; p99 only n>=100', cpu_unit='seconds of worker process CPU')
    result['eligible'] = not result['issues']
    return result


def _analyze(read, out, spec, mode):
    issues = out['issues']; counts = Counter()
    c = read.json('effective_config.json'); s = read.json('run_status.json')
    from simulator.experiment_config import ExperimentConfig
    ExperimentConfig.from_dict(c)
    prov = read.json('run_provenance.json'); inv = read.json('source_inventory.json')
    rid = s['run_id']; origin = number(s['experiment_start_monotonic']); duration = int(c['duration_seconds'])
    n = c['normal_traffic']; out.update(run_id=rid, configuration=c)
    out['provenance'].update(configuration=c, runtime_provenance=prov)
    if (s['status']!='completed' or s['end_reason']!='simulation_end' or not s.get('producers_drained') or s.get('errors')):
        issues.append('execution incomplete or interrupted')
    if s.get('experiment_id') != c['id']: issues.append('configuration/run identity mismatch')
    if prov.get('run_id') != rid: issues.append('provenance run mismatch')
    if read.manifest and read.manifest['run_id'] != rid: issues.append('dataset run mismatch')
    if (c.get('topology',{}).get('mode')!='direct' or c['attack']['enabled'] or c['attack']['attackers']
        or c['server']['process_pool_workers']!=2 or not c.get('diagnostics',{}).get('enabled')):
        issues.append('incompatible topology/composition/instrumentation')
    if mode=='a2':
        if (n['clients'],n['rate'],n['max_concurrent_sends'],duration)!=(2,1,4,60) or n['endpoint'] not in ('/medium','/expensive'):
            issues.append('incompatible A2 configuration')
        role = spec.get('role')
        if role not in ROLES or n['endpoint'] != ('/medium' if role.startswith('M') else '/expensive'):
            issues.append('A2 role/endpoint mismatch')
    elif ((n['clients'],n['rate']) not in A1 or n['max_concurrent_sends']!=64 or duration!=150 or n['endpoint']!='/medium'):
        issues.append('incompatible A1 configuration')
    out['comparability'] = dict(server=c['server'], monitoring=c['monitoring'],
        topology=c.get('topology'),normal={k:v for k,v in n.items() if k!='endpoint'})
    out['configuration_code'] = A1.get((n['clients'],n['rate'])) if mode=='a1' else spec.get('role')
    policy = read.json('operational_policy.json')
    if spec.get('certification'):
        final_path = Path(spec['certification']).resolve()
        policy = read.json_path(final_path)
        if policy.get('export',{}).get('sha256') != digest(read.root/'dataset_manifest.json'):
            issues.append('final certificate/export binding mismatch')
    out['provenance']['operational_policy'] = policy
    out['comparability'].update(images=policy.get('images'), policy_limits=policy.get('limits'), policy_version=policy.get('version'))
    execution = policy.get('execution') or {}
    if execution.get('sha256') != digest(read.path('run_status.json')):
        issues.append('certificate/status binding mismatch')
    if policy.get('certification')!='completed' or policy.get('procedure_completed') is not True:
        issues.append('operational certification pending/blocked')
    meta = read.json('diagnostics/metadata.json')
    if meta['run_id']!=rid or number(meta['origin_monotonic'])!=origin: issues.append('diagnostic anchor/run mismatch')
    out['provenance']['diagnostic_metadata'] = meta
    out['comparability'].update(victim_image_id=meta.get('victim_image_id'),source_image=meta.get('source_image'),source_hashes=meta.get('source_sha256'))
    clock_ok = read.json('diagnostics/victim_clock_validation.json').get('comparable') is True
    if not clock_ok: issues.append('victim clock not comparable')
    if read.json('source_artifacts/clock_validation.json').get('comparable') is not True: issues.append('source clock not comparable')
    for kind,name in [('csv','traffic_capture.csv.capture.json'),('pcap','source_artifacts/traffic_capture.pcap.capture.json')]:
        capture=read.json(name)
        if not capture.get('accepted') or capture.get('capture_counters',{}).get('packets_dropped_by_kernel')!=0:
            issues.append('capture integrity: '+kind)
    requests = read.csv('request_log.csv'); by_id=defaultdict(list)
    for r in requests: by_id[r['request_id']].append(r)
    sources = {}; last_closure=[]
    out['source_ids']=[e['source_id'] for e in inv]
    if len(inv)!=n['clients'] or len({e['source_id'] for e in inv})!=len(inv): issues.append('source inventory mismatch')
    for source in inv:
        sid=source['source_id']
        if source['run_id']!=rid or source['source_type']!='normal': issues.append('source identity mismatch')
        root='source_artifacts/'+sid+'/output/'
        journal=read.lines(root+'journal.jsonl')
        begins={}; finishes={}
        for i,item in enumerate(journal,1):
            if item['sequence']!=i or item['run_id']!=rid or item['source_id']!=sid: issues.append('journal identity/sequence mismatch')
            if item['kind'] in ('request_begin','request_finish'):
                p=item['payload']; table=begins if item['kind']=='request_begin' else finishes
                if p['request_id'] in table: issues.append('duplicate journal request')
                table[p['request_id']]=p
            if item['kind']=='source_closed': last_closure.append(number(item['payload']['elapsed_seconds']))
        for key,p in begins.items():
            if key in sources: issues.append('request belongs to multiple sources')
            sources[key]=sid
            if key not in by_id or len(by_id[key])!=1: issues.append('journal/requests mismatch')
            else:
                r=by_id[key][0]
                if p.get('run_id')!=rid or number(p['elapsed_seconds'])!=number(r['elapsed_seconds']) or p['target_url']!=r['target_url'] or int(r['worker_id'])!=source['worker_index']:
                    issues.append('source/request fields mismatch')
                if bool(r['end_elapsed_seconds']) != (key in finishes): issues.append('journal completion mismatch')
                elif key in finishes:
                    end=finishes[key]
                    if number(end['end_elapsed_seconds'])!=number(r['end_elapsed_seconds']) or end['outcome']!=r['outcome']:
                        issues.append('journal finish fields mismatch')
        summary=read.json(root+'diagnostics/events.summary.json')
        if summary.get('complete') is not True: issues.append('source diagnostics incomplete')
        final=read.json(root+'final_status.json')
        if final.get('run_id')!=rid or not final.get('drained') or not final.get('logger_complete'): issues.append('source closure incomplete')
    if set(sources)!=set(by_id): issues.append('requests without source journal')
    out['coverage'] = dict(nominal_seconds=duration,source_closures=last_closure,
                          closed_through_nominal=bool(last_closure) and len(last_closure)==len(inv) and min(last_closure)>=duration)
    if not out['coverage']['closed_through_nominal']: issues.append('nominal horizon not certified')
    writer=read.json('diagnostics/victim/events.summary.json'); events=read.lines('diagnostics/victim/events.jsonl')
    if writer.get('complete') is not True or writer['written']!=len(events): issues.append('victim writer incomplete')
    ends=defaultdict(list); starts=Counter()
    for e in events:
        key=e.get('request_id')
        if not key:
            if e.get('phase') in ('setup','capture_audit'): counts['setup_events_excluded']+=1
            else: counts['unidentified_events']+=1
            continue
        if e.get('run_id') not in (None,rid): issues.append('foreign diagnostic run')
        if e['kind']=='handler_started': starts[key]+=1
        if e['kind']=='handler_finished': ends[key].append(e)
    for key in set(ends)-set(by_id): counts['cpu_without_request']+=len(ends[key])
    if set(starts)-set(by_id): issues.append('handler start without request')
    for key,rows in by_id.items():
        reasons=[]; r=rows[0]; completed=bool(r['end_elapsed_seconds'])
        if not key: reasons.append('missing_id')
        if len(rows)!=1: reasons.append('duplicate_request')
        if r['run_id']!=rid: reasons.append('foreign_run')
        if r['generator']!='normal' or r['traffic_class']!='benign': reasons.append('foreign_class')
        if urlsplit(r['target_url']).path!=n['endpoint']: reasons.append('endpoint_mismatch')
        if key not in sources: reasons.append('source_missing')
        if not completed: reasons.append('request_unfinished')
        if len(ends[key])==0: reasons.append('measurement_missing')
        if len(ends[key])>1: reasons.append('measurement_duplicate')
        if starts[key]!=1: reasons.append('handler_begin_missing_or_duplicate')
        op=dict(run_id=rid,request_id=key,source_id=sources.get(key),endpoint=n['endpoint'],
                http_status=r.get('http_status'),outcome=r.get('outcome'),cpu_seconds=None,
                work_start_seconds=None,work_end_seconds=None,submitted_seconds=None,worker_pid=None)
        op['http_start_seconds']=number(r['elapsed_seconds'])
        op['http_end_seconds']=number(r['end_elapsed_seconds']) if completed else None
        if completed and op['http_end_seconds']<op['http_start_seconds']: reasons.append('negative_http_duration')
        e=ends[key][0] if len(ends[key])==1 else {}
        if e and e.get('endpoint')!=n['endpoint']: reasons.append('endpoint_mismatch')
        try:
            if 'work_cpu_seconds' not in e: reasons.append('cpu_missing')
            else:
                cpu=number(e['work_cpu_seconds'])
                if cpu<0: reasons.append('cpu_negative')
                else:
                    op['cpu_seconds']=cpu
                    if cpu==0: counts['cpu_zero']+=1
        except (ValueError,TypeError): reasons.append('cpu_invalid')
        wc=e.get('worker_clock',{});op['worker_pid']=wc.get('pid')
        if clock_ok and wc.get('time_namespace')==writer['clock'].get('time_namespace') and wc.get('time_namespace') is not None:
            try:
                a,b,d=[number(e[k])-origin for k in ('work_submitted_at','work_started_at','work_finished_at')]
                if not 0<=a<=b<=d: raise ValueError('invalid work timeline')
                op.update(submitted_seconds=a,work_start_seconds=b,work_end_seconds=d)
            except (KeyError,ValueError,TypeError): reasons.append('work_timeline_missing_or_invalid')
        else:
            reasons.append('work_clock_unverified')
        op['valid']=not reasons;op['reasons']=';'.join(sorted(set(reasons)))
        counts.update(set(reasons));out['operations'].append(op)
    counts['requests_observed']=len(requests);counts['operations_valid']=sum(o['valid'] for o in out['operations'])
    counts['operations_invalid']=len(out['operations'])-counts['operations_valid']
    out['counts']=dict(counts)
    if counts['operations_invalid'] or counts['cpu_without_request'] or counts['unidentified_events']:
        issues.append('operation integrity anomalies; valid subset is diagnostic only')
    if counts['operations_valid']==0: issues.append('no valid CPU operations')
    out['cpu_seconds']=describe(o['cpu_seconds'] for o in out['operations'] if o['valid'])
    out['valid_fraction']=ratio(counts['operations_valid'],len(requests))
    out['temporal']=[dict(run_id=rid,start_seconds=a,end_seconds=a+10,
        **describe(o['cpu_seconds'] for o in out['operations'] if o['valid'] and a<=o['work_start_seconds']<a+10))
        for a in range(0,duration,10)]
    out['tail_work_operations']=sum(o['valid'] and o['work_start_seconds']>=duration for o in out['operations'])
    metrics=read.csv('simulation_metrics.csv')
    if not metrics: issues.append('CPU telemetry absent')
    for m in metrics:
        if m['run_id']!=rid: issues.append('foreign CPU metric run')
    out['cpu_coverage'] = dict(samples=len(metrics), first=min((number(m['elapsed_seconds']) for m in metrics),default=None),
        last=max((number(m['elapsed_seconds']) for m in metrics),default=None))
    out['phases']=[phase(out,requests,sources,metrics,a,b) for a,b in ((0,30),(30,150))] if mode=='a1' else []
    if mode=='a1':
        if out['phases'][1]['cpu_docker_percent']['n']==0: issues.append('main interval CPU telemetry absent')
        for a in range(0,150,10):
            out.setdefault('temporal_metrics',[]).append(phase(out,requests,sources,metrics,a,a+10))


def phase(out, requests, sources, metrics, a, b):
    own=[r for r in requests if a<=number(r['elapsed_seconds'])<b]
    finished=[r for r in own if r['end_elapsed_seconds']]
    duration=[(number(r['end_elapsed_seconds'])-number(r['elapsed_seconds'])) for r in finished]
    cpu=[number(m['average_cpu_percent']) for m in metrics if m.get('active_containers_names') and a<=number(m['elapsed_seconds'])<b]
    if any(x<0 for x in cpu): raise ValueError('negative CPU percentage')
    ops=[o for o in out['operations'] if o['work_start_seconds'] is not None]
    waits=[o['work_start_seconds']-o['submitted_seconds'] for o in ops if a<=o['http_start_seconds']<b]
    # Reconstructed intervals only: unfinished handlers may lack all submission metadata.
    intervals=[(o['submitted_seconds'],o['work_start_seconds']) for o in ops]
    times=sorted({a,b,*[t for pair in intervals for t in pair if a<=t<b]})
    pending=lambda t:sum(x<=t<y for x,y in intervals)
    n=out['configuration']['normal_traffic']; nominal=n['clients']*n['rate']
    per_source={sid:sum(sources.get(r['request_id'])==sid for r in own)/(b-a) for sid in out['source_ids']}
    outcomes=Counter(r['outcome'] for r in own)
    successes=sum(bool(r['http_status']) and 200<=int(r['http_status'])<300 for r in finished)
    return dict(run_id=out['run_id'],start_seconds=a,end_seconds=b,starts=len(own),
        nominal_rps=nominal,started_rps=len(own)/(b-a),relative_rate_error=(len(own)/(b-a)-nominal)/nominal,
        per_source_rps=per_source,completed=len(finished),unfinished=len(own)-len(finished),
        completions_after_boundary=sum(number(r['end_elapsed_seconds'])>=b for r in finished),
        http_seconds=describe(duration),cpu_docker_percent=describe(cpu),worker_wait_seconds=describe(waits),
        successes_2xx=successes,success_fraction_per_started=ratio(successes,len(own)),
        http_errors=outcomes['http_error'],transport_errors=outcomes['transport_error'],
        connection_errors=sum('Connection' in r.get('error_type','') for r in own),client_errors=outcomes['client_error'],timeouts=sum('Timeout' in r.get('error_type','') for r in own),
        submitted=sum(a<=x<b for x,y in intervals),work_started=sum(a<=o['work_start_seconds']<b for o in ops),
        work_finished=sum(a<=o['work_end_seconds']<b for o in ops),
        pending_peak_reconstructed=max((pending(t) for t in times if t<b),default=0) if intervals else None,
        pending_at_end_reconstructed=pending(b) if intervals else None,
        pending_basis='submitted-to-worker-start intervals of returned worker metadata; not private queue depth',
        outcomes=dict(outcomes))


def a2_ratios(runs):
    if len({json.dumps(r.get('comparability'),sort_keys=True) for r in runs})>1:
        return dict(defined=False,reason='incompatible environments/configurations; no pooled ratio')
    means={r.get('role'):r.get('cpu_seconds',{}).get('mean') if r['eligible'] else None for r in runs}
    if len(runs)!=4 or Counter(r.get('role') for r in runs)!=Counter(ROLES):
        return dict(defined=False,reason='require exactly four explicit roles M_A E_A E_B M_B')
    m=[means.get('M_A'),means.get('M_B')];e=[means.get('E_A'),means.get('E_B')]
    return dict(E_A_over_M_A=ratio(e[0],m[0]),E_B_over_M_B=ratio(e[1],m[1]),
        global_ratio=ratio(statistics.mean(e),statistics.mean(m)) if None not in e+m else None,
        basis='ratio of unweighted run means; pairs are runs, not matched requests')


def write_csv(path, rows, fallback):
    fields=sorted({k for r in rows for k in r}) or fallback
    with path.open('x',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        for r in rows:writer.writerow({k:json.dumps(v,sort_keys=True,allow_nan=False) if isinstance(v,(dict,list)) else v for k,v in r.items()})


def analyze(mode, specs, output):
    output=Path(output).absolute()
    if output.exists() or output.is_symlink(): raise FileExistsError(output)
    roots=[Path(s['path']).resolve() for s in specs]
    if any(output.resolve().is_relative_to(r) or r.is_relative_to(output.resolve()) for r in roots):
        raise ValueError('output must be separate from inputs')
    runs=[]
    for spec in specs:
        try:r=analyze_run(spec,mode)
        except (OSError,ValueError,KeyError,TypeError) as exc:
            r=dict(path=str(spec['path']),eligible=False,issues=['read failure: '+str(exc)],operations=[],phases=[],temporal=[])
        runs.append(r)
    ids=[r.get('run_id') for r in runs if r.get('run_id')]
    if len(ids)!=len(set(ids)):
        for r in runs:r['eligible']=False;r['issues'].append('duplicate run identity')
    for r in runs:
        for path,h in r.get('provenance',{}).get('inputs',{}).items():
            if digest(path)!=h: raise ValueError('input changed during analysis: '+path)
    output.mkdir(parents=True,exist_ok=False)
    integrity=dict(version=VERSION,mode=mode,runs=runs,automatic_selection=False,
        limitations=['Descriptive only; no inference or configuration selection.',
                     'CPU Docker 100% is approximately one logical core, not all host cores.',
                     'CPU zero is retained with a counter; resolution can produce zero. Positive denominators required.',
                     'HTTP cohorts use starts and all known completions, including drain; unfinished is not definitive failure.',
                     'Temporal CPU bins use worker start minus verified monotonic anchor; tail separate.',
                     'CPU samples are tick means, not exact time-weighted utilization; absent bins remain empty.'])
    (output/'integrity.json').write_text(json.dumps(integrity,indent=2,sort_keys=True,allow_nan=False)+'\n')
    rows=[{k:v for k,v in r.items() if k not in ('operations','temporal','phases','temporal_metrics','provenance')} for r in runs]
    write_csv(output/'per_run.csv',rows,['run_id','eligible'])
    if mode=='a2':
        ratios=a2_ratios(runs)
        (output/'ratios.json').write_text(json.dumps(ratios,indent=2,sort_keys=True,allow_nan=False)+'\n')
        write_csv(output/'cpu_operations.csv',[o for r in runs for o in r['operations']],['run_id','request_id','valid'])
        write_csv(output/'temporal_cpu.csv',[o for r in runs for o in r['temporal']],['run_id','start_seconds','n','mean'])
    else:
        write_csv(output/'temporal_metrics.csv',[o for r in runs for o in r.get('temporal_metrics',[])],['run_id','start_seconds'])
        write_csv(output/'comparison.csv',[dict(configuration=r.get('configuration_code'),**p) for r in runs if r['eligible'] for p in r['phases'] if p['start_seconds']==30],['configuration','run_id'])
    text=['# '+mode.upper()+' — análise exploratória', '', 'Estatísticas e unidades: integrity.json; CSVs preservam precisão. Sem inferência ou seleção automática.', '', '| Execução | Configuração | Comparação principal | Problemas |','|---|---|---|---|']
    for r in runs:text.append('| {} | {} | {} | {} |'.format(r.get('run_id',r['path']),r.get('configuration_code',''),r['eligible'],'; '.join(r['issues'])))
    if mode=='a2':
        text+=['','CPU por execução (segundos de CPU do worker):','','| Run | Endpoint | n válido | Média | Mediana | Fração válida |','|---|---|---:|---:|---:|---:|']
        for r in runs:
            stat=r.get('cpu_seconds',{})
            text.append('| {} | {} | {} | {} | {} | {} |'.format(r.get('run_id',''),r.get('configuration',{}).get('normal_traffic',{}).get('endpoint',''),stat.get('n'),stat.get('mean'),stat.get('p50'),r.get('valid_fraction')))
    else:
        text+=['','Coortes HTTP iniciadas em [30,150), incluindo conclusões conhecidas na drenagem. CPU em percentual Docker; duração/espera em segundos.','','| Configuração | Run | Starts/s | HTTP média | CPU média | Espera média | Sucesso/starts |','|---|---|---:|---:|---:|---:|---:|']
        for r in runs:
            for p in r['phases']:
                if p['start_seconds']==30:
                    text.append('| {} | {} | {} | {} | {} | {} | {} |'.format(r.get('configuration_code'),r.get('run_id'),p['started_rps'],p['http_seconds']['mean'],p['cpu_docker_percent']['mean'],p['worker_wait_seconds']['mean'],p['success_fraction_per_started']))
        text+=['','Contrastes planejados: L2/L6 e L3/L7 (mesma taxa); L2/L3 e L6/L7 (mesmas fontes). Uma execução por célula não demonstra causalidade. Linhas excluídas da comparação principal continuam disponíveis acima para diagnóstico.']
    if mode=='a2':text+=['','Razões descritivas:','', '```json',json.dumps(ratios,indent=2,allow_nan=False),'```']
    text+=['','Configurações com problemas permanecem diagnósticas e são excluídas das comparações principais. Contagens sem observações são zero; estatísticas sem suporte são nulas. Consulte integrity.json para hashes e detalhes.']
    (output/'report.md').write_text('\n'.join(text)+'\n')
    return integrity


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('mode',choices=['a1','a2'])
    parser.add_argument('--runs',nargs='+',required=True,help='Raw/dataset paths; A2 requires a JSON list with path and explicit role')
    parser.add_argument('--output',required=True);args=parser.parse_args()
    specs=[]
    for value in args.runs:
        p=Path(value)
        if p.is_file():
            entries=json.loads(p.read_text())
            for entry in entries:
                entry=dict(entry);entry['path']=str((p.parent/entry['path']).resolve())
                if entry.get('certification'):entry['certification']=str((p.parent/entry['certification']).resolve())
                specs.append(entry)
        else:specs.append(dict(path=value))
    result=analyze(args.mode,specs,args.output)
    raise SystemExit(0 if all(r['eligible'] for r in result['runs']) else 1)


if __name__=='__main__':main()
