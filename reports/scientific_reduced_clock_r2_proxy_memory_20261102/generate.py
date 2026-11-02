#!/usr/bin/env python3
"""Quatro verificações offline da memória bruta do proxy clock r2."""
import argparse
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from datetime import datetime
from functools import reduce
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
import csv

os.environ.setdefault('MPLCONFIGDIR','/tmp/clock-r2-matplotlib')
os.environ.setdefault('XDG_CACHE_HOME','/tmp/clock-r2-cache')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np

SCENARIOS=['C16','M16','E16']
PHASES=['PRE','ACTIVE','POST']
MIB=2**20
QUANTILES=[.1,.25,.5,.75,.9]
# Fixed before calculation; no screening by significance or effect magnitude.
PREDICTORS=['status_duration_ms','docker_duration_ms','operation_gap_us','engine_after_status_end_ms',
    'monitor_log_to_engine_ms','delay_ms','docker_interval_seconds','reading','writing','waiting','active',
    'upstream_benign_ms','upstream_attack_ms','scientific_completions_per_s']
RULES=dict(status_max_distance_seconds=.5,log_window_seconds=1.,
    monitor_log_tolerance_seconds=.005,consecutive_max_distance_seconds=1.5,
    min_correlation_pairs=8,visual_bin_seconds=1.,time_window_seconds=30.,page_quantum_bytes=4096)


def require(condition,message):
    if not condition:raise ValueError(message)


def load_module(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def ranks(a):
    _,inverse,count=np.unique(a,return_inverse=True,return_counts=True)
    return (np.cumsum(count)-count/2+.5)[inverse]


def correlation(x,y):
    a,b=np.asarray(x,dtype=float),np.asarray(y,dtype=float)
    good=np.isfinite(a)&np.isfinite(b);a,b=a[good],b[good]
    n=len(a)
    if n<RULES['min_correlation_pairs']:return None,n,'insufficient_pairs'
    if np.ptp(a)==0 or np.ptp(b)==0:return None,n,'constant_variable'
    return float(np.corrcoef(ranks(a),ranks(b))[0,1]),n,None


def quantiles(values,prefix=''):
    a=np.asarray([v for v in values if v is not None and np.isfinite(v)],dtype=float)
    out={prefix+'n':len(a)}
    for name,fn in [('mean',np.mean),('min',np.min),('max',np.max),('q10',lambda x:np.quantile(x,.1)),
        ('q25',lambda x:np.quantile(x,.25)),('median',np.median),('q75',lambda x:np.quantile(x,.75)),
        ('q90',lambda x:np.quantile(x,.9))]:out[prefix+name]=float(fn(a)) if len(a) else None
    return out


def paired_monitor_log(start,duration,epochs,used):
    tol=RULES['monitor_log_tolerance_seconds']
    lo,hi=bisect_left(epochs,start-tol),bisect_right(epochs,start+duration+tol)
    candidates=list(range(lo,hi))
    if not candidates:return None,'no_candidate'
    if len(candidates)!=1:return None,'ambiguous'
    if candidates[0] in used:return None,'already_matched'
    used.add(candidates[0]);return candidates[0],'unique'


def memory_key_paths(value,path=''):
    found=[]
    if isinstance(value,dict):
        for key,child in value.items():
            own=path+'.'+key
            if re.search(r'memory|\b(?:rss|pss|anon|cache|sock|slab)\b',key,re.I):found.append(own)
            found.extend(memory_key_paths(child,own))
    elif isinstance(value,list):
        for i,child in enumerate(value):found.extend(memory_key_paths(child,path+f'[{i}]'))
    return found


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for key in ['repo','plan','checkpoint','output']:ap.add_argument('--'+key,type=Path,required=True)
    ap.add_argument('--checkpoint-sha256',required=True)
    ap.add_argument('--overwrite',action='store_true')
    args=ap.parse_args();repo=args.repo.resolve()
    utility_path=repo/'reports/scientific_reduced_clock_r2_temporal_20261102/generate.py'
    util=load_module(utility_path,'temporal_io');io=util.Inputs(repo);io.track(utility_path)
    out=io.locate(args.output).resolve()
    protected=[repo/x for x in ['experiment_results','experiments','simulator','analysis','docs',
        'reports/scientific_reduced_clock_r2_proxy_20261102',
        'reports/scientific_reduced_clock_r2_figures_20261031',
        'reports/scientific_reduced_clock_r2_temporal_20261102',
        'reports/scientific_reduced_clock_r2_temporal_cli_20261102',
        'reports/scientific_reduced_clock_r2_20261030']]
    require(out!=repo and all(out!=p and p not in out.parents and out not in p.parents for p in protected),'Saída protegida')
    require(not any((out/f).is_symlink() for f in ['figures','tables']),'Subdiretório de saída não pode ser symlink')
    if out.exists() and not args.overwrite:
        require(all(p.name in {'generate.py','test_memory.py'} for p in out.iterdir()),'Saídas existentes; use outro diretório ou --overwrite')
    require(len(args.checkpoint_sha256)==64 and all(c in '0123456789abcdef' for c in args.checkpoint_sha256),'SHA256 esperado inválido')
    cp=io.read(args.checkpoint,args.checkpoint_sha256);require(cp['partition']=='TEST','Checkpoint não é TEST')
    plan=io.read(args.plan,cp['authority']['plan_sha256'])
    for path in ['simulator/proxy_monitor.py','simulator/http_proxy.py','simulator/config.py','experiments/dataset_schema.py']:
        io.track(path,plan['runtime_hashes'][path])
    monitor_code=io.track('simulator/proxy_monitor.py').read_text()
    io.track('docs/proxy_observability.md')
    old=repo/'reports/scientific_reduced_clock_r2_proxy_20261102'
    previous=io.read(old/'provenance.json')
    require(previous['checkpoint_sha256']==args.checkpoint_sha256,'Associação anterior pertence a outro checkpoint')
    source_table=io.track(old/'tables/sources.csv',previous['outputs']['tables/sources.csv'])
    old_sources={str(io.locate(r['path']).resolve()):r['sha256'] for r in io.csv(source_table)}
    ledger=io.track(old/'tables/access_association.csv',previous['outputs']['tables/access_association.csv'])
    io.track(old/'methodology.md',previous['outputs']['methodology.md'])
    log_groups=defaultdict(list);ledger_counts=Counter()
    with ledger.open(newline='') as stream:
        for r in csv.DictReader(stream):
            if not r['log_seconds']:
                ledger_counts['invalid_timestamp']+=1;continue
            cls=r['traffic_class'] if r['selection_reason']=='scientific' else r['log_phase']
            value=float(r['upstream_ms']) if r['final_reason']=='valid_scientific_upstream' and r['upstream_ms'] else None
            log_groups[r['entry']].append((float(r['log_seconds']),cls,value,float(r['log_epoch']),int(r['access_line']),r['run_id']))
            ledger_counts[cls]+=1
    entries={e['id']:e for e in plan['entries'] if e['partition']=='TEST'}
    records=[];summaries=[];associations=[];conditionals=[];windows=[];fields=[];runs=[];transitions=[]
    slot_counters=Counter();docker_keys=Counter();component_inventory=[]
    for ref in cp['receipts']:
        doc=io.artifact(ref);entry=doc['entry'];eid=entry['id'];receipt=doc['receipt']
        require(entry==entries[eid],'Identidade do recibo diverge')
        ds=io.locate(receipt['dataset']);dm=io.read(ds/'dataset_manifest.json',receipt['dataset_manifest_sha256'])
        require(dm['run_id']==receipt['run_id'],'Run do dataset diverge')
        def linked(relative):return io.linked(ds,dm['files'],relative)
        for relative in ['evidence/proxy/proxy_access.log','raw/service/request_log.csv']:
            p=linked(relative)
            require(old_sources.get(str(p.resolve()))==io.sources[str(p.resolve())], 'Associação anterior não vinculada a estes bytes')
        status=io.read(linked(dm['run_status']));require(status['run_id']==receipt['run_id'],'Âncora de outro run')
        identity=io.read(linked('evidence/proxy/proxy_identity.json'))
        config=linked('metadata/topology/proxy/proxy_config.conf').read_text()
        schema=io.read(linked('schema.json'))
        provenance=io.read(linked('metadata/run_provenance.json'))
        # Inventory actual preserved metadata; victim metrics are not proxy decomposition.
        metadata_documents=[('proxy_identity',identity),('dataset_schema',schema),('run_provenance',provenance)]
        for relative in ['evidence/proxy/monitor_summary.json','evidence/proxy/readiness.json',
                'evidence/proxy/monitor_networks.json','metadata/topology/proxy/capture_metadata.json',
                'metadata/topology/proxy/backend_inventory.json']:
            metadata_documents.append((relative,io.read(linked(relative))))
        for family,document in metadata_documents:
            topkeys=sorted(document) if isinstance(document,dict) else sorted({k for item in document if isinstance(item,dict) for k in item})
            fields.append(dict(entry=eid,artifact=family,top_level_keys=json.dumps(topkeys),
                memory_related_key_paths=json.dumps(memory_key_paths(document)),
                victim_memory_definition=json.dumps([f for f in schema['tables']['metrics']['fields'] if f['name']=='mem_usage']) if family=='dataset_schema' else None))
        events=io.csv(linked('raw/attacks/attack_events.csv'));require(len(events)==int(entry['scenario']!='C16'),'Eventos divergentes')
        event=events[0] if events else None
        start=float(event['actual_start_seconds']) if event else None
        end=float(event['actual_end_seconds']) if event else 270.
        stop=receipt['operational']['scalars']['stop_command_seconds'];stop=float(stop) if stop is not None else None
        phases={name:(float(r['start_seconds']),float(r['bin_end_seconds'])) for name,r in receipt['operational']['phases'].items()}
        require(phases==dict(PRE=(30.,150.),ACTIVE=(150.,end),POST=(end,390.)),'Fases operacionais divergentes')
        base=dict(entry=eid,run_id=receipt['run_id'],block=entry['block'],scenario=entry['scenario'])
        logs=sorted(log_groups[eid]);require(all(r[5]==receipt['run_id'] for r in logs),'Ledger de outro run')
        scientific=[r for r in logs if r[1] in {'benign','attack'}];science_times=[r[0] for r in scientific]
        monitor=[r for r in logs if r[1]=='monitoring'];epochs=[r[3] for r in monitor];used=set()
        with linked('evidence/proxy/monitor_samples.jsonl').open() as stream:samples=[json.loads(l) for l in stream]
        own=[]
        for i,s in enumerate(samples):
            require(s['run_id']==receipt['run_id'] and s['container_id']==identity['id'],'Identidade da amostra diverge')
            d,z=s['docker'],s['status'];data=d['data'] if d['success'] else {}
            docker_keys.update(data.keys());m=data.get('memory_usage_bytes');t=d['elapsed_seconds']
            phase=next((p for p,(a,b) in phases.items() if a<=t<b),'OUT')
            read_epoch=datetime.fromisoformat(data['docker_read'].replace('Z','+00:00')).timestamp() if data.get('docker_read') else None
            last=own[-1] if own else None
            dt=t-last['docker_seconds'] if last else None
            delta=m-last['memory_bytes'] if m is not None and last and last['memory_bytes'] is not None else None
            schedule_step=s['scheduled_elapsed_seconds']-samples[i-1]['scheduled_elapsed_seconds'] if i else None
            slots_skipped=max(0,int(round(schedule_step))-1) if schedule_step is not None else 0
            slot_counters['skipped_slots']+=slots_skipped
            status_lag=t-z['elapsed_seconds'];aligned=z['success'] and 0<=status_lag<=RULES['status_max_distance_seconds']
            k,match_reason=paired_monitor_log(z['timestamp'],z['duration_seconds'],epochs,used)
            slot_counters['monitor_log_'+match_reason]+=1
            a=phases[phase][0] if phase!='OUT' else None
            lo,hi=bisect_left(science_times,t-1),bisect_left(science_times,t)
            completions=scientific[lo:hi]
            row=dict(base,index=i,phase=phase,docker_seconds=t,docker_epoch=d['timestamp'],docker_read=data.get('docker_read'),
                memory_bytes=m,memory_mib=m/MIB if m is not None else None,
                previous_memory_bytes=last['memory_bytes'] if last else None,
                delta_bytes=delta,delta_mib=delta/MIB if delta is not None else None,docker_interval_seconds=dt,
                previous_phase=last['phase'] if last else None,
                consecutive_within_phase=bool(last and dt>0 and dt<=RULES['consecutive_max_distance_seconds'] and last['phase']==phase and phase!='OUT'),
                scheduled_seconds=s['scheduled_elapsed_seconds'],delay_ms=s['delay_seconds']*1000,
                scheduled_step_seconds=schedule_step,skipped_slots_before=slots_skipped,
                status_seconds=z['elapsed_seconds'],status_epoch=z['timestamp'],status_success=z['success'],status_error=z['error'],
                status_duration_ms=z['duration_seconds']*1000,docker_duration_ms=d['duration_seconds']*1000,
                status_to_docker_seconds=status_lag,status_alignment_valid=aligned,
                operation_gap_us=(t-z['elapsed_seconds']-z['duration_seconds'])*1e6,
                engine_after_status_end_ms=(read_epoch-z['timestamp']-z['duration_seconds'])*1000 if read_epoch else None,
                engine_after_docker_start_ms=(read_epoch-d['timestamp'])*1000 if read_epoch else None,
                engine_before_docker_end_ms=(d['timestamp']+d['duration_seconds']-read_epoch)*1000 if read_epoch else None,
                monitor_log_match=match_reason,monitor_access_line=monitor[k][4] if k is not None else None,
                monitor_log_to_engine_ms=(read_epoch-epochs[k])*1000 if read_epoch and k is not None else None,
                log_window_start=t-1,log_window_end=t,log_window_crosses_phase_start=bool(a is not None and t-1<a),
                scientific_completions_per_s=len(completions),event_start_seconds=start,event_end_seconds=end if event else None,stop_command_seconds=stop)
            for field,source in [('reading','reading_connections'),('writing','writing_connections'),
                                 ('waiting','waiting_connections'),('active','active_connections')]:
                row[field]=z['data'][source] if aligned else None
            for cls in ['benign','attack']:
                values=[v[2] for v in completions if v[1]==cls and v[2] is not None]
                row['upstream_'+cls+'_ms']=float(np.mean(values)) if values else None
                row['upstream_'+cls+'_n']=len(values)
                row['completions_'+cls]=sum(v[1]==cls for v in completions)
            require(all(t-1<=r[0]<t for r in completions),'Janela de logs fora do limite de 1 s')
            require(z['success'] or all(row[k] is None for k in ['reading','writing','waiting','active']),'Falha de status preenchida')
            own.append(row)
        records.extend(own)
        runs.append(dict(base,event_start_seconds=start,event_end_seconds=end if event else None,stop_command_seconds=stop,
            monitor_records=len(own),status_failures=sum(not r['status_success'] for r in own),
            memory_missing=sum(r['memory_bytes'] is None for r in own),
            skipped_slots=sum(r['skipped_slots_before'] for r in own),
            scheduled_steps_not_1s=sum(r['scheduled_step_seconds'] is not None and not math.isclose(r['scheduled_step_seconds'],1.) for r in own),
            repeated_docker_read=sum(a['docker_read']==b['docker_read'] for a,b in zip(own,own[1:])),
            monitor_log_matches=sum(r['monitor_log_match']=='unique' for r in own),
            page_aligned_4096=sum(r['memory_bytes'] is not None and r['memory_bytes']%4096==0 for r in own),
            operation_gap_negative_count=sum(r['operation_gap_us']<0 for r in own),
            operation_gap_min_us=min(r['operation_gap_us'] for r in own),operation_gap_max_us=max(r['operation_gap_us'] for r in own),
            engine_after_status_end_min_ms=min(r['engine_after_status_end_ms'] for r in own if r['engine_after_status_end_ms'] is not None),
            engine_after_status_end_max_ms=max(r['engine_after_status_end_ms'] for r in own if r['engine_after_status_end_ms'] is not None),
            read_before_docker_call=sum(r['engine_after_docker_start_ms']<0 for r in own if r['engine_after_docker_start_ms'] is not None),
            read_after_docker_call=sum(r['engine_before_docker_end_ms']<0 for r in own if r['engine_before_docker_end_ms'] is not None),
            max_delay_ms=max(r['delay_ms'] for r in own),
            proxy_artifact_paths=json.dumps([f['path'] for f in dm['files'] if '/proxy/' in f['path'] or f['path'].startswith('evidence/proxy/')])))
        for p,(a,b) in phases.items():
            subset=[r for r in own if r['phase']==p];values=[r['memory_mib'] for r in subset if r['memory_mib'] is not None]
            pairs=[r for r in subset if r['consecutive_within_phase'] and r['delta_mib'] is not None]
            deltas=[r['delta_mib'] for r in pairs]
            memory_bytes=[r['memory_bytes'] for r in subset if r['memory_bytes'] is not None]
            summary=dict(base,phase=p,start_seconds=a,end_seconds=b,**quantiles(values,'memory_'),
                **quantiles(deltas,'delta_'),**quantiles([abs(v) for v in deltas],'abs_delta_'),
                unique_memory_values=len(set(memory_bytes)),repeated_adjacent=sum(v==0 for v in deltas),
                positive_steps=sum(v>0 for v in deltas),negative_steps=sum(v<0 for v in deltas),
                nonzero_steps_per_second=sum(v!=0 for v in deltas)/(b-a),
                total_variation_mib_per_second=sum(abs(v) for v in deltas)/(b-a),
                aligned_status=sum(r['status_alignment_valid'] for r in subset),
                status_failed=sum(not r['status_success'] for r in subset),
                status_distance_excluded=sum(r['status_success'] and not r['status_alignment_valid'] for r in subset),
                log_windows_cross_phase_start=sum(r['log_window_crosses_phase_start'] for r in subset))
            trend=[r for r in subset if r['memory_mib'] is not None]
            summary['memory_slope_mib_per_100s']=float(np.polyfit([r['docker_seconds'] for r in trend],[r['memory_mib'] for r in trend],1)[0]*100) if len(trend)>1 else None
            summary['delta_gcd_bytes']=reduce(math.gcd,[abs(int(r['delta_bytes'])) for r in pairs],0)
            summary['memory_gcd_bytes']=reduce(math.gcd,[int(v) for v in memory_bytes],0)
            summary.update(quantiles([r['status_duration_ms'] for r in subset],'status_duration_ms_'))
            summary.update(quantiles([r['docker_duration_ms'] for r in subset],'docker_duration_ms_'))
            summary.update(quantiles([r['operation_gap_us'] for r in subset],'operation_gap_us_'))
            summary.update(quantiles([r['engine_after_status_end_ms'] for r in subset],'engine_after_status_end_ms_'))
            summary.update(quantiles([r['delay_ms'] for r in subset],'delay_ms_'))
            summary['reversal_pairs']=sum(x*y<0 for x,y in zip(deltas,deltas[1:]))
            summary['reversal_candidates']=sum(x!=0 and y!=0 for x,y in zip(deltas,deltas[1:]))
            summaries.append(summary)
            for succeeded in [True,False]:
                vals=[r['memory_mib'] for r in subset if r['status_success']==succeeded]
                conditionals.append(dict(base,phase=p,status_success=succeeded,**quantiles(vals,'memory_')))
            for predictor in PREDICTORS:
                for mode in ['level','difference']:
                    x=[];y=[]
                    for r in subset:
                        if r['memory_mib'] is None:continue
                        if predictor.startswith('upstream_') or predictor=='scientific_completions_per_s':
                            if r['log_window_crosses_phase_start']:continue
                        if mode=='level':
                            if r[predictor] is not None:x.append(r['memory_mib']);y.append(r[predictor])
                        elif r['consecutive_within_phase']:
                            before=own[r['index']-1]
                            if predictor.startswith('upstream_') or predictor=='scientific_completions_per_s':
                                if before['log_window_crosses_phase_start']:continue
                            if r[predictor] is not None and before[predictor] is not None:
                                x.append(r['delta_mib']);y.append(r[predictor]-before[predictor])
                    rho,n,reason=correlation(x,y)
                    associations.append(dict(base,phase=p,predictor=predictor,mode=mode,spearman=rho,n_pairs=n,undefined_reason=reason))
        for a in range(30,390,30):
            vals=[r['memory_mib'] for r in own if a<=r['docker_seconds']<a+30 and r['memory_mib'] is not None]
            windows.append(dict(base,start_seconds=a,end_seconds=a+30,emission_overlap_seconds=max(0,min(a+30,end)-max(a,start)) if event else 0,
                **quantiles(vals,'memory_')))
        for relative in ['evidence/proxy/monitor_samples.jsonl','evidence/proxy/proxy_identity.json',
                         'metadata/run_provenance.json','schema.json']:
            component_inventory.append(dict(base,path=relative,proxy_total_present=relative.endswith('monitor_samples.jsonl'),
                proxy_anon_rss_saved=False,proxy_file_cache_saved=False,proxy_socket_kernel_saved=False,proxy_process_stats_saved=False))
    require(len(runs)==36 and len(summaries)==108,'Escopo TEST incompleto')
    require(sum(r['status_failures'] for r in runs)==119,'Falhas de status divergem')
    require(sum(r['memory_missing'] for r in runs)==0,'Ausências de memória não esperadas: investigar sem imputar')
    require(sum(r['page_aligned_4096'] for r in runs)==len(records),'Alinhamento em 4096 bytes não se sustenta')
    require('memory_stats' not in docker_keys and 'rss' not in docker_keys,'Composição adicional encontrada: rever diagnóstico')
    for phase in PHASES:
        for block in range(1,13):
            control=next(r for r in summaries if r['scenario']=='C16' and r['block']==block and r['phase']==phase)
            for scenario in ['M16','E16']:
                own=next(r for r in summaries if r['scenario']==scenario and r['block']==block and r['phase']==phase)
                row=dict(block=block,phase=phase,contrast=scenario+'-C16')
                for metric in ['mean','q10','q25','median','q75','q90']:
                    row['delta_memory_'+metric]=own['memory_'+metric]-control['memory_'+metric]
                transitions.append(row)
    if out.exists() and args.overwrite and (out/'provenance.json').exists():
        old_prov=json.loads((out/'provenance.json').read_text())
        for rel in old_prov.get('outputs',{}):
            path=(out/rel).resolve();require(out in path.parents and path.parent in {out,out/'tables',out/'figures'},'Saída antiga fora da apresentação')
        for rel in old_prov.get('outputs',{}):(out/rel).unlink(missing_ok=True)
    out.mkdir(parents=True,exist_ok=True);(out/'tables').mkdir(exist_ok=True);(out/'figures').mkdir(exist_ok=True)
    def table(name,values):util.table(out,name,values)
    table('native_memory_alignment',records);table('run_phase_distributions',summaries)
    table('within_run_associations',associations);table('status_success_conditions',conditionals)
    table('fixed_windows_30s',windows);table('paired_quantile_differences',transitions)
    table('run_support',runs);table('composition_inventory',component_inventory);table('metadata_field_inventory',fields)
    table('saved_docker_fields',[dict(field=k,observations=v) for k,v in sorted(docker_keys.items())])
    plot(out,records,summaries,associations,runs)
    write_diagnosis(out,summaries,associations,runs,windows,transitions,slot_counters,ledger_counts)
    table('sources',[dict(path=str(Path(p).relative_to(repo)) if repo in Path(p).parents else p,sha256=h) for p,h in sorted(io.sources.items())])
    command=shlex.join([sys.executable,'-B',str(Path(__file__).resolve()),'--repo',str(repo),'--plan',str(args.plan),
        '--checkpoint',str(args.checkpoint),'--checkpoint-sha256',args.checkpoint_sha256,'--output',str(out)]+(['--overwrite'] if args.overwrite else []))
    prov=dict(checkpoint_sha256=args.checkpoint_sha256,plan_sha256=cp['authority']['plan_sha256'],
        generator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),command=command,
        python=platform.python_version(),numpy=np.__version__,matplotlib=matplotlib.__version__,
        rules=RULES,monitor_log_matching=dict(slot_counters),ledger_classes=dict(ledger_counts),
        scientific_runtime_imported=False,inferential_tests=False,new_collection=False,
        source_files=len(io.sources),composition='Somente total bruto do cgroup; componentes não persistidos',
        transformations=['bytes/2**20','diferenças consecutivas com dt<=1.5s e mesma fase',
            'quantis lineares descritivos por execução/fase e janelas fixas de 30 s',
            'Spearman com empates por posto médio, sem p, IC ou hipótese nula; n>=8 pares variáveis',
            'logs científicos na janela passada [t-1,t), sem preenchimento; status do mesmo ciclo a até 0.5s',
            'monitor logs únicos no intervalo status±5ms; HTTP log não é término de processo',
            'ECDFs e quantis de cada run separados; sem pooling inferencial ou corte alto/baixo'],
        outputs={str(p.relative_to(out)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.rglob('*'))
            if p.is_file() and (p.parent.name in {'figures','tables'} or p.name in {'diagnosis.md','methodology.md'})})
    (out/'provenance.json').write_text(json.dumps(prov,indent=2,ensure_ascii=False)+'\n')
    (out/'reproduce.sh').write_text('#!/bin/sh\n'+command+'\n')
    print(json.dumps(dict(runs=len(runs),records=len(records),phases=len(summaries),monitor_logs=dict(slot_counters),output=str(out)),ensure_ascii=False))


def plot(out,records,summaries,associations,runs):
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9,'pdf.fonttype':42,'ps.fonttype':42,
        'axes.spines.top':False,'axes.spines.right':False,'path.simplify':False})
    def save(fig,name):
        for ext in ['pdf','png']:fig.savefig(out/'figures'/(name+'.'+ext),dpi=300,facecolor='white')
        plt.close(fig)
    own=[r for r in records if r['phase']!='OUT'];lo=min(r['memory_mib'] for r in own);hi=max(r['memory_mib'] for r in own)
    fig,axs=plt.subplots(3,1,figsize=(11.69,8.27),sharex=True)
    for ax,scenario in zip(axs,SCENARIOS):
        matrix=np.full((12,360),np.nan);counts=np.zeros((12,360),int)
        for r in own:
            if r['scenario']==scenario:
                j,k=r['block']-1,math.floor(r['docker_seconds'])-30
                require(counts[j,k]==0,'Mais de uma leitura por bin visual de 1 s; não agregar silenciosamente')
                matrix[j,k]=r['memory_mib'];counts[j,k]+=1
        cmap=plt.get_cmap('viridis').copy();cmap.set_bad('#dddddd')
        mesh=ax.pcolormesh(np.arange(30,391),np.arange(13),matrix,cmap=cmap,vmin=lo,vmax=hi,rasterized=False)
        for r in runs:
            if r['scenario']!=scenario or r['event_start_seconds'] is None:continue
            j=r['block']-1
            ax.plot([r['event_start_seconds']]*2,[j+.05,j+.95],color='white',ls='--',lw=1)
            ax.plot([r['event_end_seconds']]*2,[j+.05,j+.95],color='white',lw=1)
            if r['stop_command_seconds'] is not None:ax.plot([r['stop_command_seconds']]*2,[j+.05,j+.95],color='#ff69b4',ls=':',lw=1)
        ax.set(yticks=np.arange(12)+.5,yticklabels=[f'B{b:02}' for b in range(1,13)],ylim=(12,0),xlim=(30,390),
               xticks=[30,90,150,210,270,330,390],title=scenario)
        ax.tick_params(labelsize=8)
    axs[-1].set_xlabel('Tempo desde a origem (s); célula = bin [i,i+1) contendo uma leitura nativa')
    cax=fig.add_axes([.91,.16,.015,.68]);bar=fig.colorbar(mesh,cax=cax,label='Memória bruta do cgroup (MiB)')
    bar.solids.set_rasterized(False)
    fig.suptitle('A · Memória nativa do proxy nas 36 execuções',fontsize=14,y=.98)
    fig.text(.5,.025,'Uma leitura por célula, sem interpolação. Escala integral comum; cinza = ausência.\n'
        'Branco tracejado/contínuo: início/fim reais; rosa: comando. C16 não recebe fronteiras ofensivas.',ha='center',fontsize=8)
    fig.subplots_adjust(left=.07,right=.88,bottom=.14,top=.91,hspace=.35)
    save(fig,'A_native_memory_all_runs')
    fig,axs=plt.subplots(3,3,figsize=(11.69,8.27),sharex=True,sharey=True)
    colors=plt.get_cmap('tab20')(np.linspace(0,.95,12))
    for i,scenario in enumerate(SCENARIOS):
        for j,phase in enumerate(PHASES):
            ax=axs[i,j]
            for b in range(1,13):
                values=sorted(r['memory_mib'] for r in own if r['scenario']==scenario and r['phase']==phase and r['block']==b)
                ax.step(values,np.arange(1,len(values)+1)/len(values),where='post',color=colors[b-1],lw=.8,alpha=.8)
            ax.set_title(scenario+' · '+phase);ax.grid(alpha=.15)
            if i==2:ax.set_xlabel('Memória (MiB)')
            if j==0:ax.set_ylabel('Fração acumulada no run')
    fig.legend(handles=[Line2D([],[],color=colors[b-1],label=f'B{b:02}') for b in range(1,13)],
        loc='lower center',bbox_to_anchor=(.5,.045),ncol=12,fontsize=7,frameon=False)
    fig.suptitle('B · Distribuições completas, sem corte alto/baixo',fontsize=14,y=.98)
    fig.text(.5,.014,'Cada curva é uma execução/fase. E16 possui exposições ACTIVE diferentes. Não há pooling de réplicas nem IC.',ha='center',fontsize=8)
    fig.subplots_adjust(left=.07,right=.98,bottom=.14,top=.91,hspace=.3,wspace=.15)
    save(fig,'B_memory_ecdf_by_run_phase')
    fig,axs=plt.subplots(2,3,figsize=(11.69,8.27),sharey=True)
    choices=[('status_duration_ms','Duração da consulta status'),('active','Conexões ativas'),('upstream_benign_ms','Upstream legítimo, passado 1 s')]
    groups=[(s,p) for s in SCENARIOS for p in PHASES]
    for i,mode in enumerate(['level','difference']):
        for j,(predictor,label) in enumerate(choices):
            ax=axs[i,j]
            for k,(s,p) in enumerate(groups):
                for r in associations:
                    if r['scenario']==s and r['phase']==p and r['predictor']==predictor and r['mode']==mode and r['spearman'] is not None:
                        ax.plot(k+(r['block']-6.5)*.035,r['spearman'],'o',color=colors[r['block']-1],ms=3.5)
            ax.axhline(0,color='#777777',lw=.7)
            ax.set(xticks=range(9),xticklabels=[s+'\n'+p for s,p in groups],ylim=(-1,1),title=label+'\n'+('Níveis' if mode=='level' else 'Diferenças consecutivas'))
            ax.tick_params(axis='x',labelsize=7);ax.grid(axis='y',alpha=.15)
            if j==0:ax.set_ylabel('Spearman descritivo por run/fase')
    fig.suptitle('C · Associações dentro das execuções; sem testes inferenciais',fontsize=14,y=.98)
    fig.legend(handles=[Line2D([],[],color=colors[b-1],marker='o',lw=0,label=f'B{b:02}') for b in range(1,13)],
        loc='lower center',bbox_to_anchor=(.5,.045),ncol=12,fontsize=7,frameon=False)
    fig.text(.5,.014,'Ponto = uma execução/fase, não uma leitura. Indefinidos não viram zero. Suporte e demais variáveis constam no CSV.',ha='center',fontsize=8)
    fig.subplots_adjust(left=.07,right=.98,bottom=.16,top=.88,hspace=.4,wspace=.12)
    save(fig,'C_within_run_associations')


def write_diagnosis(out,summaries,associations,runs,windows,contrasts,slots,ledger_counts):
    fmt=lambda x:'indefinido' if x is None else f'{x:.3f}'.replace('.',',')
    def median(values):
        v=[x for x in values if x is not None];return float(np.median(v)) if v else None
    lines=['# Diagnóstico offline da memória bruta do proxy — clock r2','',
        'Escopo restrito às quatro verificações solicitadas: valores/saltos; monitoramento; conexões/atendimento; composição salva. '
        '36 execuções TEST, fontes vinculadas por hash. Nenhum Docker, experimento, coleta ou detector foi executado.','',
        '## 1. Observações confirmadas: distribuição e saltos','',
        'Não foi escolhido limiar alto/baixo. Usam-se distribuições completas e quantis com posições fixas, '
        'diferenças assinadas/absolutas e contagens de sinal. A tabela informa a mediana entre 12 resumos por execução; '
        'quantis de cada run são descritivos, não ICs nem percentis de uma mistura dos 12 runs.','',
        '| Cenário/fase | Média (MiB) | q10 | Mediana | q75 | q90 | q90 de abs(Δmemória) (MiB) |',
        '|---|---:|---:|---:|---:|---:|---:|']
    for s in SCENARIOS:
        for p in PHASES:
            subset=[r for r in summaries if r['scenario']==s and r['phase']==p]
            values=[median([r[k] for r in subset]) for k in ['memory_mean','memory_q10','memory_median','memory_q75','memory_q90','abs_delta_q90']]
            lines.append('| '+s+'/'+p+' | '+' | '.join(fmt(v) for v in values)+' |')
    maximum_e16=max(r['memory_max'] for r in summaries if r['scenario']=='E16' and r['phase']=='ACTIVE')
    maximum_c16=max(r['memory_max'] for r in summaries if r['scenario']=='C16' and r['phase']=='ACTIVE')
    e=[r for r in contrasts if r['phase']=='ACTIVE' and r['contrast']=='E16-C16']
    lines+=['',f"Em ACTIVE, diferença E16−C16 pareada por bloco: mediana das diferenças das médias = {fmt(median([r['delta_memory_mean'] for r in e]))} MiB; "
        f"q10 = {fmt(median([r['delta_memory_q10'] for r in e]))}; mediana = {fmt(median([r['delta_memory_median'] for r in e]))}; "
        f"q90 = {fmt(median([r['delta_memory_q90'] for r in e]))} MiB. "
        'A queda da média descreve uma redistribuição das leituras, sobretudo afastamento da parte superior; '
        'não demonstra queda equivalente da memória do worker.','',
        f'Os picos não desaparecem: máximo observado em E16/ACTIVE={fmt(maximum_e16)} MiB, '
        f'em C16/ACTIVE={fmt(maximum_c16)} MiB. A queda da média não é uma queda uniforme de toda a distribuição.','',
        'Todas as leituras de memória estão em múltiplos de 4096 bytes; isso é compatível com quantização em páginas de 4 KiB, '
        'mas não identifica o componente que ganhou/perdeu páginas. Valores repetidos, GCD dos incrementos, sinais, '
        'amplitude e variação total estão por run/fase no CSV. As oscilações já ocorrem em C16/PRE; não dependem de emissão ofensiva.','',
        'Para distinguir passagem do tempo de emissão, o CSV de janelas fixas usa todos os intervalos consecutivos de 30 s, '
        'sem realinhar ataques. Em particular, [150,180) tem a mesma idade experimental nos três cenários; '
        'a comparação integral ACTIVE também é preservada, com duração variável E16.','',
        '| Cenário | Média em [120,150), mediana entre runs | Média em [150,180), mediana entre runs |',
        '|---|---:|---:|']
    for s in SCENARIOS:
        cells=[median([r['memory_mean'] for r in windows if r['scenario']==s and r['start_seconds']==a]) for a in [120,150]]
        lines.append('| '+s+' | '+' | '.join(fmt(v) for v in cells)+' |')
    lines+=['','Essa comparação torna insuficiente uma explicação baseada apenas na idade da execução: '
        'o deslocamento E16 já aparece no intervalo inicial de ACTIVE. Ao mesmo tempo, tendências e oscilações '
        'em C16 e POST mostram que não se deve atribuir toda mudança à emissão. Não é uma estimativa causal.','',
        '## 2. Associações com o monitoramento','',
        'O código confirma status por `exec_run(wget)` → retorno/exit_code/parsing → `stats(one_shot=True)`. '
        'Em sucesso normal, o comando bloqueante retornou antes da chamada Docker. As falhas existentes são de parsing, '
        'não evidência de timeout de wget em execução. Não há timestamp dedicado de término de cada processo ou liberação do cgroup.','',
        '| Cenário/fase | Variável | Mediana ρ em níveis | Mediana ρ em diferenças | Runs com ρ(Δ) negativo / definido |',
        '|---|---|---:|---:|---:|']
    for s,p in [('C16','PRE'),('C16','ACTIVE'),('E16','ACTIVE')]:
        for predictor in ['status_duration_ms','docker_duration_ms']:
            a=[r for r in associations if r['scenario']==s and r['phase']==p and r['predictor']==predictor]
            level=[r['spearman'] for r in a if r['mode']=='level'];dif=[r['spearman'] for r in a if r['mode']=='difference' and r['spearman'] is not None]
            lines.append(f"| {s}/{p} | {predictor} | {fmt(median(level))} | {fmt(median(dif))} | {sum(v<0 for v in dif)}/{len(dif)} |")
    lines+=['',
        'Há associação repetida entre a variação de memória e a duração das operações de observação, inclusive em controle/PRE. '
        'Ela é compatível com sensibilidade ao momento de amostragem, contabilização/liberação de memória transitória ou '
        'atividade auxiliar; não identifica wget como causa. Consultas status/Docker, runtime e NGINX podem responder à carga compartilhada. '
        'Diferenças consecutivas reduzem a contribuição de tendência lenta, mas não removem confundimento, autocorrelação ou seleção temporal.','',
        f"Slots pulados registrados pela diferença de scheduled_elapsed_seconds: {slots['skipped_slots']}. "
        f"Logs HTTP de monitoring pareados univocamente: {slots['monitor_log_unique']}; "
        f"sem candidato={slots['monitor_log_no_candidate']}, ambíguos={slots['monitor_log_ambiguous']}, reutilizados={slots['monitor_log_already_matched']}. "
        'Cadência, atraso e duração estão preservados por leitura; nenhum slot ausente foi preenchido.','',
        'A distância entre começo Docker e fim estimado de status pode ser ligeiramente negativa: '
        '`started` antecede `clock.sample()` e a duração inclui esse intervalo. Logo, começo+duration não é um fim exato; '
        'diferenças de microssegundos não provam sobreposição ou inversão da ordem. `docker_read` é preservado separadamente; '
        'o fim HTTP do log de monitoring também não é o fim do processo wget.','',
        '## 3. Relação com conexões e atendimento','',
        'Reading/Writing/Waiting/active usam somente status bem-sucedido do mesmo ciclo, separado da leitura Docker '
        'por no máximo 0,5 s. As 119 falhas permanecem ausentes; não se busca o último sucesso. '
        'Upstream e volume científicos usam logs associados a IDs no mesmo run, na janela passada [t−1,t), '
        'com suporte por classe; janelas vazias dão média upstream ausente e volume observado zero. '
        'Monitoring/setup/capture_audit são excluídos das estatísticas de logs científicos e mantidos no controle de suporte. '
        'Os gauges de conexões são globais, incluem monitoring e não permitem separação por classe via request_id; '
        'não se subtrai uma conexão presumida por consulta.','',
        'O CSV de associações inclui níveis e primeiras diferenças por execução/fase para as variáveis pré-especificadas, '
        'com n de pares e motivo de indefinição. Variáveis constantes (por exemplo Reading) não geram correlação zero artificial. '
        'A figura mostra duração de status, conexões ativas e upstream legítimo. Relações de nível com conexões/atendimento '
        'podem compartilhar tendência no tempo; sua persistência ou ausência nas diferenças deve ser lida junto ao suporte. '
        'Não há teste de independência das milhares de leituras nem p-valores ou ICs exploratórios.','',
        '## 4. Composição efetivamente salva e identificação','',
        '`resources` recebe a resposta stats Docker, mas salva da memória apenas `memory_stats.usage` como '
        '`memory_usage_bytes`. As chaves de docker.data foram inventariadas nas 14.094 leituras. '
        'Anon/RSS, cache de arquivos, sockets/kernel, PID/RSS/PSS por processo e eventos de alocação/liberação não estão '
        'nos registros do proxy. A API pode oferecer outros campos dependendo da versão/cgroup; isso não os torna '
        'retroativamente disponíveis. `raw/infrastructure` e `mem_usage` do schema descrevem vítimas, não decomposição do proxy.','',
        '**Hipóteses compatíveis:** variação transitória/contabilização do cgroup e efeito do momento de amostragem '
        'em relação às operações auxiliares; resposta compartilhada à carga, incluindo atendimento e custos das consultas. '
        '**Não verificável com os registros atuais:** qual componente físico mudou, quanto pertence ao worker/master/wget, '
        'se houve queda de RSS do NGINX, liberação de cache, memória de sockets ou retenção/liberação pós-processo. '
        'Não se estima nenhuma parcela por subtração.','',
        'Faltam séries sincronizadas de anon/RSS/cache/kernel/sockets do cgroup; memória e vida dos PIDs do worker, master '
        'e auxiliares; instantes de spawn/exit e liberação de contabilização; e evidência que separe a variação do monitor '
        'da carga compartilhada. Estes itens delimitam a identificação ausente; nenhum novo experimento foi preparado ou executado.','',
        '## Arquivos e legendas','',
        '- [A: 36 séries](figures/A_native_memory_all_runs.pdf) · [PNG](figures/A_native_memory_all_runs.png): memória bruta nativa por bin de 1 s contendo uma leitura; fronteiras reais por linha, sem corte de amplitude ou interpolação.',
        '- [B: distribuições](figures/B_memory_ecdf_by_run_phase.pdf) · [PNG](figures/B_memory_ecdf_by_run_phase.png): ECDF separada de cada run/fase; redistribuição sem limiar alto/baixo.',
        '- [C: associações](figures/C_within_run_associations.pdf) · [PNG](figures/C_within_run_associations.png): um coeficiente descritivo por execução/fase, em níveis e diferenças; indefinidos não viram zero.',
        '- [Leituras/alinhamentos](tables/native_memory_alignment.csv), [distribuições/saltos](tables/run_phase_distributions.csv), [associações e n](tables/within_run_associations.csv), [status sucesso/falha](tables/status_success_conditions.csv).',
        '- [Janelas de 30 s](tables/fixed_windows_30s.csv), [diferenças de quantis pareadas](tables/paired_quantile_differences.csv), [suporte por run](tables/run_support.csv), [inventário de composição](tables/composition_inventory.csv), [chaves efetivas](tables/saved_docker_fields.csv).',
        '- [Metodologia/alinhamento](methodology.md), [fontes e hashes](tables/sources.csv), [proveniência](provenance.json), [comando exato](reproduce.sh).','']
    timing=[f"Gaps estimados negativos: {sum(r['operation_gap_negative_count'] for r in runs)} de {sum(r['monitor_records'] for r in runs)}, "
        f"faixa global {fmt(min(r['operation_gap_min_us'] for r in runs))} a {fmt(max(r['operation_gap_max_us'] for r in runs))} μs. "
        f"docker_read após fim estimado de status: {fmt(min(r['engine_after_status_end_min_ms'] for r in runs))} a "
        f"{fmt(max(r['engine_after_status_end_max_ms'] for r in runs))} ms; fora do intervalo aproximado da chamada Docker: "
        f"{sum(r['read_before_docker_call']+r['read_after_docker_call'] for r in runs)}. "
        f"Maior atraso de agendamento registrado: {fmt(max(r['max_delay_ms'] for r in runs))} ms. "
        'Esses marcadores não sincronizam a leitura de memória com a liberação de um processo.','',
        f"Falhas de parsing aparecem em {sum(r['status_failed']>0 for r in summaries)} estratos run/fase, "
        f"com 1 a {max(r['status_failed'] for r in summaries)} falhas por estrato não vazio. "
        'A comparação sucesso/falha é apenas descritiva, com n pequeno/irregular; a duração da operação é observada mesmo quando o gauge falha.','']
    where=lines.index('## 3. Relação com conexões e atendimento');lines[where:where]=timing
    table=['| E16/ACTIVE | ρ níveis, mediana entre runs | ρ diferenças, mediana | Definidos nível/Δ | Pares nível / Δ, faixa entre runs |',
        '|---|---:|---:|---:|---:|']
    for predictor in ['reading','writing','waiting','active','upstream_benign_ms','upstream_attack_ms','scientific_completions_per_s']:
        subset=[r for r in associations if r['scenario']=='E16' and r['phase']=='ACTIVE' and r['predictor']==predictor]
        level=[r for r in subset if r['mode']=='level'];diff=[r for r in subset if r['mode']=='difference']
        ns=lambda values:f"{min(r['n_pairs'] for r in values)}–{max(r['n_pairs'] for r in values)}"
        table.append(f"| {predictor} | {fmt(median([r['spearman'] for r in level]))} | "
            f"{fmt(median([r['spearman'] for r in diff]))} | "
            f"{sum(r['spearman'] is not None for r in level)}/12; {sum(r['spearman'] is not None for r in diff)}/12 | {ns(level)} / {ns(diff)} |")
    table+=['','Reading é constante em E16/ACTIVE; por isso o coeficiente é indefinido, apesar dos pares observados. '
        'Writing, conexões ativas e upstream têm associação positiva de nível, mas mediana dos coeficientes em diferenças próxima de zero. '
        'O padrão de saltos não acompanha essas variações de atendimento de modo tão repetido quanto a duração das operações de observação. '
        'Isso limita explicações simples baseadas somente em número de conexões ou upstream; não exclui efeitos atrasados, indiretos ou carga compartilhada.','',
        f"No horizonte, status alinhado em {sum(r['aligned_status'] for r in summaries)} leituras; "
        f"falha={sum(r['status_failed'] for r in summaries)}; sucesso fora da distância permitida={sum(r['status_distance_excluded'] for r in summaries)}. "
        'Suporte por preditor e modo está no CSV, inclusive médias upstream ausentes quando nenhuma conclusão válida ocorreu na janela passada.','']
    where=lines.index('## 4. Composição efetivamente salva e identificação');lines[where:where]=table
    (out/'diagnosis.md').write_text('\n'.join(lines))
    (out/'methodology.md').write_text('''# Regras das quatro verificações

1. **Nativos e saltos.** Mantêm-se bytes inteiros, MiB=bytes/2²⁰, timestamps de cada fonte e docker_read. Todas as leituras são exportadas; distribuições usam [30,390) e fases operacionais PRE [30,150), ACTIVE [150,e), POST [e,390), com e real ou 270 em C16. Saltos usam pares consecutivos do mesmo run/fase, 0<dt≤1,5 s, sem atravessar ausência ou fronteira. Quantis são posições fixas 0,1/0,25/0,5/0,75/0,9 com interpolação linear apenas na estatística do quantil, não nas séries. Frequências são contagens de sinais/zeros e variação total por duração da fase, sem definir amplitude alta/baixa. Alinhamento a 4096 bytes é observado, não prova do tamanho físico de página/componente. Janelas fixas de 30 s são todas as consecutivas de 30 a 390; exposição sobreposta é registrada, sem sincronizar artificialmente o fim E16.

2. **Monitor.** Status→Docker é a ordem de código, não uma suposição da ordem dos logs. `started` e `clock.sample` não são o mesmo marcador. Fim estimado status=timestamp de início+duration_seconds tem incerteza de instrumentação; pequenos gaps negativos são guardados, sem clamp em zero. docker_read é convertido de ISO epoch para comparação; Python preserva microssegundos, com perda inferior a 1 μs dos dígitos excedentes, além da precisão de float/relógio. Monitoring HTTP é pareado apenas dentro do run, se houver exatamente uma linha entre início status−5 ms e início+duration+5 ms, sem reutilização. Os 5 ms são tolerância de alinhamento declarada para precisão de log/instrumentação, não limite metrológico certificado. Matching sem candidato/ambíguo não é preenchido. Fim HTTP não mede exit/liberação do processo. Cadência e slots são diferenças de scheduled_elapsed_seconds sob cadência nominal de 1 s; delay_seconds permanece o valor original. Não se recalcula CPU nem se executa exec/wget/stats.

3. **Atendimento.** Usa-se o ledger de IDs já conferido na apresentação anterior, autenticado pelo hash de sua proveniência. Os hashes dos access logs e CSVs de clientes também precisam coincidir com os arquivos vinculados nos datasets deste checkpoint. Não se refaz o detector ou a auditoria histórica. Conexões são do mesmo ciclo, sucesso e distância status→Docker entre 0 e 0,5 s (metade da cadência nominal); sem fallback para outro ciclo. Os gauges são globais e incluem monitoring; request_id não os decompõe por classe e não se subtrai uma conexão presumida do status. Logs científicos usam janela passada semiaberta [t−1,t), duração fixa de 1 s e distância máxima 1 s; não há associação ilimitada por último valor. Atribuição por conclusão/escrita, classes do request_id, auxiliares excluídos somente das estatísticas de logs científicos. Média sem conclusões válidas é ausente; contagem zero é zero registros no arquivo observado. A diferença entre relógios epoch/monotônico usa âncora preservada, sem correção estimada de drift. As tolerâncias são regras analíticas, não garantia de sincronização física. Correlações com logs excluem janelas que atravessam o início da fase; primeiras diferenças também exigem ambas as janelas elegíveis.

As associações são Spearman descritivo (postos médios em empates), n≥8 pares e duas variáveis não constantes. Exportam-se todos os preditores fixos, sem seleção por significância. Níveis e primeiras diferenças são separados; cada execução/fase é uma unidade de resumo, não milhares de réplicas. Não há teste, p-valor, IC, busca de limiar ótimo ou identificação causal. Falhas de parsing são ausências de gauges, mas sua duração/flag continuam observáveis. Comparações condicionais sucesso/falha informam n; poucas falhas não sustentam inferência.

4. **Composição.** Inventariam-se chaves realmente salvas de docker.data e metadados vinculados, schema, configuração e código de captura congelado. Não se inferem campos retroativos da API nem se subtrai memória das vítimas ou RSS ausente do total bruto do proxy. Não há estatística por processo ou sincronização com vida do wget. Somente o total é observável.

As figuras A/B mantêm amplitude integral; A usa uma leitura existente por bin visual de 1 s (mais de uma causaria recusa, não média silenciosa). Cinza significa ausência. Valores nativos completos e diferenças estão no CSV. C usa um ponto por run/fase, com escalas [-1,1] próprias do coeficiente, sem linhas de regressão inferenciais. Relatórios anteriores e artefatos científicos são somente lidos. A análise se limita às quatro verificações, sem reconfiguração, nova coleta ou preparação de experimento.
''')


if __name__=='__main__':
    try:main()
    except (ValueError,OSError,KeyError) as exc:
        print('Erro: '+str(exc),file=sys.stderr);sys.exit(2)
