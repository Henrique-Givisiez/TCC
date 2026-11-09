"""Descriptive B2-length pilot analysis; never fits or runs a detector."""
from collections import defaultdict, Counter
from pathlib import Path
import csv
import hashlib
import json
import math
import statistics


def stats(values):
    a=sorted(values)
    return dict(n=len(a),mean=statistics.mean(a) if a else None,
                median=statistics.median(a) if a else None,
                p95=a[math.ceil(.95*len(a))-1] if a else None)


def occupancy(pairs,a,b):
    changes=defaultdict(int)
    for start,end in pairs:
        if end<start:raise ValueError('Negative interval')
        if start<b and end>a:
            changes[max(start,a)]+=1;changes[min(end,b)]-=1
    changes[a]+=0;changes[b]+=0
    current=peak=0;area=two=0;previous=a
    for t,delta in sorted(changes.items()):
        area+=current*(t-previous)
        if current==2:two+=t-previous
        current+=delta;peak=max(peak,current);previous=t
        if current<0:raise ValueError('Negative occupancy')
    return dict(mean=area/(b-a),peak=peak,two_fraction=two/(b-a))


def characterize(raw):
    from experiments.energy_campaign import read
    from experiments.offensive_analysis import classify_operations
    raw=Path(raw);hashes={}
    def text(p):
        data=p.read_bytes();hashes[str(p.resolve())]=hashlib.sha256(data).hexdigest();return data.decode()
    def js(p):return json.loads(text(p))
    def lines(p):return [json.loads(s) for s in text(p).splitlines()]
    cfg=js(raw/'effective_config.json');meta=js(raw/'diagnostics/metadata.json');origin=meta['origin_monotonic']
    if not js(raw/'diagnostics/victim_clock_validation.json')['comparable'] or not js(raw/'source_artifacts/clock_validation.json')['comparable']:
        raise ValueError('Uncertified clocks')
    requests=list(csv.DictReader(text(raw/'request_log.csv').splitlines()))
    events=lines(raw/'diagnostics/victim/events.jsonl');summary=js(raw/'diagnostics/victim/events.summary.json')
    if (not summary['complete'] or not summary['observation_complete'] or summary['dropped'] or summary['write_errors']
        or summary['written']!=len(events) or [e['sequence'] for e in events]!=list(range(1,len(events)+1))):
        raise ValueError('Incomplete victim observation')
    events,classes,correlation=classify_operations(events,requests)
    if correlation['conflicts'] or correlation['requests_without_observed_submission']:
        raise ValueError('Identity correlation failed')
    groups=defaultdict(dict)
    for e in events:
        if e['kind'] in ('work_submitted','work_started','work_completed','work_failed'):
            own=groups[e['operation_id']]
            if e['kind'] in own:raise ValueError('Duplicate event')
            own[e['kind']]=e
    operations=[];unknown=0
    for oid,own in groups.items():
        if set(own)!={'work_submitted','work_started','work_completed'}:raise ValueError('Partial/failed lifecycle: '+oid)
        if classes[oid]=='unknown':unknown+=1;continue
        s,t,u=(own[k] for k in ('work_submitted','work_started','work_completed'))
        if not s['at']<=t['at']<=u['work_started_at']<=u['work_finished_at']:raise ValueError('Invalid work timeline')
        operations.append(dict(cls=classes[oid],request=s['request_id'],s=s['at']-origin,t=t['at']-origin,
            u=u['work_finished_at']-origin,cpu=u['work_cpu_seconds']*1000,
            wall=(u['work_finished_at']-u['work_started_at'])*1000,wait=(t['at']-s['at'])*1000))
    tasks=[];admissions=[];expired=set();plans=[]
    for src in js(raw/'source_inventory.json'):
        sid=src['source_id'];folder=raw/'source_artifacts'/sid/'output';own=defaultdict(dict)
        es=lines(folder/'diagnostics/events.jsonl');ss=js(folder/'diagnostics/events.summary.json')
        if (not ss['complete'] or ss['dropped'] or ss['write_errors'] or ss['written']!=len(es)
            or [e['sequence'] for e in es]!=list(range(1,len(es)+1))):raise ValueError('Incomplete source observation')
        for e in es:
            if e['kind']=='planned':plans.append((sid,e['planned_at']-origin))
            elif e.get('attempt_id') is not None:
                if e['kind'] in own[str(e['attempt_id'])]:raise ValueError('Duplicate source event')
                own[str(e['attempt_id'])][e['kind']]=e
        for aid,v in own.items():
            if not {'submitted','task_started','task_finished'}<=set(v):raise ValueError('Partial task')
            tasks.append(dict(sid=sid,aid=aid,cls='attack' if src['source_type']=='attack' else 'benign',
                s=v['submitted']['at']-origin,t=v['task_started']['at']-origin,u=v['task_finished']['at']-origin,
                h=v['http_started']['at']-origin if 'http_started' in v else None,
                he=v['http_finished']['at']-origin if 'http_finished' in v else None))
        journal=lines(folder/'journal.jsonl')
        if [e['sequence'] for e in journal]!=list(range(1,len(journal)+1)):raise ValueError('Incomplete journal')
        for e in journal:
            if e['kind']=='admission':admissions.append(e['payload']['elapsed_seconds'])
            if e['kind']=='task_resolution' and e['payload']['decision']=='expired_before_http':
                expired.add((sid,str(e['payload']['admission_id'])))
    S=cfg['attack']['start_seconds'];E=S+cfg['attack']['duration_seconds'];T=cfg['duration_seconds'];periods={}
    for name,a,b in [('PRE',0,S),('ACTIVE',S,E),('POST',E,T)]:
        period=dict(bounds=[a,b],classes={})
        for cls in ('benign','attack'):
            co=[o for o in operations if o['cls']==cls and a<=o['s']<b]
            http=[r for r in requests if r['traffic_class']==cls and a<=float(r['elapsed_seconds'])<b]
            ends=[r for r in http if r['end_elapsed_seconds']]
            ok=[r for r in ends if r['http_status'] and 200<=int(r['http_status'])<300]
            ts=[t for t in tasks if t['cls']==cls];tc=[t for t in ts if a<=t['s']<b]
            period['classes'][cls]=dict(submitted=len(co),cohort_started=len(co),cohort_completed=len(co),
                started_in_window=sum(o['cls']==cls and a<=o['t']<b for o in operations),
                completed_in_window=sum(o['cls']==cls and a<=o['u']<b for o in operations),
                submission_rps=len(co)/(b-a),completion_rps=sum(o['cls']==cls and a<=o['u']<b for o in operations)/(b-a),
                cpu_ms=stats([o['cpu'] for o in co]),wall_ms=stats([o['wall'] for o in co]),wait_ms=stats([o['wait'] for o in co]),
                http_starts=len(http),http_rps=len(http)/(b-a),http_2xx=len(ok),
                timeouts=sum('Timeout' in r['error_type'] for r in ends),
                http_errors=sum(bool(r['http_status']) and int(r['http_status'])>=400 for r in ends),
                unfinished=len(http)-len(ends),success_fraction=len(ok)/len(http) if http else None,
                duration_all_ms=stats([float(r['duration_ms']) for r in ends]),
                duration_2xx_ms=stats([float(r['duration_ms']) for r in ok]),
                source_submitted=len(tc),source_dispatched=len(tc),
                planned=sum(a<=t<b and (sid.startswith('attack') if cls=='attack' else sid.startswith('normal')) for sid,t in plans) if cls=='benign' else None,
                admissions=sum(a<=t<b for t in admissions) if cls=='attack' else None,
                expired_submission_cohort=sum((t['sid'],t['aid']) in expired for t in tc),
                dispatch_ms=stats([(t['t']-t['s'])*1000 for t in tc]),
                http_inflight=occupancy([(t['h'],t['he']) for t in ts if t['h'] is not None],a,b))
        period['queue']=dict(waiting=occupancy([(o['s'],o['t']) for o in operations],a,b),
             running=occupancy([(o['t'],o['u']) for o in operations],a,b),
             pending=occupancy([(o['s'],o['u']) for o in operations],a,b),
             pending_end=sum(o['s']<b<=o['u'] for o in operations))
        period['bins10']=[dict(start=i,end=min(i+10,b),pending_end=sum(o['s']<min(i+10,b)<=o['u'] for o in operations),
             submissions=sum(i<=o['s']<min(i+10,b) for o in operations),completions=sum(i<=o['u']<min(i+10,b) for o in operations))
             for i in range(int(a),int(b),10)]
        periods[name]=period
    return dict(run_id=meta['run_id'],periods=periods,unknown_audit_operations=unknown,
         integrity=dict(complete=True,correlated_operations=len(operations)),input_sha256=hashes,
         semantics=dict(cohort='computational_submission',http_cohort='HTTP_start',p95='nearest_rank',
                        drainage='completions after cohort end retained; no HTTP timeout cancellation assumed'))


def analyze_pilots():
    from experiments.energy_campaign import ROOT,IDENTITY,PILOTS,save,digest,read
    out=ROOT/'reports'/IDENTITY
    if out.exists():raise FileExistsError('Pilot report already exists; never overwrite')
    values={}
    for sc in ('A3','F96'):
        receipt=PILOTS/sc/'accepted.json'
        if not receipt.exists():raise ValueError('Accepted pilot required: '+sc)
        if read(receipt)['dataset_sha256']!=digest(PILOTS/sc/'dataset/dataset_manifest.json'):
            raise ValueError('Pilot dataset binding changed')
        values[sc]=characterize(PILOTS/sc/'raw')
    out.mkdir(parents=True,exist_ok=False)
    for sc,v in values.items():save(out/(sc+'.json'),v)
    save(out/'manifest.json',dict(descriptive_only=True,pilot_slots=2,
         files={sc:dict(path=str(out/(sc+'.json')),sha256=digest(out/(sc+'.json'))) for sc in values}))
    return dict(report=str(out),scientific_adequacy_requires_researcher_decision=True)
