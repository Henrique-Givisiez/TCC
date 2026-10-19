"""Frozen TEST evaluation only. Never imports or executes a detector/policy.

The generic framework TEST gates remain unchanged. This scoped adapter consumes
hash-bound Stage15A decision JSON plus original Stage8 event truth/Stage10 labels.
All metric semantics come from the pre-TEST evaluation protocol.
"""
import argparse
from collections import Counter, defaultdict
from contextlib import contextmanager
import csv
from dataclasses import dataclass
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
from fractions import Fraction
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/'experiment_results/stage15b-test-evaluation-20261019'
EXECUTION_PARENT='0edd677d57dccb0bc0c2f513f039b68c21300c16'
COLLECTION_HEAD='f27a5ae6117667f980f6de0217222d25da0e6e42'
COLLECTION='experiment_results/stage14d-test-campaign-20261019'
STAGE15A='experiment_results/stage15a-test-scoring-20261019'
INPUTS={
 'test_inventory':dict(path=COLLECTION+'/test_collection_inventory.json',sha256='10ab05b24e9896d41e944192909f79b366e8cbbe7e08eb24f695b5d2ad1c2b47'),
 'test_collection_freeze':dict(path=COLLECTION+'/test_collection_freeze_manifest.json',sha256='8d784758ff7b751f68dc595d434a65bae1d764d5a21312b0e3d96a5f6613327d'),
 'four_method_freeze':dict(path='experiment_results/stage14-ewma-cusum-calibration-20261019/four_method_calibration_freeze_manifest.json',sha256='898e79394ac48a86a734100d324d0b6b966412166a0eac105dbdeccb2bd236f5'),
 'evaluation_protocol':dict(path='experiments/protocols/stage14_test_evaluation_protocol_v1.json',sha256='c2e1ab6314ab67c984b6b0e8f505982d72ea4de2f463e8607488e73c2764ef20'),
 'provenance_bridge':dict(path='experiment_results/stage15a-preflight-20261019/provenance_bridge.json',sha256='9c361e6b873dc39eb7d1d51de4c2b3476260aa25f4959ea126e0e07dd115c7a7'),
 'stage15a_manifest':dict(path=STAGE15A+'/stage15a_scoring_manifest.json',sha256='089a25681dd13810a94a92def805aa9a7e314955ebdcca671d625d959ae3a9d5')}
METHODS=('zscore','cov','ewma','cusum')
FEATURES=('ingress_packet_count','ingress_tcp_payload_length_sum_bytes','request_starts','mean_duration_ms','mean_cpu_percent')
CONTEXT=Context(prec=50,rounding=ROUND_HALF_EVEN)
METRIC_NAMES=('precision','recall','f1','fpr')
SEMANTICS=dict(primary_horizon=[48,144],startup_horizon=[0,48],whole_windows=True,
 overlap=dict(benign='==0',attack='==1',boundary='0<overlap<1; excluded'),
 unavailable='Excluded from confusion matrix; count separately by benign/attack/boundary truth group',
 precision='TP/(TP+FP)',recall='TP/(TP+FN)',f1='2*TP/(2*TP+FP+FN)',fpr='FP/(FP+TN)',
 undefined='null (CSV empty cell); never imputed zero',
 event='positive available primary observation-window overlap with global [actual_start,actual_end); no availability deadline',
 delay='min(eligible available_at)-actual_start; misses null',
 post_event='whole windows in [max(actual_end,48),144); positive/available; unavailable counted separately',
 summaries='run/seed; defined values only, defined/undefined counts and seed identities; sample SD ddof=1',
 arithmetic='Exact Fraction from decimal inputs; 50-digit ROUND_HALF_EVEN only at serialization/square root')


class IntegrityError(ValueError):pass


def require(condition,message):
    if not condition:raise IntegrityError('STOP: '+message)


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def json_read(path):
    def unique(pairs):
        result={}
        for k,v in pairs:
            require(k not in result,'duplicate JSON key');result[k]=v
        return result
    def reject(value):raise IntegrityError('Nonfinite JSON: '+value)
    return json.loads(Path(path).read_text(),object_pairs_hook=unique,parse_float=Decimal,parse_constant=reject)


def fraction(value):
    require(isinstance(value,(str,int,Decimal,Fraction)) and not isinstance(value,bool),'numeric representation')
    if isinstance(value,Fraction):return value
    n=Decimal(str(value));require(n.is_finite(),'nonfinite number')
    return Fraction(n)


def decimal_text(value):
    with localcontext(CONTEXT):return str(Decimal(value.numerator)/Decimal(value.denominator))


def plain(value):
    if isinstance(value,Fraction):return decimal_text(value)
    if isinstance(value,Decimal):return str(value)
    if isinstance(value,dict):return {k:plain(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [plain(v) for v in value]
    return value


def encoded(value):
    return (json.dumps(plain(value),sort_keys=True,indent=2,allow_nan=False)+'\n').encode()


def digest(value):return hashlib.sha256(encoded(value)).hexdigest()


def checked(ref):
    path=ROOT/ref['path'];require(sha(path)==ref['sha256'],'authority hash '+str(path))
    return json_read(path)


def safe_file(root,relative):
    root=Path(root).resolve();p=root/relative
    require(isinstance(relative,str) and not Path(relative).is_absolute() and '..' not in Path(relative).parts,'unsafe relative input')
    require(p.resolve().is_relative_to(root) and p.is_file(),'missing/escaping input')
    require(not any(q.is_symlink() for q in (p,*p.parents) if q!=root),'symlink input')
    return p


@contextmanager
def evaluation_only():
    previous=sys.getprofile()
    def guard(frame,event,arg):
        if event=='call':
            module=frame.f_globals.get('__name__','');name=frame.f_code.co_name
            require(not module.startswith(('analysis.detection.detectors','analysis.detection.empirical','experiments.stage15a_test_scoring')),
                    'scorer/detector/decision policy called')
            require(not (module.startswith('analysis.detection') and name in ('score_run','decide','fit_baseline','calibrate','fit')),'forbidden pipeline phase')
        if previous is not None:previous(frame,event,arg)
    sys.setprofile(guard)
    try:yield
    finally:sys.setprofile(previous)


def validate_protocol(p):
    require(p['status']=='FROZEN' and p['primary_alpha']=='0.01' and p['experimental_unit']=='run/seed','evaluation protocol identity')
    require(p['scenario_CP']['confusion_matrix']=='available decisions on pure windows only; boundary excluded; unavailable excluded and counted separately by truth group','ambiguous unavailable')
    require(p['scenario_CP']['F1']=='2*TP/(2*TP+FP+FN)','F1 semantics')
    require(p['undefined_metrics']['zero_denominator']=='null/undefined; never invent zero','undefined semantics')
    require(p['horizons']['primary_evaluation']==[48,144] and p['horizons']['startup_diagnostic']==[0,48],'horizons')
    require(p['window_ground_truth']['benign']=='overlap == 0' and p['window_ground_truth']['attack']=='overlap == 1'
            and p['window_ground_truth']['boundary_excluded_from_primary_binary_metrics'],'overlap semantics')
    require(p['event_level']['require_available_at_before_or_at_actual_end'] is False
            and p['event_level']['policy']=='global_observation_overlap_decision_availability_v2'
            and p['event_level']['miss_delay'] is None,'event association semantics')
    require(p['post_event']['interval']=='[max(E.actual_end,48),144)' and p['post_event']['zero_denominator'] is None,'post-event semantics')
    require(p['between_seed_statistics']['sample_standard_deviation_ddof']==1,'summary ddof')


def validate_sources():
    docs={key:checked(ref) for key,ref in INPUTS.items()};validate_protocol(docs['evaluation_protocol'])
    inv=docs['test_inventory'];m=docs['stage15a_manifest'];freeze=docs['test_collection_freeze']
    require(freeze['status']=='FROZEN' and freeze['collection_authority_head']==COLLECTION_HEAD and freeze['inventory']==INPUTS['test_inventory'],'collection identity')
    require(m['stage']=='15A' and m['status']=='FROZEN' and m['combinations']==960 and m['test_runs']==48
            and m['primary_configurations']==20 and m['alpha']=='0.01' and m['cov_L']==6 and m['ewma_lambda']=='0.2' and m['cusum_k']=='0.5','15A identity')
    require(m['collection_authority_head']==COLLECTION_HEAD and m['provenance_bridge_sha256']==INPUTS['provenance_bridge']['sha256'],'15A authority')
    for ref in m['inputs'].values():checked(ref)
    for path,expected in m['processing_source_sha256'].items():require(sha(ROOT/path)==expected,'Stage15A code provenance')
    for ref in freeze['authority']['references'].values():checked(ref)
    for key in ('binding','environment','evaluation_protocol','four_method_freeze'):checked(freeze['authority'][key])
    checked(dict(path='experiment_results/stage14d-release-20261019/test_campaign_release_v1.json',sha256='ae4aa451b7088696071fc12ff17557e72c2df0eaa0427d5c8600173d0cc4400e'))
    for config in docs['four_method_freeze']['primary_test_configurations']:
        ref=config['threshold_artifact'];path=Path(ref['path'])/'manifest.json'
        require(sha(path)==ref['manifest_sha256'],'threshold modified')
    for ref in docs['four_method_freeze']['zscore_baseline_models'].values():checked(ref)
    entries=inv['entries'];require(len(entries)==48 and len({e['campaign_entry'] for e in entries})==48,'48 accepted entries')
    require(Counter(e['scenario'] for e in entries)==Counter(B=16,C=16,P=16),'scenario cardinality')
    seeds={e['seed'] for e in entries};require(len(seeds)==16 and seeds==set(docs['evaluation_protocol']['paired_design']['seeds']),'seed identities')
    for seed in seeds:require(Counter(e['scenario'] for e in entries if e['seed']==seed)==Counter('BCP'),'paired seeds')
    for entry in entries:
        require(entry['dataset_valid'] is True and entry['analysis_eligible'] is True,'eligibility')
        root=ROOT/entry['output_path']
        require({str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()}==set(entry['artifacts']),'TEST file set')
        for path,record in entry['artifacts'].items():
            file=safe_file(root,path);require(sha(file)==record['sha256'] and file.stat().st_size==record['size'],'TEST bytes changed')
    expected={(e['campaign_entry'],method,feature) for e in entries for method in METHODS for feature in FEATURES}
    seen=set();outputs=m['outputs'];require(len(outputs)==960,'960 Stage15A outputs')
    for output in outputs:
        key=(output['campaign_entry'],output['method'],output['feature'])
        require(key in expected and key not in seen,'Stage15A duplicate/extra config');seen.add(key)
        path=safe_file(ROOT/STAGE15A,output['path'])
        require(sha(path)==output['sha256'] and path.stat().st_size==output['bytes'],'Stage15A score/decision bytes changed')
    require(seen==expected,'missing Stage15A combination')
    require(digest(outputs)==m['outputs_set_sha256'],'Stage15A output set digest')
    pkeys={(p['method'],p['feature']) for p in docs['evaluation_protocol']['primary_configurations']}
    require(pkeys=={(m,f) for m in METHODS for f in FEATURES} and len(docs['evaluation_protocol']['primary_configurations'])==20,'20 primary configs')
    return docs


@dataclass(frozen=True)
class FrozenDecision:
    index:int
    start:Fraction
    end:Fraction
    available_at:Fraction
    value:bool|None


@dataclass(frozen=True)
class FrozenEvent:
    event_id:str
    start:Fraction
    end:Fraction
    profile:str


@dataclass(frozen=True)
class GroundTruth:
    overlaps:tuple
    event:FrozenEvent|None
    lineage:dict


def load_ground_truth(entry):
    root=ROOT/entry['output_path'];s8=json_read(root/'stage8/dataset_manifest.json');s10=json_read(root/'stage10/feature_manifest.json')
    require(sha(root/'stage8/dataset_manifest.json')==entry['stage8']['sha256'] and sha(root/'stage10/feature_manifest.json')==entry['stage10']['sha256'],'GT manifests')
    require(s10['dataset_manifest_sha256']==entry['stage8']['sha256'] and s8['run_id']==entry['run_identity']==s10['source_run_id'],'GT lineage run')
    event_relative='raw/attacks/attack_events.csv';a=[x for x in s8['files'] if x['path']==event_relative];b=[x for x in s10['input_files'] if x['path']==event_relative]
    require(len(a)==len(b)==1 and all(a[0][k]==b[0][k] for k in ('sha256','bytes')),'GT original lineage')
    event_path=safe_file(root/'stage8',event_relative);require(sha(event_path)==a[0]['sha256'],'GT event hash')
    status=json_read(root/'stage8/metadata/run_status.json')
    require(status['status']=='completed' and status['run_id']==entry['run_identity'],'GT run status')
    for key,value in s10['window']['anchors'].items():require(fraction(status[key])==fraction(value),'GT clock anchors')
    with event_path.open(newline='') as stream:
        reader=csv.DictReader(stream,strict=True);events=[]
        require({'run_id','event_id','actual_start_seconds','actual_end_seconds','profile'}.issubset(reader.fieldnames or []),'GT event schema')
        for row in reader:
            require(None not in row and all(v is not None for v in row.values()),'GT malformed event')
            require(row['run_id']==entry['run_identity'] and row['status']=='completed','GT event run')
            for key in ('experiment_start_timestamp','experiment_start_monotonic'):require(fraction(row[key])==fraction(status[key]),'event clocks')
            event=FrozenEvent(row['event_id'],fraction(row['actual_start_seconds']),fraction(row['actual_end_seconds']),row['profile'])
            require(event.event_id and 0<=event.start<event.end,'ambiguous/empty event association');events.append(event)
    require(len(events)==(0 if entry['scenario']=='B' else 1),'B no event; C/P one global event')
    event=events[0] if events else None
    if event:require(event.profile==('continuous' if entry['scenario']=='C' else 'periodic_burst'),'global event profile')
    label_path=safe_file(root/'stage10','timeseries/labels.csv');record=[x for x in s10['outputs'] if x['path']=='timeseries/labels.csv']
    require(len(record)==1 and sha(label_path)==record[0]['sha256'],'GT label hash')
    schema=json_read(root/'stage10/feature_schema.json')['tables']['labels'];overlaps=[]
    with label_path.open(newline='') as stream:
        reader=csv.DictReader(stream,strict=True);require(reader.fieldnames==[f['name'] for f in schema['fields']],'label schema')
        for i,row in enumerate(reader):
            require(row['run_id']==entry['run_identity'] and row['window_index']==str(i)
                    and fraction(row['window_start_seconds'])==i and fraction(row['window_end_seconds'])==i+1,'GT window alignment')
            v=fraction(row['attack_event_overlap_fraction']);seconds=fraction(row['attack_event_overlap_seconds'])
            require(0<=v<=1 and v==seconds,'GT overlap domain/width')
            expected=Fraction(0) if event is None else max(Fraction(0),min(Fraction(i+1),event.end)-max(Fraction(i),event.start))
            require(v==expected,'Stage10 overlap disagrees with frozen original event')
            overlaps.append(v)
    require(len(overlaps)==s10['window']['windows'] and len(overlaps)>=144,'GT window cardinality')
    return GroundTruth(tuple(overlaps[:144]),event,dict(stage8=entry['stage8'],stage10=entry['stage10'],
        labels=dict(path=str(label_path.relative_to(ROOT)),sha256=sha(label_path)),
        original_events=dict(path=str(event_path.relative_to(ROOT)),sha256=sha(event_path)),
        event_definition='actual_start/actual_end only; drained_end is not an evaluator field'))


def load_decisions(output,entry):
    path=ROOT/STAGE15A/output['path'];require(sha(path)==output['sha256'],'decision source hash')
    data=json_read(path)
    for field,key in [('run_id','run_identity'),('campaign_entry','campaign_entry'),('seed','seed'),('scenario','scenario')]:require(data[field]==entry[key],'decision identity')
    require(data['method']==output['method'] and data['feature']==output['feature'] and data['alpha']=='0.01','decision config')
    require(data['lineage']['source']['stage10_manifest']==entry['stage10'],'decision feature lineage')
    result=[];require(len(data['records'])==144,'decision horizon')
    for i,row in enumerate(data['records']):
        require(row['window_index']==i and fraction(row['window_start_seconds'])==i and fraction(row['window_end_seconds'])==i+1,'decision grid')
        require(row['decision'] is None or type(row['decision']) is bool,'decision type')
        require(row['availability']==(row['decision'] is not None),'decision unavailable contract')
        d=FrozenDecision(i,Fraction(i),Fraction(i+1),fraction(row['available_at']),row['decision'])
        require(d.available_at>=d.end and (not result or d.available_at>=result[-1].available_at),'decision availability')
        result.append(d)
    return tuple(result)


def metadata(entry,output):
    return dict(run_id=entry['run_identity'],campaign_entry=entry['campaign_entry'],seed=entry['seed'],scenario=entry['scenario'],method=output['method'],feature=output['feature'],
        historical_warning_codes=sorted({c['check_id'] for c in entry['stage9_diagnostics'] if not c['passed']}))


def ratios(counts):
    tp,fp,tn,fn=(counts[k] for k in ('TP','FP','TN','FN'))
    denominators=dict(precision=tp+fp,recall=tp+fn,f1=2*tp+fp+fn,fpr=fp+tn)
    numerators=dict(precision=tp,recall=tp,f1=2*tp,fpr=fp)
    reasons=dict(precision='no_predicted_positive',recall='no_available_ground_truth_positive',f1='no_ground_truth_positive_or_predicted_positive',fpr='no_available_benign_decision')
    result={}
    for name in METRIC_NAMES:
        result[name]=Fraction(numerators[name],denominators[name]) if denominators[name] else None
        result[name+'_reason']=None if denominators[name] else reasons[name]
        require(result[name] is None or 0<=result[name]<=1,'metric outside unit interval')
    return result


def window_metrics(decisions,truth,scope):
    require(scope in ('PRIMARY','STARTUP_DIAGNOSTIC'),'explicit analysis scope')
    a,b=(48,144) if scope=='PRIMARY' else (0,48)
    counts=dict(TP=0,FP=0,TN=0,FN=0,eligible_attack_windows=0,eligible_benign_windows=0,
        boundary_excluded_count=0,unavailable_decision_count=0,unavailable_attack_decisions=0,
        unavailable_benign_decisions=0,unavailable_boundary_decisions=0,candidate_decisions=0,valid_decisions=0,
        attack_windows=0,benign_windows=0)
    for d in decisions:
        if not (a<=d.start and d.end<=b):continue
        v=truth.overlaps[d.index];group='benign' if v==0 else 'attack' if v==1 else 'boundary'
        counts['candidate_decisions']+=1
        if group=='boundary':counts['boundary_excluded_count']+=1
        else:counts[group+'_windows']+=1
        if d.value is None:
            counts['unavailable_decision_count']+=1;counts['unavailable_'+group+'_decisions']+=1
            continue
        counts['valid_decisions']+=1
        if group=='boundary':continue
        counts['eligible_'+group+'_windows']+=1
        cell=('TP' if d.value else 'FN') if group=='attack' else ('FP' if d.value else 'TN')
        counts[cell]+=1
    require(counts['candidate_decisions']==b-a,'selected horizon cardinality')
    require(counts['TP']+counts['FN']==counts['eligible_attack_windows'] and counts['FP']+counts['TN']==counts['eligible_benign_windows'],'confusion count invariant')
    require(sum(counts[k] for k in ('eligible_attack_windows','eligible_benign_windows','boundary_excluded_count','unavailable_attack_decisions','unavailable_benign_decisions'))==b-a,'support accounting')
    return dict(analysis_scope=scope,aggregation='PRIMARY_RUN_SEED' if scope=='PRIMARY' else 'STARTUP_DIAGNOSTIC_RUN_SEED',**counts,**ratios(counts))


def event_metrics(decisions,event):
    eligible=[d.available_at for d in decisions if d.value is True and 48<=d.start and d.end<=144 and min(d.end,event.end)>max(d.start,event.start)]
    first=min(eligible) if eligible else None;delay=None if first is None else first-event.start
    require(delay is None or delay>=0,'negative detection delay')
    return dict(analysis_scope='PRIMARY',event_applicable=True,event_id=event.event_id,
        actual_start=event.start,actual_end=event.end,event_detected=first is not None,
        detection_time=first,detection_delay_seconds=delay,event_profile=event.profile,
        event_definition='GLOBAL_ACTUAL_START_TO_ACTUAL_END',time_unit='seconds_since_experiment_start')


def post_event_metrics(decisions,event):
    a=max(event.end,Fraction(48));chosen=[d for d in decisions if a<=d.start and d.end<=144]
    available=[d for d in chosen if d.value is not None];positive=sum(d.value is True for d in available)
    return dict(analysis_scope='PRIMARY',metric_role='POST_EVENT_DIAGNOSTIC',interval_start=a,interval_end=144,
        candidate_post_event_decisions=len(chosen),post_event_eligible_windows=len(available),
        unavailable_post_event_decisions=len(chosen)-len(available),post_event_positive_decisions=positive,
        post_event_alarm_rate=Fraction(positive,len(available)) if available else None,
        post_event_alarm_rate_reason=None if available else 'no_available_post_event_decision')


def describe(values):
    valid=sorted(v for v in values if v is not None);n=len(valid)
    if not n:return dict(mean=None,median=None,sample_sd=None,min=None,max=None)
    mean=sum(valid,Fraction(0))/n;median=valid[n//2] if n%2 else (valid[n//2-1]+valid[n//2])/2
    sd=None
    if n>1:
        variance=sum(((v-mean)**2 for v in valid),Fraction(0))/(n-1)
        with localcontext(CONTEXT):sd=(Decimal(variance.numerator)/Decimal(variance.denominator)).sqrt()
    return dict(mean=mean,median=median,sample_sd=sd,min=valid[0],max=valid[-1])


def group_rows(rows):
    groups=defaultdict(list)
    for row in rows:groups[(row['scenario'],row['method'],row['feature'])].append(row)
    return groups


def summaries(rows,metrics,scope):
    result=[]
    for (scenario,method,feature),group in sorted(group_rows(rows).items()):
        require(len(group)==16 and len({r['seed'] for r in group})==16,'16 independent seed summaries')
        for metric in metrics:
            defined=[r for r in group if r[metric] is not None];undefined=[r for r in group if r[metric] is None]
            result.append(dict(scenario=scenario,method=method,feature=feature,analysis_scope=scope,
                aggregation='RUN_LEVEL_DESCRIPTIVE',experimental_unit='run/seed',metric=metric,defined_n=len(defined),undefined_n=len(undefined),
                defined_seeds=[r['seed'] for r in defined],undefined_seeds=[r['seed'] for r in undefined],**describe([r[metric] for r in group])))
    return result


def aggregate(primary,event_rows,post_rows,startup):
    pooled=[]
    for (scenario,method,feature),group in sorted(group_rows(primary).items()):
        counts={k:sum(r[k] for r in group) for k in ('TP','FP','TN','FN','eligible_attack_windows','eligible_benign_windows','boundary_excluded_count','unavailable_decision_count')}
        pooled.append(dict(scenario=scenario,method=method,feature=feature,analysis_scope='PRIMARY',aggregation='SUPPLEMENTARY_POOLED_WINDOWS',
            experimental_unit='run/seed; windows are not independent replicates',runs=16,**counts,**ratios(counts)))
    event_summary=[]
    for (scenario,method,feature),group in sorted(group_rows(event_rows).items()):
        hits=[r for r in group if r['event_detected']];misses=[r for r in group if not r['event_detected']]
        stats=describe([r['detection_delay_seconds'] for r in hits])
        event_summary.append(dict(scenario=scenario,method=method,feature=feature,analysis_scope='PRIMARY',experimental_unit='run/seed',
            events_total=len(group),events_detected=len(hits),events_missed=len(misses),event_detection_rate=Fraction(len(hits),len(group)),
            detected_n=len(hits),missed_n=len(misses),detected_seeds=[r['seed'] for r in hits],missed_seeds=[r['seed'] for r in misses],
            **{k+'_delay':v for k,v in stats.items()}))
    run_summary=summaries(primary,METRIC_NAMES,'PRIMARY')+summaries(post_rows,('post_event_alarm_rate',),'PRIMARY')
    return dict(window_metrics_pooled=pooled,run_level_descriptive_summary=run_summary,
        event_descriptive_summary=event_summary,startup_descriptive_summary=summaries(startup,METRIC_NAMES,'STARTUP_DIAGNOSTIC'))


def evaluate_all(docs,gt):
    entries={e['campaign_entry']:e for e in docs['test_inventory']['entries']}
    primary=[];startup=[];events=[];post=[];inventory=[]
    for output in docs['stage15a_manifest']['outputs']:
        entry=entries[output['campaign_entry']];truth=gt[entry['campaign_entry']];decisions=load_decisions(output,entry);meta=metadata(entry,output)
        primary.append(dict(**meta,**window_metrics(decisions,truth,'PRIMARY')))
        startup.append(dict(**meta,**window_metrics(decisions,truth,'STARTUP_DIAGNOSTIC')))
        if truth.event is not None:
            events.append(dict(**meta,**event_metrics(decisions,truth.event)));post.append(dict(**meta,**post_event_metrics(decisions,truth.event)))
        inventory.append(dict(**meta,stage15a_output=dict(path=STAGE15A+'/'+output['path'],sha256=output['sha256']),ground_truth=truth.lineage,
            dataset_valid=entry['dataset_valid'],analysis_eligible=entry['analysis_eligible'],event_applicable=truth.event is not None))
    require(len(primary)==len(startup)==960 and len(events)==len(post)==640,'evaluation cardinality')
    require(Counter(r['scenario'] for r in events)==Counter(C=320,P=320),'event scenarios')
    tables=dict(window_metrics_per_run=primary,event_metrics_per_run=events,post_event_metrics_per_run=post,startup_diagnostic_per_run=startup)
    tables.update(aggregate(primary,events,post,startup))
    return tables,inventory


def csv_bytes(rows):
    require(bool(rows),'empty output table');columns=list(rows[0]);require(all(list(r)==columns for r in rows),'table schema')
    stream=io.StringIO(newline='');writer=csv.DictWriter(stream,fieldnames=columns,lineterminator='\n');writer.writeheader()
    for row in rows:
        record=plain(row);writer.writerow({k:('' if v is None else str(v).lower() if type(v) is bool else json.dumps(v,separators=(',',':')) if isinstance(v,(dict,list)) else v) for k,v in record.items()})
    return stream.getvalue().encode()


def sources():
    paths=[Path(__file__),ROOT/'experiments/stage15b_reproduce.py',ROOT/'tests/test_stage15b_evaluation.py']
    return {str(p.relative_to(ROOT)):sha(p) for p in paths}


def preflight():
    docs=validate_sources()
    gt={e['campaign_entry']:load_ground_truth(e) for e in docs['test_inventory']['entries']}
    return docs,gt


def materialize(verify=False):
    require(verify or not OUTPUT.exists(),'Stage15B destination collision; no overwrite')
    docs,gt=preflight()
    # Import only the independent evaluator; never Stage15A executable tooling.
    from experiments.stage15b_reproduce import independent_tables
    execution_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    subprocess.run(['git','merge-base','--is-ancestor',EXECUTION_PARENT,execution_head],cwd=ROOT,check=True)
    if verify:
        original=json_read(OUTPUT/'stage15b_evaluation_manifest.json');execution_head=original['execution_head']
    else:require(execution_head==EXECUTION_PARENT,'unreviewed execution parent')
    source_snapshot=sources();tables,inventory=evaluate_all(docs,gt)
    # Independent algorithms count/classify directly from frozen decisions + GT.
    other=independent_tables(docs,gt)
    require(encoded(tables)==encoded(other),'independent metric reproduction mismatch')
    payloads={name+'.csv':csv_bytes(rows) for name,rows in tables.items()}
    payloads['evaluation_results.json']=encoded(tables)  # Explicit JSON nulls/full precision.
    payloads['evaluation_inventory.json']=encoded(dict(schema_version=1,inputs=INPUTS,semantics=SEMANTICS,entries=inventory))
    if not verify:OUTPUT.mkdir(parents=True,exist_ok=False)
    outputs=[]
    for name,data in payloads.items():
        path=OUTPUT/name
        if verify:require(path.read_bytes()==data,'published evaluation differs '+name)
        else:
            with path.open('xb') as stream:stream.write(data)
        outputs.append(dict(path=name,sha256=hashlib.sha256(data).hexdigest(),bytes=len(data),rows=len(tables[name[:-4]]) if name.endswith('.csv') else None))
    validate_sources();require(sources()==source_snapshot,'evaluator sources changed')
    manifest=dict(schema_version=1,stage='15B',status='FROZEN',inputs=INPUTS,execution_head=execution_head,execution_source_sha256=source_snapshot,
        collection_authority_head=COLLECTION_HEAD,stage15a_commit=EXECUTION_PARENT,
        source_stage15a_manifest_sha256=INPUTS['stage15a_manifest']['sha256'],test_collection_freeze_sha256=INPUTS['test_collection_freeze']['sha256'],
        evaluation_protocol_sha256=INPUTS['evaluation_protocol']['sha256'],primary_evaluation_horizon=[48,144],startup_diagnostic_horizon=[0,48],
        primary_configurations=20,runs=48,B=16,C=16,P=16,unique_paired_seeds=16,primary_run_config_evaluations=960,event_run_config_evaluations=640,
        startup_run_config_evaluations=960,window_evaluation=True,event_evaluation=True,post_event_evaluation=True,
        scores_modified=False,decisions_modified=False,thresholds_modified=False,detectors_reexecuted=False,decision_policy_reexecuted=False,
        test_fitting=False,test_calibration=False,post_test_tuning=False,ground_truth_consumed_by_evaluator=True,
        ground_truth_consumed_by_scorer=False,ground_truth_consumed_by_decision_policy=False,
        scientific_interpretation_performed=False,ranking_performed=False,hypothesis_testing_performed=False,stage15c_started=False,
        semantics=SEMANTICS,metric_definition_source='evaluation_protocol.scenario_CP; direct count-form F1, null only for its zero denominator',
        independent_reproduction='Separate algorithms; exact counts/rational metrics; byte-equivalent canonical tables',
        outputs=outputs,outputs_set_sha256=digest(outputs),csv_null='empty cell; reasons in reason columns; evaluation_results.json contains explicit null',
        experimental_unit='run/seed',pooled_role='SUPPLEMENTARY_POOLED_WINDOWS',all_20_configurations_included=True)
    data=encoded(manifest);mp=OUTPUT/'stage15b_evaluation_manifest.json'
    if verify:require(mp.read_bytes()==data,'evaluation manifest differs')
    else:
        with mp.open('xb') as stream:stream.write(data)
    freeze=dict(schema_version=1,stage='15B',status='FROZEN',inputs=INPUTS,manifest=dict(path=str(mp.relative_to(ROOT)),sha256=sha(mp)),
        evaluation_inventory=dict(path=str((OUTPUT/'evaluation_inventory.json').relative_to(ROOT)),sha256=sha(OUTPUT/'evaluation_inventory.json')),
        semantics_sha256=digest(SEMANTICS),outputs_set_sha256=digest(outputs),execution_source_sha256=source_snapshot,
        independent_reproduction_passed=True,experimental_unit='run/seed',primary_rows=960,event_rows=640,startup_rows=960,
        historical_authorities_unchanged=True,stage15c_authorized=False)
    fp=OUTPUT/'stage15b_evaluation_freeze_manifest.json'
    if verify:require(fp.read_bytes()==encoded(freeze),'evaluation freeze differs')
    else:
        with fp.open('xb') as stream:stream.write(encoded(freeze))
    expected=set(payloads)|{mp.name,fp.name}
    require({p.name for p in OUTPUT.iterdir() if p.is_file()}-{'administrative_finalization.json'}==expected,'extra/missing evaluation artifact')
    return dict(manifest_sha256=sha(mp),freeze_sha256=sha(fp),output_artifacts=len(expected),table_rows={k:len(v) for k,v in tables.items()},independent_reproduction=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--verify',action='store_true');parser.add_argument('--preflight-only',action='store_true');args=parser.parse_args()
    with evaluation_only():
        if args.preflight_only:
            docs,gt=preflight();result=dict(status='PREFLIGHT_PASSED',runs=len(gt),stage15a_outputs=len(docs['stage15a_manifest']['outputs']),metrics_calculated=False)
        else:result=materialize(verify=args.verify)
    print(json.dumps(result,indent=2))
