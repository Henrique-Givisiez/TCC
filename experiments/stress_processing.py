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
    expected = {f'normal_{i+1}': ('normal', 'benign', i) for i in range(config.normal_traffic.clients)}
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
        nominal_close = stop_bound(raw) if generator == 'attack' else 390
        if end <= 0:
            raise ValueError('Invalid observed source closure')
        within_budget = number(nominal_close) <= end <= number(nominal_close) + 30
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
                or not number(stop_bound(raw)) <= number(e['stop_requested_seconds']) <= end
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
        if any(not matches(k,event[k],snapshots[-1].get(k)) for k in EVENT_FIELDS):
            raise ValueError('Final local event snapshot mismatch: '+sid)
        # A certificate closes emission, while already-started HTTP requests can
        # drain later. Identity and emission milestones cannot change afterward.
        invariants=set(EVENT_FIELDS)-{'status','drained_end_seconds'}
        certificate=closed[0]
        if any(not matches(k,event[k],certificate.get(k)) for k in invariants):
            raise ValueError('Local emission invariant mismatch: '+sid)
        emission_index=next(j for j,x in enumerate(items) if x['kind']=='emission_closed')
        final_index=max(j for j,x in enumerate(items) if x['kind']=='event_snapshot')
        if not emission_index<final_index<len(items)-1:
            raise ValueError('Emission/final snapshot/source closure order mismatch: '+sid)
        state=certificate.get('status')
        if state not in ('emission_ended','completed'):
            raise ValueError('Invalid emission certificate state: '+sid)
        evolution=[certificate]+[x['payload'] for x in items[emission_index+1:] if x['kind']=='event_snapshot']
        transitions={'emission_ended':{'emission_ended','completed','incomplete'},
                     'completed':{'completed'},'incomplete':{'incomplete'}}
        for observed in evolution:
            next_state=observed.get('status')
            if next_state not in transitions[state] or any(not matches(k,event[k],observed.get(k)) for k in invariants):
                raise ValueError('Invalid post-emission event evolution: '+sid)
            drain=observed.get('drained_end_seconds')
            if next_state=='completed':
                if drain in ('',None) or not matches('drained_end_seconds',event['drained_end_seconds'],drain):
                    raise ValueError('Completed event drain certificate mismatch: '+sid)
                if observed is certificate and number(drain)>number(certificate['actual_end_seconds']):
                    raise ValueError('Emission prematurely certifies future drain: '+sid)
            elif drain not in ('',None):
                raise ValueError('Noncompleted event has drain certificate: '+sid)
            state=next_state

        for key in ('schema_version','experiment_id','run_id','experiment_start_timestamp','experiment_start_monotonic','attack_id','event_id','profile','scheduled_start_seconds','scheduled_end_seconds'):
            if not matches(key,event[key],aggregate[key]):raise ValueError('Local event identity/anchors mismatch: '+sid)
        own=[r for r in rows.values() if r['request_id'].startswith('request_'+sid+'_')]
        if not own:raise ValueError('Origin has no offensive starts: '+sid)
        start,end=number(event['actual_start_seconds']),number(event['actual_end_seconds'])
        if (start!=min(number(r['elapsed_seconds']) for r in own)
            or number(event['last_request_start_seconds'])!=max(number(r['elapsed_seconds']) for r in own)
            or not 150<=number(event['activation_requested_seconds'])<=start
            or not number(stop_bound(raw))<=number(event['stop_requested_seconds'])<=end<=420
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


def stop_bound(raw):
    path=Path(raw)/'source_artifacts/stress_stop.json'
    if not path.exists(): return 270
    stop=read(path)
    status=read(Path(raw)/'run_status.json')
    if stop['run_id']!=status['run_id'] or stop['reason'] not in ('service_compromise','generator_queue','collection_stale','observer_failure'):
        raise ValueError('invalid stress stop authority')
    if not 0 <= stop['observed_seconds'] <= stop['command_seconds'] <= 390:
        raise ValueError('invalid stress stop clock')
    events=csv_rows(Path(raw)/'attack_events.csv',EVENT_FIELDS)
    if len(events)!=1 or events[0]['end_reason']!='stress_'+stop['reason']:
        raise ValueError('stop reason differs from certified event')
    return stop['command_seconds']
