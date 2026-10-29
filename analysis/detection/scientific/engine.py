"""Four-method scientific fitting, replay-by-h calibration, gates and bound runs."""
from dataclasses import replace
from functools import wraps
from decimal import Decimal as D, localcontext
from pathlib import Path

from ..artifacts import publish,open_artifact,encoded,component
from ..contracts import PolicyScore,ObservedSeries
from ..inputs import ContractError,number
from ..detectors._moments import CONTEXT
from ..detectors.zscore import ZScore,zscore_spec
from ..detectors.cov import CoV,cov_spec
from ..detectors.ewma import EWMA,ewma_spec
from ..detectors.cusum import CUSUM,cusum_spec
from ..detectors.cusum_freeze import freeze_spec
from ..cusum_freeze_run import process_series,transition_rows
from ..empirical import quantile_index
from .protocol import SPEC,METHODS,FEATURES,runtime_hashes
from .data import verify_reference


def exact(function):
    @wraps(function)
    def call(*args,**kwargs):
        with localcontext(CONTEXT):return function(*args,**kwargs)
    return call


def check_authority(authority):
    from ..inputs import read_json,digest
    if digest(authority['plan_path'])!=authority['plan_sha256']:raise ContractError('Scientific authority changed')
    plan=read_json(authority['plan_path'])
    if plan['runtime_hashes']!=runtime_hashes():raise ContractError('Code changed after scientific freeze')
    if plan['protocol']!=authority['protocol'] or plan['environment']!=authority['environment']:
        raise ContractError('Scientific protocol/environment authority differs')
    for ref in (plan['protocol'],plan['environment']):
        if digest(ref['path'])!=ref['sha256']:raise ContractError('Scientific contract/environment changed')


def artifact(destination,kind,metadata):
    """Idempotent analysis resume only if the complete deterministic body matches."""
    if 'authority' in metadata:check_authority(metadata['authority'])
    path=Path(destination)
    if path.exists():
        from ..inputs import digest
        a=open_artifact(dict(path=str(path),manifest_sha256=digest(path/'manifest.json')),kind)
        expected=dict(schema_version=1,kind=kind,**metadata,outputs=[])
        if encoded(a.read())!=encoded(expected):raise ContractError('Existing analysis artifact differs; never overwrite')
        return a
    protected=[]
    def roots(value):
        if isinstance(value,dict):
            if 'feature_manifest' in value:protected.append(Path(value['feature_manifest']).parent)
            if 'dataset_manifest' in value:protected.append(Path(value['dataset_manifest']).parent)
            if 'features' in value and 'dataset' in value:
                protected.extend([Path(value['features']),Path(value['dataset'])])
            if 'path' in value and 'manifest_sha256' in value:protected.append(Path(value['path']))
            for child in value.values():roots(child)
        elif isinstance(value,(tuple,list)):
            for child in value:roots(child)
    roots(metadata)
    return publish(path,kind,metadata,protected=protected)


def publish_candidate(destination,metadata,columns,rows):
    check_authority(metadata['authority'])
    from ..inputs import digest
    if Path(destination).exists():
        a=open_artifact(dict(path=str(destination),manifest_sha256=digest(Path(destination)/'manifest.json')),'scientific-h-candidate')
        doc=a.read()
        if encoded({k:v for k,v in doc.items() if k not in ('kind','schema_version','outputs')})!=encoded(metadata):
            raise ContractError('Existing h candidate metadata differs')
        # Compare the deterministic table, including every rejected h trajectory.
        import csv,io
        stream=io.StringIO(newline='');writer=csv.DictWriter(stream,fieldnames=columns,lineterminator='\n')
        writer.writeheader();writer.writerows(rows)
        if (Path(destination)/'transitions.csv').read_text()!=stream.getvalue():raise ContractError('h replay table changed')
        return a
    return publish(destination,'scientific-h-candidate',metadata,table=('transitions.csv',columns,rows),
        protected=[Path(metadata['baseline']['path']),*[Path(s['feature_manifest']).parent for s in metadata['sources']]])


def check_sources(sources,partition,count):
    if len(sources)!=count or any(s.partition!=partition or s.reference['partition']!=partition or s.reference['run_id']!=s.series.run_id for s in sources):raise ContractError('Wrong scientific partition/count')
    if len({s.series.run_id for s in sources})!=count or len({s.reference['seed'] for s in sources})!=count:
        raise ContractError('Scientific sources alias runs/seeds')
    for s in sources:verify_reference(s.reference)
    if any((s.series.family,s.series.feature)!=(sources[0].series.family,sources[0].series.feature) for s in sources):
        raise ContractError('Mixed scientific features')


def selected(rows):return [r for r in rows if number(r['window_start_seconds'])>=30 and number(r['window_end_seconds'])<=390]


def trace(series,method,parameters=None,h=None):
    if method=='cusum-freeze':
        run=process_series(series,h=h,baseline_parameters=parameters)
        return transition_rows(run)
    constructors={'zscore':(ZScore,zscore_spec()),'cov':(CoV,cov_spec(lookback=6)),
        'ewma':(EWMA,ewma_spec()),'cusum-reference':(CUSUM,cusum_spec())}
    if method not in constructors:raise ContractError('Unknown scientific method')
    cls,spec=constructors[method];detector=cls();state=detector.start_run(None if method=='cov' else parameters,spec.config)
    rows=[]
    for observation in series.observations:
        with localcontext(CONTEXT):result=detector.update(observation,state)
        available=observation.window_end_seconds if result.available_at_seconds is None else result.available_at_seconds
        if available<observation.window_end_seconds:raise ContractError('Score available before window end')
        rows.append(dict(window_index=observation.window_index,window_start_seconds=observation.window_start_seconds,
            window_end_seconds=observation.window_end_seconds,score=result.score,
            decision=None if result.score is None or h is None else result.score>number(h),
            available_at_seconds=available,unavailable_reason=result.reason))
    return rows


@exact
def adherence(traces):
    result=[]
    for run_id,rows in traces:
        rows=selected(rows);available=[r for r in rows if r['decision'] is not None]
        result.append(dict(run_id=run_id,expected=360,available=len(available),unavailable=360-len(available),
            available_fraction=D(len(available))/360,fpr=D(sum(r['decision'] for r in available))/len(available) if available else None))
    return result


@exact
def eligible(support,mean_max,run_max):
    values=[number(r['fpr']) for r in support if r['fpr'] is not None]
    return bool(len(values)==len(support) and all(number(r['available_fraction'])>=D('0.95') for r in support)
        and sum(values)/len(values)<=number(mean_max) and max(values)<=number(run_max))


def fit(sources,destination,authority):
    check_sources(sources,'BASELINE',SPEC['counts']['BASELINE'])
    if any(s.reference['authority']!=authority for s in sources):raise ContractError('Baseline authority mismatch')
    support_ok=all(sum(o.value is not None for o in s.series.observations[30:390])>=342 for s in sources)
    series=[replace(s.series,observations=s.series.observations[30:390]) for s in sources]
    try:
        if not support_ok:raise ContractError('Baseline support below 95%')
        parameters=ZScore().fit(tuple(series),zscore_spec().config);reason=None
    except ContractError as exc:
        if sources[0].series.feature=='request_starts':raise
        parameters=None;reason=str(exc)
    return artifact(destination,'scientific-baseline',dict(authority=authority,parameters=parameters,
        feature=list((sources[0].series.family,sources[0].series.feature)),unavailable_reason=reason,sources=[s.reference for s in sources],code=runtime_hashes()))


def model_metadata(model):
    m=model.read('scientific-baseline')
    check_authority(m['authority'])
    if len(m['sources'])!=SPEC['counts']['BASELINE'] or any(ref['partition']!='BASELINE' or ref['authority']!=m['authority'] for ref in m['sources']):raise ContractError('Baseline source partition/authority differs')
    if m['parameters'] is not None:ZScore().start_run(m['parameters'],zscore_spec().config)
    if m['code']!=runtime_hashes():raise ContractError('Baseline processing code changed')
    for ref in m['sources']:verify_reference(ref)
    return m


def calibration_metadata(calibration):
    c=calibration.read('scientific-calibration')
    if c['code']!=runtime_hashes():raise ContractError('Calibration code changed')
    baseline=model_metadata(open_artifact(c['baseline'],'scientific-baseline'))
    if c['authority']!=baseline['authority'] or c['feature']!=baseline['feature'] or len(c['sources'])!=SPEC['counts']['CAL_A']:
        raise ContractError('Calibration model/authority/count differs')
    if any(ref['partition']!='CAL_A' or ref['authority']!=c['authority'] for ref in c['sources']):raise ContractError('Calibration A source membership differs')
    for ref in c['sources']:verify_reference(ref)
    for candidate in c['candidates']:
        ref=candidate['trajectory']
        from ..inputs import digest
        open_artifact(ref,'scientific-h-candidate').read()
    return c


def load_calibration(reference,*,replay=True):
    """Scientific loader: source/h selection replay, never a replacement threshold."""
    a=open_artifact(reference,'scientific-calibration');c=calibration_metadata(a)
    if replay:
        from .data import load_source
        sources=[]
        for ref in c['sources']:
            receipt=dict(entry_id=ref['entry_id'],features=str(Path(ref['feature_manifest']).parent),
                dataset=str(Path(ref['dataset_manifest']).parent),run_id=ref['run_id'],
                feature_manifest_sha256=ref['feature_manifest_sha256'],dataset_manifest_sha256=ref['dataset_manifest_sha256'])
            entry=dict(id=ref['entry_id'],partition='CAL_A',seed=ref['seed'])
            sources.append(load_source(entry,receipt,ref['family'],ref['feature'],authority=c['authority']))
        regenerated=calibrate(sources,open_artifact(c['baseline']),a.root,c['authority'])
        if regenerated.reference!=a.reference:raise ContractError('Calibrated h replay differs')
    return a


@exact
def calibrate(sources,model,destination,authority):
    check_sources(sources,'CAL_A',SPEC['counts']['CAL_A']);m=model_metadata(model)
    if m['authority']!=authority or any(s.reference['authority']!=authority for s in sources):raise ContractError('CAL-A authority mismatch')
    if any(s.series.run_id in {x['run_id'] for x in m['sources']} or s.reference['seed'] in {x['seed'] for x in m['sources']} for s in sources):
        raise ContractError('Calibration overlaps baseline')
    if list((sources[0].series.family,sources[0].series.feature))!=m['feature']:raise ContractError('Baseline feature mismatch')
    thresholds={};diagnostics={};candidate_rows=[];parameters=m['parameters']
    if parameters is None:
        return artifact(destination,'scientific-calibration',dict(authority=authority,baseline=model.reference,
            sources=[s.reference for s in sources],feature=m['feature'],thresholds={method:None for method in METHODS},
            h_reference=None,candidates=[],diagnostics={},eligible=False,reason='SECONDARY_BASELINE_UNAVAILABLE',code=runtime_hashes()))
    def quantile(method):
        traces=[(s.series.run_id,trace(s.series,method,parameters)) for s in sources]
        values=sorted(number(r['score']) for _,rows in traces for r in selected(rows) if r['score'] is not None)
        if not values:return None,traces
        return values[quantile_index(len(values),'0.01')],traces
    for method in ('zscore','cov','ewma'):
        h,traces=quantile(method);thresholds[method]=h
        decided=[(rid,[{**row,'decision':None if row['score'] is None or h is None else number(row['score'])>h} for row in rows]) for rid,rows in traces]
        diagnostics[method]=adherence(decided)
    h_ref,_=quantile('cusum-reference')
    if h_ref is None:
        return artifact(destination,'scientific-calibration',dict(authority=authority,baseline=model.reference,
            sources=[s.reference for s in sources],feature=m['feature'],thresholds={method:None for method in METHODS},
            h_reference=None,candidates=[],diagnostics=diagnostics,eligible=False,reason='NO_AVAILABLE_CALIBRATION_SCORES',code=runtime_hashes()))
    scale=h_ref if h_ref>0 else D(1)
    for multiplier in SPEC['h_grid']:
        with localcontext(CONTEXT):h=scale*D(multiplier)
        traces=[(s.series.run_id,trace(s.series,'cusum-freeze',parameters,h)) for s in sources]
        support=adherence(traces);ok=eligible(support,'0.01','0.05')
        columns=('run_id','window_index','previous_state','candidate','update_accepted','posterior_state','decision','available_at_seconds')
        table_rows=[dict(run_id=rid,**{key:row[key] for key in columns[1:]}) for rid,rows in traces for row in rows]
        candidate=publish_candidate(Path(destination).parent/'calibration-candidates'/f'candidate-{multiplier}',
            dict(authority=authority,baseline=model.reference,sources=[s.reference for s in sources],h=h,component=component(freeze_spec(h=h)),support=support,eligible=ok),
            columns,table_rows)
        candidate_rows.append(dict(h=h,multiplier=multiplier,eligible=ok,support=support,trajectory=candidate.reference))
    candidates=[number(row['h']) for row in candidate_rows if row['eligible']]
    thresholds['cusum-freeze']=min(candidates) if candidates else None
    primary_ok=bool(candidates) and all(eligible(diagnostics[method],'0.01','0.05') for method in ('zscore','cov','ewma'))
    return artifact(destination,'scientific-calibration',dict(authority=authority,baseline=model.reference,
        sources=[s.reference for s in sources],feature=m['feature'],thresholds=thresholds,h_reference=h_ref,
        candidates=candidate_rows,diagnostics=diagnostics,eligible=primary_ok,
        reason=None if primary_ok else 'NO_ELIGIBLE_THRESHOLD_OR_CAL_A_SUPPORT',code=runtime_hashes()))


def components(thresholds):
    return dict(zscore=component(zscore_spec()),cov=component(cov_spec(lookback=6)),ewma=component(ewma_spec()),
        **{'cusum-freeze':None if thresholds['cusum-freeze'] is None else component(freeze_spec(h=thresholds['cusum-freeze']))})


def unavailable_traces(series):
    return {method:[dict(window_index=o.window_index,window_start_seconds=o.window_start_seconds,
        window_end_seconds=o.window_end_seconds,score=None,decision=None,
        available_at_seconds=o.window_end_seconds,unavailable_reason='secondary_not_scientifically_calibrated')
        for o in series.observations] for method in METHODS}


def verification_metadata(verification):
    v=verification.read('scientific-verification')
    if v['code']!=runtime_hashes():raise ContractError('CAL-B code changed')
    c=calibration_metadata(open_artifact(v['calibration']))
    if c['authority']!=v['authority']:raise ContractError('CAL-B calibration authority differs')
    if len({x['seed'] for x in v['sources']})!=SPEC['counts']['CAL_B']:raise ContractError('CAL-B seed aliases')
    if len(v['sources'])!=SPEC['counts']['CAL_B'] or len({r['run_id'] for r in v['sources']})!=SPEC['counts']['CAL_B']:raise ContractError('CAL-B inventory differs')
    for ref in v['sources']:
        verify_reference(ref)
        if ref['partition']!='CAL_B':raise ContractError('Verification source role changed')
    if set(v['support'])!=set(METHODS) or set(v['method_accepted'])!=set(METHODS):raise ContractError('CAL-B method set differs')
    accepted={method:eligible(rows,'0.02','0.05') for method,rows in v['support'].items()}
    if accepted!=v['method_accepted'] or all(accepted.values())!=v['approved']:raise ContractError('CAL-B gate replay differs')
    return v


def process(source,model,calibration,destination,authority,verification=None):
    m=model_metadata(model);c=calibration_metadata(calibration)
    if (c['baseline']!=model.reference or c['feature']!=[source.series.family,source.series.feature]
        or m['authority']!=authority or c['authority']!=authority or source.reference['authority']!=authority):raise ContractError('Calibrated model/authority mismatch')
    if not c['eligible'] and source.series.feature=='request_starts':raise ContractError('CAL-A rejected: no scoring release')
    if source.partition not in ('CAL_B','TEST'):raise ContractError('Scientific score requires CAL_B or TEST')
    inherited=m['sources']+c['sources']
    if source.partition=='TEST':
        if verification is None:raise ContractError('TEST locked: CAL-B acceptance required')
        v=verification_metadata(verification)
        if v['calibration']!=calibration.reference or (not v['approved'] and source.series.feature=='request_starts'):raise ContractError('TEST locked: CAL-B rejected')
        inherited+=v['sources']
    if source.reference['run_id'] in {r['run_id'] for r in inherited} or source.reference['seed'] in {r['seed'] for r in inherited}:
        raise ContractError('Scored source overlaps training/verification')
    verify_reference(source.reference)
    evaluated=c['eligible'] and (verification is None or v['approved'])
    traces={method:trace(source.series,method,m['parameters'],c['thresholds'][method]) for method in METHODS} if evaluated else unavailable_traces(source.series)
    return artifact(destination,'scientific-run',dict(authority=authority,source=source.reference,baseline=model.reference,
        calibration=calibration.reference,verification=None if verification is None else verification.reference,
        methods=traces,components=components(c['thresholds']),evaluated=evaluated,code=runtime_hashes(),availability_basis='simulated_window_closure_not_measured_compute_latency'))


def validate_run(a):
    doc=a.read('scientific-run');c=calibration_metadata(open_artifact(doc['calibration']));m=model_metadata(open_artifact(doc['baseline']))
    if (c['baseline']!=doc['baseline'] or doc['authority']!=c['authority'] or doc['authority']!=m['authority']
        or doc['source']['authority']!=doc['authority'] or c['feature']!=[doc['source']['family'],doc['source']['feature']]):
        raise ContractError('Scientific run ancestry/feature differs')
    if doc['components']!=components(c['thresholds']):raise ContractError('Scientific component/threshold binding changed')
    if doc['code']!=runtime_hashes():raise ContractError('Scientific run code changed')
    verify_reference(doc['source'])
    # Re-open verified scalar values. No labels, roles rewritten, or alternate h.
    from .data import load_source
    ref=doc['source']
    receipt=dict(entry_id=ref['entry_id'],features=str(Path(ref['feature_manifest']).parent),
        dataset=str(Path(ref['dataset_manifest']).parent),feature_manifest_sha256=ref['feature_manifest_sha256'],
        dataset_manifest_sha256=ref['dataset_manifest_sha256'],run_id=ref['run_id'])
    entry=dict(id=ref['entry_id'],partition=ref['partition'],seed=ref['seed'])
    s=load_source(entry,receipt,ref['family'],ref['feature'],authority=doc['authority'],test_release=ref.get('test_release'))
    evaluated=c['eligible']
    if ref['partition']=='TEST':
        verification=verification_metadata(open_artifact(doc['verification']))
        evaluated=evaluated and verification['approved']
    if not evaluated and ref['feature']=='request_starts':raise ContractError('Primary scientific processing not released')
    expected={method:trace(s.series,method,m['parameters'],c['thresholds'][method]) for method in METHODS} if evaluated else unavailable_traces(s.series)
    if doc['evaluated']!=evaluated:raise ContractError('Scientific eligibility changed')
    if encoded(expected)!=encoded(doc['methods']):raise ContractError('Coupled trajectory/decision/availability changed')
    if ref['partition']=='TEST':
        v=open_artifact(doc['verification'],'scientific-verification').read()
        if v['calibration']!=doc['calibration'] or (not v['approved'] and ref['feature']=='request_starts'):raise ContractError('Run lacks valid CAL-B binding')
    return doc


def verify(sources,runs,calibration,destination,authority):
    check_sources(sources,'CAL_B',SPEC['counts']['CAL_B']);c=calibration_metadata(calibration)
    if c['authority']!=authority or any(s.reference['authority']!=authority for s in sources):raise ContractError('CAL-B authority mismatch')
    if not c['eligible'] and sources[0].series.feature=='request_starts':raise ContractError('CAL-A rejection cannot be retuned on B')
    docs=[validate_run(a) for a in runs]
    if len(docs)!=SPEC['counts']['CAL_B'] or {d['source']['run_id'] for d in docs}!={s.series.run_id for s in sources} or any(d['calibration']!=calibration.reference or d['source']['partition']!='CAL_B' for d in docs):
        raise ContractError('CAL-B run/calibration binding differs')
    support={method:adherence([(d['source']['run_id'],d['methods'][method]) for d in docs]) for method in METHODS}
    accepted={method:eligible(rows,'0.02','0.05') for method,rows in support.items()}
    from .statistics import mean_ci
    intervals={method:{**mean_ci([float(number(r['fpr'])) for r in rows if r['fpr'] is not None]),'unit':'CAL_B_run'} for method,rows in support.items()}
    return artifact(destination,'scientific-verification',dict(authority=authority,calibration=calibration.reference,
        sources=[s.reference for s in sources],runs=[a.reference for a in runs],support=support,
        method_accepted=accepted,approved=all(accepted.values()),fpr_intervals=intervals,
        failure_policy=SPEC['cal_b_failure'],code=runtime_hashes()))
