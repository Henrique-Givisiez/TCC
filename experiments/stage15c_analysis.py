"""Stage15C descriptive interpretation of frozen run/seed results; no inference.

No detector, scorer, decision policy, fitter, calibrator or evaluator is imported.
Only Stage15B per-run metrics and frozen Stage15A/Stage10 observations are read.
Outputs are delivered for scientific review, never declared FROZEN.
"""
import argparse
from collections import Counter, defaultdict
from contextlib import contextmanager
import csv
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
from fractions import Fraction
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/'experiment_results/stage15c-descriptive-analysis-20261019'
CLOSING_COMMIT='3735225a5ba14d7e6eb279af73913e0e78320dea'
EXPECTED={'stage15a_manifest':'089a25681dd13810a94a92def805aa9a7e314955ebdcca671d625d959ae3a9d5',
          'stage15b_manifest':'2b36134d60f9dd5a4dc5bd721f4c5df194cc8ad695ab5d71c73156b5bb5863ca',
          'stage15b_freeze':'8232ce397022963dd8741d7e14746630a822cdf74cda4f4a113d7ca5a974f2c2'}
METHODS=('zscore','cov','ewma','cusum')
FEATURES=('ingress_packet_count','ingress_tcp_payload_length_sum_bytes','request_starts','mean_duration_ms','mean_cpu_percent')
WINDOW_METRICS=('precision','recall','f1','fpr','TP','FP','TN','FN','unavailable_decision_count','boundary_excluded_count',
                'candidate_decisions','valid_decisions','eligible_attack_windows','eligible_benign_windows',
                'unavailable_attack_decisions','unavailable_benign_decisions','unavailable_boundary_decisions')
POST_METRICS=('post_event_alarm_rate','candidate_post_event_decisions','post_event_eligible_windows','unavailable_post_event_decisions','post_event_positive_decisions')
QUANTILES='Hyndman-Fan type 7; h=(n-1)*p, linear interpolation, zero-based; defined values only'
CONTEXT=Context(prec=50,rounding=ROUND_HALF_EVEN)


def require(condition,message):
    if not condition:raise ValueError('STOP: '+message)


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def read(path):
    def unique(items):
        d={}
        for k,v in items:require(k not in d,'duplicate JSON key');d[k]=v
        return d
    def bad(v):raise ValueError('Nonfinite '+v)
    return json.loads(Path(path).read_text(),object_pairs_hook=unique,parse_float=Decimal,parse_constant=bad)


def number(value):
    if value is None:return None
    if isinstance(value,Fraction):return value
    require(not isinstance(value,bool),'bool used as metric')
    d=Decimal(str(value));require(d.is_finite(),'nonfinite metric')
    return Fraction(d)


def text(value):
    if isinstance(value,Fraction):
        with localcontext(CONTEXT):return str(Decimal(value.numerator)/Decimal(value.denominator))
    if isinstance(value,Decimal):return str(value)
    return value


def plain(value):
    if isinstance(value,dict):return {k:plain(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [plain(v) for v in value]
    return text(value)


def encode(value):return (json.dumps(plain(value),sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
def digest(value):return hashlib.sha256(encode(value)).hexdigest()


def checked(ref):
    p=ROOT/ref['path'];require(sha(p)==ref['sha256'],'frozen hash '+str(p))
    return read(p)


def locate(pattern,expected):
    paths=subprocess.check_output(['git','ls-files',pattern],cwd=ROOT,text=True).splitlines()
    matches=[p for p in paths if sha(ROOT/p)==expected]
    require(len(matches)==1,'authority discovery '+pattern)
    return dict(path=matches[0],sha256=expected)


def quantile(values,p):
    ordered=sorted(values)
    if not ordered:return None
    require(0<=p<=1,'quantile probability')
    h=(len(ordered)-1)*p;i=h.numerator//h.denominator
    return ordered[i] if i==len(ordered)-1 else ordered[i]+(ordered[i+1]-ordered[i])*(h-i)


def describe(values):
    valid=[number(x) for x in values if x is not None];n=len(valid)
    result=dict(runs_n=len(values),defined_n=n,undefined_n=len(values)-n,mean=None,sample_sd=None,median=None,q1=None,q3=None,min=None,max=None)
    if not n:return result
    mean=sum(valid,Fraction(0))/n;sd=None
    if n>1:
        variance=sum(((v-mean)**2 for v in valid),Fraction(0))/(n-1)
        with localcontext(CONTEXT):sd=(Decimal(variance.numerator)/Decimal(variance.denominator)).sqrt()
    result.update(mean=mean,sample_sd=sd,median=quantile(valid,Fraction(1,2)),q1=quantile(valid,Fraction(1,4)),q3=quantile(valid,Fraction(3,4)),min=min(valid),max=max(valid))
    return result


def exact_metric(row,name):
    value=number(row[name])
    if name in ('precision','recall','f1','fpr'):
        tp,fp,tn,fn=(row[k] for k in ('TP','FP','TN','FN'))
        num,den={'precision':(tp,tp+fp),'recall':(tp,tp+fn),'f1':(2*tp,2*tp+fp+fn),'fpr':(fp,fp+tn)}[name]
    elif name=='post_event_alarm_rate':num,den=row['post_event_positive_decisions'],row['post_event_eligible_windows']
    else:return value
    exact=Fraction(num,den) if den else None
    require((exact is None)==(value is None),'frozen null/denominator mismatch '+name)
    require(exact is None or text(exact)==row[name],'per-run metric differs from frozen counts '+name)
    # Preserve the frozen metric/null; recover exact ratio from its own frozen
    # numerator/denominator only to avoid rounding before run-level summaries.
    return exact


@contextmanager
def analysis_only():
    previous=sys.getprofile()
    def guard(frame,event,arg):
        if event=='call':
            module=frame.f_globals.get('__name__','')
            require(not module.startswith(('analysis.detection','experiments.stage15a_test_scoring','experiments.stage15b_evaluation','experiments.stage15b_reproduce')),
                    'forbidden reexecution of scientific pipeline')
        if previous is not None:previous(frame,event,arg)
    sys.setprofile(guard)
    try:yield
    finally:sys.setprofile(previous)


def preflight():
    subprocess.run(['git','merge-base','--is-ancestor',CLOSING_COMMIT,'HEAD'],cwd=ROOT,check=True)
    bref=locate('*stage15b_evaluation_manifest.json',EXPECTED['stage15b_manifest'])
    fref=locate('*stage15b_evaluation_freeze_manifest.json',EXPECTED['stage15b_freeze'])
    b=checked(bref);freeze=checked(fref);require(freeze['manifest']==bref and b['status']==freeze['status']=='FROZEN','15B closure')
    require(b['primary_evaluation_horizon']==[48,144] and b['startup_diagnostic_horizon']==[0,48] and b['experimental_unit']=='run/seed','analysis semantics')
    require(b['semantics']['f1']=='2*TP/(2*TP+FP+FN)' and b['semantics']['unavailable'].startswith('Excluded from confusion matrix'),'null/F1 semantics')
    docs={k:checked(v) for k,v in b['inputs'].items()}
    aref=b['inputs']['stage15a_manifest'];require(aref['sha256']==EXPECTED['stage15a_manifest'],'Stage15A authority')
    a=docs['stage15a_manifest'];inventory=docs['test_inventory'];protocol=docs['evaluation_protocol'];calibration=docs['four_method_freeze']
    require(protocol['horizons']['primary_evaluation']==[48,144] and protocol['horizons']['startup_diagnostic']==[0,48],'protocol horizon')
    require(a['alpha']=='0.01' and a['cov_L']==6 and a['ewma_lambda']=='0.2' and a['cusum_k']=='0.5','primary methods')
    # Resolved bridge is an immutable referenced input; no new equivalence review.
    inputs={**b['inputs'],'stage15b_manifest':bref,'stage15b_freeze':fref}
    for ref in a['inputs'].values():checked(ref)
    for path,expected in b['execution_source_sha256'].items():
        historical=subprocess.check_output(['git','show',CLOSING_COMMIT+':'+path],cwd=ROOT)
        require(hashlib.sha256(historical).hexdigest()==expected,'historical evaluator source')
    base=(ROOT/bref['path']).parent;output_index={Path(o['path']).stem:o for o in b['outputs']}
    require(len(output_index)==len(b['outputs']),'duplicate output role')
    for o in b['outputs']:
        p=base/o['path'];require(sha(p)==o['sha256'] and p.stat().st_size==o['bytes'],'15B output bytes')
    require(digest(b['outputs'])==b['outputs_set_sha256']==freeze['outputs_set_sha256'],'15B output set')
    tables=read(base/output_index['evaluation_results']['path'])
    for name,rows in tables.items():
        ref=output_index[name]
        with (base/ref['path']).open(newline='') as stream:
            observed=list(csv.DictReader(stream))
        require(len(rows)==len(observed)==ref['rows'],'CSV/JSON cardinality '+name)
        for row,actual in zip(rows,observed):
            for k,v in row.items():
                expected='' if v is None else str(v).lower() if type(v) is bool else json.dumps(v,separators=(',',':')) if isinstance(v,(list,dict)) else str(v)
                require(actual[k]==expected,'CSV/JSON disagreement '+name+'/'+k)
    entries={e['campaign_entry']:e for e in inventory['entries']}
    require(len(entries)==48 and Counter(e['scenario'] for e in entries.values())==Counter(B=16,C=16,P=16),'48 B/C/P runs')
    seeds=sorted({e['seed'] for e in entries.values()});require(len(seeds)==16,'16 seeds')
    for seed in seeds:require(Counter(e['scenario'] for e in entries.values() if e['seed']==seed)==Counter('BCP'),'seed pairing')
    for e in entries.values():
        require(e['analysis_eligible'] and e['dataset_valid'],'eligibility')
        root=ROOT/e['output_path']
        require({str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()}==set(e['artifacts']),'scientific file set')
        for p,ref in e['artifacts'].items():require(sha(root/p)==ref['sha256'] and (root/p).stat().st_size==ref['size'],'scientific data bytes')
    expected={(entry,m,f) for entry in entries for m in METHODS for f in FEATURES}
    for name,scope,attack_only in [('window_metrics_per_run','PRIMARY',False),('startup_diagnostic_per_run','STARTUP_DIAGNOSTIC',False),('event_metrics_per_run','PRIMARY',True),('post_event_metrics_per_run','PRIMARY',True)]:
        rows=tables[name];keys=[(r['campaign_entry'],r['method'],r['feature']) for r in rows]
        subset={k for k in expected if not attack_only or entries[k[0]]['scenario']!='B'}
        require(len(rows)==len(set(keys))==len(subset) and set(keys)==subset,'run/config cardinality '+name)
        for r in rows:
            e=entries[r['campaign_entry']]
            require(r['run_id']==e['run_identity'] and r['seed']==e['seed'] and r['scenario']==e['scenario'] and r['analysis_scope']==scope,'row identity/scope')
    for name in ('window_metrics_per_run','startup_diagnostic_per_run'):
        for r in tables[name]:
            for metric in ('precision','recall','f1','fpr'):exact_metric(r,metric)
            require(r['TP']+r['FN']==r['eligible_attack_windows'] and r['FP']+r['TN']==r['eligible_benign_windows'],'confusion support')
    require(len(a['outputs'])==960,'15A cardinality');abase=(ROOT/aref['path']).parent;afiles={}
    for o in a['outputs']:
        path=abase/o['path'];require(sha(path)==o['sha256'] and path.stat().st_size==o['bytes'],'15A frozen output')
        key=(o['campaign_entry'],o['method'],o['feature']);require(key not in afiles,'15A duplicate');afiles[key]=path
    require(set(afiles)==expected,'15A matrix')
    return dict(inputs=inputs,b=b,a=a,freeze=freeze,entries=entries,seeds=seeds,tables=tables,afiles=afiles,
                calibration=calibration,protocol=protocol,output_index=output_index,bbase=base)


def grouped(rows):
    groups=defaultdict(list)
    for row in rows:groups[(row['scenario'],row['method'],row['feature'])].append(row)
    return groups


def summarize(rows,metrics,scope):
    result=[]
    for (scenario,method,feature),group in sorted(grouped(rows).items()):
        require(len(group)==16,'16 runs per summary')
        for metric in metrics:
            values=[exact_metric(r,metric) for r in group]
            result.append(dict(scenario=scenario,method=method,feature=feature,analysis_scope=scope,metric=metric,
                defined_seeds=[r['seed'] for r,v in zip(group,values) if v is not None],undefined_seeds=[r['seed'] for r,v in zip(group,values) if v is None],
                **describe(values)))
    return result


def paired_results(tables):
    differences=[];delay_pairs=[]
    for metric,table in [('recall','window_metrics_per_run'),('f1','window_metrics_per_run'),('fpr','window_metrics_per_run'),('post_event_alarm_rate','post_event_metrics_per_run')]:
        lookup={(r['scenario'],r['method'],r['feature'],r['seed']):r for r in tables[table]}
        for method in METHODS:
            for feature in FEATURES:
                seeds=sorted(k[3] for k in lookup if k[:3]==('C',method,feature))
                for seed in seeds:
                    c=exact_metric(lookup['C',method,feature,seed],metric);p=exact_metric(lookup['P',method,feature,seed],metric)
                    differences.append(dict(seed=seed,method=method,feature=feature,metric=metric,c_value=c,p_value=p,
                        p_minus_c=None if c is None or p is None else p-c,complete_pair=c is not None and p is not None,
                        selection='COMPLETE_DEFINED_PAIRS',scenario_comparison='P-C',analysis_scope='PRIMARY'))
    lookup={(r['scenario'],r['method'],r['feature'],r['seed']):r for r in tables['event_metrics_per_run']}
    for method in METHODS:
        for feature in FEATURES:
            for seed in sorted(k[3] for k in lookup if k[:3]==('C',method,feature)):
                c=lookup['C',method,feature,seed];p=lookup['P',method,feature,seed]
                both=c['event_detected'] and p['event_detected']
                delta=number(p['detection_delay_seconds'])-number(c['detection_delay_seconds']) if both else None
                delay_pairs.append(dict(seed=seed,method=method,feature=feature,metric='detection_delay_seconds',c_value=number(c['detection_delay_seconds']),p_value=number(p['detection_delay_seconds']),
                    c_detected=c['event_detected'],p_detected=p['event_detected'],p_minus_c=delta,complete_pair=both,
                    selection='DETECTED_IN_BOTH_SCENARIOS',scenario_comparison='P-C',analysis_scope='PRIMARY'))
    result=[]
    for data in (differences,delay_pairs):
        group=defaultdict(list)
        for r in data:group[r['method'],r['feature'],r['metric']].append(r)
        for (m,f,k),rows in group.items():
            result.append(dict(method=m,feature=f,metric=k,scenario_comparison='P-C',selection=rows[0]['selection'],
                paired_seeds=[r['seed'] for r in rows if r['complete_pair']],excluded_seeds=[r['seed'] for r in rows if not r['complete_pair']],
                **describe([r['p_minus_c'] for r in rows])))
    return differences,delay_pairs,result


def reconciliation(summary,event_summary,tables):
    lookup={(r['scenario'],r['method'],r['feature'],r['metric']):r for r in summary}
    checks=[]
    for table in ('run_level_descriptive_summary','startup_descriptive_summary'):
        for frozen in tables[table]:
            row=lookup.get((frozen['scenario'],frozen['method'],frozen['feature'],frozen['metric']))
            # PRIMARY and STARTUP are intentionally reconciled separately by caller.
            if row is None or row['analysis_scope']!=frozen['analysis_scope']:continue
            require(row['defined_n']==frozen['defined_n'] and row['undefined_n']==frozen['undefined_n'],'frozen summary support')
            for k in ('mean','median','sample_sd','min','max'):
                require(text(row[k])==frozen[k],'15B summary reconciliation '+k)
            checks.append(dict(scenario=row['scenario'],method=row['method'],feature=row['feature'],metric=row['metric'],analysis_scope=row['analysis_scope'],all_five_statistics_identical=True))
    for row in event_summary:
        frozen=next(r for r in tables['event_descriptive_summary'] if all(r[k]==row[k] for k in ('scenario','method','feature')))
        require(row['events_detected']==frozen['events_detected'] and row['events_missed']==frozen['events_missed'],'event supports')
        for k in ('mean','median','sample_sd','min','max'):require(text(row[k])==frozen[k+'_delay'],'frozen event delay summary')
        checks.append(dict(scenario=row['scenario'],method=row['method'],feature=row['feature'],metric='detection_delay_seconds',analysis_scope='PRIMARY',all_five_statistics_identical=True))
    return checks


def persistence(bundle):
    tables=bundle['tables'];window={(r['seed'],r['scenario'],r['method'],r['feature']):r for r in tables['window_metrics_per_run']}
    events={(r['seed'],r['scenario'],r['method'],r['feature']):r for r in tables['event_metrics_per_run']}
    entry_by={(e['seed'],e['scenario']):e for e in bundle['entries'].values()}
    baseline={f:checked(ref)['parameters'] for f,ref in bundle['calibration']['zscore_baseline_models'].items()}
    selected_seed=min(bundle['seeds']);temporal=[];records=[];cache={};consumed={}
    def source(entry,method,feature):
        key=(entry['campaign_entry'],method,feature)
        if key not in cache:
            path=bundle['afiles'][key];data=read(path);consumed[str(path.relative_to(ROOT))]=sha(path)
            # Inspect only observations already stored in Stage15A. Verify against
            # the referenced observed Stage10 scalar column, without extraction.
            ref=data['lineage']['source']['feature_table'];csv_path=ROOT/ref['path'];require(sha(csv_path)==ref['sha256'],'observed feature lineage')
            with csv_path.open(newline='') as stream:raw=list(csv.DictReader(stream))
            require(len(data['records'])==144 and len(raw)>=144,'observed horizon')
            for i,r in enumerate(data['records']):
                require(number(r['observation_value'])==number(None if raw[i][feature]=='' else raw[i][feature]),'stored observation differs from Stage10')
            cache[key]=data
        return cache[key]
    for row in tables['post_event_metrics_per_run']:
        seed,scenario,method,feature=(row[k] for k in ('seed','scenario','method','feature'))
        entry=entry_by[seed,scenario];bentry=entry_by[seed,'B'];data=source(entry,method,feature);bdata=source(bentry,method,feature)
        event=events[seed,scenario,method,feature];start=number(row['interval_start']);mu=number(baseline[feature]['mu'])
        chosen=[r for r in data['records'] if number(r['window_start_seconds'])>=start and number(r['window_end_seconds'])<=144]
        positives=[r for r in chosen if r['decision'] is True];available=[r for r in chosen if r['decision'] is not None]
        require(len(positives)==row['post_event_positive_decisions'] and len(available)==row['post_event_eligible_windows'],'stored decisions/post-event support')
        x=[number(r['observation_value']) for r in chosen];matched_b=[number(bdata['records'][r['window_index']]['observation_value']) for r in chosen]
        scores=[number(r['score']) for r in chosen];d=describe(x);bd=describe(matched_b)
        score_values=[s for s in scores if s is not None]
        under=[r for r in positives if r['observation_value'] is not None and number(r['observation_value'])<=mu]
        record=dict(run_id=row['run_id'],campaign_entry=row['campaign_entry'],seed=seed,scenario=scenario,method=method,feature=feature,
            analysis_scope='POST_EVENT_MECHANISM_DIAGNOSTIC',b_primary_fpr=exact_metric(window[seed,'B',method,feature],'fpr'),
            scenario_primary_fpr=exact_metric(window[seed,scenario,method,feature],'fpr'),post_event_alarm_rate=exact_metric(row,'post_event_alarm_rate'),
            post_candidate_n=len(chosen),post_available_n=len(available),post_positive_n=len(positives),
            post_observed_n=d['defined_n'],matched_B_observed_n=bd['defined_n'],post_feature_mean=d['mean'],matched_B_feature_mean=bd['mean'],
            post_minus_matched_B_feature_mean=None if d['mean'] is None or bd['mean'] is None else d['mean']-bd['mean'],
            frozen_baseline_mean=mu,post_positive_observation_at_or_below_baseline_mean_n=len(under),
            post_positive_with_observation_n=sum(r['observation_value'] is not None for r in positives),
            first_available_post_score=score_values[0] if score_values else None,last_available_post_score=score_values[-1] if score_values else None,
            min_post_score=min(score_values) if score_values else None,max_post_score=max(score_values) if score_values else None,
            stored_threshold=number(data['threshold']),last_primary_decision=data['records'][-1]['decision'],last_observation=number(data['records'][-1]['observation_value']))
        records.append(record)
    for scenario in 'BCP':
        entry=entry_by[selected_seed,scenario]
        for method in METHODS:
            for feature in FEATURES:
                data=source(entry,method,feature)
                ev=events.get((selected_seed,scenario,method,feature))
                for r in data['records']:
                    temporal.append(dict(seed=selected_seed,scenario=scenario,method=method,feature=feature,**r,
                        actual_start=None if ev is None else ev['actual_start'],actual_end=None if ev is None else ev['actual_end'],threshold=data['threshold']))
    group=defaultdict(list)
    for r in records:group[r['scenario'],r['method'],r['feature']].append(r)
    mechanism_summary=[]
    for (scenario,method,feature),rows in sorted(group.items()):
        pos=sum(r['post_positive_n'] for r in rows);low=sum(r['post_positive_observation_at_or_below_baseline_mean_n'] for r in rows)
        mechanism_summary.append(dict(scenario=scenario,method=method,feature=feature,runs_n=16,
            runs_last_primary_decision_positive=sum(r['last_primary_decision'] is True for r in rows),
            runs_last_primary_decision_unavailable=sum(r['last_primary_decision'] is None for r in rows),
            post_positive_observation_n=pos,post_positive_at_or_below_baseline_mean_n=low,
            pooled_window_diagnostic_fraction=Fraction(low,pos) if pos else None,
            diagnostic_role='SUPPLEMENTARY_WINDOW_COUNTS_NOT_INDEPENDENT_REPLICATES',
            raw_post_minus_matched_B_run_mean=describe([r['post_minus_matched_B_feature_mean'] for r in rows]),
            post_alarm_rate_run_summary=describe([r['post_event_alarm_rate'] for r in rows])))
    return records,mechanism_summary,temporal,selected_seed,consumed


def build_tables(bundle):
    t=bundle['tables'];primary=summarize(t['window_metrics_per_run'],WINDOW_METRICS,'PRIMARY')
    startup=summarize(t['startup_diagnostic_per_run'],WINDOW_METRICS,'STARTUP_DIAGNOSTIC')
    post=summarize(t['post_event_metrics_per_run'],POST_METRICS,'PRIMARY')
    event_summary=[]
    for (scenario,method,feature),rows in sorted(grouped(t['event_metrics_per_run']).items()):
        detected=[r for r in rows if r['event_detected']]
        event_summary.append(dict(scenario=scenario,method=method,feature=feature,events_evaluated=16,
            events_detected=len(detected),events_missed=16-len(detected),event_detection_rate=Fraction(len(detected),16),
            detected_seeds=[r['seed'] for r in detected],missed_seeds=[r['seed'] for r in rows if not r['event_detected']],
            **describe([number(r['detection_delay_seconds']) for r in rows])))
    checks=reconciliation(primary+post,event_summary,t)+reconciliation(startup,[],t)
    require(len(checks)==560,'all 15B summaries reconciled')
    pairs,delay_pairs,pair_summary=paired_results(t)
    mechanisms,mechanism_summary,temporal,selected_seed,consumed=persistence(bundle)
    results=dict(primary_per_run=t['window_metrics_per_run'],startup_per_run=t['startup_diagnostic_per_run'],
        event_per_run=t['event_metrics_per_run'],post_event_per_run=t['post_event_metrics_per_run'],
        primary_descriptive=primary,startup_descriptive=startup,post_event_descriptive=post,event_descriptive=event_summary,
        paired_p_minus_c=pairs,paired_delay_detected_both=delay_pairs,paired_descriptive=pair_summary,
        persistence_per_run=mechanisms,persistence_mechanism_summary=mechanism_summary,temporal_example=temporal,
        reconciliation=checks)
    return results,dict(example_seed=selected_seed,example_selection='minimum seed among all 16 frozen paired eligible B/C/P seeds, independent of performance',consumed_series=consumed)


def csv_bytes(rows):
    if not rows:return b''
    fields=list(rows[0]);stream=io.StringIO(newline='');writer=csv.DictWriter(stream,fieldnames=fields,lineterminator='\n');writer.writeheader()
    for row in rows:
        d=plain(row);writer.writerow({k:'' if v is None else str(v).lower() if type(v) is bool else json.dumps(v,sort_keys=True,separators=(',',':')) if isinstance(v,(list,dict)) else v for k,v in d.items()})
    return stream.getvalue().encode()


def write_new(path,data,verify=False):
    if path.exists():require(path.read_bytes()==data,'existing Stage15C artifact differs '+str(path))
    else:
        require(not verify,'missing delivered artifact '+str(path));path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('xb') as f:f.write(data)


def execute(verify=False,tables_only=False):
    bundle=preflight();data,meta=build_tables(bundle)
    payloads={'tables/'+name+'.csv':csv_bytes(rows) for name,rows in data.items()}
    payloads['analysis_tables.json']=encode(data)
    # Repeat table construction before publication; no fit/scoring/evaluation calls.
    repeated,_=build_tables(bundle);require(encode(data)==encode(repeated),'nondeterministic descriptive tables')
    for name,payload in payloads.items():write_new(OUTPUT/name,payload,verify)
    if not tables_only:
        from experiments.stage15c_figures import render
        from experiments.stage15c_report import report
        for name,payload in render(data,meta).items():write_new(OUTPUT/name,payload,verify);payloads[name]=payload
        payloads['relatorio_cientifico.md']=report(data,meta,bundle).encode()
        write_new(OUTPUT/'relatorio_cientifico.md',payloads['relatorio_cientifico.md'],verify)
    after=preflight();require(bundle['inputs']==after['inputs'],'input authority changed during analysis')
    outputs=[dict(path=name,sha256=hashlib.sha256(value).hexdigest(),bytes=len(value)) for name,value in sorted(payloads.items())]
    codepaths=[Path(__file__),ROOT/'experiments/stage15c_figures.py',ROOT/'experiments/stage15c_report.py',ROOT/'tests/test_stage15c_analysis.py']
    manifest=dict(schema_version=1,stage='15C',status='DELIVERED_FOR_SCIENTIFIC_REVIEW',not_frozen=True,
        inputs=bundle['inputs'],stage15b_closing_commit=CLOSING_COMMIT,
        execution_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        source_sha256={str(p.relative_to(ROOT)):sha(p) for p in codepaths if p.exists()},
        quantile_convention=QUANTILES,summary_arithmetic='Exact frozen per-run count ratios; no intermediate ratio rounding; Decimal 50 digits HALF_EVEN for serialization/sqrt',
        experimental_unit='run/seed',runs=48,paired_seeds=16,primary_evaluations=960,startup_evaluations=960,event_evaluations=640,post_event_evaluations=640,
        example=meta,table_reproduction='byte-identical repeated construction',reconciled_frozen_summaries=len(data['reconciliation']),
        python_version=sys.version,quantile_sd_are_descriptive_not_confidence_intervals=True,
        documentation_inputs={p:sha(ROOT/p) for p in ('docs/stage14_test_evaluation_protocol_v1.md','docs/stage15a_frozen_test_scoring.md','docs/stage15b_frozen_test_evaluation.md')},
        plotting_versions=({name:__import__(name).__version__ for name in ('matplotlib','numpy')} if not tables_only else {}),
        figures_complete=not tables_only,outputs=outputs,outputs_set_sha256=digest(outputs),
        no_new_scores=True,no_new_decisions=True,no_new_thresholds=True,no_GT_changes=True,no_posthoc_run_exclusions=True,
        entry29_C_included=True,parameter_changes=False,test_calibration=False,hypothesis_testing=False,p_values=False,bootstrap=False,confidence_intervals=False,
        global_ranking=False,commit_created=False,push=False,
        agent_instructions='No AGENTS.md found in repository or checked ancestors; local frozen protocols and stage closure documents read.')
    write_new(OUTPUT/'stage15c_analysis_manifest.json',encode(manifest),verify)
    return dict(status=manifest['status'],manifest_sha256=sha(OUTPUT/'stage15c_analysis_manifest.json'),table_rows={k:len(v) for k,v in data.items()},outputs=len(outputs),example_seed=meta['example_seed'])


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--verify',action='store_true');parser.add_argument('--preflight-only',action='store_true');args=parser.parse_args()
    try:
        with analysis_only():
            if args.preflight_only:
                b=preflight();result=dict(status='PREFLIGHT_PASSED',runs=len(b['entries']),primary_rows=len(b['tables']['window_metrics_per_run']))
            else:result=execute(verify=args.verify)
        print(json.dumps(result,indent=2))
    except Exception as exc:
        # Never repair scientific inputs or produce conclusions after failure.
        raise SystemExit('STOP: '+str(exc)) from exc
