"""N1/N2 lifecycle adaptation; frozen CSV/journal reconciliation and service rules."""
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit
import json
from types import SimpleNamespace
from experiments import development_d3 as old
from experiments import development_d3_minimal as base
from simulator.request_logger import REQUEST_FIELDS
from simulator.ground_truth import EVENT_FIELDS
from simulator.source_manager import worker_quotas
from simulator.source_aggregate import reconcile as reconcile_event
read=old.read
number=old.number
load_requests=old.load_requests
csv_rows=old.csv_rows
equal=old.equal
START_FIELDS=old.START_FIELDS
END_FIELDS=old.END_FIELDS

def reconcile(raw, config):
    """Missing rows/finishes are not silently converted to open requests.

    Worker indices are scoped by generator (normal_1 and attack_1 both use 0).
    Global attack context is recomputed by aggregation; local context is not
    compared to it. All other scientific fields are reconciled independently.
    """
    raw = Path(raw)
    status, inventory = read(raw / 'run_status.json'), read(raw / 'source_inventory.json')
    run = status['run_id']
    expected = {f'normal_{i+1}': ('normal', 'benign', i) for i in range(4)}
    if config.attack.enabled:
        expected.update({f'attack_{i+1}': ('attack', 'attack', i) for i in range(config.attack.attackers)})
    if len(inventory) != len(expected) or {s['source_id'] for s in inventory} != set(expected):
        raise ValueError('Inventory must match configured benign and offensive origins')
    requests = load_requests(raw / 'request_log.csv', run)
    rows = {r['request_id']: r for r in csv_rows(raw / 'request_log.csv', REQUEST_FIELDS)}
    begins, finishes, local, origins, closures, admissions = {}, {}, {}, {}, [], []
    controlled = True
    for source in inventory:
        sid = source['source_id']
        generator, cls, worker = expected[sid]
        if (source['run_id'] != run or source['source_type'] != generator
                or source['traffic_class'] != cls or source['worker_index'] != worker):
            raise ValueError('Inventory class/run/source identity mismatch')
        budget = config.attack.max_concurrent_sends if cls=='attack' else config.normal_traffic.max_concurrent_sends
        count = config.attack.attackers if cls=='attack' else config.normal_traffic.clients
        if source['send_workers'] != worker_quotas(budget,count)[worker]:raise ValueError('Inventory worker quota mismatch')
        output = raw / 'source_artifacts' / sid / 'output'
        lines = (output / 'journal.jsonl').read_text().splitlines(keepends=True)
        if not lines or any(not x.endswith('\n') for x in lines):
            raise ValueError('Missing/truncated journal: ' + sid)
        items = [json.loads(x) for x in lines]
        if any(x['sequence'] != i or x['source_id'] != sid or x['run_id'] != run for i, x in enumerate(items, 1)):
            raise ValueError('Journal sequence/run/source mismatch')
        closed = [x['payload'] for x in items if x['kind'] == 'source_closed']
        if len(closed) != 1 or items[-1]['kind'] != 'source_closed':
            raise ValueError('Missing/duplicate/nonfinal source_closed: ' + sid)
        closure = closed[0]
        final, state = read(output / 'final_status.json'), source['status_final']
        if any(final.get(k) != state.get(k) for k in ('source_id', 'run_id', 'drained', 'logger_complete')):
            raise ValueError('Final status disagrees with source inventory')
        if final.get('source_id') != sid or final.get('run_id') != run:
            raise ValueError('Final status identity mismatch')
        if any(closure.get(k) != final.get(k) for k in ('drained', 'logger_complete')):
            raise ValueError('Closure disagrees with final status')
        # logger_complete=False also occurs for persisted incomplete attempts;
        # row/journal reconciliation below decides whether records were lost.
        controlled &= bool(closure['drained'] and closure['logger_complete'] and not state['forced'] and state['exit_code'] == 0)
        end = number(closure['elapsed_seconds'])
        nominal_close = 270 if generator == 'attack' else 390
        if end <= 0:
            raise ValueError('Invalid observed source closure')
        within_budget = nominal_close <= end <= nominal_close + 30
        controlled &= within_budget
        closures.append(dict(source_id=sid, within_reserved_lifecycle=within_budget, **closure))
        own = []
        for item in items:
            kind, payload = item['kind'], item['payload']
            if kind not in ('request_begin', 'request_finish'):
                continue
            rid = payload['request_id']
            table = begins if kind == 'request_begin' else finishes
            if (rid in table or not rid.startswith('request_' + sid + '_') or payload['run_id'] != run
                    or payload['worker_id'] != worker or payload['generator'] != generator or payload['traffic_class'] != cls):
                raise ValueError('Duplicate or mismatched journal request origin')
            if number(payload['elapsed_seconds']) >= end or (kind == 'request_finish' and number(payload['end_elapsed_seconds']) > end):
                raise ValueError('Request after its source closure')
            if kind == 'request_begin':
                origins[rid] = sid
                own.append(payload)
            table[rid] = payload
        local_rows = csv_rows(output / 'local_requests.csv', REQUEST_FIELDS)
        # Validate incomplete and terminal contracts locally as well.
        load_requests(output / 'local_requests.csv', run)
        if {r['request_id'] for r in local_rows} != {r['request_id'] for r in own} or len(local_rows) != len(own):
            raise ValueError('Local CSV lost/duplicated records: ' + sid)
        for row in local_rows:
            if row['request_id'] in local:
                raise ValueError('Duplicate local request')
            local[row['request_id']] = row
        if generator == 'attack':
            admitted = [x['payload'] for x in items if x['kind'] == 'admission']
            abandoned = [x['payload'] for x in items if x['kind'] == 'abandoned_admission']
            net_admissions = Counter(x['event_id'] for x in admitted)
            net_admissions.subtract(Counter(x['event_id'] for x in abandoned))
            if (net_admissions != Counter(r['event_id'] for r in own)
                    or any(number(x['elapsed_seconds']) < 150 for x in admitted)):
                raise ValueError('Attack admission/start correspondence mismatch')
            admissions.append(dict(source_id=sid, admitted=len(admitted), abandoned=len(abandoned), started=len(own)))
    if set(rows) != set(begins) or set(rows) != set(local) or set(finishes) - set(begins):
        raise ValueError('Missing/extra journal or aggregate CSV records')
    for rid, row in rows.items():
        if any(not equal(k, row[k], begins[rid].get(k)) for k in START_FIELDS):
            raise ValueError('Begin and aggregate CSV fields disagree: ' + rid)
        if any(not equal(k, row[k], local[rid].get(k)) for k in END_FIELDS):
            raise ValueError('Local and aggregate CSV fields disagree: ' + rid)
        if (row['outcome'] == 'incomplete') != (rid not in finishes):
            raise ValueError('Missing finish for terminal row or fabricated finish for incomplete')
        if rid in finishes and any(not equal(k, row[k], finishes[rid].get(k)) for k in END_FIELDS):
            raise ValueError('Finish and aggregate CSV fields disagree: ' + rid)
        endpoint = config.normal_traffic.endpoint if row['traffic_class'] == 'benign' else config.attack.endpoint
        if urlsplit(row['target_url']).path != endpoint:
            raise ValueError('Wrong observed endpoint')
    cutoff = max(number(c['elapsed_seconds']) for c in closures)
    return dict(run_id=run, cutoff=cutoff, closures=closures, controlled_closure=controlled,
                starts=len(rows), known_ends=len(finishes), open_without_end=len(rows)-len(finishes),
                records_lost=0, origins=origins, admissions=admissions), rows, requests


def validate_ground_truth(raw, config, rows, run):
    events = csv_rows(Path(raw) / 'attack_events.csv', EVENT_FIELDS)
    status = read(Path(raw) / 'run_status.json')
    if len(events) != int(config.attack.enabled):
        raise ValueError('Ground truth must contain zero/control or one/attack event')
    attack = [r for r in rows.values() if r['traffic_class'] == 'attack']
    intervals = []
    for e in events:
        if (e['run_id'] != run or e['experiment_id'] != config.id or e['profile'] != 'continuous'
                or e['event_id'] != 'event_001' or e['attack_id'] != 'attack_001'
                or number(e['scheduled_start_seconds']) != 150 or number(e['scheduled_end_seconds']) != 270):
            raise ValueError('Ground truth identity/profile/schedule mismatch')
        if (number(e['schema_version']) != 1 or number(e['experiment_start_timestamp']) != number(status['experiment_start_timestamp'])
                or number(e['experiment_start_monotonic']) != number(status['experiment_start_monotonic'])):
            raise ValueError('Ground truth anchors mismatch')
        certify_event(raw,config,e,rows,run)
        if not attack:
            raise ValueError('Expected offensive event has no starts')
        start, end = number(e['actual_start_seconds']), number(e['actual_end_seconds'])
        if (start != min(number(r['elapsed_seconds']) for r in attack)
                or number(e['last_request_start_seconds']) != max(number(r['elapsed_seconds']) for r in attack)
                or not 150 <= number(e['activation_requested_seconds']) <= start
                or not 270 <= number(e['stop_requested_seconds']) <= end
                or not start < end <= 420 or any(not start <= number(r['elapsed_seconds']) < end for r in attack)):
            raise ValueError('Ground truth emission milestones disagree with requests')
        known = [number(r['end_elapsed_seconds']) for r in attack if r['end_elapsed_seconds']]
        if e['status'] == 'completed':
            if len(known) != len(attack) or number(e['drained_end_seconds']) != max(known):
                raise ValueError('Ground truth drain differs from last offensive completion')
        elif e['status'] != 'incomplete' or e['drained_end_seconds']:
            raise ValueError('Uncertified event drain/status')
        intervals.append((start, end, e['event_id']))
    for r in rows.values():
        t = number(r['elapsed_seconds'])
        ids = sorted(eid for start, end, eid in intervals if start <= t < end)
        if r['attack_active'] != str(int(bool(ids))) or json.loads(r['active_event_ids']) != ids:
            raise ValueError('Global attack context mismatch')
        if r['traffic_class'] == 'attack':
            if r['attack_id'] != 'attack_001' or r['event_id'] != 'event_001':
                raise ValueError('Attack row lacks originating event')
        elif r['attack_id'] or r['event_id']:
            raise ValueError('Benign request incorrectly attributed to attack event')
    return dict(valid=True, events=events, actual_emission_intervals=intervals,
                starts_after_nominal_attack_end=sum(number(r['elapsed_seconds']) >= 270 for r in attack))



def certify_event(raw, config, aggregate, rows, run):
    """Check every local certificate before reproducing production aggregation."""
    inventory=read(Path(raw)/'source_inventory.json');journal=[]
    numeric={'schema_version','experiment_start_timestamp','experiment_start_monotonic','scheduled_start_seconds','scheduled_end_seconds','activation_requested_seconds','actual_start_seconds','stop_requested_seconds','actual_end_seconds','last_request_start_seconds','drained_end_seconds'}
    def matches(key,a,b):
        if a in ('',None) or b in ('',None):return a in ('',None) and b in ('',None)
        return number(a)==number(b) if key in numeric else str(a)==str(b)
    for i in range(config.attack.attackers):
        sid=f'attack_{i+1}';out=Path(raw)/'source_artifacts'/sid/'output'
        local=csv_rows(out/'local_events.csv',EVENT_FIELDS)
        items=[json.loads(x) for x in (out/'journal.jsonl').read_text().splitlines()]
        journal+=items
        snapshots=[x['payload'] for x in items if x['kind']=='event_snapshot']
        closed=[x['payload'] for x in items if x['kind']=='emission_closed']
        if len(local)!=1 or not snapshots or len(closed)!=1:raise ValueError('Missing local emission certificate: '+sid)
        event=local[0]
        if any(not matches(k,event[k],p.get(k)) for p in (snapshots[-1],closed[0]) for k in EVENT_FIELDS):raise ValueError('Local event certificate mismatch: '+sid)
        for key in ('schema_version','experiment_id','run_id','experiment_start_timestamp','experiment_start_monotonic','attack_id','event_id','profile','scheduled_start_seconds','scheduled_end_seconds'):
            if not matches(key,event[key],aggregate[key]):raise ValueError('Local event identity/anchors mismatch: '+sid)
        own=[r for r in rows.values() if r['request_id'].startswith('request_'+sid+'_')]
        if not own:raise ValueError('Origin has no offensive starts: '+sid)
        start,end=number(event['actual_start_seconds']),number(event['actual_end_seconds'])
        if (start!=min(number(r['elapsed_seconds']) for r in own)
            or number(event['last_request_start_seconds'])!=max(number(r['elapsed_seconds']) for r in own)
            or not 150<=number(event['activation_requested_seconds'])<=start
            or not 270<=number(event['stop_requested_seconds'])<=end<=420
            or any(not start<=number(r['elapsed_seconds'])<end for r in own)
            or any(number(x['payload']['elapsed_seconds'])>number(event['stop_requested_seconds']) for x in items if x['kind']=='admission')):
            raise ValueError('Local emission milestones mismatch: '+sid)
        closure=next(x['payload'] for x in items if x['kind']=='source_closed')
        if end>number(closure['elapsed_seconds']):raise ValueError('Emission certificate after source closure: '+sid)
        known=[number(r['end_elapsed_seconds']) for r in own if r['end_elapsed_seconds']]
        if event['status']=='completed':
            if len(known)!=len(own) or number(event['drained_end_seconds'])!=max(known):raise ValueError('Local drain mismatch: '+sid)
        elif event['status']!='incomplete' or event['drained_end_seconds']:raise ValueError('Uncertified local drain: '+sid)
        # CSV parsing represents numeric fields as strings; production uses numbers.
        for item in items:
            if item['kind'] in ('event_snapshot','emission_closed'):
                for key in numeric:
                    value=item['payload'].get(key)
                    item['payload'][key]=None if value in ('',None) else number(value)
    event=SimpleNamespace(row=dict(aggregate),accepting=True)
    truth=SimpleNamespace(_events={'event_001':event},persist=lambda:None)
    reconcile_event(truth,inventory,journal,final=True)
    if any(not matches(k,aggregate[k],event.row[k]) for k in EVENT_FIELDS):raise ValueError('Global event differs from all-origin certificates')


def generator_evidence(raw,rows,origins):
    cfg=base.ExperimentConfig.load(Path(raw)/'effective_config.json')
    # Reuse the established delay diagnostic per origin, then expose all origins.
    inventory=read(Path(raw)/'source_inventory.json');rates=[];admissions=[]
    for cls,rate,count,prefix in (('benign',cfg.normal_traffic.rate,cfg.normal_traffic.clients,'normal'),('attack',cfg.attack.rate,cfg.attack.attackers,'attack')):
        for phase,a,b in (('PRE',30,150),('ACTIVE',150,270),('POST',270,390)):
            if cls=='attack' and phase!='ACTIVE':continue
            per=[]
            for i in range(count):
                sid=f'{prefix}_{i+1}'
                n=sum(r['traffic_class']==cls and origins[r['request_id']]==sid and a<=r['start']<b for r in rows)
                per.append(dict(source_id=sid,starts=n,nominal_expected=(b-a)*rate,nominal_rps=rate,
                    observed_start_rps=base.ratio(n,b-a),starts_over_nominal_expectation=base.ratio(n,(b-a)*rate)))
            n=sum(x['starts'] for x in per)
            rates.append(dict(traffic_class=cls,phase=phase,starts=n,nominal_expected=(b-a)*rate*count,
                starts_over_nominal_expectation=base.ratio(n,(b-a)*rate*count),per_origin=per))
    for source in inventory:
        if source['source_type']!='attack':continue
        items=[json.loads(x) for x in (Path(raw)/'source_artifacts'/source['source_id']/'output/journal.jsonl').read_text().splitlines()]
        waiting=[];delays=[];maximum=0;ambiguous=False;admitted=begun=abandoned=0
        for item in items:
            kind,p=item['kind'],item['payload']
            if kind=='admission':admitted+=1;waiting.append(number(p['elapsed_seconds']));maximum=max(maximum,len(waiting))
            elif kind=='request_begin':
                begun+=1
                if len(waiting)==1:delays.append(number(p['elapsed_seconds'])-waiting.pop())
                else:ambiguous=True
            elif kind=='abandoned_admission':abandoned+=1;ambiguous=True
        paired=not ambiguous and not waiting and len(delays)==begun and abandoned==0
        admissions.append(dict(source_id=source['source_id'],send_workers=source['send_workers'],admitted=admitted,started=begun,abandoned=abandoned,
            max_unmatched=maximum,uniquely_paired_in_this_trace=paired,admission_to_begin_ms=dict(n=len(delays),
                p50=base.quantile([x*1000 for x in delays],'.5') if paired else None,
                p95=base.quantile([x*1000 for x in delays],'.95') if paired else None)))
    return dict(full_scheduled_load_verified=False,legitimate_opportunity_schedule='not_recorded',legitimate_submission_and_queue_delay='not_recorded',
        configured_offensive_rps=cfg.attack.rate*cfg.attack.attackers,nominal_start_adherence=rates,
        attack_admission=dict(admitted=sum(x['admitted'] for x in admissions),started=sum(x['started'] for x in admissions),
            abandoned=sum(x['abandoned'] for x in admissions),per_origin=admissions),independent_of_service_qualification=True)
